"""第一批局面题（design.md 第六节组 1）的选取脚本：两种棋各 30 个局面，写成 data/batch1/<棋种>.jsonl。

    python3 data/batch1/select_positions.py xiangqi
    python3 data/batch1/select_positions.py chess --csv <解压出的 lichess 谜题 CSV>

中国象棋：上一轮 74 步昏招的走前局面（~/repos/ai-research/topics/llm-xiangqi-play/ 的 blunder_cases.tsv、plies.tsv，
  着法取自 ~/repos/jev-study/artifacts/xiangqi_llm/<A..E>/game.jsonl，只读）。规则：
  1. 排除走前已经必胜 / 必败的（上一轮引擎分 |eval_before| >= 1000，即截断口径 ±1000）；
  2. 类别是「规则落盘错」「看对但漏看」「看对但判断错」的全要（谁能吃到谁那一类），
     但同一件事连着好几步的只取前 2 个：C 盘 15–30（g5 车挂在象口）、D 盘 8–16（b 线车炮互相悬挂）、B 盘 69–73（e5 车对 e6 卒）；
  3. 不够 30 个，用「无法判断」里带 BIG（上一轮亏损 >= 250）的补，按亏损从大到小，同样排除上面三段。
中国象棋每条带从开局起的全部着法（ICCS），判长将 / 长捉要用；走前 FEN 由 pyffish 重放得出，并和 plies.tsv 的着法核对。

国际象棋：lichess 公开谜题库（CC0，https://database.lichess.org/#puzzles）。只取文件开头一段就够：
    curl -r 0-31457279 https://database.lichess.org/lichess_db_puzzle.csv.zst -o head.csv.zst
    zstd -dc head.csv.zst > head.csv      # 末尾会报 premature end，属预期；最后半行脚本会丢掉
  2026-09-25 取的前 30MB 解出约 62.9 万条。谜题库每月更新、行序可能变，所以入库的 chess.jsonl 才是这批题的真身，
  重跑本脚本只用来说明怎么选的。规则：NbPlays >= 1000、RatingDeviation <= 90、Popularity >= 80；
  Rating 800–2000 分 6 段（每段 200），每段 5 题 = 4 题「谁能吃到谁」主题 + 1 题杀棋（mateIn1 / mateIn2 隔段交替）；
  8 个主题（hangingPiece fork pin skewer discoveredAttack capturingDefender trappedPiece attraction）轮流分到各段，
  每个主题共 3 题；主题题要求 Themes 里不含 mate；同一段内按固定种子随机抽。
  lichess 谜题的 FEN 是对手走之前的局面，Moves 第一步是对手的着，走完才是要解的局面；正解首着是 Moves 第二步。
"""
import argparse, ast, csv, json, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

XQ_DIR = os.path.expanduser('~/repos/ai-research/topics/llm-xiangqi-play')
XQ_ART = os.path.expanduser('~/repos/jev-study/artifacts/xiangqi_llm')
GOOD_CLASSES = ('规则落盘错', '看对但漏看', '看对但判断错')
EPISODES = {'C': (15, 30), 'D': (8, 16), 'B': (69, 73)}     # 同一件事连着好几步：每段只取前 2 个
PER_EPISODE = 2
N = 30

CAPTURE_THEMES = ('hangingPiece', 'fork', 'pin', 'skewer', 'discoveredAttack', 'capturingDefender',
                  'trappedPiece', 'attraction')
BINS = [(800 + 200 * i, 1000 + 200 * i) for i in range(6)]
SEED = 20260925
LICHESS_SOURCE = 'lichess puzzle database, CC0 (https://database.lichess.org/#puzzles)'


def write_jsonl(path, rows):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    os.replace(tmp, path)


