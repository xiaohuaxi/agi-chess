"""离线单元测试：事后引擎分析（llmchess/analyze.py）。不调 claude；重放用例起本机引擎，深度压低保证快。
记录文件是人造的，放在每个用例自建的临时目录里（名字带随机后缀），用完删掉。
"""
import contextlib, io, json, os, shutil, tempfile, unittest

from llmchess import analyze as A

FSF_MISSING = shutil.which('fairy-stockfish') is None and not os.path.exists('/opt/homebrew/bin/fairy-stockfish')
STOCKFISH_MISSING = shutil.which('stockfish') is None and not os.path.exists('/opt/homebrew/bin/stockfish')
QUIET = lambda *a: None


def usage(n):
    return {'in': 2, 'cache_read': n, 'cache_write': 100, 'out': 50, 'think': 30, 'text_out': 20, 'cost': 0.01}


def stat(n, attempts=1, illegal=0):
    return {'attempts': attempts, 'illegal': illegal, 'noparse': 0, 'flags': 0, 'empty': 0, 'elapsed': 2.0,
            'cost': 0.01 * attempts, 'in': 2, 'cache_read': n, 'cache_write': 100, 'out': 50, 'think': 30,
            'text_out': 20}


def make_run(root, game, moves, model='w', end=None, pause=False, extra=None):
    """人造一盘记录：model 方是 claude:opus，另一方 random；每步一次合法尝试。extra: {半回合号: [额外的事件]}，
    放在该半回合的合法尝试之前。"""
    d = tempfile.mkdtemp(prefix='run-', dir=root)
    players = {s: ('claude:opus' if s == model else 'random') for s in 'wb'}
    sc = {'effort': 'medium', 'memory': 'session', 'view': [], 'history': -1, 'legal': 'none', 'selfcheck': 'off',
          'recite': 'off', 'notes_keep': 1, 'session_view': 'full', 'max_plies': 200}
    recs = [{'type': 'config', 'cfg': {'game': game, 'tag': os.path.basename(d), 'players': players,
                                        'sides': {'w': dict(sc), 'b': dict(sc, effort='high')},
                                        'retries': 3, 'max_plies': 200, 'seed': 1}}]
    for i, mv in enumerate(moves):
        ply, side = i + 1, 'wb'[i % 2]
        recs += (extra or {}).get(ply, [])
        k = sum(1 for r in recs if r['type'] == 'attempt' and r['ply'] == ply)
        a = {'type': 'attempt', 'ply': ply, 'side': side, 'try': k + 1, 'player': players[side], 'move': mv,
             'legal': True}
        if side == model:
            a.update(usage=usage(1000 * ply), elapsed=2.0, move_text=mv)
        recs.append(a)
        recs.append({'type': 'move', 'ply': ply, 'side': side, 'move': mv, 'text': mv,
                     'stat': dict(stat(1000 * ply, attempts=k + 1), side=side)})
    if pause:
        recs.append({'type': 'pause', 'ply': len(moves), 'why': '按 --stop-after 停下'})
    if end:
        recs.append({'type': 'end', 'end': end, 'plies': len(moves), 'moves': moves})
    with open(os.path.join(d, 'game.jsonl'), 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    return d


def read_rows(d):
    with open(os.path.join(d, 'analysis.jsonl'), encoding='utf-8') as f:
        return [json.loads(l) for l in f]


class TmpCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='llmchess-analyze-test-')

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


