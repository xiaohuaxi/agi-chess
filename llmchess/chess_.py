"""国际象棋模块：规则、终局与自动申诉、着法解析、局面呈现、提示、棋谱、引擎参数。

规则判定一律用 python-chess 1.11.2，不自己改棋规；坐标着法的违规分类照搬 jev-study boards.violation 的国际象棋分支。
终局口径（design.md P16，已拍板）：将死判负；逼和、子力不足、五次重复、七十五回合判和；三次重复、五十回合由程序
替棋手自动申诉，按终局判和。注意 python-chess 的 outcome(claim_draw=True) 在「走一步就能凑成三次重复 / 五十回合」
时也算可申诉，会提前一个半回合结束，所以这里只在局面**已经**出现三次、计数**已经**到 100 个半回合时才判。
"""
import os, re, shutil

import chess
import chess.pgn

from . import memory, records

SIDES = {'w': '白方', 'b': '黑方'}
ALL_VIEW = 'fen,ascii'            # show=all：FEN + 字母棋盘（国际象棋默认 view 里本来没有子力清单）
# 呈现方式（show 档）→ view。整盘对局（cli）和局面题（quiz）共用。
SHOWS = {'all': ALL_VIEW, 'board': 'ascii', 'pieces': 'pieces', 'fen': 'fen'}
DEFAULT_SHOW = 'all'              # 第 4P2 批复核后保留现状：字母棋盘缺易位权和吃过路兵信息，不按简洁换
RECITE = False                    # 复述格式和打分还没有
START = chess.STARTING_FEN
MAIA_DIR = os.path.expanduser('~/.local/share/maia')

PIECE_ZH = {'k': '王', 'q': '后', 'r': '车', 'b': '象', 'n': '马', 'p': '兵'}


def _zh(p):
    return ('白' if p.isupper() else '黑') + PIECE_ZH[p.lower()]


# ---------------------------------------------------------------- 约定的函数：状态
def start():
    """状态：board 是 python-chess 的棋盘（带着法栈），fens 是起始局面加每步之后的局面，moves 是 UCI，record 是 SAN。"""
    return {'board': chess.Board(), 'fens': [START], 'moves': [], 'record': []}


def turn(st):
    return 'w' if st['board'].turn == chess.WHITE else 'b'


def legal(st):
    return sorted(m.uci() for m in st['board'].legal_moves)


def banned(st, moves):
    return {}


def push(st, mv):
    b = st['board']
    m = chess.Move.from_uci(mv)
    assert m in b.legal_moves, ('非法着法', b.fen(), mv)
    st['record'].append(b.san(m))
    b.push(m)
    st['moves'].append(mv)
    st['fens'].append(b.fen())


TERMINATION = {
    chess.Termination.CHECKMATE: '将死',
    chess.Termination.STALEMATE: '逼和，判和',
    chess.Termination.INSUFFICIENT_MATERIAL: '双方子力都不足以将死，判和',
    chess.Termination.SEVENTYFIVE_MOVES: '七十五回合没有吃子和兵的走动，判和',
    chess.Termination.FIVEFOLD_REPETITION: '同一局面出现五次，判和',
}


def ending(st):
    """{'winner': 'w' / 'b' / None, 'reason': ...}，没结束返回 None。"""
    b = st['board']
    o = b.outcome()                               # 将死、逼和、子力不足、五次重复、七十五回合
    if o is not None:
        return {'winner': None if o.winner is None else ('w' if o.winner else 'b'), 'reason': TERMINATION[o.termination]}
    if b.is_repetition(3):
        return {'winner': None, 'reason': '同一局面出现三次，程序替棋手申诉，判和'}
    if b.halfmove_clock >= 100:
        return {'winner': None, 'reason': '五十回合没有吃子和兵的走动，程序替棋手申诉，判和'}
    return None


def in_check(st):
    return st['board'].is_check()


