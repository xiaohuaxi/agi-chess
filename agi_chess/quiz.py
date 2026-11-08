"""局面题模式（design.md 第六节组 1、第八节）：固定局面、stateless，每次只让模型走一步，引擎事后判这步好坏。

    python3 -m agi_chess.quiz run --game xiangqi                 # 30 局面 × 四档 × 2 遍；断点续跑就是再跑一次同一条
    python3 -m agi_chess.quiz run --game chess --jobs 4 --efforts medium,high,xhigh,max --reps 2
    python3 -m agi_chess.quiz run --game chess --ids c01 --efforts medium --reps 1    # 冒烟
    python3 -m agi_chess.quiz run --game xiangqi --ids x01 --dry-run                   # 只打印提示，不调模型
    python3 -m agi_chess.quiz judge --game chess                 # 引擎事后判，写 judged.jsonl
    python3 -m agi_chess.quiz report                             # 两种棋 × 档位的汇总表
    # 分档（第二批块 A）：--arm 起名，--set 改变量（可重复），记录放 runs/quiz-<batch>/<档名>/<棋种>/
    python3 -m agi_chess.quiz run --game xiangqi --batch batch2 --arm threats --set threats=on --efforts xhigh --reps 3
    python3 -m agi_chess.quiz run --game chess --batch batch2 --arm legal --set legal=list --efforts xhigh --reps 2
    python3 -m agi_chess.quiz copy --game xiangqi --batch batch2 --from-arm zh --arm base   # 同局面同提示的旧作答复用过来
    python3 -m agi_chess.quiz judge --batch batch2 [--arm threats]   # 不给 --arm 就判全部档
    python3 -m agi_chess.quiz report --batch batch2                  # 按档分组出表；threats 档另出一张清单打分表
    # 第三批块 A：batch2 的局面（剔除 x2-25）、reason 档，记录另放一个根目录（--out，judge / report 给同一个 --out）
    python3 -m agi_chess.quiz run --game chess --batch batch2 --out runs/quiz-batch3 --arm reason --set reason=on --efforts xhigh --reps 2

--set 可改的变量：view、show all|board|pieces|fen|boardpieces、legal none|list、selfcheck on|off、recite on|off（只有中国象棋）、
  threats on|off、attackmap on|off、reason on|off。
  show：局面怎么呈现（X.SHOWS / C.SHOWS，整盘对局共用）。**不给 show 时用棋种默认给法 DEFAULT_SHOW：中国象棋 pieces、
    国际象棋 all**（第 4P2 批定的，见 docs/results/batch4-presentation.md 末节）。all 是改默认之前的给法（ALL_VIEW），
    --set show=all 和以前不给 show 的提示逐字相同，第 4P2 批及以前的数据都是它；board 只给文字棋盘，pieces 只给
    子力清单，fen 只给 FEN 串。轮到谁走、执哪方、坐标和回答格式本来就在开头几行和系统提示里，各档都有，除呈现那段外提示一字不差。
    注意国际象棋的 all 是 fen,ascii，没有子力清单，所以国际象棋的 all 只有两样，pieces 档的清单 all 里没有。
    boardpieces（第 4P2 批新增）：只有中国象棋有，= 文字棋盘 + 子力清单（all 去掉 FEN 那段，逐字相同）；国际象棋没有这档，传了报错。
    和 view 二选一。每次作答的 result、judged.jsonl 各记一个 show 字段（给了 view 的档记 null）。新跑的档不给 show 时，
    默认给法（不是 all 的话）会显式写进 batch.json 和每题 config 的 set；旧档 set 里没有 show 的，一律按 all 解读。
    不给 --arm 的旧布局也用默认给法，所以第一批中国象棋的旧目录（set 为空）不能再续跑（会报 set 不一致）。
  reason=on：系统提示末尾加一句，请它用自己的话说明这步为什么这么走（REASON_ASK，措辞的讲究见那里）；只进提示，不打分。
  threats=on：要求回答里在「着法:」之前先列「走后威胁:」清单（走完这步后对方所有吃子、将军着法），程序按走后真实局面
    打分（列中 / 漏列 / 错列），分数只写进记录，不回灌给模型。
  attackmap=on：局面后附程序算出的攻击关系（对方能吃到我哪些子、我哪些子没保护）。它碰到 AGENTS.md 硬约束「棋手不准用规则库
    帮忙」，**待用户拍板，未批不准跑**：run 遇到它除非同时给 --allow-attackmap 否则直接退出；--dry-run 看提示不受限。
  同一个档名下 --set 的值、局面（同一 id 的局面内容）和已有记录不一致时报错，不混写。不给 --arm 时不许 --set，布局同第一批。
--timeout：单次 claude -p 调用的超时秒数（默认 3600）。每次超时或调不通在该题自己的记录里写一条 call_fail（带题号 / 档 / 遍）。
--on-limit wait|pause：撞额度时默认在程序里等到解除（读出解除时间就等到那时，读不出按 10 分钟起翻倍、最多 30 分钟退避），
  每次等待的起止在该题记录里各写一条 limit_wait；pause 恢复旧行为。等待中 Ctrl-C / SIGTERM：在等的线程马上醒来写 pause，
  退出码 3，再跑同一条命令接着来；再按一次强退。

局面在 data/<batch>/<棋种>.jsonl（选取脚本同目录），或用 --positions 指定。标了 excluded（剔除理由）的局面 run / copy
跳过，judge / report 照样判已有记录（目前只有 x2-25）。记录在 runs/quiz-<batch>/[<档名>/]<棋种>/（不入库）：
  每次作答一个文件 <局面id>-<effort>-r<遍>.jsonl：config、attempt（和整盘同一格式，由 runner.model_turn 写）、
  call_fail（超时 / 调不通）、limit_wait（撞额度等解除的起止）、pause（暂停）、最后一行 result。有 result 的就算答完，再跑时跳过；只有 attempt 没 result 的
  （中途撞额度），续跑时接上已用掉的尝试次数（runner.pending_ply），和整盘续跑一样。
  batch.json 记 claude 运行目录、档名、--set 值、用过的局面文件；judge 按它找局面。
  judge 在每个 <棋种> 目录写 judged.jsonl，report 在 runs/quiz-<batch>/ 下写 report.txt。

提示和整盘对局给模型的完全一样：同一个系统提示（里面「满 200 个半回合判和」之类的整盘规则文字原样保留，没有为局面题改写，
免得两种模式的提示不一样）、同样的默认给法（show）、history=0（只给当前局面，不附着法历史；「对方刚走」那句保留）。
中国象棋的状态里带着从开局起的全部着法，禁着（长将 / 长捉）照样按完整历史判；只是提示里不给历史。
国际象棋谜题没有开局到这步的着法，状态从谜题 FEN 起、走完对手那一步；回合数改用 FEN 里的真实回合数（见 QuizChess）。

整批停下（--on-limit pause 时撞额度、连续调不通、停止信号；claude_cli 抛 Paused）时：不再开新题，已经在跑的等它们答完，
退出码 3，下次跑同一条命令接着来。
明确拒答一次即终止整批并回报用户，禁止自动续跑。只有普通空回复超过 runner.MAX_FLAGS 次时，整盘模式暂停；
局面题把这一题记成「放弃（空回复）」，不拖停整批。

引擎只在 judge 里用，永远不进提示。
"""
import argparse, collections, concurrent.futures, json, math, os, pathlib, re, statistics, sys, tempfile, threading, uuid

