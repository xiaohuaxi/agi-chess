"""中国象棋模块：规则、禁着与终局、着法解析、局面呈现、提示、复述打分、棋谱、引擎参数。

规则判定照搬 jev-study，不自己改棋规（以 pyffish 为准）：
  - 坐标换算、FEN 解析、合法着法、将军、将死 / 困毙、中文记谱、违规分类：主干 games/xiangqi/boards.py；
  - 终局（rule_end / ending）、禁着（banned）、记谱兜底（notation）：分支 archive/duel-web 的 play_xiangqi.py（11d0bf0）；
  - 呈现、历史、提示、自查、复述打分、着法解析（resolve / check_iccs）：同分支的 llm_duel.py。
搬过来时只做了两处改动：函数改成只处理中国象棋（去掉 game 参数），FEN 解析改名 board_of（parse 这个名字留给着法解析）。

胜负：将死、困毙判负；同一局面第三次出现时，一方长将（或按 pyffish 的近似判法长捉）判负，否则判和；
连续一百个半回合没有吃子判和。会因长将 / 长捉当场判负的着法当作非法着法退回（banned）。
"""
import json, os, re, shutil

import cchess
import pyffish as sf

XQ = 'xiangqi'
START = sf.start_fen(XQ)
SIDES = {'w': '红方', 'b': '黑方'}
ALL_VIEW = 'grid,pieces,fen'       # show=all：棋盘 + 清单 + FEN，第 4P2 批之前的默认给法，旧记录都是它
# 呈现方式（show 档）→ view。整盘对局（cli）和局面题（quiz）共用。boardpieces = all 去掉 FEN 那段（逐字相同）。
SHOWS = {'all': ALL_VIEW, 'board': 'grid', 'pieces': 'pieces', 'fen': 'fen', 'boardpieces': 'grid,pieces'}
DEFAULT_SHOW = 'pieces'           # 第 4P2 批定的默认给法（docs/results/batch4-presentation.md 末节），show=all 回到旧提示
RECITE = True                     # 支持复述打分


def other(side):
    return 'b' if side == 'w' else 'w'


# ---------------------------------------------------------------- 坐标与 FEN（boards.py）
_ICCS = re.compile(r'^([a-i])(\d)([a-i])(\d)$')
_FSF = re.compile(r'^([a-i])(\d+)([a-i])(\d+)$')


def to_fsf(mv):
    """ICCS -> Fairy-Stockfish 着法（横线 +1）。"""
    m = _ICCS.match(mv)
    assert m, ('不是 ICCS 着法', mv)
    return '%s%d%s%d' % (m[1], int(m[2]) + 1, m[3], int(m[4]) + 1)


def from_fsf(mv):
    """Fairy-Stockfish 着法 -> ICCS。"""
    m = _FSF.match(mv)
    assert m, ('不是 Fairy-Stockfish 中国象棋着法', mv)
    y1, y2 = int(m[2]) - 1, int(m[4]) - 1
    assert 0 <= y1 <= 9 and 0 <= y2 <= 9, mv
    return '%s%d%s%d' % (m[1], y1, m[3], y2)


def xy(sq):
    return 'abcdefghi'.index(sq[0]), int(sq[1:])


def sq_of(x, y):
    return 'abcdefghi'[x] + str(y)


def board_of(fen):
    """FEN -> ({格: 棋子字母}, 行棋方 'w'/'b')。大写 = 红。（boards.parse）"""
    parts = fen.split()
    rows = parts[0].split('/')
    assert len(rows) == 10, ('FEN 横线数不对', fen)
    board = {}
    for i, row in enumerate(rows):
        y, x, num = 9 - i, 0, ''
        for ch in row:
            if ch.isdigit():
                num += ch
                continue
            if num:
                x += int(num)
                num = ''
            assert ch.isalpha(), ('FEN 里有不认识的字符', fen)
            board[sq_of(x, y)] = ch
            x += 1
        if num:
            x += int(num)
        assert x == 9, ('FEN 某一行格数不对', fen, row)
    return board, (parts[1] if len(parts) > 1 else 'w')