# ---------------------------------------------------------------- 纯函数
class Scores(unittest.TestCase):
    def test_value_clip_and_mate(self):
        self.assertEqual(A.value(('cp', 35)), 35)
        self.assertEqual(A.value(('cp', 1500)), 1000)
        self.assertEqual(A.value(('cp', -2400)), -1000)
        self.assertEqual(A.value(('mate', 3)), 1000)
        self.assertEqual(A.value(('mate', -2)), -1000)
        self.assertEqual(A.value(('end', 1)), 1000)
        self.assertEqual(A.neg(('mate', 3)), ('mate', -3))
        self.assertTrue(A.decided(('mate', 5)))
        self.assertTrue(A.decided(('cp', -1000)))
        self.assertFalse(A.decided(('cp', 999)))

    def test_parse_search(self):
        lines = ['info depth 1 seldepth 1 multipv 1 score cp 20 nodes 20 pv e2e4',
                 'info depth 2 seldepth 2 multipv 1 score cp 35 nodes 90 pv d2d4',
                 'info depth 3 seldepth 4 multipv 1 score cp 80 lowerbound nodes 200 pv d2d4',
                 'info depth 3 seldepth 4 multipv 2 score cp -50 nodes 200 pv a2a3',
                 'info depth 3 seldepth 4 multipv 1 score mate -4 nodes 300 pv g1f3',
                 'bestmove g1f3 ponder b8c6']
        self.assertEqual(A.parse_search(lines), (('mate', -4), 3, 'g1f3'))
        self.assertEqual(A.parse_search(['info depth 0 score mate 0', 'bestmove (none)']), (('mate', 0), 0, None))

    def test_lichess_formula_and_judgement(self):
        # scalachess WinPercent：cp 0 → 50%；系数 −0.00368208
        self.assertAlmostEqual(A.win_percent(('cp', 0)), 50.0)
        self.assertAlmostEqual(A.winning_chances(300), 2 / (1 + 2.718281828459045 ** (-0.00368208 * 300)) - 1)
        self.assertAlmostEqual(A.win_percent(('mate', 2)), A.win_percent(('cp', 1000)))
        # 厘兵对厘兵：delta 门槛 0.1 / 0.2 / 0.3
        self.assertEqual(A.lichess_judgement(('cp', 0), ('cp', -10))[0], None)
        j, d = A.lichess_judgement(('cp', 0), ('cp', -300))
        self.assertEqual(j, 'Blunder')
        self.assertGreaterEqual(d, 0.3)
        self.assertEqual(A.lichess_judgement(('cp', 0), ('cp', -120))[0], 'Mistake')
        self.assertEqual(A.lichess_judgement(('cp', 0), ('cp', -60))[0], 'Inaccuracy')
        # MateCreated：按走前厘兵分
        self.assertEqual(A.lichess_judgement(('cp', 50), ('mate', -3))[0], 'Blunder')
        self.assertEqual(A.lichess_judgement(('cp', -800), ('mate', -3))[0], 'Mistake')
        self.assertEqual(A.lichess_judgement(('cp', -1200), ('mate', -3))[0], 'Inaccuracy')
        # MateLost：按走后厘兵分；有杀→被杀也算
        self.assertEqual(A.lichess_judgement(('mate', 2), ('cp', 1200))[0], 'Inaccuracy')
        self.assertEqual(A.lichess_judgement(('mate', 2), ('cp', 800))[0], 'Mistake')
        self.assertEqual(A.lichess_judgement(('mate', 2), ('cp', 100))[0], 'Blunder')
        self.assertEqual(A.lichess_judgement(('mate', 2), ('mate', -5))[0], 'Blunder')
        # 杀得慢了、已经将死：不判
        self.assertEqual(A.lichess_judgement(('mate', 2), ('mate', 4))[0], None)
        self.assertEqual(A.lichess_judgement(('mate', 1), ('end', 1))[0], None)


class Phases(unittest.TestCase):
    def test_buckets_by_own_move_number(self):
        rows = []
        for i in range(100):                       # 每方 50 步
            side, n = 'wb'[i % 2], i // 2 + 1
            big = side == 'w' and n in (3, 20, 21, 47)
            rows.append({'ply': i + 1, 'side': side, 'n': n, 'decided': n > 48, 'loss': 300 if big else 10,
                         'cls': 'blunder' if big else None})
        s = A.summarize(rows, {'game': 'xiangqi', 'players': {'w': 'claude:opus', 'b': 'random'}})['sides']['w']
        self.assertEqual([p['range'] for p in s['phases']], ['1-15', '16-30', '31-45', '46-'])
        self.assertEqual([p['plies'] for p in s['phases']], [15, 15, 15, 5])
        self.assertEqual([p['blunders'] for p in s['phases']], [1, 2, 0, 1])
        self.assertEqual([p['undecided'] for p in s['phases']], [15, 15, 15, 3])
        self.assertEqual(s['phases'][0]['acpl'], round((300 + 14 * 10) / 15, 1))
        self.assertEqual((s['plies'], s['undecided'], s['blunders']), (50, 48, 4))
        self.assertEqual(s['events'], 3)            # 第 20、21 步相邻（半回合 39、41）并成一件
        self.assertAlmostEqual(s['blunder_rate'], round(4 / 48, 4))


# ---------------------------------------------------------------- 重放 + 引擎
@unittest.skipIf(STOCKFISH_MISSING, '本机没有 stockfish')
class ChessReplay(TmpCase):
    def test_hanging_queen_is_blunder(self):
        # 1.e4 d6 2.Qg4?? Bxg4：白方第二步白送后
        d = make_run(self.root, 'chess', ['e2e4', 'd7d6', 'd1g4', 'c8g4'])
        s = A.analyse_run(d, depth=10, log=QUIET)
        rows = read_rows(d)
        self.assertEqual([r['ply'] for r in rows], [1, 2, 3, 4])
        r3, r4 = rows[2], rows[3]
        self.assertEqual((r3['side'], r3['text'], r3['n']), ('w', 'Qg4', 2))
        self.assertGreater(r3['before_v'], -100)
        self.assertLess(r3['after_v'], -500)       # 走后是走子方（白）视角，丢了后
        self.assertGreaterEqual(r3['loss'], 250)
        self.assertEqual(r3['cls'], 'blunder')
        self.assertEqual(r3['lichess'], 'Blunder')
        self.assertNotEqual(r3['best'], 'd1g4')
        self.assertLess(r4['loss'], 100)          # 黑方吃后是好棋
        self.assertGreater(r4['before_v'], 500)
        self.assertEqual(s['sides']['w']['blunders'], 1)
        self.assertEqual(s['sides']['b']['blunders'], 0)
        self.assertEqual(s['params']['depth'], 10)
        # 参数一致就跳过，--force 重算
        msgs = []
        A.analyse_run(d, depth=10, log=msgs.append)
        self.assertTrue(any('跳过' in m for m in msgs))
        msgs = []
        A.analyse_run(d, depth=10, force=True, log=msgs.append)
        self.assertFalse(any('跳过' in m for m in msgs))

    def test_mate_scores(self):
        # 愚者杀：1.f3 e5 2.g4?? Qh4#
        d = make_run(self.root, 'chess', ['f2f3', 'e7e5', 'g2g4', 'd8h4'], end={'winner': 'b', 'reason': '将死'})
        A.analyse_run(d, depth=10, log=QUIET)
        rows = read_rows(d)
        r3, r4 = rows[2], rows[3]
        self.assertEqual(r3['after'], 'mate -1')   # 白走完被一步杀
        self.assertEqual(r3['after_v'], -1000)
        self.assertEqual(r3['cls'], 'blunder')
        self.assertEqual(r3['lichess'], 'Blunder')  # MateCreated
        self.assertIsNone(r3['wc_loss'])
        self.assertEqual(r4['before'], 'mate 1')
        self.assertEqual(r4['after'], 'end +1')    # 走完已经将死，不问引擎
        self.assertEqual(r4['loss'], 0)
        self.assertTrue(r4['decided'])
        self.assertIsNone(r4['cls'])


