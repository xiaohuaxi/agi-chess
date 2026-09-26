"""离线测试：批量驱动（llmchess/batch.py）。不调 claude：盘都是 random / 引擎，下得很短。
批次放在每个用例自建的临时目录里（名字带随机后缀），用完删掉。起引擎的用例在本机没有引擎时跳过。
"""
import contextlib, io, json, os, shutil, tempfile, unittest

from llmchess import batch as B, records
from llmchess import xiangqi as X

FSF_MISSING = shutil.which('fairy-stockfish') is None and not os.path.exists('/opt/homebrew/bin/fairy-stockfish')


def run_quiet(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = B.main(argv)
    return rc, buf.getvalue()


def moves(gdir):
    return [r['move'] for r in records.read(os.path.join(gdir, 'game.jsonl')) if r['type'] == 'move']


class Helpers(unittest.TestCase):
    def test_parse_seeds(self):
        self.assertEqual(B.parse_seeds('1-3,7,2'), [1, 2, 3, 7])
        with self.assertRaises(SystemExit):
            B.parse_seeds('a-b')

    def test_specs(self):
        self.assertEqual(B.full_spec('maia-1500'), 'engine:maia-1500')
        self.assertEqual(B.full_spec('random'), 'random')
        self.assertEqual(B.full_spec('claude:opus'), 'claude:opus')
        self.assertEqual(B.slug('engine:stockfish:elo=1600'), 'stockfish-elo1600')
        self.assertEqual(B.slug('engine:fsf:nodes=10'), 'fsf-nodes10')
        self.assertEqual(B.slug('engine:maia-1100'), 'maia-1100')

    def test_wilson(self):
        lo, hi = B.wilson(5, 10)
        self.assertAlmostEqual(lo, 0.2366, places=4)
        self.assertAlmostEqual(hi, 0.7634, places=4)
        lo, hi = B.wilson(10, 10)
        self.assertAlmostEqual(lo, 0.7225, places=4)
        self.assertEqual(hi, 1.0)
        lo, hi = B.wilson(0, 4)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.4899, places=4)
        self.assertEqual(B.wilson(0, 0), (None, None))


