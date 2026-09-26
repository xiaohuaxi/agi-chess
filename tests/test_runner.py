"""离线整盘测试：runner.py 的对局循环 + cli.py 的入口，走 random / engine 棋手，绝不调 claude。

用 tempfile.mkdtemp() 建独立目录跑，跑完删掉；不碰仓库里的 runs/。
"""
import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from llmchess import chess_ as C, claude_cli, cli, quiz, records, runner
from llmchess import xiangqi as X
from llmchess.claude_cli import Paused


def run_quiet(argv):
    """跑 cli.main，把它往 stdout 打的棋谱、进度都吞掉，只要返回码。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(argv)
    return rc


class WholeGameOffline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_xiangqi_random_vs_engine(self):
        out = os.path.join(self.tmp, 'runs')
        rc = run_quiet(['play', '--game', 'xiangqi', '--tag', 'x1', '--out', out,
                        '--red', 'random', '--black', 'engine:fsf:nodes=1',
                        '--seed', '5', '--max-plies', '10'])
        self.assertEqual(rc, 0)
        run_dir = os.path.join(out, 'x1')
        recs = records.read(os.path.join(run_dir, 'game.jsonl'))
        self.assertEqual(recs[0]['type'], 'config')
        ends = [r for r in recs if r['type'] == 'end']
        self.assertEqual(len(ends), 1)
        self.assertGreater(len(ends[0]['moves']), 0)
        self.assertTrue(os.path.exists(os.path.join(run_dir, 'record.txt')))
        players = {r.get('player') for r in recs if r['type'] == 'attempt'}
        self.assertEqual(players, {'random', 'engine:fsf:nodes=1'})

    def test_chess_random_vs_random(self):
        out = os.path.join(self.tmp, 'runs')
        rc = run_quiet(['play', '--game', 'chess', '--tag', 'c1', '--out', out,
                        '--white', 'random', '--black', 'random',
                        '--seed', '7', '--max-plies', '10'])
        self.assertEqual(rc, 0)
        run_dir = os.path.join(out, 'c1')
        recs = records.read(os.path.join(run_dir, 'game.jsonl'))
        ends = [r for r in recs if r['type'] == 'end']
        self.assertEqual(len(ends), 1)
        self.assertTrue(os.path.exists(os.path.join(run_dir, 'record.txt')))
        self.assertTrue(os.path.exists(os.path.join(run_dir, 'game.pgn')))


class ResumeReproducesRandomSeed(unittest.TestCase):
    """随机走子按 (种子, 半回合号) 起随机数，和暂停/续跑无关：直接一口气下完，
    和"中途暂停再续跑"应该走出完全一样的着法序列。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _moves_of(self, run_dir):
        recs = records.read(os.path.join(run_dir, 'game.jsonl'))
        return [r['move'] for r in recs if r['type'] == 'move']

    def test_xiangqi_stop_and_resume_matches_direct_run(self):
        common = ['--game', 'xiangqi', '--red', 'random', '--black', 'random',
                 '--seed', '99', '--max-plies', '12']

        out_direct = os.path.join(self.tmp, 'direct')
        rc = run_quiet(['play', '--tag', 'x'] + common + ['--out', out_direct])
        self.assertEqual(rc, 0)
        direct_moves = self._moves_of(os.path.join(out_direct, 'x'))
        self.assertEqual(len(direct_moves), 12)

        out_resumed = os.path.join(self.tmp, 'resumed')
        rc1 = run_quiet(['play', '--tag', 'x'] + common + ['--out', out_resumed, '--stop-after', '5'])
        self.assertEqual(rc1, 3, '按 --stop-after 停下应该退出码 3')
        run_dir = os.path.join(out_resumed, 'x')
        mid_types = [r['type'] for r in records.read(os.path.join(run_dir, 'game.jsonl'))]
        self.assertIn('pause', mid_types)
        self.assertEqual(len(self._moves_of(run_dir)), 5)

        rc2 = run_quiet(['resume', run_dir])
        self.assertEqual(rc2, 0)
        resumed_moves = self._moves_of(run_dir)
        self.assertEqual(resumed_moves, direct_moves)

    def test_resume_on_finished_game_refuses(self):
        out = os.path.join(self.tmp, 'runs')
        run_quiet(['play', '--game', 'xiangqi', '--tag', 'x2', '--out', out,
                  '--red', 'random', '--black', 'random', '--seed', '1', '--max-plies', '4'])
        run_dir = os.path.join(out, 'x2')
        with self.assertRaises(SystemExit):
            cli.main(['resume', run_dir])


