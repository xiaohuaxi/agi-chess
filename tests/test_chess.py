"""离线单元测试：国际象棋规则模块（llmchess/chess_.py）。

不调 claude；局面用 python-chess 的 FEN 直接构造（parse() 只用得到 st['board']，
不需要凑齐 start() 返回的完整状态）。
"""
import unittest

import chess

from llmchess import chess_ as C


def mkst(fen):
    b = chess.Board(fen)
    return {'board': b, 'fens': [fen], 'moves': [], 'record': []}


class Parse(unittest.TestCase):
    def test_uci_simple(self):
        st = C.start()
        self.assertEqual(C.parse(st, 'e2e4'), ('e2e4', None))

    def test_san_simple(self):
        st = C.start()
        self.assertEqual(C.parse(st, 'Nf3'), ('g1f3', None))

    def test_castling_uci_and_san(self):
        st = C.start()
        for mv in ['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1c4', 'f8c5']:
            C.push(st, mv)
        for text in ('O-O', '0-0', 'e1g1'):
            self.assertEqual(C.parse(st, text), ('e1g1', None), text)

    def test_en_passant_uci_and_san(self):
        st = C.start()
        for mv in ['e2e4', 'a7a6', 'e4e5', 'd7d5']:
            C.push(st, mv)
        self.assertIn('e5d6', C.legal(st))
        self.assertEqual(C.parse(st, 'e5d6'), ('e5d6', None))
        self.assertEqual(C.parse(st, 'exd6'), ('e5d6', None))

    def test_promotion_uci_and_san(self):
        st = mkst('k7/4P3/8/8/8/8/8/7K w - - 0 1')
        self.assertEqual(C.parse(st, 'e7e8q'), ('e7e8q', None))
        self.assertEqual(C.parse(st, 'e8=Q'), ('e7e8q', None))

    def test_promotion_missing_gives_reason(self):
        st = mkst('k7/4P3/8/8/8/8/8/7K w - - 0 1')
        mv, why = C.parse(st, 'e7e8')
        self.assertEqual(mv, 'e7e8')
        self.assertEqual(why, '白兵从 e7 走到 e8 不合规：兵走到底线要写明升变成什么（如 e7e8q）')

    def test_promotion_suffix_when_not_last_rank(self):
        st = mkst('4k3/8/8/8/8/8/4P3/4K3 w - - 0 1')
        mv, why = C.parse(st, 'e2e4q')
        self.assertEqual(mv, 'e2e4q')
        self.assertEqual(why, '白兵从 e2 走到 e4 不合规：只有兵走到底线才能写升变')

    def test_ambiguous_san(self):
        st = mkst('4k3/8/8/8/8/2N3N1/8/4K3 w - - 0 1')
        self.assertEqual({m.uci() for m in st['board'].legal_moves if m.uci().endswith('e4')},
                         {'c3e4', 'g3e4'})
        mv, why = C.parse(st, 'Ne4')
        self.assertIsNone(mv)
        self.assertEqual(why, '「Ne4」有两个以上的子都能走，要写明是哪一个（如 Nbd2）')

    def test_pinned_piece_cannot_leave_pin_line(self):
        st = mkst('4r1k1/8/8/8/8/8/4B3/4K3 w - - 0 1')
        self.assertFalse(st['board'].is_check())
        mv, why = C.parse(st, 'e2d3')
        self.assertEqual(mv, 'e2d3')
        self.assertEqual(why, '白象从 e2 走到 d3 不合规：被牵制的子离开牵制线')
        # SAN 写法走同一条查错路径，给出的是“找不到能合法走到的子”那种措辞
        mv2, why2 = C.parse(st, 'Bd3')
        self.assertIsNone(mv2)
        self.assertIn('被牵制的子离开牵制线', why2)

    def test_king_cannot_walk_into_attacked_square(self):
        st = mkst('4r1k1/8/8/8/8/8/8/3K4 w - - 0 1')
        self.assertFalse(st['board'].is_check())
        mv, why = C.parse(st, 'd1e1')
        self.assertEqual(mv, 'd1e1')
        self.assertEqual(why, '白王从 d1 走到 e1 不合规：王走进被攻击的格')

    def test_pawn_blocked(self):
        st = mkst('4k3/8/8/8/8/4p3/4P3/4K3 w - - 0 1')
        mv, why = C.parse(st, 'e2e3')
        self.assertEqual(mv, 'e2e3')
        self.assertEqual(why, '白兵从 e2 走到 e3 不合规：兵前方有子')

    def test_rook_jump(self):
        st = mkst('4k3/8/8/8/8/N7/R7/4K3 w - - 0 1')
        mv, why = C.parse(st, 'a2a4')
        self.assertEqual(mv, 'a2a4')
        self.assertEqual(why, '白车从 a2 走到 a4 不合规：越子')

    def test_text_none(self):
        st = C.start()
        mv, why = C.parse(st, None)
        self.assertIsNone(mv)
        self.assertEqual(why, '回复里没有找到「着法: 」那一行')


