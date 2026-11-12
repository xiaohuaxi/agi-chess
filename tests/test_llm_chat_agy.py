"""仓内 llm-chat 的 agy 路径：失败的结构化分类（LLM_CHAT_ERROR）、--accept-recovered 取回中断后已生成的答复、
--sessions-dir 把会话记录放到指定目录。全部用伪造的 agy 输出，不起 agy、不调模型；每个用例在自己的临时目录里跑。"""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from agi_chess import chat


def load_llm_chat():
    spec = importlib.util.spec_from_file_location('repo_llm_chat_agy_test', chat._REPO_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def stream(status='SUCCESS', response='着法: e2e4', error=None, deltas=(), tools=(), conversation='conv-1'):
    lines = [{'event': 'init', 'conversation_id': conversation, 'init': {'model': 'gemini-4-carbon'}}]
    for n, text in enumerate(deltas):
        lines.append({'event': 'step_update', 'step_update': {'step_index': n, 'step_type': 'agent_response',
                                                              'text_delta': text, 'state': 'DONE'}})
    for n, name in enumerate(tools, 100):
        lines.append({'event': 'step_update', 'step_update': {'step_index': n, 'step_type': 'tool',
                                                              'tool_name': name, 'state': 'DONE'}})
    result = {'status': status, 'response': response, 'conversation_id': conversation, 'usage': {}}
    if error:
        result['error'] = error
    lines.append({'event': 'result', 'result': result})
    return '\n'.join(json.dumps(x, ensure_ascii=False) for x in lines) + '\n'


INTERRUPTED = 'The stream was interrupted. Please continue the task you were working on.'


class FakeIn(io.StringIO):
    def isatty(self):
        return False


class AgyCoreChecks(unittest.TestCase):
    def setUp(self):
        mod = load_llm_chat()
        for p in (mock.patch.object(sys, 'path', list(sys.path)), mock.patch.dict(sys.modules)):
            p.start()
            self.addCleanup(p.stop)
        sys.modules.pop('agy_core', None)
        self.core = mod.agy_core()

    def check(self, *args, **kw):
        return self.core.check_turn(*args, allowed_tools=('view_file',), **kw)

    def test_sources_name_the_failed_check(self):
        cases = ((0, stream('ERROR', '', INTERRUPTED), '', 'status'),
                 (1, '', 'boom', 'exit'), (3, '', 'AGY_ERROR: {"code": 503}', 'exit'),
                 (0, '', '', 'no_result'),
                 (0, stream(response=''), '', 'empty'),
                 (0, stream(tools=('run_command',)), '', 'tool'),
                 (0, stream(), 'print timeout after 600s with turn in progress', 'print_timeout'))
        for code, out, err, source in cases:
            with self.subTest(source=source):
                with self.assertRaises(self.core.AgyError) as ctx:
                    self.check(code, out, err)
                self.assertEqual(ctx.exception.source, source)
        self.assertEqual(self.check(0, stream(), '')[1], '着法: e2e4')

    def test_recovered_answer_only_with_flag_and_all_checks(self):
        out = stream('ERROR', '理由\n着法: e2e4', INTERRUPTED)
        with self.assertRaises(self.core.AgyError) as ctx:
            self.check(0, out, '')
        self.assertEqual(ctx.exception.source, 'status')
        info, response = self.check(0, out, '', accept_recovered=True)
        self.assertEqual(response, '理由\n着法: e2e4')
        self.assertEqual(info['recovered']['status'], 'ERROR')
        self.assertIn('interrupted', info['recovered']['error'])
        # 流里本进程收到的答复正文与结果一致才认
        self.assertEqual(self.check(0, stream('ERROR', '着法: e2e4', INTERRUPTED, deltas=('着法: ', 'e2e4')), '',
                                    accept_recovered=True)[1], '着法: e2e4')
        for bad, source in ((stream('ERROR', '着法: e2e4', INTERRUPTED, deltas=('着法: d2d4',)), 'status'),
                            (stream('ERROR', '', INTERRUPTED), 'status'),
                            (stream('ERROR', '着法: e2e4', INTERRUPTED, tools=('run_command',)), 'tool')):
            with self.subTest(source=source):
                with self.assertRaises(self.core.AgyError) as ctx:
                    self.check(0, bad, '', accept_recovered=True)
                self.assertEqual(ctx.exception.source, source)
        with self.assertRaises(self.core.AgyError) as ctx:     # 非零退出不走取回
            self.check(1, out, 'x', accept_recovered=True)
        self.assertEqual(ctx.exception.source, 'exit')


class LlmChatAgyMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='llm-chat-agy-')
        self.addCleanup(__import__('shutil').rmtree, self.tmp, ignore_errors=True)
        self.mod = load_llm_chat()
        for p in (mock.patch.dict(os.environ, {'XDG_STATE_HOME': os.path.join(self.tmp, 'state')}),
                  mock.patch.object(sys, 'path', list(sys.path)), mock.patch.dict(sys.modules)):
            p.start()
            self.addCleanup(p.stop)
        sys.modules.pop('agy_core', None)
        self.core = self.mod.agy_core()
        self.outputs = []
        run = mock.patch.object(self.core, 'run_agy', side_effect=lambda *a, **k: self.outputs.pop(0))
        run.start()
        self.addCleanup(run.stop)

    def main(self, argv, text='hi'):
        out, err = io.StringIO(), io.StringIO()
        rc = self.mod.main(['-m', 'gemini-4-carbon', '--effort', 'high', *argv], FakeIn(text), out, err)
        return rc, out.getvalue(), err.getvalue()

    def test_sessions_dir_and_structured_errors(self):
        sdir = os.path.join(self.tmp, 'run', '.llm-chat', 'sessions')
        self.outputs = [(0, stream(), '')]
        rc, out, err = self.main(['--sessions-dir', sdir, '--system', 'sys'])
        self.assertEqual(rc, 0, err)
        meta = json.loads(err.split(self.mod.META_PREFIX, 1)[1])
        self.assertTrue(os.path.isfile(os.path.join(sdir, meta['session'] + '.json')))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'state', 'llm-chat', 'sessions', meta['session'] + '.json')))
        # 工作目录仍在状态目录下（模型看得到的路径不变）
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, 'state', 'llm-chat', 'agy', meta['session'])))
        self.assertNotIn('recovered', meta)
        # 续接不带 --sessions-dir 就找不到（必须每轮同一目录）
        self.outputs = [(0, stream(), '')]
        rc, _, err = self.main(['--session', meta['session']])
        self.assertEqual(rc, 1)
        self.assertIn('not found', err)
        # 中断报错：没有 --accept-recovered → 失败，带结构化分类
        self.outputs = [(0, stream('ERROR', '着法: d2d4', INTERRUPTED), '')]
        rc, out, err = self.main(['--sessions-dir', sdir, '--session', meta['session']])
        self.assertEqual((rc, out), (1, ''))
        detail = json.loads(err.split(self.mod.ERROR_PREFIX, 1)[1])
        self.assertEqual(detail, {'backend': 'agy', 'kind': 'error', 'source': 'status'})
        self.assertTrue(chat.transport_failure(out, err, rc, False))
        # 带 --accept-recovered：采用并标记
        self.outputs = [(0, stream('ERROR', '着法: d2d4', INTERRUPTED), '')]
        rc, out, err = self.main(['--sessions-dir', sdir, '--session', meta['session'], '--accept-recovered'])
        self.assertEqual((rc, out), (0, '着法: d2d4\n'))
        meta2 = json.loads(err.split(self.mod.META_PREFIX, 1)[1])
        self.assertEqual(meta2['recovered']['status'], 'ERROR')
        # 取回的答复与上一轮一模一样：当成旧答复重放，不采用，也不算传输类
        self.outputs = [(0, stream('ERROR', '着法: d2d4', INTERRUPTED), '')]
        rc, out, err = self.main(['--sessions-dir', sdir, '--session', meta['session'], '--accept-recovered'])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(err.split(self.mod.ERROR_PREFIX, 1)[1])['source'], 'stale')
        self.assertFalse(chat.transport_failure(out, err, rc, False))
        with open(os.path.join(sdir, meta['session'] + '.json')) as f:
            saved = json.load(f)
        self.assertEqual(len(saved['turns']), 2)          # 失败的轮次不入会话

    def test_accept_recovered_is_agy_only(self):
        with mock.patch.dict(os.environ, {'API_KEY_OPENROUTER': 'fake-key-for-test'}):
            out, err = io.StringIO(), io.StringIO()
            rc = self.mod.main(['-m', 'openrouter:openai/gpt-5', '--system', 's', '--accept-recovered'],
                               FakeIn('hi'), out, err)
        self.assertEqual(rc, 1)
        self.assertIn('--accept-recovered is supported only on agy', err.getvalue())
        self.assertNotIn(self.mod.ERROR_PREFIX, err.getvalue())


