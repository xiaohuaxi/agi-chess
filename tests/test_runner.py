"""离线整盘测试：runner.py 的对局循环 + cli.py 的入口，走 random / engine 棋手，绝不调 claude。

用 tempfile.mkdtemp() 建独立目录跑，跑完删掉；不碰仓库里的 runs/。
"""
import contextlib
import io
import os
import shutil
import tempfile
import unittest

from llmchess import cli, records, runner
from llmchess import xiangqi as X


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


if __name__ == '__main__':
    unittest.main()
