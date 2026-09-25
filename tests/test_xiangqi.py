"""离线单元测试：中国象棋规则模块（llmchess/xiangqi.py）。

不调 claude、不起子进程；棋规判定用 pyffish 直接核实（它就是 xiangqi.py 包装的库），
局面用 xiangqi.board_fen() 手搭（只涉及棋子摆放，和被测的着法解析 / 终局逻辑是两回事）。
"""
import unittest

import pyffish as sf

from llmchess import xiangqi as X

XQ = 'xiangqi'


def mk(pieces, stm):
    """{格: 棋子字母} -> 完整 FEN。K/k 两个帅（将）必须都给，否则 violation() 的照面检查会 KeyError。"""
    return X.board_fen(pieces) + ' %s - - 0 1' % stm


def st_of(fen):
    return {'fens': [fen], 'fsf': [], 'moves': [], 'record': []}


class ToFsfFromFsf(unittest.TestCase):
    def test_round_trip(self):
        for mv in ('a0a1', 'h2e2', 'i9i8', 'e0e9'):
            self.assertEqual(X.from_fsf(X.to_fsf(mv)), mv)

    def test_boundaries(self):
        # ICCS 横线 0-9 <-> 引擎 1-10，边界格 a0、i9
        self.assertEqual(X.to_fsf('a0i9'), 'a1i10')
        self.assertEqual(X.from_fsf('a1i10'), 'a0i9')
        self.assertEqual(X.to_fsf('i9a0'), 'i10a1')
        self.assertEqual(X.from_fsf('i10a1'), 'i9a0')


class ParseLegal(unittest.TestCase):
    def test_iccs(self):
        # 起始局面，红炮二平五（design.md 第二节原文例子）
        mv, why = X.parse(X.start(), 'h2e2')
        self.assertEqual(mv, 'h2e2')
        self.assertIsNone(why)

    def test_red_chinese(self):
        mv, why = X.parse(X.start(), '炮二平五')
        self.assertEqual(mv, 'h2e2')
        self.assertIsNone(why)

    def test_black_chinese_half_and_full_width(self):
        st = X.start()
        X.push(st, 'h2e2')
        for text in ('马8进7', '马８进７'):
            mv, why = X.parse(st, text)
            self.assertEqual((mv, why), ('h9g7', None), text)


