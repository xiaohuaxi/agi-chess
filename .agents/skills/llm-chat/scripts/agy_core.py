#!/usr/bin/env python3
"""Dedicated agy (Antigravity CLI) ACP invocation for llm-chat: one turn over stdio JSON-RPC 2.0.

Standard library only (Python 3.9+ compatible).

Every turn runs as
    agy acp --agent llm-chat-session
without ``--dangerously-skip-permissions`` or ``--sandbox``, and passes
``mcpServers: []`` in ``session/new`` / ``session/resume``. Any permission
request (``session/request_permission``) is rejected synchronously before tool
execution (selecting an explicit reject option or cancelling and terminating the
child process group if none exists), turning the call into a loud ``AgyError``
so callers can halt immediately.
"""

import json
import os
import queue
import re
import selectors
import signal
import subprocess
import threading
import time
from pathlib import Path

AGY_BIN = "agy"
# Environment handed to agy. A whitelist (so unrelated secrets in the caller's
# environment, e.g. other providers' API keys or repository tokens, do not reach
# the agent) plus agy's own configuration variables. How agy authenticates is
# agy's business, not this script's: agy's settings.json decides (subscription
# login, `modelProvider: "gemini"` with GEMINI_API_KEY, Application Default
# Credentials via AGY_ADC_AUTH, an enterprise gateway via AGY_LLM_GATEWAY_*), and
# agy reads the secrets for those modes only from its environment, so they are
# passed through unchanged and never interpreted, logged or put on the command line.
ENV_KEEP = {
    "HOME", "PATH", "USER", "LOGNAME", "SHELL", "LANG", "TMPDIR", "TERM",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
}
AGY_OWN_ENV = {
    "GEMINI_API_KEY", "GOOGLE_GEMINI_BASE_URL", "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "CLOUDSDK_CONFIG",
}
AGY_OWN_PREFIXES = ("AGY_", "ANTIGRAVITY_")
# Values of passed-through variables with these name parts are scrubbed from any
# error text this module produces (stderr tails, agy's own error messages).
SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.I)
# agy writes this into the answer text when Gemini's safety filter blocks a reply.
FILTER_NOTICE = "This request was blocked by Gemini's filters"
REFUSAL_STOPS = frozenset({"refusal", "safety", "content_filter"})
NON_RECOVERABLE_STOPS = frozenset({"cancelled", "max_tokens", "max_turn_requests", "refusal"})
REFUSAL_MARKS = (
    "safeguards flagged",
    "[reasoning_extraction]",
    "safety filter blocked the answer",
    "flagged by our safeguards",
)
REFUSAL_META_RE = re.compile(
    r"\b(?:stop_reason|stopreason|finish_reason|finishreason)[\"']?\s*[:=]\s*[\"']?"
    r"(?:refusal|content_filter|safety)\b",
    re.I,
)
COT_REFUSAL_RE = re.compile(
    r"(?:i (?:cannot|can't|won't|am unable to)|i'm unable to)\s+"
    r"(?:provide|share|reveal|disclose|show)[^.!?\n]{0,100}"
    r"(?:chain[- ]of[- ]thought|hidden (?:reasoning|thoughts)|private (?:reasoning|thoughts)|internal reasoning)"
    r"|(?:不能|无法|不会|不便)(?:提供|分享|披露|展示|透露|公开)[^。！？\n]{0,50}"
    r"(?:思维链|内部推理|隐藏思考|内部思考|私密推理)",
    re.I,
)
PRINT_TIMEOUT_NOTICE = re.compile(r"print timeout after \S+ with turn in progress")
NO_OUTPUT_NOTICE = "no output produced"
AGY_ERROR_LINE = re.compile(r"AGY_ERROR:\s*(\{.*\})\s*$", re.M)
SESSION_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
# Tools the runtime may invoke internally without accessing files, commands, or web.
INTERNAL_TOOLS = frozenset({"manage_task", "finish"})
EFFORT_SUFFIXES = ("low", "medium", "high", "xhigh", "extra", "max")
STOP_GRACE = 5.0

PATH_PARAM_KEYS = (
    "Path",
    "AbsolutePath",
    "TargetFile",
    "NotebookPath",
    "DirectoryPath",
    "SearchPath",
    "SearchDirectory",
)

ACTION_TOOLS = {
    "read_file": ("read_file", "view_file", "list_dir", "grep_search", "find_by_name"),
    "write_file": ("write_file", "edit_file", "write_to_file", "replace_file_content",
                   "multi_replace_file_content", "notebook_edit"),
    "command": ("run_command",),
    "read_url": ("read_url_content",),
    "mcp": ("call_mcp_tool",),
}

# agy's permission rules live in these JSON files (CLI settings, settings shared
# with the desktop app, per-project settings). Only they can widen the
# workspace boundary that attachment-reading sessions rely on.
PERMISSION_FILES = ("~/.gemini/antigravity-cli/settings.json", "~/.gemini/config/config.json")
PERMISSION_GLOBS = ("~/.gemini/config/projects/*.json",)


class AgyError(Exception):
    """A user-facing failure. ``kind`` and ``source`` classify what failed.

    ``source`` values:
      - Transport (retryable up to caller cap): "hard_timeout", "print_timeout",
        "exit", "no_result", "status"
      - Non-retryable: "denied", "tool", "filtered", "refusal", "empty", "conversation",
        "config", "max_tokens", "max_turn_requests", "cancelled", "protocol",
        "missing_cli", "stop"
    """

    def __init__(self, message, kind="error", source=None):
        super().__init__(message)
        self.kind = kind
        self.source = source