# ---------------------------------------------------------------- 中国象棋
def xiangqi():
    from llmchess import xiangqi as X
    cases = list(csv.DictReader(open(os.path.join(XQ_DIR, 'blunder_cases.tsv'), encoding='utf-8'), delimiter='\t'))
    plies = {(r['game'], int(r['ply'])): r
             for r in csv.DictReader(open(os.path.join(XQ_DIR, 'plies.tsv'), encoding='utf-8'), delimiter='\t')}
    games = {}
    for g in 'ABCDE':
        recs = [json.loads(l) for l in open(os.path.join(XQ_ART, g, 'game.jsonl'), encoding='utf-8')]
        end = [r for r in recs if r['type'] == 'end'][0]
        mv = end['moves']
        games[g] = ast.literal_eval(mv) if isinstance(mv, str) else mv
        cfg = recs[0]['cfg']
        cfg = ast.literal_eval(cfg) if isinstance(cfg, str) else cfg
        games[g + ':cfg'] = {k: cfg.get(k) for k in ('view', 'history', 'selfcheck', 'effort')}

    def episode(c):
        lo_hi = EPISODES.get(c['game'])
        return c['game'] if lo_hi and lo_hi[0] <= int(c['ply']) <= lo_hi[1] else None

    ok = [c for c in cases if abs(int(plies[(c['game'], int(c['ply']))]['eval_before'])) < 1000]
    taken, per_ep = [], {}

    def take(c):
        ep = episode(c)
        if ep:
            if per_ep.get(ep, 0) >= PER_EPISODE:
                return
            per_ep[ep] = per_ep.get(ep, 0) + 1
        taken.append(c)

    for c in ok:
        if c['class'] in GOOD_CLASSES:
            take(c)
    fill = sorted((c for c in ok if c['class'] not in GOOD_CLASSES and 'BIG' in c['flags'].split(',') and not episode(c)),
                  key=lambda c: -int(plies[(c['game'], int(c['ply']))]['loss_cp']))
    for c in fill:
        if len(taken) >= N:
            break
        take(c)
    assert len(taken) >= N, ('候选不够 30 个', len(taken))
    taken = sorted(taken[:N], key=lambda c: int(c['case']))
    rows = []
    for i, c in enumerate(taken):
        g, ply = c['game'], int(c['ply'])
        p = plies[(g, ply)]
        moves = games[g][:ply - 1]
        st = X.start()
        for m in moves:
            X.push(st, m)
        played = games[g][ply - 1]
        assert played == p['move'], ('着法和 plies.tsv 对不上', g, ply, played, p['move'])
        assert X.turn(st) == p['side'], (g, ply)
        rows.append({
            'id': 'x%02d' % (i + 1), 'game': 'xiangqi', 'source': 'llm-xiangqi-play round 1, game %s ply %d' % (g, ply),
            'src_game': g, 'src_ply': ply, 'src_case': int(c['case']), 'src_condition': games[g + ':cfg'],
            'fen': st['fens'][-1], 'moves': moves, 'turn': X.turn(st),
            'prev_move': played, 'prev_move_cn': c['move_cn'], 'prev_class': c['class'], 'prev_flags': c['flags'],
            'prev_basis': c['basis'], 'prev_eval_before': int(p['eval_before']), 'prev_eval_after': int(p['eval_after']),
            'prev_loss_cp': int(p['loss_cp']), 'engine_best': p['engine_best'],
            'engine_best_cn': X.notation(st['fens'][-1], p['engine_best']),
            'engine_note': 'engine_best / prev_eval_* 取自上一轮 plies.tsv（Fairy-Stockfish depth 16，截断 ±1000，走子方视角）',
        })
    return rows


# ---------------------------------------------------------------- 国际象棋
def chess_rows(csv_path):
    import chess
    pool = []
    with open(csv_path, encoding='utf-8', newline='') as f:
        rd = csv.DictReader(f)
        for r in rd:
            try:
                rating, rd_, pop, plays = int(r['Rating']), int(r['RatingDeviation']), int(r['Popularity']), int(r['NbPlays'])
            except (TypeError, ValueError):          # 截断的最后半行
                continue
            if not r.get('GameUrl') or plays < 1000 or rd_ > 90 or pop < 80 or not (800 <= rating < 2000):
                continue
            pool.append(r)
    pool.sort(key=lambda r: r['PuzzleId'])
    rng = random.Random(SEED)
    chosen, used = [], set()
    for b, (lo, hi) in enumerate(BINS):
        in_bin = [r for r in pool if lo <= int(r['Rating']) < hi]
        wants = [('theme', CAPTURE_THEMES[(4 * b + j) % len(CAPTURE_THEMES)]) for j in range(4)]
        wants.append(('mate', 'mateIn1' if b % 2 == 0 else 'mateIn2'))
        for kind, theme in wants:
            cands = []
            for r in in_bin:
                th = r['Themes'].split()
                if r['PuzzleId'] in used or theme not in th:
                    continue
                if kind == 'theme' and any(t.startswith('mate') for t in th):
                    continue
                cands.append(r)
            assert cands, ('这一段没有候选', lo, hi, theme)
            r = rng.choice(cands)
            used.add(r['PuzzleId'])
            chosen.append((theme, r))
    rows = []
    for i, (theme, r) in enumerate(chosen):
        mv = r['Moves'].split()
        b = chess.Board(r['FEN'])
        opp = chess.Move.from_uci(mv[0])
        assert opp in b.legal_moves, r['PuzzleId']
        opp_san = b.san(opp)
        b.push(opp)
        sol = chess.Move.from_uci(mv[1])
        assert sol in b.legal_moves, r['PuzzleId']
        rows.append({
            'id': 'c%02d' % (i + 1), 'game': 'chess', 'source': LICHESS_SOURCE,
            'puzzle_id': r['PuzzleId'], 'rating': int(r['Rating']), 'rating_dev': int(r['RatingDeviation']),
            'popularity': int(r['Popularity']), 'plays': int(r['NbPlays']), 'themes': r['Themes'], 'game_url': r['GameUrl'],
            'pick_theme': theme, 'puzzle_fen': r['FEN'], 'puzzle_moves': r['Moves'],
            'fen_before_opp': r['FEN'], 'opp_move': mv[0], 'opp_move_san': opp_san,
            'fen': b.fen(), 'turn': 'w' if b.turn else 'b', 'solution': mv[1], 'solution_san': b.san(sol),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('game', choices=('xiangqi', 'chess'))
    ap.add_argument('--csv', help='国际象棋：解压出的 lichess 谜题 CSV')
    ap.add_argument('--out', default=HERE)
    a = ap.parse_args()
    if a.game == 'xiangqi':
        rows = xiangqi()
    else:
        if not a.csv:
            raise SystemExit('国际象棋要 --csv')
        rows = chess_rows(a.csv)
    path = os.path.join(a.out, '%s.jsonl' % a.game)
    write_jsonl(path, rows)
    print('写了 %d 条到 %s' % (len(rows), path))


if __name__ == '__main__':
    main()