# ---------------------------------------------------------------- 违规分类（boards.violation 的国际象棋分支）
VIOLATIONS = {
    'own': '目标格有己方子', 'shape': '不合这个子的走法', 'jump': '越子', 'pawn_block': '兵前方有子',
    'castle': '不满足易位条件', 'pin': '被牵制的子离开牵制线', 'king_attacked': '王走进被攻击的格', 'self_check': '走完自己被将',
    'promo': '兵走到底线要写明升变成什么（如 e7e8q）', 'no_promo': '只有兵走到底线才能写升变',
}


def _xy(sq):
    return 'abcdefgh'.index(sq[0]), int(sq[1])


def _sq(x, y):
    return 'abcdefgh'[x] + str(y)


def _between(a, b):
    (x1, y1), (x2, y2) = _xy(a), _xy(b)
    dx, dy = x2 - x1, y2 - y1
    if not (dx == 0 or dy == 0 or abs(dx) == abs(dy)):
        return None
    n = max(abs(dx), abs(dy))
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    return [_sq(x1 + sx * i, y1 + sy * i) for i in range(1, n)]


def _pieces(b):
    return {chess.square_name(s): p.symbol() for s, p in b.piece_map().items()}


def violation(b, mv):
    """行棋方走 mv（UCI）犯了哪条规则：返回 VIOLATIONS 里的键，合法返回 None。起点必须是行棋方的子。"""
    board = _pieces(b)
    fr, to, promo = mv[:2], mv[2:4], (mv[4:] or None)
    p = board.get(fr)
    white = b.turn == chess.WHITE
    assert p is not None and p.isupper() == white, ('起点不是行棋方的子', b.fen(), mv)
    kind = p.lower()
    tgt = board.get(to)
    if tgt is not None and tgt.isupper() == white:
        return 'own'
    (x1, y1), (x2, y2) = _xy(fr), _xy(to)
    dx, dy = x2 - x1, y2 - y1
    adx, ady = abs(dx), abs(dy)
    fwd = dy if white else -dy
    path = _between(fr, to)
    legal_ucis = {m.uci() for m in b.legal_moves}
    if promo and kind != 'p':
        return 'no_promo'
    if kind == 'n':
        if sorted((adx, ady)) != [1, 2]:
            return 'shape'
    elif kind in 'brq':
        ok = {'b': adx == ady, 'r': dx == 0 or dy == 0, 'q': adx == ady or dx == 0 or dy == 0}[kind]
        if not ok or (adx == 0 and ady == 0):
            return 'shape'
        if any(board.get(s) for s in path):
            return 'jump'
    elif kind == 'k':
        if adx == 2 and dy == 0 and y1 == (1 if white else 8) and x1 == 4:
            return None if mv in legal_ucis else 'castle'
        if max(adx, ady) != 1:
            return 'shape'
    elif kind == 'p':
        start_rank = 2 if white else 7
        if dx == 0 and fwd == 1:
            if tgt is not None:
                return 'pawn_block'
        elif dx == 0 and fwd == 2 and y1 == start_rank:
            if tgt is not None or board.get(_sq(x1, y1 + (1 if white else -1))):
                return 'pawn_block'
        elif adx == 1 and fwd == 1:
            ep = b.ep_square
            if tgt is None and (ep is None or chess.square_name(ep) != to):
                return 'shape'
        else:
            return 'shape'
        last = y2 == (8 if white else 1)
        if last and not promo:
            return 'promo'
        if promo and not last:
            return 'no_promo'
    if mv in legal_ucis:
        return None
    if kind == 'k':
        return 'king_attacked'
    if b.is_pinned(b.turn, chess.parse_square(fr)) and not b.is_check():
        return 'pin'
    return 'self_check'