if __name__ == '__main__':
    unittest.main()


class AgyEnvAndRedaction(unittest.TestCase):
    """agy 的认证方式由 agy 自己的配置决定：仓库原样放行 agy 自身的配置变量、挡住其他密钥，且不让 key 进命令行或报错文本。"""

    FAKE = 'fake-agy-secret-value-0123456789'

    def setUp(self):
        mod = load_llm_chat()
        for p in (mock.patch.object(sys, 'path', list(sys.path)), mock.patch.dict(sys.modules)):
            p.start()
            self.addCleanup(p.stop)
        sys.modules.pop('agy_core', None)
        self.core = mod.agy_core()

    def env(self, **extra):
        base = {'HOME': '/home/x', 'PATH': '/bin', 'LC_ALL': 'C.UTF-8'}
        base.update(extra)
        return mock.patch.dict(os.environ, base, clear=True)

    def test_agy_own_variables_pass_others_do_not(self):
        with self.env(GEMINI_API_KEY=self.FAKE, GOOGLE_GEMINI_BASE_URL='https://example.invalid',
                      AGY_ADC_AUTH='1', AGY_LLM_GATEWAY_URL='https://gw.invalid', ANTIGRAVITY_X='1',
                      GOOGLE_APPLICATION_CREDENTIALS='/tmp/adc.json',
                      ANTHROPIC_API_KEY='a' * 20, OPENAI_API_KEY='o' * 20, API_KEY_OPENROUTER='r' * 20,
                      GH_TOKEN='g' * 20, LLM_CHAT_AGY_API_KEY='1'):
            env = self.core.agy_env()
        for name in ('HOME', 'PATH', 'LC_ALL', 'GEMINI_API_KEY', 'GOOGLE_GEMINI_BASE_URL', 'AGY_ADC_AUTH',
                     'AGY_LLM_GATEWAY_URL', 'ANTIGRAVITY_X', 'GOOGLE_APPLICATION_CREDENTIALS'):
            self.assertIn(name, env)
        for name in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'API_KEY_OPENROUTER', 'GH_TOKEN', 'LLM_CHAT_AGY_API_KEY'):
            self.assertNotIn(name, env)

    def test_no_opt_in_switch_or_settings_flag(self):
        with self.env(LLM_CHAT_AGY_SETTINGS='{"modelProvider": "gemini"}', GEMINI_API_KEY=self.FAKE):
            cmd = self.core.build_command('a', model='gemini-4-carbon', effort='high', conversation='c')
        self.assertNotIn('--settings', cmd)
        self.assertFalse(any(self.FAKE in part for part in cmd))

    def test_key_value_redacted_from_errors(self):
        out = stream('ERROR', '', 'bad key ' + self.FAKE)
        with self.env(GEMINI_API_KEY=self.FAKE):
            for code, o, err in ((0, out, ''), (1, '', 'denied for ' + self.FAKE), (0, '', 'x ' + self.FAKE)):
                with self.assertRaises(self.core.AgyError) as cm:
                    self.core.check_turn(code, o, err, allowed_tools=('view_file',))
                self.assertNotIn(self.FAKE, str(cm.exception))
                self.assertIn('[REDACTED]', str(cm.exception))
            info, _ = self.core.check_turn(0, stream('ERROR', '着法: e2e4', 'oops ' + self.FAKE), '',
                                           allowed_tools=('view_file',), accept_recovered=True)
            self.assertNotIn(self.FAKE, json.dumps(info['recovered']))

    def test_redact_leaves_short_and_unrelated_values(self):
        with self.env(GEMINI_API_KEY='short', OTHER_TOKEN=self.FAKE):
            self.assertEqual(self.core.redact('short ' + self.FAKE), 'short ' + self.FAKE)
