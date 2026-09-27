"""局面题模式的离线测试：局面加载、状态构造、提示、作答记录与续跑（claude 调用换成假的）、规则判定、lichess 判级、引擎判定。

绝不调 claude：claude_cli.call / version 都打桩。记录写进 tempfile.mkdtemp() 的独立目录，跑完删掉。
"""
import contextlib, io, json, os, shutil, tempfile, unittest
from unittest import mock

import chess

from llmchess import claude_cli, quiz as Q, records, runner, xiangqi as X
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

    def test_reason_on_adds_one_sentence_off_unchanged(self):
        for game, side in (('xiangqi', 'w'), ('chess', 'b')):
            G = Q.game_module(game)
            p = positions(game)[0]
            st = Q.build_state(p)
            off = Q.quiz_cfg(G, game, side, 'high', 'opus', '/tmp/x')['system'][side]
            off2 = Q.quiz_cfg(G, game, side, 'high', 'opus', '/tmp/x', {'reason': 'off'})['system'][side]
            on = Q.quiz_cfg(G, game, side, 'high', 'opus', '/tmp/x', {'reason': 'on'})['system'][side]
            self.assertEqual(off, G.system_prompt(side, Q.side_cfg(G, 'high'), Q.memory.system_text(Q.side_cfg(G, 'high'))))
            self.assertEqual(off, off2)
            self.assertNotIn(Q.REASON_ASK, off)
            self.assertEqual(on, off + '\n\n' + Q.REASON_ASK)
            # 用户提示两档一样，只差系统提示那一句
            self.assertEqual(Q.prompt_of(G, st, Q.side_cfg(G, 'high', {'reason': 'on'})),
                             Q.prompt_of(G, st, Q.side_cfg(G, 'high')))
        self.assertIn('为什么这么走', Q.REASON_ASK)
        self.assertIn('「着法: 」', Q.REASON_ASK)
        for bad in ('思考', '思路', '候选'):                                  # 别像在索取内部思考，也不设栏目
            self.assertNotIn(bad, Q.REASON_ASK)
        with self.assertRaises(SystemExit):
            Q.parse_sets(Q.game_module('chess'), ['reason=maybe'])


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


def legal_reply(cmd, prompt, cwd, **k):
    """假 claude：从提示里的 FEN 取第一步合法着法作答（只用于国际象棋）。"""
    b = chess.Board(' '.join(prompt.split('FEN：')[1].split()[0:6]))
    return fake_reply('着法: %s' % next(iter(b.legal_moves)).uci()), 0.1


