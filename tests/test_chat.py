"""新协议（protocol=real）+ llm-chat 后端的离线测试：用一个假的 llm_chat.py（按剧本回话、记下每次的命令行和 stdin）
代替真脚本，走真的 chat.run / claude_cli.call / runner 流程，绝不调模型。

每个用例在自己的临时目录里建假脚本、剧本和记录，跑完删掉。
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from llmchess import chat, chess_ as C, cli, memory, records, runner
from llmchess import xiangqi as X

FAKE = r'''
import json, os, sys, uuid
d = os.environ['FAKE_CHAT_DIR']
argv = sys.argv[1:]
prompt = sys.stdin.read()
with open(os.path.join(d, 'plan.json')) as f:
    plan = json.load(f)
n = len(open(os.path.join(d, 'calls.jsonl')).readlines()) if os.path.exists(os.path.join(d, 'calls.jsonl')) else 0
with open(os.path.join(d, 'calls.jsonl'), 'a') as f:
    f.write(json.dumps({'argv': argv, 'stdin': prompt}, ensure_ascii=False) + '\n')
step = plan[n] if n < len(plan) else {'error': 'plan exhausted'}
if 'text' in step:
    sid = argv[argv.index('--session') + 1] if '--session' in argv else str(uuid.uuid4())
    sys.stdout.write(step['text'] + '\n')
    meta = {'session': sid, 'model': 'fake-model', 'provider': 'fake', 'cache_read': 5, 'cache_write': 1,
            'cost_usd': step.get('cost', 0.01), 'input_tokens': 10, 'output_tokens': 20, 'reasoning_tokens': 15}
    if 'dropped' in step:
        meta['thinking_dropped'] = step['dropped']
    sys.stderr.write('some noise\nLLM_CHAT_META ' + json.dumps(meta) + '\n')
    sys.exit(0)
if step.get('refuse'):
    sys.stderr.write("llm-chat: error: claude failed (exit 1): API Error: Opus 5.5's safeguards flagged this message\n")
    sys.exit(1)
if step.get('empty'):
    sys.stderr.write('llm-chat: error: claude returned an empty answer\n')
    sys.exit(1)
sys.stderr.write('llm-chat: error: ' + step['error'] + '\n')
sys.exit(1)
'''


class FakeChat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-chat-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.fake = os.path.join(self.tmp, 'fake_llm_chat.py')
        with open(self.fake, 'w') as f:
            f.write(FAKE)
        p1 = mock.patch.object(chat, 'SCRIPT', self.fake)
        p2 = mock.patch.dict(os.environ, {'FAKE_CHAT_DIR': self.tmp, 'XDG_STATE_HOME': os.path.join(self.tmp, 'state')})
        p1.start(), p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)

    def plan(self, steps):
        with open(os.path.join(self.tmp, 'plan.json'), 'w') as f:
            json.dump(steps, f, ensure_ascii=False)

    def calls(self):
        with open(os.path.join(self.tmp, 'calls.jsonl')) as f:
            return [json.loads(x) for x in f]

    def play(self, argv):
        with contextlib.redirect_stdout(io.StringIO()):
            return cli.main(['play', '--out', self.tmp] + argv)

    def recs(self, tag):
        return records.read(os.path.join(self.tmp, tag, 'game.jsonl'))

    # ------------------------------------------------------------------ 调用包装
    def test_run_folds_outcomes(self):
        self.plan([{'text': '着法: e2e4'}, {'refuse': True}, {'empty': True}, {'error': 'HTTP 500 from x'}])
        cmd = chat.command('opus', 'medium', system='sys', timeout=30)
        out, err, rc = chat.run(cmd, 'hi', self.tmp, dict(os.environ), 30)
        d = json.loads(out)
        self.assertEqual((rc, d['result'], d['meta']['model']), (0, '着法: e2e4', 'fake-model'))
        d = json.loads(chat.run(cmd, 'hi', self.tmp, dict(os.environ), 30)[0])
        self.assertEqual(d['stop_reason'], 'refusal')
        d = json.loads(chat.run(cmd, 'hi', self.tmp, dict(os.environ), 30)[0])
        self.assertEqual(d['result'], '')
        self.assertEqual(chat.run(cmd, 'hi', self.tmp, dict(os.environ), 30)[2], 1)

    def test_usage_mapping(self):
        d = {'meta': {'input_tokens': 100, 'cache_read': 60, 'output_tokens': 30, 'reasoning_tokens': 20,
                      'cost_usd': 0.5, 'session': 's', 'model': 'm'}}
        self.assertEqual(chat.usage(d, 'claude')['in'], 100)          # Claude 的 input_tokens 本来就不含缓存
        self.assertEqual(chat.usage(d, 'codex')['in'], 40)            # codex / DeepSeek 含缓存命中，要减掉
        self.assertEqual(chat.usage(d, 'deepseek')['text_out'], 10)

    def test_model_id(self):
        slugs = ['gpt-6-astra', 'gpt-6-sol', 'gpt-5.6-sol', 'gpt-5.5']
        self.assertEqual(chat.model_id('codex', 'sol', slugs), 'gpt-6-sol')
        self.assertEqual(chat.model_id('codex', 'gpt-5.6-sol', slugs), 'gpt-5.6-sol')
        self.assertEqual(chat.model_id('deepseek', 'deepseek'), chat.DEEPSEEK_DEFAULT)
        self.assertEqual(chat.model_id('claude', 'opus'), 'opus')
        with self.assertRaises(SystemExit):
            chat.model_id('codex', 'nova', slugs)

    # ------------------------------------------------------------------ 整盘
    def test_xiangqi_session_illegal_retry_and_loose_parse(self):
        # 红方模型对随机：第 1 步先走非法（车 a0 越过 a3 的兵），再只写一行着法；第 3 步用英文「Move:」
        self.plan([{'text': '我走车。\n着法: a0a9', 'cost': 0.01}, {'text': 'h2e2', 'cost': 0.02},
                   {'text': 'I move the rook.\nMove: i0i1', 'cost': 0.04}])
        rc = self.play(['--game', 'xiangqi', '--tag', 'x', '--black', 'random', '--max-plies', '4', '--seed', '3'])
        self.assertEqual(rc, 0)
        calls = self.calls()
        self.assertEqual(len(calls), 3)
        # 第一次新建会话（--system），之后都续接同一个会话
        self.assertIn('--system', calls[0]['argv'])
        sid = [r for r in self.recs('x') if r['type'] == 'attempt' and r['side'] == 'w'][0]['session']
        for c in calls[1:]:
            self.assertEqual(c['argv'][c['argv'].index('--session') + 1], sid)
            self.assertNotIn('--system', c['argv'])
        for c in calls:
            self.assertEqual(c['argv'][c['argv'].index('--effort') + 1], 'medium')   # 思考深度每次显式传
        # 重选提示只说不合法，不说越子；局面提示里不报将军、第二步不重给着法记录
        self.assertIn('这步不合法', calls[1]['stdin'])
        self.assertIn('本步还可重选 2 次', calls[1]['stdin'])
        self.assertNotIn('越子', calls[1]['stdin'])
        for c in (calls[0], calls[2]):
            self.assertNotIn('将军', c['stdin'])
        self.assertIn('对方刚走', calls[2]['stdin'])
        self.assertNotIn('此前已走着法', calls[2]['stdin'])
        self.assertNotIn('子）', calls[0]['stdin'])                   # 子力清单不写子数
        recs = self.recs('x')
        cfg = recs[0]['cfg']
        self.assertEqual((cfg['protocol'], cfg['backend'], cfg['sides']['w']['memory']), ('real', 'llm-chat', 'session'))
        self.assertNotIn('请用中文回答', cfg['system']['w'])
        atts = [r for r in recs if r['type'] == 'attempt' and r['side'] == 'w']
        self.assertEqual([a['legal'] for a in atts], [False, True, True])
        self.assertEqual(atts[0]['feedback'], 'illegal')
        self.assertIn('越子', atts[0]['reason'])                       # 完整原因只进记录
        self.assertEqual([round(a['usage']['cost'], 4) for a in atts], [0.01, 0.02, 0.04])
        costs = records.attempt_costs(recs)[0]
        self.assertEqual([round(costs[id(a)], 4) for a in atts], [0.01, 0.02, 0.04])
        end = [r for r in recs if r['type'] == 'end'][0]
        self.assertEqual(end['summary']['w']['illegal'], 1)

    def test_forfeit_after_three_illegal(self):
        # real 下一手棋最多 3 次（用户 2026-09-29 定）：第 3 次仍非法直接判负，不再调第 4 次
        self.plan([{'text': '着法: a0a9'}, {'text': '没想好'}, {'text': 'Move: zz'}, {'text': '着法: h2e2'}])
        rc = self.play(['--game', 'xiangqi', '--tag', 'f', '--black', 'random', '--max-plies', '4'])
        self.assertEqual(rc, 0)
        calls = self.calls()
        self.assertEqual(len(calls), 3)
        self.assertIn('本步还可重选 2 次', calls[1]['stdin'])
        self.assertIn('这步的写法认不出来', calls[2]['stdin'])            # 「没想好」按最后一行读，认不出
        self.assertIn('本步还可重选 1 次', calls[2]['stdin'])
        recs = self.recs('f')
        self.assertEqual(recs[0]['cfg']['retries'], 2)
        self.assertIn('一步里连续 3 次都没给出合法着法判负', recs[0]['cfg']['system']['w'])   # 赛制预先写进系统提示
        end = [r for r in recs if r['type'] == 'forfeit'][0]['end']
        self.assertEqual(end['winner'], 'b')
        self.assertIn('连续 3 次', end['reason'])

    def test_legacy_keeps_four_attempts(self):
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(['play', '--out', self.tmp, '--game', 'chess', '--tag', 'lg', '--protocol', 'legacy',
                      '--white', 'random', '--black', 'random', '--max-plies', '2', '--seed', '1'])
        self.assertEqual(self.recs('lg')[0]['cfg']['retries'], 3)

    def test_old_record_resumes_with_its_own_limit(self):
        # 改之前开的 real 盘 config 里记的是 retries=3（一步 4 次）：续跑照记录，系统提示和余下次数都不变
        self.plan([{'text': '着法: a0a9'}])
        with mock.patch.object(runner.claude_cli, '_wait', lambda s: True):
            rc = self.play(['--game', 'xiangqi', '--tag', 'o', '--black', 'random', '--max-plies', '2',
                            '--retries', '3'])
        self.assertEqual(rc, 3)
        self.assertIn('一步里连续 4 次', self.recs('o')[0]['cfg']['system']['w'])
        self.plan([{'text': '着法: a0a9'}, {'text': '着法: a0a9'}, {'text': '着法: a0a9'}])
        os.remove(os.path.join(self.tmp, 'calls.jsonl'))
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(['resume', os.path.join(self.tmp, 'o')])
        self.assertEqual(rc, 0)
        c = self.calls()
        self.assertEqual(len(c), 3)
        self.assertIn('还可重选 3 次', c[0]['stdin'])
        self.assertIn('连续 4 次', [r for r in self.recs('o') if r['type'] == 'forfeit'][0]['end']['reason'])

    def test_refusal_on_first_turn_resends_full_prompt(self):
        # 第一轮被拦时 llm-chat 不存会话：重问要带系统提示和完整局面，不能只发「请重新回答」
        self.plan([{'refuse': True}, {'text': '着法: e2e4'}, {'text': '着法: d2d4'}])
        rc = self.play(['--game', 'chess', '--tag', 'r', '--black', 'random', '--max-plies', '3', '--seed', '1'])
        self.assertEqual(rc, 0)
        calls = self.calls()
        self.assertIn('--system', calls[1]['argv'])
        self.assertIn('FEN', calls[1]['stdin'])
        flags = [r for r in self.recs('r') if r['type'] == 'flag']
        self.assertEqual(len(flags), 1)
        self.assertIn('--session', calls[2]['argv'])

    def test_chess_last_move_is_uci_only(self):
        self.plan([{'text': '着法: e7e5'}])
        self.play(['--game', 'chess', '--tag', 'c', '--white', 'random', '--black', 'claude:opus',
                   '--max-plies', '2', '--seed', '5'])
        p = self.calls()[0]['stdin']
        mv = [r for r in self.recs('c') if r['type'] == 'move'][0]['move']
        self.assertIn('对方刚走：%s\n' % mv, p)
        self.assertIn('此前已走着法（UCI）：\n1. %s' % mv, p)

    def test_resume_keeps_session_and_pending_feedback(self):
        self.plan([{'text': '着法: a0a9'}])            # 一次非法后剧本用完 → 调不通；等重试时直接停
        with mock.patch.object(runner.claude_cli, '_wait', lambda s: True):
            rc = self.play(['--game', 'xiangqi', '--tag', 'p', '--black', 'random', '--max-plies', '2'])
        self.assertEqual(rc, 3)
        self.plan([{'text': '着法: a0a9'}, {'text': '着法: h2e2'}])
        os.remove(os.path.join(self.tmp, 'calls.jsonl'))
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(['resume', os.path.join(self.tmp, 'p')])
        self.assertEqual(rc, 0)
        c = self.calls()
        self.assertIn('--session', c[0]['argv'])
        self.assertIn('还可重选 2 次', c[0]['stdin'])            # 暂停前用掉的一次照记录接上
        self.assertIn('还可重选 1 次', c[1]['stdin'])


    def test_reason_default_brief_and_goes_into_pgn_comment(self):
        # 默认请棋手在着法前写理由；理由里提到别的着法（Nf3、d4）不影响读着法，落定那次的理由进该步评注
        self.plan([{'text': '也可以 Nf3，但我想先占中心，d4 留到下一步。\n\n着法: e2e4'},
                   {'text': '中心已经有兵了，再出马。\nMove: g1f3'}])
        rc = self.play(['--game', 'chess', '--tag', 'rs', '--black', 'random', '--max-plies', '3', '--seed', '2'])
        self.assertEqual(rc, 0)
        recs = self.recs('rs')
        cfg = recs[0]['cfg']
        self.assertEqual(cfg['sides']['w']['reason'], 'brief')
        self.assertEqual(cfg['sides']['w']['drop_thinking'], 'off')
        self.assertIn(memory.ANSWER_LEAD['brief'], cfg['system']['w'])
        self.assertIn('简短写出', cfg['system']['w'])
        self.assertIn(memory.ANSWER_LEAD['brief'], self.calls()[0]['argv'][self.calls()[0]['argv'].index('--system') + 1])
        self.assertNotIn('--drop-thinking', self.calls()[0]['argv'])
        self.assertNotIn('thinking_dropped', [r for r in recs if r['type'] == 'attempt'][0])
        self.assertNotIn('drop_warn', [r['type'] for r in recs])
        moves = [r['move'] for r in recs if r['type'] == 'move' and r['side'] == 'w']
        self.assertEqual(moves, ['e2e4', 'g1f3'])
        with open(os.path.join(self.tmp, 'rs', 'game.pgn')) as f:
            pgn = f.read()
        self.assertIn('我想先占中心，d4 留到下一步。', pgn)
        self.assertIn('中心已经有兵了，再出马。', pgn)

    def test_xiangqi_reason_goes_into_record(self):
        self.plan([{'text': '先架中炮，马八进七也可以。\n着法: h2e2'}])
        self.play(['--game', 'xiangqi', '--tag', 'rx', '--black', 'random', '--max-plies', '2', '--seed', '4'])
        with open(os.path.join(self.tmp, 'rx', 'record.txt')) as f:
            self.assertIn('先架中炮，马八进七也可以。', f.read())
        self.assertEqual([r['move'] for r in self.recs('rx') if r['type'] == 'move'][0], 'h2e2')

    def test_reason_off_keeps_old_prompt(self):
        self.plan([{'text': '着法: h2e2'}])
        self.play(['--game', 'xiangqi', '--tag', 'ro', '--black', 'random', '--max-plies', '2', '--reason', 'off'])
        cfg = self.recs('ro')[0]['cfg']
        self.assertEqual(cfg['sides']['w']['reason'], 'off')
        self.assertIn('回答格式：只需给出着法，写成一行「着法: 」加着法，', cfg['system']['w'])
        self.assertNotIn('理由', cfg['system']['w'])

    # ------------------------------------------------------------------ 去掉此前思考（drop_thinking）
    def test_drop_thinking_per_side_flag_first_turn_and_warn(self):
        # 白方开：只在会话首轮传 --drop-thinking，理由默认跟着变详细；每次调用记 thinking_dropped，续接轮为 0 告警不中断
        self.plan([{'text': '着法: e2e4', 'dropped': 0}, {'text': '着法: g1f3', 'dropped': 1},
                   {'text': '着法: f1c4', 'dropped': 0}])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = cli.main(['play', '--out', self.tmp, '--game', 'chess', '--tag', 'dt', '--black', 'random',
                           '--max-plies', '5', '--seed', '3', '--w', 'drop_thinking=on'])
        self.assertEqual(rc, 0)
        recs = self.recs('dt')
        cfg = recs[0]['cfg']
        self.assertEqual((cfg['sides']['w']['drop_thinking'], cfg['sides']['w']['reason']), ('on', 'detailed'))
        self.assertEqual((cfg['sides']['b']['drop_thinking'], cfg['sides']['b']['reason']), ('off', 'brief'))
        self.assertIn(memory.ANSWER_LEAD['detailed'], cfg['system']['w'])
        self.assertIn('--drop-thinking', cfg['commands']['w'])
        c = self.calls()
        self.assertEqual(len(c), 3)
        self.assertIn('--drop-thinking', c[0]['argv'])
        self.assertIn('--system', c[0]['argv'])
        for x in c[1:]:
            self.assertIn('--session', x['argv'])
            self.assertNotIn('--drop-thinking', x['argv'])
        atts = [r for r in recs if r['type'] == 'attempt' and r['side'] == 'w']
        self.assertEqual([a['thinking_dropped'] for a in atts], [0, 1, 0])
        warns = [r for r in recs if r['type'] == 'drop_warn']
        self.assertEqual(len(warns), 1)                           # 首轮的 0 不算
        self.assertEqual((warns[0]['ply'], warns[0]['thinking_dropped'], warns[0]['prev_think']), (5, 0, 15))
        self.assertIn('thinking_dropped=0', out.getvalue())
        self.assertEqual(recs[-1]['type'], 'end')
        meta = records.move_meta(recs)
        self.assertEqual([meta[p]['dropped'] for p in (1, 3, 5)], [0, 1, 0])
        with open(os.path.join(self.tmp, 'dt', 'game.pgn')) as f:
            pgn = f.read()
        self.assertIn('[%dropped 1]', pgn)

    def test_drop_thinking_reason_override_and_resume(self):
        # 显式给 reason 就照给的；暂停后续跑接同一会话，不再传 --drop-thinking，续接轮照样查 thinking_dropped
        self.plan([{'text': '着法: e2e4', 'dropped': 0}, {'text': '着法: g1f3', 'dropped': 0}])
        rc = self.play(['--game', 'chess', '--tag', 'dr', '--black', 'random', '--max-plies', '3', '--seed', '3',
                        '--drop-thinking', 'on', '--black', 'random', '--w', 'reason=brief', '--stop-after', '2'])
        self.assertEqual(rc, 3)
        cfg = self.recs('dr')[0]['cfg']
        self.assertEqual((cfg['sides']['w']['drop_thinking'], cfg['sides']['w']['reason']), ('on', 'brief'))
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(['resume', os.path.join(self.tmp, 'dr')])
        self.assertEqual(rc, 0)
        c = self.calls()
        self.assertIn('--drop-thinking', c[0]['argv'])
        self.assertIn('--session', c[1]['argv'])
        self.assertNotIn('--drop-thinking', c[1]['argv'])
        warns = [r for r in self.recs('dr') if r['type'] == 'drop_warn']
        self.assertEqual([(w['ply'], w['prev_think']) for w in warns], [(3, None)])   # 续跑后上一轮思考不知道

    def test_drop_thinking_rejected_before_start(self):
        # GPT / DeepSeek 棋手开、非 session、legacy、旧写法 reason=on：开局前就报错，一次模型都不调
        self.plan([])
        bad = [['--black', 'codex:gpt-6-sol', '--b', 'drop_thinking=on'],
               ['--black', 'deepseek', '--drop-thinking', 'on', '--effort', 'high'],
               ['--black', 'random', '--drop-thinking', 'on', '--memory', 'stateless'],
               ['--black', 'random', '--protocol', 'legacy', '--drop-thinking', 'on'],
               ['--black', 'random', '--reason', 'on'],
               ['--black', 'random', '--w', 'drop_thinking=yes']]
        for i, extra in enumerate(bad):
            with self.subTest(extra=extra), self.assertRaises(SystemExit):
                self.play(['--game', 'chess', '--tag', 'bad%d' % i, '--max-plies', '2'] + extra)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'calls.jsonl')))
        # 对手是引擎 / 随机时公共开关不碍事（它们不看这一项）；dry-run 能看到详细理由的提示
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.main(['play', '--game', 'chess', '--black', 'random', '--drop-thinking', 'on', '--dry-run'])
        self.assertIn(memory.ANSWER_LEAD['detailed'], out.getvalue())


class RealProtocolPrompts(unittest.TestCase):
    def test_legacy_prompt_unchanged_without_protocol(self):
        sc = {'memory': 'stateless', 'selfcheck': 'off', 'max_plies': 200}
        s = X.system_prompt('w', sc, memory.system_text(sc))
        self.assertIn('请用中文回答', s)
        self.assertIn('长将判负（这类着法会被当作不合规退回）', s)

    def test_feedback_classes(self):
        self.assertEqual(X.feedback(None, '回复里没有找到「着法: 」那一行'), 'no_move')
        self.assertEqual(X.feedback('xx', '既不是 ICCS 坐标，也对不上任何一步合法着法的中文记谱'), 'unreadable')
        self.assertEqual(X.feedback('e0e1', X.BANNED_REASON), 'illegal')
        self.assertEqual(C.feedback('Nd2', '「Nd2」有两个以上的子都能走，要写明是哪一个（如 Nbd2）'), 'ambiguous')
        self.assertEqual(C.feedback('e1e2', '王从 e1 走到 e2 不合规：走完自己被将'), 'illegal')

    def test_extract_move_loose(self):
        self.assertEqual(memory.extract_move('Move: Nf3', loose=True), 'Nf3')
        self.assertEqual(memory.extract_move('**e2e4**', loose=True), 'e2e4')
        self.assertIsNone(memory.extract_move('Move: Nf3'))
        self.assertIsNone(memory.extract_move('a' * 40, loose=True))

    def test_reason_switch_per_side_and_old_records(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.main(['play', '--game', 'chess', '--b', 'reason=off', '--dry-run'])
        w, b = out.getvalue().split('== 系统提示（黑方')[:2]
        self.assertIn(memory.ANSWER_LEAD['brief'], w)
        self.assertIn(memory.ANSWER_LEAD['off'], b)
        # 改之前的 real 记录 config 里没有 reason：按 off 走，提示和原来逐字相同
        sc = {'protocol': 'real', 'memory': 'session', 'selfcheck': 'off', 'max_plies': 200, 'retries': 3}
        self.assertIn('回答格式：只需给出着法，', X.system_prompt('w', sc, memory.system_text(sc)))

    def test_reason_rejected_under_legacy_and_not_recorded(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(io.StringIO()):
                cli.main(['play', '--game', 'chess', '--protocol', 'legacy', '--reason', 'on', '--dry-run'])
        a = mock.Mock(protocol='legacy', **{k: None for k in cli.SIDE_KEYS})
        a.configure_mock(effort='medium', memory=None, history=-1, legal='none', selfcheck='off', recite='off',
                         notes_keep=1, session_view='full', retries=3)
        self.assertNotIn('reason', cli.side_cfg(a, C, None, 200))

    def test_quiz_real_reason_not_doubled(self):
        from llmchess import quiz
        sc = dict(quiz.side_cfg(C, 'high', {'reason': 'on'}), protocol='real', retries=3)
        s = quiz.system_of(C, 'w', sc)
        self.assertIn(quiz.REASON_ASK, s)
        self.assertNotIn(memory.ANSWER_LEAD['brief'], s)
        self.assertNotIn(memory.ANSWER_LEAD['detailed'], s)

    def test_real_rejects_legal_list(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(io.StringIO()):
                cli.main(['play', '--game', 'chess', '--legal', 'list', '--dry-run'])


if __name__ == '__main__':
    unittest.main()
