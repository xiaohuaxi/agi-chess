"""调 `codex exec` 当棋手：sol 走 ChatGPT 订阅（棋手写成 codex:<模型>），DeepSeek 走本机 deepseek profile 的供应商
（deepseek:<模型>）。只支持无状态（stateless / notes）：每次一个新会话、--ephemeral 不落会话记录。

隔离（证据见 docs/results/batch5-isolation.md）：
  - --ignore-user-config：不读 ~/.codex/config.toml（里面有 MCP、hooks、全开沙箱等）。**它会连 profile 一起丢掉**
    （profile 就是叠在用户配置那一层上的），所以 DeepSeek 不用 -p，而是读 ~/.codex/deepseek.config.toml，把里面的
    模型、供应商表、模型目录原样用 -c 拼回来——事实仍只在那份 profile 里。
  - 工具清零：features 关掉 shell / 代码模式 / 子代理 / 插件 / 浏览器等（DISABLED_FEATURES）；另外模型目录里的条目会
    自带一些工具（sol 是 code_mode_only + 多代理 v2 + clock，DeepSeek 带 shell），features 关不掉，所以给每次调用
    写一份只含这一个模型的目录副本，把 shell_type / tool_mode / multi_agent_version / experimental_supported_tools /
    apply_patch_tool_type 改掉（patch_model），用 -c model_catalog_json 指过去。抓包核实请求里工具数为 0。
  - 系统提示用 -c model_instructions_file 换掉 Codex 自带的那段编码助手说明，和 claude -p --system-prompt 对应；
    权限说明、技能清单、协作模式、环境说明（含工作目录）这几段都用 -c 关掉。
  - 运行目录是仓库外的空临时目录（和 claude 同一个），另加 project_doc_max_bytes=0；-s read-only、--ignore-rules。
  - **关不掉的**：~/.codex/AGENTS.md（用户级全局规范，约 1.2 万字）会作为一条用户消息注入。0.157.1 源码里它只认
    CODEX_HOME，没有配置开关；换 CODEX_HOME 要搬 ChatGPT 登录凭据，有把用户本机登录弄失效的风险，没做。它不带工具，
    只是每题一样的一段噪声。
兜底：事件流里出现 agent_message / reasoning 以外的条目（命令、文件改动、MCP、联网……）就抛 ToolUsed，整批停下。

用量：turn.completed 里的 input_tokens（含缓存命中）、cached_input_tokens、cache_write_input_tokens、output_tokens、
reasoning_output_tokens。换成 claude_cli.usage 的口径：in = input − cached，out 按 OpenAI 口径已含思考，think = reasoning。
没有花费字段（sol 走订阅，DeepSeek 按量计费但事件流里不给钱），cost 记 0。
"""
import hashlib, json, os, pathlib, re, subprocess, threading

KINDS = ('codex', 'deepseek')
ALIASES = {'sol': 'codex:gpt-6-sol'}          # quiz --model 的简写；deepseek 单写时取 profile 里的默认模型
PROFILE = pathlib.Path(os.environ.get('CODEX_HOME') or pathlib.Path.home() / '.codex') / 'deepseek.config.toml'
DISABLED_FEATURES = ('shell_tool', 'unified_exec', 'code_mode_host', 'sleep_tool', 'multi_agent', 'multi_agent_v2',
                     'view_image', 'image_generation', 'apps', 'plugins', 'browser_use', 'browser_use_external',
                     'computer_use', 'in_app_browser', 'goals', 'tool_suggest', 'skill_search', 'memories', 'hooks')
OFF = ('include_permissions_instructions=false', 'include_apps_instructions=false',
       'include_collaboration_mode_instructions=false', 'include_environment_context=false',
       'skills.include_instructions=false', 'web_search="disabled"', 'tools.experimental_request_user_input.enabled=false',
       'project_doc_max_bytes=0')
NO_TOOLS = {'shell_type': 'disabled', 'tool_mode': 'direct', 'multi_agent_version': 'disabled',
            'experimental_supported_tools': [], 'apply_patch_tool_type': None}
TEXT_ITEMS = ('agent_message', 'reasoning')


class ToolUsed(RuntimeError):
    """事件流里出现了工具调用：隔离失效，不能当棋手，整批停下交给人看。"""


def spec_of(model):
    """quiz --model 的值 → 棋手串：sol → codex:gpt-6-sol；deepseek → deepseek:<profile 默认模型>；
    写成 codex:<模型> / deepseek:<模型> 原样；其余当 claude 模型名。"""
    if model in ALIASES:
        return ALIASES[model]
    if model == 'deepseek':
        return 'deepseek:' + profile()['model']
    if model.split(':', 1)[0] in KINDS:
        return model
    return 'claude:' + model