def board_fen(board):
    """{格: 棋子} -> FEN 第一段。"""
    rows = []
    for y in range(9, -1, -1):
        row, blank = '', 0
        for x in range(9):
            p = board.get(sq_of(x, y))
            if p is None:
                blank += 1
            else:
                if blank:
                    row += str(blank)
                    blank = 0
                row += p
        rows.append(row + (str(blank) if blank else ''))
    return '/'.join(rows)


def key_of(fen):
    """判重复用：只看棋盘、行棋方，忽略步数计数。"""
    return ' '.join(fen.split()[:4])


def is_red(piece):
    return piece.isupper()


def legal_fen(fen):
    return sorted(from_fsf(m) for m in sf.legal_moves(XQ, fen, []))


def in_check_fen(fen):
    return sf.gives_check(XQ, fen, [])


def status(fen):
    """'mate'（受将且无着）/ 'stalemate'（困毙）/ 'check' / 'ok'。"""
    moves = sf.legal_moves(XQ, fen, [])
    chk = sf.gives_check(XQ, fen, [])
    if not moves:
        return 'mate' if chk else 'stalemate'
    return 'check' if chk else 'ok'


# ---------------------------------------------------------------- 中文记谱（boards.py + play_xiangqi.notation）
CN_NAME = {'K': '帅', 'A': '仕', 'B': '相', 'N': '马', 'R': '车', 'C': '炮', 'P': '兵',
           'k': '将', 'a': '士', 'b': '象', 'n': '马', 'r': '车', 'c': '炮', 'p': '卒'}
_RED_NUM = '零一二三四五六七八九'
_BLACK_NUM = '０１２３４５６７８９'


def cn_notation(fen, mv):
    """cchess 的中文记谱（如 '炮二平五'；黑方用全角数字 '炮８平５'）。"""
    m = cchess.ChessBoard(fen).move(xy(mv[:2]), xy(mv[2:4]))
    assert m is not None, ('cchess 不认这步', fen, mv)
    return m.to_text()


def cn_text(fen, mv):
    """不经 cchess、按规范独立写出的中文记谱，只用来交叉核对 cn_notation()；写不了的局面返回 None。"""
    board, _ = board_of(fen)
    fr, to = mv[:2], mv[2:4]
    p = board[fr]
    red, kind = is_red(p), p.lower()
    (x1, y1), (x2, y2) = xy(fr), xy(to)
    num = _RED_NUM if red else _BLACK_NUM
    fnum = (lambda x: 9 - x) if red else (lambda x: x + 1)
    name = CN_NAME[p]
    head = name + num[fnum(x1)]
    if kind in 'rncp':
        same = [s for s, q in board.items() if q == p and s[0] == fr[0]]
        if len(same) >= 3:
            return None
        if kind == 'p':
            per_file = {}
            for s, q in board.items():
                if q == p:
                    per_file[s[0]] = per_file.get(s[0], 0) + 1
            if sum(v >= 2 for v in per_file.values()) >= 2:
                return None
        if len(same) == 2:
            oy = xy([s for s in same if s != fr][0])[1]
            head = ('前' if (y1 > oy if red else y1 < oy) else '后') + name
    dy = (y2 - y1) * (1 if red else -1)
    op = '平' if dy == 0 else ('进' if dy > 0 else '退')
    dest = abs(dy) if (kind in 'rcpk' and dy != 0) else fnum(x2)
    return head + op + num[dest]


def notation(fen, mv):
    """中文记谱（cchess）。它写不准的局面（多路兵、同一纵线三个同种子）在后面补上坐标。"""
    try:
        t = cn_notation(fen, mv)
        if cn_text(fen, mv) != t:
            t += '（%s）' % mv
        return t
    except Exception:
        return mv


