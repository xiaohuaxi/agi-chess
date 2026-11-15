"""离线单元测试：思考延续三种模式的文字处理（agi_chess/memory.py）。全是纯函数，手写假回复即可。"""
import unittest

import chess

from agi_chess import chess_ as C, memory as M, xiangqi as X

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

    def test_english_move_line_anchored_and_revised(self):
        # 行首 Move:（含 markdown 包裹、空 Move: 后跟新行 Move:、以及 c2-02 真实复现的两处 Move:）
        self.assertEqual(M.extract_move('**Move: e2e4**', loose=True), 'e2e4**')
        self.assertEqual(M.extract_move('**Move:** h2e2', loose=True), 'h2e2')
        self.assertEqual(M.extract_move('**Move**: Nf3', loose=True), 'Nf3')
        self.assertIsNone(M.extract_move('**Move:**', loose=True))
        self.assertEqual(X.parse(X.start(), M.extract_move('**Move:** h2e2', loose=True)), ('h2e2', None))
        self.assertEqual(C.parse(C.start(), M.extract_move('**Move**: Nf3', loose=True)), ('g1f3', None))
        self.assertEqual(M.extract_move('Move:\n\nMove: g5f6', loose=True), 'g5f6')
        self.assertEqual(M.extract_move('Move: f6 is the target; Bg5xf6.\n\nMove: g5f6', loose=True), 'g5f6')
        # 正文句中出现的 "move: xxx" 不在行首，不当作着法标记（防误拆评注或错取对手上一步）
        prose_only = "After Black's last move: c7c5, White controls the d5 square and prepares central expansion."
        self.assertIsNone(M.extract_move(prose_only, loose=True))

    def test_extract_reason_note_first_and_move_first(self):
        self.assertEqual(M.extract_reason('White controls the center.\n\nMove: e2e4'), 'White controls the center.')
        self.assertEqual(M.extract_reason('White controls the center.\n\n**Move:** e2e4'), 'White controls the center.')
        self.assertEqual(M.extract_reason('Move: e2e4\n\nWhite controls the center.'), 'White controls the center.')
        self.assertIsNone(M.extract_reason('Move: e2e4'))
        self.assertIsNone(M.extract_reason('**Move: e2e4**'))
        self.assertIsNone(M.extract_reason('**Move:** e2e4'))


class ExtractNote(unittest.TestCase):
    def test_note_stops_before_move_line(self):
        reply = '便条: 计划中心\n多行\n继续便条\n着法: e2e4'
        self.assertEqual(M.extract_note(reply), '计划中心\n多行\n继续便条')

    def test_english_note_stops_before_move_line(self):
        reply = 'Note: Contest the open e-file\nand prepare O-O.\nMove: g1f3'
        self.assertEqual(M.extract_note(reply), 'Contest the open e-file\nand prepare O-O.')
        reply_md = '**Note:** Watch the central pawn.\n**Move:** e2e4'
        self.assertEqual(M.extract_note(reply_md), 'Watch the central pawn.')
        reply_multiline = 'Note:\nWatch d5 square.\nMove: e2e4'
        self.assertEqual(M.extract_note(reply_multiline), 'Watch d5 square.')

    def test_empty_note_before_move_line_does_not_swallow_move(self):
        self.assertIsNone(M.extract_note('Note:\nMove: e2e4'))
        self.assertIsNone(M.extract_note('Note:   \nMove: e2e4'))
        self.assertIsNone(M.extract_note('**Note:**\n**Move:** e2e4'))
        self.assertIsNone(M.extract_note('便条:\n着法: e2e4'))

    def test_no_note(self):
        self.assertIsNone(M.extract_note('没有便条只有着法: e2e4'))
        self.assertIsNone(M.extract_note('White develops the knight.\nMove: g1f3'))

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

    def test_english_notes_and_retry_prompt(self):
        sc_en = {'protocol': 'real', 'lang': 'en', 'memory': 'session'}
        self.assertEqual(M.notes_text(['plan A'], 1, sc_en), 'Your note from the previous turn:\nplan A')
        self.assertIn('1. plan A\n2. plan B', M.notes_text(['plan A', 'plan B'], 2, sc_en))
        retry = M.retry_prompt_real(sc_en, 'BASE', [('（没写）', M.feedback_text(sc_en, 'no_move'))], 1)
        self.assertEqual(
            retry,
            'Your previous move "(none)": no move was found in your response. '
            'Please make another move (1 retry remaining on this turn before forfeit.)',
        )
        sc_sl = {'protocol': 'real', 'lang': 'en', 'memory': 'stateless'}
        retry_sl = M.retry_prompt_real(sc_sl, 'BASE', [('a0a9', M.feedback_text(sc_sl, 'illegal'))], 2)
        self.assertIn('Moves you already tried on this turn:\n"a0a9": that move is illegal', retry_sl)
        self.assertIn('2 retries remaining on this turn before forfeit.', retry_sl)
        # notes + reason=off 英文下允许附带 Note: 行，不与单行无他文冲突；session + reason=off 仍严格单行
        self.assertIn('only a single line "Move: "', M.answer_lead({'protocol': 'real', 'lang': 'en', 'memory': 'session', 'reason': 'off'}))
        notes_off = M.answer_lead({'protocol': 'real', 'lang': 'en', 'memory': 'notes', 'reason': 'off'})
        self.assertIn('optional "Note: " line', notes_off)
        self.assertNotIn('only a single line', notes_off)


if __name__ == '__main__':
    unittest.main()