# ---------------------------------------------------------------- deepseek profile（只认这份文件用到的简单 TOML）
_TABLE = re.compile(r'^\[([A-Za-z0-9_.\-"]+)\]\s*$')
_KV = re.compile(r'^([A-Za-z0-9_\-]+)\s*=\s*(.+?)\s*$')


def _value(s):
    if s in ('true', 'false'):
        return s == 'true'
    if re.fullmatch(r'-?\d+', s):
        return int(s)
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return json.loads(s)
    raise ValueError('profile 里有认不出的值：%r' % s)


def parse_profile(text):
    """把 profile 读成 {键: 值, 表名: {键: 值}}。只支持「键 = 字符串 / 布尔 / 整数」和 [a.b] 表头，别的写法直接报错，
    免得读错了还悄悄往下跑。"""
    out, cur = {}, None
    for raw in text.splitlines():
        line = raw.split(' #', 1)[0].strip() if not raw.strip().startswith('#') else ''
        if not line:
            continue
        m = _TABLE.match(line)
        if m:
            cur = out.setdefault(m[1], {})
            continue
        m = _KV.match(line)
        if not m:
            raise ValueError('profile 里有认不出的行：%r' % raw)
        (cur if cur is not None else out)[m[1]] = _value(m[2])
    return out


def profile(path=None):
    p = parse_profile(pathlib.Path(path or PROFILE).read_text(encoding='utf-8'))
    prov = p['model_provider']
    return {'model': p['model'], 'provider': prov, 'provider_table': p['model_providers.' + prov],
            'catalog': os.path.expanduser(p['model_catalog_json'])}


def _toml(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    return json.dumps(v, ensure_ascii=False)


def inline_table(d):
    return '{%s}' % ','.join('%s=%s' % (k, _toml(v)) for k, v in d.items())


# ---------------------------------------------------------------- 模型目录副本
def catalog_models(kind, prof=None):
    """模型目录：sol 取 `codex debug models`（Codex 自己在用的那份），DeepSeek 取 profile 指的目录文件。"""
    if kind == 'deepseek':
        return json.loads(pathlib.Path((prof or profile())['catalog']).read_text(encoding='utf-8'))['models']
    p = subprocess.run(['codex', 'debug', 'models'], capture_output=True, text=True, timeout=120,
                       stdin=subprocess.DEVNULL)
    return json.loads(p.stdout)['models']


def patch_model(models, slug):
    """取出这一个模型的条目，把会带出工具的字段改掉（NO_TOOLS），其余原样。"""
    hit = [m for m in models if m.get('slug') == slug]
    if not hit:
        raise SystemExit('模型目录里没有 %s（有：%s）' % (slug, ', '.join(m.get('slug', '?') for m in models)))
    return dict(hit[0], **NO_TOOLS)


def efforts_of(entry):
    return [x['effort'] for x in entry.get('supported_reasoning_levels') or []]


def _write_once(path, text):
    """内容按哈希命名，已有就不写；新写的先写临时文件再改名顶上，不会读到半截。
    quiz --jobs>1 时同进程几个线程会同时写同一个文件，临时文件名带上进程号和线程号，各写各的，
    谁后改名谁覆盖，内容一样；只用进程号时几个线程共用一个临时文件，先改名的把它挪走，后改名的就找不到了。"""
    if path.exists():
        return path
    tmp = path.with_name('.%s.%d-%d.tmp' % (path.name, os.getpid(), threading.get_ident()))
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)
    return path


def side_dir(cwd):
    """系统提示和模型目录副本放在运行目录旁边（<cwd>.codex/），运行目录本身保持空。"""
    d = pathlib.Path(str(cwd).rstrip('/') + '.codex')
    d.mkdir(parents=True, exist_ok=True)
    return d


def _digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]


_CATALOG = {}


def prepare(kind, model, effort, system, cwd, prof=None):
    """写好系统提示文件和模型目录副本，返回 (系统提示路径, 目录路径)。思考深度不在模型支持的档里就报错退出。"""
    key = (kind, model)
    if key not in _CATALOG:
        _CATALOG[key] = patch_model(catalog_models(kind, prof), model)
    entry = _CATALOG[key]
    if effort not in efforts_of(entry):
        raise SystemExit('%s:%s 的思考深度只能是 %s，收到 %s' % (kind, model, '/'.join(efforts_of(entry)), effort))
    d = side_dir(cwd)
    cat = json.dumps({'models': [entry]}, ensure_ascii=False, sort_keys=True)
    sys_path = _write_once(d / ('system-%s.md' % _digest(system)), system)
    cat_path = _write_once(d / ('catalog-%s-%s.json' % (model, _digest(cat))), cat)
    return str(sys_path), str(cat_path)


