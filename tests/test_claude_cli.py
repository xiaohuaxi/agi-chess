"""离线单元测试：claude_cli.py 里不调 claude 的纯函数——用量展开、拼命令、会话记录路径编码。

绝对不调 `claude` 本体（call() 会花订阅额度，不测）；全部用手写的假 JSON / 假目录。
"""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from llmchess import claude_cli as CL


class Usage(unittest.TestCase):
    def test_expands_all_fields(self):
        d = {
            'usage': {'input_tokens': 100, 'cache_read_input_tokens': 20, 'cache_creation_input_tokens': 5,
                      'output_tokens': 70, 'output_tokens_details': {'thinking_tokens': 30}},
            'total_cost_usd': 0.0123, 'duration_ms': 1234, 'ttft_ms': 56, 'session_id': 'sid1',
            'modelUsage': {'claude-opus-5-5': {}}, 'stop_reason': 'end_turn', 'api_error_status': None,
        }
        u = CL.usage(d)
        self.assertEqual(u['in'], 100)
        self.assertEqual(u['cache_read'], 20)
        self.assertEqual(u['cache_write'], 5)
        self.assertEqual(u['out'], 70)
        self.assertEqual(u['think'], 30)
        # text_out = out - think（design.md P3：output_tokens 已经包含思考）
        self.assertEqual(u['text_out'], 40)
        self.assertEqual(u['cost'], 0.0123)
        self.assertEqual(u['session_id'], 'sid1')
        self.assertEqual(u['model'], 'claude-opus-5-5')
        self.assertEqual(u['stop_reason'], 'end_turn')

    def test_missing_fields_default_to_zero(self):
        u = CL.usage({})
        self.assertEqual(u['in'], 0)
        self.assertEqual(u['cache_read'], 0)
        self.assertEqual(u['cache_write'], 0)
        self.assertEqual(u['out'], 0)
        self.assertEqual(u['think'], 0)
        self.assertEqual(u['text_out'], 0)
        self.assertEqual(u['cost'], 0)
        self.assertEqual(u['model'], '')

    def test_text_out_excludes_thinking(self):
        # 冒烟实测过的那条边界：正文只回 "ok"，output=37、thinking=33 时 text_out 应该是 4
        d = {'usage': {'output_tokens': 37, 'output_tokens_details': {'thinking_tokens': 33}}}
        self.assertEqual(CL.usage(d)['text_out'], 4)


class Command(unittest.TestCase):
    def test_stateless_or_notes_uses_no_session_persistence(self):
        cmd = CL.command('opus', 'high', 'SYS')
        self.assertIn('--no-session-persistence', cmd)
        self.assertNotIn('--session-id', cmd)
        self.assertNotIn('--resume', cmd)
        self.assertEqual(cmd[cmd.index('--model') + 1], 'opus')
        self.assertEqual(cmd[cmd.index('--effort') + 1], 'high')
        self.assertEqual(cmd[cmd.index('--system-prompt') + 1], 'SYS')

    def test_session_first_call_uses_session_id(self):
        cmd = CL.command('opus', 'high', 'SYS', session='abc-123', new_session=True)
        self.assertIn('--session-id', cmd)
        self.assertEqual(cmd[cmd.index('--session-id') + 1], 'abc-123')
        self.assertNotIn('--resume', cmd)
        self.assertNotIn('--no-session-persistence', cmd)

    def test_session_followup_uses_resume(self):
        cmd = CL.command('opus', 'high', 'SYS', session='abc-123', new_session=False)
        self.assertIn('--resume', cmd)
        self.assertEqual(cmd[cmd.index('--resume') + 1], 'abc-123')
        self.assertNotIn('--session-id', cmd)
        self.assertNotIn('--no-session-persistence', cmd)


class TranscriptPath(unittest.TestCase):
    def test_directory_encoding(self):
        cwd = '/Users/xhx/repos/llm-chess/runs/x1/cwd'
        p = CL.transcript_path(cwd, 'sess-123')
        expected_dir = '-Users-xhx-repos-llm-chess-runs-x1-cwd'
        self.assertEqual(p, pathlib.Path.home() / '.claude' / 'projects' / expected_dir / 'sess-123.jsonl')

    def test_non_alnum_all_become_dashes(self):
        # 用一个带各种非字母数字字符、但确定不是符号链接的临时目录，核实“非字母数字都换成 -”这条规则本身
        tmp = tempfile.mkdtemp(prefix='llmchess.test_')
        try:
            real = os.path.realpath(tmp)
            p = CL.transcript_path(tmp, 's1')
            expected = ''.join(c if c.isalnum() else '-' for c in real)
            self.assertEqual(p.parent.name, expected)
            self.assertEqual(p.name, 's1.jsonl')
        finally:
            shutil.rmtree(tmp)


