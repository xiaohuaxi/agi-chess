"""第二批块 A（docs/plan-batch2.md「块 A · 局面」）的选取脚本：写 data/batch2/xiangqi.jsonl（约 30 个）和 chess.jsonl（约 20 个）。

    python3 data/batch2/select_positions.py xiangqi [--jobs 4]   # 要跑引擎验看杀题，几分钟
    python3 data/batch2/select_positions.py chess                  # 不跑引擎
    python3 data/batch2/select_positions.py check                  # 只读检查两份局面文件（FEN 合法、走子方、着法合法）

输入都只读：data/batch1/*.jsonl、runs/quiz-batch1/<棋种>/judged.jsonl（第一批局面题判分）、
runs/b1-{xq,ch}-*/game.jsonl + analysis.jsonl（第一批 B 块整盘，Fairy-Stockfish depth 16 / Stockfish depth 18 逐步分析），
上一轮的 ~/repos/ai-research/topics/llm-xiangqi-play/ 和 ~/repos/jev-study/artifacts/xiangqi_llm/（只在补位时用，路径和
「同一件事」的段落沿用 data/batch1/select_positions.py）。runs/ 不入库，所以入库的 jsonl 才是这批题的真身，重跑本脚本
只用来说明怎么选的。

中国象棋（目标约 30 个），按下面顺序取，编号 x2-01 起：
  1. 第一批局面题（data/batch1/xiangqi.jsonl）里任一档（medium/high/xhigh/max）任一遍被判大失误（亏损 >= 250）的，全要。
     原字段原样保留，另加 batch1_id（第二批 base 档可以和块 0 的 zh 复测按这个配对）。
  2. 第一批 B 块 6 盘里模型方的大失误（analysis.jsonl 里 cls == 'blunder'：未分胜负、亏损 >= 250）的走前局面。
     去重：走前局面相同（棋盘 + 走子方）的只留一个（按盘名排序取第一个）；另外 SAME_EVENT 里手工并掉的
     （session-1 第 15 步和 notes-2 / stateless-2 第 9 步是同一个「车九平八」被隔炮打车，局面差一两步，plan 要求只留一个）。
  3. 看杀题：B 块被将死的 5 盘里，模型方 (a) 被将死前的最后 3 步，或 (b) 走前还没被引擎算出杀、走完就被算出杀
     （after 是 mate -N）的那一步。候选局面用 Fairy-Stockfish 重验，和 quiz judge 同一个引擎、同一深度、同样带完整历史：
     对每个合法着法（去掉长将 / 长捉禁着）看走完后引擎是否给对方杀棋分。至少一个着法不被杀（「仍有不输着法」）、
     且至少一个着法被杀（真有杀可看）才要。每个局面记下 safe_moves（不被杀的着法）和 n_losing。
     同一盘里半回合相差 <= 6 的连成一件事；一件事最多取 2 个（先取 (b) 那种走进杀的、按先后，再取其余的、离将死由近到远）。
  4. 不够 30 个：从上一轮「同一件事连着好几步」那三段（C 15–30、D 8–16、B 69–73，第一批只取了每段前 2 个）
     里第一批没取的补，走前 |eval_before| < 1000，三段轮流、段内按半回合先后。这些和已选局面是同一件事、强相关，
     记 fill=True，related_to 指向同段已选的局面。

国际象棋（目标约 20 个），编号 c2-01 起：
  1. 第一批谜题（data/batch1/chess.jsonl）里 xhigh 或 max 档任一遍被判大失误（lichess 口径）的，全要，原字段保留、加 batch1_id。
  2. 第一批 B 块 9 盘里模型方 cls == 'blunder' 的走前局面，走前局面相同的只留一个（路线 A 的 3 盘同一步 Nxe5）。
     整盘局面没有谜题那样的「对手那一步」，这里取对局里对手的上一步：fen_before_opp = 上一步之前的局面，
     opp_move = 上一步，这样 quiz 的 build_state 不用改。solution = 分析里的引擎最佳着（Stockfish depth 18），
     judge 的「解中」对这类题就是「走了引擎首选或直接将死」。

每个局面都带：
  - kind：b1-quiz / b1-game-blunder / b1-game-mate / r1-fill；source：人读的来源（第一批题号 / 哪盘第几半回合）。
  - category：谁能吃到谁 / 看杀 / 多步战术或其他；category_basis 写依据。能继承就继承：第一批中国象棋题按上一轮的类别
    （规则落盘错 / 看对但漏看 / 看对但判断错 = 谁能吃到谁）或第一批答错那几遍的静态判定；第一批国际象棋按 pick_theme
    （mate* = 看杀，其余 = 谁能吃到谁）；B 块的大失误按 quiz 的静态判定（白送子 / 漏吃 = 谁能吃到谁，送杀 / 漏杀 = 看杀）；
    看杀题 = 看杀。
  - group：同一件事去重后的分组号（1 起，两种棋各自编），group_note 说明是哪件事；related_to：同组的其它局面 id。
    算统计时同组的局面不独立。
引擎只在选题时用，从不进模型提示。
"""
import argparse, ast, collections, concurrent.futures, csv, importlib.util, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from llmchess import xiangqi as X          # noqa: E402
from llmchess import quiz as Q             # noqa: E402
from llmchess import analyze as A          # noqa: E402
from llmchess import records               # noqa: E402

