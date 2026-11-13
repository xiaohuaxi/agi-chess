"""整盘棋手的模型调用走仓内 skill llm-chat 的脚本（Claude / GPT / DeepSeek / Gemini / agy 一个入口，会话能续接）。

脚本默认在仓内 .agents/skills/llm-chat/scripts/llm_chat.py（不存在则回退 ~/.claude/skills/llm-chat/scripts/llm_chat.py），
环境变量 AGI_CHESS_LLM_CHAT（兼容 AGICHESS_LLM_CHAT / LLMCHESS_LLM_CHAT）可以改。这里只调用、
不改：用户提示走 stdin，回答在 stdout，stderr 最后一行是 `LLM_CHAT_META {json}`；失败时 stderr 写 `llm-chat: error: …`、
退出码 1（信号取消 130）。第一次调用给 --system，之后 --session <id> 续接同一段对话（Claude 是 claude -p --resume，
GPT 是 codex exec resume，DeepSeek 是脚本自己回放历史正文，Gemini / agy 是 agy 续接）。隔离与跨轮思考的实测见 docs/results/llm-chat-isolation.md。

这里做的只是把一次调用包成 claude_cli.call 认得的样子，好沿用那一套调不通重试、撞额度等解除、停止信号：
  - 成功：{'result': 回答, 'meta': META, 'is_error': False}
  - 安全分类器拦下（各服务商明确拒答标记）：{'result': 报错, 'stop_reason': 'refusal', 'is_error': True}，
    交给对局循环记 flag 并立即中止，不算非法、不重问。
  - 回答为空（三路的报错文字都带 empty answer）：{'result': '', 'empty_error': 报错}，对局循环照旧记「空回复」。
  - agy 后端失败（含空正文、缺失/无效 META）结果不确定，默认停止；只有 transport_failure 认定的传输类失败可按
    对局 config 的 agy_retries 有上限地重发（design.md「agy 会话失败不能重发」一节），其余后端沿用原重试行为。
  - 会话记录（llm-chat 的 sessions/）新盘放在对局目录里（--sessions-dir，见 runner.sessions_dir），重启或换机后仍能续接。
"""
import hashlib, importlib.util, json, os, pathlib, re, shlex, shutil, subprocess, sys, tempfile
from functools import lru_cache

from . import claude_cli

_REPO_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / '.agents' / 'skills' / 'llm-chat' / 'scripts' / 'llm_chat.py'
_USER_SCRIPT = pathlib.Path.home() / '.claude' / 'skills' / 'llm-chat' / 'scripts' / 'llm_chat.py'


def _default_script():
    env = (os.environ.get('AGI_CHESS_LLM_CHAT')
           or os.environ.get('AGICHESS_LLM_CHAT')
           or os.environ.get('LLMCHESS_LLM_CHAT'))
    return env or str(_REPO_SCRIPT if _REPO_SCRIPT.is_file() else _USER_SCRIPT)


SCRIPT = _default_script()
META = 'LLM_CHAT_META '
ERROR_META = 'LLM_CHAT_ERROR '
# llm-chat LLM_CHAT_ERROR 的 source：这些是「没拿到答复」的传输 / 服务端类失败，可以有上限地重发。
# 工具、拒答、过滤、空正文、会话号不符、复读上一轮（stale）等一律不在其中，仍然锁住。
TRANSPORT_SOURCES = ('hard_timeout', 'print_timeout', 'exit', 'no_result', 'status')
# 旧记录 / 旧脚本没有 LLM_CHAT_ERROR 时的兜底：按大类匹配，不追具体版本的措辞。
_TRANSPORT_TEXT = re.compile(r'stream|timed? ?out|timeout|deadline|connection|network|interrupted|unavailable'
                             r'|\b5\d\d\b|reset by peer|\beof\b|capacity|overloaded', re.I)
KINDS = ('claude', 'codex', 'deepseek', 'gemini', 'agy', 'openrouter')
AGY_KINDS = ('gemini', 'agy')
DEEPSEEK_DEFAULT = 'deepseek-v4-pro'
DEEPSEEK_EFFORTS = ('low', 'high', 'max')       # DeepSeek 没有 medium / xhigh（batch5-isolation.md）
MARGIN = 60                                     # 外层超时比脚本自己的 --timeout 多等这么久，让脚本先收掉它的子进程
_EMPTY = re.compile(r'empty answer', re.I)


