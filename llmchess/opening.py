"""随机开局（plan-batch2 0.4）：前 N 个半回合双方都由程序走，模型从第 N+1 个半回合起接手。

每个半回合让引擎浅搜（国际象棋 Stockfish、中国象棋 Fairy-Stockfish；固定深度、单线程、每个局面前 ucinewgame），
MultiPV 3，取和最好着分差 ≤ 50 厘兵的着法，按 (开局种子, 半回合号) 起的随机数抽一个。
固定深度 + 单线程 + 清哈希，同一局面的搜索结果每次一样，所以同种子两次生成的开局一致。

生成一次就写进 config（opening.moves），续跑照记录重放、不重新抽。引擎在这里只摆出双方共同的起始局面，
它的任何输出都不进模型提示：模型只在着法历史里看到已走的着法（plan 0.4 的论证）。
"""
import random, re

from .engine import Engine, EngineError

DEPTH = 10
MULTIPV = 3
MARGIN = 50
MATE = 100000
SPECS = {'chess': 'stockfish:depth=%d', 'xiangqi': 'fsf:depth=%d'}

_INFO = re.compile(r'\bdepth (\d+)\b.*?\bmultipv (\d+)\b.*?\bscore (cp|mate) (-?\d+)( (?:lower|upper)bound)?.*?\bpv (\S+)')


def parse_mode(text):
    """'random:N' -> N；空或 None -> 0。"""
    if not text:
        return 0
    kind, _, n = text.partition(':')
    if kind != 'random' or not n.isdigit():
        raise ValueError('开局写成 random:N（N 是程序替双方走的半回合数），收到 %r' % text)
    return int(n)


def score_value(kind, n):
    """把 UCI 评分换成可比的数：厘兵原样；N 步杀 = MATE − N，被 N 步杀 = −MATE + N。"""
    if kind == 'cp':
        return n
    return MATE - n if n > 0 else -MATE - n


def parse_multipv(lines):
    """UCI 搜索输出 -> [(着法（引擎写法）, 评分值)]，按 multipv 序号排。每个序号取最深的一条非上下界的 info。"""
    best = {}
    for line in lines:
        if not line.startswith('info ') or ' multipv ' not in line:
            continue
        m = _INFO.search(line)
        if not m or m.group(5):
            continue
        depth, k = int(m.group(1)), int(m.group(2))
        if k not in best or depth >= best[k][0]:
            best[k] = (depth, m.group(6), score_value(m.group(3), int(m.group(4))))
    return [(best[k][1], best[k][2]) for k in sorted(best)]


class Picker(Engine):
    def top(self, start_fen, moves, searchmoves=None):
        self._send('ucinewgame')
        self._send('isready')
        self._until('readyok')
        self._send('position fen %s%s' % (start_fen, (' moves ' + ' '.join(moves)) if moves else ''))
        cmd = self.spec['go'] + (' searchmoves ' + ' '.join(searchmoves) if searchmoves else '')
        self._send(cmd)
        return parse_multipv(self._until('bestmove'))


def spec_for(G, game):
    spec = G.engine_spec(SPECS[game] % DEPTH)
    return dict(spec, name='%s-opening' % spec['name'], options=spec['options'] + [('MultiPV', str(MULTIPV))])


def choose(cands, seed, ply):
    """cands 是 [(着法, 评分值)]，第一个是最好着；取分差 ≤ MARGIN 的，按 (种子, 半回合号) 抽。"""
    top = cands[0][1]
    pool = [mv for mv, v in cands if top - v <= MARGIN]
    return random.Random('opening:%s:%d' % (seed, ply)).choice(pool), pool


def generate(G, game, n, seed):
    """生成开局：返回写进 config 的 dict。n 个半回合里先分出胜负就停（实际不会发生）。"""
    spec = spec_for(G, game)
    st = G.start()
    plies = []
    with Picker(spec, timeout=60) as eng:
        for i in range(n):
            if G.ending(st) is not None:
                break
            moves = G.legal(st)
            ban = G.banned(st, moves)
            search = [G.to_engine(m) for m in moves if m not in ban] if ban else None
            raw = eng.top(st['fens'][0], [G.to_engine(m) for m in st['moves']], search)
            cands = [(G.from_engine(m), v) for m, v in raw]
            cands = [(m, v) for m, v in cands if m in moves and m not in ban]
            if not cands:
                raise EngineError('开局引擎在第 %d 个半回合没给出能走的着法：%r' % (i + 1, raw))
            mv, pool = choose(cands, seed, i + 1)
            G.push(st, mv)
            plies.append({'ply': i + 1, 'move': mv, 'text': st['record'][-1], 'pool': pool,
                          'cands': [[m, v] for m, v in cands]})
        eng_id = eng.id
    return {'mode': 'random', 'plies': n, 'seed': seed, 'engine': spec['name'], 'engine_id': eng_id,
            'go': spec['go'], 'multipv': MULTIPV, 'margin': MARGIN,
            'moves': [p['move'] for p in plies], 'record': [p['text'] for p in plies], 'detail': plies}


def moves_of(cfg):
    """config 里记下的开局着法（没有随机开局就是空表）。"""
    return list((cfg.get('opening') or {}).get('moves') or [])
