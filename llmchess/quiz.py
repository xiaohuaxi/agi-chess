"""局面题模式（design.md 第六节组 1）：固定局面、stateless，每次只让模型走一步，引擎事后判这步好坏。

    python3 -m llmchess.quiz run --game xiangqi                 # 30 局面 × 四档 × 2 遍；断点续跑就是再跑一次同一条
    python3 -m llmchess.quiz run --game chess --jobs 4 --efforts medium,high,xhigh,max --reps 2
    python3 -m llmchess.quiz run --game chess --ids c01 --efforts medium --reps 1    # 冒烟
    python3 -m llmchess.quiz run --game xiangqi --ids x01 --dry-run                   # 只打印提示，不调模型
    python3 -m llmchess.quiz judge --game chess                 # 引擎事后判，写 judged.jsonl
    python3 -m llmchess.quiz report                             # 两种棋 × 档位的汇总表

局面在 data/<batch>/<棋种>.jsonl（选取脚本同目录）。记录在 runs/quiz-<batch>/<棋种>/（不入库）：
  每次作答一个文件 <局面id>-<档>-r<遍>.jsonl：config、attempt（和整盘同一格式，由 runner.model_turn 写）、
  pause（撞额度）、最后一行 result。有 result 的就算答完，再跑时跳过；只有 attempt 没 result 的（中途撞额度），
  续跑时接上已用掉的尝试次数（runner.pending_ply），和整盘续跑一样。
  judge 写 judged.jsonl，report 写 report.txt（两种棋都在 runs/quiz-<batch>/ 下）。

提示和整盘对局给模型的完全一样：同一个系统提示（里面「满 200 个半回合判和」之类的整盘规则文字原样保留，没有为局面题改写，
免得两种模式的提示不一样）、该棋种默认 view、history=0（只给当前局面，不附着法历史；「对方刚走」那句保留）。
中国象棋的状态里带着从开局起的全部着法，禁着（长将 / 长捉）照样按完整历史判；只是提示里不给历史。
国际象棋谜题没有开局到这步的着法，状态从谜题 FEN 起、走完对手那一步；回合数改用 FEN 里的真实回合数（见 QuizChess）。

撞额度（claude_cli 抛 Paused）时：不再开新题，已经在跑的等它们答完，退出码 3，下次跑同一条命令接着来。
一次作答里被安全分类器拦或空回复超过 runner.MAX_FLAGS 次，整盘模式会暂停交给人看；局面题里只把这一题记成
「放弃（拦截 / 空回复）」，不拖停整批。

引擎只在 judge 里用，永远不进提示。
"""
import argparse, collections, concurrent.futures, json, math, os, pathlib, re, statistics, sys, tempfile, threading, uuid

import chess
import pyffish as sf

from . import chess_ as C
from . import xiangqi as X
from . import claude_cli, memory, records, runner
from .claude_cli import Paused
from .cli import commit
from .engine import Engine

ROOT = pathlib.Path(__file__).resolve().parent.parent
EFFORTS = ('medium', 'high', 'xhigh', 'max')
GAMES = ('xiangqi', 'chess')


# ---------------------------------------------------------------- 局面与状态
def positions_path(batch, game):
    return ROOT / 'data' / batch / ('%s.jsonl' % game)


