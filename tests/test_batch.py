"""离线测试：批量驱动（llmchess/batch.py）。不调 claude：盘都是 random / 引擎，或者 PATH 里换成假 claude，下得很短。
批次放在每个用例自建的临时目录里（名字带随机后缀），用完删掉。起引擎的用例在本机没有引擎时跳过。
"""
import argparse, contextlib, io, json, os, shutil, signal, subprocess, sys, tempfile, time, unittest
from unittest import mock

from llmchess import batch as B, claude_cli as CL, records
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

    def test_batch_meta_show(self):
        # 批次记实际给法：中国象棋默认 pieces 记成 show；all（含国际象棋默认、显式 show=all）不记，和改默认前的旧批次对得上
        def meta(game, sets, player='claude:opus', protocol='legacy'):
            a = argparse.Namespace(game=game, player=player, effort='xhigh', memory='stateless', set=sets,
                                   opening='', max_plies=200, retries=3, protocol=protocol)
            return B.batch_meta(a)
        old = {'game': 'xiangqi', 'player': 'claude:opus', 'effort': 'xhigh', 'memory': 'stateless', 'set': [],
               'opening': '', 'max_plies': 200, 'retries': 3}
        self.assertEqual(meta('xiangqi', None), dict(old, show='pieces'))
        self.assertEqual(meta('xiangqi', ['show=pieces']), dict(old, show='pieces'))
        self.assertEqual(meta('xiangqi', ['show=all']), old)
        self.assertEqual(meta('xiangqi', ['view=fen']), dict(old, set=['view=fen']))
        self.assertEqual(meta('xiangqi', None, 'engine:fsf:nodes=10'), dict(old, player='engine:fsf:nodes=10'))
        self.assertEqual(meta('chess', None), dict(old, game='chess'))
        self.assertEqual(meta('chess', ['show=board', 'legal=list']), dict(old, game='chess', set=['legal=list'], show='board'))
        # 新协议的批次记 protocol；旧批次的 batch.json 没有这一项，只有 legacy 对得上
        self.assertEqual(meta('chess', None, protocol='real'), dict(old, game='chess', protocol='real'))

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


def ns(**kw):
    """batch run 的参数（只含驱动拼命令要用的那些），kw 覆盖。"""
    import argparse
    base = dict(game='chess', player='claude:opus', effort='xhigh', memory='stateless', max_plies=200, retries=3,
                set=None, opening='random:8', timeout=None, on_limit='wait', protocol='legacy')
    base.update(kw)
    return argparse.Namespace(**base)


class PassThrough(unittest.TestCase):
    """--on-limit（默认 wait）和 --timeout 透传给每盘的 play 和 resume。"""

    @staticmethod
    def opt(cmd, flag):
        return cmd[cmd.index(flag) + 1] if flag in cmd else None

    def test_defaults_and_overrides(self):
        gdir = os.path.join('runs', 'b', 'maia-1500-s1-w')
        a = ns()
        for cmd in (B.play_cmd(a, gdir, 'engine:maia-1500', 1, 'w'), B.resume_cmd(a, gdir)):
            self.assertEqual(self.opt(cmd, '--on-limit'), 'wait')
            self.assertIsNone(self.opt(cmd, '--timeout'))
        a = ns(timeout=100, on_limit='pause')
        for cmd in (B.play_cmd(a, gdir, 'engine:maia-1500', 1, 'w'), B.resume_cmd(a, gdir)):
            self.assertEqual(self.opt(cmd, '--on-limit'), 'pause')
            self.assertEqual(self.opt(cmd, '--timeout'), '100')

    def test_agy_player_and_opponent_build_real_config(self):
        from llmchess import cli
        player, opp = 'agy:claude-opus-5-5-high', 'gemini:gemini-4-argon-high'
        self.assertEqual(B.full_spec(player), player)
        a = ns(player=player, protocol='real', memory='session', effort='high')
        seen = {}
        def capture(args):
            seen.update(cli.build_cfg(args)[1])
            return 0
        with mock.patch.object(cli, 'cmd_play', capture):
            self.assertEqual(cli.main(B.play_cmd(a, 'runs/b/agymodel-s1-b', opp, 1, 'b')[3:]), 0)
        self.assertEqual(seen['models'], {'w': 'gemini-4-argon-high', 'b': 'agy/claude-opus-5-5-high'})
        self.assertEqual(seen['backend'], 'llm-chat')

    def test_commands_parse(self):
        """拼出来的 play / resume 命令，play / resume 自己的命令行都认。"""
        from llmchess import cli
        a = ns(timeout=100, on_limit='pause')
        seen = {}
        with mock.patch.object(cli, 'cmd_play', lambda x: seen.setdefault('play', x) and 0), \
                mock.patch.object(cli, 'cmd_resume', lambda x: seen.setdefault('resume', x) and 0):
            cli.main(B.play_cmd(a, 'runs/b/random-s1-w', 'random', 1, 'w')[3:])
            cli.main(B.resume_cmd(a, 'runs/b/random-s1-w')[3:])
        for k in ('play', 'resume'):
            self.assertEqual((seen[k].on_limit, seen[k].timeout), ('pause', 100))
            self.assertTrue(seen[k].stop_file.endswith(B.STOP))