class FakeBatchSummary(unittest.TestCase):
    """手写一个批次：4 盘中国象棋，其中两盘前 20 个半回合一模一样；另一个对手 1 盘。看得分率、区间、大失误、独立性。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bdir = os.path.join(self.tmp, 'fb')
        os.makedirs(self.bdir)

    def make(self, name, opp, side, mvs, winner, rows=None):
        gdir = os.path.join(self.bdir, name)
        os.makedirs(gdir)
        log = os.path.join(gdir, 'game.jsonl')
        players = {side: 'claude:opus', 'wb'[side == 'w']: opp}
        sc = {'effort': 'xhigh', 'memory': 'stateless'}
        records.write(log, {'type': 'config', 'cfg': {'game': 'xiangqi', 'players': players,
                                                      'sides': {'w': sc, 'b': sc}, 'opening': {'moves': mvs[:2]}}})
        for i, mv in enumerate(mvs):
            records.write(log, {'type': 'move', 'ply': i + 1, 'side': 'wb'[i % 2], 'move': mv,
                                **({'opening': True} if i < 2 else {})})
        if winner != 'unfinished':
            records.write(log, {'type': 'end', 'end': {'winner': winner, 'reason': 'x'}})
        if rows is not None:
            with open(os.path.join(gdir, 'analysis.jsonl'), 'w', encoding='utf-8') as f:
                for r in rows:
                    f.write(json.dumps(r) + '\n')
            with open(os.path.join(gdir, 'analysis-summary.json'), 'w', encoding='utf-8') as f:
                f.write('{}')

    @staticmethod
    def random_game(seed, n):
        import random
        rng = random.Random(seed)
        st = X.start()
        for _ in range(n):
            X.push(st, rng.choice(X.legal(st)))
        return st['moves']

    def rows_for(self, mvs, big_plies, decided_plies=()):
        return [{'ply': i + 1, 'side': 'wb'[i % 2], 'opening': i < 2, 'decided': i + 1 in decided_plies,
                 'loss': 300 if i + 1 in big_plies else 10, 'cls': 'blunder' if i + 1 in big_plies else None}
                for i in range(len(mvs))]

    def test_summary(self):
        g1 = self.random_game(1, 24)
        g2 = g1[:22]                                       # 前 20 个半回合同 g1（长度不同，整盘不一样）
        g3 = self.random_game(3, 24)
        short = self.random_game(4, 10)
        # 我方执红（w）：奇数半回合是我方；第 1 个半回合是开局，那里的「大失误」不能算
        self.make('fsf-nodes10-s1-w', 'engine:fsf:nodes=10', 'w', g1, 'w', self.rows_for(g1, {1, 5, 7}, {7}))
        self.make('fsf-nodes10-s2-w', 'engine:fsf:nodes=10', 'w', g2, None, self.rows_for(g2, {9}))
        self.make('fsf-nodes10-s3-b', 'engine:fsf:nodes=10', 'b', g3, 'w')                   # 没分析
        self.make('fsf-nodes10-s4-b', 'engine:fsf:nodes=10', 'b', short, 'unfinished')
        self.make('random-s1-w', 'random', 'w', short, 'w')
        res = B.summarize([self.bdir])
        g = {x['opponent']: x for x in res['groups']}
        f = g['engine:fsf:nodes=10']
        self.assertEqual((f['games'], f['finished'], f['win'], f['draw'], f['loss']), (4, 3, 1, 1, 1))
        self.assertAlmostEqual(f['score_rate'], 0.5)
        lo, hi = B.wilson(1.5, 3)
        self.assertEqual(f['ci95'], [round(lo, 4), round(hi, 4)])
        # 分析过的两盘：g1 我方非开局步 11 步（半回合 3,5,…,23），第 7 个半回合已分胜负 → 未分胜负 10；大失误只数 5
        # g2 我方非开局步 10 步（3,…,21），大失误 9
        self.assertEqual(f['analysed'], 2)
        self.assertEqual((f['blunders'], f['undecided']), (2, 20))
        self.assertAlmostEqual(f['blunder_rate'], 0.1)
        self.assertAlmostEqual(f['acpl'], round((11 * 10 + 2 * 290 + 10 * 10 + 290) / 21, 1))
        self.assertEqual(f['overlaps'], [['fsf-nodes10-s1-w', 'fsf-nodes10-s2-w']])
        self.assertEqual(f['independent'], 2)
        r = g['random']
        self.assertEqual((r['finished'], r['win'], r['score_rate']), (1, 1, 1.0))
        self.assertIsNone(r['blunder_rate'])
        md = B.markdown(res)
        self.assertIn('fsf-nodes10-s1-w、fsf-nodes10-s2-w', md)
        rc, _ = run_quiet(['summary', self.bdir])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(os.path.join(self.bdir, 'summary.md')))


class RunAndResume(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def argv(self, batch, *extra):
        return ['run', '--game', 'xiangqi', '--batch', batch, '--out', self.tmp, '--player', 'random',
                '--opp', 'random', '--seeds', '1-2', '--opening', 'none', '--max-plies', '8', '--no-analyze'] + list(extra)

    def test_skip_done_and_resume_paused(self):
        rc, out = run_quiet(self.argv('direct', '--jobs', '2'))
        self.assertEqual(rc, 0, out)
        names = sorted(n for n in os.listdir(os.path.join(self.tmp, 'direct')) if B.NAME.match(n))
        self.assertEqual(names, ['random-s1-b', 'random-s1-w', 'random-s2-b', 'random-s2-w'])
        direct = {n: moves(os.path.join(self.tmp, 'direct', n)) for n in names}
        stamp = {n: os.path.getmtime(os.path.join(self.tmp, 'direct', n, 'game.jsonl')) for n in names}
        # 再跑同一条命令：全部跳过，记录不动
        rc, out = run_quiet(self.argv('direct', '--jobs', '2'))
        self.assertEqual(rc, 0)
        self.assertNotIn('开始', out)
        for n in names:
            self.assertEqual(os.path.getmtime(os.path.join(self.tmp, 'direct', n, 'game.jsonl')), stamp[n])
        # 设置变了就拒绝
        with self.assertRaises(SystemExit):
            run_quiet(self.argv('direct', '--effort', 'high'))

        # 一路并发、每盘走 3 步就暂停：第一盘停下后不再开新盘，退出码 3
        rc, out = run_quiet(self.argv('paused', '--jobs', '1', '--stop-after', '3'))
        self.assertEqual(rc, 3)
        pdir = os.path.join(self.tmp, 'paused')
        started = [n for n in os.listdir(pdir) if B.NAME.match(n)]
        self.assertEqual(len(started), 1)
        self.assertEqual(len(moves(os.path.join(pdir, started[0]))), 3)
        self.assertFalse(os.path.exists(os.path.join(pdir, B.STOP)))
        self.assertFalse(os.path.exists(os.path.join(pdir, B.LOCK)))
        # 同一条命令（去掉 --stop-after）续跑：没下完的接着下，其余新开，结果和一口气下完的一样
        rc, out = run_quiet(self.argv('paused', '--jobs', '2'))
        self.assertEqual(rc, 0, out)
        self.assertIn('续跑', out)
        for n in names:
            self.assertEqual(moves(os.path.join(pdir, n)), direct[n])
        with open(os.path.join(pdir, 'summary.json'), encoding='utf-8') as f:
            s = json.load(f)
        self.assertEqual(s['groups'][0]['finished'], 4)

    def test_lock_blocks_second_driver(self):
        bdir = os.path.join(self.tmp, 'locked')
        os.makedirs(bdir)
        with open(os.path.join(bdir, B.LOCK), 'w') as f:
            f.write(str(os.getpid()))                   # 当作有个活着的驱动占着
        with self.assertRaises(SystemExit):
            run_quiet(self.argv('locked'))
        with open(os.path.join(bdir, B.LOCK), 'w') as f:
            f.write('999999999')                        # 占着的进程不在了：接手
        rc, _ = run_quiet(self.argv('locked'))
        self.assertEqual(rc, 0)


class Signals(unittest.TestCase):
    """Ctrl-C / SIGTERM：第一次只放 .stop（在跑的盘走完当前这步自己停），第二次直接打断在跑的盘（发 SIGINT 给它的进程组）。"""

    def test_first_stops_second_interrupts(self):
        import signal, subprocess, sys
        tmp = tempfile.mkdtemp(prefix='llmchess-test-')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        drv = B.Driver(None, tmp, 1)
        p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
        self.addCleanup(p.kill)
        drv.procs.add(p)
        with contextlib.redirect_stdout(io.StringIO()):
            drv.on_signal(signal.SIGINT, None)
            self.assertTrue(drv.stop.is_set())
            self.assertTrue(os.path.exists(os.path.join(tmp, B.STOP)))
            self.assertIsNone(p.poll())
            drv.on_signal(signal.SIGTERM, None)
        self.assertNotEqual(p.wait(timeout=10), 0)


@unittest.skipIf(FSF_MISSING, '本机没有 fairy-stockfish')
class RunWithOpening(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_same_opening_both_colors_engine_vs_random(self):
        rc, out = run_quiet(['run', '--game', 'xiangqi', '--batch', 'op', '--out', self.tmp,
                             '--player', 'engine:fsf:nodes=1', '--opp', 'random', '--seeds', '3',
                             '--opening', 'random:2', '--max-plies', '6', '--jobs', '2'])
        self.assertEqual(rc, 0, out)
        cfgs = {c: records.read(os.path.join(self.tmp, 'op', 'random-s3-' + c, 'game.jsonl'))[0]['cfg'] for c in 'wb'}
        self.assertEqual(cfgs['w']['players'], {'w': 'engine:fsf:nodes=1', 'b': 'random'})
        self.assertEqual(cfgs['b']['players'], {'w': 'random', 'b': 'engine:fsf:nodes=1'})
        self.assertEqual(cfgs['w']['opening']['moves'], cfgs['b']['opening']['moves'])
        self.assertEqual(len(cfgs['w']['opening']['moves']), 2)
        # 默认会分析：每盘都有 analysis-summary.json，汇总里有大失误数
        for c in 'wb':
            self.assertTrue(os.path.exists(os.path.join(self.tmp, 'op', 'random-s3-' + c, 'analysis-summary.json')))
        with open(os.path.join(self.tmp, 'op', 'summary.json'), encoding='utf-8') as f:
            g = json.load(f)['groups'][0]
        self.assertEqual(g['analysed'], 2)


if __name__ == '__main__':
    unittest.main()