class Arms(unittest.TestCase):
    """分档：路径、--set 冲突、局面冲突、旧布局兼容、attackmap 开关、超时记录带题号。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-quiz-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out = os.path.join(self.tmp, 'batch')

    def main(self, *extra, call=legal_reply):
        argv = ['run', '--game', 'chess', '--ids', 'c01', '--efforts', 'medium', '--reps', '1', '--jobs', '1',
                '--out', self.out] + list(extra)
        with mock.patch.object(claude_cli, 'call', call), mock.patch.object(claude_cli, 'version', lambda: 'test'):
            rc = quiet(Q.main, argv)
        for d in Q.judge_units(self.out):
            meta = Q.read_meta(Q.unit_dir(self.out, *d))
            if meta:
                self.addCleanup(shutil.rmtree, meta['claude_cwd'], ignore_errors=True)
        return rc

    def test_arm_layout_and_set_conflict(self):
        self.assertEqual(self.main('--arm', 'sc', '--set', 'selfcheck=on'), 0)
        d = os.path.join(self.out, 'sc', 'chess')
        self.assertTrue(os.path.exists(Q.answer_path(d, 'c01', 'medium', 1)))
        recs = records.read(Q.answer_path(d, 'c01', 'medium', 1))
        self.assertEqual(recs[0]['arm'], 'sc')
        self.assertIn('每步落子前先自查', recs[0]['cfg']['system']['b'])
        self.assertEqual(Q.read_meta(d)['set'], {'selfcheck': 'on'})
        self.assertEqual(self.main('--arm', 'sc', '--set', 'selfcheck=on'), 0)       # 同设置续跑：不再调
        with self.assertRaises(SystemExit):
            self.main('--arm', 'sc', '--set', 'legal=list')
        with self.assertRaises(SystemExit):
            self.main('--set', 'legal=list')                                        # --set 要带 --arm
        with self.assertRaises(SystemExit):
            self.main('--arm', 'x', '--set', 'recite=on')                           # 国际象棋没有复述
        with self.assertRaises(SystemExit):
            self.main('--arm', 'chess')
        self.assertEqual(Q.judge_units(self.out), [('sc', 'chess')])

    def test_reason_arm_records_prompt(self):
        self.assertEqual(self.main('--arm', 'reason', '--set', 'reason=on'), 0)
        recs = records.read(Q.answer_path(os.path.join(self.out, 'reason', 'chess'), 'c01', 'medium', 1))
        self.assertTrue(recs[0]['cfg']['system']['b'].endswith(Q.REASON_ASK))
        self.assertEqual(recs[0]['set'], {'reason': 'on'})

    def test_show_arm_records(self):
        self.assertEqual(self.main('--arm', 'fen', '--set', 'show=fen'), 0)
        recs = records.read(Q.answer_path(os.path.join(self.out, 'fen', 'chess'), 'c01', 'medium', 1))
        self.assertEqual(recs[0]['set'], {'show': 'fen'})
        self.assertEqual(recs[0]['cfg']['sides']['b']['view'], ['fen'])
        att = next(r for r in recs if r['type'] == 'attempt')
        self.assertIn('FEN：', att['prompt'])
        self.assertNotIn('字符棋盘', att['prompt'])
        self.assertEqual(recs[-1]['type'], 'result')
        self.assertEqual(recs[-1]['show'], 'fen')

    def test_positions_conflict_in_same_arm(self):
        self.assertEqual(self.main('--arm', 'b'), 0)
        other = os.path.join(self.tmp, 'other.jsonl')
        p = dict(positions('chess')[1], id='c01')                 # 同名 id、不同局面
        with open(other, 'w', encoding='utf-8') as f:
            f.write(json.dumps(p) + '\n')
        with self.assertRaises(SystemExit):
            self.main('--arm', 'b', '--positions', other)
        same = os.path.join(self.tmp, 'same.jsonl')                # 同一局面换个文件：允许，记进 batch.json
        with open(same, 'w', encoding='utf-8') as f:
            f.write(json.dumps(positions('chess')[0]) + '\n')
        self.assertEqual(self.main('--arm', 'b', '--positions', same), 0)
        self.assertEqual(len(Q.read_meta(os.path.join(self.out, 'b', 'chess'))['positions']), 2)

    def test_legacy_layout_unchanged(self):
        self.assertEqual(self.main(), 0)
        self.assertTrue(os.path.exists(Q.answer_path(os.path.join(self.out, 'chess'), 'c01', 'medium', 1)))
        self.assertEqual(self.main('--arm', 'zh'), 0)
        self.assertEqual(Q.judge_units(self.out), [(None, 'chess'), ('zh', 'chess')])
        self.assertEqual(Q.judge_units(self.out, 'zh'), [('zh', 'chess')])
        self.assertEqual(Q.meta_positions(Q.read_meta(os.path.join(self.out, 'chess')), 'batch1', 'chess'),
                         ['data/batch1/chess.jsonl'])

    def test_copy_same_position_between_arms(self):
        self.assertEqual(self.main('--arm', 'zh'), 0)
        newpos = os.path.join(self.tmp, 'b2.jsonl')
        with open(newpos, 'w', encoding='utf-8') as f:
            f.write(json.dumps(dict(positions('chess')[0], id='c2-99')) + '\n')     # 同一局面、新 id
            f.write(json.dumps(dict(positions('chess')[1], id='c2-98')) + '\n')     # 来源里没答过
        quiet(Q.main, ['copy', '--game', 'chess', '--out', self.out, '--from-arm', 'zh', '--arm', 'base',
                       '--positions', newpos])
        d = os.path.join(self.out, 'base', 'chess')
        res = Q.result_of(Q.answer_path(d, 'c2-99', 'medium', 1))
        self.assertEqual((res['pos'], res['arm']), ('c2-99', 'base'))
        self.assertIn('copied_from', res)
        self.assertEqual(sorted(os.listdir(d)), ['batch.json', 'c2-99-medium-r1.jsonl'])
        with mock.patch.object(claude_cli, 'call', side_effect=AssertionError('不该再调')):
            self.assertEqual(self.main('--arm', 'base', '--positions', newpos, '--ids', 'c2-99'), 0)
        with self.assertRaises(SystemExit):                                      # 目标档设置不同：不复制
            self.main('--arm', 'sc', '--set', 'selfcheck=on')
            quiet(Q.main, ['copy', '--game', 'chess', '--out', self.out, '--from-arm', 'zh', '--arm', 'sc',
                           '--positions', newpos])

    def test_attackmap_gate(self):
        with self.assertRaises(SystemExit) as cm:
            self.main('--arm', 'am', '--set', 'attackmap=on')
        self.assertIn('待用户拍板', str(cm.exception))
        self.assertFalse(os.path.exists(self.out))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            Q.main(['run', '--game', 'xiangqi', '--ids', 'x01', '--arm', 'am', '--set', 'attackmap=on', '--dry-run'])
        self.assertIn('对方现在能吃到你的子', buf.getvalue())
        self.assertIn('黑马 g2 能吃', buf.getvalue())

    def test_call_fail_tagged_in_answer_file(self):
        def call(cmd, prompt, cwd, **k):
            self.assertEqual(k['timeout'], 120)
            k['on_fail']({'try': 1, 'timeout': True, 'rc': -1, 'elapsed': 120.0, 'stderr': 'timeout 120s', 'stdout': '',
                          'next_wait': 30})
            return legal_reply(cmd, prompt, cwd)
        self.assertEqual(self.main('--arm', 't', '--timeout', '120', call=call), 0)
        path = Q.answer_path(os.path.join(self.out, 't', 'chess'), 'c01', 'medium', 1)
        recs = records.read(path)
        f = [r for r in recs if r['type'] == 'call_fail'][0]
        self.assertEqual((f['pos'], f['effort'], f['rep'], f['arm'], f['ply'], f['timeout']),
                         ('c01', 'medium', 1, 't', 2, True))          # 谜题状态里已有对手那一步
        res = Q.result_of(path)
        self.assertEqual((res['call_fails'], res['timeouts']), (1, 1))
        self.assertEqual(recs[0]['cfg']['timeout'], 120)


class Show(unittest.TestCase):
    """show 档（呈现方式）：四档两种棋都能出提示；all 和改动前逐字一致；其余档只含自己那一种呈现，行棋方、执哪方都在。"""
    FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures')
    IDS = {'xiangqi': 'x2-01', 'chess': 'c2-01'}
    # 各种呈现的标志文字：文字棋盘 / 子力清单 / FEN 串
    MARK = {'xiangqi': {'board': '棋盘（上方是黑方', 'pieces': '子力清单', 'fen': 'FEN：'},
            'chess': {'board': '字符棋盘', 'pieces': '子力清单', 'fen': 'FEN：'}}
    SIDE = {'xiangqi': '红方', 'chess': '白方'}

    def pos(self, game):
        return next(p for p in Q.load_positions(Q.positions_path('batch2', game)) if p['id'] == self.IDS[game])

    def dry_run(self, game, *extra):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = Q.main(['run', '--game', game, '--batch', 'batch2', '--ids', self.IDS[game], '--efforts', 'high',
                         '--dry-run'] + list(extra))
        self.assertEqual(rc, 0)
        return buf.getvalue()

    def test_all_matches_prompt_before_change(self):
        # fixtures 是加 show 之前 --dry-run 的原样输出（系统提示 + 用户提示）
        for game in Q.GAMES:
            with open(os.path.join(self.FIXTURE, 'quiz_prompt_%s.txt' % self.IDS[game]), encoding='utf-8') as f:
                want = f.read()
            self.assertEqual(self.dry_run(game), want)
            self.assertEqual(self.dry_run(game, '--arm', 't', '--set', 'show=all'), want)

    def test_each_show_has_only_its_view(self):
        for game in Q.GAMES:
            G = Q.game_module(game)
            st = Q.build_state(self.pos(game))
            side = G.turn(st)
            base = Q.side_cfg(G, 'high')
            sys0, user0 = Q.system_of(G, side, base), Q.prompt_of(G, st, base)
            for show in ('all', 'board', 'pieces', 'fen'):
                with self.subTest(game=game, show=show):
                    sc = Q.side_cfg(G, 'high', Q.parse_sets(G, ['show=' + show]))
                    system, user = Q.system_of(G, side, sc), Q.prompt_of(G, st, sc)
                    self.assertEqual(system, sys0)                         # 系统提示各档一样
                    self.assertIn('执' + self.SIDE[game], system)
                    self.assertIn('轮到你（%s）走' % self.SIDE[game], user)
                    self.assertIn('对方刚走', user)
                    self.assertTrue(user.endswith(user0.split('\n\n')[-1]))   # 最后「请走一步」那句一样
                    if show == 'all':
                        self.assertEqual(user, user0)
                        continue
                    for kind, mark in self.MARK[game].items():
                        (self.assertIn if kind == show else self.assertNotIn)(mark, user)
                    # 除呈现那段以外一字不差：开头几行、结尾一样，中间只有这一段
                    head = user0.split('\n\n')[0]
                    self.assertEqual(user, '\n\n'.join([head, G.VIEWS[Q.SHOW_VIEWS[game][show]](
                        *((st,) if game == 'chess' else (st['fens'][-1], X.board_of(st['fens'][-1])[0]))), user0.split('\n\n')[-1]]))

    def test_bad_value_and_view_conflict(self):
        G = Q.game_module('xiangqi')
        with self.assertRaises(SystemExit):
            Q.parse_sets(G, ['show=grid'])
        with self.assertRaises(SystemExit):
            Q.parse_sets(G, ['show=fen', 'view=fen'])
        self.assertEqual(Q.show_of({}), 'all')
        self.assertEqual(Q.show_of({'view': 'fen'}), None)
        self.assertEqual(Q.show_of({'show': 'pieces'}), 'pieces')

    def test_boardpieces_xiangqi_is_all_minus_fen(self):
        # boardpieces（第 4P2 批新增，只有中国象棋有）：文字棋盘 + 子力清单，逐字等于 all 去掉 FEN 那一段
        game = 'xiangqi'
        G = Q.game_module(game)
        st = Q.build_state(self.pos(game))
        side = G.turn(st)
        sc_all = Q.side_cfg(G, 'high', Q.parse_sets(G, ['show=all']))
        sc_bp = Q.side_cfg(G, 'high', Q.parse_sets(G, ['show=boardpieces']))
        user_all, user_bp = Q.prompt_of(G, st, sc_all), Q.prompt_of(G, st, sc_bp)
        parts_all = user_all.split('\n\n')
        self.assertIn('FEN：', parts_all[-2])                   # all 里 FEN 段在「请走一步」那句之前
        self.assertEqual(user_bp, '\n\n'.join(parts_all[:-2] + parts_all[-1:]))
        self.assertIn(self.MARK[game]['board'], user_bp)
        self.assertIn(self.MARK[game]['pieces'], user_bp)
        self.assertNotIn(self.MARK[game]['fen'], user_bp)

    def test_boardpieces_not_defined_for_chess(self):
        G = Q.game_module('chess')
        with self.assertRaises(SystemExit):
            Q.side_cfg(G, 'high', Q.parse_sets(G, ['show=boardpieces']))


class Excluded(unittest.TestCase):
    """剔除的局面（x2-25）：run 不再出，旧记录照样能判。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-quiz-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out = os.path.join(self.tmp, 'batch')
        self.pos = {p['id']: p for p in Q.load_positions(Q.positions_path('batch2', 'xiangqi'))}

    def test_batch2_marks_only_x2_25(self):
        self.assertEqual([i for i, p in self.pos.items() if p.get('excluded')], ['x2-25'])
        active = Q.active_positions(list(self.pos.values()))
        self.assertEqual(len(active), len(self.pos) - 1)
        self.assertNotIn('x2-25', [p['id'] for p in active])
        self.assertIn('x2-25', Q.merge_positions([Q._rel(Q.positions_path('batch2', 'xiangqi'))]))   # judge 用的全集

    def run_ids(self, ids):
        def call(cmd, prompt, cwd, **k):
            pid = next(i for i in ids.split(',') if not self.pos[i].get('excluded'))
            return fake_reply('着法: %s' % self.pos[pid]['prev_move']), 0.1
        argv = ['run', '--game', 'xiangqi', '--batch', 'batch2', '--ids', ids, '--efforts', 'medium', '--reps', '1',
                '--jobs', '1', '--out', self.out, '--arm', 'base']
        with mock.patch.object(claude_cli, 'call', call), mock.patch.object(claude_cli, 'version', lambda: 'test'):
            rc = quiet(Q.main, argv)
        meta = Q.read_meta(Q.unit_dir(self.out, 'base', 'xiangqi'))
        if meta:
            self.addCleanup(shutil.rmtree, meta['claude_cwd'], ignore_errors=True)
        return rc

    def test_run_skips_excluded(self):
        self.assertEqual(self.run_ids('x2-24,x2-25'), 0)
        d = Q.unit_dir(self.out, 'base', 'xiangqi')
        self.assertEqual(sorted(n for n in os.listdir(d) if n.startswith('x2-')), ['x2-24-medium-r1.jsonl'])
        with self.assertRaises(SystemExit):
            self.run_ids('x2-25')

    def test_old_answer_to_excluded_still_judged(self):
        d = Q.unit_dir(self.out, 'base', 'xiangqi')
        os.makedirs(d)
        Q.write_meta(d, {'arm': 'base', 'set': {}, 'positions': [Q._rel(Q.positions_path('batch2', 'xiangqi'))]})
        p = self.pos['x2-25']
        records.write(Q.answer_path(d, 'x2-25', 'medium', 1),
                      {'type': 'result', 'pos': 'x2-25', 'game': 'xiangqi', 'effort': 'medium', 'rep': 1,
                       'side': p['turn'], 'move': p['prev_move'], 'forfeit': False, 'gave_up': None, 'attempts': 1,
                       'first_legal': True, 'first_think': 10, 'stat': records.new_stat()})
        with mock.patch.object(Q, 'XQ_DEPTH', 6):
            rows, _ = quiet(Q.judge_game, 'xiangqi', 'batch2', self.out, None, 'base')
        self.assertEqual([(r['pos'], r['move']) for r in rows], [('x2-25', p['prev_move'])])
        self.assertIn('loss', rows[0])


