#!/usr/bin/env python3
"""opus max 棋力定位（docs/results/opus-max-rating.md）的估分与刻度换算：离线复算，不调模型、不起引擎。

本目录的数据（入库，体量小）：
  games-engines.csv  引擎互下标定的战绩。每行是同一批次里同一对阵连续的一段对局，scores 按原顺序逐盘写
                     （player 视角：1 胜、= 和、0 负）。顺序要保留：自助法按对阵分层重抽，抽到哪盘取决于顺序
  games-opus.csv     opus 对引擎，一盘一行：终局原因、半回合数，满上限的盘另记事后裁判对最后局面的评分（opus 视角）
  human-scale.json   lichess 上官方 Maia 机器人的分、lichess 分布、ChessGoals 换算表（第三方数据，出处和抓取日期在文件里）

用法（在仓库根目录）：
  python3 analysis/rating/rate.py report       # 复算结论文档里的全部刻度数字（自助法 1,000 次，约两三分钟）
  python3 analysis/rating/rate.py fit --game chess [--opus-only maia|stockfish] [--cap draw|eval|loss] [--boot N]
  python3 analysis/rating/rate.py export       # 从本机 runs/ 重新导出两个 csv（原始 game.jsonl 与标定目录不入库，只有原机器上有）

口径（同结论文档「刻度怎么搭」）：
  - Elo 逻辑模型最大似然，引擎标定对局和 opus 对局放在一起拟合；国际象棋以 Maia-1900 为 0，中国象棋以 nodes=100 为 0。
  - 自助法：按对阵分层有放回重抽（种子 12345），标定对局一起重抽重拟合；另报似然比区间（标定固定在最大似然处）。
  - 人类刻度只做国际象棋：三个 Maia 锚（本机刻度 → lichess 机器人分）各拟一条最小二乘直线，超快棋、快棋各一条；
    百分位按 lichess 分布 25 分一档、档内线性插值；FIDE 按 ChessGoals 表线性插值，表外不外推。
  - --cap：满 200 个半回合那几盘怎么算。draw 按当时的规则判和（主表）；eval 按 2026-10-04 定的新规则回看
    （事后裁判评分一方领先 ≥300 厘兵判该方胜，否则和；等于结论文档的「改判版」）；loss 全判 opus 负（最保守）。
"""
import argparse, csv, json, math, os, random, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ENGINES_CSV = os.path.join(HERE, 'games-engines.csv')
OPUS_CSV = os.path.join(HERE, 'games-opus.csv')
HUMAN = os.path.join(HERE, 'human-scale.json')

OPUS = 'claude:opus'
ANCHOR = {'chess': 'engine:maia-1900', 'xiangqi': 'engine:fsf:nodes=100'}
# 拟合时批次的先后（决定对局顺序，自助法要靠它逐数复现）；export 也按这个顺序导
BATCHES = {'chess': ['zcal-c-m1900', 'zcal-c-m1500', 'zcal-c-m1100', 'zcal-c-sf1900', 'zc'],
           'xiangqi': ['zcal-x-n1000', 'zcal-x-n100', 'b2cal-n1000v300', 'b2cal-n300v100', 'b2cal-n100v30',
                       'b2cal-n30v10', 'zx']}
OPUS_BATCH = {'chess': 'zc', 'xiangqi': 'zx'}
CAP_MARGIN = 300          # 新规则：满上限时领先 ≥300 厘兵判胜（design.md 第三节 max_plies）
SEED = 12345
K = math.log(10) / 400
SCORE = {'1': 1.0, '=': 0.5, '0': 0.0}


# ---------------------------------------------------------------- 读数据
def human_scale():
    with open(HUMAN, encoding='utf-8') as f:
        return json.load(f)


def cap_lead(text):
    """'cp -445' / 'mate -1'（opus 视角）→ opus 领先的厘兵数，杀棋按 ±无穷。"""
    kind, n = text.split()
    n = int(n)
    return n if kind == 'cp' else (math.inf if n > 0 else -math.inf)


