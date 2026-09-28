"""整盘棋手的模型调用走用户级 skill llm-chat 的脚本（Claude / GPT / DeepSeek 三路一个入口，不带工具，会话能续接）。

脚本默认在 ~/.claude/skills/llm-chat/scripts/llm_chat.py，环境变量 LLMCHESS_LLM_CHAT 可以改。它是别处维护的，这里只调用、
不改：用户提示走 stdin，回答在 stdout，stderr 最后一行是 `LLM_CHAT_META {json}`；失败时 stderr 写 `llm-chat: error: …`、
退出码 1（信号取消 130）。第一次调用给 --system，之后 --session <id> 续接同一段对话（Claude 是 claude -p --resume，
GPT 是 codex exec resume，DeepSeek 是脚本自己回放历史正文）。隔离与跨轮思考的实测见 docs/results/llm-chat-isolation.md。

这里做的只是把一次调用包成 claude_cli.call 认得的样子，好沿用那一套调不通重试、撞额度等解除、停止信号：
  - 成功：{'result': 回答, 'meta': META, 'is_error': False}
  - 安全分类器拦下（Claude 的报错正文带 safeguards flagged）：{'result': 报错, 'stop_reason': 'refusal', 'is_error': True}，
    交给对局循环记 flag，和以前一样不算非法。
  - 回答为空（三路的报错文字都带 empty answer）：{'result': '', 'empty_error': 报错}，对局循环照旧记「空回复」。
  - 其余失败原样交回（撞额度的文字由 claude_cli.limit_hit 认，其余按调不通重试）。
"""
import hashlib, json, os, pathlib, re, subprocess, sys, tempfile

from . import claude_cli

SCRIPT = os.environ.get('LLMCHESS_LLM_CHAT') or str(
    pathlib.Path.home() / '.claude' / 'skills' / 'llm-chat' / 'scripts' / 'llm_chat.py')
META = 'LLM_CHAT_META '
KINDS = ('claude', 'codex', 'deepseek')
DEEPSEEK_DEFAULT = 'deepseek-v4-pro'
DEEPSEEK_EFFORTS = ('low', 'high', 'max')       # DeepSeek 没有 medium / xhigh（batch5-isolation.md）
MARGIN = 60                                     # 外层超时比脚本自己的 --timeout 多等这么久，让脚本先收掉它的子进程
_EMPTY = re.compile(r'empty answer', re.I)


def state_dir():
    """llm-chat 的状态目录（规则照它的 SKILL.md：${XDG_STATE_HOME:-~/.local/state}/llm-chat）。只读，用来找 Claude 会话记录。"""
    base = os.environ.get('XDG_STATE_HOME', '')
    root = pathlib.Path(base) if base and os.path.isabs(base) else pathlib.Path.home() / '.local' / 'state'
    return root / 'llm-chat'


def script_info():
    """记进 config：脚本路径和内容摘要（llm-chat 改了版，记录里看得出来）。"""
    try:
        digest = hashlib.sha256(pathlib.Path(SCRIPT).read_bytes()).hexdigest()[:16]
    except OSError as e:
        digest = '? (%s)' % e
    return {'script': SCRIPT, 'sha256': digest}


def _latest(slugs, short):
    """codex 模型目录里以 -<short> 结尾的条目取版本号最大的（gpt-6-sol 胜过 gpt-5.6-sol）。"""
    def ver(s):
        return [int(x) if x.isdigit() else 0 for x in re.findall(r'\d+', s)]
    hit = sorted((s for s in slugs if s.endswith('-' + short)), key=ver)
    return hit[-1] if hit else None


def model_id(kind, model, slugs=None):
    """棋手串里的模型名 → 传给 llm-chat 的 -m。claude 原样（opus 之类的别名由 claude 自己解析，实际模型记在 meta 里）；
    codex 写全名（gpt-…）原样，写短名（sol）按 `codex debug models` 的目录取最新一代；deepseek 空着取 deepseek-v4-pro。"""
    if kind == 'claude':
        return model
    if kind == 'deepseek':
        return model if model and model != 'deepseek' else DEEPSEEK_DEFAULT
    if model.startswith('gpt-'):
        return model
    if slugs is None:
        p = subprocess.run(['codex', 'debug', 'models'], capture_output=True, text=True, timeout=120)
        slugs = [m['slug'] for m in json.loads(p.stdout)['models']]
    full = _latest(slugs, model)
    if not full:
        raise SystemExit('codex 模型目录里找不到 %r（有：%s）' % (model, ', '.join(slugs)))
    return full


def command(model, effort, system=None, session=None, timeout=claude_cli.TIMEOUT):
    """一次调用的命令。第一次调用给 system（新会话），续接给 session；两个都不给不行。"""
    cmd = [sys.executable, SCRIPT, '-m', model, '--effort', effort, '--timeout', str(timeout)]
    if session:
        return cmd + ['--session', session]
    assert system is not None, '新会话要系统提示'
    return cmd + ['--system', system]