# ---------------------------------------------------------------- 违规分类（boards.violation 的中国象棋分支）
VIOLATIONS = {
    'own': '目标格有己方子', 'shape': '不合这个子的走法', 'palace': '出九宫', 'river': '相过河',
    'eye': '塞象眼', 'leg': '蹩马腿', 'jump': '越子', 'screen0': '炮吃子没有炮架', 'screen2': '炮隔两个以上的子吃子',
    'pawn_side': '兵未过河就横走', 'pawn_back': '兵后退', 'facing': '走完帅将照面', 'self_check': '走完自己被将',
}


def _between(a, b):
    (x1, y1), (x2, y2) = xy(a), xy(b)
    dx, dy = x2 - x1, y2 - y1
    if not (dx == 0 or dy == 0 or abs(dx) == abs(dy)):
        return None
    n = max(abs(dx), abs(dy))
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    return [sq_of(x1 + sx * i, y1 + sy * i) for i in range(1, n)]


def _in_palace(sq, red):
    x, y = xy(sq)
    return 3 <= x <= 5 and (y <= 2 if red else y >= 7)


def violation(fen, mv):
    """行棋方走 mv 犯了哪条规则：返回 VIOLATIONS 里的键，合法返回 None。起点必须是行棋方的子。"""
    board, stm = board_of(fen)
    fr, to = mv[:2], mv[2:4]
    p = board.get(fr)
    assert p is not None and is_red(p) == (stm == 'w'), ('起点不是行棋方的子', fen, mv)
    red, kind = is_red(p), p.lower()
    tgt = board.get(to)
    if tgt is not None and is_red(tgt) == red:
        return 'own'
    (x1, y1), (x2, y2) = xy(fr), xy(to)
    dx, dy = x2 - x1, y2 - y1
    adx, ady = abs(dx), abs(dy)
    fwd = dy if red else -dy
    path = _between(fr, to)
    if kind == 'k':
        if adx + ady != 1:
            return 'shape'
        if not _in_palace(to, red):
            return 'palace'
    elif kind == 'a':
        if (adx, ady) != (1, 1):
            return 'shape'
        if not _in_palace(to, red):
            return 'palace'
    elif kind == 'b':
        if (adx, ady) != (2, 2):
            return 'shape'
        if (y2 >= 5) if red else (y2 <= 4):
            return 'river'
        if board.get(sq_of(x1 + dx // 2, y1 + dy // 2)):
            return 'eye'
    elif kind == 'n':
        if sorted((adx, ady)) != [1, 2]:
            return 'shape'
        leg = sq_of(x1 + (dx // 2 if adx == 2 else 0), y1 + (dy // 2 if ady == 2 else 0))
        if board.get(leg):
            return 'leg'
    elif kind == 'r':
        if dx and dy:
            return 'shape'
        if any(board.get(s) for s in path):
            return 'jump'
    elif kind == 'c':
        if dx and dy:
            return 'shape'
        n = sum(1 for s in path if board.get(s))
        if tgt is None and n:
            return 'jump'
        if tgt is not None and n == 0:
            return 'screen0'
        if tgt is not None and n >= 2:
            return 'screen2'
    elif kind == 'p':
        crossed = (y1 >= 5) if red else (y1 <= 4)
        if adx + ady != 1:
            return 'shape'
        if fwd < 0:
            return 'pawn_back'
        if dy == 0 and not crossed:
            return 'pawn_side'
    after = dict(board)
    del after[fr]
    after[to] = p
    ks = {q: s for s, q in after.items() if q in 'Kk'}
    if ks['K'][0] == ks['k'][0] and not any(after.get(s) for s in _between(ks['K'], ks['k'])):
        return 'facing'
    return None if mv in legal_fen(fen) else 'self_check'


# ---------------------------------------------------------------- 终局与禁着（play_xiangqi.py）
def rule_end(fens, fsf):
    """按 pyffish 看走完 fsf（从开局起的着法）后对局是否因重复或限着结束。fens 是每步走之前的局面再加上当前局面。
    返回 None，或 (赢家 'w' / 'b' / None, pyffish 给的分值)。"""
    fen = fens[-1]
    key = key_of(fen)
    if int(fen.split()[4]) < 100 and all(key_of(f) != key for f in fens[:-1]):
        return None     # 局面头一回出现、限着也没到，pyffish 不会判结束；免得每步都把整局重放一遍
    stm = fen.split()[1]
    for fn in (sf.is_immediate_game_end, sf.is_optional_game_end):
        end, v = fn(XQ, fens[0], fsf)
        if end:
            return (None if v == 0 else (stm if v > 0 else other(stm))), v
    return None


def _ending(fens, fsf):
    fen = fens[-1]
    stm = fen.split()[1]
    st = status(fen)
    if st in ('mate', 'stalemate'):
        return {'winner': other(stm), 'reason': '将死' if st == 'mate' else '困毙'}
    r = rule_end(fens, fsf)
    if r is None:
        return None
    winner = r[0]
    if winner is None:
        return {'winner': None, 'reason': '一百个半回合没有吃子，判和' if int(fen.split()[4]) >= 100
                else '同一局面出现三次，判和'}
    # 输的一方在这个循环里每步都将军，就是长将；否则是 pyffish 判的长捉（它的近似实现）
    loser = other(winner)
    key = key_of(fen)
    first = next(i for i, f in enumerate(fens) if key_of(f) == key)
    checks = [in_check_fen(fens[t + 1]) for t in range(first, len(fens) - 1) if fens[t].split()[1] == loser]
    return {'winner': winner, 'reason': '长将，判负' if checks and all(checks) else '长捉，判负'}


def _key_after(fen, mv):
    board, stm = board_of(fen)
    board[mv[2:]] = board.pop(mv[:2])
    return '%s %s - -' % (board_fen(board), other(stm))


def _banned(fens, fsf, moves):
    """moves 里走了会因长将 / 长捉当场判负的着法。先用局面键筛，剩下的再交给 pyffish。"""
    seen = {key_of(f) for f in fens}
    mover = fens[-1].split()[1]
    out = set()
    for mv in moves:
        if _key_after(fens[-1], mv) not in seen:
            continue
        f = to_fsf(mv)
        r = rule_end(fens + [sf.get_fen(XQ, fens[-1], [f])], fsf + [f])
        if r is not None and r[0] == other(mover):
            out.add(mv)
    return out


# ---------------------------------------------------------------- 约定的函数：状态
def start():
    """状态：fens 是起始局面加每步之后的局面，fsf 是对应的 Fairy-Stockfish 着法，moves 是 ICCS，record 是中文记谱。"""
    return {'fens': [START], 'fsf': [], 'moves': [], 'record': []}


def turn(st):
    return st['fens'][-1].split()[1]


def legal(st):
    return legal_fen(st['fens'][-1])


BANNED_REASON = '这步会形成长将（或长捉），按规则判负，不许走'


def banned(st, moves):
    """{着法: 不许走的原因}。步步都判负就不拦了（同网页双人对弈）。"""
    ban = _banned(st['fens'], st['fsf'], moves)
    if len(ban) == len(moves):
        return {}
    return {m: BANNED_REASON for m in ban}


def push(st, mv):
    fen = st['fens'][-1]
    f = to_fsf(mv)
    assert f in sf.legal_moves(XQ, fen, []), ('非法着法', fen, mv)
    st['record'].append(notation(fen, mv))
    st['moves'].append(mv)
    st['fsf'].append(f)
    st['fens'].append(sf.get_fen(XQ, fen, [f]))


def ending(st):
    """{'winner': 'w' / 'b' / None, 'reason': ...}，没结束返回 None。"""
    return _ending(st['fens'], st['fsf'])


def in_check(st):
    return in_check_fen(st['fens'][-1])


# ---------------------------------------------------------------- 着法解析（llm_duel.py）
_DIG = {c: str(i) for s in ('零一二三四五六七八九', '０１２３４５６７８９', '0123456789') for i, c in enumerate(s)}
_UNIFY = str.maketrans({'車': '车', '俥': '车', '馬': '马', '傌': '马', '砲': '炮', '帥': '帅', '將': '帅', '士': '仕',
                        '象': '相', '卒': '兵', '進': '进', '後': '后', '将': '帅'})
NAME = {'k': ('帅', '将'), 'a': ('仕', '士'), 'b': ('相', '象'), 'n': ('马', '马'), 'r': ('车', '车'),
        'c': ('炮', '炮'), 'p': ('兵', '卒')}


def cn_key(text):
    t = re.sub(r'[\s()（）\[\]【】「」*`]', '', text).translate(_UNIFY)
    return ''.join(_DIG.get(c, c) for c in t)


def check_iccs(fen, mv):
    board, stm = board_of(fen)
    fr, to = mv[:2], mv[2:]
    if fr == to:
        return mv, '起点和终点是同一格'
    p = board.get(fr)
    if p is None:
        return mv, '起点 %s 上没有棋子' % fr
    if is_red(p) != (stm == 'w'):
        return mv, '起点 %s 上是对方的%s' % (fr, NAME[p.lower()][0 if is_red(p) else 1])
    v = violation(fen, mv)
    if v:
        return mv, '%s从 %s 走到 %s 不合规：%s' % (NAME[p.lower()][0 if is_red(p) else 1], fr, to, VIOLATIONS[v])
    return mv, None


def resolve(fen, text):
    """把模型写的着法换成 ICCS。返回 (着法或 None, 非法 / 解析不出的原因或 None)。"""
    if text is None:
        return None, '回复里没有找到「着法: 」那一行'
    t = text.strip().strip('*`「」"\'。.').lower()
    m = re.match(r'^([a-i])\s*[-]?\s*(\d)\s*[-–—>→ ]*\s*([a-i])\s*(\d)', t)
    if m:
        return check_iccs(fen, '%s%s%s%s' % m.groups())
    key = cn_key(text)
    table = {cn_key(notation(fen, mv)): mv for mv in legal_fen(fen)}
    for k, mv in table.items():
        if key.startswith(k):
            return mv, None
    return None, '既不是 ICCS 坐标，也对不上任何一步合法着法的中文记谱'


def parse(st, text):
    """约定的解析函数：(着法或 None, 不合法原因或 None)。禁着（长将长捉）由循环按 banned() 另查。"""
    fen = st['fens'][-1]
    mv, why = resolve(fen, text)
    if mv and not why and mv not in legal_fen(fen):
        why = '走完自己的帅（将）被将军或照面'   # violation 查不出的兜底
    return mv, why


# ---------------------------------------------------------------- 局面呈现（llm_duel.py）
RED_CH = {'K': '帅', 'A': '仕', 'B': '相', 'N': '马', 'R': '车', 'C': '炮', 'P': '兵'}
BLACK_CH = {'k': '将', 'a': '士', 'b': '象', 'n': '馬', 'r': '車', 'c': '砲', 'p': '卒'}  # 黑方马车炮用繁体，和红方不同字
EMPTY = '＋'
RED_FILE = '九八七六五四三二一'
BLACK_FILE = '１２３４５６７８９'
LEGEND = '大写字母是红方，小写字母是黑方；K 帅/将，A 仕/士，B 相/象，N 马，R 车，C 炮，P 兵/卒；点是空格'


def view_grid(board):
    lines = ['棋盘（上方是黑方，下方是红方；每行开头是横线号 0–9，列头是纵线 a–i）：',
             '   ' + ' '.join(BLACK_FILE) + '   ← 黑方记谱的纵线号',
             '   ' + '  '.join('abcdefghi')]
    for y in range(9, -1, -1):
        cells = [board.get(sq_of(x, y)) for x in range(9)]
        row = ' '.join((RED_CH.get(p) or BLACK_CH.get(p)) if p else EMPTY for p in cells)
        lines.append('%d  %s' % (y, row))
        if y == 5:
            lines.append('   ～～～～ 楚河 汉界 ～～～～')
    lines.append('   ' + '  '.join('abcdefghi'))
    lines.append('   ' + ' '.join(RED_FILE) + '   ← 红方记谱的纵线号')
    lines.append('图例：红方 帅 仕 相 马 车 炮 兵；黑方 将 士 象 馬 車 砲 卒（黑方的马车炮用繁体字，以示区分）；%s 是空点。' % EMPTY)
    return '\n'.join(lines)


def view_pieces(board):
    out = ['子力清单（ICCS 坐标）：']
    for side, red in (('红方', True), ('黑方', False)):
        parts, n = [], 0
        for letter in 'KABRNCP':
            p = letter if red else letter.lower()
            sqs = sorted((s for s, q in board.items() if q == p), key=lambda s: (s[0], s[1]))
            if sqs:
                n += len(sqs)
                parts.append('%s %s' % (NAME[letter.lower()][0 if red else 1], ' '.join(sqs)))
        out.append('%s（%d 子）：%s' % (side, n, '；'.join(parts)))
    return '\n'.join(out)


def _label(p):
    return ('红' if is_red(p) else '黑') + CN_NAME[p]


def view_cells(board):
    """boards.state(..., 'cells') 的格子表：只列有子的格，按横线从上到下、纵线从左到右。"""
    order = [sq_of(x, y) for y in range(9, -1, -1) for x in range(9)]
    return '格子表：' + json.dumps({s: _label(board[s]) for s in order if s in board}, ensure_ascii=False)


def view_board(board):
    rows = []
    for y in range(9, -1, -1):
        rows.append('%d %s' % (y, ' '.join(board.get(sq_of(x, y), '.') for x in range(9))))
    rows.append('  ' + ' '.join('abcdefghi'))
    return '字符棋盘（%s）：\n%s' % (LEGEND, '\n'.join(rows))


VIEWS = {'grid': lambda fen, bd: view_grid(bd), 'pieces': lambda fen, bd: view_pieces(bd),
         'fen': lambda fen, bd: 'FEN：' + fen, 'cells': lambda fen, bd: view_cells(bd),
         'board': lambda fen, bd: view_board(bd)}


def history_text(st, n):
    rec = st['record']
    if n == 0 or not rec:
        return '' if n == 0 else '着法记录：（开局，还没有着法）'
    first = 0 if n < 0 else max(0, len(rec) - n)
    first -= first % 2                               # 从红方那步起，按回合成行
    lines = []
    for i in range(first, len(rec), 2):
        row = '%d. %s（%s）' % (i // 2 + 1, rec[i], st['moves'][i])
        if i + 1 < len(rec):
            row += '　%s（%s）' % (rec[i + 1], st['moves'][i + 1])
        lines.append(row)
    head = '着法记录（中文记谱，括号里是 ICCS）' + ('' if first == 0 else '，只列最近 %d 个半回合，更早的省略' % (len(rec) - first))
    return head + '：\n' + '\n'.join(lines)


RECITE_ASK = ('回答时先复述当前局面，再思考和走棋。复述写 10 行，从横线 9 写到横线 0：每行开头是横线号，后面 9 个字依次对应纵线 a 到 i，'
              '用和上面棋盘相同的字（红方 帅仕相马车炮兵，黑方 将士象馬車砲卒），空点写＋。')


def render(st, sc):
    """本步提示的局面部分（不含最后「请走一步」那句，那句由循环按思考延续方式补）。"""
    fen = st['fens'][-1]
    board, stm = board_of(fen)
    ply = len(st['moves'])
    head = ['第 %d 回合（已走 %d 个半回合），轮到你（%s）走。' % (ply // 2 + 1, ply, SIDES[stm]),
            '你现在正被将军！' if in_check_fen(fen) else '你现在没有被将军。']
    if st['moves']:
        head.append('对方刚走：%s（%s）' % (st['record'][-1], st['moves'][-1]))
    parts = ['\n'.join(head)] + [VIEWS[v](fen, board) for v in sc['view']]
    h = history_text(st, sc['history'])
    if h:
        parts.append(h)
    if sc['legal'] == 'list':
        moves = legal_fen(fen)
        parts.append('你的全部合法着法（共 %d 个）：%s' % (
            len(moves), '、'.join('%s(%s)' % (notation(fen, m), m) for m in moves)))
    if sc.get('attackmap') == 'on':
        parts.append(attack_map(fen))
    if sc['recite'] == 'on':
        parts.append(RECITE_ASK)
    return '\n\n'.join(parts)


def _flip(fen):
    f = fen.split()
    f[1] = other(f[1])
    return ' '.join(f)


def attack_map(fen):
    """局面题 attackmap 档（诊断用，待用户拍板，见 design.md）：对方每个子现在能吃到我哪些子、我哪些子没有保护。
    能吃到：把行棋方换成对方后，pyffish 给出的合法吃子着法（炮架、马腿、象眼、照面都由 pyffish 判）。
    有保护：假设对方一个车站到这个格上，我方有合法着法能吃回来。帅（将）不列。"""
    board, stm = board_of(fen)
    me_red = stm == 'w'
    lines = ['攻击关系（程序按规则算出，只列事实）：', '对方现在能吃到你的子：']
    caps = {}
    for mv in legal_fen(_flip(fen)):
        tgt = board.get(mv[2:4])
        if tgt and is_red(tgt) == me_red and tgt.lower() != 'k':
            caps.setdefault(mv[:2], []).append(mv)
    for fr in sorted(caps):
        lines.append('- %s %s 能吃：%s' % (_label(board[fr]), fr, '、'.join(
            '%s %s（%s）' % (_label(board[m[2:4]]), m[2:4], m) for m in sorted(caps[fr]))))
    if not caps:
        lines.append('- 无')
    loose = []
    for sq, p in sorted(board.items()):
        if is_red(p) != me_red or p.lower() == 'k':
            continue
        b2 = dict(board)
        b2[sq] = 'r' if me_red else 'R'
        f2 = '%s %s - - 0 1' % (board_fen(b2), stm)
        try:
            ok = any(m[2:4] == sq for m in legal_fen(f2))
        except Exception:
            ok = False
        if not ok:
            loose.append('%s %s' % (_label(p), sq))
    lines.append('你没有保护的子：' + ('、'.join(loose) if loose else '无'))
    return '\n'.join(lines)


def last_move_text(st):
    return '%s（%s）' % (st['record'][-1], st['moves'][-1])


# ---------------------------------------------------------------- 提示（llm_duel.py）
SELFCHECK = ('每步落子前先自查：\n'
             '1. 对方上一步之后，对方下一步能吃我什么子、能不能将我、能不能将死我？\n'
             '2. 我打算走的这步走完以后，会不会白送子？会不会被对方将军、将死，或者把自己的帅（将）的出路堵死？\n'
             '3. 这步是否合规：马腿、象眼、炮架、九宫、兵是否过河、帅将是否照面。\n'
             '自查没问题再落子；有问题就换一步再查。')


def system_prompt(side, sc, memory_text):
    s = ['你在下一盘中国象棋，执%s。对手是另一位棋手。目标是赢棋。' % SIDES[side],
         '规则按标准中国象棋：将死或困毙对方为胜；长将判负（这类着法会被当作不合规退回）；同一局面出现三次且不属于长将、长捉判和；'
         '连续一百个半回合没有吃子判和；满 %d 个半回合仍未分胜负判和。' % sc['max_plies'],
         '坐标用 ICCS：纵线 a 到 i 从红方左手边数起，横线 0 到 9 从红方底线数起；一步棋写成起点加终点，例如 h2e2（红炮二平五）。',
         '每一步我都会给你当前局面。' + memory_text]
    if sc['selfcheck'] == 'on':
        s.append(SELFCHECK)
    s.append('回答格式：请用中文回答。可以先写简短的思路，最后一行只写「着法: 」加着法，用 ICCS 坐标（例如 着法: h2e2），'
             '也可以用中文记谱（例如 着法: 炮二平五）。')
    if sc.get('threats') == 'on':
        s.append(THREATS_ASK)
    return '\n\n'.join(s)


# 局面题 threats 档（plan-batch2 块 A）：先列走后对方的吃子 / 将军着法，程序事后按真实局面打分（quiz.threat_score），不回灌
THREATS_HEAD = '走后威胁'
THREATS_ASK = ('在最后一行「着法: 」之前，先写一个以「%s:」开头的清单：假设你打算走的这步已经走了，列出对方下一步所有能吃掉你的子的着法、'
               '所有能将你的着法，每行一着，用 ICCS 坐标写对方那步的起点加终点（例如 b7b0），后面可以用括号注明吃什么或将军；'
               '一着都没有就只写一行「无」。清单写完，最后一行照常写「着法: 」加你的着法。' % THREATS_HEAD)


# ---------------------------------------------------------------- 复述打分（llm_duel.py）
_CELL = set(RED_CH.values()) | set(BLACK_CH.values()) | {EMPTY, '马', '车', '炮'}


def recite_score(st, reply):
    """回复里复述的网格和真实局面逐格比：每条横线取回复里第一行能读出 9 个格子的；没找到的横线整行算错。"""
    board = board_of(st['fens'][-1])[0]
    rows = {}
    for line in (reply or '').splitlines():
        m = re.match(r'^[\s`|>*]*(\d)[\s|:：.]+(.*)$', line)
        if not m or int(m[1]) in rows:
            continue
        cells = [c for c in m[2] if c in _CELL]
        if len(cells) == 9 and len(re.sub(r'[\s|]', '', m[2])) <= 12:
            rows[int(m[1])] = cells
    ok = 0
    for y in range(10):
        for x in range(9):
            p = board.get(sq_of(x, y))
            want = (RED_CH.get(p) or BLACK_CH.get(p)) if p else EMPTY
            ok += y in rows and rows[y][x] == want
    return {'cells_ok': ok, 'cells': 90, 'rows_found': len(rows), 'all_ok': ok == 90}


# ---------------------------------------------------------------- 棋谱
def exports(st, cfg, end, summary_lines):
    res = ('%s胜' % SIDES[end['winner']] if end['winner'] else '和棋') + '（%s）' % end['reason']
    lines = ['中国象棋 · 模型对弈 · %s' % cfg['tag'],
             '红方：%s　黑方：%s' % (cfg['players']['w'], cfg['players']['b']),
             '结果：%s，共 %d 个半回合' % (res, len(st['moves'])), '']
    rec = st['record']
    for i in range(0, len(rec), 2):
        lines.append('%d. %s%s' % (i // 2 + 1, rec[i], '　' + rec[i + 1] if i + 1 < len(rec) else ''))
    lines += ['', 'ICCS：' + ' '.join(st['moves']), ''] + summary_lines
    return {'record.txt': '\n'.join(lines) + '\n'}


# ---------------------------------------------------------------- 引擎对手
def engine_spec(desc):
    """'fsf'、'fsf:nodes=200'、'fsf:depth=2'、'fsf:movetime=100'（毫秒）。不写参数时 nodes=1000。
    本机 Fairy-Stockfish 14.0.1；UCI_Elo 的刻度是国际象棋的，在中国象棋上只当相对旋钮，所以只给节点数 / 深度 / 时间。"""
    name, _, arg = desc.partition(':')
    if name != 'fsf':
        raise ValueError('中国象棋引擎只认 fsf（Fairy-Stockfish），收到 %r' % desc)
    k, _, v = (arg or 'nodes=1000').partition('=')
    if k not in ('nodes', 'depth', 'movetime') or not v.isdigit():
        raise ValueError('fsf 的参数写成 nodes=N / depth=N / movetime=毫秒，收到 %r' % arg)
    path = os.environ.get('FAIRY_STOCKFISH') or shutil.which('fairy-stockfish') or '/opt/homebrew/bin/fairy-stockfish'
    return {'name': desc, 'cmd': [path], 'go': 'go %s %s' % (k, v),
            'options': [('UCI_Variant', 'xiangqi'), ('Threads', '1'), ('Hash', '16')]}


to_engine = to_fsf
from_engine = from_fsf
