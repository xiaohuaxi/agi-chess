"""满半回合上限的判法（用户 2026-10-04 定）：有引擎一方的对局到上限按事后裁判引擎的评分判，一方领先 ≥300 厘兵判胜、
否则和；模型对模型、随机走子、legacy、--cap-rule draw 照旧判和。离线：只走 random / engine 棋手，会起本机引擎。"""
import contextlib
import io
import os
import shutil
import tempfile
import unittest

from llmchess import analyze, cli, records, runner

FSF_MISSING = shutil.which('fairy-stockfish') is None and not os.path.exists('/opt/homebrew/bin/fairy-stockfish')
STOCKFISH_MISSING = shutil.which('stockfish') is None and not os.path.exists('/opt/homebrew/bin/stockfish')


def run_quiet(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(argv)
    return rc, buf.getvalue()


class CapVerdict(unittest.TestCase):
    def test_margin_and_mate(self):
        self.assertEqual(analyze.cap_verdict(('cp', 300), 300), 'stm')
        self.assertIsNone(analyze.cap_verdict(('cp', 299), 300))
        self.assertIsNone(analyze.cap_verdict(('cp', -299), 300))
        self.assertEqual(analyze.cap_verdict(('cp', -300), 300), 'other')
        self.assertEqual(analyze.cap_verdict(('mate', 3), 300), 'stm')
        self.assertEqual(analyze.cap_verdict(('mate', -2), 300), 'other')


class CapRuleInGames(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-test-cap-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out = os.path.join(self.tmp, 'runs')

    def play(self, tag, *argv):
        rc, _ = run_quiet(['play', '--tag', tag, '--out', self.out] + list(argv))
        self.assertEqual(rc, 0)
        run_dir = os.path.join(self.out, tag)
        recs = records.read(os.path.join(run_dir, 'game.jsonl'))
        end = [r for r in recs if r['type'] == 'end']
        self.assertEqual(len(end), 1)
        return recs[0]['cfg'], end[0]['end'], run_dir

    def check_adjudicated(self, cfg, end, run_dir, plies, depth):
        self.assertEqual(cfg['adjudicate'], {'margin': runner.CAP_MARGIN})
        self.assertTrue(end['reason'].startswith('满 %d 个半回合（研究设的上限），到上限按引擎评分判：' % plies), end['reason'])
        adj = end['adjudication']
        self.assertEqual((adj['depth'], adj['margin']), (depth, runner.CAP_MARGIN))
        kind, n = adj['score'].split()
        v = analyze.cap_verdict((kind, int(n)), runner.CAP_MARGIN)
        other = 'b' if adj['stm'] == 'w' else 'w'
        self.assertEqual(end['winner'], None if v is None else adj['stm'] if v == 'stm' else other)
        with open(os.path.join(run_dir, 'record.txt'), encoding='utf-8') as f:
            self.assertIn('到上限按引擎评分判', f.read())
        # 系统提示里写的是新规则，且不提「引擎」（不透露对手是引擎）
        for s in 'wb':
            self.assertIn('仍未分胜负时由裁判评估局面：一方领先至少 300 厘兵判该方胜，否则判和。', cfg['system'][s])
            self.assertNotIn('引擎', cfg['system'][s])

    @unittest.skipIf(STOCKFISH_MISSING, 'stockfish not installed')
    def test_chess_engine_far_ahead_wins_at_cap(self):
        cfg, end, run_dir = self.play('c1', '--game', 'chess', '--white', 'engine:stockfish:depth=4', '--black', 'random',
                                      '--seed', '3', '--max-plies', '12')
        self.check_adjudicated(cfg, end, run_dir, 12, analyze.DEPTH['chess'])
        self.assertEqual(end['winner'], 'w')          # 引擎对随机走 6 步，早已大优
        with open(os.path.join(run_dir, 'game.pgn'), encoding='utf-8') as f:
            pgn = f.read()
        self.assertIn('[Result "1-0"]', pgn)
        self.assertIn('到上限按引擎评分判', pgn)

    @unittest.skipIf(STOCKFISH_MISSING, 'stockfish not installed')
    def test_chess_balanced_is_draw_at_cap(self):
        cfg, end, run_dir = self.play('c2', '--game', 'chess', '--white', 'engine:stockfish:depth=8',
                                      '--black', 'engine:stockfish:depth=8', '--max-plies', '2')
        self.check_adjudicated(cfg, end, run_dir, 2, analyze.DEPTH['chess'])
        self.assertIsNone(end['winner'])
        self.assertIn('差距不到 300，判和', end['reason'])

    @unittest.skipIf(FSF_MISSING, 'fairy-stockfish not installed')
    def test_xiangqi_engine_vs_random(self):
        cfg, end, run_dir = self.play('x1', '--game', 'xiangqi', '--red', 'engine:fsf:nodes=100', '--black', 'random',
                                      '--seed', '5', '--max-plies', '10')
        self.check_adjudicated(cfg, end, run_dir, 10, analyze.DEPTH['xiangqi'])

    @unittest.skipIf(STOCKFISH_MISSING, 'stockfish not installed')
    def test_draw_rule_and_no_engine_keep_old_behaviour(self):
        old = '满 %d 个半回合（研究设的上限），判和'
        cfg, end, _ = self.play('d1', '--game', 'chess', '--white', 'random', '--black', 'random', '--seed', '7',
                                '--max-plies', '4')
        self.assertNotIn('adjudicate', cfg)
        self.assertEqual(end, {'winner': None, 'reason': old % 4})
        self.assertIn('满 4 个半回合仍未分胜负判和。', cfg['system']['w'])
        cfg, end, _ = self.play('d2', '--game', 'chess', '--white', 'engine:stockfish:depth=4', '--black', 'random',
                                '--seed', '3', '--max-plies', '12', '--cap-rule', 'draw')
        self.assertNotIn('adjudicate', cfg)
        self.assertEqual(end, {'winner': None, 'reason': old % 12})
        self.assertNotIn('cap_margin', cfg['sides']['w'])

    def test_model_games_and_legacy_unchanged(self):
        # 模型对模型：不按评分判，系统提示逐字照旧
        rc, out = run_quiet(['play', '--game', 'chess', '--dry-run'])
        self.assertEqual(rc, 0)
        self.assertIn('满 200 个半回合仍未分胜负判和。', out)
        self.assertNotIn('裁判评估', out)
        # 模型对引擎：提示里是新规则
        rc, out = run_quiet(['play', '--game', 'xiangqi', '--black', 'engine:fsf:nodes=1', '--dry-run'])
        self.assertEqual(rc, 0)
        self.assertIn('满 200 个半回合仍未分胜负时由裁判评估局面', out)
        # legacy 对引擎：旧提示、旧判法
        rc, out = run_quiet(['play', '--game', 'chess', '--protocol', 'legacy', '--black', 'engine:maia-1100', '--dry-run'])
        self.assertEqual(rc, 0)
        self.assertNotIn('裁判评估', out)
        with self.assertRaises(SystemExit):
            run_quiet(['play', '--game', 'chess', '--cap-rule', 'eval', '--dry-run'])


if __name__ == '__main__':
    unittest.main()
