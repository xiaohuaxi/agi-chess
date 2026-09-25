"""对局记录：runs/<tag>/game.jsonl，一行一条 JSON（design.md 第四节）。

type：config / attempt（每次调用或引擎出棋）/ move（落定的一步）/ flag（安全分类器拦截）/ pause / resume /
forfeit（重试用完判负）/ end（结果与每方统计）。每条带 t（本地时间）。
"""
import datetime, json, statistics

SUM_KEYS = ('in', 'cache_read', 'cache_write', 'out', 'think', 'text_out')


def now():
    return datetime.datetime.now().isoformat(timespec='seconds')


def write(path, rec):
    """追加一行。只有对局进程一个写者，追加写即可（一行一次 write，断电最多丢最后半行，load 会跳过）。"""
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(dict(rec, t=now()), ensure_ascii=False) + '\n')


def read(path):
    out = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except ValueError:               # 写到一半断掉的最后一行
                continue
    return out


def new_stat():
    s = {'attempts': 0, 'illegal': 0, 'noparse': 0, 'flags': 0, 'empty': 0, 'elapsed': 0.0, 'cost': 0.0}
    s.update({k: 0 for k in SUM_KEYS})
    return s


def add_usage(stat, u, dt):
    stat['attempts'] += 1
    stat['elapsed'] += dt
    stat['cost'] += u.get('cost') or 0
    for k in SUM_KEYS:
        stat[k] += u.get(k) or 0


def summary(stats, players):
    """每方合计与中位数。stats 是每个半回合一条（带 side）。"""
    out = {}
    for side in 'wb':
        ss = [s for s in stats if s['side'] == side]
        row = {'player': players[side], 'plies': len(ss), 'calls': sum(s['attempts'] for s in ss),
               'illegal': sum(s['illegal'] for s in ss), 'noparse': sum(s['noparse'] for s in ss),
               'flags': sum(s.get('flags', 0) for s in ss), 'empty': sum(s.get('empty', 0) for s in ss),
               'cost': round(sum(s['cost'] for s in ss), 4)}
        for k in ('elapsed',) + SUM_KEYS:
            vals = [s[k] for s in ss]
            row['sum_' + k] = round(sum(vals), 1)
            row['median_' + k] = round(statistics.median(vals), 1) if vals else 0
        rs = [r for s in ss for r in s.get('recite', [])]
        if rs:
            row['recite'] = {'n': len(rs), 'cell_acc': round(sum(r['cells_ok'] for r in rs) / sum(r['cells'] for r in rs), 4),
                             'all_ok': sum(r['all_ok'] for r in rs), 'rows_missing': sum(10 - r['rows_found'] for r in rs)}
        out[side] = row
    return out


def summary_lines(summ, sides):
    lines = []
    for side in 'wb':
        s = summ[side]
        lines.append('%s（%s）：%d 步，调用 %d 次，非法 %d 次（其中没写出着法 %d 次），被拦截 %d 次，空回复 %d 次；'
                     '每步中位：用时 %.1f 秒、输入 %d+%d 缓存读+%d 缓存写、输出 %d（其中思考 %d）；共 $%.3f' % (
                         sides[side], s['player'], s['plies'], s['calls'], s['illegal'], s['noparse'], s['flags'], s['empty'],
                         s['median_elapsed'], s['median_in'], s['median_cache_read'], s['median_cache_write'],
                         s['median_out'], s['median_think'], s['cost']))
        if 'recite' in s:
            r = s['recite']
            lines.append('　复述局面 %d 次：逐格正确率 %.2f%%，整盘全对 %d 次，缺行 %d 行' % (
                r['n'], 100 * r['cell_acc'], r['all_ok'], r['rows_missing']))
    return lines