class Cancelled(BaseException):
    """SIGINT/SIGTERM arrived; unwinds past normal error handling."""

    def __init__(self, signum):
        super().__init__(signum)
        self.signum = signum


def raise_cancelled(signum, _frame):
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal.SIG_IGN)
    raise Cancelled(signum)


def agy_bin():
    return os.environ.get("AGY_BIN") or AGY_BIN


def passed_through(name):
    return (name in ENV_KEEP or name in AGY_OWN_ENV or name.startswith("LC_")
            or name.startswith(AGY_OWN_PREFIXES))


def redact(text):
    """Replace the value of every secret-looking variable handed to agy with [REDACTED]."""
    text = str(text)
    for name, value in os.environ.items():
        if value and len(value) >= 8 and SECRET_NAME.search(name) and passed_through(name):
            text = text.replace(value, "[REDACTED]")
    return text


def clip(text, limit=1500):
    # Redact the full text first: cutting first could leave a secret's tail behind.
    text = redact(text)
    return text if len(text) <= limit else "..." + text[-limit:]


def clip_head_tail(text, limit=1000):
    """Redact first, then preserve both head and tail so refusal phrases at either end survive."""
    text = redact(text)
    if len(text) <= limit:
        return text
    half = max(1, (limit - 5) // 2)
    return text[:half] + " ... " + text[-half:]


def _has_refusal_marker(text):
    """Check raw text for refusal markers before any truncation or redaction."""
    if not text:
        return False
    low = str(text).lower().replace("\u2019", "'")
    if any(mark in low for mark in REFUSAL_MARKS):
        return True
    if REFUSAL_META_RE.search(low):
        return True
    return bool(COT_REFUSAL_RE.search(low))


def _find_refusal_snippet(text):
    """Extract a short diagnostic snippet around a refusal match from ALREADY-REDACTED text.

    Full-text ``redact()`` MUST run before slicing ``[lo:hi]`` so a secret value
    straddling the 40-char slice boundary can never be cut in half and leaked.
    """
    if not text:
        return ""
    raw = redact(text)
    norm = raw.lower().replace("\u2019", "'")
    span = None
    for mark in REFUSAL_MARKS:
        idx = norm.find(mark)
        if idx >= 0:
            span = (idx, idx + len(mark))
            break
    if span is None:
        m = REFUSAL_META_RE.search(norm) or COT_REFUSAL_RE.search(norm)
        if m is not None:
            span = m.span()
    if span is None:
        return ""
    lo = max(0, span[0] - 40)
    hi = min(len(raw), span[1] + 40)
    return raw[lo:hi].strip()


def _stop_error_source(stop_str):
    """Map non-end_turn stop reasons to non-retryable sources when appropriate."""
    s = str(stop_str or "").strip().lower()
    if s == "max_tokens":
        return "max_tokens"
    if s == "cancelled":
        return "cancelled"
    if s == "max_turn_requests":
        return "max_turn_requests"
    return "status"


def _select_reject_option_id(options):
    """Pick an explicit rejection optionId from ACP request_permission options, or None.

    Only explicit ACP rejection kinds (``reject_once``, ``reject_always``) are accepted;
    any missing, allow-flavored, or unknown ``kind`` returns ``None`` so the caller falls
    back to ACP ``cancelled`` + child-group termination.
    """
    if not isinstance(options, list):
        return None
    valid = []
    for opt in options:
        if not isinstance(opt, dict):
            continue
        oid = opt.get("optionId")
        kind = opt.get("kind")
        if not isinstance(oid, str) or not oid.strip():
            continue
        if not isinstance(kind, str) or not kind.strip():
            continue
        k_low = kind.strip().lower()
        o_low = oid.strip().lower()
        if "allow" in k_low or "allow" in o_low:
            continue
        valid.append((oid, k_low))
    for target in ("reject_once", "reject_always"):
        for oid, k_low in valid:
            if k_low == target:
                return oid
    return None


def agy_env(extra=None):
    env = {k: v for k, v in os.environ.items() if passed_through(k)}
    env.update(extra or {})
    return env


# ---------------------------------------------------------------- agent files

def agent_markdown(name, description, tools, inherit, body):
    """Markdown custom agent as agy reads it (frontmatter + system prompt body).

    inherit=False also sets excludeDefaultComponents, which drops agy's default
    prompt sections (AGENTS.md / GEMINI.md / skills).
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ValueError(f"bad agent name {name!r}")
    lines = [
        "---",
        f"name: {name}",
        "description: " + json.dumps(description),
        "inheritCustomizations: " + ("true" if inherit else "false"),
        "excludeDefaultComponents: " + ("false" if inherit else "true"),
        "subagent: false",
        "tools: [" + ", ".join(tools) + "]",
        "---",
        body.rstrip("\n"),
        "",
    ]
    return "\n".join(lines)


def parse_agent_frontmatter(text):
    """Minimal reader for the frontmatter written by agent_markdown (tests, checks)."""
    if not text.startswith("---\n"):
        raise ValueError("no frontmatter")
    head = text[4:].split("\n---\n", 1)[0]
    out = {}
    for line in head.splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            out[key.strip()] = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",") if v.strip()]
        elif value in ("true", "false"):
            out[key.strip()] = value == "true"
        else:
            out[key.strip()] = value.strip('"')
    return out


# ---------------------------------------------------------------- process

def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def stop_group(proc, grace=STOP_GRACE):
    """SIGINT first, then SIGTERM, then SIGKILL; reap process group cleanly."""
    pgid = proc.pid
    for sig, wait in ((signal.SIGINT, grace), (signal.SIGTERM, 3.0), (signal.SIGKILL, 5.0)):
        if proc.poll() is not None and not group_alive(pgid):
            break
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            pass
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if proc.poll() is not None and not group_alive(pgid):
                break
            time.sleep(0.05)
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    if group_alive(pgid):
        raise AgyError(f"could not stop agy process group {pgid}", source="stop")


class signals_ignored:
    """Ignore SIGINT/SIGTERM inside the block (main thread only); restore afterwards."""

    def __enter__(self):
        self.saved = {}
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self.saved[sig] = signal.signal(sig, signal.SIG_IGN)
            except ValueError:  # not the main thread
                pass
        return self

    def __exit__(self, *exc):
        for sig, handler in self.saved.items():
            signal.signal(sig, handler)


class signals_held:
    """Hold SIGINT/SIGTERM inside the block; release() re-raises what arrived (main thread only)."""

    def __enter__(self):
        self.saved, self.pending = {}, []
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self.saved[sig] = signal.signal(sig, lambda signum, _frame: self.pending.append(signum))
            except ValueError:  # not the main thread
                pass
        return self

    def __exit__(self, *exc):
        for sig, handler in self.saved.items():
            signal.signal(sig, handler)

    def release(self):
        pending, self.pending = self.pending, []
        for sig in dict.fromkeys(pending):
            signal.raise_signal(sig)


def build_command(agent, add_dirs=(), extra_flags=(), **_unused):
    """Build the ``agy acp`` command. Never adds --dangerously-skip-permissions or --sandbox."""
    cmd = [agy_bin(), "acp", "--agent", agent]
    for d in add_dirs:
        cmd += ["--add-dir", str(d)]
    cmd += list(extra_flags)
    return cmd


# ---------------------------------------------------------------- ACP helpers

def tool_path(call):
    """Extract a file or directory path argument from a tool call, or '' if absent."""
    params = call.get("parameters") or {}
    for key in PATH_PARAM_KEYS:
        val = params.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def tool_target(call):
    path = tool_path(call)
    if path:
        return path
    params = call.get("parameters") or {}
    for key in ("Url", "CommandLine", "query", "Query"):
        if params.get(key):
            return str(params[key])
    return json.dumps(params, ensure_ascii=False)[:200] if params else ""


def _config_entry(config_options, cid):
    for item in config_options or ():
        if isinstance(item, dict) and item.get("id") == cid:
            return item
    return None


def _option_values(entry):
    if not isinstance(entry, dict):
        return []
    return [o.get("value") for o in (entry.get("options") or ())
            if isinstance(o, dict) and isinstance(o.get("value"), str) and o.get("value")]


def match_acp_model(requested_model, available_models):
    """Resolve ``requested_model`` against ACP ``model`` configOptions.

    Returns ``(target_model, implied_effort)`` or raises ``AgyError(kind="config", source="config")``.
    """
    if not requested_model:
        return None, None
    req = requested_model.strip().lower()
    if not available_models:
        raise AgyError("agy ACP returned an empty model list", kind="config", source="config")
    exact = [m for m in available_models if m.lower() == req]
    if len(exact) == 1:
        return exact[0], None
    base, sep, suffix = req.rpartition("-")
    if sep and base and suffix in EFFORT_SUFFIXES:
        exact_base = [m for m in available_models if m.lower() == base]
        if len(exact_base) == 1:
            return exact_base[0], suffix
    raise AgyError(
        f"unknown agy model {requested_model!r} (available: {', '.join(available_models)})",
        kind="config",
        source="config",
    )


def match_acp_effort(target_model, effort, implied_effort, config_options):
    """Resolve effort against ACP ``thought_level`` configOptions.

    Supports both independent ``thought_level`` models (e.g. ``gemini-4-carbon`` + ``high``)
    and fixed-effort model slugs with no ``thought_level`` option when the resolved model ID
    ends with ``-<effort>`` (e.g. ``gpt-oss-120b-medium`` + ``--effort medium``).
    Returns the ``thought_level`` string to apply, or ``None`` when no ``thought_level``
    update should be sent.
    """
    if effort and implied_effort:
        norm_e = "xhigh" if effort.lower() == "extra" else effort.lower()
        norm_i = "xhigh" if implied_effort.lower() == "extra" else implied_effort.lower()
        if norm_e != norm_i:
            raise AgyError(
                f"agy model {target_model!r} suffix effort {implied_effort!r} conflicts with --effort {effort!r}",
                kind="config",
                source="config",
            )
    desired = (effort or implied_effort or "").strip().lower() or None
    tl_entry = _config_entry(config_options, "thought_level")
    tl_values = _option_values(tl_entry)
    if not tl_values:
        if desired is None:
            return None
        if target_model and target_model.lower().endswith(f"-{desired}"):
            return None
        raise AgyError(
            f"agy model {target_model or '<default>'!r} does not support --effort {desired!r}",
            kind="config",
            source="config",
        )
    if desired is None:
        return None
    candidate = desired
    if candidate == "extra" and "xhigh" in tl_values:
        candidate = "xhigh"
    elif candidate == "xhigh" and "extra" in tl_values and "xhigh" not in tl_values:
        candidate = "extra"
    if candidate not in tl_values:
        raise AgyError(
            f"agy model {target_model or '<default>'!r} does not accept --effort {desired!r} "
            f"(available: {', '.join(tl_values)})",
            kind="config",
            source="config",
        )
    return candidate


def _convert_acp_usage(raw_usage):
    """Convert ACP ``session/prompt`` ``result.usage`` to llm-chat per-turn usage.

    In ``agy 1.5.8 acp``, ``inputTokens`` is uncached input only and ``totalTokens ==
    inputTokens + cachedReadTokens + cachedWriteTokens + outputTokens`` (with
    ``thoughtTokens`` already included inside ``outputTokens``). ``agi_chess/chat.py``
    subtracts ``cache_read`` from ``input_tokens`` for ``agy``, so ``input_tokens`` here
    must report ``inputTokens + (cachedReadTokens or 0)`` while keeping
    ``cache_read_tokens`` and ``cache_write_tokens`` separately (``None`` when unreported).
    """
    if not isinstance(raw_usage, dict):
        return {}

    def _as_int(val):
        return int(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else None

    uncached_in = _as_int(raw_usage.get("inputTokens"))
    cached_read = _as_int(raw_usage.get("cachedReadTokens"))
    cached_write = _as_int(raw_usage.get("cachedWriteTokens"))
    total_in = (uncached_in + (cached_read or 0)) if uncached_in is not None else None
    return {
        "input_tokens": total_in,
        "cache_read_tokens": cached_read,
        "cache_write_tokens": cached_write,
        "output_tokens": _as_int(raw_usage.get("outputTokens")),
        "thinking_tokens": _as_int(raw_usage.get("thoughtTokens")),
    }


# ---------------------------------------------------------------- ACP turn execution

def turn(agent, prompt, cwd, *, allowed_tools, model=None, effort=None, conversation=None,
         add_dirs=(), extra_flags=(), timeout=600.0, env=None, accept_recovered=False):
    """Run one turn over ``agy acp`` stdio JSON-RPC 2.0 and validate every tool/filter invariant."""
    cmd = build_command(agent, add_dirs=add_dirs, extra_flags=extra_flags)
    started = time.monotonic()
    timeout_s = max(1.0, float(timeout))
    deadline = started + timeout_s
    allowed_set = set(allowed_tools) | INTERNAL_TOOLS

    proc = None
    stdin_fd = None
    events = queue.Queue()
    stderr_lines = []
    stderr_lock = threading.Lock()
    timed_out = threading.Event()
    t_out = None
    t_err = None
    watchdog = None

    text_chunks = []
    tools_by_id = {}
    denied_calls = []
    drained_extra_texts = []
    drained_edatas = []
    drained_stop_reasons = []
    emergency_kill = False

    def err_full():
        with stderr_lock:
            return "".join(stderr_lines)

    def err_tail(limit=800):
        raw = err_full().strip()
        return clip(raw, limit) if raw else ""

    def tool_calls_list():
        return list(tools_by_id.values())

    def with_streamed(base_msg):
        streamed_now = "".join(text_chunks).strip()
        if not streamed_now:
            return base_msg
        return f"{base_msg}; streamed: {clip_head_tail(streamed_now, 1000)}"

    def check_tool_and_denial():
        if denied_calls:
            desc = "; ".join(f"{c.get('name')} {tool_target(c)}".strip() for c in denied_calls)
            raise AgyError(
                "agy soft-denied a tool and ended the turn (headless mode cannot ask): attempted: " + desc,
                kind="permission",
                source="denied",
            )
        bad = [c for c in tool_calls_list() if c.get("name") not in allowed_set]
        if bad:
            raise AgyError(
                "agy called tools outside this preset: "
                + "; ".join(f"{c.get('name')} {tool_target(c)}".strip() for c in bad),
                kind="tool",
                source="tool",
            )

    def check_filter_and_refusal(*extra_texts, stop_reason=None, edata=None):
        streamed_now = "".join(text_chunks)
        texts = [streamed_now] + [str(t) for t in extra_texts if t]
        sample = streamed_now.strip() or next((str(t).strip() for t in extra_texts if t and str(t).strip()), "")
        if any(FILTER_NOTICE in t for t in texts):
            clipped = clip_head_tail(sample, 800)
            if FILTER_NOTICE not in clipped:
                clipped = (clipped + f" [matched: {FILTER_NOTICE}]").strip()
            raise AgyError(
                "Gemini's safety filter blocked the answer (agy wrote its notice into the reply): "
                + clipped,
                kind="filtered",
                source="filtered",
            )
        is_refusal_stop = str(stop_reason or "").strip().lower() in REFUSAL_STOPS
        if not is_refusal_stop and isinstance(edata, dict):
            is_refusal_stop = any(
                str(edata.get(k) or "").strip().lower() in REFUSAL_STOPS
                for k in ("stopReason", "stop_reason", "finishReason", "finish_reason", "status", "reason")
            )
        has_marker = any(_has_refusal_marker(t) for t in texts)
        matched_snip = next((s for s in (_find_refusal_snippet(t) for t in texts) if s), "") if has_marker else ""
        if is_refusal_stop or has_marker:
            clipped = clip_head_tail(sample, 800) if sample else ""
            if clipped:
                if matched_snip and matched_snip not in clipped:
                    suffix = f": {clipped} [matched: {matched_snip}]"
                else:
                    suffix = f": {clipped}"
            elif matched_snip:
                suffix = f": {matched_snip}"
            else:
                suffix = ""
            raise AgyError(
                "agy refused the turn (stop_reason=refusal)" + suffix,
                kind="refusal",
                source="refusal",
            )

    def record_server_event(msg):
        """Pure state update for server notifications/requests (no RPC writes)."""
        if "id" in msg and "method" in msg:
            method = msg.get("method")
            if method == "session/request_permission":
                params = msg.get("params") or {}
                opts = params.get("options") or []
                rej_id = _select_reject_option_id(opts)
                tc = params.get("toolCall") or {}
                t_name = tc.get("name") or tc.get("title") or "unknown_tool"
                t_args = {}
                if isinstance(tc.get("rawInput"), dict):
                    t_args.update(tc["rawInput"])
                if isinstance(tc.get("args"), dict):
                    t_args.update(tc["args"])
                denied_calls.append({"name": t_name, "parameters": t_args})
                return ("permission", msg["id"], rej_id)
            return ("unsupported", msg["id"], method)

        if msg.get("method") == "session/update":
            upd = (msg.get("params") or {}).get("update") or {}
            st = upd.get("sessionUpdate")
            if st == "agent_message_chunk":
                content = upd.get("content")
                if isinstance(content, dict) and content.get("type") == "text":
                    text_chunks.append(content.get("text") or "")
            elif st in ("tool_call", "tool_call_update"):
                tc_id = upd.get("toolCallId") or f"anon_{len(tools_by_id)}"
                entry = tools_by_id.setdefault(tc_id, {"name": None, "parameters": {}, "state": None})
                if upd.get("name") or upd.get("title"):
                    entry["name"] = upd.get("name") or entry["name"] or upd.get("title")
                merged_in = {}
                if isinstance(upd.get("rawInput"), dict):
                    merged_in.update(upd["rawInput"])
                if isinstance(upd.get("args"), dict):
                    merged_in.update(upd["args"])
                if merged_in:
                    merged = dict(entry["parameters"])
                    merged.update(merged_in)
                    entry["parameters"] = merged
                if upd.get("status"):
                    entry["state"] = upd["status"]
        return None

    def _record_drained_rpc_response(msg):
        """Capture RPC result/error payloads seen during offline queue draining for security audit."""
        res_obj = msg.get("result")
        if isinstance(res_obj, dict):
            drained_edatas.append(res_obj)
            sr = str(res_obj.get("stopReason") or res_obj.get("stop_reason") or "").strip()
            if sr:
                drained_stop_reasons.append(sr)
            if isinstance(res_obj.get("response"), str) and res_obj["response"]:
                drained_extra_texts.append(res_obj["response"])
            if res_obj.get("error"):
                drained_extra_texts.append(str(res_obj["error"]))
        err_obj = msg.get("error")
        if err_obj is not None:
            if isinstance(err_obj, dict):
                emsg = err_obj.get("message") or json.dumps(err_obj, ensure_ascii=False)
                ed = err_obj.get("data")
                full_e = f"{emsg} ({json.dumps(ed, ensure_ascii=False)})" if ed is not None else str(emsg)
                drained_extra_texts.append(full_e)
                if isinstance(ed, dict):
                    drained_edatas.append(ed)
                    if isinstance(ed.get("response"), str) and ed["response"]:
                        drained_extra_texts.append(ed["response"])
                    es = str(ed.get("stopReason") or ed.get("stop_reason") or ed.get("status") or "").strip()
                    if es:
                        drained_stop_reasons.append(es)
            else:
                drained_extra_texts.append(str(err_obj))

    def _drain_events_for_audit(stop_and_join=False):
        """Stop child group (when requested), converge readers, and audit all queued stdout events."""
        nonlocal emergency_kill
        readers_converged = True
        if stop_and_join:
            if proc is not None:
                with signals_ignored():
                    stop_group(proc, grace=0.05 if emergency_kill else STOP_GRACE)
            if t_out is not None and t_out is not threading.current_thread():
                t_out.join(timeout=1.0)
                if t_out.is_alive():
                    readers_converged = False
            if t_err is not None and t_err is not threading.current_thread():
                t_err.join(timeout=1.0)
        while True:
            try:
                ev_type, payload = events.get_nowait()
            except queue.Empty:
                break
            if ev_type != "stdout" or not payload:
                continue
            line = payload.strip()
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if "method" in msg:
                act = record_server_event(msg)
                if act and act[0] == "permission" and act[2] is None:
                    emergency_kill = True
            else:
                _record_drained_rpc_response(msg)
        return readers_converged

    def _audit_after_drain(ef):
        check_tool_and_denial()
        for sr in drained_stop_reasons:
            check_filter_and_refusal(*drained_extra_texts, ef, stop_reason=sr)
        for ed in drained_edatas:
            check_filter_and_refusal(*drained_extra_texts, ef, edata=ed)
        check_filter_and_refusal(*drained_extra_texts, ef)
        for sr in drained_stop_reasons:
            src = _stop_error_source(sr)
            if src != "status":
                raise AgyError(
                    with_streamed(f"agy stopReason {sr} before completion"),
                    kind="error",
                    source=src,
                )

    def raise_timeout():
        converged = _drain_events_for_audit(stop_and_join=True)
        ef = err_full()
        _audit_after_drain(ef)
        if not converged:
            raise AgyError(
                with_streamed("agy timed out and stdout reader did not converge after stopping child"),
                kind="error",
                source="stop",
            )
        if PRINT_TIMEOUT_NOTICE.search(ef):
            raise AgyError(
                with_streamed(
                    f"agy hit --print-timeout with the turn still running; partial output discarded "
                    f"({len(''.join(text_chunks))} chars)"
                ),
                kind="timeout",
                source="print_timeout",
            )
        raise AgyError(
            with_streamed(f"agy did not finish within {timeout_s:.0f}s; killed"),
            kind="timeout",
            source="hard_timeout",
        )

    def _fail_stdin_protocol(reason):
        _drain_events_for_audit(stop_and_join=True)
        _audit_after_drain(err_full())
        raise AgyError(with_streamed(reason), kind="error", source="protocol")

    def send_rpc(payload):
        if stdin_fd is None:
            return
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        view = memoryview(data)
        sent = 0
        total = len(data)
        try:
            sel = selectors.DefaultSelector()
        except OSError as exc:
            _fail_stdin_protocol(f"agy stdin selector init failed: {exc}")
        with sel:
            try:
                sel.register(stdin_fd, selectors.EVENT_WRITE)
            except (OSError, ValueError) as exc:
                if proc.poll() is not None:
                    return
                _fail_stdin_protocol(f"agy stdin register failed: {exc}")
            while sent < total:
                remaining = deadline - time.monotonic()
                if timed_out.is_set() or remaining <= 0:
                    raise_timeout()
                if proc.poll() is not None:
                    break
                try:
                    ready = sel.select(timeout=min(0.2, max(0.01, remaining)))
                except InterruptedError:
                    continue
                except (OSError, ValueError) as exc:
                    if proc.poll() is not None:
                        break
                    _fail_stdin_protocol(f"agy stdin poll failed: {exc}")
                if not ready:
                    continue
                try:
                    n = os.write(stdin_fd, view[sent:])
                except (BlockingIOError, InterruptedError):
                    continue
                except BrokenPipeError:
                    break
                except OSError as exc:
                    if proc.poll() is not None:
                        break
                    _fail_stdin_protocol(f"agy stdin write failed: {exc}")
                if n == 0:
                    if proc.poll() is not None:
                        break
                    _fail_stdin_protocol("agy stdin write returned 0 bytes")
                sent += n

    def handle_server_message(msg):
        act = record_server_event(msg)
        if act is None:
            return
        kind_act, msg_id, extra = act
        if kind_act == "permission":
            if extra is not None:
                send_rpc({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"outcome": {"outcome": "selected", "optionId": extra}},
                })
            else:
                nonlocal emergency_kill
                emergency_kill = True
                send_rpc({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"outcome": {"outcome": "cancelled"}},
                })
                check_tool_and_denial()
        else:
            send_rpc({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not supported in llm-chat: {extra}"},
            })

    def rpc_call(req_id, method, params):
        send_rpc({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        while True:
            remaining = deadline - time.monotonic()
            if timed_out.is_set() or remaining <= 0:
                raise_timeout()
            try:
                ev_type, payload = events.get(timeout=min(1.0, max(0.05, remaining)))
            except queue.Empty:
                continue
            if ev_type == "timeout":
                raise_timeout()
            if ev_type == "eof":
                if t_out is not None and t_out is not threading.current_thread():
                    t_out.join(timeout=0.3)
                if t_err is not None:
                    t_err.join(timeout=0.3)
                try:
                    proc.wait(timeout=0.3)
                except subprocess.TimeoutExpired:
                    pass
                _drain_events_for_audit(stop_and_join=False)
                ef = err_full()
                _audit_after_drain(ef)
                if PRINT_TIMEOUT_NOTICE.search(ef):
                    raise AgyError(
                        with_streamed(
                            f"agy hit --print-timeout with the turn still running; partial output discarded "
                            f"({len(''.join(text_chunks))} chars)"
                        ),
                        kind="timeout",
                        source="print_timeout",
                    )
                rc = proc.returncode
                if rc not in (0, None):
                    match = AGY_ERROR_LINE.search(ef)
                    detail = match.group(1) if match else (err_tail() or "".join(text_chunks)[-800:])
                    raise AgyError(
                        with_streamed(f"agy exited {rc}: {clip(detail)}"),
                        kind="api" if rc == 3 else "error",
                        source="exit",
                    )
                raise AgyError(
                    with_streamed(f"agy produced no result for {method}: {err_tail() or clip(''.join(text_chunks))}"),
                    kind="error",
                    source="no_result",
                )
            if ev_type == "stdout":
                line = payload.strip()
                if not line.startswith("{"):
                    continue
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                if "method" in msg:
                    handle_server_message(msg)
                    continue
                if msg.get("id") == req_id:
                    return msg

    def unwrap_rpc(resp_msg, method):
        if method == "session/prompt":
            check_tool_and_denial()
        if "error" in resp_msg and resp_msg["error"] is not None:
            err_obj = resp_msg["error"]
            if isinstance(err_obj, dict):
                code = err_obj.get("code")
                emsg = err_obj.get("message") or json.dumps(err_obj, ensure_ascii=False)
                edata = err_obj.get("data")
            else:
                code, emsg, edata = None, str(err_obj), None
            full_err = f"{emsg} ({json.dumps(edata, ensure_ascii=False)})" if edata is not None else str(emsg)
            edata_resp = (
                edata.get("response")
                if isinstance(edata, dict) and isinstance(edata.get("response"), str)
                else ""
            )
            check_filter_and_refusal(full_err, edata_resp, err_full(), edata=edata)
            if method == "session/set_config_option" and code in (-32600, -32602):
                raise AgyError(
                    with_streamed(f"agy rejected config option: {clip(full_err)}"),
                    kind="config",
                    source="config",
                )
            if method == "session/resume" and (
                code in (-32600, -32602)
                or re.search(r"(session|conversation).*(not found|invalid|unknown|missing)", full_err, re.I)
            ):
                raise AgyError(
                    with_streamed(f"agy could not resume conversation {conversation}: {clip(full_err)}"),
                    kind="error",
                    source="conversation",
                )
            if method == "session/prompt" and isinstance(edata, dict):
                edata_status = str(edata.get("stopReason") or edata.get("stop_reason") or edata.get("status") or "").strip()
                edata_src = _stop_error_source(edata_status)
                if edata_src != "status":
                    raise AgyError(
                        with_streamed(f"agy RPC error ({method} {code}, stopReason={edata_status}): {clip(full_err)}"),
                        kind="error",
                        source=edata_src,
                    )
                if accept_recovered and edata_resp.strip():
                    rec_status = edata_status or "ERROR"
                    streamed_strip = "".join(text_chunks).strip()
                    if rec_status not in NON_RECOVERABLE_STOPS:
                        if streamed_strip and streamed_strip != edata_resp.strip():
                            raise AgyError(
                                with_streamed("agy streamed text disagrees with final response"),
                                kind="error",
                                source="protocol",
                            )
                        return {
                            "stopReason": rec_status,
                            "response": edata_resp,
                            "error": full_err,
                            "usage": edata.get("usage") or {},
                        }
            raise AgyError(
                with_streamed(f"agy RPC error ({method} {code}): {clip(full_err)}"),
                kind="error",
                source="status",
            )
        res = resp_msg.get("result")
        return res if isinstance(res, dict) else {}

    held = signals_held()
    try:
        with held:
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=str(cwd),
                    env=env if env is not None else agy_env(),
                    start_new_session=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
            except FileNotFoundError:
                pass
        held.release()
        if proc is None:
            raise AgyError(f"{cmd[0]} CLI not found in PATH (Antigravity CLI)", source="missing_cli")
        stdin_fd = proc.stdin.fileno()
        os.set_blocking(stdin_fd, False)

        def _stdout_reader():
            try:
                for line in proc.stdout:
                    events.put(("stdout", line))
            except ValueError:
                pass
            finally:
                events.put(("eof", None))

        def _stderr_reader():
            try:
                for line in proc.stderr:
                    with stderr_lock:
                        stderr_lines.append(line)
                        if len(stderr_lines) > 400:
                            del stderr_lines[:200]
            except ValueError:
                pass

        t_out = threading.Thread(target=_stdout_reader, daemon=True)
        t_err = threading.Thread(target=_stderr_reader, daemon=True)
        t_out.start()
        t_err.start()

        def _on_timeout():
            timed_out.set()
            events.put(("timeout", None))
            if proc is not None and proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGINT)
                except (ProcessLookupError, PermissionError):
                    pass

        watchdog = threading.Timer(timeout_s, _on_timeout)
        watchdog.daemon = True
        watchdog.start()

        next_id = 1
        unwrap_rpc(
            rpc_call(next_id, "initialize", {"protocolVersion": 1, "clientInfo": {"name": "llm-chat", "version": "2.0"}}),
            "initialize",
        )
        next_id += 1

        if conversation:
            sess_res = unwrap_rpc(
                rpc_call(next_id, "session/resume", {"sessionId": conversation, "cwd": str(cwd), "mcpServers": []}),
                "session/resume",
            )
        else:
            sess_res = unwrap_rpc(
                rpc_call(next_id, "session/new", {"cwd": str(cwd), "mcpServers": []}),
                "session/new",
            )
        next_id += 1

        sid = sess_res.get("sessionId")
        if not isinstance(sid, str) or not sid.strip():
            raise AgyError("agy did not report a conversation id", source="conversation")
        if conversation and sid != conversation:
            raise AgyError(f"agy answered in conversation {sid}, not {conversation}", source="conversation")
        if not conversation and not SESSION_UUID_RE.match(sid):
            raise AgyError(f"agy reported invalid sessionId {sid!r}", source="conversation")

        config_options = sess_res.get("configOptions") or []
        model_entry = _config_entry(config_options, "model")
        available_models = _option_values(model_entry)
        current_model = model_entry.get("currentValue") if isinstance(model_entry, dict) else None

        target_model, implied_effort = match_acp_model(model, available_models) if model else (current_model, None)
        if target_model and target_model != current_model:
            cfg_res = unwrap_rpc(
                rpc_call(
                    next_id,
                    "session/set_config_option",
                    {"sessionId": sid, "configId": "model", "value": target_model},
                ),
                "session/set_config_option",
            )
            next_id += 1
            config_options = cfg_res.get("configOptions") or config_options
            model_entry = _config_entry(config_options, "model")
            current_model = (model_entry.get("currentValue") if isinstance(model_entry, dict) else None) or target_model

        resolved_model = target_model or current_model or model
        effective_effort = match_acp_effort(resolved_model, effort, implied_effort, config_options)
        if effective_effort is not None:
            tl_entry = _config_entry(config_options, "thought_level")
            current_tl = tl_entry.get("currentValue") if isinstance(tl_entry, dict) else None
            if effective_effort != current_tl:
                cfg_res = unwrap_rpc(
                    rpc_call(
                        next_id,
                        "session/set_config_option",
                        {"sessionId": sid, "configId": "thought_level", "value": effective_effort},
                    ),
                    "session/set_config_option",
                )
                next_id += 1
                config_options = cfg_res.get("configOptions") or config_options

        prompt_res = unwrap_rpc(
            rpc_call(
                next_id,
                "session/prompt",
                {"sessionId": sid, "prompt": [{"type": "text", "text": prompt}]},
            ),
            "session/prompt",
        )
        check_tool_and_denial()

        stop_reason = prompt_res.get("stopReason")
        streamed = "".join(text_chunks)
        raw_res_resp = prompt_res.get("response") if isinstance(prompt_res.get("response"), str) else ""
        check_filter_and_refusal(raw_res_resp, prompt_res.get("error"), err_full(), stop_reason=stop_reason, edata=prompt_res)

        streamed_strip = streamed.strip()
        res_strip = raw_res_resp.strip()
        recovered = None

        if stop_reason in ("end_turn", None):
            if streamed_strip and res_strip and streamed_strip != res_strip:
                raise AgyError(
                    with_streamed("agy streamed text disagrees with final response"),
                    kind="error",
                    source="protocol",
                )
            response = streamed if streamed_strip else raw_res_resp
        else:
            stop_str = str(stop_reason).strip()
            if stop_str == "max_tokens":
                raise AgyError(
                    with_streamed("agy truncated the answer (stopReason=max_tokens)"),
                    kind="error",
                    source="max_tokens",
                )
            if (
                accept_recovered
                and stop_str not in NON_RECOVERABLE_STOPS
                and bool(res_strip)
            ):
                if streamed_strip and streamed_strip != res_strip:
                    raise AgyError(
                        with_streamed("agy streamed text disagrees with final response"),
                        kind="error",
                        source="protocol",
                    )
                response = streamed if streamed_strip else raw_res_resp
                recovered = {
                    "status": stop_str,
                    "error": clip(str(prompt_res.get("error") or err_tail()), 300),
                }
            else:
                raise AgyError(
                    with_streamed(f"agy stopReason {stop_reason}: {clip(str(prompt_res.get('error') or err_tail()))}"),
                    kind="error",
                    source=_stop_error_source(stop_str),
                )

        if not response.strip():
            reason = "agy returned an empty answer"
            ef = err_full()
            if NO_OUTPUT_NOTICE in ef and err_tail():
                reason += ": " + err_tail()
            raise AgyError(reason, kind="error", source="empty")

        raw_usage = prompt_res.get("usage") if isinstance(prompt_res.get("usage"), dict) else {}
        return {
            "response": response,
            "conversation_id": sid,
            "model": resolved_model,
            "turn_usage": _convert_acp_usage(raw_usage),
            "conversation_usage": raw_usage,
            "tool_calls": tool_calls_list(),
            "recovered": recovered,
            "seconds": round(time.monotonic() - started, 1),
        }
    finally:
        if watchdog is not None:
            watchdog.cancel()
        if proc is not None:
            with signals_ignored():
                stop_err = None
                try:
                    stop_group(proc, grace=0.05 if emergency_kill else STOP_GRACE)
                except BaseException as exc:
                    stop_err = exc
                finally:
                    for pipe in (proc.stdin, proc.stdout, proc.stderr):
                        try:
                            if pipe is not None:
                                pipe.close()
                        except Exception:
                            pass
                    if t_out is not None:
                        t_out.join(timeout=1.0)
                    if t_err is not None:
                        t_err.join(timeout=1.0)
                if stop_err is not None:
                    raise stop_err


def file_grants():
    """read_file(...) / view_file(...) / write_file(...) rules found in agy's permission files."""
    found = []
    paths = [Path(os.path.expanduser(p)) for p in PERMISSION_FILES]
    for pattern in PERMISSION_GLOBS:
        base = Path(os.path.expanduser(os.path.dirname(pattern)))
        paths += sorted(base.glob(os.path.basename(pattern))) if base.is_dir() else []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                stack += list(item.values())
            elif isinstance(item, list):
                stack += item
            elif isinstance(item, str) and re.match(r"(read_file|view_file|write_file|write_to_file|edit_file)\(", item):
                found.append(f"{path}: {item}")
    return found


# ---------------------------------------------------------------- files

def link_or_copy(src, dst):
    """Hard-link src to dst (same filesystem), else copy. Never a symlink: agy
    resolves symlinks and treats a target outside the workspace as outside."""
    import shutil
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
        return
    except OSError:
        pass
    try:
        shutil.copy2(src, dst)
    except BaseException:
        dst.unlink(missing_ok=True)  # no half-copied file left behind
        raise


def claude_memory_dir(cwd):
    """Claude Code's project memory directory for cwd, or None when there is none."""
    projects = Path.home() / ".claude" / "projects"
    seen = []
    for form in (os.path.abspath(str(cwd)), os.path.realpath(str(cwd))):
        name = re.sub(r"[^A-Za-z0-9]", "-", form)
        if name in seen:
            continue
        seen.append(name)
        candidate = projects / name / "memory"
        if (candidate / "MEMORY.md").is_file():
            return candidate
    return None


def is_within(path, root):
    try:
        Path(os.path.realpath(str(path))).relative_to(os.path.realpath(str(root)))
        return True
    except ValueError:
        return False
