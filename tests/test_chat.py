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
import subprocess
import unittest
from unittest import mock

from llmchess import batch, chat, chess_ as C, cli, memory, records, runner
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
    meta.update(step.get('extra_meta', {}))
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
        self.assertEqual(chat.usage(d, 'gemini')['in'], 40)

    def test_model_id(self):
        slugs = ['gpt-6-astra', 'gpt-6-sol', 'gpt-5.6-sol', 'gpt-5.5']
        self.assertEqual(chat.model_id('codex', 'sol', slugs), 'gpt-6-sol')
        self.assertEqual(chat.model_id('codex', 'gpt-5.6-sol', slugs), 'gpt-5.6-sol')
        self.assertEqual(chat.model_id('deepseek', 'deepseek'), chat.DEEPSEEK_DEFAULT)
        self.assertEqual(chat.model_id('deepseek', 'v4-pro'), 'deepseek-v4-pro')
        self.assertEqual(chat.model_id('deepseek', 'flash'), 'deepseek-flash')
        self.assertEqual(chat.model_id('deepseek', 'deepseek-flash'), 'deepseek-flash')
        self.assertEqual(chat.model_id('claude', 'opus'), 'opus')
        self.assertEqual(chat.model_id('agy', 'claude-opus-5-5-high'), 'agy/claude-opus-5-5-high')
        self.assertEqual(chat.model_id('agy', 'gemini-4-argon-high'), 'agy/gemini-4-argon-high')
        for name in ('', 'agy/claude-opus-5-5-high', '../opus', 'opus:high', ' opus'):
            with self.assertRaises(SystemExit):
                chat.model_id('agy', name)
        self.assertEqual(chat.model_id('gemini', 'gemini-3.8-flash-high'), 'gemini-3.8-flash-high')
        for name in ('', 'flash', 'google/gemini-3.8-flash-high'):
            with self.assertRaises(SystemExit):
                chat.model_id('gemini', name)
        with self.assertRaises(SystemExit):
            chat.model_id('codex', 'nova', slugs)

    # ------------------------------------------------------------------ 整盘
    def test_agy_chess_sessions_and_batch_entry(self):
        self.plan([{'text': '着法: e2e4'}, {'text': '着法: e7e5'},
                   {'text': '着法: g1f3'}, {'text': '着法: b8c6'}])
        white, black = 'gemini:gemini-4-argon-high', 'agy:claude-opus-5-5-high'
        self.assertEqual(batch.full_spec(black), black)
        self.assertEqual(self.play(['--game', 'chess', '--tag', 'agy-chess', '--white', white,
                                    '--black', black, '--effort', 'high', '--max-plies', '4']), 0)
        recs, calls = self.recs('agy-chess'), self.calls()
        self.assertEqual(recs[0]['cfg']['models'], {'w': 'gemini-4-argon-high', 'b': 'agy/claude-opus-5-5-high'})
        starts = [r for r in recs if r['type'] == 'call_started']
        atts = [r for r in recs if r['type'] == 'attempt']
        self.assertEqual(len(starts), 4)
        self.assertEqual([r['call_id'] for r in starts], [r['call_id'] for r in atts])
        for n, call in enumerate(calls):
            argv = call['argv']
            self.assertEqual(argv[argv.index('-m') + 1], recs[0]['cfg']['models']['wb'[n % 2]])
            self.assertEqual(argv[argv.index('--effort') + 1], 'high')
            if n >= 2:
                self.assertEqual(argv[argv.index('--session') + 1], atts[n - 2]['session'])
        self.assertNotEqual(atts[0]['session'], atts[1]['session'])

    def test_agy_rejected_before_start(self):
        for extra in (['--protocol', 'legacy'], ['--w', 'drop_thinking=on']):
            with self.assertRaises(SystemExit):
                self.play(['--game', 'chess', '--tag', 'bad-agy',
                           '--white', 'agy:claude-opus-5-5-high', '--black', 'random'] + extra)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'calls.jsonl')))

    def test_agy_failure_blocks_retry_and_resume(self):
        for n, failure in enumerate(({'error': '503 No capacity available'},
                                     {'error': 'rate limit exceeded'}, {'empty': True}, {'text': ''})):
            with self.subTest(failure=failure):
                self.plan([failure] * (n + 1))
                tag = 'agy-uncertain%d' % n
                with mock.patch.object(runner.claude_cli, '_wait') as wait:
                    self.assertEqual(self.play(['--game', 'chess', '--tag', tag, '--white',
                                               'agy:claude-opus-5-5-high', '--black', 'random',
                                               '--max-plies', '1']), 3)
                wait.assert_not_called()
                recs = self.recs(tag)
                self.assertEqual(sum(r['type'] == 'call_started' for r in recs), 1)
                fail = next(r for r in recs if r['type'] == 'call_fail')
                self.assertEqual(fail['outcome'], 'uncertain')
                self.assertIsNone(fail['next_wait'])
                self.assertFalse(any(r['type'] in ('move', 'end', 'forfeit') for r in recs))
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(['resume', os.path.join(self.tmp, tag)]), 3)
                    self.assertIsNone(runner.play(runner.load(C, os.path.join(self.tmp, tag))))
                self.assertEqual(len(self.calls()), n + 1)

    def test_agy_pending_call_locks_before_dispatch(self):
        self.plan([{'text': '着法: e2e4'}, {'text': '着法: g1f3'}])
        tag = 'agy-pending'
        self.assertEqual(self.play(['--game', 'chess', '--tag', tag, '--white', 'agy:claude-opus-5-5-high',
                                    '--black', 'random', '--max-plies', '3', '--stop-after', '1']), 3)
        path = os.path.join(self.tmp, tag, 'game.jsonl')
        start = {'type': 'call_started', 'side': 'w', 'ply': 3, 'call_id': 'pending'}
        records.write(path, start)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['resume', os.path.join(self.tmp, tag)]), 3)
            self.assertEqual(cli.main(['resume', os.path.join(self.tmp, tag), '--retry-idle-timeout']), 3)
            ctx = runner.load(C, os.path.join(self.tmp, tag))
            self.assertEqual({k: ctx['uncertain'][k] for k in start}, start)
            self.assertIsNone(runner.play(ctx))
        self.assertEqual(len(self.calls()), 1)

    def test_idle_timeout_explicit_resume_and_new_failure_lock(self):
        idle = {'error': 'agy: stream idle timeout (5m0s):context deadline exceeded'}
        self.plan([idle, idle, {'text': '着法: e2e4'}])
        tag = 'idle-retry'
        path = os.path.join(self.tmp, tag)
        self.assertEqual(self.play(['--game', 'chess', '--tag', tag, '--white',
                                    'agy:gemini-4-argon-high', '--black', 'random',
                                    '--max-plies', '1']), 3)
        before = self.recs(tag)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['resume', path]), 3)
            self.assertEqual(len(self.calls()), 1)
            self.assertEqual(cli.main(['resume', path, '--retry-idle-timeout']), 3)
            self.assertEqual(cli.main(['resume', path]), 3)
            self.assertEqual(len(self.calls()), 2)
            self.assertEqual(cli.main(['resume', path, '--retry-idle-timeout']), 0)
        after = self.recs(tag)
        self.assertEqual(after[:len(before)], before)
        retries = [r for r in after if r['type'] == 'retry_idle_timeout']
        self.assertEqual(len(retries), 2)
        for r in retries:
            self.assertEqual(after[r['failed_record']]['type'], 'call_fail')
            self.assertEqual(after[r['started_record']]['call_id'], r['call_id'])
            self.assertEqual(after[r['failed_record']]['call_id'], r['call_id'])
        self.assertNotEqual(retries[0]['call_id'], retries[1]['call_id'])
        self.assertIsNone(runner.load(C, path)['uncertain'])
        self.assertEqual(len(self.calls()), 3)

    def test_idle_retry_legacy_failure_and_exact_audit_scope(self):
        cfg = {'players': {'w': 'agy:gemini-4-argon-high'}}
        start = {'type': 'call_started', 'side': 'w', 'ply': 1, 'call_id': 'first'}
        fail = {'type': 'call_fail', 'side': 'w', 'ply': 1,
                'stderr': 'stream idle timeout (5m0s):context deadline exceeded'}
        recs = [start, fail]
        event = runner.idle_retry_event(runner.uncertain_records(recs, cfg))
        self.assertIsNotNone(event)  # 旧 call_fail 没有 call_id 仍可由唯一未完成调用关联。
        self.assertIsNone(runner.uncertain_record(recs + [event], cfg))
        for wrong in (dict(event, call_id='other'), dict(event, failed_record=3),
                      dict(event, side='b'), dict(event, ply=2)):
            self.assertIsNotNone(runner.uncertain_record(recs + [wrong], cfg))
        self.assertIsNotNone(runner.uncertain_record([event] + recs, cfg))
        newer = dict(start, call_id='second')
        self.assertIsNotNone(runner.uncertain_record(recs + [event, newer, fail, event], cfg))
        for invalid in ([start], [fail], [start, dict(start, call_id='another'), fail],
                        [start, dict(fail, side='b')], [start, dict(fail, call_id='other')],
                        [start, dict(fail, stderr='503 No capacity')],
                        [start, dict(fail, stderr=fail['stderr'] + ' [reasoning_extraction]')],
                        [start, dict(fail, stderr=fail['stderr'] +
                                     ' the model opened files that were not attached: /etc/hosts')]):
            self.assertIsNone(runner.idle_retry_event(runner.uncertain_records(invalid, cfg)))
        self.assertIsNone(runner.idle_retry_event(runner.uncertain_records(
            recs, {'players': {'w': 'claude:opus'}})))

    def test_idle_retry_cli_cannot_bypass_nonidle_tools_or_refusal(self):
        for n, failure in enumerate(({'error': '503 No capacity'},
                                     {'error': 'stream idle timeout (5m0s):context deadline exceeded; '
                                               'the model opened files that were not attached: /etc/hosts'},
                                     {'refuse': True})):
            self.plan([failure] * (n + 1))
            tag = 'idle-deny%d' % n
            self.assertEqual(self.play(['--game', 'chess', '--tag', tag, '--white',
                                        'agy:gemini-4-argon-high', '--black', 'random',
                                        '--max-plies', '1']), 3)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['resume', os.path.join(self.tmp, tag),
                                           '--retry-idle-timeout']), 3)
            self.assertEqual(len(self.calls()), n + 1)
            self.assertFalse(any(r['type'] == 'retry_idle_timeout' for r in self.recs(tag)))

    def test_gemini_xiangqi_selfplay_sessions(self):
        self.plan([{'text': '着法: h2e2'}, {'text': '着法: h7e7'},
                   {'text': '着法: i0i1'}, {'text': '着法: i9i8'}])
        spec = 'gemini:gemini-3.8-flash-high'
        self.assertEqual(self.play(['--game', 'xiangqi', '--tag', 'gemini', '--red', spec, '--black', spec,
                                    '--effort', 'high', '--max-plies', '4']), 0)
        recs, calls = self.recs('gemini'), self.calls()
        cfg = recs[0]['cfg']
        self.assertEqual(cfg['models'], dict.fromkeys('wb', 'gemini-3.8-flash-high'))
        self.assertEqual((cfg['protocol'], cfg['backend']), ('real', 'llm-chat'))
        atts = [r for r in recs if r['type'] == 'attempt']
        self.assertEqual(len(atts), 4)
        self.assertTrue(all(a['legal'] for a in atts))
        self.assertNotEqual(atts[0]['session'], atts[1]['session'])
        for n, call in enumerate(calls):
            argv = call['argv']
            self.assertEqual(argv[argv.index('-m') + 1], 'gemini-3.8-flash-high')
            self.assertEqual(argv[argv.index('--effort') + 1], 'high')
            if n < 2:
                self.assertIn('--system', argv)
            else:
                self.assertEqual(argv[argv.index('--session') + 1], atts[n - 2]['session'])

    def test_gemini_rejected_before_start(self):
        for extra in (['--protocol', 'legacy'], ['--w', 'drop_thinking=on']):
            with self.assertRaises(SystemExit):
                self.play(['--game', 'xiangqi', '--tag', 'bad-gemini',
                           '--red', 'gemini:gemini-3.8-flash-high', '--black', 'random'] + extra)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'calls.jsonl')))

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

    def test_refusal_on_first_turn_stops_and_locks_resume(self):
        self.plan([{'refuse': True}, {'text': '着法: e2e4'}])
        rc = self.play(['--game', 'chess', '--tag', 'r', '--black', 'random', '--max-plies', '3'])
        self.assertEqual(rc, 3)
        self.assertEqual(len(self.calls()), 1)
        recs = self.recs('r')
        refusal = next(r for r in recs if r['type'] == 'refusal')
        self.assertEqual((refusal['provider'], refusal['ply']), ('claude', 1))
        self.assertIn('safeguards flagged', refusal['evidence']['response']['result'])
        self.assertFalse(any(r['type'] in ('move', 'end', 'forfeit') for r in recs))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['resume', os.path.join(self.tmp, 'r')]), 3)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.recs('r'), recs)

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

    def test_provider_refusals_stop_without_call_retry(self):
        cases = [('agy:claude-opus-5-5-high', {'text': '[reasoning_extraction]'}),
                 ('gemini:gemini-3.8-flash-high', {'error': "Gemini’s safety filter blocked the answer"}),
                 ('codex:gpt-6-sol', {'text': "I cannot provide my private chain-of-thought."}),
                 ('deepseek:deepseek-v4-pro', {'text': '我无法提供内部思考过程。'}),
                 ('claude:opus', {'text': '[reasoning_extraction]'}),
                 ('codex:gpt-6-sol', {'error': "codex reported an error: unexpected codex item 'refusal'; plain chat allows no tools"})]
        for i, (player, reply) in enumerate(cases):
            with self.subTest(player=player):
                self.plan([reply] * (i + 1))
                with mock.patch.object(runner.claude_cli, '_wait') as wait:
                    rc = self.play(['--game', 'chess', '--tag', 'ref%d' % i, '--white', player,
                                    '--black', 'random', '--effort', 'high', '--max-plies', '1'])
                self.assertEqual(rc, 3)
                wait.assert_not_called()
                self.assertEqual(len(self.calls()), i + 1)
                rs = self.recs('ref%d' % i)
                self.assertEqual(rs[-1]['type'], 'refusal')
                self.assertFalse(any(r['type'] == 'call_fail' for r in rs))

    def test_text_metadata_refusal_is_not_an_empty_reply(self):
        self.plan([{'error': 'empty answer (finish_reason=content_filter); no text returned'},
                   {'text': '着法: e2e4'}])
        with mock.patch.object(runner.claude_cli, '_wait') as wait:
            rc = self.play(['--game', 'chess', '--tag', 'filter', '--white', 'deepseek:deepseek-v4-pro',
                            '--black', 'random', '--effort', 'high', '--max-plies', '1'])
        self.assertEqual(rc, 3)
        self.assertEqual(len(self.calls()), 1)
        wait.assert_not_called()
        self.assertIn('finish_reason=content_filter', self.recs('filter')[-1]['evidence']['response']['result'])

    def test_transcript_refusal_stops_even_with_valid_move(self):
        self.plan([{'text': '着法: e2e4'}])
        evidence = 'Your last response was flagged by our safeguards system.'
        with mock.patch.object(runner.claude_cli, 'transcript_flags_at', return_value=[evidence]):
            rc = self.play(['--game', 'chess', '--tag', 'tr', '--black', 'random', '--max-plies', '1'])
        self.assertEqual(rc, 3)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.recs('tr')[-1]['evidence']['transcript'], [evidence])
        self.assertFalse(any(r['type'] == 'move' for r in self.recs('tr')))

    def test_empty_reply_still_retries_without_changing_reason(self):
        self.plan([{'empty': True}, {'text': '思考后决定占中心，理由如下。\n着法: e2e4'}])
        rc = self.play(['--game', 'chess', '--tag', 'em', '--black', 'random', '--max-plies', '1'])
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.calls()), 2)
        self.assertNotIn('简短', self.calls()[1]['stdin'])
        self.assertFalse(any(r['type'] == 'refusal' for r in self.recs('em')))

    def test_capacity_error_still_retries(self):
        self.plan([{'error': '503 No capacity available'}, {'text': '着法: e2e4'}])
        with mock.patch.object(runner.claude_cli, '_wait', return_value=False) as wait:
            rc = self.play(['--game', 'chess', '--tag', 'cap', '--black', 'random', '--max-plies', '1'])
        self.assertEqual(rc, 0)
        wait.assert_called_once_with(30)
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual(sum(r['type'] == 'call_fail' for r in self.recs('cap')), 1)

    def test_gemini_failure_blocks_retry_and_resume(self):
        for n, failure in enumerate(({'error': '503 No capacity available'},
                                     {'error': 'rate limit exceeded'},
                                     {'error': 'unexpected tool view_file'}, {'empty': True})):
            with self.subTest(failure=failure):
                self.plan([failure] * (n + 1))
                before = n
                tag = 'uncertain%d' % n
                with mock.patch.object(runner.claude_cli, '_wait') as wait:
                    rc = self.play(['--game', 'chess', '--tag', tag, '--white',
                                    'gemini:gemini-3.8-flash-high', '--black', 'random', '--max-plies', '1'])
                self.assertEqual(rc, 3)
                wait.assert_not_called()
                self.assertEqual(len(self.calls()), before + 1)
                recs = self.recs(tag)
                self.assertFalse(any(r['type'] in ('move', 'forfeit', 'end') for r in recs))
                fail = next(r for r in recs if r['type'] == 'call_fail')
                self.assertEqual(fail['outcome'], 'uncertain')
                self.assertIsNone(fail['next_wait'])
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(['resume', os.path.join(self.tmp, tag)]), 3)
                    ctx = runner.load(C, os.path.join(self.tmp, tag))
                    self.assertIsNone(runner.play(ctx))
                self.assertEqual(len(self.calls()), before + 1)

    def test_gemini_timeout_and_malformed_metadata_do_not_retry(self):
        for model in ('gemini-3.8-flash-high', 'agy/claude-opus-5-5-high'):
            cmd = chat.command(model, 'high', system='sys')
            cases = [ValueError('wrapper parse failure'), OSError('wrapper failed'),
                     subprocess.TimeoutExpired(cmd, 1, output=b'partial reply', stderr=b'partial error'),
                     subprocess.CompletedProcess(cmd, 0, 'reply', 'LLM_CHAT_META {broken'),
                     subprocess.CompletedProcess(cmd, 0, 'reply', 'LLM_CHAT_META []'),
                     subprocess.CompletedProcess(cmd, 0, 'reply', ''),
                     subprocess.CompletedProcess(cmd, 0, '', 'LLM_CHAT_META {"session":"s"}')]
            for result in cases:
                with self.subTest(result=result):
                    fails = []
                    options = {'side_effect': result} if isinstance(result, Exception) else {'return_value': result}
                    with mock.patch.object(chat.subprocess, 'run', **options) as run, \
                            mock.patch.object(runner.claude_cli, '_wait') as wait:
                        with self.assertRaises(runner.Paused):
                            chat.call(cmd, 'prompt', on_fail=fails.append)
                    self.assertEqual(run.call_count, 1)
                    wait.assert_not_called()
                    self.assertEqual(fails[0]['outcome'], 'uncertain')


    def test_gemini_pending_and_old_fail_records_lock(self):
        for player in ('gemini:gemini-3.8-flash-high', 'agy:claude-opus-5-5-high'):
            cfg = {'players': {'w': player, 'b': 'random'}}
            start = {'type': 'call_started', 'side': 'w', 'ply': 1, 'call_id': 'unique'}
            attempt = {'type': 'attempt', 'side': 'w', 'ply': 1, 'call_id': 'unique', 'legal': True}
            move = {'type': 'move', 'side': 'w', 'ply': 1}
            self.assertEqual(runner.uncertain_record([start], cfg), start)
            self.assertEqual(runner.uncertain_record([start, attempt], cfg), start)
            self.assertIsNone(runner.uncertain_record([start, attempt, move], cfg))
            self.assertIsNone(runner.uncertain_record([start, dict(attempt, legal=False)], cfg))
            old = {'type': 'call_fail', 'side': 'w', 'ply': 1}
            self.assertEqual(runner.uncertain_record([old, move], cfg), old)


    def test_gemini_completed_turn_can_resume(self):
        self.plan([{'text': '着法: e2e4'}, {'text': '着法: d2d4'}])
        self.assertEqual(self.play(['--game', 'chess', '--tag', 'safe-resume', '--white',
                                    'gemini:gemini-3.8-flash-high', '--black', 'random',
                                    '--max-plies', '3', '--stop-after', '1']), 3)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['resume', os.path.join(self.tmp, 'safe-resume')]), 0)
        self.assertEqual(len(self.calls()), 2)

    def test_gemini_stop_before_dispatch_does_not_lock(self):
        cmd = chat.command('gemini-3.8-flash-high', 'high', system='sys')
        start = mock.Mock()
        runner.claude_cli.STOP.set()
        try:
            with mock.patch.object(chat.subprocess, 'run') as run:
                with self.assertRaises(runner.Paused):
                    chat.call(cmd, 'prompt', on_start=start)
            start.assert_not_called()
            run.assert_not_called()
        finally:
            runner.claude_cli.STOP.clear()

    def test_tool_errors_stop_all_providers_and_lock_resume(self):
        cases = [('agy:claude-opus-5-5-high', 'the model opened files that were not attached: /tmp/test'),
                 ('gemini:gemini-3.8-flash-high', 'agy soft-denied a tool and ended the turn (headless mode cannot ask): attempted: view_file /etc/hosts'),
                 ('gemini:gemini-3.8-flash-high', 'the model opened files that were not attached: /tmp/test'),
                 ('claude:opus', 'the model used server-side tools (web_search: 1); plain chat allows none'),
                 ('codex:gpt-6-sol', "unexpected codex item 'command_execution'; plain chat allows no tools"),
                 ('deepseek:deepseek-v4-pro', 'the model called a tool; plain chat allows none')]
        for i, (player, error) in enumerate(cases):
            with self.subTest(player=player, error=error):
                self.plan([{'error': error}] * (i + 1))
                tag = 'tool%d' % i
                with mock.patch.object(runner.claude_cli, '_wait') as wait:
                    rc = self.play(['--game', 'chess', '--tag', tag, '--white', player,
                                    '--black', 'random', '--effort', 'high', '--max-plies', '1'])
                self.assertEqual(rc, 3)
                wait.assert_not_called()
                self.assertEqual(len(self.calls()), i + 1)
                recs = self.recs(tag)
                self.assertFalse(any(r['type'] in ('refusal', 'call_fail', 'move', 'end', 'forfeit') for r in recs))
                flag = next(r for r in recs if r['type'] == 'flag')
                self.assertEqual(flag['source'], 'tool_call')
                self.assertIn(error, flag['evidence']['stderr'])
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(['resume', os.path.join(self.tmp, tag)]), 3)
                    self.assertIsNone(runner.play(runner.load(C, os.path.join(self.tmp, tag))))
                self.assertEqual(len(self.calls()), i + 1)

    def test_structured_tool_denial_overrides_successful_answer(self):
        self.plan([{'text': '着法: e2e4', 'extra_meta': {'denied_actions': ['read']}}])
        self.assertEqual(self.play(['--game', 'chess', '--tag', 'denied', '--black', 'random',
                                    '--max-plies', '1']), 3)
        recs = self.recs('denied')
        self.assertIsNotNone(runner.tool_record(recs))
        self.assertFalse(any(r['type'] in ('refusal', 'move', 'forfeit', 'end') for r in recs))

    def test_gemini_stop_after_success_can_resume_next_side(self):
        self.plan([{'text': '着法: e2e4'}, {'text': '着法: e7e5'}])
        original = chat.run
        def stopping_run(*args, **kwargs):
            result = original(*args, **kwargs)
            runner.claude_cli.STOP.set()
            return result
        spec = 'gemini:gemini-3.8-flash-high'
        with mock.patch.object(chat, 'run', side_effect=stopping_run):
            self.assertEqual(self.play(['--game', 'chess', '--tag', 'stop-safe', '--white', spec,
                                        '--black', spec, '--max-plies', '2']), 3)
        ctx = runner.load(C, os.path.join(self.tmp, 'stop-safe'))
        self.assertIsNone(ctx.get('uncertain'))
        self.assertEqual(sum(r['type'] == 'call_started' for r in self.recs('stop-safe')), 1)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['resume', os.path.join(self.tmp, 'stop-safe')]), 0)
        self.assertEqual(len(self.calls()), 2)

    def test_brief_format_by_stored_system(self):
        # 按存下的系统提示判：不修饰 / 详细换成简短、其余一字不差；本来简短、off、旧协议都不兜底
        for r in ('plain', 'detailed'):
            sys_ = '前文\n\n回答格式：' + memory.ANSWER_LEAD[r] + '用 UCI 坐标。\n\n后文'
            self.assertEqual(memory.brief_format(sys_), '回答格式：' + memory.ANSWER_LEAD['brief'] + '用 UCI 坐标。')
        for r in ('brief', 'off'):
            self.assertIsNone(memory.brief_format('回答格式：' + memory.ANSWER_LEAD[r] + '用 UCI 坐标。'))
        self.assertIsNone(memory.brief_format('回答格式：请用中文回答。可以先写简短的思路，最后一行只写「着法: 」加着法'))
        self.assertIsNone(memory.brief_format(None))


    def test_reason_default_plain_and_goes_into_pgn_comment(self):
        # 默认请棋手在着法前写理由（不修饰，不说简短 / 详细）；理由里提到别的着法（Nf3、d4）不影响读着法，落定那次的理由进该步评注
        self.plan([{'text': '也可以 Nf3，但我想先占中心，d4 留到下一步。\n\n着法: e2e4'},
                   {'text': '中心已经有兵了，再出马。\nMove: g1f3'}])
        rc = self.play(['--game', 'chess', '--tag', 'rs', '--black', 'random', '--max-plies', '3', '--seed', '2'])
        self.assertEqual(rc, 0)
        recs = self.recs('rs')
        cfg = recs[0]['cfg']
        self.assertEqual(cfg['sides']['w']['reason'], 'plain')
        self.assertEqual(cfg['sides']['w']['drop_thinking'], 'off')
        self.assertIn(memory.ANSWER_LEAD['plain'], cfg['system']['w'])
        self.assertIn('用你自己的话写出这步的理由', cfg['system']['w'])
        for word in ('简短', '详细'):
            self.assertNotIn(word, cfg['system']['w'])
        self.assertIn(memory.ANSWER_LEAD['plain'], self.calls()[0]['argv'][self.calls()[0]['argv'].index('--system') + 1])
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

    def test_reason_brief_still_selectable(self):
        # 之前的默认 brief「简短」保留可选：和 plain 只差「简短」两个字
        self.assertEqual(memory.ANSWER_LEAD['brief'], memory.ANSWER_LEAD['plain'].replace('写出', '简短写出'))
        self.plan([{'text': '先架中炮。\n着法: h2e2'}])
        self.play(['--game', 'xiangqi', '--tag', 'rb', '--black', 'random', '--max-plies', '2', '--reason', 'brief'])
        cfg = self.recs('rb')[0]['cfg']
        self.assertEqual(cfg['sides']['w']['reason'], 'brief')
        self.assertIn(memory.ANSWER_LEAD['brief'], cfg['system']['w'])

    def test_resume_keeps_prompt_stored_at_start(self):
        # 已开局的记录续跑照开局时存下的系统提示，不按现在的措辞重拼：黑方的会话在续跑后才开，把 brief 的措辞临时换掉，
        # 发出去的仍是开局时那句
        self.plan([{'text': '着法: e7e5'}])
        rc = self.play(['--game', 'chess', '--tag', 'rk', '--white', 'random', '--black', 'claude:opus', '--max-plies', '2',
                        '--seed', '5', '--b', 'reason=brief', '--stop-after', '1'])
        self.assertEqual(rc, 3)
        stored = self.recs('rk')[0]['cfg']['system']['b']
        old = memory.ANSWER_LEAD['brief']
        self.assertIn(old, stored)
        with mock.patch.dict(memory.ANSWER_LEAD, brief='（改过的措辞）'), \
                contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(['resume', os.path.join(self.tmp, 'rk')])
        self.assertEqual(rc, 0)
        argv = self.calls()[0]['argv']
        self.assertEqual(argv[argv.index('--system') + 1], stored)

    # ------------------------------------------------------------------ 去掉此前思考（drop_thinking）
    def test_drop_thinking_per_side_flag_first_turn_and_warn(self):
        # 白方开：只在会话首轮传 --drop-thinking，理由默认仍是不修饰（详细已弃用）；每次调用记 thinking_dropped，续接轮为 0 告警不中断
        self.plan([{'text': '着法: e2e4', 'dropped': 0}, {'text': '着法: g1f3', 'dropped': 1},
                   {'text': '着法: f1c4', 'dropped': 0}])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = cli.main(['play', '--out', self.tmp, '--game', 'chess', '--tag', 'dt', '--black', 'random',
                           '--max-plies', '5', '--seed', '3', '--w', 'drop_thinking=on'])
        self.assertEqual(rc, 0)
        recs = self.recs('dt')
        cfg = recs[0]['cfg']
        self.assertEqual((cfg['sides']['w']['drop_thinking'], cfg['sides']['w']['reason']), ('on', 'plain'))
        self.assertEqual((cfg['sides']['b']['drop_thinking'], cfg['sides']['b']['reason']), ('off', 'plain'))
        self.assertIn(memory.ANSWER_LEAD['plain'], cfg['system']['w'])
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
        # 显式给 reason 就照给的（弃用的 detailed 也照给）；暂停后续跑接同一会话，不再传 --drop-thinking，续接轮照样查 thinking_dropped
        self.plan([{'text': '着法: e2e4', 'dropped': 0}, {'text': '着法: g1f3', 'dropped': 0}])
        rc = self.play(['--game', 'chess', '--tag', 'dr', '--black', 'random', '--max-plies', '3', '--seed', '3',
                        '--drop-thinking', 'on', '--black', 'random', '--w', 'reason=detailed', '--stop-after', '2'])
        self.assertEqual(rc, 3)
        cfg = self.recs('dr')[0]['cfg']
        self.assertEqual((cfg['sides']['w']['drop_thinking'], cfg['sides']['w']['reason']), ('on', 'detailed'))
        self.assertIn(memory.ANSWER_LEAD['detailed'], cfg['system']['w'])
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
        # 对手是引擎 / 随机时公共开关不碍事（它们不看这一项）；开了去掉思考，dry-run 里理由仍是不修饰
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.main(['play', '--game', 'chess', '--black', 'random', '--drop-thinking', 'on', '--dry-run'])
        self.assertIn(memory.ANSWER_LEAD['plain'], out.getvalue())
        self.assertNotIn(memory.ANSWER_LEAD['detailed'], out.getvalue())


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
        self.assertIn(memory.ANSWER_LEAD['plain'], w)
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
        for r in ('plain', 'brief', 'detailed'):
            self.assertNotIn(memory.ANSWER_LEAD[r], s)

    def test_real_rejects_legal_list(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(io.StringIO()):
                cli.main(['play', '--game', 'chess', '--legal', 'list', '--dry-run'])

    def test_repo_bundled_llm_chat_and_agy_core(self):
        import importlib.util
        self.assertTrue(chat._REPO_SCRIPT.is_file())
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('LLMCHESS_LLM_CHAT', None)
            self.assertEqual(chat._default_script(), str(chat._REPO_SCRIPT))
            with mock.patch.object(chat, '_REPO_SCRIPT', chat._REPO_SCRIPT.parent / 'missing.py'):
                self.assertEqual(chat._default_script(), str(chat._USER_SCRIPT))
        with mock.patch.dict(os.environ, {'LLMCHESS_LLM_CHAT': '/custom/llm_chat.py'}):
            self.assertEqual(chat._default_script(), '/custom/llm_chat.py')
        spec = importlib.util.spec_from_file_location('repo_llm_chat', chat._REPO_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.AGY_CORE_DIR, chat._REPO_SCRIPT.parent)
        with mock.patch.object(sys, 'path', list(sys.path)), mock.patch.dict(sys.modules):
            sys.modules.pop('agy_core', None)
            core = mod.agy_core()
            self.assertEqual(os.path.realpath(core.__file__), os.path.realpath(str(chat._REPO_SCRIPT.parent / 'agy_core.py')))

    def test_llm_chat_deepseek_openrouter_fallback_and_env_aliases(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('repo_llm_chat', chat._REPO_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        class FakeIn(io.StringIO):
            def isatty(self):
                return False

        with tempfile.TemporaryDirectory(prefix='llm-chat-fallback-') as tmp:
            # 1) DeepSeek key present (via DEEPSEEK_API_KEY alias) -> official DeepSeek API
            with mock.patch.dict(os.environ, {'XDG_STATE_HOME': tmp, 'DEEPSEEK_API_KEY': 'ds-secret-12345678'}, clear=True):
                self.assertEqual(mod.route('deepseek-flash'), ('deepseek', 'deepseek-flash'))
                self.assertEqual(mod.route('deepseek-v4-pro'), ('deepseek', 'deepseek-v4-pro'))
                self.assertEqual(mod.route('deepseek'), ('deepseek', 'deepseek-v4-pro'))
                self.assertEqual(mod.api_key('deepseek'), 'ds-secret-12345678')

            # 2) No DeepSeek key, OPENROUTER_API_KEY set -> auto-fallback to OpenRouter
            with mock.patch.dict(os.environ, {'XDG_STATE_HOME': tmp, 'OPENROUTER_API_KEY': 'or-secret-12345678'}, clear=True):
                self.assertEqual(mod.route('deepseek'), ('openrouter', 'deepseek/deepseek-v4-pro'))
                self.assertEqual(mod.route('deepseek-v4-pro'), ('openrouter', 'deepseek/deepseek-v4-pro'))
                self.assertEqual(mod.route('deepseek-reasoner'), ('openrouter', 'deepseek/deepseek-v4-pro'))
                self.assertEqual(mod.route('deepseek-flash'), ('openrouter', 'deepseek/deepseek-v4.1-flash'))
                self.assertEqual(mod.route('deepseek-chat'), ('openrouter', 'deepseek/deepseek-v4.1-flash'))
                calls = []

                def fake_http(url, key, body=None, timeout=None):
                    calls.append((url, key, body))
                    return {'model': body['model'], 'provider': 'Wafer',
                            'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'OK'}}],
                            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'cost': 0.0001,
                                      'prompt_tokens_details': {'cached_tokens': 0, 'cache_write_tokens': 0},
                                      'completion_tokens_details': {'reasoning_tokens': 3}}}

                with mock.patch.object(mod, 'http_request', side_effect=fake_http):
                    out, err = io.StringIO(), io.StringIO()
                    rc = mod.main(['-m', 'deepseek-flash', '--effort', 'low', '--system', 'sys'], FakeIn('hi'), out, err)
                    self.assertEqual((rc, out.getvalue()), (0, 'OK\n'))
                    meta = json.loads(err.getvalue().strip().splitlines()[-1][len(mod.META_PREFIX):])
                    self.assertEqual(meta['model'], 'deepseek/deepseek-v4.1-flash')
                    self.assertEqual(calls[0][0], mod.OPENROUTER_CHAT_URL)
                    self.assertEqual(calls[0][1], 'or-secret-12345678')
                    out2, err2 = io.StringIO(), io.StringIO()
                    rc2 = mod.main(['-m', 'deepseek-flash', '--effort', 'low', '--session', meta['session']], FakeIn('next'), out2, err2)
                    self.assertEqual((rc2, out2.getvalue()), (0, 'OK\n'))

            # 3) Neither DeepSeek key nor OpenRouter key set -> clear error mentioning both
            with mock.patch.dict(os.environ, {'XDG_STATE_HOME': tmp}, clear=True):
                out, err = io.StringIO(), io.StringIO()
                rc = mod.main(['-m', 'deepseek-flash', '--system', 'sys'], FakeIn('hi'), out, err)
                self.assertEqual(rc, 1)
                self.assertIn('missing API key: set API_KEY_DEEPSEEK (or API_KEY_OPENROUTER to route DeepSeek via OpenRouter)',
                              err.getvalue())

    def test_missing_local_clis_report_clean_error(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('repo_llm_chat', chat._REPO_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        class FakeIn(io.StringIO):
            def isatty(self):
                return False

        with tempfile.TemporaryDirectory(prefix='llm-chat-nocli-') as tmp:
            with mock.patch.dict(os.environ, {'XDG_STATE_HOME': tmp, 'HOME': tmp, 'PATH': tmp}, clear=True), \
                    mock.patch.object(sys, 'path', list(sys.path)), mock.patch.dict(sys.modules):
                sys.modules.pop('agy_core', None)
                for model, cli_name in (('opus', 'claude'), ('gpt-6-sol', 'codex'), ('gemini-3.8-flash-low', 'agy')):
                    out, err = io.StringIO(), io.StringIO()
                    rc = mod.main(['-m', model, '--system', 'sys'], FakeIn('hi'), out, err)
                    self.assertEqual(rc, 1)
                    self.assertIn(f'{cli_name} CLI not found in PATH', err.getvalue())
                    self.assertNotIn('Traceback', err.getvalue())
        with mock.patch.object(chat.subprocess, 'run', side_effect=FileNotFoundError('codex')):
            with self.assertRaises(SystemExit) as ctx:
                chat.model_id('codex', 'sol')
            self.assertIn('codex CLI not found in PATH', str(ctx.exception))



if __name__ == '__main__':
    unittest.main()
