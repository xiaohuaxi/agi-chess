"""生成 viewer/test/fixtures/ 下的测试数据（入库）。在仓库根目录跑：python3 viewer/test/gen_fixtures.py

- xq-roundtrip.json：象棋记谱往返。一批局面（多路兵、同线多子、仕相同线、随机对局途中、兵多的随机局面），
  每个局面的全部合法着法由导出端 llmchess.xiangqi.pgn_move 写成中文记谱，并带 pyffish 判的「走完是否将军」。
  JS 端解析回坐标、判将军，应与这里逐条一致。
- 两盘样例（有 runs/ 时才重取）：从本机对局截一盘象棋、一盘国际象棋的 game.pgn，
  连同 game.jsonl 里每步的坐标与将军标记。
"""
import json
import os
import random
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import pyffish as sf  # noqa: E402

from llmchess import xiangqi as X  # noqa: E402

OUT = os.path.join(ROOT, 'viewer', 'test', 'fixtures')
# 对局记录目录：环境变量 VIEWER_RUNS 优先；worktree（.agents/worktrees/<名>）里没有 runs/，默认用主检出的
RUNS = os.environ.get('VIEWER_RUNS') or os.path.join(ROOT.split('/.agents/worktrees/')[0], 'runs')
SAMPLES = {'xq-sample': 'b3max-xq/fsf-nodes100-s2-w', 'chess-sample': 'b1-ch-session-3'}

KINGS = {'e0': 'K', 'd9': 'k'}
# 与 tests/test_export.py 的 XqbaseNotation 同一批局面
BUILT = [
    {'f7': 'P', 'f5': 'P', 'e6': 'P', 'd7': 'P', 'd5': 'P'},
    {'c6': 'P', 'c5': 'P', 'g6': 'P'},
    {'c7': 'P', 'c6': 'P', 'c5': 'P', 'g5': 'P'},
    {'c8': 'P', 'c7': 'P', 'c6': 'P', 'c5': 'P'},
    {'c9': 'P', 'c8': 'P', 'c7': 'P', 'c6': 'P', 'c5': 'P'},
    {'d7': 'P', 'd6': 'P', 'd5': 'P', 'g6': 'P', 'g5': 'P'},
    {'a0': 'R', 'a4': 'R'},
    {'b2': 'N', 'b5': 'N'},
    {'h2': 'C', 'h5': 'C'},
    {'f0': 'A', 'f2': 'A'},
    {'c0': 'B', 'c4': 'B'},
    {'c0': 'B', 'c4': 'B', 'f0': 'A', 'f2': 'A', 'b2': 'N', 'b5': 'N', 'h2': 'C', 'h5': 'C', 'a0': 'R', 'a4': 'R'},
]


def fen_of(pieces, turn):
    return '%s %s - - 0 1' % (X.board_fen(pieces), turn)


def flip(pieces):
    return {X.sq_of(8 - X.xy(s)[0], 9 - X.xy(s)[1]): p.swapcase() for s, p in pieces.items()}


def ok(fen):
    """行棋方的对手没有被将（否则局面不合法），且有着可走。"""
    board, turn = X.board_of(fen)
    other = fen.replace(' %s ' % turn, ' %s ' % X.other(turn), 1)
    return not sf.gives_check(X.XQ, other, []) and sf.legal_moves(X.XQ, fen, [])


def entry(fen):
    """造的局面里有的对方已经被将（不合法，比如兵贴着将），这时 pyffish 只看这步有没有「给」将，
    和「走完是否被将」不是一回事，将军标记写 None、只测记谱。"""
    legal_pos = ok(fen)
    moves = []
    for mv in X.legal_fen(fen):
        chk = bool(sf.gives_check(X.XQ, fen, [X.to_fsf(mv)])) if legal_pos else None
        moves.append([mv, X.pgn_move(fen, mv), chk])
    texts = [m[1] for m in moves]
    assert len(set(texts)) == len(texts), fen
    return {'fen': fen, 'moves': moves}


def random_crowd(rng):
    """兵多的随机局面：双方各 5 个过河兵随机摆，再加几个大子，专测多路兵编号。"""
    while True:
        pieces = {X.sq_of(rng.randint(3, 5), rng.randint(0, 2)): 'K', X.sq_of(rng.randint(3, 5), rng.randint(7, 9)): 'k'}
        for p, ys in (('P', range(5, 10)), ('p', range(0, 5))):
            for _ in range(5):
                pieces.setdefault(X.sq_of(rng.randint(0, 8), rng.choice(ys)), p)
        for p in 'RNCrnc':
            pieces.setdefault(X.sq_of(rng.randint(0, 8), rng.randint(0, 9)), p)
        fen = fen_of(pieces, rng.choice('wb'))
        if ok(fen):
            return fen


def roundtrip():
    rng = random.Random(20260929)
    fens = []
    for pieces in BUILT:
        fens.append(fen_of(dict(KINGS, **pieces), 'w'))
        fens.append(fen_of(flip(dict(KINGS, **pieces)), 'b'))
    fens += [random_crowd(rng) for _ in range(40)]
    for _ in range(3):                           # 随机对局途中每隔几步取一个局面
        fen = X.START
        for ply in range(120):
            legal = sf.legal_moves(X.XQ, fen, [])
            if not legal:
                break
            if ply % 4 == 0:
                fens.append(fen)
            fen = sf.get_fen(X.XQ, fen, [rng.choice(legal)])
    data = [entry(f) for f in fens]
    with open(os.path.join(OUT, 'xq-roundtrip.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')
    print('xq-roundtrip.json: %d 个局面，%d 步' % (len(data), sum(len(d['moves']) for d in data)))


def samples():
    for name, tag in SAMPLES.items():
        d = os.path.join(RUNS, tag)
        if not os.path.isdir(d):
            print('跳过样例 %s：没有 %s' % (name, d))
            continue
        shutil.copyfile(os.path.join(d, 'game.pgn'), os.path.join(OUT, name + '.pgn'))
        rows = [json.loads(l) for l in open(os.path.join(d, 'game.jsonl'), encoding='utf-8')]
        moves = sorted((r for r in rows if r['type'] == 'move'), key=lambda r: r['ply'])
        exp = {'source': 'runs/' + tag, 'moves': [[r['move'], bool(r['check'])] for r in moves]}
        with open(os.path.join(OUT, name + '.json'), 'w', encoding='utf-8') as f:
            json.dump(exp, f, ensure_ascii=False)
            f.write('\n')
        print('%s: %d 步（%s）' % (name, len(moves), tag))


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    roundtrip()
    samples()