def opus_score(row, cap):
    s = float(row['score'])
    if row['capped'] != '1' or cap == 'draw':
        return s
    if cap == 'loss':
        return 0.0
    lead = cap_lead(row['cap_eval'])
    return 1.0 if lead >= CAP_MARGIN else 0.0 if lead <= -CAP_MARGIN else 0.5


def load(game, cap='draw', opus_only=None):
    """按 BATCHES 的先后拼出对局列表 [(player, opponent, score)]，和评测时直接读 runs/ 的顺序一致。"""
    with open(ENGINES_CSV, encoding='utf-8') as f:
        segs = [r for r in csv.DictReader(f) if r['game'] == game]
    with open(OPUS_CSV, encoding='utf-8') as f:
        opus = [r for r in csv.DictReader(f) if r['game'] == game]
    games = []
    for b in BATCHES[game]:
        for r in segs:
            if r['batch'] == b:
                games += [(r['player'], r['opponent'], SCORE[c]) for c in r['scores']]
        for r in opus:
            if r['batch'] == b and (not opus_only or re.search(opus_only, r['opponent'])):
                games.append((OPUS, r['opponent'], opus_score(r, cap)))
    return games


# ---------------------------------------------------------------- 拟合
def exp_(ra, rb):
    return 1 / (1 + 10 ** ((rb - ra) / 400))


def fit(games, anchor, init=None, iters=300):
    names = sorted({p for g in games for p in g[:2]})
    r = dict(init or {})
    for n in names:
        r.setdefault(n, 0.0)
    r[anchor] = 0.0
    for _ in range(iters):
        delta = 0
        for n in names:
            if n == anchor:
                continue
            gsum, h = 0.0, 0.0
            for a, b, s in games:
                if a == n:
                    e = exp_(r[a], r[b]); gsum += (s - e); h += e * (1 - e)
                elif b == n:
                    e = exp_(r[b], r[a]); gsum += ((1 - s) - e); h += e * (1 - e)
            # 弱先验：均值 0、标准差 1000 分，只为全胜 / 全负时不发散
            gsum = gsum * K - r[n] / 1000 ** 2
            h = h * K * K + 1 / 1000 ** 2
            step = max(-200, min(200, gsum / h))
            r[n] += step
            delta = max(delta, abs(step))
        if delta < 1e-3:
            break
    return r


def loglik(games, r):
    ll = 0
    for a, b, s in games:
        e = min(max(exp_(r[a], r[b]), 1e-12), 1 - 1e-12)
        ll += s * math.log(e) + (1 - s) * math.log(1 - e)
    return ll


def lichess_map(r, bots):
    """三个 Maia 锚：刻度 → lichess 分，[(截距, 斜率) 超快棋, 快棋]。缺锚（不到两个）返回 None。"""
    pts = [(r[k], (v['blitz'], v['rapid'])) for k, v in bots.items() if k in r]
    if len(pts) < 2:
        return None
    out = []
    for i in range(2):
        xs = [p[0] for p in pts]; ys = [p[1][i] for p in pts]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
        out.append((my - b * mx, b))
    return out


def q(xs, p):
    xs = sorted(x for x in xs if x == x)
    return xs[int(p * (len(xs) - 1))]