class TranscriptFlags(unittest.TestCase):
    def test_finds_safeguard_mentions_in_user_messages_only(self):
        tmp = tempfile.mkdtemp(prefix='llmchess.test_')
        try:
            cwd = os.path.join(tmp, 'cwd')
            os.makedirs(cwd)
            session = 'sess-xyz'
            p = CL.transcript_path(cwd, session)
            p.parent.mkdir(parents=True, exist_ok=True)
            lines = [
                {'type': 'user', 'message': {'content': 'normal text'}},
                {'type': 'assistant', 'message': {'content': 'safeguards mention here should be ignored'}},
                {'type': 'user', 'message': {'content': 'Your last response was flagged by our safeguards system.'}},
            ]
            with open(p, 'w', encoding='utf-8') as f:
                for l in lines:
                    f.write(json.dumps(l, ensure_ascii=False) + '\n')
                f.write('not json, should be skipped without raising\n')
            hits = CL.transcript_flags(cwd, session)
            self.assertEqual(len(hits), 1)
        finally:
            shutil.rmtree(tmp)

    def test_missing_transcript_returns_none(self):
        tmp = tempfile.mkdtemp(prefix='llmchess.test_')
        try:
            cwd = os.path.join(tmp, 'cwd')
            os.makedirs(cwd)
            self.assertIsNone(CL.transcript_flags(cwd, 'no-such-session'))
        finally:
            shutil.rmtree(tmp)


class CallTimeout(unittest.TestCase):
    """call() 的超时可配、失败回调：subprocess.run 打桩，不真调 claude。"""

    def test_timeout_param_and_on_fail_then_success(self):
        seen, fails = [], []
        good = subprocess.CompletedProcess([], 0, stdout=json.dumps({'result': '着法: e2e4'}), stderr='')

        def run(cmd, **k):
            seen.append(k['timeout'])
            if len(seen) == 1:
                raise subprocess.TimeoutExpired(cmd, k['timeout'])
            return good
        with mock.patch.object(CL.subprocess, 'run', run), mock.patch.object(CL.time, 'sleep', lambda s: None):
            d, _ = CL.call(['claude'], 'p', '/tmp', waits=(5,), timeout=77, on_fail=fails.append)
        self.assertEqual(d['result'], '着法: e2e4')
        self.assertEqual(seen, [77, 77])
        self.assertEqual(len(fails), 1)
        self.assertTrue(fails[0]['timeout'])
        self.assertEqual((fails[0]['try'], fails[0]['next_wait'], fails[0]['rc']), (1, 5, -1))

    def test_default_timeout_and_broken_callback(self):
        seen = []
        bad = subprocess.CompletedProcess([], 1, stdout='not json', stderr='boom')

        def run(cmd, **k):
            seen.append(k['timeout'])
            return bad

        def broken(info):
            raise RuntimeError('记录坏了')
        with mock.patch.object(CL.subprocess, 'run', run), mock.patch.object(CL.time, 'sleep', lambda s: None), \
                mock.patch('builtins.print'):
            with self.assertRaises(CL.Paused):          # 回调出错不影响重试，最后照常抛「连续调不通」
                CL.call(['claude'], 'p', '/tmp', waits=(0,), on_fail=broken)
        self.assertEqual(seen, [CL.TIMEOUT, CL.TIMEOUT])
        self.assertEqual(CL.TIMEOUT, 3600)


class Flagged(unittest.TestCase):
    """flagged() 现在吃整个响应 dict（不是只吃正文字符串）：refusal 的 stop_reason，或正文里带那句拦截文字。"""

    def test_stop_reason_refusal(self):
        self.assertTrue(CL.flagged({'stop_reason': 'refusal', 'result': 'whatever'}))

    def test_result_text_mentions_flag(self):
        self.assertTrue(CL.flagged({'stop_reason': 'end_turn', 'result': 'blah safeguards flagged this message blah'}))

    def test_normal_reply_not_flagged(self):
        self.assertFalse(CL.flagged({'stop_reason': 'end_turn', 'result': '着法: e2e4'}))


if __name__ == '__main__':
    unittest.main()