class ParseIllegal(unittest.TestCase):
    """每条违规都独立手搭一个最小局面：两个帅在不相关的两个纵线（d/f 或 e/e 但用别的子隔开），
    避免棋子照面之类的副作用把测试的那条规则盖住。"""

    def test_text_none(self):
        mv, why = X.parse(X.start(), None)
        self.assertIsNone(mv)
        self.assertEqual(why, '回复里没有找到「着法: 」那一行')

    def test_gibberish(self):
        mv, why = X.parse(X.start(), '这不是一步棋随便写的')
        self.assertIsNone(mv)
        self.assertEqual(why, '既不是 ICCS 坐标，也对不上任何一步合法着法的中文记谱')

    def test_origin_empty(self):
        # check_iccs 在“着法本身写对了格式、但内容不合规”时，mv 仍然原样带回（不是 None），
        # 靠 why 非空来判断不合法——parse() 直接转发，不会另外把 mv 收回 None
        mv, why = X.parse(X.start(), 'e4e5')
        self.assertEqual(mv, 'e4e5')
        self.assertEqual(why, '起点 e4 上没有棋子')

    def test_origin_opponent_piece(self):
        # 起始局面轮到红方，e9 是黑方的将
        mv, why = X.parse(X.start(), 'e9e8')
        self.assertEqual(mv, 'e9e8')
        self.assertEqual(why, '起点 e9 上是对方的将')

    def test_leg(self):
        # 蹩马腿：马 e4 想跳 f6，腿 e5 被己方兵占住
        fen = mk({'d0': 'K', 'f9': 'k', 'e4': 'N', 'e5': 'P'}, 'w')
        self.assertNotIn(X.to_fsf('e4f6'), sf.legal_moves(XQ, fen, []))
        mv, why = X.parse(st_of(fen), 'e4f6')
        self.assertEqual((mv, why), ('e4f6', '马从 e4 走到 f6 不合规：蹩马腿'))

    def test_eye(self):
        # 塞象眼：相 c0 想去 e2（没过河），眼 d1 被占
        fen = mk({'d0': 'K', 'f9': 'k', 'c0': 'B', 'd1': 'P'}, 'w')
        self.assertNotIn(X.to_fsf('c0e2'), sf.legal_moves(XQ, fen, []))
        mv, why = X.parse(st_of(fen), 'c0e2')
        self.assertEqual((mv, why), ('c0e2', '相从 c0 走到 e2 不合规：塞象眼'))

    def test_river(self):
        # 相过河：c4 -> e6，y2=6 已过河
        fen = mk({'d0': 'K', 'f9': 'k', 'c4': 'B'}, 'w')
        self.assertNotIn(X.to_fsf('c4e6'), sf.legal_moves(XQ, fen, []))
        mv, why = X.parse(st_of(fen), 'c4e6')
        self.assertEqual((mv, why), ('c4e6', '相从 c4 走到 e6 不合规：相过河'))

    def test_rook_jump(self):
        # 车越子：e4 -> e7，路上 e5 有子
        fen = mk({'d0': 'K', 'f9': 'k', 'e4': 'R', 'e5': 'P'}, 'w')
        self.assertNotIn(X.to_fsf('e4e7'), sf.legal_moves(XQ, fen, []))
        mv, why = X.parse(st_of(fen), 'e4e7')
        self.assertEqual((mv, why), ('e4e7', '车从 e4 走到 e7 不合规：越子'))

    def test_cannon_screen0(self):
        # 炮吃子没有炮架：e4 吃 e6，中间没有子
        fen = mk({'d0': 'K', 'f9': 'k', 'e4': 'C', 'e6': 'r'}, 'w')
        self.assertNotIn(X.to_fsf('e4e6'), sf.legal_moves(XQ, fen, []))
        mv, why = X.parse(st_of(fen), 'e4e6')
        self.assertEqual((mv, why), ('e4e6', '炮从 e4 走到 e6 不合规：炮吃子没有炮架'))

    def test_cannon_screen2(self):
        # 炮隔两个以上的子吃子：e4 吃 e8，中间 e5、e6 都有子
        fen = mk({'d0': 'K', 'f9': 'k', 'e4': 'C', 'e5': 'P', 'e6': 'P', 'e8': 'r'}, 'w')
        self.assertNotIn(X.to_fsf('e4e8'), sf.legal_moves(XQ, fen, []))
        mv, why = X.parse(st_of(fen), 'e4e8')
        self.assertEqual((mv, why), ('e4e8', '炮从 e4 走到 e8 不合规：炮隔两个以上的子吃子'))

    def test_pawn_side_before_river(self):
        # 兵未过河就横走：红兵 e3（未过河）横移到 f3
        fen = mk({'d0': 'K', 'f9': 'k', 'e3': 'P'}, 'w')
        self.assertNotIn(X.to_fsf('e3f3'), sf.legal_moves(XQ, fen, []))
        mv, why = X.parse(st_of(fen), 'e3f3')
        self.assertEqual((mv, why), ('e3f3', '兵从 e3 走到 f3 不合规：兵未过河就横走'))

    def test_pawn_back(self):
        # 兵后退：红兵 e5 退到 e4
        fen = mk({'d0': 'K', 'f9': 'k', 'e5': 'P'}, 'w')
        self.assertNotIn(X.to_fsf('e5e4'), sf.legal_moves(XQ, fen, []))
        mv, why = X.parse(st_of(fen), 'e5e4')
        self.assertEqual((mv, why), ('e5e4', '兵从 e5 走到 e4 不合规：兵后退'))

    def test_facing(self):
        # 走完帅将照面：两帅同在 e 线，车 e5 是唯一的遮挡，移开后照面
        fen = mk({'e0': 'K', 'e9': 'k', 'e5': 'R'}, 'w')
        self.assertNotIn(X.to_fsf('e5d5'), sf.legal_moves(XQ, fen, []))
        mv, why = X.parse(st_of(fen), 'e5d5')
        self.assertEqual((mv, why), ('e5d5', '车从 e5 走到 d5 不合规：走完帅将照面'))

    def test_self_check_pin(self):
        # 走完自己被将：黑车 d9 牵制红车 d3（隔着打红帅 d0），红车离开牵制线
        fen = mk({'d0': 'K', 'f9': 'k', 'd9': 'r', 'd3': 'R'}, 'w')
        self.assertNotIn(X.to_fsf('d3c3'), sf.legal_moves(XQ, fen, []))
        mv, why = X.parse(st_of(fen), 'd3c3')
        self.assertEqual((mv, why), ('d3c3', '车从 d3 走到 c3 不合规：走完自己被将'))


