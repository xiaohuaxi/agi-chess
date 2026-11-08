#!/usr/bin/env python3
"""opus max 棋力定位（docs/results/opus-max-rating.md）的对局汇总：读本机 runs/zc、runs/zx（及旧协议对照批次 runs/b1、
runs/b2），出一份中文 markdown——按对手的战绩、每盘明细（花费、思考 token、耗时、非法、被拦、等额度、墙钟）、合计、
同开局新旧协议对照。刻度与人类刻度不在这里，见同目录 rate.py（只读入库的 csv，不要 runs/）。

只依赖本地原始对局记录 game.jsonl（公开仓库仅入库脱敏后的 game.pgn / analysis.jsonl / summary.*，不含 game.jsonl）；
没下完 / 没分析的盘稳妥跳过并注明。大失误、ACPL 要先跑过事后分析
（python3 -m agi_chess.batch summary runs/zc --analyze）。

    python3 analysis/rating/stats.py [--out 路径]     # 默认打到标准输出
"""
import argparse, datetime, os, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from agi_chess import batch, analyze, records  # noqa: E402

RUNS = os.path.join(ROOT, 'runs')
GAME_ZH = {'chess': '国际象棋', 'xiangqi': '中国象棋'}


# ---------------------------------------------------------------- 小工具
def f(v, fmt='%s'):
    return '–' if v is None else fmt % v


def pct(x):
    return '–' if x is None else '%.0f%%' % (100 * x)


def parse_t(s):
    return datetime.datetime.fromisoformat(s)


def median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def opus_side(cfg):
    for s in 'wb':
        if str(cfg['players'][s]).startswith('claude'):
            return s
    return None


# ---------------------------------------------------------------- 每盘用量细节（花费、思考、耗时、非法、拦截、等额度、墙钟、工具调用）
def game_usage(gdir, name):
    path = os.path.join(gdir, 'game.jsonl')
    recs = records.read(path)
    if not recs or recs[0].get('type') != 'config':
        return None
    cfg = recs[0]['cfg']
    side = opus_side(cfg)
    if side is None:          # 双方都不是模型（标定批次），不是我们要的盘
        return None
    u = analyze.usage_row(recs, side)                     # illegal / flags（拦截）/ cost / median_think 等，口径见 analyze.py
    mv_stats = [r['stat'] for r in recs if r.get('type') in ('move', 'forfeit') and r.get('side') == side
               and not r.get('opening')]
    think_vals = [s.get('think', 0) for s in mv_stats]
    att = [r for r in recs if r.get('type') == 'attempt' and r.get('side') == side]
    att_elapsed = [r.get('elapsed') for r in att if r.get('elapsed') is not None]
    lw = [r for r in recs if r.get('type') == 'limit_wait' and r.get('side') == side]
    lw_start = [r for r in lw if r.get('phase') == 'start']
    lw_end = [r for r in lw if r.get('phase') == 'end']
    tool_calls = sum(r.get('type') == 'flag' and r.get('side') == side and r.get('source') == 'tool_call'
                     for r in recs)
    t0, t1 = recs[0].get('t'), recs[-1].get('t')
    wall_h = None
    if t0 and t1:
        try:
            wall_h = (parse_t(t1) - parse_t(t0)).total_seconds() / 3600
        except ValueError:
            wall_h = None
    return {
        'name': name, 'game': cfg['game'], 'side': side,
        'cost': u['cost'], 'elapsed_sum': u['elapsed'],
        'think_median': median(think_vals), 'think_max': max(think_vals) if think_vals else None,
        'attempt_elapsed_median': median(att_elapsed),
        'illegal': u['illegal'], 'blocked': u['flags'],
        'limit_wait_n': len(lw_start), 'limit_wait_waited': sum(r.get('waited') or 0 for r in lw_end),
        'limit_wait_unresolved': len(lw_start) - len(lw_end),
        'tool_calls': tool_calls, 'wall_h': wall_h,
    }


def list_game_dirs(bdir):
    if not os.path.isdir(bdir):
        return []
    return sorted(n for n in os.listdir(bdir) if batch.NAME.match(n)
                 and os.path.exists(os.path.join(bdir, n, 'game.jsonl')))


