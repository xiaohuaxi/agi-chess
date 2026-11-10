"""路由、依赖与 effort 的离线前置检查；不调用真实模型。"""
import contextlib
import io
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from agi_chess import batch, chat, cli
from tests import test_chat


class ProcessPreflight(unittest.TestCase):
    """通过真实模块入口验证 CLI 缺失时开局前退出。"""

    def run_cli(self, tmp, args, *, fake_agy=False):
        root = pathlib.Path(tmp)
        bindir = root / 'bin'
        bindir.mkdir(exist_ok=True)
        marker = root / 'agy-was-run'
        if fake_agy:
            agy = bindir / 'agy'
            agy.write_text('#!/bin/sh\nprintf invoked > "$AGY_MARKER"\nexit 91\n')
            agy.chmod(0o755)
        # 只保留运行 Python 所需的系统环境；密钥值从不读取或打印。
        env = {key: value for key, value in os.environ.items()
               if not key.startswith('API_KEY_') and key != 'OPENROUTER_API_KEY'
               and key not in ('AGI_CHESS_LLM_CHAT', 'AGICHESS_LLM_CHAT', 'LLMCHESS_LLM_CHAT')}
        env['PATH'] = str(bindir)
        env['AGY_MARKER'] = str(marker)
        repo = pathlib.Path(__file__).resolve().parents[1]
        return subprocess.run([sys.executable, '-m', 'agi_chess', *args], cwd=str(repo),
                              env=env, text=True, capture_output=True, check=False), marker

    def test_missing_claude_before_play_and_safe_openrouter_command(self):
        with tempfile.TemporaryDirectory(prefix='agi-preflight-play-') as tmp:
            out = pathlib.Path(tmp) / 'runs'
            args = ['play', '--game', 'chess', '--white', 'agy:gemini-3.8-flash', '--black', 'claude:haiku',
                    '--tag', 'space ; literal', '--out', str(out), '--w', 'effort=low', '--b', 'reason=off']
            result, marker = self.run_cli(tmp, args, fake_agy=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('claude CLI not found', result.stderr)
            self.assertIn('OpenRouter API 另行付费', result.stderr)
            self.assertIn('API_KEY_OPENROUTER', result.stderr)
            command = next(line for line in result.stderr.splitlines() if line.startswith('python3 '))
            rebuilt = shlex.split(command)[3:]
            expected = list(args)
            expected[6] = 'openrouter:anthropic/<model-id>'
            self.assertEqual(rebuilt, expected)
            self.assertFalse(marker.exists())
            self.assertFalse((out / 'space ; literal').exists())

    def test_missing_openrouter_key_does_not_run_other_agy(self):
        with tempfile.TemporaryDirectory(prefix='agi-preflight-key-') as tmp:
            args = ['play', '--game', 'chess', '--white', 'agy:gemini-3.8-flash', '--black',
                    'openrouter:openai/gpt-5', '--tag', 'key-missing', '--out', str(pathlib.Path(tmp) / 'runs')]
            result, marker = self.run_cli(tmp, args, fake_agy=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('API_KEY_OPENROUTER', result.stderr)
            self.assertFalse(marker.exists())
            self.assertFalse((pathlib.Path(tmp) / 'runs' / 'key-missing').exists())

    def test_both_missing_clis_report_all_and_dry_run_stays_offline(self):
        with tempfile.TemporaryDirectory(prefix='agi-preflight-all-') as tmp:
            args = ['play', '--game', 'chess', '--white', 'claude:haiku', '--black', 'codex:luna',
                    '--tag', 'all-missing', '--out', str(pathlib.Path(tmp) / 'runs')]
            result, _ = self.run_cli(tmp, args)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('claude CLI not found', result.stderr)
            self.assertIn('codex CLI not found', result.stderr)
            self.assertIn('API_KEY_OPENROUTER', result.stderr)
            self.assertFalse((pathlib.Path(tmp) / 'runs' / 'all-missing').exists())

            dry_args = ['play', '--game', 'chess', '--white', 'codex:luna', '--black', 'random',
                        '--tag', 'dry-only', '--out', str(pathlib.Path(tmp) / 'runs'), '--dry-run']
            dry, _ = self.run_cli(tmp, dry_args)
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertFalse((pathlib.Path(tmp) / 'runs' / 'dry-only').exists())


class Routes(unittest.TestCase):
    def test_new_gemini_prefix_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(cli.main(['play', '--game', 'chess', '--white', 'gemini:gemini-3.8-flash',
                                       '--black', 'random', '--dry-run']), 2)
        self.assertIn('agy:gemini-3.8-flash', err.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(batch.main(['run', '--game', 'chess', '--batch', 'unused', '--seeds', '1',
                                         '--player', 'random', '--opp', 'gemini:gemini-3.8-flash']), 2)

    def test_explicit_openrouter_and_default_routes(self):
        mod = chat.backend_module()
        for model, backend in [('anthropic/claude-opus-4.1', 'claude'), ('openai/gpt-5', 'codex')]:
            self.assertEqual(mod.route(model)[0], backend)
            self.assertEqual(mod.route('openrouter:' + model), ('openrouter', model))
            self.assertEqual(chat.model_id('openrouter', model), 'openrouter:' + model)
        for model in ['openrouter/auto', '@preset', 'vendor/@preset', 'vendor/model:online',
                      'vendor/model:free', 'vendor/multi-agent', 'typesafe/jev-router', 'vendor/', 'a/b/c']:
            with self.subTest(model=model), self.assertRaises(mod.ChatError):
                mod.route('openrouter:' + model)

    def test_http_request_records_usage_and_blocks_tools(self):
        mod = chat.backend_module()
        opts = mod.build_parser().parse_args(['-m', 'openrouter:anthropic/claude-opus-4.1', '--system', 'sys'])
        session = mod.new_session(opts, 'openrouter', 'anthropic/claude-opus-4.1', 'sys')
        session['provider_only'] = None
        response = {'model': session['model'], 'provider': 'Anthropic',
                    'choices': [{'finish_reason': 'stop', 'message': {'content': 'OK'}}],
                    'usage': {'cost': 0.25, 'prompt_tokens': 30, 'completion_tokens': 9}}
        with mock.patch.dict(os.environ, {'API_KEY_OPENROUTER': 'fake-test-key'}, clear=True), \
                mock.patch.object(mod, 'http_request', return_value=response) as http:
            result = mod.call_openrouter(session, 'hi', opts)
            self.assertEqual((result['provider'], result['cost_usd']), ('Anthropic', 0.25))
            self.assertEqual(http.call_args.args[2]['plugins'], [{'id': 'web', 'enabled': False}])
            response['choices'][0]['message']['tool_calls'] = [{'id': 'tool'}]
            with self.assertRaises(mod.ChatError):
                mod.call_openrouter(session, 'hi', opts)

    def test_session_backend_cannot_change(self):
        mod = chat.backend_module()
        opts = mod.build_parser().parse_args(['-m', 'openrouter:deepseek/deepseek-v4-pro', '--system', 'sys'])
        session = mod.new_session(opts, 'deepseek', 'deepseek-v4-pro', 'sys')
        with self.assertRaises(mod.ChatError):
            mod.continue_session(session, opts, 'openrouter', 'deepseek/deepseek-v4-pro', 'sys')

    def test_agy_effort_dual_source(self):
        mod = chat.backend_module()
        for model in ['gemini-3.8-flash', 'agy/claude-opus-5-5']:
            mod.check_agy_effort(model, 'medium')
            mod.check_agy_effort(model + '-high', None)
            mod.check_agy_effort(model + '-high', 'high')
            with self.assertRaises(mod.ChatError):
                mod.check_agy_effort(model + '-high', 'medium')
        with mock.patch.object(chat, 'preflight') as preflight, contextlib.redirect_stderr(io.StringIO()) as err:
            rc = cli.main(['play', '--game', 'chess', '--white', 'agy:gemini-3.8-flash-high',
                           '--black', 'random', '--w', 'effort=low', '--w', 'effort=medium'])
        self.assertEqual(rc, 2)
        self.assertIn('--w effort=high', err.getvalue())
        preflight.assert_not_called()
        chat.check_effort('codex', 'gpt-example-high', 'medium', 'w')
        chat.check_effort('claude', 'claude-example-high', 'medium', 'w')

    def test_all_missing_and_shell_safe_template(self):
        argv = ['play', '--game', 'xiangqi', '--red', 'claude:haiku', '--black=codex:sol',
                '--tag', 'space;$(literal)', '--w', 'effort=low', '--w', 'effort=high', '--b', 'reason=off']
        with mock.patch.object(chat, 'SCRIPT', str(chat._REPO_SCRIPT)), \
                mock.patch.object(chat.shutil, 'which', return_value=None), \
                mock.patch.object(chat.subprocess, 'run') as run, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(cli.main(argv), 2)
        run.assert_not_called()
        text = err.getvalue()
        self.assertIn('claude CLI not found', text)
        self.assertIn('codex CLI not found', text)
        self.assertIn('API_KEY_OPENROUTER', text)
        command = next(x for x in text.splitlines() if x.startswith('python3 '))
        rebuilt = shlex.split(command)[3:]
        expected = [*argv]
        expected[4] = 'openrouter:anthropic/<model-id>'
        expected[5] = '--black=openrouter:openai/<model-id>'
        self.assertEqual(rebuilt, expected)

    def test_missing_agy_preserves_known_vendor_only(self):
        players = {'w': 'agy:gemini-3.8-flash', 'b': 'agy:claude-opus-5-5', 'other': 'agy:unknown-model'}
        with mock.patch.object(chat, 'SCRIPT', str(chat._REPO_SCRIPT)), \
                mock.patch.object(chat.shutil, 'which', return_value=None), \
                self.assertRaises(chat.ConfigError) as error:
            chat.preflight(players)
        self.assertEqual(error.exception.missing, {
            players['w']: 'openrouter:google/<model-id>',
            players['b']: 'openrouter:anthropic/<model-id>',
            players['other']: 'openrouter:<vendor>/<model-id>',
        })

    def test_missing_api_key_before_any_call_and_dry_run_offline(self):
        with mock.patch.object(chat, 'SCRIPT', str(chat._REPO_SCRIPT)), \
                mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(chat.subprocess, 'run') as run, \
                contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['play', '--game', 'chess', '--white', 'random',
                                       '--black', 'openrouter:openai/gpt-5']), 2)
            self.assertEqual(cli.main(['play', '--game', 'chess', '--white', 'codex:sol',
                                       '--black', 'openrouter:openai/gpt-5', '--dry-run']), 0)
        run.assert_not_called()

    def test_batch_checks_all_opponents_before_driver(self):
        with tempfile.TemporaryDirectory(prefix='agi-routes-batch-') as tmp, \
                mock.patch.object(chat, 'SCRIPT', str(chat._REPO_SCRIPT)), \
                mock.patch.object(chat.shutil, 'which', return_value='/fake/claude'), \
                mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(batch.Driver, 'run') as run, \
                contextlib.redirect_stderr(io.StringIO()):
            rc = batch.main(['run', '--game', 'chess', '--batch', 'test', '--out', tmp, '--seeds', '1',
                             '--player', 'random', '--opp', 'claude:haiku', '--opp', 'openrouter:openai/gpt-5'])
            self.assertEqual(rc, 2)
            self.assertFalse((pathlib.Path(tmp) / 'test').exists())
            run.assert_not_called()

    def test_resume_checks_saved_channel(self):
        with tempfile.TemporaryDirectory(prefix='agi-routes-session-') as tmp, \
                mock.patch.object(chat, 'SCRIPT', str(chat._REPO_SCRIPT)), \
                mock.patch.dict(os.environ, {'XDG_STATE_HOME': tmp, 'API_KEY_OPENROUTER': 'fake'}, clear=True):
            path = chat.state_dir() / 'sessions'
            path.mkdir(parents=True)
            (path / 'sid.json').write_text(json.dumps({'backend': 'deepseek'}))
            with self.assertRaisesRegex(chat.ConfigError, '固定渠道 deepseek'):
                chat.preflight({'w': 'deepseek:deepseek-v4-pro'}, {'w': 'deepseek-v4-pro'}, {'w': 'sid'})


class OpenRouterGame(unittest.TestCase):
    setUp = test_chat.FakeChat.setUp
    plan = test_chat.FakeChat.plan
    calls = test_chat.FakeChat.calls
    play = test_chat.FakeChat.play
    recs = test_chat.FakeChat.recs
    def test_openrouter_session_and_resume(self):
        self.plan([{'text': '着法: e2e4'}, {'text': '着法: e7e5'},
                   {'text': '着法: g1f3'}, {'text': '着法: b8c6'}])
        players = ['--white', 'openrouter:anthropic/claude-opus-4.1', '--black', 'openrouter:openai/gpt-5']
        with mock.patch.object(chat, 'claude_transcript', side_effect=AssertionError('wrong transcript')), \
                mock.patch.object(chat, 'codex_tool_calls', side_effect=AssertionError('wrong transcript')):
            self.assertEqual(self.play(['--game', 'chess', '--tag', 'or-game', '--max-plies', '4',
                                        '--stop-after', '2', *players]), 3)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['resume', os.path.join(self.tmp, 'or-game')]), 0)
        self.assertEqual(len(self.calls()), 4)
        self.assertIn('--session', self.calls()[2]['argv'])
        recs = self.recs('or-game')
        usage = next(r['usage'] for r in recs if r['type'] == 'attempt')
        self.assertEqual((usage['provider'], usage['cost']), ('fake', 0.01))

    def test_old_gemini_record_resumes(self):
        self.plan([{'text': '着法: e2e4'}, {'text': '着法: e7e5'},
                   {'text': '着法: g1f3'}, {'text': '着法: b8c6'}])
        self.assertEqual(self.play(['--game', 'chess', '--tag', 'old-gemini', '--max-plies', '4',
                                    '--stop-after', '2', '--white', 'agy:gemini-3.8-flash-high',
                                    '--black', 'agy:gemini-3.8-flash-high']), 3)
        # 仅改本测试自己创建的记录，模拟公开前的旧 gemini: 格式。
        path = pathlib.Path(self.tmp) / 'old-gemini' / 'game.jsonl'
        path.write_text(path.read_text().replace('agy:gemini-', 'gemini:gemini-').replace('agy/gemini-', 'gemini-'))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['resume', str(path.parent)]), 0)
        self.assertEqual(len(self.calls()), 4)
        self.assertIn('gemini-3.8-flash-high', self.calls()[2]['argv'])

    def test_resume_rejects_old_conflicting_effort(self):
        self.plan([{'text': '着法: e2e4'}])
        self.assertEqual(self.play(['--game', 'chess', '--tag', 'old-conflict', '--max-plies', '4',
                                    '--stop-after', '1', '--white', 'agy:gemini-3.8-flash-high',
                                    '--black', 'random']), 3)
        path = pathlib.Path(self.tmp) / 'old-conflict' / 'game.jsonl'
        recs = self.recs('old-conflict')
        recs[0]['cfg']['sides']['w']['effort'] = 'medium'
        path.write_text(''.join(json.dumps(r) + '\n' for r in recs))
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(cli.main(['resume', str(path.parent)]), 2)
        self.assertIn('--w effort=high', err.getvalue())
        self.assertEqual(len(self.calls()), 1)


