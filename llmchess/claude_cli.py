"""调 `claude -p`：拼命令、调不通重试、撞额度等解除（或抛暂停）、用量展开、安全分类器拦截识别。

命令（design.md P1、P7）：
  CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 claude -p --model M --effort E --tools "" --strict-mcp-config
      --setting-sources "" --system-prompt <系统提示> --output-format json
      （stateless / notes 加 --no-session-persistence；session 第一步 --session-id，之后 --resume）
stdin 接 /dev/null（否则 claude 会等 3 秒并打警告）。思考深度每次显式传。
"""
import datetime, json, os, pathlib, re, signal, subprocess, threading, time

FLAG_TEXT = 'safeguards flagged'
TIMEOUT = 3600          # 单次调用的默认超时（秒）；第一批写死 1800，max 档撞了 7/120 次

# 撞额度时怎么办（design.md 第四节 limit_wait）。真正会卡的是 5 小时额度：agent 会被平台自动续跑，claude -p 子进程不会。
LIMIT_MODE = 'wait'           # 'wait'：在程序里等到解除再接着调（默认）；'pause'：旧行为，抛 Paused，退出码 3
LIMIT_BACKOFF = (600, 1800)   # 读不出解除时间时：首次等 10 分钟，之后每次翻倍，最多 30 分钟
LIMIT_MARGIN = 120            # 读出了解除时间时多等的余量（秒）
LIMIT_HORIZON = 8 * 86400     # 读出的解除时间离现在超过 8 天（或早于 5 分钟前）就当读错，按退避等
STOP = threading.Event()      # 停止信号：置位后在等的线程立刻醒来抛 Paused，也不再发起新调用
_now = time.time              # 测试里换成假时钟


def _wait(secs):
    """可被停止信号打断的等待；返回 True 表示被打断。测试里换成假的。"""
    return STOP.wait(secs)


def install_stop_handlers(on_stop=None, on_force=None):
    """Ctrl-C / SIGTERM：第一次只置 STOP——在等额度或等重试的线程马上醒来，写 pause 收尾，已在跑的调用答完为止
    （Ctrl-C 会连带终止同一进程组里的 claude 子进程，那次调用按失败记，不扣重试）；第二次立刻强退。
    on_stop()：第一次置 STOP 之后调（批量驱动用它把停止转告各盘子进程）；on_force()：给了就用它代替第二次的强退。
    只能在主线程调；返回一个恢复原处理函数的函数。"""
    STOP.clear()
    old = {}

    def handler(signum, frame):
        if STOP.is_set():
            if on_force is None:
                os._exit(128 + signum)
            on_force()
            return
        STOP.set()
        if on_stop is None:
            print('\n收到停止信号：不再发起新调用，等额度的线程马上收尾；再来一次强制退出', flush=True)
        else:
            on_stop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        old[sig] = signal.signal(sig, handler)

    def restore():
        for sig, h in old.items():
            signal.signal(sig, h)
    return restore


class Refused(Exception):
    """明确拒答：终止本盘，不允许自动重问或续跑。"""


class Paused(Exception):
    """撞额度（--on-limit pause）、连续调不通或收到停止信号：停在两步之间，写 pause 后退出，之后用 resume 接着下。"""


class ToolAttempt(Paused):
    """棋手尝试工具：暂停分析、锁住续跑，批次中也停止其他任务的新调用。"""


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


def refusal_text(text):
    """只认明确拦截标记或拒绝披露内部思考的句子；提到理由、思考本身不算。"""
    t = (text or '').lower().replace('’', "'")
    if any(mark in t for mark in ('safeguards flagged', '[reasoning_extraction]',
                                  'safety filter blocked the answer',
                                  'flagged by our safeguards',
                                  "unexpected codex item 'refusal'")):
        return True
    # CLI 常把后端元数据串进 stderr（有时同时写 empty answer），仍属明确拒答。
    if re.search(r"\b(?:stop_reason|finish_reason|finishreason)[\"']?\s*[:=]\s*[\"']?"
                 r"(?:refusal|content_filter|safety)\b", t):
        return True
    return bool(re.search(
        r"(?:i (?:cannot|can't|won't|am unable to)|i'm unable to)\s+"
        r"(?:provide|share|reveal|disclose|show)[^.!?\n]{0,100}"
        r"(?:chain[- ]of[- ]thought|hidden (?:reasoning|thoughts)|private (?:reasoning|thoughts)|internal reasoning)"
        r"|(?:不能|无法|不会|不便)(?:提供|分享|披露|展示|透露|公开)[^。！？\n]{0,50}"
        r"(?:思维链|内部推理|隐藏思考|内部思考|私密推理)", t))