def check_uci(b, mv):
    fr, to = mv[:2], mv[2:4]
    if fr == to:
        return mv, '起点和终点是同一格'
    p = b.piece_at(chess.parse_square(fr))
    if p is None:
        return mv, '起点 %s 上没有棋子' % fr
    if p.color != b.turn:
        return mv, '起点 %s 上是对方的%s' % (fr, _zh(p.symbol()))
    v = violation(b, mv)
    if v:
        return mv, '%s从 %s 走到 %s 不合规：%s' % (_zh(p.symbol()), fr, to, VIOLATIONS[v])
    return mv, None


# ---------------------------------------------------------------- 着法解析
_UCI = re.compile(r'^([a-h])\s*([1-8])\s*[-–—x:>→ ]*\s*([a-h])\s*([1-8])\s*=?\s*([qrbn])?')
_SAN = re.compile(r'^([KQRBN])?([a-h])?([1-8])?x?([a-h][1-8])(?:=?([QRBN]))?$')


def _san_reason(b, t):
    """SAN 对不上合法着法时说出原因：按写法找出能对上的己方子，逐个用 violation 查。"""
    if t.startswith('O-O'):
        return '现在不能这样易位（王或车走动过、中间有子、王正被将或要经过被攻击的格）'
    m = _SAN.match(t)
    if not m:
        return '既不是 UCI 坐标（如 e2e4），也不是合法的 SAN 写法（如 Nf3、O-O）'
    kind = (m[1] or 'P').lower()
    to, promo = m[4], (m[5] or '').lower()
    white = b.turn == chess.WHITE
    cands = [s for s, p in _pieces(b).items() if p.lower() == kind and p.isupper() == white
             and (not m[2] or s[0] == m[2]) and (not m[3] or s[1] == m[3])]
    name = ('白' if white else '黑') + PIECE_ZH[kind]
    if not cands:
        return '棋盘上没有符合这个写法的%s' % name
    reasons = []
    for s in sorted(cands):
        if s == to:
            continue
        mv = s + to + promo
        v = violation(b, mv)
        reasons.append('%s 的%s：%s' % (s, name, VIOLATIONS[v] if v else '可以走，但写法有歧义或不规范'))
    if not reasons:
        return '棋盘上没有能走到 %s 的%s' % (to, name)
    return '没有哪个%s能合法走到 %s（%s）' % (name, to, '；'.join(reasons))


def parse(st, text):
    """(着法或 None, 不合法原因或 None)。认 UCI（e2e4、e7e8q、易位写 e1g1）和 SAN（Nf3、exd5、O-O、e8=Q）。"""
    if text is None:
        return None, '回复里没有找到「着法: 」那一行'
    b = st['board']
    t = text.strip().strip('*`「」"\'。.，,').strip()
    # 大写棋子字母或易位开头的按 SAN 读（B2c3 是 SAN，不能转小写当成坐标 b2c3），其余先试 UCI
    m = None if re.match(r'^[KQRBNO0]', t) else _UCI.match(t.lower())
    if m:
        mv = '%s%s%s%s%s' % (m[1], m[2], m[3], m[4], m[5] or '')
        return check_uci(b, mv)
    san = re.sub(r'[+#!?]+$', '', t.split()[0] if t.split() else t).replace('0-0-0', 'O-O-O').replace('0-0', 'O-O')
    try:
        mv = b.parse_san(san)
        if mv not in b.legal_moves:               # parse_san 会放过空着（--、0000 之类）
            return None, '「%s」不是一步合法着法（空着不算）' % san
        return mv.uci(), None
    except chess.AmbiguousMoveError:
        return None, '「%s」有两个以上的子都能走，要写明是哪一个（如 Nbd2）' % san
    except (chess.IllegalMoveError, chess.InvalidMoveError, ValueError):
        return None, _san_reason(b, san)


# ---------------------------------------------------------------- 局面呈现
LEGEND = '大写字母是白方，小写字母是黑方；K 王，Q 后，R 车，B 象，N 马，P 兵；点是空格'


