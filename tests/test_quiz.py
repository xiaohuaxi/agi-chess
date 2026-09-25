"""局面题模式的离线测试：局面加载、状态构造、提示、作答记录与续跑（claude 调用换成假的）、规则判定、lichess 判级、引擎判定。

绝不调 claude：claude_cli.call / version 都打桩。记录写进 tempfile.mkdtemp() 的独立目录，跑完删掉。
"""
import contextlib, io, json, os, shutil, tempfile, unittest
from unittest import mock

import chess

from llmchess import claude_cli, quiz as Q, records, runner
from llmchess.claude_cli import Paused


def fake_reply(text, think=50):
    return {'result': text, 'stop_reason': 'end_turn', 'total_cost_usd': 0.01, 'session_id': 'x', 'duration_ms': 10,
            'usage': {'input_tokens': 10, 'output_tokens': think + 10, 'output_tokens_details': {'thinking_tokens': think}}}


def positions(game):
    return Q.load_positions(Q.positions_path('batch1', game))


def quiet(fn, *a):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a)


class Positions(unittest.TestCase):
    def test_both_sets_load_and_rebuild(self):
        for game in Q.GAMES:
            ps = positions(game)
            self.assertEqual(len(ps), 30, game)
            self.assertEqual(len({p['id'] for p in ps}), 30)
            for p in ps:
                st = Q.build_state(p)           # 内部断言重放出的局面和题目 FEN 一致
                G = Q.game_module(game)
                self.assertEqual(G.turn(st), p['turn'])
                self.assertIn(p['prev_move'] if game == 'xiangqi' else p['solution'], G.legal(st))

    def test_xiangqi_state_keeps_full_history(self):
        p = positions('xiangqi')[0]
        st = Q.build_state(p)
        self.assertEqual(st['moves'], p['moves'])
        self.assertEqual(len(st['fens']), len(p['moves']) + 1)

    def test_chess_rating_spread(self):
        rs = [p['rating'] for p in positions('chess')]
        self.assertTrue(min(rs) >= 800 and max(rs) < 2000)


class Prompts(unittest.TestCase):
    def test_xiangqi_no_history_but_last_move(self):
        p = positions('xiangqi')[0]
        st = Q.build_state(p)
        G = Q.game_module('xiangqi')
        text = Q.prompt_of(G, st, Q.side_cfg(G, 'medium'))
        self.assertIn('对方刚走', text)
        self.assertNotIn('着法记录', text)
        self.assertIn('已走 %d 个半回合' % len(p['moves']), text)

    def test_chess_head_uses_real_move_number(self):
        p = positions('chess')[0]
        st = Q.build_state(p)
        G = Q.game_module('chess')
        text = Q.prompt_of(G, st, Q.side_cfg(G, 'medium'))
        b = chess.Board(p['fen'])
        self.assertTrue(text.startswith('第 %d 回合' % b.fullmove_number), text[:40])
        self.assertIn('对方刚走：%s（%s）' % (p['opp_move_san'], p['opp_move']), text)
        self.assertIn('FEN：' + p['fen'], text)

    def test_system_prompt_same_as_whole_game(self):
        G = Q.game_module('xiangqi')
        cfg = Q.quiz_cfg(G, 'xiangqi', 'w', 'high', 'opus', '/tmp/x')
        self.assertIn('满 200 个半回合', cfg['system']['w'])
        self.assertEqual(cfg['sides']['w']['history'], 0)
        self.assertIn('--effort', claude_cli.command('opus', 'high', '-'))