def rate(games, anchor, boot=1000, bots=None):
    """返回 {mle, lr, boot: {名字: [2.5%, 50%, 97.5%]}, lichess: {map, blitz: [点, 下, 上], rapid: …}}。"""
    pairs = {}
    for g in games:
        pairs.setdefault(tuple(sorted(g[:2])), []).append(g)
    r = fit(games, anchor)
    res = {'mle': r, 'pairs': {k: len(v) for k, v in pairs.items()}}
    if OPUS in r:                               # 似然比区间：其他人固定在最大似然处，5 分一步往外走
        base = loglik(games, r)
        lo = hi = r[OPUS]
        rr = dict(r)
        while True:
            rr[OPUS] = lo - 5
            if base - loglik(games, rr) > 1.92 or lo < -3000: break
            lo -= 5
        while True:
            rr[OPUS] = hi + 5
            if base - loglik(games, rr) > 1.92 or hi > 3000: break
            hi += 5
        res['lr'] = [lo, hi]
    mp = lichess_map(r, bots) if bots else None
    rng = random.Random(SEED)
    boots = {n: [] for n in r}
    blic = [[], []]
    for _ in range(boot):
        bg = []
        for k, v in pairs.items():
            bg += [rng.choice(v) for _ in v]
        br = fit(bg, anchor, init=r, iters=100)
        for n in r:
            boots[n].append(br.get(n, float('nan')))
        if mp and OPUS in br:
            m = lichess_map(br, bots)
            for j in range(2):
                blic[j].append(m[j][0] + m[j][1] * br[OPUS])
    res['boot'] = {n: [q(boots[n], 0.025), q(boots[n], 0.5), q(boots[n], 0.975)] for n in r}
    if mp and OPUS in r:
        pt = [mp[j][0] + mp[j][1] * r[OPUS] for j in range(2)]
        res['lichess'] = {'map': mp, 'blitz': [pt[0], q(blic[0], 0.025), q(blic[0], 0.975)],
                          'rapid': [pt[1], q(blic[1], 0.025), q(blic[1], 0.975)]}
    return res


# ---------------------------------------------------------------- 人类刻度：百分位、FIDE
def share_above(dist, x):
    """lichess 分布里分数高于 x 的人占多少（width 分一档，档内按均匀分布线性插值）。"""
    bs, cnt = dist['bin_start'], dist['count']
    width, total = bs[1] - bs[0], sum(cnt)
    if x <= bs[0]:
        return 1.0
    if x >= bs[-1] + width:
        return 0.0
    above = 0.0
    for b0, c in zip(bs, cnt):
        b1 = b0 + width
        if b1 <= x:
            continue
        above += c if b0 >= x else c * (b1 - x) / width
    return above / total


def to_fide(cg, col, x):
    """ChessGoals 表里 col 列（LichessBlitz / LichessRapid）→ FIDE，线性插值；表外返回 None。"""
    i, fi = cg['columns'].index(col), cg['columns'].index('FIDE')
    pts = sorted((float(r[i]), float(r[fi])) for r in cg['rows'] if r[fi] != '--')
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    if x < xs[0] or x > xs[-1]:
        return None
    for j in range(len(xs) - 1):
        if xs[j] <= x <= xs[j + 1]:
            return ys[j] if xs[j + 1] == xs[j] else ys[j] + (x - xs[j]) / (xs[j + 1] - xs[j]) * (ys[j + 1] - ys[j])
    return ys[-1]


# ---------------------------------------------------------------- 输出
def fmt_human(res, hs, point_only=False):
    """lichess 分（区间）、排前百分比、粗折 FIDE。point_only：区间用点估计的直线换算（结论文档里标「约」的那几行）。"""
    lines = []
    for key, col, name in (('blitz', 'LichessBlitz', '超快棋'), ('rapid', 'LichessRapid', '快棋')):
        if point_only:
            a, b = res['map_point'][0 if key == 'blitz' else 1]
            lo, hi = res['boot'][OPUS][0], res['boot'][OPUS][2]
            v = [a + b * res['mle'][OPUS], a + b * lo, a + b * hi]
            lines.append('    %s 约 %.0f（约 %.0f–%.0f）' % (name, *v))
            continue
        v = res['lichess'][key]
        dist = hs['lichess_distribution'][key]
        top = ['%.0f%%' % (100 * share_above(dist, x)) for x in v]
        fide = ['表外' if f is None else '%.0f' % f for f in (to_fide(hs['chessgoals'], col, x) for x in v)]
        lines.append('    %s %.0f（%.0f–%.0f）；排前 %s（下界 %s，上界 %s）；粗折 FIDE %s（%s–%s）' % (
            name, *v, *top, *fide))
    return lines


