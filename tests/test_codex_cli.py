"""离线测试：codex exec 棋手（codex_cli.py）——拼命令、事件流解析、用量换算、profile 读取、模型目录补丁，
以及经 claude_cli.call / quiz.answer_one 的整条通路。

绝不调 codex 本体：subprocess.run 和模型目录都打桩；文件写进 tempfile.mkdtemp() 的独立目录，跑完删掉。
"""
import contextlib, io, json, os, shutil, subprocess, tempfile, threading, unittest
from unittest import mock

import chess

from llmchess import claude_cli, codex_cli as X, quiz as Q, records, runner


def events(text='着法: e2e4', usage=None, extra=()):
    u = usage or {'input_tokens': 7669, 'cached_input_tokens': 1000, 'cache_write_input_tokens': 5,
                  'output_tokens': 74, 'reasoning_output_tokens': 38}
    ev = [{'type': 'thread.started', 'thread_id': 'th-1'}, {'type': 'turn.started'}, *extra,
          {'type': 'item.completed', 'item': {'id': 'item_0', 'type': 'agent_message', 'text': text}},
          {'type': 'turn.completed', 'usage': u}]
    return '\n'.join(json.dumps(e, ensure_ascii=False) for e in ev) + '\n'


FAILED = '\n'.join(json.dumps(e) for e in (
    {'type': 'thread.started', 'thread_id': 'th-2'}, {'type': 'turn.started'},
    {'type': 'error', 'message': 'stream disconnected'},
    {'type': 'turn.failed', 'error': {'message': 'stream disconnected'}})) + '\n'

CATALOG = [{'slug': 'gpt-6-sol', 'shell_type': 'unified_exec', 'tool_mode': 'code_mode_only', 'multi_agent_version': 'v2',
            'experimental_supported_tools': ['send_user_message_async', 'clock'], 'apply_patch_tool_type': 'freeform',
            'supported_reasoning_levels': [{'effort': e} for e in ('low', 'medium', 'high', 'xhigh', 'max')],
            'context_window': 272000},
           {'slug': 'deepseek-v4-pro', 'shell_type': 'shell_command', 'tool_mode': None, 'multi_agent_version': 'v2',
            'experimental_supported_tools': [], 'apply_patch_tool_type': 'freeform',
            'supported_reasoning_levels': [{'effort': e} for e in ('low', 'high', 'max')]}]

PROFILE = '''model = "deepseek-v4-pro"
model_provider = "deepseek"
model_reasoning_effort = "high"
model_catalog_json = "~/.codex/deepseek-models.json"

[model_providers.deepseek]
name = "DeepSeek"
base_url = "https://api.deepseek.com"
wire_api = "responses"
env_key = "API_KEY_DEEPSEEK"
requires_openai_auth = false
'''
PROF = {'model': 'deepseek-v4-pro', 'provider': 'deepseek', 'catalog': '/nonexistent/catalog.json',
        'provider_table': {'name': 'DeepSeek', 'base_url': 'https://api.deepseek.com', 'wire_api': 'responses',
                           'env_key': 'API_KEY_DEEPSEEK', 'requires_openai_auth': False}}


def opts(cmd):
    """命令里全部 -c 的值。"""
    return [cmd[i + 1] for i, x in enumerate(cmd) if x == '-c']


class Parse(unittest.TestCase):
    def test_success(self):
        d = X.parse(events('想了想\n着法: e2e4'))
        self.assertEqual(d['result'], '想了想\n着法: e2e4')
        self.assertFalse(d['is_error'])
        self.assertEqual(d['thread_id'], 'th-1')
        self.assertEqual(d['items'], ['agent_message'])

    def test_reasoning_item_allowed_last_message_wins(self):
        extra = [{'type': 'item.completed', 'item': {'type': 'reasoning', 'text': '...'}},
                 {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '先说一句'}}]
        d = X.parse(events('着法: d2d4', extra=extra))
        self.assertEqual(d['result'], '着法: d2d4')
        self.assertEqual(d['items'], ['reasoning', 'agent_message', 'agent_message'])

    def test_tool_item_raises(self):
        for t in ('command_execution', 'file_change', 'mcp_tool_call', 'web_search', 'collab_tool_call'):
            for phase in ('item.started', 'item.completed'):
                extra = [{'type': phase, 'item': {'type': t, 'command': 'stockfish'}}]
                with self.assertRaises(X.ToolUsed, msg=(t, phase)):
                    X.parse(events(extra=extra))

    def test_failed_turn_is_error(self):
        d = X.parse(FAILED)
        self.assertTrue(d['is_error'])
        self.assertEqual(d['result'], 'stream disconnected')

    def test_reconnect_notice_is_not_error(self):
        # DeepSeek 实录：流被 max_output_tokens 截断，codex 自己重连后照常答完
        note = 'Reconnecting... 1/5 (stream disconnected before completion: Incomplete response returned, ' \
               'reason: max_output_tokens)'
        d = X.parse(events('着法: d3f4', extra=[{'type': 'error', 'message': note}]))
        self.assertFalse(d['is_error'])
        self.assertEqual(d['result'], '着法: d3f4')
        self.assertEqual(d['reconnects'], [note])
        self.assertEqual(d['errors'], [])

    def test_reconnect_then_failed_is_error(self):
        ev = [{'type': 'thread.started', 'thread_id': 'th-3'}, {'type': 'turn.started'}]
        ev += [{'type': 'error', 'message': 'Reconnecting... %d/5 (stream disconnected)' % i} for i in range(1, 6)]
        ev += [{'type': 'turn.failed', 'error': {'message': 'stream disconnected'}}]
        d = X.parse('\n'.join(json.dumps(e) for e in ev))
        self.assertTrue(d['is_error'])
        self.assertEqual(len(d['reconnects']), 5)
        # 重连提示之后断流、没有 turn.completed：也算失败
        self.assertTrue(X.parse('\n'.join(json.dumps(e) for e in ev[:3]))['is_error'])

    def test_empty_or_truncated(self):
        self.assertIsNone(X.parse(''))
        self.assertIsNone(X.parse('Reading additional input from stdin...\n'))
        cut = events().splitlines()[:3]          # 没有 turn.completed
        self.assertTrue(X.parse('\n'.join(cut))['is_error'])