def load_positions(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


class QuizChess:
    """国际象棋模块的薄包装，只改一处：render 头一行的回合数。谜题状态里只有对手刚走的那一步，
    chess_.render 按 len(moves) 会写成「第 1 回合（已走 1 个半回合）」，这里换成 FEN 里的真实回合数。其余原样转给 chess_。"""
    _HEAD = re.compile(r'^第 \d+ 回合（已走 \d+ 个半回合）')

    def __getattr__(self, name):
        return getattr(C, name)

    def render(self, st, sc):
        b = st['board']
        ply = 2 * (b.fullmove_number - 1) + (b.turn == chess.BLACK)
        return self._HEAD.sub('第 %d 回合（已走 %d 个半回合）' % (ply // 2 + 1, ply), C.render(st, sc), count=1)


def game_module(game):
    return X if game == 'xiangqi' else QuizChess()


def build_state(pos):
    """题目局面的棋种状态。中国象棋从开局重放全部着法（禁着判定要完整历史）；国际象棋从谜题 FEN 走完对手那步。"""
    if pos['game'] == 'xiangqi':
        st = X.start()
        for m in pos['moves']:
            X.push(st, m)
    else:
        fen0 = pos['fen_before_opp']
        st = {'board': chess.Board(fen0), 'fens': [fen0], 'moves': [], 'record': []}
        C.push(st, pos['opp_move'])
    assert st['fens'][-1].split()[:2] == pos['fen'].split()[:2], ('重放出的局面和题目 FEN 对不上', pos['id'])
    return st


def side_cfg(G, effort):
    """和 cli.side_cfg 默认值一致，只把 history 设成 0、effort 按档位。max_plies 只用来拼系统提示里那句整盘规则。"""
    return {'effort': effort, 'memory': 'stateless', 'view': G.DEFAULT_VIEW.split(','), 'history': 0, 'legal': 'none',
            'selfcheck': 'off', 'recite': 'off', 'notes_keep': 1, 'session_view': 'full', 'max_plies': 200}


def quiz_cfg(G, game, side, effort, model, cwd):
    sc = side_cfg(G, effort)
    player = 'claude:%s' % model
    return {'game': game, 'players': {side: player}, 'sides': {side: sc}, 'retries': 3, 'max_plies': 200,
            'system': {side: G.system_prompt(side, sc, memory.system_text(sc))},
            'commands': {side: claude_cli.shown(claude_cli.command(model, effort, '-'))}, 'claude_cwd': cwd}


def prompt_of(G, st, sc):
    return G.render(st, sc) + '\n\n' + memory.ask(sc)


# ---------------------------------------------------------------- 作答
def answer_path(out, pid, effort, rep):
    return os.path.join(out, '%s-%s-r%d.jsonl' % (pid, effort, rep))


def result_of(path):
    if not os.path.exists(path):
        return None
    return next((r for r in records.read(path) if r['type'] == 'result'), None)


def summarize_attempts(recs, ply):
    """首答：第一次既没被拦、也不是空回复的尝试。"""
    atts = [r for r in recs if r['type'] == 'attempt' and r.get('ply') == ply]
    real = [r for r in atts if not r.get('flagged') and not r.get('empty')]
    first = real[0] if real else None
    return {'attempts': len(atts), 'first_legal': first.get('legal') if first else None,
            'first_move_text': first.get('move_text') if first else None,
            'first_think': (first.get('usage') or {}).get('think') if first else None,
            'first_elapsed': first.get('elapsed') if first else None,
            'illegal_reasons': [r.get('reason') for r in real if not r.get('legal')]}


def answer_one(pos, effort, rep, out, model, cwd, batch_meta):
    """答一题。返回 result；撞额度（非拦截原因的 Paused）照样抛出去。"""
    path = answer_path(out, pos['id'], effort, rep)
    done = result_of(path)
    if done:
        return done
    G = game_module(pos['game'])
    st = build_state(pos)
    side = G.turn(st)
    ply = len(st['moves']) + 1
    cfg = quiz_cfg(G, pos['game'], side, effort, model, cwd)
    ctx = runner.new_ctx(G, cfg, out)
    ctx['st'], ctx['log'] = st, path
    if os.path.exists(path):
        recs = records.read(path)
        ctx['pending'] = runner.pending_ply(recs, ply)
        runner.log(ctx, {'type': 'resume', 'ply': ply})
    else:
        runner.log(ctx, {'type': 'config', 'cfg': cfg, 'pos': pos['id'], 'effort': effort, 'rep': rep,
                         'fen': st['fens'][-1], **batch_meta})
    moves = G.legal(st)
    ban = G.banned(st, moves)
    gave_up = None
    try:
        mv, stat, _ = runner.model_turn(ctx, side, moves, ban)
    except Paused as e:
        recs = records.read(path)
        n_flags = sum(1 for r in recs if r['type'] == 'attempt' and r.get('ply') == ply
                      and (r.get('flagged') or r.get('empty')))
        runner.log(ctx, {'type': 'pause', 'ply': ply, 'why': str(e)})
        if n_flags <= runner.MAX_FLAGS:
            raise                                    # 撞额度 / 连续调不通：整批停
        mv, stat, gave_up = None, None, 'flags'     # 拦截 / 空回复太多：这一题记成放弃，不拖停整批
    recs = records.read(path)
    res = {'type': 'result', 'pos': pos['id'], 'game': pos['game'], 'effort': effort, 'rep': rep, 'side': side,
           'move': mv, 'forfeit': mv is None and gave_up is None, 'gave_up': gave_up}
    res.update(summarize_attempts(recs, ply))
    agg = records.new_stat()
    for r in recs:
        if r['type'] == 'attempt' and r.get('ply') == ply:
            records.add_usage(agg, r.get('usage') or {}, r.get('elapsed') or 0)
            agg['flags'] += bool(r.get('flagged'))
            agg['empty'] += bool(r.get('empty'))
            agg['illegal'] += (not r.get('flagged') and not r.get('empty') and not r.get('legal'))
    res['stat'] = agg
    runner.log(ctx, res)
    return res


def cmd_run(a):
    game = a.game
    G = game_module(game)
    pos_all = load_positions(a.positions or positions_path(a.batch, game))
    if a.ids:
        want = set(a.ids.split(','))
        pos_all = [p for p in pos_all if p['id'] in want]
        if not pos_all:
            raise SystemExit('一个 id 都没对上：%s' % a.ids)
    efforts = a.efforts.split(',')
    for e in efforts:
        if e not in EFFORTS:
            raise SystemExit('effort 只能是 %s' % '/'.join(EFFORTS))
    if a.dry_run:
        p = pos_all[0]
        st = build_state(p)
        sc = side_cfg(G, efforts[0])
        print('== 系统提示 ==\n%s\n\n== 用户提示（%s）==\n%s' % (
            G.system_prompt(G.turn(st), sc, memory.system_text(sc)), p['id'], prompt_of(G, st, sc)))
        return 0
    out = os.path.join(a.out or str(ROOT / 'runs' / ('quiz-' + a.batch)), game)
    os.makedirs(out, exist_ok=True)
    meta_path = os.path.join(out, 'batch.json')
    if os.path.exists(meta_path):
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)
    else:
        # claude 的运行目录：仓库外的空临时目录（design.md P7、P17），一批共用一个，记下来续跑沿用
        meta = {'claude_cwd': os.path.join(os.path.realpath(tempfile.gettempdir()), 'llmchess-cwd',
                                           'quiz-%s-%s-%s' % (a.batch, game, uuid.uuid4().hex[:8])),
                'first_commit': commit(), 'claude_version': claude_cli.version()}
        tmp = meta_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        os.replace(tmp, meta_path)
    os.makedirs(meta['claude_cwd'], exist_ok=True)
    batch_meta = {'commit': commit(), 'claude_version': meta['claude_version'], 'model': a.model, 'argv': sys.argv}
    # 先答完第 1 遍的全部局面 × 档位，再答第 2 遍：中途撞额度时，已有的数据各档是齐的
    tasks = [(p, e, r) for r in range(1, a.reps + 1) for p in pos_all for e in efforts]
    todo = [t for t in tasks if not result_of(answer_path(out, t[0]['id'], t[1], t[2]))]
    print('%s：共 %d 题，已答 %d，这次要答 %d（%d 路并发）' % (game, len(tasks), len(tasks) - len(todo), len(todo), a.jobs),
          flush=True)
    stop = threading.Event()
    why = []

    def work(t):
        p, e, r = t
        if stop.is_set():
            return None
        print('→ %s %s r%d 开始' % (p['id'], e, r), flush=True)
        try:
            res = answer_one(p, e, r, out, a.model, meta['claude_cwd'], batch_meta)
        except Paused as ex:
            stop.set()
            why.append(str(ex))
            print('！%s %s r%d 撞额度或调不通，整批停下：%s' % (p['id'], e, r, ex), flush=True)
            return None
        print('← %s %s r%d：%s%s' % (p['id'], e, r, res['move'],
                                     '（首答非法）' if res.get('first_legal') is False else ''), flush=True)
        return res

    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        list(ex.map(work, todo))
    left = sum(1 for t in tasks if not result_of(answer_path(out, t[0]['id'], t[1], t[2])))
    if stop.is_set():
        print('停下了（%s）。还剩 %d 题，接着跑同一条命令即可。' % (why[0][:300], left))
        return 3
    print('%s：全部答完（剩 %d）。' % (game, left))
    return 0


# ---------------------------------------------------------------- 引擎事后判
CHESS_DEPTH = 18
XQ_DEPTH = 16                # 上一轮 analyze.py 的口径
CLIP = 1000                  # 分数截断 ±1000，杀棋记 ±1000（上一轮口径）
XQ_BIG, XQ_MIS = 250, 100    # 中国象棋：亏损 >= 250 大失误，100–249 失误（上一轮 report.py）
# 国际象棋按 lichess（lila modules/tree/src/main/Advice.scala，2026-09-25 读的 master）：
#   winningChances = 2 / (1 + exp(-0.00368208 * cp)) - 1，取值 -1..1；走完这步 winningChances 降 >= 0.3 大失误、>= 0.2 失误、
#   >= 0.1 不精确。换成 0–100 的胜率（50 + 50 * winningChances）是降 >= 15 / 10 / 5。杀棋另有规则：本来没杀、走完被对方
#   有杀（MateCreated），或本来有杀、走完没了（MateLost），都算大失误，只在走前已经 <= -700 / 走后仍 >= 700 时降一档。
LI_BLUNDER, LI_MISTAKE, LI_INACC = 0.3, 0.2, 0.1


def engine_for(game):
    if game == 'chess':
        spec = dict(C.engine_spec('stockfish:depth=%d' % CHESS_DEPTH))
    else:
        spec = dict(X.engine_spec('fsf:depth=%d' % XQ_DEPTH))
    spec['options'] = [(k, '64' if k == 'Hash' else v) for k, v in spec['options']]
    return Engine(spec, timeout=600).start()


_INFO = re.compile(r'\bdepth (\d+)\b.*?\bscore (cp|mate) (-?\d+)(.*?)\bpv (\S+)')


def analyse(eng, start_fen, moves):
    """引擎看「start_fen 走完 moves（引擎写法）」这个局面，行棋方视角。返回 {'cp' 或 'mate', 'best', 'depth'}。"""
    eng._send('ucinewgame')
    eng._send('isready')
    eng._until('readyok')
    eng._send('position fen %s%s' % (start_fen, (' moves ' + ' '.join(moves)) if moves else ''))
    eng._send(eng.spec['go'])
    lines = eng._until('bestmove')
    last = None
    for l in lines:
        if not l.startswith('info') or ' multipv ' in l and ' multipv 1 ' not in l:
            continue
        m = _INFO.search(l)
        if m and 'bound' not in m[4]:
            last = m
    best = lines[-1].split()[1] if len(lines[-1].split()) > 1 else None
    if last is None:
        raise RuntimeError('引擎没给分：%s' % lines[-3:])
    out = {'depth': int(last[1]), 'best': best}
    out['cp' if last[2] == 'cp' else 'mate'] = int(last[3])
    return out


def clip(s):
    """{'cp'} / {'mate'} → 截断到 ±1000 的厘兵；杀棋 ±1000（mate 0 = 已经将死对方，记 +1000）。"""
    if 'mate' in s:
        return CLIP if s['mate'] >= 0 else -CLIP
    return max(-CLIP, min(CLIP, s['cp']))


def neg(s):
    return {'cp': -s['cp']} if 'cp' in s else {'mate': -s['mate']}


def win_chances(cp):
    return max(-1.0, min(1.0, 2 / (1 + math.exp(-0.00368208 * cp)) - 1))


def win_pct(s):
    """lichess 的 0–100 胜率：杀棋按 ±1000 厘兵，厘兵先截断到 ±1000。"""
    return 50 + 50 * win_chances(clip(s))


def lichess_judgement(before, after):
    """lila 的 Advice：先看杀棋序列，再看 winningChances 下降。before / after 都是走子方视角。"""
    bm, am = before.get('mate'), after.get('mate')
    bcp, acp = before.get('cp'), after.get('cp')
    if bcp is not None and am is not None and am < 0:                      # MateCreated
        return 'inaccuracy' if bcp < -999 else 'mistake' if bcp < -700 else 'blunder'
    if bm is not None and bm > 0 and (acp is not None or (am is not None and am < 0)):   # MateLost
        a0 = acp or 0
        return 'inaccuracy' if a0 > 999 else 'mistake' if a0 > 700 else 'blunder'
    if bcp is None or acp is None:
        return None
    d = win_chances(bcp) - win_chances(acp)
    return 'blunder' if d >= LI_BLUNDER else 'mistake' if d >= LI_MISTAKE else 'inaccuracy' if d >= LI_INACC else None


# ---------------------------------------------------------------- 规则判定（静态，不用引擎）
# 口径照搬上一轮 analyze.py（它调 jev-study boards.py 的 material / _gain_of / safety），两种棋同一套：
#   子值：中国象棋 车 9、马 4、炮 4.5、仕相 2、兵 1（过河 2）、将帅 0；国际象棋 兵 1、马象 3、车 5、后 9、王 0。
#   三层（three_ply）：我走这步 → 对方任选一步（取对我最坏的）→ 我最多吃回一个子（或不吃）；相对走前的子力净变化。
#     走完对方无着：我赢（中国象棋将死或困毙，国际象棋将死）记 +99，国际象棋逼和记 0；对方应完我无着：记 -99（国际象棋逼和记 0）。
#   两层（two_ply）：我走这步 → 对方取让我子力降最多的一步（吃子、兵过河、升变都算）；相对走前的净变化。
#   白送子：这步三层 <= -2，而且最好的着法三层比它高 >= 2。
#   漏吃：有吃子着两层净得 >= 2（吃了对方最强回应后仍净赚），而所走着两层、三层都比其中最好的低 1.5 以上。
#   漏杀：有一步杀（中国象棋含一步困毙）没走。送杀：走完对方有一步杀（有别的着法可走时才算）。
#   这是纯子力的静态判定，弃子求杀、换子后占优会被误标成白送子；报告里「谁能吃到谁类昏招」只数同时是引擎失误以上的。
XQ_VAL = {'r': 9, 'n': 4, 'c': 4.5, 'a': 2, 'b': 2, 'p': 1, 'k': 0}
CH_VAL = {'p': 1, 'n': 3, 'b': 3, 'r': 5, 'q': 9, 'k': 0}
WIN, LOSE = 99, -99


class XqRules:
    game = 'xiangqi'

    def legal(self, fen):
        return X.legal_fen(fen)

    def play(self, fen, mv):
        return sf.get_fen(X.XQ, fen, [X.to_fsf(mv)])

    def value(self, p, sq):
        if p.lower() == 'p':
            y = int(sq[1:])
            return 2 if (y >= 5 if p.isupper() else y <= 4) else 1
        return XQ_VAL[p.lower()]

    def mat(self, fen):
        """行棋方视角的子力差。"""
        board, stm = X.board_of(fen)
        v = sum(self.value(p, s) * (1 if p.isupper() else -1) for s, p in board.items())
        return v if stm == 'w' else -v

    def gains(self, fen):
        """{着法: (净得, 是否吃子)}：吃到的子值 + 自己这个子的升值（兵过河）。"""
        board, _ = X.board_of(fen)
        out = {}
        for mv in self.legal(fen):
            p, cap = board[mv[:2]], board.get(mv[2:4])
            g = (self.value(cap, mv[2:4]) if cap else 0) + self.value(p, mv[2:4]) - self.value(p, mv[:2])
            out[mv] = (g, cap is not None)
        return out

    def no_move_value(self, fen):
        """行棋方无着时，对行棋方而言的结果：中国象棋将死、困毙都判负。"""
        return LOSE

    def is_capture(self, fen, mv):
        return X.board_of(fen)[0].get(mv[2:4]) is not None


class ChessRules:
    game = 'chess'

    def legal(self, fen):
        return [m.uci() for m in chess.Board(fen).legal_moves]

    def play(self, fen, mv):
        b = chess.Board(fen)
        b.push(chess.Move.from_uci(mv))
        return b.fen()

    def mat(self, fen):
        b = chess.Board(fen)
        v = sum(CH_VAL[p.symbol().lower()] * (1 if p.color else -1) for p in b.piece_map().values())
        return v if b.turn == chess.WHITE else -v

    def gains(self, fen):
        b = chess.Board(fen)
        out = {}
        for m in b.legal_moves:
            cap = b.piece_at(m.to_square)
            g = CH_VAL[cap.symbol().lower()] if cap else (1 if b.is_en_passant(m) else 0)
            if m.promotion:
                g += CH_VAL[chess.piece_symbol(m.promotion)] - 1
            out[m.uci()] = (g, b.is_capture(m))
        return out

    def no_move_value(self, fen):
        return LOSE if chess.Board(fen).is_check() else 0

    def is_capture(self, fen, mv):
        return chess.Board(fen).is_capture(chess.Move.from_uci(mv))


def rules_for(game):
    return XqRules() if game == 'xiangqi' else ChessRules()


def static_table(R, fen):
    """局面上每个合法着法的三层、两层子力、走完是否对方无着、对方是否有一步杀。一个局面算一次，多次作答共用。"""
    base = R.mat(fen)
    tp, two, mates, allows = {}, {}, [], {}
    for mv in R.legal(fen):
        f1 = R.play(fen, mv)
        replies = R.legal(f1)
        if not replies:
            v = -R.no_move_value(f1)               # 对方无着：对方的结果取反就是我的
            tp[mv] = two[mv] = v
            if v == WIN:
                mates.append(mv)
            allows[mv] = False
            continue
        after = -R.mat(f1)
        g1 = R.gains(f1)
        two[mv] = after - max(0, max(g for g, _ in g1.values())) - base
        worst, opp_mate = None, False
        for r in replies:
            f2 = R.play(f1, r)
            qs = R.gains(f2)
            if not qs:
                v = R.no_move_value(f2)
                opp_mate = opp_mate or v == LOSE
                v = v if v == LOSE else 0
            else:
                v = R.mat(f2) + max([0] + [g for g, cap in qs.values() if cap]) - base
            worst = v if worst is None else min(worst, v)
        tp[mv] = worst
        allows[mv] = opp_mate
    return {'tp': tp, 'two': two, 'mates': sorted(mates), 'allows': allows,
            'free_caps': [m for m in two if R.is_capture(fen, m) and two[m] >= 2]}


def labels(tab, mv):
    tp, two = tab['tp'], tab['two']
    free = tab['free_caps']
    hang = tp[mv] <= -2 and max(tp.values()) - tp[mv] >= 2
    missed_cap = bool(free) and two[mv] < max(two[m] for m in free) - 1.5 and tp[mv] < max(tp[m] for m in free) - 1.5
    missed_mate = bool(tab['mates']) and mv not in tab['mates']
    allows_mate = tab['allows'][mv] and not all(tab['allows'].values())
    return {'hang': hang, 'missed_capture': missed_cap, 'missed_mate': missed_mate, 'allows_mate': allows_mate,
            'tp': tp[mv], 'tp_best': max(tp.values()), 'two': two[mv]}


def to_eng(game, mv):
    return X.to_fsf(mv) if game == 'xiangqi' else mv


def from_eng(game, mv):
    return X.from_fsf(mv) if game == 'xiangqi' else mv


def judge_game(game, batch, out_root, positions=None):
    pos_by = {p['id']: p for p in load_positions(positions or positions_path(batch, game))}
    ans_dir = os.path.join(out_root, game)
    results = []
    for name in sorted(os.listdir(ans_dir)) if os.path.isdir(ans_dir) else []:
        if name.endswith('.jsonl') and name != 'judged.jsonl':
            r = result_of(os.path.join(ans_dir, name))
            if r:
                results.append(r)
    R = rules_for(game)
    eng = engine_for(game)
    cache, rows = {}, []
    try:
        for res in results:
            pos = pos_by[res['pos']]
            st = build_state(pos)
            fen = st['fens'][-1]
            if game == 'xiangqi':      # 带完整历史给引擎（重复局面、长将它自己会避）
                start, hist = st['fens'][0], [X.to_fsf(m) for m in st['moves']]
            else:
                start, hist = fen, []
            if res['pos'] not in cache:
                before = analyse(eng, start, hist)
                before['best'] = from_eng(game, before['best'])          # 换成和作答同一种写法（中国象棋 ICCS）
                cache[res['pos']] = {'before': before, 'best': before['best'],
                                     'tab': static_table(R, fen), 'after': {}}
                print('  判 %s：走前 %s，引擎最佳 %s' % (res['pos'], before, cache[res['pos']]['best']), flush=True)
            c = cache[res['pos']]
            row = {k: res.get(k) for k in ('pos', 'game', 'effort', 'rep', 'side', 'move', 'forfeit', 'gave_up',
                                           'attempts', 'first_legal', 'first_move_text', 'first_think', 'first_elapsed')}
            row['stat'] = res['stat']
            row['before'] = c['before']
            row['engine_best'] = c['best']
            mv = res['move']
            if mv is None:
                rows.append(row)
                continue
            if mv not in c['after']:
                f1 = R.play(fen, mv)
                if not R.legal(f1):
                    term = R.no_move_value(f1)
                    c['after'][mv] = {'mate': 0} if term == LOSE else {'cp': 0}
                else:
                    c['after'][mv] = neg(analyse(eng, start, hist + [to_eng(game, mv)]))
            before, after = c['before'], c['after'][mv]
            row['after'] = after
            row['loss'] = clip(before) - clip(after)
            row['best_match'] = mv == c['best']
            row.update(labels(c['tab'], mv))
            if game == 'xiangqi':
                row['blunder'] = row['loss'] >= XQ_BIG
                row['mistake'] = XQ_MIS <= row['loss'] < XQ_BIG
                row['solved'] = row['best_match']
                row['same_as_prev'] = mv == pos['prev_move']
            else:
                j = lichess_judgement(before, after)
                row['judgement'] = j
                row['blunder'] = j == 'blunder'
                row['mistake'] = j == 'mistake'
                row['winpct_drop'] = round(win_pct(before) - win_pct(after), 1)
                b = chess.Board(fen)
                b.push(chess.Move.from_uci(mv))
                row['solved'] = mv == pos['solution'] or b.is_checkmate()
            rows.append(row)
    finally:
        eng.close()
    path = os.path.join(ans_dir, 'judged.jsonl')
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    os.replace(tmp, path)
    return rows, path


def engine_note(game):
    if game == 'chess':
        return ('Stockfish 19 depth %d（Threads 1，Hash 64），分数截断 ±%d；大失误 / 失误按 lichess：winningChances（-1..1）'
                '降 >= 0.3 / 0.2，即 0–100 胜率降 >= 15 / 10，另加 lichess 的杀棋规则' % (CHESS_DEPTH, CLIP))
    return ('Fairy-Stockfish 14.0.1（UCI_Variant xiangqi）depth %d（Threads 1，Hash 64），带完整着法历史，分数截断 ±%d；'
            '亏损 >= %d 大失误、%d–%d 失误（上一轮 report.py 口径）' % (XQ_DEPTH, CLIP, XQ_BIG, XQ_MIS, XQ_BIG - 1))


def cmd_judge(a):
    out_root = a.out or str(ROOT / 'runs' / ('quiz-' + a.batch))
    for game in (GAMES if a.game == 'all' else (a.game,)):
        if not os.path.isdir(os.path.join(out_root, game)):
            print('%s：没有作答记录，跳过' % game)
            continue
        rows, path = judge_game(game, a.batch, out_root)
        print('%s：判了 %d 条 → %s\n  %s' % (game, len(rows), path, engine_note(game)))
    return 0


# ---------------------------------------------------------------- 汇总
def _pct(n, d):
    return '%.0f%%' % (100.0 * n / d) if d else '-'


def _med(xs):
    xs = [x for x in xs if x is not None]
    return '%.0f' % statistics.median(xs) if xs else '-'


COLS = ('棋种', '档位', '样本', '首答非法', '判负/放弃', '大失误', '失误', '平均亏损', '与引擎最佳一致', '解中',
        '白送子', '漏吃', '谁能吃到谁类昏招', '漏杀', '送杀', '思考tok中位', '首答思考中位', '耗时中位s', '拦截', '空回复')


def report_rows(game, rows):
    by = collections.OrderedDict((e, []) for e in EFFORTS)
    for r in rows:
        by.setdefault(r['effort'], []).append(r)
    out = []
    for e, rs in by.items():
        if not rs:
            continue
        n = len(rs)
        firsts = [r for r in rs if r.get('first_legal') is not None]
        judged = [r for r in rs if r.get('move') is not None]
        m = len(judged)
        cnt = lambda k: sum(1 for r in judged if r.get(k))
        capture = sum(1 for r in judged if (r['hang'] or r['missed_capture']) and (r['blunder'] or r['mistake']))
        out.append([game, e, str(n), _pct(sum(1 for r in firsts if not r['first_legal']), len(firsts)),
                    '%d/%d' % (sum(1 for r in rs if r.get('forfeit')), sum(1 for r in rs if r.get('gave_up'))),
                    _pct(cnt('blunder'), m), _pct(cnt('mistake'), m),
                    '%.0f' % (sum(max(0, r['loss']) for r in judged) / m) if m else '-',
                    _pct(cnt('best_match'), m), _pct(cnt('solved'), m) if game == 'chess' else '-',
                    _pct(cnt('hang'), m), _pct(cnt('missed_capture'), m), _pct(capture, m),
                    _pct(cnt('missed_mate'), m), _pct(cnt('allows_mate'), m),
                    _med([r['stat']['think'] for r in rs]), _med([r.get('first_think') for r in rs]),
                    _med([r['stat']['elapsed'] for r in rs]),
                    str(sum(r['stat']['flags'] for r in rs)), str(sum(r['stat']['empty'] for r in rs))])
    return out


REPORT_NOTES = [
    '样本：已答完的作答数（局面 × 遍）。首答非法：第一次既没被拦也不是空回复的回答里给了非法着 / 没写出着法的比例。',
    '判负/放弃：重试 3 次仍非法 / 拦截或空回复超过上限；这两类不进后面的比例（分母是有着法的作答）。',
    '平均亏损：厘兵，负数按 0 计。与引擎最佳一致：走的正是引擎首选。解中：国际象棋走的是谜题正解首着或直接将死。',
    '白送子 / 漏吃 / 漏杀 / 送杀：静态子力判定（口径见 quiz.py「规则判定」注释）；谁能吃到谁类昏招 = (白送子 或 漏吃) 且引擎判失误以上。',
    '思考 tok：一次作答所有尝试合计；首答思考：第一次有效回答的思考 token。耗时：一次作答所有尝试合计。',
]


def cmd_report(a):
    out_root = a.out or str(ROOT / 'runs' / ('quiz-' + a.batch))
    table = []
    notes = []
    for game in GAMES:
        path = os.path.join(out_root, game, 'judged.jsonl')
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as f:
            rows = [json.loads(l) for l in f if l.strip()]
        table += report_rows(game, rows)
        notes.append('%s：%s' % (game, engine_note(game)))
    if not table:
        raise SystemExit('没有 judged.jsonl，先跑 judge')
    lines = ['| ' + ' | '.join(COLS) + ' |', '|' + '---|' * len(COLS)]
    lines += ['| ' + ' | '.join(r) + ' |' for r in table]
    text = '\n'.join(lines + [''] + notes + REPORT_NOTES) + '\n'
    path = os.path.join(out_root, 'report.txt')
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)
    print(text + '\n（已写 %s）' % path)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m llmchess.quiz', description=__doc__.split('\n')[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run', help='作答（断点续跑：再跑同一条）')
    r.add_argument('--game', required=True, choices=GAMES)
    r.add_argument('--batch', default='batch1', help='局面在 data/<batch>/，记录在 runs/quiz-<batch>/')
    r.add_argument('--positions', help='局面文件，默认 data/<batch>/<棋种>.jsonl')
    r.add_argument('--out', help='记录的上级目录，默认 runs/quiz-<batch>')
    r.add_argument('--ids', help='只答这些局面，逗号分隔')
    r.add_argument('--efforts', default=','.join(EFFORTS))
    r.add_argument('--reps', type=int, default=2)
    r.add_argument('--jobs', type=int, default=4, help='并发调用数')
    r.add_argument('--model', default='opus')
    r.add_argument('--dry-run', action='store_true', help='只打印第一个局面的系统提示和用户提示')
    j = sub.add_parser('judge', help='引擎事后判')
    j.add_argument('--game', default='all', choices=GAMES + ('all',))
    j.add_argument('--batch', default='batch1')
    j.add_argument('--out')
    p = sub.add_parser('report', help='汇总表')
    p.add_argument('--batch', default='batch1')
    p.add_argument('--out')
    a = ap.parse_args(argv)
    return {'run': cmd_run, 'judge': cmd_judge, 'report': cmd_report}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