# ---------------------------------------------------------------- 第 1 节：按对手汇总（含执先/执后分拆）+ 未下完盘
def section_overview(game, bdir):
    res = batch.summarize([bdir]) if os.path.isdir(bdir) else {'groups': [], 'games': []}
    games = res['games']
    lines = ['### %s（%s）' % (GAME_ZH[game], os.path.basename(bdir)), '',
             '| 对手 | 下完/共 | 胜-和-负 | 得分率 | 95% 区间 | 执先 | 执后 | 大失误（率，分母） | ACPL |',
             '|---|---|---|---|---|---|---|---|---|']
    for g in res['groups']:
        opp = g['opponent']
        rs = [r for r in games if r['opponent'] == opp]
        sides = {}
        for sd in 'wb':
            rr = [r for r in rs if r['side'] == sd and r['finished']]
            n, pts = len(rr), sum(r['score'] for r in rr)
            sides[sd] = '–' if not n else '%g/%d（%s）' % (pts, n, pct(pts / n))
        lines.append('| %s | %d/%d | %d-%d-%d | %s | %s | %s | %s | %s | %s |' % (
            opp, g['finished'], g['games'], g['win'], g['draw'], g['loss'], pct(g['score_rate']),
            '–' if g['ci95'][0] is None else '%s–%s' % (pct(g['ci95'][0]), pct(g['ci95'][1])),
            sides['w'], sides['b'],
            '–' if not g['analysed'] else '%d（%s，%d）' % (g['blunders'], pct(g['blunder_rate']), g['undecided']),
            f(g['acpl'])))
    unfinished = [r for r in games if not r['finished']]
    lines.append('')
    if unfinished:
        lines.append('没下完 / 被停掉的盘（%d 个）：' % len(unfinished))
        for r in unfinished:
            lines.append('- %s：%s（已下 %d 个半回合）' % (r['run'], r['reason'], r['plies']))
    else:
        lines.append('没有未下完的盘。')
    return '\n'.join(lines) + '\n', res