class Usage(unittest.TestCase):
    def test_maps_to_claude_fields(self):
        u = X.usage(X.parse(events()), 'gpt-6-sol')
        self.assertEqual((u['in'], u['cache_read'], u['cache_write']), (6669, 1000, 5))
        self.assertEqual((u['out'], u['think'], u['text_out']), (74, 38, 36))
        self.assertEqual(u['cost'], 0)
        self.assertEqual(u['session_id'], 'th-1')
        self.assertEqual(u['model'], 'gpt-6-sol')
        self.assertEqual(set(records.SUM_KEYS) - set(u), set())

    def test_missing_usage(self):
        u = X.usage({'is_error': True})
        self.assertEqual((u['in'], u['out'], u['think']), (0, 0, 0))
        self.assertEqual(u['stop_reason'], 'error')


class Profile(unittest.TestCase):
    def test_parse_real_shape(self):
        p = X.parse_profile(PROFILE)
        self.assertEqual(p['model'], 'deepseek-v4-pro')
        self.assertIs(p['model_providers.deepseek']['requires_openai_auth'], False)

    def test_unknown_syntax_raises(self):
        for bad in ('x = [1, 2]', 'what', 'x = 1.5'):
            with self.assertRaises(ValueError, msg=bad):
                X.parse_profile(bad)

    def test_profile_file(self):
        tmp = tempfile.mkdtemp(prefix='llmchess-codex-test-')
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, 'deepseek.config.toml')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(PROFILE)
        p = X.profile(path)
        self.assertEqual((p['model'], p['provider']), ('deepseek-v4-pro', 'deepseek'))
        self.assertEqual(p['catalog'], os.path.expanduser('~/.codex/deepseek-models.json'))
        self.assertEqual(X.inline_table(p['provider_table']),
                         '{name="DeepSeek",base_url="https://api.deepseek.com",wire_api="responses",'
                         'env_key="API_KEY_DEEPSEEK",requires_openai_auth=false}')

    def test_spec_of(self):
        self.assertEqual(X.spec_of('opus'), 'claude:opus')
        self.assertEqual(X.spec_of('sol'), 'codex:gpt-6-sol')
        self.assertEqual(X.spec_of('codex:gpt-6-luna'), 'codex:gpt-6-luna')
        self.assertEqual(X.spec_of('deepseek:deepseek-v4-flash'), 'deepseek:deepseek-v4-flash')
        with mock.patch.object(X, 'profile', lambda: PROF):
            self.assertEqual(X.spec_of('deepseek'), 'deepseek:deepseek-v4-pro')