def fmt_rate(res, label):
    lines = ['  %s：opus %+.0f，自助法 95%% %.0f – %.0f，似然比 95%% %.0f – %.0f' % (
        label, res['mle'][OPUS], res['boot'][OPUS][0], res['boot'][OPUS][2], *res['lr'])]
    return lines


def fmt_ladder(res):
    lines = ['  标定（最大似然，括号里自助法 95%）：']
    for n, v in sorted(res['mle'].items(), key=lambda x: x[1]):
        if n == OPUS:
            continue
        b = res['boot'][n]
        lines.append('    %-28s %+5.0f（%.0f – %.0f）' % (n, v, b[0], b[2]))
    return lines


def tally(game, cap):
    """opus 每档胜-和-负（按 --cap 规则）。"""
    with open(OPUS_CSV, encoding='utf-8') as f:
        rows = [r for r in csv.DictReader(f) if r['game'] == game]
    out = {}
    for r in rows:
        s = opus_score(r, cap)
        w = out.setdefault(r['opponent'], [0, 0, 0])
        w[0 if s == 1 else 1 if s == 0.5 else 2] += 1
    return ['    %s：%d-%d-%d，得分 %.0f%%' % (k, *v, 100 * (v[0] + v[1] / 2) / sum(v)) for k, v in out.items()]


CAP_NAME = {'draw': '按规则计和（主表）', 'eval': '按新规则回看（领先 ≥300 厘兵判胜，= 改判版）',
            'loss': '最保守：满上限全判 opus 负'}


def report(boot):
    hs = human_scale()
    bots = {k: v for k, v in hs['lichess_bots']['bots'].items()}
    print('# 国际象棋（Maia-1900 = 0）')
    for i, cap in enumerate(('draw', 'eval', 'loss')):
        res = rate(load('chess', cap), ANCHOR['chess'], boot, bots)
        if i == 0:
            print('\n'.join(fmt_ladder(res)))
            a, b = res['lichess']['map'][0], res['lichess']['map'][1]
            print('  换算直线：超快棋 = %.0f + %.2f × 刻度，快棋 = %.0f + %.2f × 刻度' % (*a, *b))
        print('\n'.join(fmt_rate(res, CAP_NAME[cap])))
        print('\n'.join(tally('chess', cap)))
        print('\n'.join(fmt_human(res, hs)))
        if i == 0:
            point_map = res['lichess']['map']
    for pat, label in (('maia', '只用 opus 对 Maia 的盘'), ('stockfish', '只用 opus 对 Stockfish 的盘')):
        res = rate(load('chess', 'draw', pat), ANCHOR['chess'], boot)
        res['map_point'] = point_map
        print('\n'.join(fmt_rate(res, label)))
        print('\n'.join(fmt_human(res, hs, point_only=True)))
    print('\n# 中国象棋（nodes=100 = 0）')
    res = rate(load('xiangqi'), ANCHOR['xiangqi'], boot)
    print('\n'.join(fmt_ladder(res)))
    print('\n'.join(fmt_rate(res, '全部 37 盘')))


def cmd_fit(a):
    hs = human_scale()
    bots = hs['lichess_bots']['bots'] if a.game == 'chess' and not a.opus_only else None
    res = rate(load(a.game, a.cap, a.opus_only), ANCHOR[a.game], a.boot, bots)
    print('\n'.join(fmt_ladder(res)))
    print('\n'.join(fmt_rate(res, '%s，%s%s' % (a.game, CAP_NAME[a.cap], '，只用对手匹配 %s 的盘' % a.opus_only
                                                 if a.opus_only else ''))))
    if 'lichess' in res:
        print('\n'.join(fmt_human(res, hs)))


