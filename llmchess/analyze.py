"""事后引擎分析：逐步亏损、大失误 / 失误，以及多盘汇总表（design.md 第四节末尾）。

    python3 -m llmchess.analyze runs/<tag> [runs/<tag2> ...]          # 逐步分析，写 analysis.jsonl 和 analysis-summary.json
    python3 -m llmchess.analyze --force runs/<tag>                     # 参数一致也重算
    python3 -m llmchess.analyze --table runs/a runs/b ...              # 每盘一行、模型方的数字；缺分析的先补
    python3 -m llmchess.analyze --table --out runs/t1 runs/*           # 表另存 runs/t1.md 和 runs/t1.json

口径：
  - 按 config 和 move 事件从起始局面重放全部落定着法（棋种模块的 start / push / ending），每个局面问一次引擎
    （起始局面加完整历史，和对局时一样）。走前评分 = 走子方在走前局面的评分，走后评分 = 走完之后局面评分取反，
    都是走子方视角；终局局面不问引擎，按棋种的终局判定给胜负或 0。
  - 厘兵亏损 = 截断到 ±1000 的走前评分 − 截断后的走后评分（杀棋分数当 ±1000）。亏 ≥250 大失误、100–250 失误，
    只在「未分胜负」的步里数：走前评分不是杀棋分数、且绝对值 <1000
    （~/repos/ai-research/topics/llm-xiangqi-play.md 第三节口径原文：「走前分数绝对值 <1000，且引擎还没算出杀棋」）。
    国际象棋沿用同一组厘兵阈值，只作参照，主口径看下面的 lichess 胜率。
  - 件数：同一方连续几步（该方相邻两步）都是大失误并成一件；另给两方合在一起、相邻半回合并成一件的全局件数
    （上一轮 stats.py 的数法）。
  - ACPL：全部步的 max(0, 截断亏损) 取平均（上一轮 stats.py 的数法）；另给只算未分胜负步的 acpl_undecided。
  - 国际象棋另给 lichess 口径，照 lila / scalachess 现行源码（2026-09-25 查）：
      winningChances(cp) = 2 / (1 + exp(-0.00368208 * cp)) − 1，结果夹在 [−1, 1]
        （scalachess core/src/main/scala/eval.scala，WinPercent.winningChances；系数出自 lila PR #11148）；
      两边都是厘兵时，走子方视角 delta = 走前 winningChances − 走后 winningChances，
        ≥0.3 大失误（Blunder）、≥0.2 失误（Mistake）、≥0.1 不精确（Inaccuracy）
        （lila modules/tree/src/main/Advice.scala，CpAdvice.winningChanceJudgements；换成 0–100 的胜率是 15 / 10 / 5 个点）；
      有杀棋分数时走 MateAdvice：厘兵→被杀（MateCreated）按走前厘兵分，< −999 不精确、< −700 失误、否则大失误；
        有杀→没杀（MateLost，含有杀→被杀）按走后厘兵分（被杀时当 0），> 999 不精确、> 700 失误、否则大失误；
        其余（比如杀得慢了）不判。lichess 对全部步都判，这里也一样，不按未分胜负筛。
    wc_loss 字段就是上面那个 delta；win%（0–100）= 50 + 50 × winningChances，lichess 在 WinPercent.fromCentiPawns
    里先把厘兵截到 ±1000 再换，CpAdvice 这里不截，照抄。
  - 引擎：国际象棋 Stockfish 固定深度 18，中国象棋 Fairy-Stockfish（UCI_Variant xiangqi）固定深度 16（同上一轮）；
    单线程、每个局面前 ucinewgame 清哈希，同一局面重跑结果一样。
  - 阶段分桶：按该方第几步分成 1–15、16–30、31–45、46+。

没下完的盘（有 pause 没 end）照样分析已落定的着法；分析参数一致、步数也没变就跳过。
"""
import argparse, json, math, os, re, statistics, sys

from . import records
from .cli import game_module
from .engine import Engine

VERSION = 1                       # 口径或输出字段改了就加一，旧结果会被判为参数不一致而重算
DEPTH = {'chess': 18, 'xiangqi': 16}
HASH = 64
CLIP = 1000
BIG, MIS = 250, 100
PHASES = ((1, 15), (16, 30), (31, 45), (46, None))
LICHESS_WC = ((0.3, 'Blunder'), (0.2, 'Mistake'), (0.1, 'Inaccuracy'))
ENGINE_TIMEOUT = 600