class Command(unittest.TestCase):
    def test_codex_isolation_flags(self):
        cmd = X.command('codex', 'gpt-6-sol', 'high', '/s/sys.md', '/s/cat.json', '/w/cwd')
        self.assertEqual(cmd[:2], ['codex', 'exec'])
        for flag in ('--ignore-user-config', '--ignore-rules', '--ephemeral', '--skip-git-repo-check', '--json'):
            self.assertIn(flag, cmd)
        self.assertNotIn('-p', cmd)
        self.assertNotIn('--profile', cmd)
        self.assertEqual(cmd[cmd.index('-s') + 1], 'read-only')
        self.assertEqual(cmd[cmd.index('-C') + 1], '/w/cwd')
        self.assertEqual(cmd[cmd.index('-m') + 1], 'gpt-6-sol')
        o = opts(cmd)
        self.assertIn('model_reasoning_effort="high"', o)
        self.assertIn('model_catalog_json="/s/cat.json"', o)
        self.assertIn('model_instructions_file="/s/sys.md"', o)
        for f in X.DISABLED_FEATURES:
            self.assertIn('features.%s=false' % f, o)
        for x in X.OFF:
            self.assertIn(x, o)
        self.assertFalse([x for x in o if x.startswith('model_provider')])      # sol 走默认供应商（ChatGPT 登录）

    def test_deepseek_provider_from_profile(self):
        cmd = X.command('deepseek', 'deepseek-v4-pro', 'high', '/s/sys.md', '/s/cat.json', '/w/cwd', PROF)
        o = opts(cmd)
        self.assertIn('model_provider="deepseek"', o)
        self.assertIn('model_providers.deepseek=' + X.inline_table(PROF['provider_table']), o)
        self.assertEqual(cmd[cmd.index('-m') + 1], 'deepseek-v4-pro')
        self.assertIn('--ignore-user-config', cmd)

    def test_shown_has_no_paths(self):
        s = X.shown('codex', 'gpt-6-sol', 'high')
        self.assertIn('<系统提示文件>', s)
        self.assertTrue(s.endswith('<用户提示>'))


class Prepare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-codex-test-')
        self.addCleanup(shutil.rmtree, self.tmp)
        self.cwd = os.path.join(self.tmp, 'cwd')
        os.makedirs(self.cwd)
        X._CATALOG.clear()
        self.addCleanup(X._CATALOG.clear)

    def test_patch_model(self):
        m = X.patch_model(CATALOG, 'gpt-6-sol')
        for k, v in X.NO_TOOLS.items():
            self.assertEqual(m[k], v)
        self.assertEqual(m['context_window'], 272000)            # 其余原样
        self.assertEqual(CATALOG[0]['shell_type'], 'unified_exec')  # 不改原表
        with self.assertRaises(SystemExit):
            X.patch_model(CATALOG, 'no-such')

    def test_write_once_threads_same_path(self):
        # quiz --jobs>1 时同进程多个线程同时写同一个按内容哈希命名的文件：等所有线程都写完临时文件再一起改名，
        # 临时文件名若撞了，后改名的会找不到源文件（FileNotFoundError）
        n, path, text = 6, X.pathlib.Path(self.tmp) / 'system-x.md', '系统提示' * 100
        gate, real, errs = threading.Barrier(n, timeout=10), os.replace, []

        def replace(src, dst):
            gate.wait()
            real(src, dst)

        def work():
            try:
                X._write_once(path, text)
            except Exception as e:
                errs.append(e)
        with mock.patch.object(X.os, 'replace', replace):
            ts = [threading.Thread(target=work) for _ in range(n)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
        self.assertEqual(errs, [])
        self.assertEqual(path.read_text(encoding='utf-8'), text)
        self.assertEqual(sorted(os.listdir(self.tmp)), ['cwd', 'system-x.md'])  # 不留临时文件

    def test_files_beside_cwd_and_effort_checked(self):
        with mock.patch.object(X, 'catalog_models', lambda kind, prof=None: CATALOG):
            sp, cp = X.prepare('deepseek', 'deepseek-v4-pro', 'high', '系统提示', self.cwd, PROF)
            self.assertEqual(os.listdir(self.cwd), [])             # 运行目录保持空
            self.assertEqual(os.path.dirname(sp), self.cwd + '.codex')
            with open(sp, encoding='utf-8') as f:
                self.assertEqual(f.read(), '系统提示')
            with open(cp, encoding='utf-8') as f:
                cat = json.load(f)
            self.assertEqual([m['slug'] for m in cat['models']], ['deepseek-v4-pro'])
            self.assertEqual(cat['models'][0]['shell_type'], 'disabled')
            self.assertEqual(X.prepare('deepseek', 'deepseek-v4-pro', 'high', '系统提示', self.cwd, PROF), (sp, cp))
            with self.assertRaises(SystemExit):
                X.prepare('deepseek', 'deepseek-v4-pro', 'xhigh', '系统提示', self.cwd, PROF)
        self.addCleanup(shutil.rmtree, self.cwd + '.codex', ignore_errors=True)


class CallThroughClaudeCli(unittest.TestCase):
    """claude_cli.call 借给 codex：解析换成 codex_cli.parse，重试 / 调不通照旧。"""

    def run_seq(self, outs):
        it = iter(outs)
        seen = []

        def run(cmd, **k):
            seen.append(cmd)
            return next(it)
        with mock.patch.object(claude_cli.subprocess, 'run', run), mock.patch.object(claude_cli, '_wait', lambda s: False), \
                mock.patch('builtins.print'):
            return claude_cli.call(['codex', 'exec'], 'P', '/tmp', waits=(1,), parse=X.parse), seen

    def test_failed_turn_retried_then_success(self):
        (d, _), seen = self.run_seq([subprocess.CompletedProcess([], 1, stdout=FAILED, stderr=''),
                                     subprocess.CompletedProcess([], 0, stdout=events(), stderr='')])
        self.assertEqual(d['result'], '着法: e2e4')
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0][-1], 'P')

    def test_reconnect_notice_not_retried(self):
        out = events('着法: e2e4', extra=[{'type': 'error', 'message': 'Reconnecting... 1/5 (x)'}])
        (d, _), seen = self.run_seq([subprocess.CompletedProcess([], 0, stdout=out,
                                                                 stderr='Reading additional input from stdin...\n')])
        self.assertEqual(d['result'], '着法: e2e4')
        self.assertEqual(len(seen), 1)

    def test_tool_use_propagates(self):
        bad = events(extra=[{'type': 'item.started', 'item': {'type': 'command_execution', 'command': 'ls'}}])
        with self.assertRaises(X.ToolUsed):
            self.run_seq([subprocess.CompletedProcess([], 0, stdout=bad, stderr='')])