# ---------------------------------------------------------------- 命令
def command(kind, model, effort, system_file, catalog_file, cwd, prof=None):
    """拼 codex exec 命令（用户提示由 call 接在最后）。思考深度每次显式传。"""
    cmd = ['codex', 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral', '--skip-git-repo-check',
           '-C', str(cwd), '-s', 'read-only', '-m', model, '-c', 'model_reasoning_effort="%s"' % effort]
    if kind == 'deepseek':
        prof = prof or profile()
        cmd += ['-c', 'model_provider="%s"' % prof['provider'],
                '-c', 'model_providers.%s=%s' % (prof['provider'], inline_table(prof['provider_table']))]
    cmd += ['-c', 'model_catalog_json=%s' % json.dumps(str(catalog_file), ensure_ascii=False),
            '-c', 'model_instructions_file=%s' % json.dumps(str(system_file), ensure_ascii=False)]
    for f in DISABLED_FEATURES:
        cmd += ['-c', 'features.%s=false' % f]
    for o in OFF:
        cmd += ['-c', o]
    return cmd + ['--json']


def shown(kind, model, effort, prof=None):
    """记进 config 的命令行：文件路径换成占位，不碰盘（DeepSeek 的供应商表照 profile 展开，不含密钥本身）。"""
    cmd = command(kind, model, effort, '<系统提示文件>', '<模型目录副本>', '<运行目录>', prof)
    return ' '.join(repr(x) if (x == '' or ' ' in x) else x for x in cmd) + ' <用户提示>'


def version():
    try:
        return subprocess.run(['codex', '--version'], capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL).stdout.strip()
    except Exception as e:                       # 只是记进 config
        return '? (%s)' % e


# ---------------------------------------------------------------- 事件流
def parse(out):
    """把 --json 事件流（JSONL）收成和 claude -p 结果相近的 dict：result（最后一条 agent_message）、is_error、
    usage（turn.completed 原样）、thread_id、items（各条目类型，按出现顺序）。一行事件都没有返回 None（调用方按调不通处理）。
    出现 agent_message / reasoning 以外的条目就抛 ToolUsed。"""
    d = {'result': '', 'is_error': False, 'usage': None, 'thread_id': None, 'items': [], 'errors': []}
    n = 0
    for line in (out or '').splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        n += 1
        t = e.get('type')
        if t == 'thread.started':
            d['thread_id'] = e.get('thread_id')
        elif t in ('item.started', 'item.updated', 'item.completed'):
            it = e.get('item') or {}
            if it.get('type') not in TEXT_ITEMS:
                raise ToolUsed('事件流里出现了 %s：%s' % (it.get('type'), json.dumps(it, ensure_ascii=False)[:500]))
            if t == 'item.completed':
                d['items'].append(it.get('type'))
                if it.get('type') == 'agent_message':
                    d['result'] = it.get('text') or ''
        elif t == 'turn.completed':
            d['usage'] = e.get('usage') or {}
        elif t in ('turn.failed', 'error'):
            d['is_error'] = True
            msg = (e.get('error') or {}).get('message') if t == 'turn.failed' else e.get('message')
            d['errors'].append(msg)
            d['result'] = msg or d['result']
    if not n:
        return None
    if d['usage'] is None and not d['is_error']:
        d['is_error'] = True                     # 没收尾就断了
    return d


def usage(d, model=None):
    """换成 claude_cli.usage 的口径（字段含义见模块说明）。"""
    u = d.get('usage') or {}
    inp = u.get('input_tokens') or 0
    cached = u.get('cached_input_tokens') or 0
    out = u.get('output_tokens') or 0
    think = u.get('reasoning_output_tokens') or 0
    return {'in': inp - cached, 'cache_read': cached, 'cache_write': u.get('cache_write_input_tokens') or 0,
            'out': out, 'think': think, 'text_out': out - think, 'cost': 0,
            'duration_ms': None, 'ttft_ms': None, 'session_id': d.get('thread_id'), 'model': model or '',
            'stop_reason': 'error' if d.get('is_error') else 'end_turn', 'api_error_status': None}