class RepeatedPositionDetectedAfterReload(unittest.TestCase):
    """手写一份 game.jsonl（config 行 + 几条 move 行），让局面在重放之后恰好第三次重复；
    runner.load() 把完整历史重建出来后，G.ending() 应该能判出和棋——这是"续跑后重复局面还能判"的核心保证：
    ending() 靠的是完整着法历史，和当时给模型看了多少 history 无关。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_xiangqi_repetition_survives_reload(self):
        run_dir = os.path.join(self.tmp, 'rep1')
        os.makedirs(run_dir)
        log = os.path.join(run_dir, 'game.jsonl')

        cfg = {'game': 'xiangqi', 'tag': 'rep1', 'players': {'w': 'random', 'b': 'random'},
               'sides': {'w': {'memory': 'stateless'}, 'b': {'memory': 'stateless'}},
               'seed': 1, 'retries': 3, 'max_plies': 200}
        records.write(log, {'type': 'config', 'cfg': cfg})

        # 双方各自的马来回跳（b0<->c2、b9<->c7），两步一循环，跳两轮后回到开局局面第三次
        moves = ['b0c2', 'b9c7', 'c2b0', 'c7b9'] * 2
        sides = ['w', 'b'] * 4
        st = X.start()
        for i, (mv, side) in enumerate(zip(moves, sides)):
            X.push(st, mv)
            stat = records.new_stat()
            stat['attempts'] = 1
            stat['side'] = side
            records.write(log, {'type': 'move', 'ply': i + 1, 'side': side, 'move': mv,
                                'text': st['record'][-1], 'check': X.in_check(st), 'note': None, 'stat': stat})

        ctx = runner.load(X, run_dir)
        self.assertIsNone(ctx['end'], '手写的记录里没写 end，load() 不该自己编一个出来')
        self.assertEqual(ctx['st']['moves'], moves)
        end = X.ending(ctx['st'])
        self.assertEqual(end, {'winner': None, 'reason': '同一局面出现三次，判和'})


class SessionCostIsCumulative(unittest.TestCase):
    """claude -p --resume 返回的 total_cost_usd 是整段会话的累计值：session 档每次调用的花费要按会话做差，
    续跑时从记录里接上一次的累计值；stateless 原样记。claude 调用打桩，不真调。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def make_ctx(self, mem):
        run_dir = os.path.join(self.tmp, 'run-' + mem)
        os.makedirs(run_dir)
        sc = dict(quiz.side_cfg(C, 'medium'), memory=mem)
        cfg = {'game': 'chess', 'players': {'w': 'claude:opus', 'b': 'random'}, 'sides': {'w': sc, 'b': dict(sc)},
               'retries': 3, 'max_plies': 200, 'seed': 1, 'system': {'w': 'sys', 'b': 'sys'},
               'claude_cwd': os.path.join(run_dir, 'cwd')}
        ctx = runner.new_ctx(C, cfg, run_dir)
        runner.log(ctx, {'type': 'config', 'cfg': cfg})
        return ctx

    @staticmethod
    def fake_call(totals, seen):
        """按顺序回放累计花费：(文本, 累计值)；用完抛 Paused。会话 id 取命令行里的那个，seen 记下每次的会话参数。"""
        it = iter(totals)

        def call(cmd, prompt, cwd, **k):
            try:
                text, total = next(it)
            except StopIteration:
                raise Paused('额度限制：test')
            flag = next((x for x in ('--session-id', '--resume') if x in cmd), None)
            seen.append(flag)
            sid = cmd[cmd.index(flag) + 1] if flag else 'x'
            return {'result': text, 'stop_reason': 'end_turn', 'total_cost_usd': total, 'session_id': sid,
                    'usage': {'input_tokens': 10, 'output_tokens': 20}}, 1.0
        return call

    def turn(self, ctx):
        st = ctx['st']
        moves = C.legal(st)
        with contextlib.redirect_stdout(io.StringIO()):
            return runner.model_turn(ctx, 'w', moves, C.banned(st, moves))

    def attempts(self, ctx):
        return [r for r in records.read(ctx['log']) if r['type'] == 'attempt']

    def test_session_deltas_and_resume(self):
        ctx = self.make_ctx('session')
        seen = []
        # 非法 0.01 → 空回复累计 0.03 → 撞额度暂停
        with mock.patch.object(claude_cli, 'call', self.fake_call([('着法: a1a1', 0.01), ('', 0.03)], seen)):
            with self.assertRaises(Paused):
                self.turn(ctx)
        runner.log(ctx, {'type': 'pause', 'ply': 0, 'why': 'test'})
        ctx2 = runner.load(C, ctx['dir'])
        sid = ctx['sessions']['w']
        self.assertEqual(ctx2['sessions']['w'], sid)
        self.assertAlmostEqual(ctx2['cost_total'][sid], 0.03)      # 续跑从记录里接上累计值
        self.assertAlmostEqual(ctx2['pending']['stat']['cost'], 0.03)
        with mock.patch.object(claude_cli, 'call', self.fake_call([('着法: e2e4', 0.06)], seen)):
            mv, stat, _ = self.turn(ctx2)
        self.assertEqual(mv, 'e2e4')
        self.assertEqual(seen, ['--session-id', '--resume', '--resume'])
        atts = self.attempts(ctx)
        self.assertTrue(atts[1]['empty'])
        for a, cost, total in zip(atts, (0.01, 0.02, 0.03), (0.01, 0.03, 0.06)):
            self.assertAlmostEqual(a['usage']['cost'], cost)
            self.assertAlmostEqual(a['usage']['cost_total'], total)
        self.assertAlmostEqual(stat['cost'], 0.06)

    def test_session_old_records_resume(self):
        """旧记录没有 cost_total、cost 就是累计值：pending 统计和续跑后的做差照样对。"""
        ctx = self.make_ctx('session')
        base = {'type': 'attempt', 'ply': 1, 'side': 'w', 'player': 'claude:opus', 'session': 's1', 'elapsed': 1.0}
        runner.log(ctx, dict(base, **{'try': 1, 'legal': False, 'move_text': 'a1a1', 'reason': 'x',
                                      'usage': {'cost': 0.02}}))
        runner.log(ctx, dict(base, **{'try': 2, 'legal': False, 'move_text': 'a1a1', 'reason': 'x',
                                      'usage': {'cost': 0.05}}))
        ctx2 = runner.load(C, ctx['dir'])
        self.assertAlmostEqual(ctx2['pending']['stat']['cost'], 0.05)
        with mock.patch.object(claude_cli, 'call', self.fake_call([('着法: e2e4', 0.09)], [])):
            mv, stat, _ = self.turn(ctx2)
        self.assertAlmostEqual(self.attempts(ctx)[-1]['usage']['cost'], 0.04)
        self.assertAlmostEqual(stat['cost'], 0.09)

    def test_stateless_unchanged(self):
        ctx = self.make_ctx('stateless')
        with mock.patch.object(claude_cli, 'call', self.fake_call([('着法: a1a1', 0.01), ('着法: e2e4', 0.01)], [])):
            mv, stat, _ = self.turn(ctx)
        self.assertEqual(mv, 'e2e4')
        for a in self.attempts(ctx):
            self.assertAlmostEqual(a['usage']['cost'], 0.01)
            self.assertNotIn('cost_total', a['usage'])
        self.assertAlmostEqual(stat['cost'], 0.02)

    def test_call_fail_logged_with_ply_and_timeout_passed(self):
        ctx = self.make_ctx('stateless')
        ctx['cfg']['timeout'] = 77
        seen = []

        def call(cmd, prompt, cwd, **k):
            seen.append(k['timeout'])
            k['on_fail']({'try': 1, 'timeout': True, 'rc': -1, 'elapsed': 77.0, 'stderr': 'timeout 77s', 'stdout': '',
                          'next_wait': 30})
            return {'result': '着法: e2e4', 'stop_reason': 'end_turn', 'usage': {}}, 1.0
        with mock.patch.object(claude_cli, 'call', call):
            mv, _, _ = self.turn(ctx)
        self.assertEqual((mv, seen), ('e2e4', [77]))
        fails = [r for r in records.read(ctx['log']) if r['type'] == 'call_fail']
        self.assertEqual(len(fails), 1)
        self.assertEqual((fails[0]['ply'], fails[0]['side'], fails[0]['attempt'], fails[0]['timeout']), (1, 'w', 1, True))

    def test_limit_wait_logged_with_ply(self):
        ctx = self.make_ctx('stateless')

        def call(cmd, prompt, cwd, **k):
            k['on_wait']({'phase': 'start', 'start': 'a', 'reset_at': None, 'planned': 600, 'n': 1, 'reason': 'limit'})
            k['on_wait']({'phase': 'end', 'start': 'a', 'end': 'b', 'waited': 600, 'stopped': False})
            return {'result': '着法: e2e4', 'stop_reason': 'end_turn', 'usage': {}}, 1.0
        with mock.patch.object(claude_cli, 'call', call):
            mv, stat, _ = self.turn(ctx)
        self.assertEqual((mv, stat['illegal']), ('e2e4', 0))
        waits = [r for r in records.read(ctx['log']) if r['type'] == 'limit_wait']
        self.assertEqual([(w['phase'], w['ply'], w['side']) for w in waits], [('start', 1, 'w'), ('end', 1, 'w')])

    def test_play_records_timeout_and_chinese_prompt(self):
        out = os.path.join(self.tmp, 'runs')
        run_quiet(['play', '--game', 'chess', '--tag', 'c9', '--out', out, '--white', 'random', '--black', 'random',
                   '--seed', '1', '--max-plies', '2', '--timeout', '900'])
        cfg = records.read(os.path.join(out, 'c9', 'game.jsonl'))[0]['cfg']
        self.assertEqual(cfg['timeout'], 900)
        for G in (C, X):
            sc = quiz.side_cfg(G, 'medium')
            self.assertIn('请用中文回答。', G.system_prompt('w', sc, 'x'))

    def test_cost_delta_reset(self):
        self.assertEqual(records.cost_delta(0.5, None), 0.5)
        self.assertAlmostEqual(records.cost_delta(0.5, 0.2), 0.3)
        self.assertEqual(records.cost_delta(0.1, 0.4), 0.1)       # 累计值变小（被重置）：用原值


if __name__ == '__main__':
    unittest.main()