class ViolationCrossCheck(unittest.TestCase):
    """violation() 是照搬 boards.py 独立手写的判定；和 python-chess 自己的合法着法表逐格比对。"""

    def _check(self, b):
        legal = {m.uci() for m in b.legal_moves}
        pieces = C._pieces(b)
        white = b.turn == chess.WHITE
        mismatches = []
        for fr, p in pieces.items():
            if p.isupper() != white:
                continue
            for f2 in 'abcdefgh':
                for r2 in '12345678':
                    to = f2 + r2
                    if to == fr:
                        continue
                    for promo in ('', 'q', 'r', 'b', 'n'):
                        mv = fr + to + promo
                        v = C.violation(b, mv)
                        by_chess = mv in legal
                        by_violation = v is None
                        if by_chess != by_violation:
                            mismatches.append((mv, by_chess, v))
        self.assertEqual(mismatches, [], b.fen())

    def test_start_position(self):
        self._check(chess.Board())

    def test_after_a_few_plies(self):
        import random
        st = C.start()
        rng = random.Random(20260925)
        for _ in range(6):
            mvs = [m.uci() for m in st['board'].legal_moves]
            C.push(st, rng.choice(mvs))
            self._check(st['board'])


class Ending(unittest.TestCase):
    def test_threefold_repetition_not_premature(self):
        """回归用例：python-chess 的 outcome(claim_draw=True) 在“再走一步就能凑成三次重复”时就已经
        可以申诉判和（提前一个半回合），chess_.ending() 刻意绕开这点，只在局面**已经**出现第三次时才判。"""
        b = chess.Board()
        st = {'board': b, 'fens': [b.fen()], 'moves': [], 'record': []}
        moves = ['g1f3', 'g8f6', 'f3g1', 'f6g8'] * 2
        results = []
        for mv in moves:
            C.push(st, mv)
            results.append((b.is_repetition(3), b.outcome(claim_draw=True), C.ending(st)))
        # 第 7 步（0 起算第 6 个）：claim_draw=True 已经能申诉和棋，但还不是真正的第三次重复
        rep3_early, claim_early, our_early = results[6]
        self.assertFalse(rep3_early)
        self.assertIsNotNone(claim_early, '这一步 claim_draw=True 应该已经可以申诉（提前），用来对照下面我们没有提前')
        self.assertIsNone(our_early, 'chess_.ending() 不该在真正三次重复之前就判和')
        # 第 8 步：真正的第三次重复，才判和
        rep3_final, claim_final, our_final = results[7]
        self.assertTrue(rep3_final)
        self.assertEqual(our_final, {'winner': None, 'reason': '同一局面出现三次，程序替棋手申诉，判和'})

    def test_fifty_move_rule_at_halfmove_100(self):
        # halfmove clock 提前设到 99（子力足够，避免碰到子力不足判和），走一步安静着法刚好到 100
        fen = '4k3/8/8/8/8/8/8/R3K3 w - - 99 60'
        b = chess.Board(fen)
        st = {'board': b, 'fens': [fen], 'moves': [], 'record': []}
        self.assertIsNone(C.ending(st))
        C.push(st, 'a1a2')
        self.assertEqual(b.halfmove_clock, 100)
        self.assertEqual(C.ending(st), {'winner': None, 'reason': '五十回合没有吃子和兵的走动，程序替棋手申诉，判和'})

    def test_checkmate(self):
        st = C.start()
        for mv in ['f2f3', 'e7e5', 'g2g4', 'd8h4']:   # 愚人开局
            C.push(st, mv)
        self.assertEqual(C.ending(st), {'winner': 'b', 'reason': '将死'})

    def test_stalemate(self):
        st = mkst('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1')
        self.assertTrue(st['board'].is_stalemate())
        self.assertEqual(C.ending(st), {'winner': None, 'reason': '逼和，判和'})

    def test_insufficient_material(self):
        st = mkst('4k3/8/8/8/8/8/8/4K3 w - - 0 1')
        self.assertTrue(st['board'].is_insufficient_material())
        self.assertEqual(C.ending(st), {'winner': None, 'reason': '双方子力都不足以将死，判和'})


class Exports(unittest.TestCase):
    def test_pgn_result_matches_decisive_outcome(self):
        st = C.start()
        for mv in ['f2f3', 'e7e5', 'g2g4', 'd8h4']:
            C.push(st, mv)
        end = C.ending(st)
        self.assertEqual(end['winner'], 'b')
        cfg = {'tag': 't1', 'players': {'w': 'random', 'b': 'random'}}
        files = C.exports(st, cfg, end, ['summary line'])
        self.assertIn('game.pgn', files)
        self.assertIn('Result "0-1"', files['game.pgn'])
        self.assertIn('Termination "将死"', files['game.pgn'])
        self.assertIn('黑方胜', files['record.txt'])

    def test_pgn_result_matches_draw(self):
        st = C.start()
        end = {'winner': None, 'reason': '逼和，判和'}
        cfg = {'tag': 't2', 'players': {'w': 'random', 'b': 'random'}}
        files = C.exports(st, cfg, end, ['summary line'])
        self.assertIn('Result "1/2-1/2"', files['game.pgn'])

    def test_pgn_result_matches_white_win(self):
        st = C.start()
        end = {'winner': 'w', 'reason': '将死'}
        cfg = {'tag': 't3', 'players': {'w': 'random', 'b': 'random'}}
        files = C.exports(st, cfg, end, ['summary line'])
        self.assertIn('Result "1-0"', files['game.pgn'])


if __name__ == '__main__':
    unittest.main()