class QuizPath(unittest.TestCase):
    """quiz.answer_one 用 sol / deepseek 作答：命令是 codex exec、用量落进记录；session 档直接拒绝。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llmchess-codex-quiz-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cwd = os.path.join(self.tmp, 'cwd')
        os.makedirs(self.cwd)
        X._CATALOG.clear()
        self.addCleanup(X._CATALOG.clear)
        for name, val in (('catalog_models', lambda kind, prof=None: CATALOG), ('profile', lambda path=None: PROF)):
            p = mock.patch.object(X, name, val)
            p.start()
            self.addCleanup(p.stop)

    def answer(self, model, reply_of):
        p = Q.load_positions(Q.positions_path('batch1', 'chess'))[0]
        seen = []

        def run(cmd, **k):
            seen.append(cmd)
            prompt = cmd[-1]
            b = chess.Board(' '.join(prompt.split('FEN：')[1].split()[0:6]))
            return subprocess.CompletedProcess([], 0, stdout=reply_of(b), stderr='')
        with mock.patch.object(claude_cli.subprocess, 'run', run), contextlib.redirect_stdout(io.StringIO()):
            res = Q.answer_one(p, 'high', 1, self.tmp, model, self.cwd, {'commit': 'test'})
        return p, res, seen

    def test_sol_and_deepseek(self):
        for model, kind in (('sol', 'codex'), ('deepseek', 'deepseek')):
            p, res, seen = self.answer(model, lambda b: events('着法: %s' % next(iter(b.legal_moves)).uci()))
            self.assertIsNotNone(res['move'], model)
            self.assertEqual(seen[0][:2], ['codex', 'exec'])
            self.assertIn('--ephemeral', seen[0])
            recs = records.read(Q.answer_path(self.tmp, p['id'], 'high', 1))
            cfg = recs[0]['cfg']
            self.assertEqual(cfg['players'][res['side']].split(':')[0], kind)
            self.assertTrue(cfg['commands'][res['side']].startswith('codex exec'))
            att = [r for r in recs if r['type'] == 'attempt']
            self.assertEqual(att[0]['usage']['think'], 38)
            self.assertEqual(res['stat']['out'], 74)
            os.remove(Q.answer_path(self.tmp, p['id'], 'high', 1))

    def test_unparsed_text_counts_as_illegal(self):
        # DeepSeek 没有工具时会把「工具调用」写成正文（隔离对照里见过）：解析不出着法，按非法重试，不会被执行
        dsml = '<｜｜DSML｜｜tool_calls><｜｜DSML｜｜invoke name="bash">cat x</｜｜DSML｜｜invoke></｜｜DSML｜｜tool_calls>'
        replies = iter([dsml])
        p, res, seen = self.answer('deepseek', lambda b: events(next(replies, '着法: %s' % next(iter(b.legal_moves)).uci())))
        self.assertEqual(res['stat']['illegal'], 1)
        self.assertEqual(len(seen), 2)
        self.assertIsNotNone(res['move'])

    def test_session_rejected(self):
        G = Q.game_module('chess')
        p = Q.load_positions(Q.positions_path('batch1', 'chess'))[0]
        st = Q.build_state(p)
        side = G.turn(st)
        cfg = Q.quiz_cfg(G, 'chess', side, 'high', 'sol', self.cwd)
        cfg['sides'][side]['memory'] = 'session'
        ctx = runner.new_ctx(G, cfg, self.tmp)
        ctx['st'], ctx['log'] = st, os.path.join(self.tmp, 'x.jsonl')
        with self.assertRaises(SystemExit):
            runner.model_turn(ctx, side, G.legal(st), {})


if __name__ == '__main__':
    unittest.main()