class StopWhileWaiting(unittest.TestCase):
    """局面题多线程：两题都在等额度时收到停止信号，都醒来写 pause，退出码 3；再跑同一条接着答。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-quiz-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(claude_cli.STOP.clear)

    def test_stop_wakes_all_waiters(self):
        import threading
        out = os.path.join(self.tmp, 'b')
        argv = ['run', '--game', 'chess', '--ids', 'c01,c02,c03', '--efforts', 'medium', '--reps', '1', '--jobs', '2',
                '--out', out, '--arm', 'w']
        started = []

        def waiting(cmd, prompt, cwd, **k):
            k['on_wait']({'phase': 'start', 'planned': 600})
            started.append(1)
            if len(started) == 2:
                threading.Timer(0.2, claude_cli.STOP.set).start()
            stopped = claude_cli.STOP.wait(30)
            k['on_wait']({'phase': 'end', 'stopped': stopped})
            raise Paused('等额度解除时收到停止信号')
        with mock.patch.object(claude_cli, 'call', waiting), mock.patch.object(claude_cli, 'version', lambda: 'test'):
            self.assertEqual(quiet(Q.main, argv), 3)
        d = os.path.join(out, 'w', 'chess')
        self.addCleanup(shutil.rmtree, Q.read_meta(d)['claude_cwd'], ignore_errors=True)
        self.assertEqual(len(started), 2)                  # 第三题没开
        for pid in ('c01', 'c02'):
            recs = records.read(Q.answer_path(d, pid, 'medium', 1))
            types = [r['type'] for r in recs]
            self.assertIn('pause', types)
            waits = [r for r in recs if r['type'] == 'limit_wait']
            self.assertEqual([w['phase'] for w in waits], ['start', 'end'])
            self.assertEqual((waits[0]['pos'], waits[0]['arm'], waits[1]['stopped']), (pid, 'w', True))
        with mock.patch.object(claude_cli, 'call', legal_reply), mock.patch.object(claude_cli, 'version', lambda: 'test'):
            self.assertEqual(quiet(Q.main, argv), 0)


class Threats(unittest.TestCase):
    def test_extract(self):
        self.assertIsNone(Q.extract_threats('思路……\n着法: e2e4'))
        self.assertEqual(Q.extract_threats('走后威胁：无\n着法: e2e4'), [])
        self.assertEqual(Q.extract_threats('先想想走后威胁: 待会列\n\n**走后威胁：**\n1. b7i7（砲吃车）\n- g2e3\n\n'
                                           '再说几句\n着法: i6i7'), ['b7i7（砲吃车）', 'g2e3'])
        self.assertEqual(Q.extract_threats('走后威胁:\n- d5b5\n着法: b1b5'), ['d5b5'])

    def test_xiangqi_cannon_screen(self):
        p = positions('xiangqi')[0]                  # x01：车一进一（i6i7），黑砲 b7 借 c7 马做炮架打车
        st = Q.build_state(p)
        fen = st['fens'][-1]
        f1, caps, checks = Q.threat_truth('xiangqi', fen, 'i6i7')
        self.assertIn('b7i7', caps)
        cn = Q.X.notation(f1, 'b7i7')
        reply = '走后威胁:\n- g2e3（马吃兵）\n- %s（吃车）\n- a9a8\n- z9z9\n\n着法: i6i7' % cn
        sc = Q.threat_score('xiangqi', fen, 'i6i7', reply)
        self.assertTrue(sc['found'])
        self.assertIn('b7i7', sc['listed'])          # 中文记谱读成 b7i7
        self.assertEqual(sc['hit'], 2)
        self.assertEqual(sc['miss'], len(sc['true']) - 2)
        self.assertEqual(sc['wrong'], 2)            # a9a8 合法但不是吃子 / 将军；z9z9 读不出坐标、当中文也对不上
        self.assertEqual(sc['unparsed'], 1)

    def test_chess_captures_checks_and_san(self):
        fen = '4k3/8/8/3q4/8/8/P7/1Q2K3 w - - 0 1'
        _, caps, checks = Q.threat_truth('chess', fen, 'b1b3')
        self.assertIn('d5b3', caps)
        self.assertIn('d5d1', checks)
        sc = Q.threat_score('chess', fen, 'b1b3', '走后威胁：\n- d5b3（吃后）\n- Qd1+\n- a2a3\n着法: b1b3')
        self.assertEqual((sc['hit'], sc['wrong'], sc['unparsed']), (2, 1, 1))
        self.assertEqual(sc['miss'], len(sc['true']) - 2)
        none = Q.threat_score('chess', '4k3/8/8/8/8/8/P7/4K3 w - - 0 1', 'a2a3', '走后威胁: 无\n着法: a2a3')
        self.assertEqual((none['none'], none['true'], none['wrong']), (True, [], 0))

    def test_answer_scores_final_attempt_only(self):
        tmp = tempfile.mkdtemp(prefix='llmchess-quiz-test-')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        p = positions('chess')[0]
        replies = iter([fake_reply('走后威胁:\n- a1a2\n着法: a1a1'),
                        fake_reply('走后威胁: 无\n着法: %s' % p['solution_san'])])
        with mock.patch.object(claude_cli, 'call', lambda *a, **k: (next(replies), 1.0)):
            res = quiet(Q.answer_one, p, 'xhigh', 1, tmp, 'opus', tmp, {}, {'threats': 'on'}, 'th')
        self.assertEqual(res['arm'], 'th')
        self.assertTrue(res['threats']['none'])
        self.assertEqual(res['threats']['wrong'], 0)
        cfg = records.read(Q.answer_path(tmp, p['id'], 'xhigh', 1))[0]['cfg']
        self.assertIn('走后威胁', cfg['system'][p['turn']])

    def test_class_and_report_by_arm(self):
        th = {'found': True, 'none': False, 'true': ['a', 'b'], 'listed': ['a'], 'hit': 1, 'miss': 1, 'wrong': 0}
        self.assertEqual(Q.threat_class({'threats': th, 'refute': 'a'}), 'listed')
        self.assertEqual(Q.threat_class({'threats': th, 'refute': 'b'}), 'unlisted')
        self.assertEqual(Q.threat_class({'threats': th, 'refute': 'c'}), 'quiet')
        self.assertEqual(Q.threat_class({'threats': dict(th, found=False), 'refute': 'a'}), 'no_list')
        tmp = tempfile.mkdtemp(prefix='llmchess-quiz-test-')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        base = {'game': 'chess', 'effort': 'xhigh', 'move': 'e2e4', 'first_legal': True, 'loss': 400, 'blunder': True,
                'mistake': False, 'best_match': False, 'solved': False, 'hang': True, 'missed_capture': False,
                'missed_mate': False, 'allows_mate': False, 'stat': dict(records.new_stat(), elapsed=10), 'refute': 'b'}
        for arm, extra in ((None, {}), ('base', {}), ('threats', {'threats': th, 'threat_class': 'unlisted'})):
            d = Q.unit_dir(tmp, arm, 'chess')
            os.makedirs(d)
            with open(os.path.join(d, 'judged.jsonl'), 'w', encoding='utf-8') as f:
                f.write(json.dumps(dict(base, **extra)) + '\n')
        self.assertEqual(quiet(Q.main, ['report', '--out', tmp]), 0)
        with open(os.path.join(tmp, 'report.txt'), encoding='utf-8') as f:
            text = f.read()
        self.assertIn('| 棋种 | 档 | 档位 |', text)
        self.assertIn('| chess | - | xhigh |', text)
        self.assertIn('| chess | base | xhigh |', text)
        self.assertIn('| chess | threats | xhigh | 1 | 1 | 0 | 2 | 1 | 50% | 0 | 0 | 1 | 0 | 1 | 0 | 0 |', text)


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