@unittest.skipIf(FSF_MISSING, '本机没有 fairy-stockfish')
class XiangqiReplay(TmpCase):
    def test_hanging_cannon_is_blunder(self):
        # 炮二平五 马８进７ 炮五进四?? 马７进５：红炮打中卒后被马吃掉
        d = make_run(self.root, 'xiangqi', ['h2e2', 'h9g7', 'e2e6', 'g7e6'])
        s = A.analyse_run(d, depth=10, log=QUIET)
        rows = read_rows(d)
        r3, r4 = rows[2], rows[3]
        self.assertEqual(r3['text'], '炮五进四')
        self.assertGreaterEqual(r3['loss'], 250)
        self.assertEqual(r3['cls'], 'blunder')
        self.assertLess(r3['after_v'], -150)
        self.assertNotIn('lichess', r3)
        self.assertLess(r4['loss'], 100)
        self.assertRegex(r3['best'], r'^[a-i]\d[a-i]\d$')     # 引擎最佳着已换回 ICCS
        self.assertEqual(s['sides']['w']['blunders'], 1)
        self.assertEqual(s['sides']['w']['events'], 1)
        self.assertEqual(s['events_global'], 1)


# ---------------------------------------------------------------- 汇总表
@unittest.skipIf(STOCKFISH_MISSING, '本机没有 stockfish')
class Table(TmpCase):
    def test_unfinished_game_row(self):
        bad = {'type': 'attempt', 'ply': 4, 'side': 'b', 'try': 1, 'player': 'claude:opus', 'move_text': 'e5e4',
               'move': None, 'legal': False, 'reason': '那里没有子', 'usage': usage(9), 'elapsed': 1.0}
        empty = {'type': 'attempt', 'ply': 4, 'side': 'b', 'try': 2, 'player': 'claude:opus', 'reply': '',
                 'flagged': False, 'empty': True, 'usage': usage(9), 'elapsed': 1.0}
        flag = {'type': 'flag', 'ply': 4, 'side': 'b', 'source': 'result', 'session': 's', 'text': 'x'}
        flagged = dict(empty, **{'try': 3, 'flagged': True, 'empty': False})
        d = make_run(self.root, 'chess', ['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1c4', 'g8f6'], model='b', pause=True,
                     extra={4: [bad, empty, flag, flagged]})
        out = os.path.join(self.root, 'tbl')
        rows = A.table_rows([d], depth=6, log=QUIET)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r['side'], r['opponent'], r['effort'], r['memory']), ('b', 'random', 'high', 'session'))
        self.assertFalse(r['finished'])
        self.assertEqual(r['result'], '未完')
        self.assertEqual(r['plies'], 3)
        self.assertEqual((r['illegal'], r['retries'], r['flags'], r['empty']), (1, 3, 1, 1))
        # 每步总输入 = in + cache_read + cache_write，按 move 的合计；黑方三步是 2000/4000/6000 缓存读
        self.assertEqual(r['median_input'], 2 + 4000 + 100)
        self.assertEqual(r['median_cache_read'], 4000)
        self.assertEqual(r['input_thirds'], [2102, 4102, 6102])
        self.assertEqual(r['cost'], round(0.01 * 6, 4))       # 三步合法 + 三次退回，每次 0.01
        self.assertIsNotNone(r['lichess_blunders'])
        md = A.markdown(rows)
        self.assertIn('未完', md)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(A.main(['--table', '--quiet', '--depth', '6', '--out', out, d]), 0)
        with open(out + '.json', encoding='utf-8') as f:
            self.assertEqual(json.load(f)[0]['result'], '未完')


if __name__ == '__main__':
    unittest.main()