class StructuredRefusal(unittest.TestCase):
    def test_openrouter_refusal_stops_once_and_locks_resume(self):
        mod = chat.backend_module()
        cases = [
            ('stop', {'content': None, 'refusal': 'I cannot disclose hidden chain of thought.'}),
            ('stop', {'content': None, 'refusal': 'declined'}),
            *[(finish, {'content': '着法: e2e4'}) for finish in ('content_filter', 'refusal', 'safety')],
        ]
        for finish, message in cases:
            with self.subTest(finish=finish, message=message), \
                    tempfile.TemporaryDirectory(prefix='agi-structured-refusal-') as tmp:
                secret = 'fake-openrouter-key-for-redaction'
                response = {'choices': [{'finish_reason': finish, 'message': message}],
                            'provider': 'mock-provider', 'diagnostic': secret}

                def run_script(cmd, **kwargs):
                    self.assertEqual(cmd[1], str(chat._REPO_SCRIPT))
                    out, err = io.StringIO(), io.StringIO()
                    rc = mod.main(cmd[2:], io.StringIO(kwargs['input']), out, err)
                    return subprocess.CompletedProcess(cmd, rc, out.getvalue(), err.getvalue())

                with mock.patch.dict(os.environ, {'API_KEY_OPENROUTER': secret, 'XDG_STATE_HOME': tmp}), \
                        mock.patch.object(chat, 'SCRIPT', str(chat._REPO_SCRIPT)), \
                        mock.patch.object(mod, 'resolve_provider_slug', return_value=None), \
                        mock.patch.object(mod, 'http_request', return_value=response) as request, \
                        mock.patch.object(chat.subprocess, 'run', side_effect=run_script) as script, \
                        mock.patch.object(cli, 'commit', return_value='test'), \
                        mock.patch.object(cli.claude_cli, 'version', return_value='test'), \
                        mock.patch.object(cli.claude_cli, '_wait') as wait, \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(['play', '--game', 'chess', '--tag', 'refusal', '--out', tmp,
                                               '--white', 'openrouter:anthropic/claude-opus-4.1',
                                               '--black', 'random', '--max-plies', '1']), 3)
                    run_dir = pathlib.Path(tmp) / 'refusal'
                    self.assertEqual(cli.main(['resume', str(run_dir)]), 3)
                    request.assert_called_once()
                    script.assert_called_once()
                    wait.assert_not_called()
                rows = cli.records.read(run_dir / 'game.jsonl')
                self.assertEqual(rows[-1]['type'], 'refusal')
                self.assertFalse(any(r['type'] in ('move', 'call_fail', 'end', 'forfeit') for r in rows))
                evidence = rows[-1]['evidence']['response']['refusal_evidence']['stderr']
                raw = json.loads(evidence.split('response=', 1)[1])
                self.assertEqual(raw['choices'], response['choices'])
                self.assertEqual(raw['diagnostic'], '[REDACTED]')
                self.assertNotIn(secret, (run_dir / 'game.jsonl').read_text())

    def test_tool_evidence_precedes_structured_refusal(self):
        mod = chat.backend_module()
        for extra, usage in [({'tool_calls': [{'id': 'tool'}]}, {}),
                             ({'annotations': [{'type': 'url_citation'}]}, {}),
                             ({}, {'server_tool_use': {'web_search_requests': 1}})]:
            response = {'choices': [{'finish_reason': 'content_filter',
                                     'message': {'content': None, 'refusal': 'declined', **extra}}],
                        'usage': usage}
            with self.subTest(extra=extra, usage=usage), self.assertRaises(mod.ChatError) as error:
                mod.check_choice(response)
            self.assertTrue(cli.claude_cli.tool_error_text(str(error.exception)))
            self.assertFalse(cli.claude_cli.refusal_text(str(error.exception)))