class Signals(unittest.TestCase):
    """Ctrl-C / SIGTERM 走 claude_cli 同一套停止处理：第一次置 STOP、放 .stop、给每个在跑的盘发一次 SIGTERM
    （只发给这盘的进程本身）；第二次向在跑的盘的进程组发 SIGINT 直接打断，驱动自己不退。"""

    def setUp(self):
        CL.STOP.clear()
        self.addCleanup(CL.STOP.clear)

    def test_first_stops_second_interrupts(self):
        tmp = tempfile.mkdtemp(prefix='llmchess-test-')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        marker = os.path.join(tmp, 'got-term')
        # 子进程：收到 SIGTERM 只记一笔（像 play 的停止处理一样不退），SIGINT 照默认退出
        code = ('import signal, sys, time\n'
                'signal.signal(signal.SIGTERM, lambda *x: open(sys.argv[1], "a").write("t"))\n'
                'open(sys.argv[1] + ".ready", "w").close()\n'
                'time.sleep(30)\n')
        p = subprocess.Popen([sys.executable, '-c', code, marker], start_new_session=True, stderr=subprocess.DEVNULL)
        self.addCleanup(p.kill)
        wait_for(lambda: os.path.exists(marker + '.ready'))
        drv = B.Driver(None, tmp, 1)
        drv.procs.add(p)
        restore = CL.install_stop_handlers(on_stop=lambda: drv.request_stop('测试'), on_force=drv.interrupt)
        try:
            handler = signal.getsignal(signal.SIGINT)
            with contextlib.redirect_stdout(io.StringIO()):
                handler(signal.SIGINT, None)
                self.assertTrue(CL.STOP.is_set())
                self.assertTrue(os.path.exists(os.path.join(tmp, B.STOP)))
                wait_for(lambda: os.path.exists(marker))
                self.assertIsNone(p.poll())                     # SIGTERM 只叫醒，不打断
                drv.request_stop('又一盘暂停')                   # 再请求一次停止：不重复转告
                handler(signal.SIGTERM, None)                   # 第二次信号：打断，不强退本进程
        finally:
            restore()
        self.assertNotEqual(p.wait(timeout=10), 0)
        with open(marker) as f:
            self.assertEqual(f.read(), 't')

    def test_no_new_game_after_stop(self):
        tmp = tempfile.mkdtemp(prefix='llmchess-test-')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        a = ns(game='xiangqi', player='random', opening='', max_plies=4, stop_after=None,
                             no_analyze=True)
        drv = B.Driver(a, tmp, 1)
        drv.spawn = mock.Mock(side_effect=AssertionError('STOP 之后不该再起盘'))
        CL.STOP.set()
        drv.run_one('random-s1-w', 'random', 1, 'w')
        self.assertEqual(drv.result, {'random-s1-w': 'not started'})
        self.assertFalse(os.path.exists(os.path.join(tmp, 'random-s1-w')))


FAKE_CLAUDE = """#!%s
# 假 claude：看 $FAKE_CLAUDE_MODE 这个文件里写的模式回话。limit：报撞额度（读不出解除时间）；illegal：回一个非法着法。
import json, os, sys
if '--version' in sys.argv:
    print('0.0.0 (fake)'); sys.exit(0)
mode = open(os.environ['FAKE_CLAUDE_MODE']).read().strip()
if mode == 'limit':
    print(json.dumps({'type': 'result', 'is_error': True, 'result': 'Claude usage limit reached.'})); sys.exit(1)
print(json.dumps({'type': 'result', 'is_error': False, 'result': '着法: zz', 'session_id': 'fake',
                  'usage': {'input_tokens': 1, 'output_tokens': 1}, 'total_cost_usd': 0}))
"""


def wait_for(cond, secs=60):
    """轮询到条件成立（测试里等子进程写出记录）；超时就失败。只是轮询，不靠睡够某个时长。"""
    deadline = time.monotonic() + secs
    while not cond():
        if time.monotonic() > deadline:
            raise AssertionError('等了 %d 秒条件还不成立' % secs)
        time.sleep(0.05)