def state_dir():
    """llm-chat 的状态目录（规则照它的 SKILL.md：${XDG_STATE_HOME:-~/.local/state}/llm-chat）。只读，用来找 Claude 会话记录。"""
    base = os.environ.get('XDG_STATE_HOME', '')
    root = pathlib.Path(base) if base and os.path.isabs(base) else pathlib.Path.home() / '.local' / 'state'
    return root / 'llm-chat'


def sessions_root(sessions_dir=None):
    """会话记录目录：新盘是对局目录里的 --sessions-dir；旧盘（config 里没有）照旧在状态目录的 sessions/。"""
    return pathlib.Path(sessions_dir) if sessions_dir else state_dir() / 'sessions'


def read_session(session, sessions_dir=None):
    try:
        return json.loads((sessions_root(sessions_dir) / ('%s.json' % session)).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


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
    codex 写全名（gpt-…）原样，写短名（sol）按 `codex debug models` 的目录取最新一代；deepseek 空着取 deepseek-v4-pro；
    Gemini 必须给完整 gemini-* slug；agy 给 `agy models` 中的完整 slug，固定补 agy/，不猜别名。"""
    if kind == 'openrouter':
        try:
            backend_module().assert_openrouter_allowed(model, explicit=True)
        except backend_module().ChatError as e:
            raise ConfigError(str(e)) from e
        return 'openrouter:' + model
    if kind == 'claude':
        return model
    if kind == 'deepseek':
        if not model or model == 'deepseek':
            return DEEPSEEK_DEFAULT
        return model if model.startswith(('deepseek-', 'deepseek/')) else 'deepseek-' + model
    if kind == 'gemini':
        if not re.fullmatch(r'gemini-[A-Za-z0-9][A-Za-z0-9._-]*', model):
            raise SystemExit('Gemini 要写 agy models 中的完整 gemini-* slug，收到 %r' % model)
        return model
    if kind == 'agy':
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', model):
            raise SystemExit('agy 要写 agy models 中的完整 slug（不含 agy/），收到 %r' % model)
        return 'agy/' + model
    if model.startswith('gpt-'):
        return model
    if slugs is None:
        try:
            p = subprocess.run(['codex', 'debug', 'models'], capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            raise SystemExit('codex CLI not found in PATH（请先安装并登录 Codex CLI，或写完整模型名如 codex:gpt-6-sol）')
        if p.returncode != 0:
            raise SystemExit('codex debug models 失败（exit %d）：%s' % (p.returncode, (p.stderr or p.stdout).strip()))
        try:
            slugs = [m['slug'] for m in json.loads(p.stdout)['models']]
        except (ValueError, KeyError, TypeError) as e:
            raise SystemExit('codex debug models 输出解析失败：%s' % e)
    full = _latest(slugs, model)
    if not full:
        raise SystemExit('codex 模型目录里找不到 %r（有：%s）' % (model, ', '.join(slugs)))
    return full


def command(model, effort, system=None, session=None, timeout=claude_cli.TIMEOUT, drop_thinking=False,
            sessions_dir=None, accept_recovered=False):
    """一次调用的命令。第一次调用给 system（新会话），续接给 session；两个都不给不行。
    drop_thinking：续接时不带此前几轮的思考。llm-chat 在会话首轮定下、存进会话，之后省略即沿用（中途加上会报错），
    所以只在新会话那次传；续接轮不传。
    sessions_dir：会话记录放哪（llm-chat --sessions-dir）；None 用 llm-chat 默认位置（旧盘）。
    accept_recovered：agy 报非 SUCCESS 但结果里已有本轮答复时接受并标 recovered（llm-chat --accept-recovered，只限 agy）。"""
    cmd = [sys.executable, SCRIPT, '-m', model, '--effort', effort, '--timeout', str(timeout)]
    if sessions_dir:
        cmd += ['--sessions-dir', str(sessions_dir)]
    if accept_recovered and model.startswith(('gemini-', 'agy/')):
        cmd += ['--accept-recovered']
    if session:
        return cmd + ['--session', session]
    assert system is not None, '新会话要系统提示'
    return cmd + (['--drop-thinking'] if drop_thinking else []) + ['--system', system]


def shown(model, effort, drop_thinking=False):
    return 'python3 %s -m %s --effort %s [%s--system <系统提示> | --session <会话>] < <用户提示>' % (
        SCRIPT, model, effort, '--drop-thinking ' if drop_thinking else '')


def run(cmd, prompt, cwd, env, timeout):
    """claude_cli.call 的 run 钩子：用户提示走 stdin，把脚本的输出折成一个 JSON 串交回（见模块说明）。"""
    try:
        p = subprocess.run(cmd, input=prompt, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout + MARGIN)
    except FileNotFoundError as e:
        return '', 'llm-chat: error: %s\n' % e, 1
    out, err, rc = p.stdout, p.stderr, p.returncode
    if claude_cli.refusal_text(err) or claude_cli.refusal_text(out):
        return json.dumps({'result': out or err, 'stop_reason': 'refusal', 'is_error': True,
                           'refusal_evidence': {'stdout': out, 'stderr': err, 'rc': rc}},
                          ensure_ascii=False), err, 0
    if rc == 0:
        meta = None
        for line in reversed(err.splitlines()):
            if line.startswith(META):
                try:
                    meta = json.loads(line[len(META):])
                except ValueError:
                    return out, err + '\n（LLM_CHAT_META 格式无效）', 1
                break
        if not isinstance(meta, dict) or not isinstance(meta.get('session'), str) or not meta['session']:
            return out, err + '\n（缺少有效 LLM_CHAT_META/session）', 1
        text = out[:-1] if out.endswith('\n') else out
        if agy_command(cmd) and not text.strip():
            return out, err + '\n（agy 返回空正文，无法确认本次会话结果）', 1
        return json.dumps({'result': text, 'meta': meta, 'is_error': False}, ensure_ascii=False), err, 0
    if rc == 1 and not agy_command(cmd) and _EMPTY.search(err) and 'llm-chat: error:' in err:
        return json.dumps({'result': '', 'empty_error': err.strip()[-500:], 'is_error': False}), err, 0
    return out, err, rc


def error_meta(err):
    """llm-chat 失败时 stderr 里的 LLM_CHAT_ERROR {json}（只有 agy 失败才有）；没有或格式不对返回 None。"""
    for line in reversed((err or '').splitlines()):
        if line.startswith(ERROR_META):
            try:
                d = json.loads(line[len(ERROR_META):])
            except ValueError:
                return None
            return d if isinstance(d, dict) else None
    return None


def transport_failure(out, err, rc=1, timed_out=False):
    """这次 agy 调用失败是不是「传输 / 服务端类、没拿到答复」，可以有上限地重发。

    优先看 llm-chat 的结构化 LLM_CHAT_ERROR（source 属于 TRANSPORT_SOURCES）；旧脚本 / 旧记录没有它时，
    才对 llm-chat 报错做大类文字匹配（不追具体 agy 版本措辞）。下面这些一律不算：外层超时（llm-chat 自己被杀，
    agy 子进程组可能还在跑，重发会与它并发写同一会话）、信号取消（130）、包装层错误（META 缺失 / 无效、OSError）、
    工具事件、明确拒答。rc=None 表示旧记录没存退出码。"""
    if timed_out or rc not in (1, None):
        return False
    text = '%s\n%s' % (out or '', err or '')
    if claude_cli.tool_error_text(text) or claude_cli.refusal_text(text):
        return False
    meta = error_meta(err)
    if meta is not None:
        return meta.get('backend') == 'agy' and meta.get('source') in TRANSPORT_SOURCES
    if 'LLM_CHAT_META' in (err or '') or '（缺少有效 LLM_CHAT_META' in (err or ''):
        return False
    lines = [x for x in (err or '').splitlines() if x.startswith('llm-chat: error:')]
    if not lines and rc is None:             # 旧记录可能只存了报错正文
        lines = [err or '']
    return bool(lines) and bool(_TRANSPORT_TEXT.search(lines[-1])) and not _EMPTY.search(lines[-1])


def agy_command(cmd):
    """llm-chat 的 agy 路由：保留旧 gemini-*，也覆盖 agy/claude-* 等完整型号。"""
    return '-m' in cmd and cmd[cmd.index('-m') + 1].startswith(('gemini-', 'agy/'))


def call(cmd, prompt, retry_wait=None, on_retry=None, **kw):
    """返回 (dict, 用时)。agy 后端失败默认即停；retry_wait() 给出下次重发前等几秒（None 不重发）时，
    只对 transport_failure 认定的传输类失败重发，重发前先调 on_retry(info) 落审计记录。其他后端带重试/等额度。
    kw 透传给 claude_cli.call。"""
    cwd = tempfile.gettempdir()                 # 脚本自己在它的空目录里起 CLI，这里的运行目录无所谓
    timeout = int(cmd[cmd.index('--timeout') + 1])
    if agy_command(cmd):
        kw['fail_closed'] = True
        if retry_wait:
            kw.update(transient=transport_failure, retry_wait=retry_wait, on_retry=on_retry)
    return claude_cli.call(cmd, prompt, cwd, timeout=timeout, run=run, **kw)


def usage(d, kind):
    """换成 claude_cli.usage 的口径：in 是没走缓存的输入，out 含思考，think 单列。
    llm-chat 的 input_tokens：Claude 是没走缓存的那部分；GPT（codex）、DeepSeek 和 agy 后端含缓存命中，要减掉。
    cost 是这一轮自己的（Claude 按标价估；GPT、DeepSeek、agy 没有，记 0）。"""
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


def claude_transcript(session, sessions_dir=None):
    """Claude 会话在 claude 那边的记录文件路径（查安全分类器自动插的那条消息用）；拿不到返回 None。
    会话 id 对应的 claude 会话记在 llm-chat 的会话文件里（backend_session），运行目录是它的 empty/
    （运行目录始终在状态目录下，--sessions-dir 只挪会话记录）。"""
    if not session:
        return None
    s = read_session(session, sessions_dir)
    if s is None:
        return None
    backend = s.get('backend_session')
    return claude_cli.transcript_path(str(state_dir() / 'empty'), backend) if backend else None


TOOL_ITEMS = ('function_call', 'custom_tool_call', 'local_shell_call', 'web_search_call', 'tool_search_call',
              'mcp_tool_call')


def codex_tool_calls(session, sessions_dir=None):
    """GPT 会话里的工具调用条数（读 llm-chat 的 codex 会话记录，只读）；找不到记录返回 None。
    兜底用：llm-chat 的 GPT 路径请求里还挂着 code mode 的几件工具（执行层关着，调出来也落空），它自己又不检测
    工具调用（docs/results/llm-chat-isolation.md）。这里补上 batch5 那道「出现正文和思考以外的条目就停」。"""
    if not session:
        return None
    s = read_session(session, sessions_dir)
    if s is None:
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


class ConfigError(ValueError):
    """调用前即可确定的配置错误；CLI 统一返回 2。"""


@lru_cache(maxsize=1)
def backend_module():
    # 路由规则以仓内脚本为唯一来源；导入不启动资源，也不读取凭据内容。
    spec = importlib.util.spec_from_file_location('agi_chess_llm_chat', _REPO_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_effort(kind, model, effort, side):
    if kind in AGY_KINDS:
        try:
            backend_module().check_agy_effort(model, effort)
        except backend_module().ChatError as e:
            raise ConfigError(str(e) + '；整盘用 --%s effort=%s，或显式选择一致型号' %
                              (side, model.rsplit('-', 1)[-1])) from e


def preflight(players, models=None, sessions=None, via_chat=True, sessions_dir=None):
    """仅检查可执行文件和 key 是否存在，不证明登录有效，不调用模型或切换渠道。

    自定义脚本拥有自己的后端契约，因此只检查脚本可读；不假设它使用本仓的 CLI/key。
    """
    if not any(spec.partition(':')[0] in KINDS for spec in players.values()):
        return
    if via_chat and pathlib.Path(SCRIPT).resolve() != _REPO_SCRIPT.resolve():
        if not pathlib.Path(SCRIPT).is_file():
            raise ConfigError('自定义 AGI_CHESS_LLM_CHAT 脚本不存在：%s' % SCRIPT)
        return
    mod = backend_module()
    errors, missing = [], {}
    for side, spec in players.items():
        kind, _, name = spec.partition(':')
        if kind not in KINDS:
            continue
        model = (models or {}).get(side)
        if not via_chat:
            backend = 'codex' if kind == 'deepseek' else kind
            if kind == 'deepseek':
                # 旧 DeepSeek 实际走 Codex profile，不应用整盘 HTTP 的 key/回退规则。
                from . import codex_cli
                try:
                    table = codex_cli.profile()['provider_table']
                except (OSError, ValueError, KeyError):
                    raise ConfigError('旧 DeepSeek 的 Codex profile 缺失或无效；请恢复原配置') from None
                key_name = table.get('env_key')
                if key_name and not os.environ.get(key_name):
                    errors.append('旧 DeepSeek profile 缺少 API Key：' + key_name)
        elif model is None and kind == 'codex' and not name.startswith('gpt-'):
            backend = 'codex'  # 别名解析之前先检查 CLI，dry-run 则完全不解析。
        else:
            model = model or model_id(kind, name)
            try:
                backend, _ = mod.route(model)
            except mod.ChatError as e:
                raise ConfigError(str(e)) from e
        sid = (sessions or {}).get(side)
        if via_chat and sid:
            sdir = sessions_dir.get(sid) if isinstance(sessions_dir, dict) else sessions_dir
            try:
                saved = json.loads((sessions_root(sdir) / (sid + '.json')).read_text())
            except (OSError, ValueError) as e:
                raise ConfigError('无法检查 llm-chat 会话 %s：%s' % (sid, e)) from e
            if saved['backend'] != backend:
                raise ConfigError('会话 %s 固定渠道 %s，当前配置路由到 %s；请恢复原渠道配置，不能切换续跑' %
                                  (sid, saved['backend'], backend))
        if backend in ('claude', 'codex', 'agy'):
            if not shutil.which(backend):
                errors.append('%s CLI not found in PATH（%s）' % (backend, spec))
                vendor = {'claude': 'anthropic', 'codex': 'openai', 'deepseek': 'deepseek',
                          'gemini': 'google'}.get(kind, '<vendor>')
                if kind == 'agy':
                    vendor = ('google' if name.startswith('gemini-') else
                              'anthropic' if name.startswith('claude-') else '<vendor>')
                missing[spec] = 'openrouter:%s/<model-id>' % vendor
        elif not mod.find_api_key(backend):
            keys = ' / '.join(mod.key_env_names(backend))
            if backend == 'deepseek':
                keys += '（或 API_KEY_OPENROUTER / OPENROUTER_API_KEY）'
            errors.append('缺少 API Key：' + keys)
    if errors:
        error = ConfigError('；'.join(errors))
        error.missing = missing
        raise error


def config_error_message(error, argv, module):
    message = str(error)
    missing = getattr(error, 'missing', {})
    if not missing:
        return message
    # 保留全部原参数与重复 side overrides；仅替换缺失棋手。未知映射不猜型号。
    args = list(argv)
    flags = ('--white', '--red', '--black', '--player', '--opp')
    for i, arg in enumerate(args):
        if arg in flags and i + 1 < len(args) and args[i + 1] in missing:
            args[i + 1] = missing[args[i + 1]]
        elif '=' in arg:
            flag, value = arg.split('=', 1)
            if flag in flags and value in missing:
                args[i] = flag + '=' + missing[value]
    if module == 'agi_chess' and args and args[0] == 'play':
        for flag in ('--white', '--black'):
            if not any(x == flag or x.startswith(flag + '=') for x in args) and not (
                    flag == '--white' and any(x == '--red' or x.startswith('--red=') for x in args)):
                if 'claude:opus' in missing:
                    args += [flag, missing['claude:opus']]
    elif module == 'agi_chess.batch' and not any(x == '--player' or x.startswith('--player=') for x in args):
        if 'claude:opus' in missing:
            args += ['--player', missing['claude:opus']]
    legacy = '--protocol=legacy' in args or any(
        arg == '--protocol' and i + 1 < len(args) and args[i + 1] == 'legacy'
        for i, arg in enumerate(args))
    if legacy:
        message += '\nlegacy 协议不能使用 OpenRouter；请恢复原 CLI，或另开 real 协议的新对局。'
    if args and args[0] != 'resume' and not legacy:
        message += ('\n可选 OpenRouter 命令模板（须先把占位项（如 <model-id>）替换成已确认的具体型号；不可原样执行）：\n' +
                    shlex.join(['python3', '-m', module, *args]))
    message += '\nOpenRouter API 另行付费，需配置 API_KEY_OPENROUTER（或 OPENROUTER_API_KEY）；不会自动安装、登录或换渠道。'
    return message