def shown(model, effort):
    return 'python3 %s -m %s --effort %s [--system <系统提示> | --session <会话>] < <用户提示>' % (SCRIPT, model, effort)


def run(cmd, prompt, cwd, env, timeout):
    """claude_cli.call 的 run 钩子：用户提示走 stdin，把脚本的输出折成一个 JSON 串交回（见模块说明）。"""
    p = subprocess.run(cmd, input=prompt, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout + MARGIN)
    out, err, rc = p.stdout, p.stderr, p.returncode
    if rc == 0:
        meta = None
        for line in reversed(err.splitlines()):
            if line.startswith(META):
                meta = json.loads(line[len(META):])
                break
        if meta is None:
            return out, err + '\n（没有 LLM_CHAT_META 行）', 1
        text = out[:-1] if out.endswith('\n') else out
        return json.dumps({'result': text, 'meta': meta, 'is_error': False}, ensure_ascii=False), err, 0
    if rc == 1 and claude_cli.FLAG_TEXT in err:
        return json.dumps({'result': err.strip()[-2000:], 'stop_reason': 'refusal', 'is_error': True},
                          ensure_ascii=False), err, 0
    if rc == 1 and _EMPTY.search(err) and 'llm-chat: error:' in err:
        return json.dumps({'result': '', 'empty_error': err.strip()[-500:], 'is_error': False}), err, 0
    return out, err, rc


def call(cmd, prompt, **kw):
    """跑一次（带重试、等额度）；返回 (dict, 用时)。kw 透传给 claude_cli.call（on_fail / on_wait）。"""
    cwd = tempfile.gettempdir()                 # 脚本自己在它的空目录里起 CLI，这里的运行目录无所谓
    timeout = int(cmd[cmd.index('--timeout') + 1])
    return claude_cli.call(cmd, prompt, cwd, timeout=timeout, run=run, **kw)


def usage(d, kind):
    """换成 claude_cli.usage 的口径：in 是没走缓存的输入，out 含思考，think 单列。
    llm-chat 的 input_tokens：Claude 是没走缓存的那部分；GPT（codex）和 DeepSeek 含缓存命中，要减掉。
    cost 是这一轮自己的（Claude 按标价估；GPT、DeepSeek 没有，记 0）。"""
    m = d.get('meta') or {}
    inp = m.get('input_tokens') or 0
    cached = m.get('cache_read') or 0
    out = m.get('output_tokens') or 0
    think = m.get('reasoning_tokens') or 0
    return {'in': inp if kind == 'claude' else max(0, inp - cached), 'cache_read': cached,
            'cache_write': m.get('cache_write') or 0, 'out': out, 'think': think, 'text_out': out - think,
            'cost': m.get('cost_usd') or 0, 'duration_ms': None, 'ttft_ms': None, 'session_id': m.get('session'),
            'model': m.get('model') or '', 'provider': m.get('provider'),
            'stop_reason': 'refusal' if d.get('stop_reason') == 'refusal' else 'end_turn', 'api_error_status': None}


def claude_transcript(session):
    """Claude 会话在 claude 那边的记录文件路径（查安全分类器自动插的那条消息用）；拿不到返回 None。
    会话 id 对应的 claude 会话记在 llm-chat 的会话文件里（backend_session），运行目录是它的 empty/。"""
    if not session:
        return None
    try:
        s = json.loads((state_dir() / 'sessions' / ('%s.json' % session)).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    backend = s.get('backend_session')
    return claude_cli.transcript_path(str(state_dir() / 'empty'), backend) if backend else None


TOOL_ITEMS = ('function_call', 'custom_tool_call', 'local_shell_call', 'web_search_call', 'tool_search_call',
              'mcp_tool_call')


def codex_tool_calls(session):
    """GPT 会话里的工具调用条数（读 llm-chat 的 codex 会话记录，只读）；找不到记录返回 None。
    兜底用：llm-chat 的 GPT 路径请求里还挂着 code mode 的几件工具（执行层关着，调出来也落空），它自己又不检测
    工具调用（docs/results/llm-chat-isolation.md）。这里补上 batch5 那道「出现正文和思考以外的条目就停」。"""
    if not session:
        return None
    try:
        s = json.loads((state_dir() / 'sessions' / ('%s.json' % session)).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    thread = s.get('thread_id')
    if not thread:
        return None
    hits = list((state_dir() / 'codex-home' / 'sessions').glob('*/*/*/rollout-*%s.jsonl' % thread))
    if not hits:
        return None
    n = 0
    for line in hits[0].read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get('type') == 'response_item' and (r.get('payload') or {}).get('type') in TOOL_ITEMS:
            n += 1
    return n
