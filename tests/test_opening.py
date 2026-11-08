"""离线测试：随机开局（agi_chess/opening.py 和 runner / cli / analyze 里接它的地方）。不调 claude。
起本机引擎的用例在没有引擎时跳过；记录放在每个用例自建的临时目录里，用完删掉。
"""
import contextlib, io, json, os, shutil, tempfile, unittest
from unittest import mock

from agi_chess import analyze as A, chess_ as C, cli, opening, records
from agi_chess import xiangqi as X
from agi_chess.engine import find_engine_binary

FSF_MISSING = find_engine_binary('fairy-stockfish', 'FAIRY_STOCKFISH') is None
STOCKFISH_MISSING = find_engine_binary('stockfish', 'STOCKFISH') is None


def run_quiet(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(argv)
    return rc, buf.getvalue()


class ParseAndChoose(unittest.TestCase):
    def test_parse_multipv_takes_deepest_exact_line(self):
        lines = ['info depth 9 seldepth 10 multipv 1 score cp 40 nodes 1 pv e2e4 e7e5',
                 'info depth 10 seldepth 11 multipv 1 score cp 25 nodes 2 pv e2e4 e7e5',
                 'info depth 10 seldepth 11 multipv 2 score cp 15 nodes 2 pv g1f3 d7d5',
                 'info depth 10 seldepth 11 multipv 3 score cp 90 upperbound nodes 2 pv a2a3',   # 上下界不算
                 'info depth 9 seldepth 11 multipv 3 score cp -30 nodes 2 pv d2d4',
                 'bestmove e2e4 ponder e7e5']
        self.assertEqual(opening.parse_multipv(lines), [('e2e4', 25), ('g1f3', 15), ('d2d4', -30)])

    def test_mate_values_order(self):
        self.assertGreater(opening.score_value('mate', 1), opening.score_value('mate', 3))
        self.assertGreater(opening.score_value('mate', 3), opening.score_value('cp', 5000))
        self.assertLess(opening.score_value('mate', -1), opening.score_value('mate', -4))
        self.assertLess(opening.score_value('mate', -4), opening.score_value('cp', -5000))

    def test_choose_margin_and_seed(self):
        cands = [('a', 30), ('b', -20), ('c', -21)]          # c 差 51，不进池子
        picks = set()
        for seed in range(40):
            mv, pool = opening.choose(cands, seed, 3)
            self.assertEqual(pool, ['a', 'b'])
            self.assertEqual(mv, opening.choose(cands, seed, 3)[0])     # 同种子同半回合，结果一样
            picks.add(mv)
        self.assertEqual(picks, {'a', 'b'})

    def test_parse_mode(self):
        self.assertEqual(opening.parse_mode(None), 0)
        self.assertEqual(opening.parse_mode('random:8'), 8)
        for bad in ('random', 'random:x', 'book:3'):
            with self.assertRaises(ValueError):
                opening.parse_mode(bad)


@unittest.skipIf(STOCKFISH_MISSING, '本机没有 stockfish')
class ChessGenerate(unittest.TestCase):
    def test_same_seed_same_opening(self):
        a = opening.generate(C, 'chess', 6, 11)
        b = opening.generate(C, 'chess', 6, 11)
        self.assertEqual(len(a['moves']), 6)
        self.assertEqual(a['moves'], b['moves'])
        self.assertEqual(a['detail'], b['detail'])           # 候选和评分也一样：搜索本身可复现
        st = C.start()
        for p in a['detail']:
            self.assertIn(p['move'], p['pool'])
            self.assertLessEqual(len(p['cands']), opening.MULTIPV)
            top = p['cands'][0][1]
            self.assertTrue(all(top - v <= opening.MARGIN for m, v in p['cands'] if m in p['pool']))
            self.assertIn(p['move'], C.legal(st))
            C.push(st, p['move'])

    def test_seeds_differ(self):
        seen = {tuple(opening.generate(C, 'chess', 6, s)['moves']) for s in range(1, 7)}
        self.assertGreater(len(seen), 1)


@unittest.skipIf(FSF_MISSING, '本机没有 fairy-stockfish')
class XiangqiGenerate(unittest.TestCase):
    def test_same_seed_same_opening(self):
        a = opening.generate(X, 'xiangqi', 4, 5)
        b = opening.generate(X, 'xiangqi', 4, 5)
        self.assertEqual(a['moves'], b['moves'])
        self.assertRegex(a['moves'][0], r'^[a-i]\d[a-i]\d$')           # 已换回 ICCS
        self.assertEqual(len(a['record']), 4)


@unittest.skipIf(FSF_MISSING, '本机没有 fairy-stockfish')
class PlayWithOpening(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='agi-chess-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def recs(self, run_dir):
        return records.read(os.path.join(run_dir, 'game.jsonl'))

    def test_opening_marked_and_resume_replays(self):
        common = ['--game', 'xiangqi', '--red', 'random', '--black', 'random', '--seed', '3',
                  '--max-plies', '10', '--opening', 'random:4', '--opening-seed', '7']
        d1 = os.path.join(self.tmp, 'direct')
        rc, _ = run_quiet(['play', '--tag', 'x'] + common + ['--out', d1])
        self.assertEqual(rc, 0)
        recs = self.recs(os.path.join(d1, 'x'))
        cfg = recs[0]['cfg']
        self.assertEqual(cfg['opening']['seed'], 7)
        op = cfg['opening']['moves']
        self.assertEqual(len(op), 4)
        mv = [r for r in recs if r['type'] == 'move']
        self.assertEqual([r['move'] for r in mv[:4]], op)
        self.assertEqual([bool(r.get('opening')) for r in mv], [True] * 4 + [False] * 6)
        # 随机走子方的尝试只从第 5 个半回合起
        self.assertEqual(min(r['ply'] for r in recs if r['type'] == 'attempt'), 5)
        end = next(r for r in recs if r['type'] == 'end')
        self.assertEqual(end['summary']['w']['plies'] + end['summary']['b']['plies'], 6)
        with open(os.path.join(d1, 'x', 'record.txt'), encoding='utf-8') as f:
            self.assertIn('随机开局', f.read())

        # 停在开局中间再续跑：续跑不重新生成，照 config 重放，走出一样的整盘
        d2 = os.path.join(self.tmp, 'resumed')
        rc, _ = run_quiet(['play', '--tag', 'x'] + common + ['--out', d2, '--stop-after', '2'])
        self.assertEqual(rc, 3)
        with mock.patch.object(opening, 'generate', side_effect=AssertionError('续跑不该重新生成开局')):
            rc, _ = run_quiet(['resume', os.path.join(d2, 'x')])
        self.assertEqual(rc, 0)
        mv2 = [r for r in self.recs(os.path.join(d2, 'x')) if r['type'] == 'move']
        self.assertEqual([r['move'] for r in mv2], [r['move'] for r in mv])
        self.assertEqual([bool(r.get('opening')) for r in mv2], [True] * 4 + [False] * 6)

    def test_dry_run_prompt_shows_opening_moves_only(self):
        rc, out = run_quiet(['play', '--game', 'xiangqi', '--black', 'random', '--opening', 'random:4',
                             '--opening-seed', '9', '--dry-run'])
        self.assertEqual(rc, 0)
        gen = opening.generate(X, 'xiangqi', 4, 9)
        prompt = out.split('用户提示')[-1]
        self.assertIn('随机开局 4 个半回合之后', out)
        for text, mv in zip(gen['record'], gen['moves']):
            self.assertIn('%s（%s）' % (text, mv), prompt)
        for leak in ('fsf', 'Fairy', 'multipv', 'MultiPV', 'depth', '引擎', '随机开局', 'score'):
            self.assertNotIn(leak, prompt)
        # 模型执黑、开局走完轮到红方（随机）：先让红方走一步，打印的是黑方真正的第一步提示
        rc, out = run_quiet(['play', '--game', 'xiangqi', '--red', 'random', '--seed', '1', '--opening', 'random:4',
                             '--opening-seed', '9', '--dry-run'])
        self.assertEqual(rc, 0)
        self.assertIn('黑方第一步的用户提示', out)
        self.assertIn('已走 5 个半回合', out.split('用户提示')[-1])


class AnalyzeSkipsOpening(unittest.TestCase):
    def test_summarize_excludes_opening_rows(self):
        rows = []
        for i in range(12):
            side, n = 'wb'[i % 2], i // 2 + 1
            op = i < 4
            rows.append({'ply': i + 1, 'side': side, 'n': n, 'decided': False, 'opening': op,
                         'loss': 400 if op else 20, 'cls': 'blunder' if op else None,
                         'lichess': 'Blunder' if op else None, 'wp_before': 50, 'wp_after': 40 if op else 49})
        s = A.summarize(rows, {'game': 'chess', 'players': {'w': 'claude:opus', 'b': 'random'}})
        self.assertEqual(s['opening_plies'], 4)
        w = s['sides']['w']
        self.assertEqual((w['plies'], w['undecided'], w['blunders'], w['acpl']), (4, 4, 0, 20))
        self.assertEqual(w['lichess']['Blunder'], 0)
        self.assertEqual(s['events_global'], 0)

    def test_records_summary_excludes_opening_stats(self):
        st = [dict(records.new_stat(), side='w', opening=True), dict(records.new_stat(), side='b', opening=True),
              dict(records.new_stat(), side='w', attempts=1, cost=0.5)]
        summ = records.summary(st, {'w': 'claude:opus', 'b': 'random'})
        self.assertEqual((summ['w']['plies'], summ['b']['plies'], summ['w']['calls']), (1, 0, 1))


if __name__ == '__main__':
    unittest.main()
