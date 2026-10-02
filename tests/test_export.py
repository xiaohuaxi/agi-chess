"""棋谱导出：中文折行、思考深度标签、中国象棋 xqbase PGN 与记谱生成（docs/viewer.md 第 1 步）。离线，不调模型。"""
import io
import re
import unittest

import chess.pgn

from llmchess import chess_ as C, records
from llmchess import xiangqi as X


def unwrap(text):
    """阅读器读折行文字的规则：换行两边都是全角字符就不补空格，否则当一个空格。"""
    out = text[0] if text else ''
    for prev, c, nxt in zip(text, text[1:], text[2:] + ' '):
        if c == '\n':
            out += '' if records.wide(prev) and records.wide(nxt) else ' '
        else:
            out += c
    return out


def fen_of(pieces, turn='w'):
    """{格: 棋子} -> 完整 FEN。"""
    return '%s %s - - 0 1' % (X.board_fen(pieces), turn)


def flip(pieces):
    """红黑互换：棋盘转 180 度、大小写对调。"""
    return {X.sq_of(8 - X.xy(s)[0], 9 - X.xy(s)[1]): p.swapcase() for s, p in pieces.items()}


def flip_mv(mv):
    a, b = X.xy(mv[:2]), X.xy(mv[2:])
    return X.sq_of(8 - a[0], 9 - a[1]) + X.sq_of(8 - b[0], 9 - b[1])