def flagged(d):
    """各服务商明确拒答或安全拦截，调用层必须在任何重试之前交回。"""
    meta = d.get('meta') or {}
    return (any(x.get('stop_reason') == 'refusal'
                or str(x.get('finish_reason', '')).lower() in ('safety', 'refusal', 'content_filter')
                for x in (d, meta))
            or refusal_text(d.get('result')))


def tool_error_text(text):
    """只认包装器明确报告的工具事件；普通网络错误或正文提到工具不算。"""
    text = (text or '').lower()
    return any(mark in text for mark in (
        'the model called a tool; plain chat allows none',
        'the model used server-side tools (',
        'the answer carries annotations (web citations); plain chat allows no web access',
        'the model opened files that were not attached:',
        'agy soft-denied a tool and ended the turn',
        'agy called tools outside this preset:',
    )) or bool(re.search(r"unexpected codex item ['\"](?!refusal['\"])[^'\"]+['\"]; plain chat allows no tools", text))


def tool_used(d):
    """已解析响应中的明确工具证据（包含被拒绝的尝试）。不扫描可见正文作猜测。"""
    if not isinstance(d, dict):
        return False
    for obj in (d, d.get('meta')):
        if not isinstance(obj, dict):
            continue
        if obj.get('stop_reason') == 'tool_call' or any(obj.get(k) for k in (
                'tool_calls', 'denied_actions', 'permission_denials')):
            return True
        content = obj.get('content')
        if isinstance(content, list) and any(isinstance(item, dict) and item.get('type') in (
                'tool_use', 'server_tool_use') for item in content):
            return True
    return False


_MONTHS = {m: i + 1 for i, m in enumerate(('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'))}
_EPOCH = re.compile(r'(?<!\d)(1\d{9})(?!\d)')
_ISO = re.compile(r'(\d{4}-\d{2}-\d{2})[T ](\d{1,2}:\d{2}(?::\d{2})?)(?:\.\d+)?\s*(Z|[+-]\d{2}:?\d{2})?')
_IN = re.compile(r'resets?\s+in\s+(?:(\d+)\s*(?:h|hr|hrs|hours?)\b)?\s*(?:(\d+)\s*(?:m|min|mins|minutes?)\b)?', re.I)
_AT = re.compile(r'resets?\s+(?:at\s+|on\s+)?(?:([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(?:at\s+)?)?'
                 r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b\s*(?:\(([^)]+)\))?', re.I)


def _tz(name):
    if name:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(name.strip())
        except Exception:
            pass
    return datetime.datetime.now().astimezone().tzinfo      # 没写时区或认不出：按本机时区


def reset_time(text, now=None):
    """从撞额度的报错里读出解除时间（epoch 秒）；读不出、或读出的时间离谱，返回 None（调用方退回固定退避），从不抛错。
    认的写法（claude 的报错文字没有公开格式，这里尽量宽松）：10 位 epoch 秒（旧版「...limit reached|1727400000」）、
    ISO 时间（带或不带时区）、「resets in 2h 30m」、「resets 5am」「resets 5:30pm (Asia/Shanghai)」「resets Sep 27, 5am」
    「resets at 17:00」。只有钟点没有日期时，取今天这个钟点，已经过了就取明天。"""
    now = _now() if now is None else now
    try:
        t = None
        m = _EPOCH.search(text or '')
        if m:
            t = float(m[1])
        if t is None:
            m = _ISO.search(text or '')
            if m:
                tz = m[3]
                s = '%sT%s%s' % (m[1], m[2], '' if not tz else '+00:00' if tz == 'Z' else
                                 (tz if ':' in tz else tz[:3] + ':' + tz[3:]))
                d = datetime.datetime.fromisoformat(s)
                if d.tzinfo is None:
                    d = d.replace(tzinfo=_tz(None))
                t = d.timestamp()
        if t is None:
            m = _IN.search(text or '')
            if m and (m[1] or m[2]):
                t = now + int(m[1] or 0) * 3600 + int(m[2] or 0) * 60
        if t is None:
            m = _AT.search(text or '')
            if m and (m[5] or m[4] is not None or m[1]):       # 光一个数字不算（免得把「resets 3 times」之类当钟点）
                tz = _tz(m[6])
                base = datetime.datetime.fromtimestamp(now, tz)
                hour, minute = int(m[3]), int(m[4] or 0)
                if m[5]:
                    hour = hour % 12 + (12 if m[5].lower() == 'pm' else 0)
                if not (0 <= hour < 24 and 0 <= minute < 60):
                    return None
                if m[1]:
                    mon = _MONTHS.get(m[1].lower())
                    if mon is None:
                        return None
                    d = base.replace(month=mon, day=int(m[2]), hour=hour, minute=minute, second=0, microsecond=0)
                    if d.timestamp() < now - 86400:
                        d = d.replace(year=d.year + 1)
                else:
                    d = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if d.timestamp() < now - 60:
                        d += datetime.timedelta(days=1)
                t = d.timestamp()
        if t is None or not (now - 300 <= t <= now + LIMIT_HORIZON):
            return None
        return t
    except Exception:
        return None