B1 = os.path.join(ROOT, 'data', 'batch1')
RUNS = os.path.join(ROOT, 'runs')
N_XQ = 30
GOOD_CLASSES = ('规则落盘错', '看对但漏看', '看对但判断错')
CAP = '谁能吃到谁'
MATE = '看杀'
OTHER = '多步战术或其他'
# 局面不同、但 plan 认定是同一个昏招的：{(盘, 半回合): (代表盘, 半回合)}
SAME_EVENT = {('b1-xq-session-1', 15): ('b1-xq-notes-2', 9)}
MATE_WINDOW = 3            # 被将死前最后几步
MATE_CHAIN = 6             # 同一盘半回合相差 <= 这么多算同一件事
PER_GROUP = 2


def load_b1_select():
    spec = importlib.util.spec_from_file_location('b1_select', os.path.join(B1, 'select_positions.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def jl(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


def write_jsonl(path, rows):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    os.replace(tmp, path)


def b1_errors(game, pred):
    """第一批局面题：{题号: ['<档>-r<遍>', ...]}，只收满足 pred 的作答。"""
    out = collections.defaultdict(list)
    for r in jl(os.path.join(RUNS, 'quiz-batch1', game, 'judged.jsonl')):
        if r.get('move') is not None and pred(r):
            out[r['pos']].append(r)
    return out


def game_runs(prefix):
    return sorted(d for d in os.listdir(RUNS) if d.startswith(prefix) and os.path.isdir(os.path.join(RUNS, d)))


def load_game(run):
    cfg, recs = A.load_run(os.path.join(RUNS, run))
    mv = [r['move'] for r in A.moves_of(recs)]
    ana = jl(os.path.join(RUNS, run, 'analysis.jsonl'))
    assert [r['move'] for r in ana] == mv, ('analysis.jsonl 和对局记录的着法对不上', run)
    end = next((r for r in recs if r['type'] == 'end'), None)
    return cfg, mv, ana, end


def cond_of(cfg, side):
    sc = cfg['sides'][side]
    return {k: sc.get(k) for k in ('memory', 'view', 'history', 'selfcheck', 'effort')}


def static_category(game, fen, mv):
    lab = Q.labels(Q.static_table(Q.rules_for(game), fen), mv)
    tags = [k for k in ('hang', 'missed_capture', 'allows_mate', 'missed_mate') if lab[k]]
    if lab['hang'] or lab['missed_capture']:
        cat = CAP
    elif lab['allows_mate'] or lab['missed_mate']:
        cat = MATE
    else:
        cat = OTHER
    return cat, '所走着法的静态判定（quiz.labels）：%s' % ('、'.join(tags) or '无标')


def assign_groups(rows):
    """按 _gkey 编组号（出现先后），填 related_to。"""
    num, members = {}, collections.defaultdict(list)
    for r in rows:
        k = r.pop('_gkey')
        num.setdefault(k, len(num) + 1)
        r['group'] = num[k]
        members[r['group']].append(r['id'])
    for r in rows:
        r['related_to'] = [i for i in members[r['group']] if i != r['id']]


# ---------------------------------------------------------------- 中国象棋
def xq_state(moves):
    st = X.start()
    for m in moves:
        X.push(st, m)
    return st


def xq_b1_quiz():
    b1 = load_b1_select()
    blund = b1_errors('xiangqi', lambda r: r['blunder'])
    rows = []
    for p in jl(os.path.join(B1, 'xiangqi.jsonl')):
        if p['id'] not in blund:
            continue
        bad = blund[p['id']]
        r = dict(p)
        r.update(kind='b1-quiz', batch1_id=p['id'], source='batch1 quiz %s（%s）' % (p['id'], p['source']),
                 b1_blunders=sorted('%s-r%d' % (a['effort'], a['rep']) for a in bad))
        labs = {k for a in bad for k in ('hang', 'missed_capture', 'missed_mate', 'allows_mate') if a.get(k)}
        if p['prev_class'] in GOOD_CLASSES or labs & {'hang', 'missed_capture'}:
            r['category'] = CAP
        elif labs & {'missed_mate', 'allows_mate'}:
            r['category'] = MATE
        else:
            r['category'] = OTHER
        r['category_basis'] = '上一轮类别「%s」；第一批大失误那几遍的静态判定：%s' % (
            p['prev_class'], '、'.join(sorted(labs)) or '无标')
        lo_hi = b1.EPISODES.get(p['src_game'])
        if lo_hi and lo_hi[0] <= p['src_ply'] <= lo_hi[1]:
            r['_gkey'] = 'r1:%s' % p['src_game']
            r['group_note'] = '上一轮 %s 盘 %d–%d 半回合连着的同一件事' % ((p['src_game'],) + lo_hi)
        else:
            r['_gkey'] = 'b1q:%s' % p['id']
            r['group_note'] = '单独一件'
        rows.append(r)
    return rows


def xq_game_row(run, cfg, mv, ana, ply):
    a = ana[ply - 1]
    st = xq_state(mv[:ply - 1])
    fen = st['fens'][-1]
    assert fen == a['fen'] and X.turn(st) == a['side'], (run, ply)
    return st, {
        'game': 'xiangqi', 'source': '第一批 B 块 %s 第 %d 半回合（模型方 %s）' % (run, ply, a['side']),
        'src_game': run, 'src_ply': ply, 'src_condition': cond_of(cfg, a['side']),
        'fen': fen, 'moves': mv[:ply - 1], 'turn': a['side'],
        'prev_move': a['move'], 'prev_move_cn': a['text'], 'prev_eval_before': a['before'], 'prev_eval_after': a['after'],
        'prev_loss_cp': a['loss'], 'engine_best': a['best'],
        'engine_best_cn': X.notation(fen, a['best']) if a['best'] else None,
        'engine_note': 'engine_best / prev_eval_* 取自该盘 analysis.jsonl（Fairy-Stockfish depth 16，带完整历史，走子方视角，'
                       'prev_eval_* 未截断）',
    }


def xq_blunders(games):
    seen, rows = {}, []
    for run, (cfg, mv, ana, end) in games.items():
        for a in ana:
            if not a['player'].startswith('claude') or a['cls'] != 'blunder':
                continue
            st, r = xq_game_row(run, cfg, mv, ana, a['ply'])
            hit = [k for k in (SAME_EVENT.get((run, a['ply'])), X.key_of(r['fen'])) if k in seen]
            if hit:
                seen[hit[0]].setdefault('dup_sources', []).append('%s 第 %d 半回合（%s）' % (run, a['ply'], a['text']))
                continue
            r['kind'] = 'b1-game-blunder'
            r['category'], r['category_basis'] = static_category('xiangqi', r['fen'], r['prev_move'])
            r['_gkey'] = 'b1g:%s:%d' % (run, a['ply'])
            r['group_note'] = '第一批 B 块单独一步大失误'
            seen[X.key_of(r['fen'])] = seen[(run, a['ply'])] = r      # 按局面和按（盘, 半回合）都登记
            rows.append(r)
    for r in rows:
        if r.get('dup_sources'):
            r['group_note'] = '同一个昏招在几盘里重复出现，只留这一个；重复的：%s' % '；'.join(r['dup_sources'])
    return rows


def mate_check(eng, st):
    """对每个合法着法（去掉禁着）看走完后对方有没有杀。返回 (合法着数, 不被杀的着法, 被杀的着法数)。"""
    legal = X.legal(st)
    ban = X.banned(st, legal)
    legal = [m for m in legal if m not in ban]
    start, hist = st['fens'][0], list(st['fsf'])
    safe, losing = [], 0
    for m in legal:
        f1 = sf_after(st, m)
        if not X.legal_fen(f1):
            safe.append(m)                   # 走完对方无着：我赢
            continue
        s = Q.analyse(eng, start, hist + [X.to_fsf(m)])      # 对方视角
        if s.get('mate') is not None and s['mate'] > 0:
            losing += 1
        else:
            safe.append(m)
    return len(legal), sorted(safe), losing


def sf_after(st, m):
    return Q.XqRules().play(st['fens'][-1], m)


def xq_mates(games, jobs):
    cands = []
    for run, (cfg, mv, ana, end) in games.items():
        if not end or end['end'].get('reason') != '将死':
            continue
        loser = 'w' if end['end']['winner'] == 'b' else 'b'
        if not cfg['players'][loser].startswith('claude'):
            continue
        mine = [a for a in ana if a['side'] == loser]
        last = {a['ply'] for a in mine[-MATE_WINDOW:]}
        for a in mine:
            walk_in = not a['before'].startswith('mate -') and a['after'].startswith('mate -')
            if walk_in or a['ply'] in last:
                cands.append((run, a['ply'], walk_in))

    def work(c):
        run, ply, walk_in = c
        cfg, mv, ana, end = games[run]
        st, r = xq_game_row(run, cfg, mv, ana, ply)
        eng = Q.engine_for('xiangqi')
        try:
            n, safe, losing = mate_check(eng, st)
        finally:
            eng.close()
        r.update(kind='b1-game-mate', walk_in=walk_in, n_legal=n, n_losing=losing, safe_moves=safe,
                 mate_note='safe_moves / n_losing：Fairy-Stockfish depth 16（quiz judge 同一设置，带完整历史）走完每个合法着法'
                           '（去掉长将 / 长捉禁着）后，对方没有 / 有杀棋分；walk_in = 这步是在走前没杀、走完被算出杀')
        print('  看杀候选 %s 第 %d 半回合：%d 着里 %d 着被杀，不被杀的 %s%s' % (
            run, ply, n, losing, safe, '（走进杀）' if walk_in else ''), flush=True)
        return r

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        checked = list(ex.map(work, cands))
    ok = [r for r in checked if r['safe_moves'] and r['n_losing']]
    # 同一盘半回合相差 <= MATE_CHAIN 连成一件事
    rows, by_game = [], collections.defaultdict(list)
    for r in ok:
        by_game[r['src_game']].append(r)
    extra = []
    for run, rs in by_game.items():
        rs.sort(key=lambda r: r['src_ply'])
        chains, cur = [], [rs[0]]
        for r in rs[1:]:
            if r['src_ply'] - cur[-1]['src_ply'] <= MATE_CHAIN:
                cur.append(r)
            else:
                chains.append(cur)
                cur = [r]
        chains.append(cur)
        for ch in chains:
            key = 'mate:%s:%d' % (run, ch[0]['src_ply'])
            order = sorted(ch, key=lambda r: (not r['walk_in'], r['src_ply'] if r['walk_in'] else -r['src_ply']))
            for i, r in enumerate(order):
                r['category'], r['category_basis'] = MATE, '被将死前的局面，引擎验过有杀可看、也有不被杀的着法'
                r['_gkey'] = key
                r['group_note'] = '%s 第 %s 半回合一带走向被杀（同盘相差 <= %d 半回合算一件）' % (
                    run, '/'.join(str(x['src_ply']) for x in ch), MATE_CHAIN)
                (rows if i < PER_GROUP else extra).append(r)
    rows.sort(key=lambda r: (r['src_game'], r['src_ply']))
    return rows, extra, [r for r in checked if not (r['safe_moves'] and r['n_losing'])]


def xq_fill(taken_rows, need):
    """上一轮三段同一件事里第一批没取的，三段轮流补 need 个。"""
    if need <= 0:
        return []
    b1 = load_b1_select()
    cases = list(csv.DictReader(open(os.path.join(b1.XQ_DIR, 'blunder_cases.tsv'), encoding='utf-8'), delimiter='\t'))
    plies = {(r['game'], int(r['ply'])): r
             for r in csv.DictReader(open(os.path.join(b1.XQ_DIR, 'plies.tsv'), encoding='utf-8'), delimiter='\t')}
    have = {(p['src_game'], p['src_ply']) for p in jl(os.path.join(B1, 'xiangqi.jsonl'))}
    per_ep = collections.defaultdict(list)
    for c in cases:
        g, ply = c['game'], int(c['ply'])
        lo_hi = b1.EPISODES.get(g)
        if lo_hi and lo_hi[0] <= ply <= lo_hi[1] and (g, ply) not in have \
                and abs(int(plies[(g, ply)]['eval_before'])) < 1000:
            per_ep[g].append(c)
    order, i = [], 0
    eps = sorted(per_ep)
    while len(order) < need and any(per_ep.values()):
        g = eps[i % len(eps)]
        if per_ep[g]:
            order.append(per_ep[g].pop(0))
        i += 1
    rows = []
    for c in order:
        g, ply = c['game'], int(c['ply'])
        recs = [json.loads(l) for l in open(os.path.join(b1.XQ_ART, g, 'game.jsonl'), encoding='utf-8')]
        end = [r for r in recs if r['type'] == 'end'][0]
        games = ast.literal_eval(end['moves']) if isinstance(end['moves'], str) else end['moves']
        p = plies[(g, ply)]
        st = xq_state(games[:ply - 1])
        assert games[ply - 1] == p['move'] and X.turn(st) == p['side'], (g, ply)
        rows.append({
            'game': 'xiangqi', 'kind': 'r1-fill', 'fill': True,
            'source': 'llm-xiangqi-play round 1, game %s ply %d（补位：同一件事的后续局面）' % (g, ply),
            'src_game': g, 'src_ply': ply, 'src_case': int(c['case']),
            'fen': st['fens'][-1], 'moves': games[:ply - 1], 'turn': X.turn(st),
            'prev_move': p['move'], 'prev_move_cn': c['move_cn'], 'prev_class': c['class'], 'prev_flags': c['flags'],
            'prev_basis': c['basis'], 'prev_eval_before': int(p['eval_before']), 'prev_eval_after': int(p['eval_after']),
            'prev_loss_cp': int(p['loss_cp']), 'engine_best': p['engine_best'],
            'engine_best_cn': X.notation(st['fens'][-1], p['engine_best']),
            'engine_note': 'engine_best / prev_eval_* 取自上一轮 plies.tsv（Fairy-Stockfish depth 16，截断 ±1000，走子方视角）',
            'category': CAP if c['class'] in GOOD_CLASSES else OTHER, 'category_basis': '上一轮类别「%s」' % c['class'],
            '_gkey': 'r1:%s' % g, 'group_note': '上一轮 %s 盘 %d–%d 半回合连着的同一件事' % ((g,) + b1.EPISODES[g]),
        })
    return rows


def xiangqi(jobs):
    games = {run: load_game(run) for run in game_runs('b1-xq-')}
    part1 = xq_b1_quiz()
    part2 = xq_blunders(games)
    part3, extra, dropped = xq_mates(games, jobs)
    rows = part1 + part2 + part3
    fill = xq_fill(rows, N_XQ - len(rows))
    rows += fill
    for i, r in enumerate(rows):
        r['id'] = 'x2-%02d' % (i + 1)
        r['game'] = 'xiangqi'
    assign_groups(rows)
    print('中国象棋：第一批题 %d、B 块大失误 %d、看杀 %d（另有同一件事超额未取 %d：%s；验下来不够格 %d：%s）、补位 %d，共 %d' % (
        len(part1), len(part2), len(part3), len(extra),
        ', '.join('%s:%d' % (r['src_game'], r['src_ply']) for r in extra), len(dropped),
        ', '.join('%s:%d' % (r['src_game'], r['src_ply']) for r in dropped), len(fill), len(rows)))
    return [order_keys(r) for r in rows]


# ---------------------------------------------------------------- 国际象棋
def chess_rows():
    import chess
    blund = b1_errors('chess', lambda r: r['blunder'] and r['effort'] in ('xhigh', 'max'))
    rows = []
    for p in jl(os.path.join(B1, 'chess.jsonl')):
        if p['id'] not in blund:
            continue
        r = dict(p)
        mate = p['pick_theme'].startswith('mate')
        r.update(kind='b1-quiz', batch1_id=p['id'], source='batch1 quiz %s（lichess 谜题 %s）' % (p['id'], p['puzzle_id']),
                 b1_blunders=sorted('%s-r%d' % (a['effort'], a['rep']) for a in blund[p['id']]),
                 category=MATE if mate else CAP, category_basis='第一批选题主题 pick_theme=%s' % p['pick_theme'],
                 _gkey='b1q:%s' % p['id'], group_note='单独一件')
        rows.append(r)
    n1 = len(rows)
    seen = {}
    for run in game_runs('b1-ch-'):
        cfg, mv, ana, end = load_game(run)
        for a in ana:
            if not a['player'].startswith('claude') or a['cls'] != 'blunder':
                continue
            ply = a['ply']
            key = ' '.join(a['fen'].split()[:4])
            if key in seen:
                seen[key]['dup_sources'].append('%s 第 %d 半回合（%s）' % (run, ply, a['text']))
                continue
            assert ply >= 2, (run, ply)
            prev = ana[ply - 2]
            b = chess.Board(prev['fen'])
            opp = chess.Move.from_uci(prev['move'])
            opp_san = b.san(opp)
            b.push(opp)
            assert b.fen().split()[:4] == a['fen'].split()[:4], (run, ply)
            sol = chess.Move.from_uci(a['best'])
            cat, basis = static_category('chess', a['fen'], a['move'])
            r = {
                'game': 'chess', 'kind': 'b1-game-blunder',
                'source': '第一批 B 块 %s 第 %d 半回合（模型方 %s）' % (run, ply, a['side']),
                'src_game': run, 'src_ply': ply, 'src_condition': cond_of(cfg, a['side']),
                'fen_before_opp': prev['fen'], 'opp_move': prev['move'], 'opp_move_san': opp_san,
                'fen': b.fen(), 'turn': 'w' if b.turn else 'b', 'solution': a['best'], 'solution_san': b.san(sol),
                'solution_note': '整盘局面没有谜题正解，solution 取该盘 analysis.jsonl 的引擎最佳着（Stockfish depth 18）',
                'prev_move': a['move'], 'prev_move_san': a['text'], 'prev_eval_before': a['before'],
                'prev_eval_after': a['after'], 'prev_loss_cp': a['loss'], 'prev_lichess': a.get('lichess'),
                'prev_wp_loss': round(a['wp_before'] - a['wp_after'], 1),
                'category': cat, 'category_basis': basis, 'dup_sources': [],
                '_gkey': 'b1g:%s:%d' % (run, ply), 'group_note': '第一批 B 块单独一步大失误',
            }
            seen[key] = r
            rows.append(r)
    # 同一盘相邻两步都是大失误（analyze.events 的并法：半回合差 2）并成一件
    last = {}
    for r in rows[n1:]:
        prev = last.get(r['src_game'])
        if prev and r['src_ply'] - prev['src_ply'] <= 2:
            r['_gkey'] = prev['_gkey']
            r['group_note'] = prev['group_note'] = '%s 相邻两步连着的大失误（analyze 并成一件的口径）' % r['src_game']
        last[r['src_game']] = r
    for r in rows[n1:]:
        if r['dup_sources']:
            r['group_note'] = '同一局面同一步在几盘里重复出现，只留这一个；重复的：%s' % '；'.join(r['dup_sources'])
        else:
            del r['dup_sources']
    for i, r in enumerate(rows):
        r['id'] = 'c2-%02d' % (i + 1)
    assign_groups(rows)
    print('国际象棋：第一批题 %d、B 块大失误 %d，共 %d' % (n1, len(rows) - n1, len(rows)))
    return [order_keys(r) for r in rows]


def order_keys(r):
    head = ('id', 'game', 'kind', 'source', 'category', 'group', 'related_to')
    return {**{k: r[k] for k in head if k in r}, **{k: v for k, v in r.items() if k not in head}}


# ---------------------------------------------------------------- 只读检查
def check():
    import chess
    bad = 0
    for game in ('xiangqi', 'chess'):
        path = os.path.join(HERE, '%s.jsonl' % game)
        rows = jl(path)
        ids = [r['id'] for r in rows]
        assert len(set(ids)) == len(ids), ('id 重复', path)
        for p in rows:
            try:
                st = Q.build_state(p)          # 和 quiz run / judge 同一个入口；FEN 对不上会断言失败
                fen = st['fens'][-1]
                if game == 'xiangqi':
                    legal = X.legal(st)
                    assert X.turn(st) == p['turn'] == fen.split()[1], '走子方不一致'
                    assert legal, '走子方无着'
                    assert p['prev_move'] in legal, 'prev_move 不合法'
                    assert not p.get('safe_moves') or set(p['safe_moves']) <= set(legal), 'safe_moves 不合法'
                else:
                    b = chess.Board(fen)
                    assert b.is_valid(), 'FEN 不合法'
                    assert ('w' if b.turn else 'b') == p['turn'], '走子方不一致'
                    assert not b.is_game_over(), '已终局'
                    assert chess.Move.from_uci(p['solution']) in b.legal_moves, 'solution 不合法'
                    assert 'prev_move' not in p or chess.Move.from_uci(p['prev_move']) in b.legal_moves, 'prev_move 不合法'
                for k in ('category', 'group', 'kind', 'source'):
                    assert p.get(k) is not None, '缺 %s' % k
            except AssertionError as ex:
                bad += 1
                print('✗ %s %s：%s' % (game, p['id'], ex))
        c = collections.Counter(r['kind'] for r in rows)
        print('%s：%d 个，%s；分组 %d 个；类别 %s' % (game, len(rows), dict(c), len({r['group'] for r in rows}),
                                          dict(collections.Counter(r['category'] for r in rows))))
    print('检查完：%s' % ('全部通过' if not bad else '%d 个有问题' % bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('what', choices=('xiangqi', 'chess', 'check'))
    ap.add_argument('--jobs', type=int, default=4, help='看杀题验证的并发引擎数')
    ap.add_argument('--out', default=HERE)
    a = ap.parse_args()
    if a.what == 'check':
        return check()
    rows = xiangqi(a.jobs) if a.what == 'xiangqi' else chess_rows()
    path = os.path.join(a.out, '%s.jsonl' % a.what)
    write_jsonl(path, rows)
    print('写了 %d 条到 %s' % (len(rows), path))
    return 0


if __name__ == '__main__':
    sys.exit(main())
