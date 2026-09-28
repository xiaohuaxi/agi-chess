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
        self.assertIn('本步还可重选 3 次', calls[1]['stdin'])
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

    def test_forfeit_after_four_illegal(self):
        self.plan([{'text': '着法: a0a9'}, {'text': '没想好'}, {'text': 'Move: zz'}, {'text': '着法: a0a9'}])
        rc = self.play(['--game', 'xiangqi', '--tag', 'f', '--black', 'random', '--max-plies', '4'])
        self.assertEqual(rc, 0)
        calls = self.calls()
        self.assertEqual(len(calls), 4)
        self.assertIn('这步的写法认不出来', calls[2]['stdin'])            # 「没想好」按最后一行读，认不出
        end = [r for r in self.recs('f') if r['type'] == 'forfeit'][0]['end']
        self.assertEqual(end['winner'], 'b')

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
        self.assertIn('还可重选 3 次', c[0]['stdin'])            # 暂停前用掉的一次照记录接上
        self.assertIn('还可重选 2 次', c[1]['stdin'])


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

    def test_real_rejects_legal_list(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(io.StringIO()):
                cli.main(['play', '--game', 'chess', '--legal', 'list', '--dry-run'])


if __name__ == '__main__':
    unittest.main()
