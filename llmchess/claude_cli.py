"""调 `claude -p`：拼命令、调不通重试、撞额度抛暂停、用量展开、安全分类器拦截识别。

命令（design.md P1、P7）：
  CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 claude -p --model M --effort E --tools "" --strict-mcp-config
      --setting-sources "" --system-prompt <系统提示> --output-format json
      （stateless / notes 加 --no-session-persistence；session 第一步 --session-id，之后 --resume）
stdin 接 /dev/null（否则 claude 会等 3 秒并打警告）。思考深度每次显式传。
"""
import json, os, pathlib, re, subprocess, time

FLAG_TEXT = 'safeguards flagged'


class Paused(Exception):
    """撞额度或连续调不通：停在两步之间，写 pause 后退出，之后用 resume 接着下。"""


def command(model, effort, system, session=None, new_session=False):
    cmd = ['claude', '-p', '--model', model, '--effort', effort, '--tools', '', '--strict-mcp-config',
           '--setting-sources', '', '--system-prompt', system, '--output-format', 'json']
    if session is None:
        cmd.append('--no-session-persistence')
    elif new_session:
        cmd += ['--session-id', session]
    else:
        cmd += ['--resume', session]
    return cmd


def shown(cmd):
    """记进 config 的命令行（系统提示换成占位）。"""
    parts = ['<系统提示>' if i and cmd[i - 1] == '--system-prompt' else x for i, x in enumerate(cmd)]
    return 'CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 ' + ' '.join(repr(x) if (x == '' or ' ' in x) else x for x in parts) + ' <用户提示>'


def version():
    try:
        return subprocess.run(['claude', '--version'], capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL).stdout.strip()
    except Exception as e:                       # 只是记进 config，拿不到不影响对局
        return '? (%s)' % e


def limit_hit(text):
    """撞额度的报错文字。只看 stderr 和结果正文，不看整段 JSON（JSON 的字段名里就有 usage，会误判）。"""
    t = (text or '').lower()
    return ('limit' in t and any(w in t for w in ('usage', 'reset', 'hit', 'reached', 'rate'))) or ' 429' in t


def flagged(d):
    """安全分类器拒答：claude 以 is_error、stop_reason=refusal 返回，正文是 "... safeguards flagged this message ..."
    （冒烟里见过 Details: [reasoning_extraction]）。这是模型那边的回复，不是调用失败，交给对局循环记 flag。"""
    return d.get('stop_reason') == 'refusal' or FLAG_TEXT in (d.get('result') or '')


def call(cmd, prompt, cwd, waits=(30, 120, 300), rebuild=None):
    """跑一次 claude -p。返回 (解析后的 JSON, 用时秒)。调不通按 waits 重试；撞额度抛 Paused。
    rebuild：每次重试前重新拼命令（新会话第一次调用超时时，会话可能已经建好，重试要改用 --resume）。"""
    env = dict(os.environ, CLAUDE_CODE_DISABLE_CLAUDE_MDS='1')
    last = None
    for n, wait in enumerate(tuple(waits) + (None,)):
        if n and rebuild:
            cmd = rebuild()
        t0 = time.time()
        try:
            p = subprocess.run(cmd + [prompt], cwd=cwd, env=env, capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, timeout=1800)
            out, err, rc = p.stdout, p.stderr, p.returncode
        except subprocess.TimeoutExpired:
            out, err, rc = '', 'timeout 1800s', -1
        dt = time.time() - t0
        try:
            d = json.loads(out)
        except ValueError:
            d = None
        if d is not None and ((rc == 0 and not d.get('is_error')) or flagged(d)):
            return d, dt
        last = {'rc': rc, 'stdout': out[-2000:], 'stderr': err[-2000:]}
        if limit_hit(err + ((d.get('result') or '') if d else out)) or (d and d.get('api_error_status') == 429):
            raise Paused('额度限制：%s' % (out + err)[-500:])
        if wait is None:
            break
        print('  调用失败（rc=%s），%d 秒后重试：%s' % (rc, wait, (err or out)[-200:].strip()), flush=True)
        time.sleep(wait)
    raise Paused('连续调不通：%s' % json.dumps(last, ensure_ascii=False)[-800:])


def usage(d):
    """用量展开（design.md P3）：output_tokens 已包含思考；输入总量 = in + cache_read + cache_write。
    token 字段是这一次调用自己的；cost（total_cost_usd）在 --resume 续接时却是整段会话的累计值，
    session 档由对局循环按会话做差（records.cost_delta），这里原样给出。"""
    u = d.get('usage') or {}
    out = u.get('output_tokens') or 0
    think = (u.get('output_tokens_details') or {}).get('thinking_tokens') or 0
    return {'in': u.get('input_tokens') or 0, 'cache_read': u.get('cache_read_input_tokens') or 0,
            'cache_write': u.get('cache_creation_input_tokens') or 0, 'out': out, 'think': think,
            'text_out': out - think, 'cost': d.get('total_cost_usd') or 0,
            'duration_ms': d.get('duration_ms'), 'ttft_ms': d.get('ttft_ms'), 'session_id': d.get('session_id'),
            'model': ','.join(sorted(d.get('modelUsage') or {})), 'stop_reason': d.get('stop_reason'),
            'api_error_status': d.get('api_error_status')}


def transcript_path(cwd, session):
    """claude 把会话记录存在 ~/.claude/projects/<运行目录，非字母数字都换成 -> /<会话 id>.jsonl。"""
    enc = re.sub(r'[^A-Za-z0-9]', '-', os.path.realpath(cwd))
    return pathlib.Path.home() / '.claude' / 'projects' / enc / ('%s.jsonl' % session)


def transcript_flags(cwd, session):
    """会话记录里提到安全分类器的用户消息（claude 拦截后自动插入的那条）。找不到记录返回 None。
    我们自己的提示里不会出现 safeguard / flagged，所以用户消息里出现就是 claude 插的。"""
    path = transcript_path(cwd, session)
    if not path.exists():
        return None
    hits = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get('type') != 'user':
            continue
        text = json.dumps((r.get('message') or {}).get('content'), ensure_ascii=False)
        if 'safeguard' in text.lower() or 'flagged' in text.lower():
            hits.append(text[:500])
    return hits