class RuleViolationCrossCheck(unittest.TestCase):
    """violation() 是照搬 boards.py 独立手写的判定；这里对起始局面和几步随机playout，
    逐一枚举“行棋方的子挪到棋盘任意格”，和 pyffish 的合法着法表比对，两边必须完全一致。
    覆盖面比手搭的几个例子大得多，用来兜没想到的违规组合。"""

    def _check(self, fen):
        legal = set(X.legal_fen(fen))
        board, stm = X.board_of(fen)
        mismatches = []
        for sq, p in board.items():
            if X.is_red(p) != (stm == 'w'):
                continue
            for tx in range(9):
                for ty in range(10):
                    to = X.sq_of(tx, ty)
                    if to == sq:
                        continue
                    mv = sq + to
                    by_pyffish = mv in legal
                    by_violation = X.violation(fen, mv) is None
                    if by_pyffish != by_violation:
                        mismatches.append((mv, by_pyffish, by_violation))
        self.assertEqual(mismatches, [], fen)

    def test_start_position(self):
        self._check(X.START)

    def test_after_a_few_plies(self):
        import random
        st = X.start()
        rng = random.Random(20260925)
        for _ in range(6):
            mvs = X.legal(st)
            X.push(st, rng.choice(mvs))
            self._check(st['fens'][-1])


class Ending(unittest.TestCase):
    def test_checkmate(self):
        # 黑将 e9 被红车 e5（file）和红车 i9（rank）夹死，无路可走
        fen = mk({'d0': 'K', 'e9': 'k', 'e5': 'R', 'i9': 'R'}, 'b')
        self.assertEqual(X.status(fen), 'mate')
        self.assertEqual(X.ending(st_of(fen)), {'winner': 'w', 'reason': '将死'})

    def test_stalemate_is_a_loss(self):
        # 困毙（中国象棋里困毙判负，不是和棋）：黑将 d9，e9 被红车 e1 管住，d8 被红马 b7 管住，d9 本身不被将
        fen = mk({'f0': 'K', 'd9': 'k', 'e1': 'R', 'b7': 'N'}, 'b')
        self.assertEqual(X.status(fen), 'stalemate')
        self.assertFalse(X.in_check_fen(fen))
        self.assertEqual(X.ending(st_of(fen)), {'winner': 'w', 'reason': '困毙'})

    def test_threefold_repetition_draw(self):
        # 双方各拿一枚不相干的车来回走，互不影响、互不将军，第三次出现同一局面判和
        fen0 = mk({'f0': 'K', 'd9': 'k', 'a0': 'R', 'i9': 'r'}, 'w')
        st = st_of(fen0)
        seq = ['a0a1', 'i9i8', 'a1a0', 'i8i9'] * 3
        end = None
        for mv in seq:
            self.assertIn(mv, X.legal(st))
            X.push(st, mv)
            end = X.ending(st)
            if end:
                break
        self.assertEqual(end, {'winner': None, 'reason': '同一局面出现三次，判和'})
        # 恰好用了两轮循环（8 步）就分出和棋，不是拖到第三轮才判
        self.assertEqual(len(st['moves']), 8)


