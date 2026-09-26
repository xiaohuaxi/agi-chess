"""离线单元测试：思考延续三种模式的文字处理（llmchess/memory.py）。全是纯函数，手写假回复即可。"""
import unittest

import chess

from llmchess import chess_ as C, memory as M, xiangqi as X

# 第二批 B1 的原样回复（b2B1 parsebug）：先写「着法: e3」，又改口「应当写皇后的着法：」，再写「着法: g3e3」
REVISED_CHESS = """**思路：** 黑后在 g4 受 e6 象保护。如果 Qxg4 Bxg4 换后，白方少三个兵进入残局，基本没有机会，所以要保留皇后。

- Qe3 可以让出 g 线，并用第三横线看住 h3。这样能防住 Bh3 配合后在 g2 将杀的威胁。
- 皇后在 e3 还同时瞄着 h6 和 b6 方向，保留一些反击机会。
- 如果黑方走 d4 赶后，白后可以退到 d3 或 e4。

着法: e3

等一下，应当写皇后的着法：

着法: g3e3"""
REVISED_FEN = 'r4rk1/2p2pp1/1p2b2p/3pP3/p5q1/6Q1/5PPP/NR3RK1 w - - 5 23'


class ExtractMove(unittest.TestCase):
    def test_takes_last_occurrence(self):
        reply = '先说点别的\n着法: e2e2误打\n然后重新想了想\n着法: e2e4\n'
        self.assertEqual(M.extract_move(reply), 'e2e4')

    def test_no_move_line(self):
        self.assertIsNone(M.extract_move('这段回复完全没提着法'))

    def test_none_reply(self):
        self.assertIsNone(M.extract_move(None))

    def test_full_width_colon(self):
        self.assertEqual(M.extract_move('着法：h2e2'), 'h2e2')

    def test_revised_move_chess_verbatim(self):
        text = M.extract_move(REVISED_CHESS)
        self.assertEqual(text, 'g3e3')
        st = {'board': chess.Board(REVISED_FEN), 'fens': [REVISED_FEN], 'moves': [], 'record': []}
        self.assertEqual(C.parse(st, text), ('g3e3', None))

    def test_revised_move_xiangqi(self):
        reply = '思路：先出马。\n\n着法: h2e2\n\n不对，我想走的是马，应该写成：\n\n**着法：h0g2**'
        text = M.extract_move(reply)
        self.assertEqual(X.parse(X.start(), text), ('h0g2', None))
        reply2 = '改一下最后的着法：\n着法：马二进三'
        self.assertEqual(X.parse(X.start(), M.extract_move(reply2)), ('h0g2', None))

    def test_move_on_next_line_after_colon(self):
        self.assertEqual(M.extract_move('我的着法：\n\ne2e4'), 'e2e4')


class ExtractNote(unittest.TestCase):
    def test_note_stops_before_move_line(self):
        reply = '便条: 计划中心\n多行\n继续便条\n着法: e2e4'
        self.assertEqual(M.extract_note(reply), '计划中心\n多行\n继续便条')

    def test_no_note(self):
        self.assertIsNone(M.extract_note('没有便条只有着法: e2e4'))

    def test_none_reply(self):
        self.assertIsNone(M.extract_note(None))

    def test_blank_note_becomes_none(self):
        reply = '便条: ```   ```\n着法: e2e4'
        self.assertIsNone(M.extract_note(reply))

    def test_takes_last_occurrence(self):
        reply = '便条: 旧的\n着法: e2e3（非法重试）\n便条: 新的\n着法: e2e4'
        self.assertEqual(M.extract_note(reply), '新的')


class NotesText(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(M.notes_text([], 1), '')
        self.assertEqual(M.notes_text([None, ''], 3), '')

    def test_keep_zero_returns_empty(self):
        self.assertEqual(M.notes_text(['a', 'b'], 0), '')

    def test_keep_one_is_singular_wording(self):
        text = M.notes_text(['n1', 'n2', 'n3'], 1)
        self.assertTrue(text.endswith('n3'))
        self.assertNotIn('n2', text)
        self.assertNotIn('1.', text)   # 只有一条时不编号

    def test_keep_several_numbers_from_oldest_to_newest(self):
        text = M.notes_text(['n1', 'n2', 'n3', None, ''], 2)
        self.assertIn('1. n2', text)
        self.assertIn('2. n3', text)
        self.assertNotIn('n1', text)

    def test_falsy_notes_are_skipped_before_truncation(self):
        # keep=1 时应该拿到最后一条“非空”便条，而不是被 None/'' 占位挤掉
        text = M.notes_text(['n1', None, '', 'n2'], 1)
        self.assertTrue(text.endswith('n2'))


if __name__ == '__main__':
    unittest.main()