# ---------------------------------------------------------------- 第 2 节：每盘一行
def section_per_game(game, bdir):
    rows = []
    for name in list_game_dirs(bdir):
        gdir = os.path.join(bdir, name)
        gr = batch.game_row(bdir, name)
        u = game_usage(gdir, name)
        if gr is None or u is None:
            continue
        acpl = gr['loss_sum'] / gr['moves_mine'] if gr.get('analysed') and gr.get('moves_mine') else None
        rows.append(dict(gr, **u, acpl=acpl))
    head = ['盘', '我方执', '结果', '终局原因', '半回合', '花费 $', '思考中位', '思考最大', '每步耗时中位(s)',
            '非法', '被拦', '等额度次数', '等额度时长(s)', '墙钟(h)', '大失误/未分胜负', 'ACPL']
    lines = ['### %s 每盘明细' % GAME_ZH[game], '', '| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
    for r in rows:
        wait = f(r['limit_wait_n'])
        if r['limit_wait_unresolved']:
            wait += '（%d 个未等完）' % r['limit_wait_unresolved']
        lines.append('| %s | %s | %s | %s | %d | %.2f | %s | %s | %s | %d | %d | %s | %s | %s | %s | %s |' % (
            r['run'], r['side'], r['result'], str(r['reason']).replace('|', '/'), r['plies'], r['cost'],
            f(r['think_median'], '%.0f'), f(r['think_max'], '%.0f'), f(r['attempt_elapsed_median'], '%.1f'),
            r['illegal'], r['blocked'], wait, f(r['limit_wait_waited'], '%.0f'), f(r['wall_h'], '%.1f'),
            '%d / %d' % (r['blunders'], r['undecided']) if r.get('analysed') else '–', f(acpl_fmt(r['acpl']))))
    return '\n'.join(lines) + '\n', rows


def acpl_fmt(v):
    return None if v is None else round(v, 1)


# ---------------------------------------------------------------- 第 3 节：合计
def section_total(game, rows):
    n = len(rows)
    cost = sum(r['cost'] for r in rows)
    illegal = sum(r['illegal'] for r in rows)
    blocked = sum(r['blocked'] for r in rows)
    tool_calls = sum(r['tool_calls'] for r in rows)
    think_pooled = median([r['think_median'] for r in rows if r['think_median'] is not None])
    lw_n = sum(r['limit_wait_n'] for r in rows)
    lines = ['### %s 合计' % GAME_ZH[game], '',
             '- 盘数（已开局，含没下完的）：%d' % n,
             '- opus 总花费：$%.2f' % cost,
             '- opus 每步思考 token 中位（各盘中位数再取中位）：%s' % f(think_pooled, '%.0f'),
             '- 非法着法总数：%d；被安全分类器拦下总数：%d；工具调用总数（隔离失效标记，GPT/codex 才有）：%d' % (
                 illegal, blocked, tool_calls),
             '- 等额度总次数：%d' % lw_n]
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------- 第 4 节：同开局配对对照
def pairing(game, new_bdir, old_bdir, opp_prefix, seeds):
    rows = []
    for seed in seeds:
        for side in 'wb':
            name = '%s-s%d-%s' % (opp_prefix, seed, side)
            new_gdir, old_gdir = os.path.join(new_bdir, name), os.path.join(old_bdir, name)
            if not (os.path.exists(os.path.join(new_gdir, 'game.jsonl'))
                   and os.path.exists(os.path.join(old_gdir, 'game.jsonl'))):
                continue
            gn = batch.game_row(new_bdir, name)
            go = batch.game_row(old_bdir, name)
            if not (gn and go and gn['finished'] and go['finished']):
                continue
            rows.append((name, gn, go))
    head = ['盘', '新协议结果', '新协议 ACPL', '新协议大失误', '旧协议结果', '旧协议 ACPL', '旧协议大失误']
    lines = ['### %s：同开局新旧协议对照（%s 对 %s）' % (GAME_ZH[game], os.path.basename(new_bdir), os.path.basename(old_bdir)),
             '', '| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
    for name, gn, go in rows:
        def cell(g):
            acpl = g['loss_sum'] / g['moves_mine'] if g.get('analysed') and g.get('moves_mine') else None
            big = '%d/%d' % (g['blunders'], g['undecided']) if g.get('analysed') else '–'
            return g['result'], f(acpl, '%.1f'), big
        rn, an, bn = cell(gn)
        ro, ao, bo = cell(go)
        lines.append('| %s | %s | %s | %s | %s | %s | %s |' % (name, rn, an, bn, ro, ao, bo))
    if rows:
        an_rows = [gn for _, gn, go in rows if gn.get('analysed')]
        ao_rows = [go for _, gn, go in rows if go.get('analysed')]
        def tot_acpl(rs):
            mv = sum(r['moves_mine'] for r in rs)
            return sum(r['loss_sum'] for r in rs) / mv if mv else None
        def tot_blunder(rs):
            und = sum(r['undecided'] for r in rs)
            b = sum(r['blunders'] for r in rs)
            return b, und, (b / und if und else None)
        bn_, un_, rn_ = tot_blunder(an_rows)
        bo_, uo_, ro_ = tot_blunder(ao_rows)
        pts_n = sum(gn['score'] for _, gn, go in rows)
        pts_o = sum(go['score'] for _, gn, go in rows)
        lines += ['', '合计（%d 对）：新协议得分 %.1f/%d（%s），ACPL %s，大失误 %d/%d（%s）；'
                 '旧协议得分 %.1f/%d（%s），ACPL %s，大失误 %d/%d（%s）。' % (
                     len(rows), pts_n, len(rows), pct(pts_n / len(rows)), f(tot_acpl(an_rows), '%.1f'),
                     bn_, un_, pct(rn_), pts_o, len(rows), pct(pts_o / len(rows)), f(tot_acpl(ao_rows), '%.1f'),
                     bo_, uo_, pct(ro_))]
    else:
        lines.append('')
        lines.append('没有两边都下完的同名盘可比。')
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------- 主流程
def main(argv=None):
    ap = argparse.ArgumentParser(description='opus max 棋力定位的对局汇总（读本机 runs/）')
    ap.add_argument('--out', help='写到这个文件（原子替换）；不给就打到标准输出')
    a = ap.parse_args(argv)
    missing = [os.path.relpath(d, ROOT) for d in (os.path.join(RUNS, 'zc'), os.path.join(RUNS, 'zx'))
               if not list_game_dirs(d)]
    if missing:
        raise SystemExit('未找到本地原始对局记录 game.jsonl（%s）。本脚本统计花费、墙钟与限流等待等原始调用明细，'
                         '依赖未入库的 game.jsonl；公开克隆环境可直接查看入库的 runs/zc/summary.md、runs/zx/summary.md '
                         '与各盘 game.pgn / analysis.jsonl，或运行 `python3 analysis/rating/rate.py report` '
                         '查看基于 analysis/rating/games-*.csv 的等级分结果。' % '、'.join(missing))
    t_start = datetime.datetime.now()
    parts = ['# opus max 棋力评测汇总', '', '生成时间：%s（仅依赖当前盘上数据）' % t_start.isoformat(timespec='seconds'), '']

    parts.append('## 一、二、三：按对手汇总、每盘明细、合计')
    parts.append('')
    for game, bdir in (('chess', os.path.join(RUNS, 'zc')), ('xiangqi', os.path.join(RUNS, 'zx'))):
        ov_md, _ = section_overview(game, bdir)
        pg_md, rows = section_per_game(game, bdir)
        parts += [ov_md, pg_md, section_total(game, rows)]

    parts.append('## 四、同开局新旧协议对照')
    parts.append('')
    parts.append(pairing('chess', os.path.join(RUNS, 'zc'), os.path.join(RUNS, 'b1'), 'maia-1900', range(1, 6)))
    parts.append(pairing('xiangqi', os.path.join(RUNS, 'zx'), os.path.join(RUNS, 'b2'), 'fsf-nodes100', range(1, 5)))
    parts.append('刻度拟合与人类刻度：`python3 analysis/rating/rate.py report`。')

    text = '\n'.join(parts)
    if not a.out:
        print(text)
        return
    tmp = a.out + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fp:
        fp.write(text)
    os.replace(tmp, a.out)


if __name__ == '__main__':
    main()