class Banned(unittest.TestCase):
    """长将判负：红车反复在 e/f 两个纵线之间来回将黑将（黑王被逼在 e8/f8 之间唯一应将）。
    车走 e4<->f4、王被迫 e9->e8->f8->e8->f8->e8->f8 应将，这个 4 步一循环的模式走满两轮
    （12 个半回合，车最后一步落在 f4，王最后一步落在 f8）之后，"红车再走回 e4"会让同一局面
    第三次出现——用 pyffish 直接核实这一步确实会被判长将负，再验证 banned() 能提前把它标出来。"""

    # 黑王第一次应将是 e9->e8；此后一直在 e8/f8 之间被将，不会再回到 e9——不是简单的定长循环，
    # 所以这里整段写死（已用 pyffish 核实这就是每一步的唯一合法应将 / 唯一有意义的将军着法）。
    FULL_SEQ = ['e4f4', 'e9e8', 'f4e4', 'e8f8', 'e4f4', 'f8e8', 'f4e4', 'e8f8', 'e4f4', 'f8e8', 'f4e4', 'e8f8']

    def _push_n(self, n):
        fen0 = mk({'d0': 'K', 'e9': 'k', 'e4': 'R'}, 'w')
        st = st_of(fen0)
        for mv in self.FULL_SEQ[:n]:
            self.assertIn(mv, X.legal(st), (n, mv))
            X.push(st, mv)
        return st

    def test_pyffish_confirms_perpetual_check_loss(self):
        st = self._push_n(12)   # 红方即将走第三次 e4f4
        self.assertEqual(st['fens'][-1].split()[1], 'w')
        f = X.to_fsf('e4f4')
        fens, fsf = st['fens'], st['fsf']
        # 直接问 pyffish：走完这一步、形成第三次重复之后，这局是不是已经结束
        end, val = sf.is_optional_game_end(XQ, fens[0], fsf + [f])
        if not end:
            end, val = sf.is_immediate_game_end(XQ, fens[0], fsf + [f])
        self.assertTrue(end, 'pyffish 应确认再走一次 e4f4 会形成三次重复的长将')
        # 谁输谁赢由 xiangqi.rule_end()（对 pyffish 的薄包装）判定——这里直接核实红方（长将方）判负，
        # banned() 就是靠这同一个 rule_end() 来判断"这步是不是会让走这步的人自己输"
        new_fen = sf.get_fen(XQ, fens[-1], [f])
        winner, _ = X.rule_end(fens + [new_fen], fsf + [f])
        self.assertEqual(winner, 'b', '红方长将三次，应判红方负、黑方胜')

    def test_banned_flags_the_repeating_check(self):
        st = self._push_n(12)
        moves = X.legal(st)
        ban = X.banned(st, moves)
        self.assertIn('e4f4', ban)
        self.assertEqual(ban['e4f4'], X.BANNED_REASON)
        # 平常着法（比如红帅动一步）不该被牵连
        self.assertNotIn('d0d1', ban)
        self.assertNotIn('d0e0', ban)

    def test_banned_does_not_flag_forced_reply_that_wins(self):
        # 红方刚走完第 9 步（第三次 e4f4）之后，轮到黑方：黑方唯一合法着法 f8e8 会让局面第三次重复，
        # 但按 pyffish 的判法，输的是红方（长将方），黑方这步不该被 banned() 拦
        # （banned 拦的是会让"自己"判负的着法）
        st = self._push_n(9)
        self.assertEqual(st['fens'][-1].split()[1], 'b')
        moves = X.legal(st)
        self.assertEqual(moves, ['f8e8'])
        ban = X.banned(st, moves)
        self.assertEqual(ban, {})

    def test_banned_empty_at_start(self):
        self.assertEqual(X.banned(X.start(), X.legal(X.start())), {})


if __name__ == '__main__':
    unittest.main()