def _iso(t):
    return datetime.datetime.fromtimestamp(t).astimezone().isoformat(timespec='seconds')


def call(cmd, prompt, cwd, waits=(30, 120, 300), rebuild=None, timeout=TIMEOUT, on_fail=None, on_wait=None, parse=None,
         run=None, refusal_check=None, fail_closed=False, on_start=None):
    """跑一次 claude -p。返回 (解析后的 JSON, 用时秒)。调不通按 waits 重试；撞额度见下。
    rebuild：每次重试前重新拼命令（新会话第一次调用超时时，会话可能已经建好，重试要改用 --resume）。
    timeout：单次调用的超时秒数。
    on_fail(info)：每次调用失败（超时、非零退出、回的不是 JSON）后、重试或抛 Paused 之前调一次，调用方用它把失败写进
    自己那盘 / 那题的记录。info = {try（第几次失败的调用，从 1 起）, timeout（是否超时）, rc, elapsed, stderr, stdout（各留末尾
    500 字）, next_wait（下次重试前等几秒，None 表示不再重试）}。
    撞额度：LIMIT_MODE 为 'pause' 时直接抛 Paused（旧行为）；默认 'wait'：从报错里读解除时间（reset_time），读得出就等到那时
    再加 LIMIT_MARGIN，读不出按 LIMIT_BACKOFF 退避，等完接着调同一次。这种等待不占 waits 里的重试次数，调用方的着法重试也
    不受影响（这一次调用还没返回）。每次等待前后各调一次 on_wait(info)：开始 {phase:'start', start, reset_at（读出的解除
    时间或 None）, planned（打算等几秒）, n（这次调用里第几次等）, reason（报错末尾）}；结束再加 {phase:'end', end, waited,
    stopped}。等待中收到停止信号（STOP）立刻醒来抛 Paused，和旧的撞额度暂停一样可以续跑。
    on_fail / on_wait 自己出错只打一行，不影响调用。
    parse(stdout)：把输出解析成 dict（认不出返回 None 或抛 ValueError）；不给就按 claude -p 的单个 JSON 读。
    codex exec 的棋手（codex_cli）借这一套重试和等额度，只换解析。
    refusal_check(d)：每次收到返回后、任何重试前检查 transcript，返回新拦截的原文列表。
    fail_closed：失败时结果可能已写进远端会话，记录完整 stdout/stderr 后立即暂停，不走重试或额度等待。
    仅 agy 后端（Gemini / agy 棋手）整盘调用启用；明确拒答仍优先返回拒答结果。
    on_start()：通过停止检查后、真正 dispatch 前持久记录调用；失败直接退出，不发送提示。
    run(cmd, prompt, cwd, env, timeout) -> (stdout, stderr, 退出码)：换掉「提示放在命令行最后一个参数」这种跑法，超时抛
    subprocess.TimeoutExpired。整盘走 llm-chat（chat.run）时用它：提示走 stdin，输出折成一个 JSON 串。"""
    env = dict(os.environ, CLAUDE_CODE_DISABLE_CLAUDE_MDS='1')
    last = None
    n = lim = calls = 0                        # n：失败次数（占 waits）；lim：撞额度等了几次；calls：总共调了几次
    waits = tuple(waits) + (None,)

    def notify(fn, info):
        if fn:
            try:
                fn(info)
            except Exception as e:               # 记录失败不能拖垮调用本身
                print('  （写记录时出错：%s）' % e, flush=True)
    while True:
        if STOP.is_set():
            raise Paused('收到停止信号，不再发起新调用')
        if calls and rebuild:
            cmd = rebuild()
        if on_start:
            on_start()
        calls += 1
        t0 = time.time()
        timed_out = False
        try:
            if run:
                out, err, rc = run(cmd, prompt, cwd, env, timeout)
            else:
                p = subprocess.run(cmd + [prompt], cwd=cwd, env=env, capture_output=True, text=True,
                                   stdin=subprocess.DEVNULL, timeout=timeout)
                out, err, rc = p.stdout, p.stderr, p.returncode
        except subprocess.TimeoutExpired as e:
            # 超时前已经返回的拒答证据不能丢，否则会把拒答当网络失败重问。
            out, err = e.output or '', e.stderr or ''
            out = out.decode('utf-8', errors='replace') if isinstance(out, bytes) else out
            err = err.decode('utf-8', errors='replace') if isinstance(err, bytes) else err
            err += '\ntimeout %ds' % timeout
            rc, timed_out = -1, True
        except (OSError, ValueError, TypeError) as e:
            if not fail_closed:
                raise
            out, err, rc = '', '%s: %s' % (type(e).__name__, e), -1
        dt = time.time() - t0
        if refusal_text(err) or (rc != 0 and refusal_text(out)):
            return {'result': out or err, 'stop_reason': 'refusal', 'is_error': True,
                    'refusal_evidence': {'stdout': out, 'stderr': err, 'rc': rc}}, dt
        try:
            d = parse(out) if parse else json.loads(out)
        except ValueError:
            d = None
        if fail_closed and not isinstance(d, dict):
            d = None
        if d is None and refusal_text(out):
            return {'result': out, 'stop_reason': 'refusal', 'is_error': True,
                    'refusal_evidence': {'stdout': out, 'stderr': err, 'rc': rc}}, dt
        hits = refusal_check(d) if refusal_check else None
        if hits:
            return dict(d or {}, stop_reason='refusal', is_error=True,
                        refusal_evidence={'stdout': out, 'stderr': err, 'rc': rc, 'transcript': hits}), dt
        if d is not None and flagged(d):
            return d, dt
        if tool_error_text(err) or (rc != 0 and tool_error_text(out)) or tool_used(d):
            return {'result': '', 'stop_reason': 'tool_call', 'is_error': True,
                    'tool_evidence': {'stdout': out, 'stderr': err, 'rc': rc}}, dt
        if d is not None and ((rc == 0 and not d.get('is_error')) or flagged(d)):
            return d, dt
        if fail_closed:
            # CLI 失败不证明后端没执行；额度错误也可能是恢复会话时重放的旧错误。
            info = {'try': calls, 'timeout': timed_out, 'rc': rc, 'elapsed': round(dt, 1),
                    'stderr': err, 'stdout': out, 'next_wait': None, 'outcome': 'uncertain'}
            notify(on_fail, info)
            raise Paused('会话调用结果不确定，禁止自动重发；请核验本地记录（%s）' % err[-500:])
        last = {'rc': rc, 'stdout': out[-2000:], 'stderr': err[-2000:]}
        text = err + ((d.get('result') or '') if d else out)
        if limit_hit(text) or (d and d.get('api_error_status') == 429):
            if LIMIT_MODE == 'pause':
                raise Paused('额度限制：%s' % (out + err)[-500:])
            now = _now()
            until = reset_time(text, now)
            planned = max(0.0, until - now) + LIMIT_MARGIN if until else \
                min(LIMIT_BACKOFF[0] * 2 ** lim, LIMIT_BACKOFF[1])
            lim += 1
            info = {'phase': 'start', 'start': _iso(now), 'reset_at': _iso(until) if until else None,
                    'planned': round(planned), 'n': lim, 'reason': text[-300:]}
            notify(on_wait, info)
            print('  撞额度，%s；等 %d 秒（到 %s）再接着调' % (
                '解除时间 %s' % info['reset_at'] if until else '读不出解除时间，按退避', planned, _iso(now + planned)),
                flush=True)
            stopped = _wait(planned)
            end = _now()
            notify(on_wait, dict(info, phase='end', end=_iso(end), waited=round(end - now), stopped=bool(stopped)))
            if stopped:
                raise Paused('等额度解除时收到停止信号（撞额度：%s）' % text[-300:])
            continue
        wait = waits[n]
        n += 1
        notify(on_fail, {'try': n, 'timeout': timed_out, 'rc': rc, 'elapsed': round(dt, 1),
                         'stderr': err[-500:], 'stdout': out[-500:], 'next_wait': wait})
        if wait is None or STOP.is_set():
            break
        print('  调用失败（rc=%s），%d 秒后重试：%s' % (rc, wait, (err or out)[-200:].strip()), flush=True)
        if _wait(wait):
            break
    if STOP.is_set():
        raise Paused('收到停止信号（最后一次调用失败：%s）' % json.dumps(last, ensure_ascii=False)[-300:])
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
    return transcript_flags_at(transcript_path(cwd, session))


def transcript_flags_at(path):
    """同 transcript_flags，直接给会话记录文件路径（llm-chat 的 Claude 会话用，见 chat.claude_transcript）。"""
    if path is None or not path.exists():
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
            hits.append(text)
    return hits