try:
    import chess
    import pyffish as sf
    from . import chess_ as C
    from . import xiangqi as X
except ModuleNotFoundError:
    chess = sf = C = X = None

from . import chat, claude_cli, codex_cli, memory, records, runner
from .claude_cli import Paused, Refused, ToolAttempt
from .cli import commit
from .engine import Engine

ROOT = pathlib.Path(__file__).resolve().parent.parent
EFFORTS = ('medium', 'high', 'xhigh', 'max')
GAMES = ('xiangqi', 'chess')


# ---------------------------------------------------------------- 局面与状态
def positions_path(batch, game):
    return ROOT / 'data' / batch / ('%s.jsonl' % game)


def load_positions(path):
    """局面文件里的全部局面，含标了 excluded 的（judge 要能判剔除前已答的记录）。"""
    with open(path, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


def active_positions(ps):
    """去掉标了 excluded 的局面（剔除理由写在局面文件那一行里，如 x2-25）。只有 run / copy 用：剔除不删行，
    judge / report 照样按全部局面判已有记录。"""
    return [p for p in ps if not p.get('excluded')]


class QuizChess:
    """国际象棋模块的薄包装，只改一处：render 头一行的回合数。谜题状态里只有对手刚走的那一步，
    chess_.render 按 len(moves) 会写成「第 1 回合（已走 1 个半回合）」，这里换成 FEN 里的真实回合数。其余原样转给 chess_。"""
    _HEAD = re.compile(r'^第 \d+ 回合（已走 \d+ 个半回合）')

    def __getattr__(self, name):
        return getattr(C, name)

    def render(self, st, sc, fresh=True):
        b = st['board']
        ply = 2 * (b.fullmove_number - 1) + (b.turn == chess.BLACK)
        return self._HEAD.sub('第 %d 回合（已走 %d 个半回合）' % (ply // 2 + 1, ply), C.render(st, sc, fresh), count=1)


def _require_rules():
    if chess is None or sf is None or C is None or X is None:
        raise SystemExit('缺少规则库依赖（chess / pyffish），请先执行：pip install -r requirements.txt')


def game_module(game):
    _require_rules()
    return X if game == 'xiangqi' else QuizChess()


def build_state(pos):
    """题目局面的棋种状态。中国象棋从开局重放全部着法（禁着判定要完整历史）；国际象棋从谜题 FEN 走完对手那步。"""
    _require_rules()
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


SET_KEYS = {'view': None, 'show': ('all', 'board', 'pieces', 'fen', 'boardpieces'), 'legal': ('none', 'list'), 'selfcheck': ('on', 'off'), 'recite': ('on', 'off'),
            'threats': ('on', 'off'), 'attackmap': ('on', 'off'), 'reason': ('on', 'off'),
            'protocol': ('legacy', 'real')}


def parse_sets(G, items):
    """--set 变量=值 → {变量: 值}（值是字符串，view 保持逗号分隔），不合法就退出。"""
    out = {}
    for item in items or []:
        k, sep, v = item.partition('=')
        if not sep or k not in SET_KEYS:
            raise SystemExit('--set 写成 变量=值，变量是 %s 之一：%r' % ('/'.join(SET_KEYS), item))
        if k == 'view':
            bad = [x for x in v.split(',') if x not in G.VIEWS]
            if bad:
                raise SystemExit('不认识的 view：%s（可选 %s）' % (','.join(bad), ','.join(G.VIEWS)))
        elif v not in SET_KEYS[k]:
            raise SystemExit('%s 只能是 %s，收到 %r' % (k, '/'.join(SET_KEYS[k]), v))
        if k == 'recite' and v == 'on' and not G.RECITE:
            raise SystemExit('这种棋还没有复述打分，recite 只能 off')
        out[k] = v
    if 'view' in out and 'show' in out:
        raise SystemExit('view 和 show 二选一')
    return out


# show 档（呈现方式）→ view 的对照放在各棋种模块（X.SHOWS / C.SHOWS），整盘对局（cli）也用它。all 就是 ALL_VIEW（第 4P2 批
# 之前的默认给法，旧提示逐字相同）；board 是各棋种的文字棋盘。
# boardpieces（第 4P2 批新增）：只有中国象棋需要，= grid + pieces（all 去掉 fen 那段，逐字相同，因为 ALL_VIEW 顺序
# 就是 grid,pieces,fen，render 按 sc['view'] 顺序逐段拼接、段间用两个换行分隔，去掉最后一段不影响前面几段的文字）。
# 国际象棋没有这档的需要：允许传但不生效没意义，也不该悄悄映射成某个已有档造成误解，所以明确报错。
SHOW_VIEWS = {
    'xiangqi': X.SHOWS if X is not None else {'all': 'grid,pieces,fen', 'board': 'grid', 'pieces': 'pieces', 'fen': 'fen', 'boardpieces': 'grid,pieces'},
    'chess': C.SHOWS if C is not None else {'all': 'fen,ascii', 'board': 'ascii', 'pieces': 'pieces', 'fen': 'fen'},
}


def show_views(G, show):
    if show not in G.SHOWS:
        raise SystemExit('%s 没有 show=%s 这一档' % ('xiangqi' if G is X else 'chess', show))
    return G.SHOWS[show].split(',')


def show_of(sets):
    """记录里这一档的呈现方式：给了 show 就是它；给了 view（自定义组合）记 None；都没给是 all。
    「都没给是 all」是旧记录（第 4P2 批之前）的含义，不随默认给法变：新跑的档由 with_default_show 把默认给法写进 set。"""
    sets = sets or {}
    return sets.get('show') or (None if 'view' in sets else 'all')


def with_default_show(G, sets):
    """新跑的档：没给 show 也没给 view 时，把棋种的默认给法（G.DEFAULT_SHOW）显式写进 set，这样 batch.json、每题记录的
    set / show 都看得出用的是哪种给法，旧记录（set 里没有 show，= all）的含义也不变。默认就是 all 的棋种（国际象棋）
    不写，免得和改动前的旧档对不上、续跑被当成不同的 set 拒掉。"""
    if 'show' in sets or 'view' in sets or G.DEFAULT_SHOW == 'all':
        return sets
    return dict(sets, show=G.DEFAULT_SHOW)


def side_cfg(G, effort, sets=None):
    """和 cli.side_cfg 默认值一致，只把 history 设成 0、effort 按档位；sets 是分档的覆盖值（parse_sets 的结果）。
    sets 按记录里的含义解读：没有 show / view 就是 all（旧给法）；新跑的默认给法由 cmd_run 先经 with_default_show 补进 sets。
    max_plies 只用来拼系统提示里那句整盘规则。threats / attackmap 只有局面题有；reason 是局面题自己的 REASON_ASK（system_of）。"""
    sc = {'effort': effort, 'memory': 'stateless', 'view': G.ALL_VIEW.split(','), 'history': 0, 'legal': 'none',
          'selfcheck': 'off', 'recite': 'off', 'threats': 'off', 'attackmap': 'off', 'reason': 'off', 'notes_keep': 1,
          'session_view': 'full', 'max_plies': 200}
    for k, v in (sets or {}).items():
        sc[k] = v.split(',') if k == 'view' else v
    if 'show' in sc:
        sc['view'] = show_views(G, sc['show'])
    return sc


# reason 档（第三批块 A）：请棋手说明这步为什么这么走。措辞是刻意的，改之前先读这段：
# - 用户要求把棋手当人看：人每走一步都有依据，由它自己说；不设栏目、不要求列候选着法、不限定写什么。
# - 不能写成「把你的思考过程写出来」之类：第一批这样写过，像在索取模型内部思考，被安全分类器拦下（memory.py ASK_NOTES
#   上方同一类教训）。只要回答正文里的理由。以后改措辞若要实测，遇到拒答立即终止，不能换措辞重问。
# 两种棋共用这一句，所以挂在这里（system_of）而不是各棋种的 system_prompt 里；off 时系统提示和以前逐字相同。
REASON_ASK = ('下棋的人每走一步都有自己的依据，可能是一个长远的计划，也可能是想走出某种局面。请在回答里用你自己的话说明这步'
              '为什么这么走，写什么、怎么写由你决定；最后一行照常只写「着法: 」加着法。')


def system_of(G, side, sc):
    """局面题的系统提示：棋种的整盘系统提示，reason=on 时末尾加 REASON_ASK。
    棋种的 real 系统提示也认 reason（整盘的「着法前写理由」，memory.answer_lead）；局面题沿用自己的 REASON_ASK，
    所以交给棋种时按 off 传，已有局面题档的提示逐字不变。"""
    s = G.system_prompt(side, dict(sc, reason='off'), memory.system_text(sc))
    return s + '\n\n' + REASON_ASK if sc.get('reason') == 'on' else s


def quiz_cfg(G, game, side, effort, model, cwd, sets=None, timeout=None):
    if model.split(':', 1)[0] in chat.AGY_KINDS or model.startswith(('agy/', 'gemini-')):
        raise SystemExit('Gemini / agy 棋手只支持 real 整盘，局面题不支持；不能改走 claude -p')
    sc = side_cfg(G, effort, sets)
    player = codex_cli.spec_of(model)            # opus → claude:opus；sol / deepseek / codex:… / deepseek:… 走 codex exec
    kind, name = player.split(':', 1)
    shown = claude_cli.shown(claude_cli.command(name, effort, '-')) if kind == 'claude' else \
        codex_cli.shown(kind, name, effort)
    return {'game': game, 'players': {side: player}, 'sides': {side: sc}, 'retries': 3, 'max_plies': 200,
            'system': {side: system_of(G, side, sc)},
            'commands': {side: shown}, 'claude_cwd': cwd,
            'timeout': timeout or claude_cli.TIMEOUT}


def prompt_of(G, st, sc):
    return G.render(st, sc) + '\n\n' + memory.ask(sc)


# ---------------------------------------------------------------- threats 档：清单解析与打分
# 模型按 THREATS_ASK（xiangqi.py / chess_.py）写「走后威胁:」清单，每行一着。这里取回复里最后一个清单，
# 把每行解析成对方着法，和「走完这步之后的真实局面」里对方的全部吃子着法、将军着法比。走子规则全交给 pyffish /
# python-chess（炮架、蹩马腿、塞象眼、牵制都由它们判），这里不写走子规则。分数只写进记录，不回灌给模型。
_TH_HEAD = re.compile(r'走后威胁[\s*`]*[:：]')
_TH_MOVE_LINE = re.compile(r'^[\s>*`#\-]*着法\s*[:：]')
_TH_BULLET = re.compile(r'^[\s>*`•·\-–—]*(?:\d+\s*[.、)）]\s*)?')
_TH_NONE = re.compile(r'^(无|没有)(\W.*)?$')
_XQ_MV = re.compile(r'(?<![a-z])([a-i])(\d)(?:\s*[-–—>→]\s*)?([a-i])(\d)(?!\d)')
_CH_MV = re.compile(r'(?<![A-Za-z])([a-h][1-8])(?:\s*[-–—x:>→]\s*)?([a-h][1-8])([qrbnQRBN])?(?![0-9])')


def extract_threats(reply):
    """回复里最后一个「走后威胁:」清单。没写清单返回 None；写了「无」返回 []；否则返回每行原文（去掉项目符号）。
    清单到「着法:」那行或清单后第一个空行为止；标题同一行后面的内容算第一行。"""
    hits = list(_TH_HEAD.finditer(reply or ''))
    if not hits:
        return None
    items = []
    for i, line in enumerate(reply[hits[-1].end():].split('\n')):
        if _TH_MOVE_LINE.match(line):
            break
        t = _TH_BULLET.sub('', line).strip().strip('*`').strip()
        if not t:
            if items:
                break
            continue
        items.append(t)
    return [t for t in items if not _TH_NONE.match(t)][:60]


def threat_truth(game, fen, mv):
    """走完 mv 之后对方的合法吃子着法、将军着法（同作答一种写法：中国象棋 ICCS，国际象棋 UCI）。"""
    if game == 'xiangqi':
        f1 = sf.get_fen(X.XQ, fen, [X.to_fsf(mv)])
        board = X.board_of(f1)[0]
        replies = X.legal_fen(f1)
        caps = [r for r in replies if board.get(r[2:4])]
        checks = [r for r in replies if X.in_check_fen(sf.get_fen(X.XQ, f1, [X.to_fsf(r)]))]
        return f1, caps, checks
    b = chess.Board(fen)
    b.push(chess.Move.from_uci(mv))
    ms = sorted(b.legal_moves, key=lambda m: m.uci())
    return b.fen(), [m.uci() for m in ms if b.is_capture(m)], [m.uci() for m in ms if b.gives_check(m)]


def resolve_threats(game, f1, items):
    """清单每行 → [(原文, 着法或 None)]。一行里写了几个坐标就算几着；没有坐标时中国象棋试中文记谱、国际象棋试 SAN。
    着法只要在走后局面里合法就给出（是不是吃子 / 将军由打分判）；不合法、读不出的给 None。"""
    out = []
    if game == 'xiangqi':
        legal = set(X.legal_fen(f1))
        for t in items:
            ms = ['%s%s%s%s' % m for m in _XQ_MV.findall(t.lower())]
            if ms:
                out += [(t, m if m in legal else None) for m in ms]
                continue
            mv, why = X.resolve(f1, t)
            out.append((t, mv if mv and not why and mv in legal else None))
        return out
    b = chess.Board(f1)
    legal = {m.uci() for m in b.legal_moves}
    for t in items:
        ms = [(a + c + (p or '')).lower() for a, c, p in _CH_MV.findall(t)]
        if ms:
            out += [(t, m if m in legal else None) for m in ms]
            continue
        got = []
        for tok in re.split(r'[\s、,，;；/（）()]+', t):
            tok = re.sub(r'[+#!?.。]+$', '', tok)
            if not tok or not C._SAN.match(tok) and not tok.startswith('O-O'):
                continue
            try:
                got.append(b.parse_san(tok).uci())
            except ValueError:
                pass
        out += [(t, m) for m in got] if got else [(t, None)]
    return out


def threat_score(game, fen, mv, reply):
    """threats 档的打分（写进 result，judge 抄进 judged.jsonl）：
    true 走后对方全部吃子 / 将军着法；listed 清单里读出的合法着法；hit 列中，miss 漏列，wrong 错列（列了但不是吃子
    或将军的合法着法、不合法或读不出的行）；unparsed 其中读不出 / 不合法的行数；found 是否写了清单，none 是否写的「无」。"""
    f1, caps, checks = threat_truth(game, fen, mv)
    true = sorted(set(caps) | set(checks))
    items = extract_threats(reply)
    rec = {'found': items is not None, 'none': items == [], 'items': items, 'captures': caps, 'checks': checks,
           'true': true}
    pairs = resolve_threats(game, f1, items or [])
    listed = sorted({m for _, m in pairs if m})
    unparsed = sum(1 for _, m in pairs if m is None)
    rec.update(listed=listed, hit=len(set(listed) & set(true)), miss=len(set(true) - set(listed)),
               wrong=len(set(listed) - set(true)) + unparsed, unparsed=unparsed)
    return rec


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
    fails = [r for r in recs if r['type'] == 'call_fail' and r.get('ply') == ply]
    return {'attempts': len(atts), 'first_legal': first.get('legal') if first else None,
            'first_move_text': first.get('move_text') if first else None,
            'first_think': (first.get('usage') or {}).get('think') if first else None,
            'first_elapsed': first.get('elapsed') if first else None,
            'illegal_reasons': [r.get('reason') for r in real if not r.get('legal')],
            'call_fails': len(fails), 'timeouts': sum(1 for r in fails if r.get('timeout'))}


def answer_one(pos, effort, rep, out, model, cwd, batch_meta, sets=None, arm=None, timeout=None):
    """答一题。返回 result；普通暂停抛 Paused，明确拒答抛 Refused。sets / arm：分档的覆盖值和档名。"""
    path = answer_path(out, pos['id'], effort, rep)
    done = result_of(path)
    if done:
        return done
    G = game_module(pos['game'])
    st = build_state(pos)
    side = G.turn(st)
    ply = len(st['moves']) + 1
    cfg = quiz_cfg(G, pos['game'], side, effort, model, cwd, sets, timeout)
    ctx = runner.new_ctx(G, cfg, out)
    ctx['st'], ctx['log'] = st, path
    ctx['tags'] = {'pos': pos['id'], 'effort': effort, 'rep': rep, 'arm': arm}
    if os.path.exists(path):
        recs = records.read(path)
        if runner.refusal_record(recs):
            raise Refused('这题已有拒答拦截记录，禁止自动续跑，请向用户回报')
        if runner.tool_record(recs):
            raise ToolAttempt(runner.TOOL_MESSAGE)
        ctx['pending'] = runner.pending_ply(recs, ply)
        runner.log(ctx, {'type': 'resume', 'ply': ply})
    else:
        runner.log(ctx, {'type': 'config', 'cfg': cfg, 'pos': pos['id'], 'effort': effort, 'rep': rep, 'arm': arm,
                         'set': sets or {}, 'fen': st['fens'][-1], **batch_meta})
    moves = G.legal(st)
    ban = G.banned(st, moves)
    gave_up = None
    try:
        mv, stat, _ = runner.model_turn(ctx, side, moves, ban)
    except Paused as e:
        if ctx.get('tool_call'):
            runner.log(ctx, {'type': 'pause', 'ply': ply, 'why': str(e)})
            raise
        recs = records.read(path)
        n_flags = sum(1 for r in recs if r['type'] == 'attempt' and r.get('ply') == ply
                      and (r.get('flagged') or r.get('empty')))
        runner.log(ctx, {'type': 'pause', 'ply': ply, 'why': str(e)})
        if n_flags <= runner.MAX_FLAGS:
            raise                                    # 撞额度 / 连续调不通：整批停
        mv, stat, gave_up = None, None, 'flags'     # 空回复太多：这一题记成放弃；字段值沿用历史格式
    recs = records.read(path)
    res = {'type': 'result', 'pos': pos['id'], 'game': pos['game'], 'effort': effort, 'rep': rep, 'arm': arm,
           'show': show_of(sets), 'side': side, 'move': mv, 'forfeit': mv is None and gave_up is None, 'gave_up': gave_up}
    res.update(summarize_attempts(recs, ply))
    agg = records.new_stat()
    for r in recs:
        if r['type'] == 'attempt' and r.get('ply') == ply:
            records.add_usage(agg, r.get('usage') or {}, r.get('elapsed') or 0)
            agg['flags'] += bool(r.get('flagged'))
            agg['empty'] += bool(r.get('empty'))
            agg['illegal'] += (not r.get('flagged') and not r.get('empty') and not r.get('legal'))
    res['stat'] = agg
    if (sets or {}).get('threats') == 'on' and mv is not None:
        # 清单以落定那次回答为准（非法重试时前几次的清单不算）
        final = [r for r in recs if r['type'] == 'attempt' and r.get('ply') == ply and r.get('legal') and r.get('move') == mv]
        res['threats'] = threat_score(pos['game'], st['fens'][-1], mv, final[-1].get('reply') if final else '')
    runner.log(ctx, res)
    return res


# ---------------------------------------------------------------- 分档与批次元数据
def _rel(path):
    p = os.path.realpath(str(path))
    root = str(ROOT) + os.sep
    return p[len(root):] if p.startswith(root) else p


def _abs(path):
    return path if os.path.isabs(path) else str(ROOT / path)


def pos_key(p):
    """判两个局面文件里同一 id 是不是同一道题：局面、到这步的着法（中国象棋禁着要看）、对手刚走的那步。"""
    return (p.get('game'), p.get('fen'), tuple(p.get('moves') or ()), p.get('fen_before_opp'), p.get('opp_move'))


def merge_positions(files):
    """几个局面文件按 id 合并；同一 id 内容不同就退出（防止两批局面的同名 id 混进同一个档）。"""
    by = {}
    for f in files:
        for p in load_positions(_abs(f)):
            q = by.get(p['id'])
            if q is not None and pos_key(q) != pos_key(p):
                raise SystemExit('局面 %s 在 %s 里和之前用过的局面文件（%s）内容不同，不能混进同一个档；换个 --arm 或 --batch'
                                 % (p['id'], f, ', '.join(files[:-1])))
            by[p['id']] = p
    return by


def unit_dir(out_root, arm, game):
    return os.path.join(out_root, arm, game) if arm else os.path.join(out_root, game)


def read_meta(d):
    path = os.path.join(d, 'batch.json')
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_meta(d, meta):
    path = os.path.join(d, 'batch.json')
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def meta_positions(meta, batch, game):
    """这个档用过的局面文件；第一批的 batch.json 没记，按默认路径算。"""
    return (meta or {}).get('positions') or [_rel(positions_path(batch, game))]


ATTACKMAP_GATE = ('attackmap 档碰到 AGENTS.md 硬约束「棋手不准用引擎或规则库帮忙」，待用户拍板，未批不准跑'
                  '（plan-batch2 块 A、Q5）。只看提示用 --dry-run；用户批了才加 --allow-attackmap。')


def check_arm(arm):
    if arm and (arm in GAMES or not re.fullmatch(r'[A-Za-z0-9_.-]+', arm)):
        raise SystemExit('档名只用字母、数字、_ . -，且不能叫 %s' % '/'.join(GAMES))


def cmd_run(a):
    game = a.game
    G = game_module(game)
    if a.set and not a.arm:
        raise SystemExit('--set 要和 --arm 一起给（不给档名时布局同第一批）')
    check_arm(a.arm)
    sets = with_default_show(G, parse_sets(G, a.set))
    if sets.get('attackmap') == 'on' and not a.dry_run and not a.allow_attackmap:
        raise SystemExit(ATTACKMAP_GATE)
    pos_file = a.positions or str(positions_path(a.batch, game))
    pos_all = load_positions(pos_file)
    if a.ids:
        want = set(a.ids.split(','))
        pos_all = [p for p in pos_all if p['id'] in want]
        if not pos_all:
            raise SystemExit('一个 id 都没对上：%s' % a.ids)
    skip = [p['id'] for p in pos_all if p.get('excluded')]
    pos_all = active_positions(pos_all)
    if skip:
        print('跳过已剔除的局面：%s（理由见局面文件里的 excluded）' % ', '.join(skip), flush=True)
    if not pos_all:
        raise SystemExit('没有可答的局面（给的 id 都已剔除）')
    efforts = a.efforts.split(',')
    for e in efforts:
        if e not in EFFORTS:
            raise SystemExit('effort 只能是 %s' % '/'.join(EFFORTS))
    if a.dry_run:
        p = pos_all[0]
        st = build_state(p)
        sc = side_cfg(G, efforts[0], sets)
        print('== 系统提示 ==\n%s\n\n== 用户提示（%s）==\n%s' % (
            system_of(G, G.turn(st), sc), p['id'], prompt_of(G, st, sc)))
        return 0
    out_root = a.out or str(ROOT / 'runs' / ('quiz-' + a.batch))
    out = unit_dir(out_root, a.arm, game)
    os.makedirs(out, exist_ok=True)
    meta = read_meta(out)
    if meta is None:
        # claude 的运行目录：仓库外的空临时目录（design.md P7、P17），一批共用一个，记下来续跑沿用
        meta = {'claude_cwd': os.path.join(os.path.realpath(tempfile.gettempdir()), 'agi-chess-cwd',
                                           'quiz-%s-%s%s-%s' % (a.batch, (a.arm + '-') if a.arm else '', game,
                                                                uuid.uuid4().hex[:8])),
                'first_commit': commit(), 'claude_version': claude_cli.version(),
                'arm': a.arm, 'set': sets, 'positions': [_rel(pos_file)]}
        write_meta(out, meta)
    else:
        if (meta.get('set') or {}) != sets:
            raise SystemExit('%s 已有记录，--set 是 %s，这次给的是 %s；不混写，换个 --arm' % (
                out, json.dumps(meta.get('set') or {}, ensure_ascii=False), json.dumps(sets, ensure_ascii=False)))
        files = meta_positions(meta, a.batch, game)
        if _rel(pos_file) not in files:
            merge_positions(files + [_rel(pos_file)])        # 同一 id 内容不同就退出
            meta['positions'] = files + [_rel(pos_file)]
            write_meta(out, meta)
    os.makedirs(meta['claude_cwd'], exist_ok=True)
    batch_meta = {'commit': commit(), 'claude_version': meta['claude_version'], 'model': a.model, 'argv': sys.argv}
    if codex_cli.spec_of(a.model).split(':', 1)[0] in codex_cli.KINDS:
        batch_meta['codex_version'] = codex_cli.version()
    # 先答完第 1 遍的全部局面 × 档位，再答第 2 遍：中途撞额度时，已有的数据各档是齐的
    tasks = [(p, e, r) for r in range(1, a.reps + 1) for p in pos_all for e in efforts]
    todo = [t for t in tasks if not result_of(answer_path(out, t[0]['id'], t[1], t[2]))]
    label = game + ('（档 %s）' % a.arm if a.arm else '')
    print('%s：共 %d 题，已答 %d，这次要答 %d（%d 路并发）' % (label, len(tasks), len(tasks) - len(todo), len(todo), a.jobs),
          flush=True)
    stop = threading.Event()
    refused = threading.Event()
    tool_attempt = threading.Event()
    why = []

    def work(t):
        p, e, r = t
        if claude_cli.STOP.is_set() and not stop.is_set():       # 收到停止信号：不再开新题
            stop.set()
            why.append('收到停止信号')
        if stop.is_set():
            return None
        print('→ %s %s r%d 开始' % (p['id'], e, r), flush=True)
        try:
            res = answer_one(p, e, r, out, a.model, meta['claude_cwd'], batch_meta, sets, a.arm, a.timeout)
        except Refused as ex:
            refused.set()
            stop.set()
            claude_cli.STOP.set()
            why.append(str(ex))
            print('！%s %s r%d 拒答，整批终止：%s' % (p['id'], e, r, ex), flush=True)
            return None
        except ToolAttempt as ex:
            tool_attempt.set()
            stop.set()
            claude_cli.STOP.set()
            why.append(str(ex))
            print('！%s %s r%d 工具尝试，整批暂停分析：%s' % (p['id'], e, r, ex), flush=True)
            return None
        except Paused as ex:
            stop.set()
            why.append(str(ex))
            print('！%s %s r%d 撞额度或调不通，整批停下：%s' % (p['id'], e, r, ex), flush=True)
            return None
        th = res.get('threats')
        print('← %s %s r%d：%s%s%s' % (p['id'], e, r, res['move'],
                                       '（首答非法）' if res.get('first_legal') is False else '',
                                       '（清单 列中 %d / 漏 %d / 错 %d）' % (th['hit'], th['miss'], th['wrong'])
                                       if th else ''), flush=True)
        return res

    # 撞额度默认在 claude_cli.call 里等到解除（--on-limit pause 恢复旧行为：整批停、退出码 3）；
    # 等待中 Ctrl-C / SIGTERM 让所有在等的线程马上醒来收尾，和撞额度暂停一样，再跑同一条命令接着来
    claude_cli.LIMIT_MODE = a.on_limit
    restore = claude_cli.install_stop_handlers()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as ex:
            list(ex.map(work, todo))
    finally:
        restore()
    left = sum(1 for t in tasks if not result_of(answer_path(out, t[0]['id'], t[1], t[2])))
    if refused.is_set():
        print('已因拒答终止，禁止自动续跑；还剩 %d 题，请向用户回报。' % left)
        return 3
    if tool_attempt.is_set():
        print('已因工具尝试暂停，先分析原因，禁止自动续跑；还剩 %d 题。' % left)
        return 3
    if stop.is_set():
        print('停下了（%s）。还剩 %d 题，接着跑同一条命令即可。' % (why[0][:300], left))
        return 3
    print('%s：全部答完（剩 %d）。' % (label, left))
    return 0


def cmd_copy(a):
    """把另一个档里「同一局面、同一提示」的已答记录复制过来当本档的样本（块 A 的 base 档复用块 0 的 zh 复测）。
    局面按内容（pos_key）对上，不看 id；复制前逐个核对系统提示和第一次的用户提示和本档会发的一字不差，不一样就跳过。
    复制出的记录里题号换成本档的 id，config / result 标 copied_from。目标已有的不覆盖。"""
    game = a.game
    G = game_module(game)
    check_arm(a.arm)
    out_root = a.out or str(ROOT / 'runs' / ('quiz-' + a.batch))
    src, dst = unit_dir(out_root, a.from_arm, game), unit_dir(out_root, a.arm, game)
    smeta = read_meta(src)
    if smeta is None:
        raise SystemExit('%s 没有记录' % src)
    sets = smeta.get('set') or {}
    pos_file = a.positions or str(positions_path(a.batch, game))
    dmeta = read_meta(dst)
    if dmeta is not None and (dmeta.get('set') or {}) != sets:
        raise SystemExit('%s 的 --set 是 %s，和来源 %s 的 %s 不同，不能复制' % (
            dst, json.dumps(dmeta.get('set') or {}), src, json.dumps(sets)))
    src_by = {pos_key(p): p for p in merge_positions(meta_positions(smeta, a.batch, game)).values()}
    os.makedirs(dst, exist_ok=True)
    if dmeta is None:
        dmeta = {'claude_cwd': smeta['claude_cwd'], 'first_commit': commit(), 'claude_version': smeta.get('claude_version'),
                 'arm': a.arm, 'set': sets, 'positions': [_rel(pos_file)]}
    else:
        files = meta_positions(dmeta, a.batch, game)
        if _rel(pos_file) not in files:
            merge_positions(files + [_rel(pos_file)])
            dmeta['positions'] = files + [_rel(pos_file)]
    write_meta(dst, dmeta)
    copied, skipped = 0, []
    for p in active_positions(load_positions(pos_file)):
        q = src_by.get(pos_key(p))
        if q is None:
            continue
        st = build_state(p)
        for name in sorted(os.listdir(src)):
            m = re.fullmatch(re.escape(q['id']) + r'-(\w+)-r(\d+)\.jsonl', name)
            if not m:
                continue
            effort, rep = m[1], int(m[2])
            to = answer_path(dst, p['id'], effort, rep)
            recs = records.read(os.path.join(src, name))
            if os.path.exists(to) or not any(r['type'] == 'result' for r in recs):
                continue
            side = G.turn(st)
            sc = side_cfg(G, effort, sets)
            cfg0 = recs[0].get('cfg') or {}
            att = next((r for r in recs if r['type'] == 'attempt'), {})
            if (cfg0.get('system') or {}).get(side) != system_of(G, side, sc) \
                    or att.get('prompt') != prompt_of(G, st, sc):
                skipped.append(name)
                continue
            tmp = to + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                for r in recs:
                    r = dict(r)
                    if 'pos' in r:
                        r['pos'] = p['id']
                    if r['type'] in ('config', 'result'):
                        r['arm'] = a.arm
                        r['copied_from'] = os.path.join(src, name)
                    f.write(json.dumps(r, ensure_ascii=False) + '\n')
            os.replace(tmp, to)
            copied += 1
    print('%s：从档 %s 复制了 %d 条作答到档 %s%s' % (game, a.from_arm, copied, a.arm,
                                              '；提示对不上跳过 %d 条：%s' % (len(skipped), ', '.join(skipped)) if skipped else ''))
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
    _require_rules()
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


def threat_class(row):
    """threats 档一条大失误归哪类：listed 列出来了还这么走；unlisted 根本没列出来；quiet 引擎给的对方最强应着不是吃子
    或将军（不在清单口径内）；no_list 没写清单。依据是引擎在走后局面的首选应着（row['refute']）。"""
    th = row.get('threats')
    if not th or not th.get('found'):
        return 'no_list'
    ref = row.get('refute')
    if ref is None or ref not in th['true']:
        return 'quiet'
    return 'listed' if ref in th['listed'] else 'unlisted'


def judge_units(out_root, arm=None, game='all'):
    """out_root 下要判的 (档名或 None, 棋种)。第一批的旧布局 <棋种>/ 档名记 None；arm 为 None 时全判。"""
    games = GAMES if game == 'all' else (game,)
    out = [(None, g) for g in games if arm is None and os.path.isdir(os.path.join(out_root, g))]
    names = sorted(d for d in os.listdir(out_root) if d not in GAMES and os.path.isdir(os.path.join(out_root, d))) \
        if os.path.isdir(out_root) else []
    out += [(d, g) for d in names if arm in (None, d) for g in games if os.path.isdir(os.path.join(out_root, d, g))]
    return out


def judge_game(game, batch, out_root, positions=None, arm=None):
    ans_dir = unit_dir(out_root, arm, game)
    meta = read_meta(ans_dir)
    pos_by = merge_positions([positions] if positions else meta_positions(meta, batch, game))
    show = show_of((meta or {}).get('set'))
    results = []
    for name in sorted(os.listdir(ans_dir)) if os.path.isdir(ans_dir) else []:
        if name.endswith('.jsonl') and name != 'judged.jsonl':
            r = result_of(os.path.join(ans_dir, name))
            if r:
                results.append(r)
    if not results:
        raise SystemExit('%s 下未找到单题原始作答记录（*.jsonl，不含 judged.jsonl）；重判依赖未入库的单题作答记录，公开克隆可直接用 quiz report 查看已入库的 judged.jsonl。' % ans_dir)
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
                                     'tab': static_table(R, fen), 'after': {}, 'refute': {}}
                print('  判 %s：走前 %s，引擎最佳 %s' % (res['pos'], before, cache[res['pos']]['best']), flush=True)
            c = cache[res['pos']]
            row = {k: res.get(k) for k in ('pos', 'game', 'effort', 'rep', 'side', 'move', 'forfeit', 'gave_up',
                                           'attempts', 'first_legal', 'first_move_text', 'first_think', 'first_elapsed',
                                           'call_fails', 'timeouts')}
            row['arm'] = arm
            row['show'] = show
            row['stat'] = res['stat']
            row['before'] = c['before']
            row['engine_best'] = c['best']
            if res.get('threats'):
                row['threats'] = res['threats']
            mv = res['move']
            if mv is None:
                rows.append(row)
                continue
            if mv not in c['after']:
                f1 = R.play(fen, mv)
                if not R.legal(f1):
                    term = R.no_move_value(f1)
                    c['after'][mv] = {'mate': 0} if term == LOSE else {'cp': 0}
                    c['refute'][mv] = None
                else:
                    a1 = analyse(eng, start, hist + [to_eng(game, mv)])
                    c['after'][mv] = neg(a1)
                    c['refute'][mv] = from_eng(game, a1['best']) if a1.get('best') else None
            before, after = c['before'], c['after'][mv]
            row['after'] = after
            row['refute'] = c['refute'][mv]              # 引擎在走后局面给对方的首选应着
            row['loss'] = clip(before) - clip(after)
            row['best_match'] = mv == c['best']
            row.update(labels(c['tab'], mv))
            if game == 'xiangqi':
                row['blunder'] = row['loss'] >= XQ_BIG
                row['mistake'] = XQ_MIS <= row['loss'] < XQ_BIG
                row['solved'] = row['best_match']
                row['same_as_prev'] = mv == pos.get('prev_move')
            else:
                j = lichess_judgement(before, after)
                row['judgement'] = j
                row['blunder'] = j == 'blunder'
                row['mistake'] = j == 'mistake'
                row['winpct_drop'] = round(win_pct(before) - win_pct(after), 1)
                b = chess.Board(fen)
                b.push(chess.Move.from_uci(mv))
                row['solved'] = mv == pos.get('solution') or b.is_checkmate()
            if row.get('threats'):
                row['threat_class'] = threat_class(row) if row['blunder'] else None
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
    units = judge_units(out_root, a.arm, a.game)
    if not units:
        print('%s 下没有要判的作答记录' % out_root)
    for arm, game in units:
        rows, path = judge_game(game, a.batch, out_root, arm=arm)
        print('%s%s：判了 %d 条 → %s\n  %s' % (game, '（档 %s）' % arm if arm else '', len(rows), path, engine_note(game)))
    return 0


# ---------------------------------------------------------------- 汇总
def _pct(n, d):
    return '%.0f%%' % (100.0 * n / d) if d else '-'


def _med(xs):
    xs = [x for x in xs if x is not None]
    return '%.0f' % statistics.median(xs) if xs else '-'


COLS = ('棋种', '档位', '样本', '首答非法', '判负/放弃', '大失误', '失误', '平均亏损', '与引擎最佳一致', '解中',
        '白送子', '漏吃', '谁能吃到谁类昏招', '漏杀', '送杀', '思考tok中位', '首答思考中位', '耗时中位s', '拦截', '空回复')


def _groups(rows):
    """按 (档名, effort) 分组，档名 None（第一批旧布局）在前、其余按名字，effort 按 EFFORTS 顺序。"""
    by = collections.defaultdict(list)
    for r in rows:
        by[(r.get('arm'), r['effort'])].append(r)
    order = lambda k: (k[0] is not None, k[0] or '', EFFORTS.index(k[1]) if k[1] in EFFORTS else 99, k[1])
    return [(k, by[k]) for k in sorted(by, key=order)]


def report_rows(game, rows, with_arm=False):
    out = []
    for (arm, e), rs in _groups(rows):
        n = len(rs)
        firsts = [r for r in rs if r.get('first_legal') is not None]
        judged = [r for r in rs if r.get('move') is not None]
        m = len(judged)
        cnt = lambda k: sum(1 for r in judged if r.get(k))
        capture = sum(1 for r in judged if (r['hang'] or r['missed_capture']) and (r['blunder'] or r['mistake']))
        out.append([game] + ([arm or '-'] if with_arm else []) + [
                    e, str(n), _pct(sum(1 for r in firsts if not r['first_legal']), len(firsts)),
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


THREAT_COLS = ('棋种', '档', 'effort', '有着法的作答', '写了清单', '写「无」', '真实威胁', '列中', '列出比例', '错列',
               '列全且无错', '大失误', '列出了还走', '没列出', '反击非吃子将军', '没写清单')


def threat_rows(game, rows):
    out = []
    for (arm, e), rs in _groups(rows):
        rs = [r for r in rs if r.get('threats') and r.get('move') is not None]
        if not rs:
            continue
        ths = [r['threats'] for r in rs]
        true = sum(len(t['true']) for t in ths)
        hit = sum(t['hit'] for t in ths)
        bl = [r for r in rs if r.get('blunder')]
        cls = collections.Counter(r.get('threat_class') or threat_class(r) for r in bl)
        out.append([game, arm or '-', e, str(len(rs)), str(sum(t['found'] for t in ths)), str(sum(t['none'] for t in ths)),
                    str(true), str(hit), _pct(hit, true), str(sum(t['wrong'] for t in ths)),
                    str(sum(1 for t in ths if t['found'] and not t['miss'] and not t['wrong'])),
                    str(len(bl)), str(cls['listed']), str(cls['unlisted']), str(cls['quiet']), str(cls['no_list'])])
    return out


REPORT_NOTES = [
    '样本：已答完的作答数（局面 × 遍）。首答非法：第一次既没被拦也不是空回复的回答里给了非法着 / 没写出着法的比例。',
    '判负/放弃：重试 3 次仍非法 / 空回复超过上限（旧记录还含拦截超限）；这两类不进后面的比例。明确拒答现行规则为终止，不记结果。',
    '平均亏损：厘兵，负数按 0 计。与引擎最佳一致：走的正是引擎首选。解中：国际象棋走的是谜题正解首着或直接将死。',
    '白送子 / 漏吃 / 漏杀 / 送杀：静态子力判定（口径见 quiz.py「规则判定」注释）；谁能吃到谁类昏招 = (白送子 或 漏吃) 且引擎判失误以上。',
    '思考 tok：一次作答所有尝试合计；首答思考：第一次有效回答的思考 token。耗时：一次作答所有尝试合计。',
]
THREAT_NOTES = [
    'threats 清单打分（只数落定那次回答的清单）：真实威胁 = 走完所走着法后对方全部合法的吃子着法和将军着法（规则由 pyffish / '
    'python-chess 判）；列中 / 错列按着法逐条比，错列含列了但不是吃子或将军的着法、不合法或读不出的行；列出比例 = 列中 / 真实威胁。',
    '大失误归类（大失误口径同上表）：看引擎在走后局面给对方的首选应着——它是吃子或将军且在清单里 = 列出了还走；是吃子或将军但'
    '清单里没有 = 没列出；不是吃子或将军 = 反击非吃子将军（不在清单口径内）；回答里没有清单 = 没写清单。',
]


def cmd_report(a):
    out_root = a.out or str(ROOT / 'runs' / ('quiz-' + a.batch))
    units = judge_units(out_root)
    with_arm = any(arm for arm, _ in units)
    rows_by = collections.defaultdict(list)
    for arm, game in units:
        path = os.path.join(unit_dir(out_root, arm, game), 'judged.jsonl')
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                rows_by[game] += [dict(json.loads(l), arm=arm) for l in f if l.strip()]
    table, threats, notes = [], [], []
    for game in GAMES:
        if rows_by[game]:
            table += report_rows(game, rows_by[game], with_arm)
            threats += threat_rows(game, rows_by[game])
            notes.append('%s：%s' % (game, engine_note(game)))
    if not table:
        raise SystemExit('没有 judged.jsonl，先跑 judge')
    cols = COLS[:1] + (('档',) if with_arm else ()) + COLS[1:]
    lines = ['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
    lines += ['| ' + ' | '.join(r) + ' |' for r in table]
    lines += [''] + notes + REPORT_NOTES
    if threats:
        lines += ['', '| ' + ' | '.join(THREAT_COLS) + ' |', '|' + '---|' * len(THREAT_COLS)]
        lines += ['| ' + ' | '.join(r) + ' |' for r in threats]
        lines += [''] + THREAT_NOTES
    text = '\n'.join(lines) + '\n'
    path = os.path.join(out_root, 'report.txt')
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)
    print(text + '\n（已写 %s）' % path)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m agi_chess.quiz', description=__doc__.split('\n')[0],
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
    r.add_argument('--model', default='opus',
                   help='claude 模型名（默认 opus）；sol（= codex:gpt-6-sol）、deepseek（= profile 默认模型）、'
                        'codex:<模型>、deepseek:<模型> 走 codex exec，只支持无状态，见 codex_cli.py')
    r.add_argument('--arm', help='档名：记录放 runs/quiz-<batch>/<档名>/<棋种>/；不给时布局同第一批')
    r.add_argument('--set', action='append', metavar='变量=值',
                   help='本档改的变量，可重复：view / show / legal / selfcheck / recite / threats / attackmap / reason（attackmap 待用户拍板，见上）')
    r.add_argument('--allow-attackmap', dest='allow_attackmap', action='store_true',
                   help='attackmap=on 真跑的开关。待用户拍板，未批不准用')
    r.add_argument('--timeout', type=int, default=claude_cli.TIMEOUT, help='单次 claude -p 调用的超时秒数，默认 3600')
    r.add_argument('--on-limit', dest='on_limit', choices=('wait', 'pause'), default='wait',
                   help='撞额度时：wait（默认）在程序里等到解除接着答，起止记 limit_wait；pause 是旧行为，整批停、退出码 3')
    r.add_argument('--dry-run', action='store_true', help='只打印第一个局面的系统提示和用户提示')
    c = sub.add_parser('copy', help='把另一个档里同一局面、同一提示的已答记录复制成本档的样本')
    c.add_argument('--game', required=True, choices=GAMES)
    c.add_argument('--batch', default='batch1')
    c.add_argument('--positions', help='本档的局面文件，默认 data/<batch>/<棋种>.jsonl')
    c.add_argument('--out')
    c.add_argument('--from-arm', dest='from_arm', required=True, help='来源档名（同一个 runs/quiz-<batch>/ 下）')
    c.add_argument('--arm', required=True, help='目标档名')
    j = sub.add_parser('judge', help='引擎事后判')
    j.add_argument('--game', default='all', choices=GAMES + ('all',))
    j.add_argument('--batch', default='batch1')
    j.add_argument('--arm', help='只判这个档；不给就判全部（含第一批旧布局）')
    j.add_argument('--out')
    p = sub.add_parser('report', help='汇总表（按档分组）')
    p.add_argument('--batch', default='batch1')
    p.add_argument('--out')
    a = ap.parse_args(argv)
    return {'run': cmd_run, 'copy': cmd_copy, 'judge': cmd_judge, 'report': cmd_report}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