class Answering(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-quiz-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cwd = os.path.join(self.tmp, 'cwd')
        os.makedirs(self.cwd)

    def run_one(self, pos, effort='medium', rep=1):
        return quiet(Q.answer_one, pos, effort, rep, self.tmp, 'opus', self.cwd, {'commit': 'test'})

    def test_illegal_then_legal(self):
        p = positions('chess')[0]
        replies = iter([fake_reply('着法: a1a1'), fake_reply('思路……\n着法: %s' % p['solution_san'], think=77)])
        with mock.patch.object(claude_cli, 'call', lambda *a, **k: (next(replies), 1.5)):
            res = self.run_one(p)
        self.assertEqual(res['move'], p['solution'])
        self.assertFalse(res['first_legal'])
        self.assertEqual(res['attempts'], 2)
        self.assertEqual(res['stat']['illegal'], 1)
        self.assertEqual(res['stat']['think'], 127)
        # 再跑一次直接拿记录里的结果，不再调用
        with mock.patch.object(claude_cli, 'call', side_effect=AssertionError('不该再调')):
            self.assertEqual(self.run_one(p)['move'], p['solution'])

    def test_quota_pause_then_resume(self):
        p = positions('xiangqi')[0]
        replies = iter([fake_reply('着法: a0a0')])

        def call_then_quota(*a, **k):
            try:
                return next(replies), 1.0
            except StopIteration:
                raise Paused('额度限制：test')
        with mock.patch.object(claude_cli, 'call', call_then_quota):
            with self.assertRaises(Paused):
                self.run_one(p)
        path = Q.answer_path(self.tmp, p['id'], 'medium', 1)
        self.assertIsNone(Q.result_of(path))
        self.assertIn('pause', [r['type'] for r in records.read(path)])
        with mock.patch.object(claude_cli, 'call', lambda *a, **k: (fake_reply('着法: %s' % p['prev_move']), 1.0)):
            res = self.run_one(p)
        self.assertEqual(res['move'], p['prev_move'])
        self.assertEqual(res['attempts'], 2)                 # 续跑接上了暂停前那次非法尝试
        self.assertFalse(res['first_legal'])

    def test_too_many_flags_gives_up_this_one_only(self):
        p = positions('chess')[1]
        blocked = dict(fake_reply('Opus safeguards flagged this message'), stop_reason='refusal')
        with mock.patch.object(claude_cli, 'call', lambda *a, **k: (blocked, 1.0)):
            res = self.run_one(p)
        self.assertEqual(res['gave_up'], 'flags')
        self.assertIsNone(res['move'])
        self.assertEqual(res['stat']['flags'], runner.MAX_FLAGS + 1)

    def test_run_command_parallel_and_skip(self):
        out = os.path.join(self.tmp, 'batch')

        def good(cmd, prompt, cwd, **k):
            fen = prompt.split('FEN：')[1].split()[0:6]
            b = chess.Board(' '.join(fen))
            return fake_reply('着法: %s' % next(iter(b.legal_moves)).uci()), 0.1
        argv = ['run', '--game', 'chess', '--ids', 'c01,c02', '--efforts', 'medium,max', '--reps', '1',
                '--jobs', '2', '--out', out]
        with mock.patch.object(claude_cli, 'call', good), mock.patch.object(claude_cli, 'version', lambda: 'test'):
            self.assertEqual(quiet(Q.main, argv), 0)
        with open(os.path.join(out, 'chess', 'batch.json'), encoding='utf-8') as f:
            meta = json.load(f)
        self.addCleanup(shutil.rmtree, meta['claude_cwd'], ignore_errors=True)
        done = [n for n in os.listdir(os.path.join(out, 'chess')) if n.startswith('c0')]
        self.assertEqual(len(done), 4)
        with mock.patch.object(claude_cli, 'call', side_effect=AssertionError('不该再调')):
            self.assertEqual(quiet(Q.main, argv), 0)


class StaticLabels(unittest.TestCase):
    def test_xiangqi_reproduces_last_round_flags(self):
        R = Q.rules_for('xiangqi')
        for p in positions('xiangqi')[:3]:          # x01 白送子、x02 白送子、x03 漏吃
            lab = Q.labels(Q.static_table(R, p['fen']), p['prev_move'])
            self.assertEqual(lab['hang'], '白送子' in p['prev_flags'], p['id'])
            self.assertEqual(lab['missed_capture'], '漏吃' in p['prev_flags'], p['id'])

    def test_chess_hang_missed_capture_mate(self):
        R = Q.rules_for('chess')
        # 白后 d1、黑后 d5 无保护：Qxd5 是白吃，走 a3 就是漏吃
        fen = '4k3/8/8/3q4/8/8/P7/3QK3 w - - 0 1'
        tab = Q.static_table(R, fen)
        self.assertTrue(Q.labels(tab, 'a2a3')['missed_capture'])
        self.assertFalse(Q.labels(tab, 'd1d5')['missed_capture'])
        # 白后走到黑后嘴里（b5，黑后 d5 横着吃得到），无保护：白送子
        fen2 = '4k3/8/8/3q4/8/8/P7/1Q2K3 w - - 0 1'
        tab2 = Q.static_table(R, fen2)
        self.assertTrue(Q.labels(tab2, 'b1b5')['hang'])
        self.assertFalse(Q.labels(tab2, 'a2a3')['hang'])
        # 一步杀：Ra8#，不走就是漏杀
        fen3 = '6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1'
        tab3 = Q.static_table(R, fen3)
        self.assertEqual(tab3['mates'], ['a1a8'])
        self.assertTrue(Q.labels(tab3, 'h2h3')['missed_mate'])
        self.assertFalse(Q.labels(tab3, 'a1a8')['missed_mate'])


class LichessJudgement(unittest.TestCase):
    def test_cp_thresholds(self):
        self.assertIsNone(Q.lichess_judgement({'cp': 0}, {'cp': -50}))
        self.assertEqual(Q.lichess_judgement({'cp': 0}, {'cp': -300}), 'blunder')     # 0.30 → -0.49
        self.assertEqual(Q.lichess_judgement({'cp': 0}, {'cp': -120}), 'mistake')     # 降约 0.22
        self.assertIsNone(Q.lichess_judgement({'cp': 900}, {'cp': 700}))              # 高分段降得少（0.93 → 0.86）

    def test_mate_rules(self):
        self.assertEqual(Q.lichess_judgement({'cp': 50}, {'mate': -3}), 'blunder')    # 走进被杀
        self.assertEqual(Q.lichess_judgement({'mate': 2}, {'cp': 300}), 'blunder')    # 放走杀棋
        self.assertEqual(Q.lichess_judgement({'mate': 2}, {'cp': 1200}), 'inaccuracy')
        self.assertIsNone(Q.lichess_judgement({'mate': 2}, {'mate': 4}))
        self.assertIsNone(Q.lichess_judgement({'mate': 1}, {'mate': 0}))              # 将死了


class JudgeWithEngine(unittest.TestCase):
    """真起 Stockfish（浅层）判两条假作答，看 judged.jsonl 的字段通不通。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-quiz-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_judge_and_report(self):
        p = [x for x in positions('chess') if x['pick_theme'] == 'mateIn1'][0]
        d = os.path.join(self.tmp, 'chess')
        os.makedirs(d)
        b = chess.Board(p['fen'])
        bad = next(m.uci() for m in b.legal_moves if m.uci() != p['solution'])
        for rep, mv in ((1, p['solution']), (2, bad)):
            stat = records.new_stat()
            records.write(Q.answer_path(d, p['id'], 'medium', rep),
                          {'type': 'result', 'pos': p['id'], 'game': 'chess', 'effort': 'medium', 'rep': rep,
                           'side': p['turn'], 'move': mv, 'forfeit': False, 'gave_up': None, 'attempts': 1,
                           'first_legal': True, 'first_think': 10, 'stat': stat})
        with mock.patch.object(Q, 'CHESS_DEPTH', 8):
            rows, path = quiet(Q.judge_game, 'chess', 'batch1', self.tmp)
        rows = {r['rep']: r for r in rows}
        self.assertTrue(rows[1]['solved'])
        self.assertEqual(rows[1]['after'], {'mate': 0})
        self.assertFalse(rows[2]['solved'])
        self.assertTrue(rows[2]['missed_mate'])
        self.assertGreater(rows[2]['loss'], 0)
        self.assertEqual(quiet(Q.main, ['report', '--out', self.tmp]), 0)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, 'report.txt')))


if __name__ == '__main__':
    unittest.main()
