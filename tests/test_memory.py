"""离线单元测试：思考延续三种模式的文字处理（llmchess/memory.py）。全是纯函数，手写假回复即可。"""
import unittest

from llmchess import memory as M


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
