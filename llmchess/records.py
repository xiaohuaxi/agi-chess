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


def cost_delta(total, prev):
    """session 档本次调用的花费。claude -p --resume 返回的 total_cost_usd 是整段会话到此为止的累计值，
    不是这一次的，逐步相加会算重，所以减去同一会话上一次调用的累计值；会话第一次、或累计值变小（被重置）时用原值。"""
    return total if prev is None or total < prev else total - prev


def attempt_costs(recs):
    """按记录顺序给每条 attempt 算本次花费，返回 ({id(记录): 花费}, {会话 id: 最后一次累计值})。
    session 档按会话 id 做差（见 cost_delta）：新记录的累计值在 usage.cost_total，旧记录没有这个字段、usage.cost 就是累计值；
    没有会话 id 的（stateless / notes / 引擎）原样取 usage.cost。"""
    out, last = {}, {}
    for r in recs:
        if r.get('type') != 'attempt':
            continue
        u = r.get('usage') or {}
        sid = r.get('session')
        if not sid:
            out[id(r)] = u.get('cost') or 0
            continue
        total = u.get('cost_total', u.get('cost')) or 0
        out[id(r)] = cost_delta(total, last.get(sid))
        last[sid] = total
    return out, last


def summary(stats, players):
    """每方合计与中位数。stats 是每个半回合一条（带 side）；随机开局那几步（opening）不算哪方的。"""
    out = {}
    for side in 'wb':
        ss = [s for s in stats if s['side'] == side and not s.get('opening')]
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


# ---------------------------------------------------------------- 棋谱里每步的元信息（design.md 第四节「每步元信息」）
META_KEYS = ('think', 'out', 'in', 'cache_read', 'cache_write')


def _known(r):
    """这条 attempt 的各项 token 后端有没有给（给了才算数，0 也算给了）。返回 {键: True/False}。
    判断看原始返回（attempt.claude），不看换算后的 usage：换算时缺的一律记成 0，分不出「没有」和「是 0」。
    llm-chat：META 里对应字段为 None 就是没给（DeepSeek 不给缓存写；三路的思考 token 都可能为 None）。
    claude -p 直调：usage 里有 output_tokens_details.thinking_tokens 才算给了思考。
    codex exec 直调：turn.completed 的 usage 里有 reasoning_output_tokens 才算给了思考。
    被拦 / 出错没有用量的，全都算没给。"""
    d = r.get('claude') or {}
    m = d.get('meta')
    if isinstance(m, dict):
        return {'think': m.get('reasoning_tokens') is not None, 'out': m.get('output_tokens') is not None,
                'in': m.get('input_tokens') is not None, 'cache_read': m.get('cache_read') is not None,
                'cache_write': m.get('cache_write') is not None}
    u = d.get('usage')
    if not isinstance(u, dict):
        return {k: False for k in META_KEYS}
    if 'cache_creation_input_tokens' in u or 'output_tokens_details' in u:          # claude -p
        return {'think': 'thinking_tokens' in (u.get('output_tokens_details') or {}), 'out': 'output_tokens' in u,
                'in': 'input_tokens' in u, 'cache_read': 'cache_read_input_tokens' in u,
                'cache_write': 'cache_creation_input_tokens' in u}
    return {'think': 'reasoning_output_tokens' in u, 'out': 'output_tokens' in u, 'in': 'input_tokens' in u,   # codex exec
            'cache_read': 'cached_input_tokens' in u, 'cache_write': 'cache_write_input_tokens' in u}


def move_meta(recs):
    """每个落定半回合（模型棋手下的）的元信息：{半回合号: {...}}。随机开局、引擎、随机走子的半回合不给。
    一步里可能调了几次（非法重选、被拦、空回复），各项是本步所有 attempt 的合计：
      emt：各次调用的用时之和（秒，只算成功回来的那次子进程，不含调不通的重试和等额度）；
      think / out / in / cache_read / cache_write：token 合计，本步任一次调用后端没给这一项就记 None（不部分相加、不补 0）；
      calls：调用次数；illegal / flagged / empty：非法、被拦、空回复次数（取 move.stat，和统计口径一致）。"""
    moves = {r['ply']: r for r in recs if r.get('type') == 'move' and not r.get('opening')}
    out = {}
    for r in recs:
        if r.get('type') != 'attempt' or r.get('ply') not in moves or 'usage' not in r:
            continue
        mv = moves[r['ply']]
        if r.get('side') != mv['side']:
            continue
        m = out.setdefault(r['ply'], dict({k: 0 for k in META_KEYS}, emt=0.0, calls=0))
        m['calls'] += 1
        m['emt'] += r.get('elapsed') or 0
        u, known = r.get('usage') or {}, _known(r)
        for k in META_KEYS:
            if m[k] is not None:
                m[k] = m[k] + (u.get(k) or 0) if known[k] else None
    for ply, m in out.items():
        s = moves[ply].get('stat') or {}
        m.update(illegal=s.get('illegal', 0), flagged=s.get('flags', 0), empty=s.get('empty', 0))
    return out


def emt(seconds):
    """PGN 规范补充（PGN Specification Supplement）的 %emt 写法：h:mm:ss，整秒（规范只给到秒）。"""
    s = int(round(seconds))
    return '%d:%02d:%02d' % (s // 3600, s % 3600 // 60, s % 60)


def meta_comment(m):
    """一步的元信息写成 PGN 评注里的内嵌命令（[%名 参数]，名只用字母数字，规范补充的要求）。
    %emt 是规范补充里的标准命令；其余是自定义的，标准阅读器按规范补充会原样保留、不做处理。没给的项整条省掉。"""
    if not m:
        return ''
    parts = ['[%%emt %s]' % emt(m['emt'])]
    for k, name in (('think', 'think'), ('out', 'out'), ('in', 'in'), ('cache_read', 'cacheread'),
                    ('cache_write', 'cachewrite')):
        if m.get(k) is not None:
            parts.append('[%%%s %d]' % (name, m[k]))
    for k in ('illegal', 'flagged', 'empty'):
        if m.get(k):
            parts.append('[%%%s %d]' % (k, m[k]))
    return ' '.join(parts)
