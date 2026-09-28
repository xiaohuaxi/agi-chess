"""棋谱里每步的元信息（records.move_meta / meta_comment，两个棋种的 exports，cli export）。离线，不调模型。

用 tempfile.mkdtemp() 建独立目录，跑完删掉；不碰仓库里的 runs/。
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import chess.pgn

from llmchess import chess_ as C, cli, records
from llmchess import xiangqi as X


def chat_attempt(ply, side, meta, usage, elapsed, legal=True, **kw):
    """llm-chat 路径的一条 attempt：原始返回在 claude.meta，换算后的在 usage。"""
    return dict({'type': 'attempt', 'ply': ply, 'side': side, 'try': 1, 'player': 'x', 'legal': legal,
                 'usage': usage, 'elapsed': elapsed, 'claude': {'result': '', 'meta': meta, 'is_error': False}}, **kw)


def move(ply, side, **stat):
    s = records.new_stat()
    s.update(stat)
    return {'type': 'move', 'ply': ply, 'side': side, 'move': 'm%d' % ply, 'stat': s}


CLAUDE_META = {'input_tokens': 2, 'cache_read': 100, 'cache_write': 50, 'output_tokens': 300, 'reasoning_tokens': 280}
CLAUDE_U = {'in': 2, 'cache_read': 100, 'cache_write': 50, 'out': 300, 'think': 280}
DS_META = {'input_tokens': 900, 'cache_read': 400, 'cache_write': None, 'output_tokens': 60, 'reasoning_tokens': None}
DS_U = {'in': 500, 'cache_read': 400, 'cache_write': 0, 'out': 60, 'think': 0}


class MoveMeta(unittest.TestCase):
    def test_sums_attempts_and_counts(self):
        recs = [chat_attempt(1, 'w', CLAUDE_META, CLAUDE_U, 10.4, legal=False),
                chat_attempt(1, 'w', CLAUDE_META, CLAUDE_U, 5.3),
                move(1, 'w', illegal=1)]
        m = records.move_meta(recs)[1]
        self.assertEqual((m['think'], m['out'], m['in'], m['cache_read'], m['cache_write']), (560, 600, 4, 200, 100))
        self.assertEqual((m['calls'], m['illegal'], m['flagged'], m['empty']), (2, 1, 0, 0))
        self.assertAlmostEqual(m['emt'], 15.7)

    def test_missing_fields_stay_missing(self):
        # DeepSeek 没给思考 token 和缓存写：换算后的 usage 里是 0，但导出不能把它当成 0
        m = records.move_meta([chat_attempt(1, 'b', DS_META, DS_U, 3.0), move(1, 'b')])[1]
        self.assertIsNone(m['think'])
        self.assertIsNone(m['cache_write'])
        self.assertEqual((m['out'], m['cache_read']), (60, 400))
        c = records.meta_comment(m)
        self.assertNotIn('%think', c)
        self.assertNotIn('%cachewrite', c)
        self.assertIn('[%out 60]', c)

    def test_blocked_attempt_without_usage_makes_tokens_unknown(self):
        blocked = {'type': 'attempt', 'ply': 1, 'side': 'w', 'try': 1, 'flagged': True, 'elapsed': 2.0,
                   'usage': dict.fromkeys(CLAUDE_U, 0), 'claude': {'result': 'x', 'stop_reason': 'refusal', 'is_error': True}}
        recs = [blocked, chat_attempt(1, 'w', CLAUDE_META, CLAUDE_U, 4.0), move(1, 'w', flags=1)]
        m = records.move_meta(recs)[1]
        self.assertIsNone(m['think'])               # 不部分相加
        self.assertEqual((m['calls'], m['flagged']), (2, 1))
        self.assertIn('[%flagged 1]', records.meta_comment(m))

    def test_legacy_backends(self):
        claude_p = {'type': 'attempt', 'ply': 1, 'side': 'w', 'elapsed': 6.0, 'usage': CLAUDE_U,
                    'claude': {'usage': {'input_tokens': 2, 'cache_read_input_tokens': 100, 'cache_creation_input_tokens': 50,
                                         'output_tokens': 300, 'output_tokens_details': {'thinking_tokens': 280}}}}
        codex_exec = {'type': 'attempt', 'ply': 2, 'side': 'b', 'elapsed': 7.0, 'usage': {'in': 10, 'out': 5, 'think': 3},
                      'claude': {'usage': {'input_tokens': 10, 'cached_input_tokens': 0, 'output_tokens': 5,
                                           'reasoning_output_tokens': 3}}}
        meta = records.move_meta([claude_p, move(1, 'w'), codex_exec, move(2, 'b')])
        self.assertEqual((meta[1]['think'], meta[1]['cache_write']), (280, 50))
        self.assertEqual(meta[2]['think'], 3)
        self.assertIsNone(meta[2]['cache_write'])   # 这条原始用量里没有缓存写

    def test_engine_random_and_opening_plies_have_no_meta(self):
        recs = [{'type': 'move', 'ply': 1, 'side': 'w', 'move': 'a', 'opening': True, 'stat': records.new_stat()},
                {'type': 'attempt', 'ply': 2, 'side': 'b', 'player': 'engine:fsf', 'elapsed': 0.1, 'move': 'b'},
                move(2, 'b')]
        self.assertEqual(records.move_meta(recs), {})
        self.assertEqual(records.meta_comment(None), '')

    def test_emt_format(self):
        self.assertEqual(records.emt(0.4), '0:00:00')
        self.assertEqual(records.emt(17.6), '0:00:18')
        self.assertEqual(records.emt(3725), '1:02:05')


class ExportsWithMeta(unittest.TestCase):
    META = {1: {'emt': 12.0, 'think': 280, 'out': 300, 'in': 2, 'cache_read': 100, 'cache_write': 50,
                'illegal': 1, 'flagged': 0, 'empty': 0, 'calls': 2}}

    def test_chess_pgn_comment_reads_back(self):
        st = C.start()
        for mv in ['e2e4', 'e7e5']:
            C.push(st, mv)
        cfg = {'tag': 't', 'players': {'w': 'claude:opus', 'b': 'engine:stockfish'}}
        pgn = C.exports(st, cfg, {'winner': None, 'reason': 'x'}, [], self.META)['game.pgn']
        self.assertIn('1. e4 { [%emt 0:00:12] [%think 280] [%out 300]', pgn)
        g = chess.pgn.read_game(io.StringIO(pgn))
        first, second = list(g.mainline())
        self.assertEqual(first.emt(), 12)            # 标准阅读器认 %emt
        self.assertIn('[%illegal 1]', first.comment)  # 自定义命令原样留在评注里
        self.assertEqual(second.comment, '')

    def test_chess_without_meta_unchanged(self):
        st = C.start()
        C.push(st, 'e2e4')
        cfg = {'tag': 't', 'players': {'w': 'random', 'b': 'random'}}
        self.assertNotIn('{', C.exports(st, cfg, {'winner': None, 'reason': 'x'}, [])['game.pgn'])

    def test_xiangqi_record_comment(self):
        st = X.start()
        for mv in ['h2e2', 'h9g7']:
            X.push(st, mv)
        cfg = {'tag': 't', 'players': {'w': 'claude:opus', 'b': 'engine:fsf'}}
        txt = X.exports(st, cfg, {'winner': None, 'reason': 'x'}, [], self.META)['record.txt']
        self.assertIn('1. %s {[%%emt 0:00:12] [%%think 280] [%%out 300] [%%in 2] [%%cacheread 100]\n'
                      '[%%cachewrite 50] [%%illegal 1]}\n1... %s\n' % (st['record'][0], st['record'][1]), txt)

    def test_xiangqi_without_meta_keeps_pair_lines(self):
        st = X.start()
        for mv in ['h2e2', 'h9g7']:
            X.push(st, mv)
        cfg = {'tag': 't', 'players': {'w': 'random', 'b': 'random'}}
        txt = X.exports(st, cfg, {'winner': None, 'reason': 'x'}, [])['record.txt']
        self.assertIn('1. %s　%s\n' % tuple(st['record']), txt)

    def test_chess_reason_text_escaped_and_wrapped(self):
        why = ('I play e4 to grab the centre {and keep 50% of options} [%fake 1]\n\n' + '中路控制很重要，' * 30)
        meta = {1: dict(self.META[1], why=why), 2: dict(self.META[1], illegal=0)}
        st = C.start()
        for mv in ['e2e4', 'e7e5', 'g1f3']:
            C.push(st, mv)
        cfg = {'tag': 't', 'players': {'w': 'claude:opus', 'b': 'claude:opus'}}
        pgn = C.exports(st, cfg, {'winner': None, 'reason': 'x'}, [], meta)['game.pgn']
        for line in pgn.splitlines():
            self.assertLess(records.cols(line), 80, line)       # 全角字符算 2 列
            self.assertLess(len(line.encode('utf-8')), 255, line)
        flat = ' '.join(pgn.split())
        self.assertIn('｛and keep 50％ of options｝ [％fake 1]', flat)
        self.assertNotIn('[%fake', pgn)
        g = chess.pgn.read_game(io.StringIO(pgn))
        nodes = list(g.mainline())
        self.assertEqual([n.san() for n in nodes], ['e4', 'e5', 'Nf3'])
        self.assertEqual(nodes[0].emt(), 12)
        self.assertIn('中路控制很重要', nodes[0].comment)
        self.assertEqual(nodes[1].emt(), 12)
        self.assertEqual(nodes[2].comment, '')
        self.assertIn('2. Nf3', pgn)
        self.assertIn('1... e5', pgn)          # 评注后面的黑方着法补「N...」


class ExtractReason(unittest.TestCase):
    def test_cuts_at_last_move_marker(self):
        from llmchess import memory
        self.assertEqual(memory.extract_reason('先出车，Nf3 也可以。\n\n**着法: e2e4**'), '先出车，Nf3 也可以。')
        self.assertEqual(memory.extract_reason('应当写皇后的着法：\n\n着法: g3e3'), '应当写皇后的着法：')
        self.assertEqual(memory.extract_reason('Develop.\nMove: Nf3'), 'Develop.')
        self.assertEqual(memory.extract_reason('Develop the knight.\nNf3'), 'Develop the knight.')
        self.assertIsNone(memory.extract_reason('着法: e2e4'))
        self.assertIsNone(memory.extract_reason('e2e4'))

    def test_move_meta_takes_reason_from_legal_attempt(self):
        bad = chat_attempt(1, 'w', CLAUDE_META, CLAUDE_U, 1.0, legal=False, move=None, reply='乱写\n着法: z9')
        good = chat_attempt(1, 'w', CLAUDE_META, CLAUDE_U, 1.0, move='m1', reply='出子。\n着法: m1')
        m = records.move_meta([bad, good, move(1, 'w', illegal=1)])[1]
        self.assertEqual(m['why'], '出子。')


class ExportCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def quiet(self, argv):
        with contextlib.redirect_stdout(io.StringIO()):
            return cli.main(argv)

    def test_reexport_finished_game_adds_meta_without_touching_log(self):
        out = os.path.join(self.tmp, 'runs')
        self.assertEqual(self.quiet(['play', '--game', 'chess', '--tag', 'c1', '--out', out, '--white', 'random',
                                     '--black', 'random', '--seed', '3', '--max-plies', '4']), 0)
        run_dir = os.path.join(out, 'c1')
        log = os.path.join(run_dir, 'game.jsonl')
        # 把第 1 个半回合改成「模型下的」：补一条带用量的 attempt（真实记录里模型的每次调用都有这条）
        lines = open(log, encoding='utf-8').read().splitlines()
        i = next(k for k, l in enumerate(lines) if json.loads(l)['type'] == 'move')
        lines.insert(i, json.dumps(chat_attempt(1, 'w', CLAUDE_META, CLAUDE_U, 9.0)))
        with open(log, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        before = open(log, 'rb').read()
        self.assertEqual(self.quiet(['export', run_dir]), 0)
        self.assertEqual(open(log, 'rb').read(), before)        # 重新导出不写记录
        pgn = open(os.path.join(run_dir, 'game.pgn'), encoding='utf-8').read()
        self.assertIn('[%emt 0:00:09] [%think 280] [%out 300]', pgn)
        self.assertEqual(pgn.count('[%emt'), 1)                   # 随机走子的半回合不带

    def test_unfinished_game_refused(self):
        out = os.path.join(self.tmp, 'runs')
        self.quiet(['play', '--game', 'xiangqi', '--tag', 'x1', '--out', out, '--red', 'random', '--black', 'random',
                    '--seed', '3', '--max-plies', '10', '--stop-after', '2'])
        with self.assertRaises(SystemExit):
            self.quiet(['export', os.path.join(out, 'x1')])


if __name__ == '__main__':
    unittest.main()