def view_ascii(b):
    rows = []
    for y in range(8, 0, -1):
        rows.append('%d %s' % (y, ' '.join((b.piece_at(chess.square(x, y - 1)) or '.').__str__() for x in range(8))))
    rows.append('  ' + ' '.join('abcdefgh'))
    return '字符棋盘（上方是黑方，下方是白方；%s）：\n%s' % (LEGEND, '\n'.join(rows))


def view_pieces(b, count=True):
    out = ['子力清单：']
    board = _pieces(b)
    for side, white in (('白方', True), ('黑方', False)):
        parts, n = [], 0
        for letter in 'KQRBNP':
            p = letter if white else letter.lower()
            sqs = sorted(s for s, q in board.items() if q == p)
            if sqs:
                n += len(sqs)
                parts.append('%s %s' % (PIECE_ZH[letter.lower()], ' '.join(sqs)))
        out.append('%s（%d 子）：%s' % (side, n, '；'.join(parts)) if count else '%s：%s' % (side, '；'.join(parts)))
    return '\n'.join(out)


def _movetext(st, first=0):
    parts = []
    for i in range(first, len(st['record'])):
        if i % 2 == 0:
            parts.append('%d. %s' % (i // 2 + 1, st['record'][i]))
        elif i == first:
            parts.append('%d... %s' % (i // 2 + 1, st['record'][i]))
        else:
            parts.append(st['record'][i])
    return ' '.join(parts)


VIEWS = {'fen': lambda st: 'FEN：' + st['board'].fen(), 'ascii': lambda st: view_ascii(st['board']),
         'pieces': lambda st: view_pieces(st['board']),
         'pgn': lambda st: 'PGN 着法：' + (_movetext(st) or '（开局，还没有着法）')}


def history_text(st, n):
    rec = st['record']
    if n == 0 or not rec:
        return '' if n == 0 else '着法记录：（开局，还没有着法）'
    first = 0 if n < 0 else max(0, len(rec) - n)
    first -= first % 2
    lines = []
    for i in range(first, len(rec), 2):
        row = '%d. %s（%s）' % (i // 2 + 1, rec[i], st['moves'][i])
        if i + 1 < len(rec):
            row += '　%s（%s）' % (rec[i + 1], st['moves'][i + 1])
        lines.append(row)
    head = '着法记录（SAN，括号里是 UCI）' + ('' if first == 0 else '，只列最近 %d 个半回合，更早的省略' % (len(rec) - first))
    return head + '：\n' + '\n'.join(lines)


def render(st, sc, fresh=True):
    """本步提示的局面部分（不含最后「请走一步」那句，那句由循环按思考延续方式补）。
    新协议（sc['protocol'] == 'real'）走 render_real；fresh 只对它有用，见那里。"""
    if sc.get('protocol') == 'real':
        return render_real(st, sc, fresh)
    b = st['board']
    ply = len(st['moves'])
    head = ['第 %d 回合（已走 %d 个半回合），轮到你（%s）走。' % (ply // 2 + 1, ply, SIDES[turn(st)]),
            '你现在正被将军！' if b.is_check() else '你现在没有被将军。']
    if st['moves']:
        head.append('对方刚走：%s' % last_move_text(st))
    parts = ['\n'.join(head)] + [VIEWS[v](st) for v in sc['view']]
    h = history_text(st, sc['history'])
    if h:
        parts.append(h)
    if sc['legal'] == 'list':
        ms = sorted(b.legal_moves, key=lambda m: m.uci())
        parts.append('你的全部合法着法（共 %d 个）：%s' % (len(ms), '、'.join('%s(%s)' % (b.san(m), m.uci()) for m in ms)))
    if sc.get('attackmap') == 'on':
        parts.append(attack_map(b))
    return '\n\n'.join(parts)


def render_real(st, sc, fresh):
    """「模型就是真实棋手」：只给轮到谁、对方上一步、局面（默认 FEN + 字母棋盘），不说是否被将军。
    对方上一步和着法记录只写 UCI 坐标：SAN 带「+」「#」，等于替它报将军。着法记录只在新会话的第一条给一次（fresh）。"""
    b = st['board']
    ply = len(st['moves'])
    head = ['第 %d 回合（已走 %d 个半回合），轮到你（%s）走。' % (ply // 2 + 1, ply, SIDES[turn(st)])]
    if st['moves']:
        head.append('对方刚走：%s' % st['moves'][-1])
    parts = ['\n'.join(head)] + [view_pieces(b, count=False) if v == 'pieces' else VIEWS[v](st) for v in sc['view']]
    if fresh and st['moves'] and sc['history'] != 0:
        first = 0 if sc['history'] < 0 else max(0, ply - sc['history'])
        first -= first % 2
        rows = ['%d. %s' % (i // 2 + 1, ' '.join(st['moves'][i:i + 2])) for i in range(first, ply, 2)]
        parts.append('此前已走着法（UCI）' + ('' if first == 0 else '，只列最近 %d 个半回合' % (ply - first)) + '：\n' +
                     '\n'.join(rows))
    if sc['legal'] == 'list':
        ms = sorted(b.legal_moves, key=lambda m: m.uci())
        parts.append('你的全部合法着法（共 %d 个）：%s' % (len(ms), '、'.join('%s(%s)' % (b.san(m), m.uci()) for m in ms)))
    if sc.get('attackmap') == 'on':
        parts.append(attack_map(b))
    return '\n\n'.join(parts)


def feedback(text, why):
    """新协议下告诉棋手的非法原因类别（memory.FEEDBACK 的键）：写法问题照实说，其余一律「不合法」。"""
    if text is None:
        return 'no_move'
    if why.startswith('既不是 UCI'):
        return 'unreadable'
    if '有两个以上的子都能走' in why:
        return 'ambiguous'
    return 'illegal'


def attack_map(b):
    """局面题 attackmap 档（诊断用，待用户拍板，见 design.md）：对方每个子现在能吃到我哪些子、我哪些子没有保护。
    按 python-chess 的攻击关系（board.attackers）算，不管牵制；王不列。"""
    me = b.turn
    lines = ['攻击关系（程序按规则算出，只列事实）：', '对方现在能吃到你的子：']
    caps = {}
    for sq, p in b.piece_map().items():
        if p.color != me or p.piece_type == chess.KING:
            continue
        for a in b.attackers(not me, sq):
            caps.setdefault(a, []).append(sq)
    for a in sorted(caps):
        lines.append('- %s %s 能吃：%s' % (_zh(b.piece_at(a).symbol()), chess.square_name(a), '、'.join(
            '%s %s' % (_zh(b.piece_at(s).symbol()), chess.square_name(s)) for s in sorted(caps[a]))))
    if not caps:
        lines.append('- 无')
    loose = ['%s %s' % (_zh(p.symbol()), chess.square_name(sq)) for sq, p in sorted(b.piece_map().items())
             if p.color == me and p.piece_type != chess.KING and not b.attackers(me, sq)]
    lines.append('你没有保护的子：' + ('、'.join(loose) if loose else '无'))
    return '\n'.join(lines)


def last_move_text(st):
    return '%s（%s）' % (st['record'][-1], st['moves'][-1])


# ---------------------------------------------------------------- 提示
SELFCHECK = ('每步落子前先自查：\n'
             '1. 对方上一步之后，对方下一步能吃我什么子、能不能将我、能不能将死我？\n'
             '2. 我打算走的这步走完以后，会不会白送子？会不会被对方将军、将死？\n'
             '3. 这步是否合规：路线上有没有子挡着、兵的走法和吃过路兵、易位条件、走完自己的王是否被将。\n'
             '自查没问题再落子；有问题就换一步再查。')


def system_prompt(side, sc, memory_text):
    if sc.get('protocol') == 'real':
        return system_real(side, sc, memory_text)
    s = ['你在下一盘国际象棋，执%s。对手是另一位棋手。目标是赢棋。' % SIDES[side],
         '规则按标准国际象棋：将死对方为胜；逼和、双方子力都不足以将死判和；同一局面出现三次、或五十回合没有吃子和兵的走动，'
         '程序自动替你们申诉判和；满 %d 个半回合仍未分胜负判和。' % sc['max_plies'],
         '坐标：纵线 a 到 h 从白方左手边数起，横线 1 到 8 从白方底线数起。',
         '每一步我都会给你当前局面。' + memory_text]
    if sc['selfcheck'] == 'on':
        s.append(SELFCHECK)
    s.append('回答格式：请用中文回答。可以先写简短的思路，最后一行只写「着法: 」加着法，用 UCI 坐标写起点加终点（例如 着法: e2e4；'
             '升变在后面加棋子字母，如 e7e8q；易位写王的走法，如 e1g1），也可以用 SAN（例如 着法: Nf3、着法: O-O）。')
    if sc.get('threats') == 'on':
        s.append(THREATS_ASK)
    return '\n\n'.join(s)


ILLEGAL_RULE = '每步给出着法后，着法不合法或认不出会告诉你，由你重新选；一步里连续 %d 次都没给出合法着法判负。'


def system_real(side, sc, memory_text):
    """「模型就是真实棋手」的系统提示（design.md 第九节），和 xiangqi.system_real 同构。"""
    s = ['你在下一盘国际象棋，执%s。对手是另一位棋手。目标是赢棋。' % SIDES[side],
         '规则按标准国际象棋：将死对方为胜；逼和、双方子力都不足以将死判和；同一局面出现三次、或五十回合没有吃子和兵的走动，'
         '程序自动替你们申诉判和；满 %d 个半回合仍未分胜负判和。' % sc['max_plies'] + ILLEGAL_RULE % (sc.get('retries', 3) + 1),
         '坐标：纵线 a 到 h 从白方左手边数起，横线 1 到 8 从白方底线数起。',
         memory_text]
    if sc['selfcheck'] == 'on':
        s.append(SELFCHECK)
    s.append('回答格式：' + memory.answer_lead(sc) + '用 UCI 坐标写起点加终点（例如 着法: e2e4；升变在后面加棋子字母，'
             '如 e7e8q；易位写王的走法，如 e1g1），也可以用 SAN（例如 着法: Nf3、着法: O-O）。')
    if sc.get('threats') == 'on':
        s.append(THREATS_ASK)
    return '\n\n'.join(s)


# 局面题 threats 档（plan-batch2 块 A）：先列走后对方的吃子 / 将军着法，程序事后按真实局面打分（quiz.threat_score），不回灌
THREATS_HEAD = '走后威胁'
THREATS_ASK = ('在最后一行「着法: 」之前，先写一个以「%s:」开头的清单：假设你打算走的这步已经走了，列出对方下一步所有能吃掉你的子的着法、'
               '所有能将你的着法，每行一着，用 UCI 坐标写对方那步的起点加终点（例如 d8d1），后面可以用括号注明吃什么或将军；'
               '一着都没有就只写一行「无」。清单写完，最后一行照常写「着法: 」加你的着法。' % THREATS_HEAD)


def recite_score(st, reply):
    raise NotImplementedError('国际象棋还没有复述打分（cli 会拦下 recite=on）')


# ---------------------------------------------------------------- 棋谱
def exports(st, cfg, end, summary_lines, meta=None):
    """meta：{半回合号: 元信息}（records.move_meta），写进 PGN 每步后的评注（records.meta_comment）。"""
    res = ('%s胜' % SIDES[end['winner']] if end['winner'] else '和棋') + '（%s）' % end['reason']
    lines = ['国际象棋 · 模型对弈 · %s' % cfg['tag'],
             '白方：%s　黑方：%s' % (cfg['players']['w'], cfg['players']['b']),
             '结果：%s，共 %d 个半回合' % (res, len(st['moves'])), '', _movetext(st), '',
             'UCI：' + ' '.join(st['moves']), ''] + summary_lines
    g = chess.pgn.Game.from_board(st['board'])
    g.headers['Event'] = 'llm-chess %s' % cfg['tag']
    g.headers['White'], g.headers['Black'] = cfg['players']['w'], cfg['players']['b']
    g.headers['Result'] = '1-0' if end['winner'] == 'w' else '0-1' if end['winner'] == 'b' else '1/2-1/2'
    g.headers['Termination'] = end['reason']
    head = str(g).split('\n\n', 1)[0]           # 标签部分用 python-chess 的；着法部分自己排，评注要按词折行
    return {'record.txt': '\n'.join(lines) + '\n', 'game.pgn': head + '\n\n' + _pgn_movetext(g, meta or {}) + '\n\n'}


def _pgn_movetext(g, meta):
    """PGN 着法部分：每步后跟 { 元信息与说明文字 }（records.meta_tokens），评注后的黑方着法补「N...」；
    所有词（评注里的也拆开）按导出格式每行不到 80 个字符贪心折行。python-chess 的导出把整段评注当一个词、不折行，
    带说明文字后一行会长过导入格式的 255 字符上限，所以不用它排着法。"""
    toks, after_comment = [], True
    for ply, node in enumerate(g.mainline(), 1):
        b = node.parent.board()
        if b.turn == chess.WHITE:
            toks.append('%d.' % b.fullmove_number)
        elif after_comment:
            toks.append('%d...' % b.fullmove_number)
        toks.append(node.san())
        c = records.meta_tokens(meta.get(ply))
        toks += ['{'] + c + ['}'] if c else []
        after_comment = bool(c)
    toks.append(g.headers['Result'])
    return records.wrap(toks, 79)


# ---------------------------------------------------------------- 引擎对手
def engine_spec(desc):
    """'maia-1100' … 'maia-1900'（lc0 加 Maia 权重，go nodes 1，按官方 README 不搜索）；
    'stockfish'、'stockfish:elo=1500'（限强，每步 100 毫秒）、'stockfish:nodes=N'、'stockfish:depth=N'、'stockfish:movetime=毫秒'。"""
    name, _, arg = desc.partition(':')
    m = re.match(r'^maia-(1[1-9]00)$', name)
    if m:
        if arg:
            raise ValueError('Maia 不带参数（固定 go nodes 1），收到 %r' % desc)
        w = os.path.join(MAIA_DIR, 'maia-%s.pb.gz' % m[1])
        if not os.path.exists(w):
            raise ValueError('找不到 Maia 权重 %s' % w)
        lc0 = shutil.which('lc0') or '/opt/homebrew/bin/lc0'
        return {'name': desc, 'cmd': [lc0, '--weights=' + w], 'go': 'go nodes 1', 'options': [('Threads', '1')]}
    if name == 'stockfish':
        path = shutil.which('stockfish') or '/opt/homebrew/bin/stockfish'
        opts = [('Threads', '1'), ('Hash', '16')]
        k, _, v = (arg or 'depth=12').partition('=')
        if not v.isdigit() or k not in ('elo', 'nodes', 'depth', 'movetime'):
            raise ValueError('stockfish 的参数写成 elo=N / nodes=N / depth=N / movetime=毫秒，收到 %r' % arg)
        if k == 'elo':
            opts += [('UCI_LimitStrength', 'true'), ('UCI_Elo', v)]
            go = 'go movetime 100'
        else:
            go = 'go %s %s' % (k, v)
        return {'name': desc, 'cmd': [path], 'go': go, 'options': opts}
    raise ValueError('国际象棋引擎只认 maia-1100 … maia-1900 和 stockfish[:参数]，收到 %r' % desc)


def to_engine(mv):
    return mv


def from_engine(s):
    return s