# ---------------------------------------------------------------- 评分
# 评分统一写成 (种类, 数)，视角由上下文定：('cp', 厘兵)、('mate', N)（N>0 这方 N 步杀对方，N<0 这方被杀）、
# ('end', 1 / -1)（已经终局：这方赢 / 输；和棋直接写 ('cp', 0)）。
def neg(s):
    return (s[0], -s[1])


def value(s):
    """截断到 ±CLIP 的厘兵值；杀棋和终局当 ±CLIP。"""
    if s[0] == 'cp':
        return max(-CLIP, min(CLIP, s[1]))
    return CLIP if s[1] > 0 else -CLIP


def show(s):
    return {'cp': 'cp %d', 'mate': 'mate %d'}.get(s[0], 'end %+d') % s[1]


def decided(s):
    return s[0] != 'cp' or abs(s[1]) >= CLIP


_INFO = re.compile(r'\bdepth (\d+)\b.*?\bscore (cp|mate) (-?\d+)( (?:lower|upper)bound)?')


def parse_search(lines):
    """UCI 搜索输出 -> (评分, 深度, 最佳着法或 None)。只取主变（multipv 1 或不写）最后一条非上下界的 score。"""
    score, depth = None, None
    for line in lines:
        if not line.startswith('info ') or ' score ' not in line:
            continue
        mp = re.search(r'\bmultipv (\d+)', line)
        if mp and mp.group(1) != '1':
            continue
        m = _INFO.search(line)
        if not m or m.group(4):
            continue
        depth, score = int(m.group(1)), (m.group(2), int(m.group(3)))
    t = lines[-1].split() if lines else []
    best = t[1] if len(t) >= 2 and t[0] == 'bestmove' and t[1] not in ('(none)', '0000') else None
    return score, depth, best


class Analyser(Engine):
    """engine.py 的收发加一个「这个局面评多少分」。"""

    def evaluate(self, start_fen, moves):
        self._send('ucinewgame')
        self._send('isready')
        self._until('readyok')
        self._send('position fen %s%s' % (start_fen, (' moves ' + ' '.join(moves)) if moves else ''))
        self._send(self.spec['go'])
        score, depth, best = parse_search(self._until('bestmove'))
        if score is None:
            raise RuntimeError('引擎 %s 没给出评分' % self.spec['name'])
        return score, depth, best


def analysis_spec(game, depth):
    G = game_module(game)
    spec = G.engine_spec(('stockfish:depth=%d' if game == 'chess' else 'fsf:depth=%d') % depth)
    spec = dict(spec, name='%s-analysis' % spec['name'])
    spec['options'] = [(k, str(HASH) if k == 'Hash' else v) for k, v in spec['options']]
    return spec


# ---------------------------------------------------------------- lichess 口径（出处见模块说明）
def winning_chances(cp):
    return max(-1.0, min(1.0, 2 / (1 + math.exp(-0.00368208 * cp)) - 1))


def win_percent(s):
    """0–100，WinPercent.fromScore：厘兵先截到 ±1000；杀棋按符号当 ±1000。"""
    cp = max(-1000, min(1000, s[1])) if s[0] == 'cp' else (1000 if s[1] > 0 else -1000)
    return 50 + 50 * winning_chances(cp)


def lichess_judgement(before, after):
    """走子方视角的走前、走后评分 -> (判定或 None, winningChances 的 delta 或 None)。"""
    if before[0] == 'cp' and after[0] == 'cp':
        d = winning_chances(before[1]) - winning_chances(after[1])
        return next((name for th, name in LICHESS_WC if d >= th), None), d
    b_mate, a_mate = before[0] != 'cp', after[0] != 'cp'
    b_cp = before[1] if not b_mate else 0
    a_cp = after[1] if not a_mate else 0
    if not b_mate and a_mate and after[1] < 0:                      # MateCreated
        return ('Inaccuracy' if b_cp < -999 else 'Mistake' if b_cp < -700 else 'Blunder'), None
    if b_mate and before[1] > 0 and (not a_mate or after[1] < 0):     # MateLost
        return ('Inaccuracy' if a_cp > 999 else 'Mistake' if a_cp > 700 else 'Blunder'), None
    return None, None


# ---------------------------------------------------------------- 读记录、重放
def load_run(run_dir):
    recs = records.read(os.path.join(run_dir, 'game.jsonl'))
    if not recs or recs[0]['type'] != 'config':
        raise SystemExit('%s：game.jsonl 第一行应是 config' % run_dir)
    return recs[0]['cfg'], recs