class FakeClaudeLimit(unittest.TestCase):
    """假 claude 撞额度：wait 时一次信号叫醒所有在等额度的盘、各自写 pause、不再开新盘、退出码 3，再跑同一条命令续跑；
    pause 时第一盘撞额度就停、退出码 3。子进程的等待都在停止信号上，测试不睡够任何时长。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        CL.STOP.clear()
        self.addCleanup(CL.STOP.clear)
        bin_dir = os.path.join(self.tmp, 'bin')
        os.makedirs(bin_dir)
        fake = os.path.join(bin_dir, 'claude')
        with open(fake, 'w') as f:
            f.write(FAKE_CLAUDE % sys.executable)
        os.chmod(fake, 0o755)
        self.mode = os.path.join(self.tmp, 'mode')
        self.set_mode('limit')
        self.env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ.get('PATH', ''), FAKE_CLAUDE_MODE=self.mode)

    def set_mode(self, m):
        with open(self.mode, 'w') as f:
            f.write(m)

    def argv(self, batch, *extra):
        # 假 claude 顶的是旧路（claude -p 直调），所以用 legacy 协议
        return ['run', '--game', 'chess', '--batch', batch, '--out', self.tmp, '--player', 'claude:opus',
                '--opp', 'random', '--seeds', '1-2', '--opening', 'none', '--max-plies', '6', '--retries', '0',
                '--no-analyze', '--protocol', 'legacy'] + list(extra)

    def recs(self, bdir, name):
        return records.read(os.path.join(bdir, name, 'game.jsonl'))

    def test_one_signal_wakes_all_waiting_games(self):
        bdir = os.path.join(self.tmp, 'w')
        cmd = [sys.executable, '-m', 'llmchess.batch'] + self.argv('w', '--jobs', '2')
        log = open(os.path.join(self.tmp, 'driver.log'), 'w')
        self.addCleanup(log.close)
        p = subprocess.Popen(cmd, cwd=str(B.ROOT), env=self.env, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True)
        self.addCleanup(lambda: p.poll() is None and os.killpg(p.pid, signal.SIGKILL))

        def waiting():
            names = [n for n in os.listdir(bdir) if B.NAME.match(n)] if os.path.isdir(bdir) else []
            ok = [n for n in names if os.path.exists(os.path.join(bdir, n, 'game.jsonl')) and any(
                r['type'] == 'limit_wait' and r['phase'] == 'start' for r in self.recs(bdir, n))]
            return len(ok) == 2 and ok
        wait_for(waiting)
        started = sorted(waiting())
        p.send_signal(signal.SIGINT)                    # 一次 Ctrl-C
        self.assertEqual(p.wait(timeout=60), 3)
        for n in started:
            rs = self.recs(bdir, n)
            ends = [r for r in rs if r['type'] == 'limit_wait' and r['phase'] == 'end']
            self.assertEqual(len(ends), 1, n)
            self.assertTrue(ends[0]['stopped'])
            self.assertLess(ends[0]['waited'], 60)          # 退避是 600 秒，是被叫醒的
            self.assertEqual(rs[-1]['type'], 'pause', n)
        games = sorted(n for n in os.listdir(bdir) if B.NAME.match(n))
        self.assertEqual(games, started)                    # 另外两盘没开
        self.assertFalse(os.path.exists(os.path.join(bdir, B.STOP)))
        self.assertFalse(os.path.exists(os.path.join(bdir, B.LOCK)))
        # 同一条命令再跑：在等的两盘续跑，另两盘新开，都下完（假 claude 回非法着法，判负）
        self.set_mode('illegal')
        with mock.patch.dict(os.environ, self.env):
            rc, out = run_quiet(self.argv('w', '--jobs', '2'))
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.count('续跑'), 2)
        for n in os.listdir(bdir):
            if B.NAME.match(n):
                self.assertEqual(B.game_state(os.path.join(bdir, n)), 'done', n)

    def test_pause_mode_stops_batch(self):
        with mock.patch.dict(os.environ, self.env):
            rc, out = run_quiet(self.argv('p', '--jobs', '1', '--on-limit', 'pause'))
        self.assertEqual(rc, 3, out)
        bdir = os.path.join(self.tmp, 'p')
        games = [n for n in os.listdir(bdir) if B.NAME.match(n)]
        self.assertEqual(len(games), 1)
        rs = self.recs(bdir, games[0])
        self.assertEqual(rs[-1]['type'], 'pause')
        self.assertIn('额度', rs[-1]['why'])
        self.assertFalse(any(r['type'] == 'limit_wait' for r in rs))
        self.assertIn('--on-limit', rs[0]['cfg']['argv'])


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