# ---------------------------------------------------------------- 从 runs/ 导出
def export():
    sys.path.insert(0, ROOT)
    from agi_chess import batch, records
    missing = []
    for game, dirs in BATCHES.items():
        for b in dirs:
            d = os.path.join(ROOT, 'runs', b)
            if not os.path.isdir(d) or not any(
                    batch.NAME.match(name) and os.path.isfile(os.path.join(d, name, 'game.jsonl'))
                    for name in os.listdir(d)):
                missing.append('runs/' + b)
    if missing:
        raise SystemExit('未找到导出所需的本地标定目录或原始 game.jsonl（%s）；export 依赖未入库的引擎标定目录与原始对局记录，'
                         '公开克隆可直接查看已入库的 analysis/rating/games-*.csv，或运行 `python3 analysis/rating/rate.py report` / `fit` 复算等级分。'
                         % '、'.join(missing))
    eng_rows, opus_rows = [], []
    for game, dirs in BATCHES.items():
        for b in dirs:
            d = os.path.join(ROOT, 'runs', b)
            games = [g for g in batch.summarize([d])['games'] if g['finished']]
            if not games:
                raise SystemExit('未在 runs/%s 下找到已完成的本地对局记录（game.jsonl 缺少 end），拒绝覆盖已入库 CSV' % b)
            if b == OPUS_BATCH[game]:
                for g in games:
                    capped = str(g['reason']).startswith('满 ')
                    opus_rows.append({'game': game, 'batch': b, 'run': g['run'], 'side': g['side'],
                                      'opponent': g['opponent'], 'score': g['score'], 'plies': g['plies'],
                                      'reason': g['reason'], 'capped': int(capped),
                                      'cap_eval': cap_eval(os.path.join(d, g['run']), g['side'], records)
                                      if capped else ''})
                continue
            for g in games:
                ch = {1.0: '1', 0.5: '=', 0.0: '0'}[g['score']]
                last = eng_rows[-1] if eng_rows else None
                if last and (last['batch'], last['player'], last['opponent']) == (b, g['player'], g['opponent']):
                    last['scores'] += ch
                else:
                    eng_rows.append({'game': game, 'batch': b, 'player': g['player'], 'opponent': g['opponent'],
                                     'scores': ch})
    for r in eng_rows:
        r['n'], r['w'], r['d'], r['l'] = (len(r['scores']), r['scores'].count('1'), r['scores'].count('='),
                                          r['scores'].count('0'))
    write_csv(ENGINES_CSV, ['game', 'batch', 'player', 'opponent', 'n', 'w', 'd', 'l', 'scores'], eng_rows)
    write_csv(OPUS_CSV, ['game', 'batch', 'run', 'side', 'opponent', 'score', 'plies', 'reason', 'capped',
                         'cap_eval'], opus_rows)
    print('写完 %s（%d 段）、%s（%d 盘）' % (ENGINES_CSV, len(eng_rows), OPUS_CSV, len(opus_rows)))


def cap_eval(run_dir, side, records):
    """满上限那盘最后局面的事后裁判评分，换成 opus（side）视角，写成 'cp N' / 'mate N'。"""
    rows = records.read(os.path.join(run_dir, 'analysis.jsonl'))
    last = rows[-1]
    kind, n = last['after'].split()            # 最后一步走子方视角的走后评分
    n = int(n) if last['side'] == side else -int(n)
    return '%s %d' % (kind, n)


def write_csv(path, cols, rows):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, cols, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('report', help='复算结论文档里的全部刻度数字')
    r.add_argument('--boot', type=int, default=1000)
    f = sub.add_parser('fit', help='拟合一种棋，可选只用部分 opus 盘、换满上限的算法')
    f.add_argument('--game', choices=sorted(BATCHES), required=True)
    f.add_argument('--opus-only', dest='opus_only', help='只用对手名匹配这个正则的 opus 盘（如 maia、stockfish）')
    f.add_argument('--cap', choices=('draw', 'eval', 'loss'), default='draw')
    f.add_argument('--boot', type=int, default=1000)
    sub.add_parser('export', help='从本机 runs/ 重新导出 games-engines.csv、games-opus.csv')
    a = ap.parse_args(argv)
    if a.cmd == 'report':
        report(a.boot)
    elif a.cmd == 'fit':
        cmd_fit(a)
    else:
        export()


if __name__ == '__main__':
    main()