def moves_of(recs):
    mv = sorted((r for r in recs if r['type'] == 'move'), key=lambda r: r['ply'])
    for i, r in enumerate(mv):
        assert r['ply'] == i + 1, ('记录里的半回合号对不上', r['ply'], i + 1)
    return mv


def terminal_score(end, stm):
    """终局局面在走子方 stm 视角的评分。"""
    if end['winner'] is None:
        return ('cp', 0)
    return ('end', 1 if end['winner'] == stm else -1)


def params_of(cfg, depth, eng_id):
    return {'version': VERSION, 'game': cfg['game'], 'engine': eng_id, 'depth': depth, 'hash': HASH, 'threads': 1,
            'clip': CLIP, 'big': BIG, 'mistake': MIS}


def analyse_run(run_dir, depth=None, force=False, log=print):
    """分析一盘。返回 summary dict（跳过时读旧的）。"""
    cfg, recs = load_run(run_dir)
    game = cfg['game']
    depth = depth or DEPTH[game]
    G = game_module(game)
    mrecs = moves_of(recs)
    out_rows = os.path.join(run_dir, 'analysis.jsonl')
    out_sum = os.path.join(run_dir, 'analysis-summary.json')
    spec = analysis_spec(game, depth)
    if not force and os.path.exists(out_rows) and os.path.exists(out_sum):
        try:
            with open(out_sum, encoding='utf-8') as f:
                old = json.load(f)
            p = old.get('params', {})
            if (old.get('plies') == len(mrecs) and p.get('version') == VERSION and p.get('depth') == depth
                    and p.get('hash') == HASH and p.get('game') == game):
                log('%s：已分析过（%d 个半回合，深度 %d），跳过' % (run_dir, len(mrecs), depth))
                return old
        except (OSError, ValueError):
            pass
    st = G.start()
    rows = []
    with Analyser(spec, timeout=ENGINE_TIMEOUT) as eng:
        def score_now():
            """当前局面走子方视角的 (评分, 深度, 引擎最佳着)。"""
            end = G.ending(st)
            if end is not None:
                return terminal_score(end, G.turn(st)), None, None
            s, d, b = eng.evaluate(st['fens'][0], [G.to_engine(m) for m in st['moves']])
            return s, d, (G.from_engine(b) if b else None)

        cur = score_now()
        count = {'w': 0, 'b': 0}
        for r in mrecs:
            side = G.turn(st)
            assert side == r['side'], ('记录里的走子方对不上', r['ply'], side, r['side'])
            count[side] += 1
            fen_before = st['fens'][-1]
            before, d_before, best = cur
            G.push(st, r['move'])
            cur = score_now()
            after = neg(cur[0])
            loss = value(before) - value(after)
            row = {'ply': r['ply'], 'side': side, 'n': count[side], 'player': cfg['players'][side],
                   'move': r['move'], 'text': st['record'][-1], 'fen': fen_before,
                   'before': show(before), 'after': show(after), 'before_v': value(before), 'after_v': value(after),
                   'loss': loss, 'best': best, 'played_best': best == r['move'], 'depth': d_before,
                   'decided': decided(before),
                   'cls': None if decided(before) else 'blunder' if loss >= BIG else 'mistake' if loss >= MIS else None}
            if game == 'chess':
                j, d = lichess_judgement(before, after)
                row.update({'wp_before': round(win_percent(before), 1), 'wp_after': round(win_percent(after), 1),
                            'wc_loss': None if d is None else round(d, 4), 'lichess': j})
            rows.append(row)
            log('  %s 第 %d 步 %s %s：%s → %s，亏 %d%s' % (run_dir, r['ply'], side, row['text'], row['before'],
                                                      row['after'], loss, ' ' + row['cls'] if row['cls'] else ''))
        eng_id = eng.id
    summ = summarize(rows, cfg)
    summ['params'] = params_of(cfg, depth, eng_id)
    summ['plies'] = len(rows)
    write_atomic(out_rows, ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    write_atomic(out_sum, json.dumps(summ, ensure_ascii=False, indent=1) + '\n')
    return summ


def write_atomic(path, text):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------- 汇总
def _rate(a, b):
    return round(a / b, 4) if b else None


def _mean(xs):
    return round(sum(xs) / len(xs), 1) if xs else None


def events(plies):
    """plies 是同一方大失误的半回合号（已排序）；该方相邻两步（半回合号差 2）都是大失误就并成一件。"""
    return sum(1 for i, p in enumerate(plies) if i == 0 or p - plies[i - 1] > 2)


def summarize(rows, cfg):
    out = {'game': cfg['game'], 'sides': {}}
    for side in 'wb':
        rs = [r for r in rows if r['side'] == side]
        und = [r for r in rs if not r['decided']]
        big = [r['ply'] for r in und if r['cls'] == 'blunder']
        s = {'player': cfg['players'][side], 'plies': len(rs), 'undecided': len(und),
             'blunders': len(big), 'mistakes': sum(r['cls'] == 'mistake' for r in und),
             'events': events(big),
             'acpl': _mean([max(0, r['loss']) for r in rs]),
             'acpl_undecided': _mean([max(0, r['loss']) for r in und])}
        s['blunder_rate'] = _rate(s['blunders'], len(und))
        s['mistake_rate'] = _rate(s['mistakes'], len(und))
        if cfg['game'] == 'chess':
            lj = {k: sum(r['lichess'] == k for r in rs) for k in ('Inaccuracy', 'Mistake', 'Blunder')}
            s['lichess'] = dict(lj, **{k + '_rate': _rate(v, len(rs)) for k, v in lj.items()})
            s['lichess']['avg_wp_loss'] = _mean([max(0, r['wp_before'] - r['wp_after']) for r in rs])   # 胜率点（0–100）
        s['phases'] = []
        for lo, hi in PHASES:
            ps = [r for r in rs if r['n'] >= lo and (hi is None or r['n'] <= hi)]
            s['phases'].append({'range': '%d-%s' % (lo, hi or ''), 'plies': len(ps),
                                'undecided': sum(not r['decided'] for r in ps),
                                'blunders': sum(r['cls'] == 'blunder' for r in ps),
                                'acpl': _mean([max(0, r['loss']) for r in ps])})
        out['sides'][side] = s
    big_all = sorted(r['ply'] for r in rows if r['cls'] == 'blunder')
    out['events_global'] = sum(1 for i, p in enumerate(big_all) if i == 0 or p - big_all[i - 1] > 1)
    return out


# ---------------------------------------------------------------- 多盘表
def _median(xs):
    return statistics.median(xs) if xs else None


def thirds(xs):
    n = len(xs)
    return [_median(xs[n * i // 3:n * (i + 1) // 3]) for i in range(3)]


def usage_row(recs, side):
    """这一方的调用统计：非法、退回、拦截、空回复、每步 token 中位、合计花费与用时。"""
    att = [r for r in recs if r['type'] == 'attempt' and r['side'] == side]
    costs = records.attempt_costs(recs)[0]    # session 档记录里的 cost 是会话累计值（旧记录）或已做差（新记录），统一按会话做差
    stats = [r['stat'] for r in recs if r['type'] in ('move', 'forfeit') and r.get('side') == side]
    tot_in = [s.get('in', 0) + s.get('cache_read', 0) + s.get('cache_write', 0) for s in stats]
    return {
        'illegal': sum(r.get('legal') is False for r in att),
        'noparse': sum(r.get('legal') is False and r.get('move_text') is None for r in att),
        'retries': len(att) - len({r['ply'] for r in att}),
        'flags': sum(r['type'] == 'flag' and r.get('side') == side for r in recs),
        'empty': sum(bool(r.get('empty')) for r in att),
        'median_input': _median(tot_in),
        'median_cache_read': _median([s.get('cache_read', 0) for s in stats]),
        'median_out': _median([s.get('out', 0) for s in stats]),
        'median_think': _median([s.get('think', 0) for s in stats]),
        'input_thirds': thirds(tot_in),
        'cost': round(sum(costs[id(r)] for r in att), 4),
        'elapsed': round(sum(r.get('elapsed') or 0 for r in att), 1),
    }


def end_of(recs):
    """(终局 dict 或 None, 是否下完)。"""
    for r in reversed(recs):
        if r['type'] in ('end', 'forfeit'):
            return r['end'], True
    return None, False


def table_rows(run_dirs, depth=None, force=False, log=print):
    out = []
    for d in run_dirs:
        cfg, recs = load_run(d)
        summ = analyse_run(d, depth, force, log)
        end, done = end_of(recs)
        for side in 'wb':
            if not str(cfg['players'][side]).startswith('claude'):
                continue
            opp = 'b' if side == 'w' else 'w'
            sc = cfg['sides'][side]
            a = summ['sides'][side]
            if not done:
                result, reason = '未完', next((r['why'] for r in reversed(recs) if r['type'] == 'pause'), '没有 end')
            else:
                result = '和' if end['winner'] is None else '胜' if end['winner'] == side else '负'
                reason = end['reason']
            row = {'run': os.path.basename(os.path.normpath(d)), 'game': cfg['game'], 'side': side,
                   'player': cfg['players'][side], 'opponent': cfg['players'][opp],
                   'memory': sc.get('memory'), 'effort': sc.get('effort'), 'finished': done,
                   'result': result, 'reason': reason, 'plies': a['plies'], 'undecided': a['undecided'],
                   'blunders': a['blunders'], 'blunder_rate': a['blunder_rate'], 'mistakes': a['mistakes'],
                   'events': a['events'], 'acpl': a['acpl'],
                   'lichess_blunders': a['lichess']['Blunder'] if 'lichess' in a else None,
                   'phases': a['phases'], 'depth': summ['params']['depth']}
            row.update(usage_row(recs, side))
            out.append(row)
    return out


def _f(v, fmt='%s'):
    return '–' if v is None else fmt % v


GAME_ZH = {'chess': '国际象棋', 'xiangqi': '中国象棋'}


def markdown(rows):
    head = ['盘', '棋种', '模型方', '对手', 'memory', 'effort', '结果', '终局原因', '半回合', '大失误（率）', '失误',
            '件数', 'ACPL', 'lichess 大失误', '非法', '退回', '拦截', '空回复', '每步输入中位', '缓存读中位',
            '输出中位', '思考中位', '输入 前/中/后', '花费 $', '用时 分']
    lines = ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
    for r in rows:
        cells = [r['run'], GAME_ZH.get(r['game'], r['game']), '%s %s' % (r['side'], r['player']), r['opponent'],
                 r['memory'], r['effort'], r['result'], r['reason'].replace('|', '/'), r['plies'],
                 '%d（%s，分母 %d）' % (r['blunders'], _f(r['blunder_rate'] if r['blunder_rate'] is None
                                                  else 100 * r['blunder_rate'], '%.0f%%'), r['undecided']),
                 r['mistakes'], r['events'], _f(r['acpl']), _f(r['lichess_blunders']), r['illegal'], r['retries'],
                 r['flags'], r['empty'], _f(r['median_input'], '%.0f'), _f(r['median_cache_read'], '%.0f'),
                 _f(r['median_out'], '%.0f'), _f(r['median_think'], '%.0f'),
                 '/'.join(_f(x, '%.0f') for x in r['input_thirds']), '%.2f' % r['cost'], '%.1f' % (r['elapsed'] / 60)]
        lines.append('| ' + ' | '.join(str(c) for c in cells) + ' |')
    lines.append('')
    lines.append('大失误率的分母是未分胜负的步（走前评分不是杀棋且绝对值 <1000）；ACPL 是全部步截断 ±1000 后的平均亏损；'
                 '输入 = 无缓存输入 + 缓存读 + 缓存写，每步合计本步各次尝试；前/中/后是按模型步数三等分的中位数。')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m llmchess.analyze', description=__doc__.split('\n')[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument('dirs', nargs='+', help='runs/<tag> 目录')
    ap.add_argument('--force', action='store_true', help='参数一致也重算')
    ap.add_argument('--depth', type=int, help='引擎深度，默认国际象棋 %(chess)d、中国象棋 %(xiangqi)d' % DEPTH)
    ap.add_argument('--table', action='store_true', help='多盘汇总成一张表（缺分析的先补）')
    ap.add_argument('--out', help='表另存成 <out>.md 和 <out>.json，默认第一盘的上级目录下 table.md / table.json')
    ap.add_argument('--quiet', action='store_true', help='不逐步打印')
    a = ap.parse_args(argv)
    log = (lambda *x: None) if a.quiet else (lambda *x: print(*x, flush=True))
    if not a.table:
        for d in a.dirs:
            s = analyse_run(d, a.depth, a.force, log)
            print(json.dumps({'run': d, 'sides': {k: {x: v[x] for x in ('plies', 'undecided', 'blunders', 'mistakes',
                                                                        'events', 'acpl')}
                                                  for k, v in s['sides'].items()}}, ensure_ascii=False))
        return 0
    rows = table_rows(a.dirs, a.depth, a.force, log)
    md = markdown(rows)
    out = a.out or os.path.join(os.path.dirname(os.path.normpath(a.dirs[0])), 'table')
    write_atomic(out + '.md', md)
    write_atomic(out + '.json', json.dumps(rows, ensure_ascii=False, indent=1) + '\n')
    print(md)
    print('已写 %s.md、%s.json' % (out, out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