class Wrap(unittest.TestCase):
    TEXT = ('先出车控制肋道，再考虑兑子。对方的马在 e5 很活跃；如果不理它，下一步 Nf3 之后会很被动：'
            '所以这里宁可先交换，保持局面平稳。' * 4)

    def test_chinese_breaks_without_adding_spaces(self):
        text = records.wrap(records.meta_tokens({'emt': 3, 'why': self.TEXT}), 40)
        # meta_tokens 按 WIDTH 切段，这里折成 40 列只看拼接规则；真实导出按 76 / 79 列
        self.assertEqual(unwrap(text), '[%emt 0:00:03] ' + self.TEXT)

    def test_lines_fit_and_prefer_punctuation(self):
        c = records.meta_comment({'emt': 3, 'why': self.TEXT})
        lines = c.split('\n')
        self.assertGreater(len(lines), 3)
        for line in lines:
            self.assertLessEqual(records.cols(line), records.WIDTH, line)
        self.assertEqual(unwrap(c), '[%emt 0:00:03] ' + self.TEXT)
        cut_after_punct = sum(l[-1] in records.CJK_BREAK_AFTER for l in lines[:-1] if records.wide(l[-1]))
        self.assertGreaterEqual(cut_after_punct, len(lines) // 2)   # 大多数行在标点后断

    def test_ellipsis_and_dash_round_trip(self):
        # 回归：「…」「—」东亚宽度是 A，阅读器不当全角；以前在「……」后断行，读回来多一个空格
        why = ('黑车就会退回 d3，我再进炮打它……这样反复追捉同一个车——就是犯规的长捉。' * 8)
        self.assertTrue(all(records.wide(c) for c in records.CJK_BREAK_AFTER))
        for width in (records.WIDTH, 79):
            text = records.wrap(records.meta_tokens({'emt': 1, 'why': why}), width)
            for line in text.split('\n'):
                self.assertLessEqual(records.cols(line), width, line)
                self.assertFalse(line.endswith(('…', '—')), line)
            self.assertEqual(unwrap(text), '[%emt 0:00:01] ' + why, width)

    def test_long_run_without_punctuation_hard_cut_between_wide_chars(self):
        why = '中' * 100 + 'abc'
        c = records.meta_comment({'emt': 1, 'why': why})
        for line in c.split('\n'):
            self.assertLessEqual(records.cols(line), records.WIDTH)
        self.assertEqual(unwrap(c), '[%emt 0:00:01] ' + why)

    def test_space_between_chinese_is_never_a_break(self):
        why = ('红方 中炮 过河 以后，黑方 必须 马上 应对，否则 中卒 丢掉 就 很 被动 了 ' * 6).strip()
        for width in (30, 40, 57, records.WIDTH, 79):     # meta_tokens 按 WIDTH 切段，窄于它时只看往返
            text = records.wrap(records.meta_tokens({'emt': 1, 'why': why}), width)
            for line in text.split('\n'):
                if width >= records.WIDTH:
                    self.assertLessEqual(records.cols(line), width, line)
                self.assertEqual(line, line.strip())
            self.assertEqual(unwrap(text), '[%emt 0:00:01] ' + why, width)

    def test_mixed_spaces_break_at_plain_space_first(self):
        why = '走 Nf3 之后 看 e5 的 反应 再 决定' * 3
        c = records.meta_comment({'emt': 1, 'why': why})
        self.assertEqual(unwrap(c), '[%emt 0:00:01] ' + why)

    def test_old_behaviour_inserted_space(self):
        # 回归：旧导出在中文字中间断行，读回来多一个空格
        c = records.meta_comment({'emt': 1, 'why': '中路控制很重要，' * 30})
        self.assertNotIn(' 中', unwrap(c).replace('[%emt 0:00:01] 中', ''))


class EffortTags(unittest.TestCase):
    def cfg(self, w, b, ew='xhigh', eb='max'):
        return {'tag': 't', 'players': {'w': w, 'b': b}, 'sides': {'w': {'effort': ew}, 'b': {'effort': eb}}}

    def test_chess_both_models(self):
        st = C.start()
        C.push(st, 'e2e4')
        pgn = C.exports(st, self.cfg('claude:opus', 'codex:astra'), {'winner': None, 'reason': 'x'}, [])['game.pgn']
        h = chess.pgn.read_game(io.StringIO(pgn)).headers
        self.assertEqual((h['WhiteEffort'], h['BlackEffort']), ('xhigh', 'max'))

    def test_engine_side_has_no_effort(self):
        st = C.start()
        cfg = self.cfg('engine:maia-1100', 'claude:opus', 'high', 'high')
        pgn = C.exports(st, cfg, {'winner': None, 'reason': 'x'}, [])['game.pgn']
        self.assertNotIn('WhiteEffort', pgn)
        self.assertIn('[BlackEffort "high"]', pgn)
        xpgn = X.exports(X.start(), dict(cfg, players={'w': 'claude:opus', 'b': 'engine:fsf'}),
                         {'winner': None, 'reason': 'x'}, [])['game.pgn']
        self.assertIn('[RedEffort "high"]', xpgn)
        self.assertNotIn('BlackEffort', xpgn)

    def test_old_config_without_sides(self):
        self.assertEqual(records.efforts({'players': {'w': 'claude:opus', 'b': 'random'}}), {})


class XiangqiPgn(unittest.TestCase):
    META = {1: {'emt': 12.0, 'think': 280, 'out': 300, 'in': 2, 'cache_read': 100, 'cache_write': 50,
                'illegal': 1, 'flagged': 0, 'empty': 0, 'calls': 2, 'why': '先架中炮。'},
            2: {'emt': 3.0, 'think': 30, 'out': 40, 'in': 2, 'cache_read': 0, 'cache_write': 0,
                'illegal': 0, 'flagged': 0, 'empty': 0, 'calls': 1}}
    # xqbase《着法表示》第三节的例子，含「前炮退二」
    MOVES = ['h2e2', 'h7e7', 'e2e6', 'd9e8', 'h0g2', 'h9g7', 'b2e2', 'b9c7', 'e6e4', 'i9h9']
    TEXTS = ['炮二平五', '炮８平５', '炮五进四', '士４进５', '马二进三', '马８进７', '炮八平五', '马２进３', '前炮退二', '车９平８']

    def export(self):
        st = X.start()
        for mv in self.MOVES:
            X.push(st, mv)
        cfg = {'tag': 'x9', 'players': {'w': 'claude:opus', 'b': 'codex:astra'},
               'sides': {'w': {'effort': 'xhigh'}, 'b': {'effort': 'xhigh'}}}
        return st, X.exports(st, cfg, {'winner': 'w', 'reason': '将死'}, ['s'], self.META)

    def test_tags(self):
        _, files = self.export()
        self.assertIn('record.txt', files)
        head = files['game.pgn'].split('\n\n')[0].split('\n')
        self.assertEqual(head, ['[Game "Chinese Chess"]', '[Event "llm-chess x9"]', '[Red "claude:opus"]',
                                '[Black "codex:astra"]', '[RedEffort "xhigh"]', '[BlackEffort "xhigh"]',
                                '[Result "1-0"]', '[Termination "将死"]'])

    def test_movetext(self):
        st, files = self.export()
        body = files['game.pgn'].split('\n\n', 1)[1]
        self.assertTrue(body.startswith('1. 炮二平五 { [%emt 0:00:12] [%think 280]'), body)
        self.assertIn('先架中炮。 } 炮８平５ { [%emt 0:00:03]', ' '.join(body.split()))
        self.assertIn('5. 前炮退二 车９平８ 1-0', ' '.join(body.split()))
        for line in body.splitlines():
            self.assertLess(records.cols(line), 80, line)
        moves = [t for t in re.sub(r'\{[^}]*\}', ' ', body).split() if not re.match(r'^\d+\.$|^1-0$', t)]
        self.assertEqual(moves, self.TEXTS)
        self.assertEqual(moves, st['record'])          # 普通局面和 record.txt 的记谱一致


class XqbaseNotation(unittest.TestCase):
    """造局面测多路兵、同线多子（xqbase《着法表示》第四节）。每个局面还检查全部合法着法写出来互不相同。"""
    KINGS = {'e0': 'K', 'd9': 'k'}

    def check(self, pieces, expect, turn='w'):
        fen = fen_of(dict(self.KINGS, **pieces), turn)
        legal = X.legal_fen(fen)
        texts = [X.pgn_move(fen, m) for m in legal]
        self.assertEqual(len(set(texts)), len(texts), sorted(texts))     # 无歧义
        for mv, want in expect.items():
            self.assertIn(mv, legal)
            self.assertEqual(X.pgn_move(fen, mv), want, mv)

    # 原文例局：四线、六线各两兵，五线一兵（这里整体往下挪了一格，结构相同）
    EXAMPLE = {'f7': 'P', 'f5': 'P', 'e6': 'P', 'd7': 'P', 'd5': 'P'}
    EXAMPLE_MOVES = {'f7e7': '一兵平五', 'f5e5': '二兵平五', 'e6e7': '兵五进一', 'd7e7': '三兵平五', 'd5e5': '四兵平五'}

    def test_xqbase_example_red(self):
        self.check(self.EXAMPLE, self.EXAMPLE_MOVES)

    def test_xqbase_example_black(self):
        pieces = flip(dict(self.KINGS, **self.EXAMPLE))
        fen = fen_of(pieces, 'b')
        got = {m: X.pgn_move(fen, flip_mv(m)) for m in self.EXAMPLE_MOVES}
        self.assertEqual(got, {'f7e7': '一卒平５', 'f5e5': '二卒平５', 'e6e7': '卒５进１',
                               'd7e7': '三卒平５', 'd5e5': '四卒平５'})

    def test_two_pawns_one_file(self):
        self.check({'c6': 'P', 'c5': 'P', 'g6': 'P'}, {'c6c7': '前兵进一', 'c5b5': '后兵平八', 'g6g7': '兵三进一'})

    def test_three_pawns_one_file(self):
        self.check({'c7': 'P', 'c6': 'P', 'c5': 'P', 'g5': 'P'},
                   {'c7c8': '前兵进一', 'c6b6': '中兵平八', 'c5d5': '后兵平六', 'g5g6': '兵三进一'})

    def test_four_and_five_pawns_one_file(self):
        self.check({'c8': 'P', 'c7': 'P', 'c6': 'P', 'c5': 'P'},
                   {'c8c9': '一兵进一', 'c7b7': '二兵平八', 'c6d6': '三兵平六', 'c5b5': '四兵平八'})
        self.check({'c9': 'P', 'c8': 'P', 'c7': 'P', 'c6': 'P', 'c5': 'P'}, {'c5b5': '五兵平八', 'c9b9': '一兵平八'})

    def test_three_plus_two_pawns(self):
        # 六线（d）三兵、三线（g）两兵：先纵线号小的三线，同线从前往后
        self.check({'d7': 'P', 'd6': 'P', 'd5': 'P', 'g6': 'P', 'g5': 'P'},
                   {'g6g7': '一兵进一', 'g5h5': '二兵平二', 'd7d8': '三兵进一', 'd6c6': '四兵平七', 'd5e5': '五兵平五'})

    def test_black_pawns_front_is_downward(self):
        self.check({'c3': 'p', 'c4': 'p', 'a0': 'R'}, {'c3c2': '前卒进１', 'c4b4': '后卒平２'}, turn='b')

    def test_rook_knight_cannon_same_file(self):
        self.check({'a0': 'R', 'a4': 'R'}, {'a4a5': '前车进一', 'a0b0': '后车平八'})
        self.check({'b2': 'N', 'b5': 'N'}, {'b5c7': '前马进七', 'b2a0': '后马退九'})
        self.check({'h2': 'C', 'h5': 'C'}, {'h5e5': '前炮平五', 'h2h1': '后炮退一'})
        self.check({'a9': 'r', 'a5': 'r'}, {'a9b9': '后车平２', 'a5a4': '前车进１'}, turn='b')

    def test_advisor_bishop_same_file_no_prefix(self):
        self.check({'f0': 'A', 'f2': 'A'}, {'f2e1': '仕四退五', 'f0e1': '仕四进五'})
        self.check({'c0': 'B', 'c4': 'B'}, {'c4e2': '相七退五', 'c0e2': '相七进五'})


if __name__ == '__main__':
    unittest.main()
