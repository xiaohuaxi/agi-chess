#!/usr/bin/env python3
"""Shared agy (Antigravity CLI) invocation: one headless turn, checked loudly.

Used by agy_run.py (bounded agent tasks) and llm-chat (plain chat with
attachments). Standard library only.

Every turn runs as
    agy --input-format stream-json --output-format stream-json
        --disable-slash-commands --print-timeout <N>s ...
with the prompt written to stdin as one ``user`` event, so it never shows in
process arguments. The event stream is then checked; anything other than a
clean answer raises AgyError. agy itself reports several failures as
``status: SUCCESS`` with exit 0 (a soft-denied tool, its own print timeout, a
safety-filter notice written into the answer), so the checks below are what
turns those into failures.
"""

import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path

AGY_BIN = "agy"
# Environment handed to agy. A whitelist on purpose: GEMINI_API_KEY or the
# AGY_LLM_GATEWAY_* variables would move the call off the subscription login.
ENV_KEEP = {"HOME", "PATH", "USER", "LOGNAME", "SHELL", "LANG", "TMPDIR", "TERM",
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
            "http_proxy", "https_proxy", "all_proxy", "no_proxy",
            "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS"}
# agy writes this into the answer text (status SUCCESS, exit 0) when Gemini's
# safety filter blocks a reply part-way. Seen with agy 1.3.5.
FILTER_NOTICE = "This request was blocked by Gemini's filters"
# stderr notices from agy 1.3.5, matched loosely (prefixes only).
PRINT_TIMEOUT_NOTICE = re.compile(r"print timeout after \S+ with turn in progress")
NO_OUTPUT_NOTICE = "no output produced"
AGY_ERROR_LINE = re.compile(r"AGY_ERROR:\s*(\{.*\})\s*$", re.M)
# Tools the runtime may call on its own in any agent; harmless (list/kill the
# agent's own background tasks, end the turn).
INTERNAL_TOOLS = frozenset({"manage_task", "finish"})
# Extra seconds after agy's own --print-timeout before the process group is killed.
HARD_KILL_GRACE = 30.0
STOP_GRACE = 5.0

DENIAL_HINTS = {
    "read_file": "a file outside the workspace (cwd plus --add-dir directories)",
    "write_file": "a write outside the workspace, or in a tier without edit rights",
    "command": "a shell command in an agent without commands",
    "read_url": "a web page read outside the research tier",
    "execute_url": "browser actuation; no preset allows it",
    "mcp": "an MCP tool; no preset allows MCP tools",
}


# Which tools raise which permission action (for naming the denied call).
ACTION_TOOLS = {
    "read_file": ("view_file", "list_dir", "grep_search", "find_by_name"),
    "write_file": ("write_to_file", "replace_file_content", "multi_replace_file_content", "notebook_edit"),
    "command": ("run_command",),
    "read_url": ("read_url_content",),
    "mcp": ("call_mcp_tool",),
}
# agy's permission rules live in these JSON files (CLI settings, settings shared
# with the desktop app, per-project settings). Only they can widen the
# workspace boundary that the read and edit presets rely on.
PERMISSION_FILES = ("~/.gemini/antigravity-cli/settings.json", "~/.gemini/config/config.json")
PERMISSION_GLOBS = ("~/.gemini/config/projects/*.json",)


class AgyError(Exception):
    """A user-facing failure. ``kind`` lets callers pick an exit code."""

    def __init__(self, message, kind="error"):
        super().__init__(message)
        self.kind = kind


class Cancelled(BaseException):
    """SIGINT/SIGTERM arrived; unwinds past normal error handling."""

    def __init__(self, signum):
        super().__init__(signum)
        self.signum = signum


def raise_cancelled(signum, _frame):
    # The first cancel wins: later SIGINT/SIGTERM are ignored from here on, so a
    # second Ctrl-C cannot land before the cleanup has shielded itself and skip
    # stopping agy. The caller restores its handlers when it is done (main()).
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal.SIG_IGN)
    raise Cancelled(signum)


def clip(text, limit=1500):
    text = str(text)
    return text if len(text) <= limit else "..." + text[-limit:]


def agy_env(extra=None):
    env = {k: v for k, v in os.environ.items() if k in ENV_KEEP or k.startswith("LC_")}
    env.update(extra or {})
    return env


# ---------------------------------------------------------------- agent files

def agent_markdown(name, description, tools, inherit, body):
    """Markdown custom agent as agy reads it (frontmatter + system prompt body).

    inherit=False also sets excludeDefaultComponents, which drops agy's default
    prompt sections; measured base context is then about 600 input tokens.
    inherit=True keeps the default sections, which is where agy injects the
    global and project rules (AGENTS.md / GEMINI.md) and the skill list.
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ValueError(f"bad agent name {name!r}")
    lines = ["---", f"name: {name}", "description: " + json.dumps(description),
             "inheritCustomizations: " + ("true" if inherit else "false"),
             "excludeDefaultComponents: " + ("false" if inherit else "true"),
             "subagent: false",
             "tools: [" + ", ".join(tools) + "]", "---", body.rstrip("\n"), ""]
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
            out[key.strip()] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
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
    """SIGINT first (agy ends the turn as INTERRUPTED), then SIGTERM, then SIGKILL."""
    pgid = proc.pid
    for sig, wait in ((signal.SIGINT, grace), (signal.SIGTERM, 3.0), (signal.SIGKILL, 5.0)):
        if proc.poll() is not None and not group_alive(pgid):
            return
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if proc.poll() is not None and not group_alive(pgid):
                return
            time.sleep(0.05)
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    if group_alive(pgid):
        raise AgyError(f"could not stop agy process group {pgid}")


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
    """Hold SIGINT/SIGTERM inside the block; release() re-raises what arrived (main thread only).

    Wraps process start: a signal that lands while Popen is still forking would
    otherwise unwind before the caller has a handle on the child, leaving agy
    running in its own session with nobody to stop it."""

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
        """Deliver held signals to the restored handlers (call where cleanup is in place)."""
        pending, self.pending = self.pending, []
        for sig in dict.fromkeys(pending):
            signal.raise_signal(sig)


def build_command(agent, model=None, effort=None, conversation=None, add_dirs=(),
                  extra_flags=(), timeout=600.0):
    cmd = [AGY_BIN, "--input-format", "stream-json", "--output-format", "stream-json",
           "--disable-slash-commands", "--print-timeout", f"{max(1, int(timeout))}s",
           "--agent", agent]
    if model:
        cmd += ["--model", model]
    if effort:
        cmd += ["--effort", effort]
    if conversation:
        cmd += ["--conversation", conversation]
    for d in add_dirs:
        cmd += ["--add-dir", str(d)]
    cmd += list(extra_flags)
    return cmd


def run_agy(cmd, prompt, cwd, timeout, env=None):
    """Run one turn; return (exit code, stdout, stderr). Raises AgyError on hard timeout."""
    stdin_line = json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n"
    proc = None
    held = signals_held()
    try:  # opened before the start, so a signal right after the handlers come back still reaches cleanup
        with held:
            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        cwd=str(cwd), env=env if env is not None else agy_env(),
                                        start_new_session=True, text=True)
            except FileNotFoundError:
                pass
        held.release()  # a cancel that arrived during the start now finds the child
        if proc is None:
            raise AgyError(f"{cmd[0]} CLI not found in PATH (Antigravity CLI)")
        out, err = proc.communicate(stdin_line, timeout=timeout + HARD_KILL_GRACE)
    except subprocess.TimeoutExpired:
        with signals_ignored():
            stop_group(proc)
        raise AgyError(f"agy did not finish within {timeout:.0f}s (+{HARD_KILL_GRACE:.0f}s grace); killed",
                       kind="timeout")
    except BaseException:
        # A second Ctrl-C during cleanup must not skip the SIGTERM/SIGKILL steps.
        if proc is not None:
            with signals_ignored():
                stop_group(proc)
        raise
    with signals_ignored():  # every cleanup path: a signal must not cut it short
        stop_group(proc)  # leftover descendants, if any
    return proc.returncode, out, err


# ---------------------------------------------------------------- stream checks

def add_usage(total, usage):
    for key, value in (usage or {}).items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total[key] = total.get(key, 0) + value


def parse_stream(out):
    """Collect what the checks need from agy's NDJSON stream."""
    info = {"conversation_id": None, "init": None, "result": None, "tools": {},
            "turn_usage": {}, "text": ""}
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("event")
        if kind == "init":
            info["init"] = event.get("init") or {}
            info["conversation_id"] = event.get("conversation_id") or info["conversation_id"]
        elif kind == "step_update":
            step = event.get("step_update") or {}
            if step.get("state") == "DONE":
                add_usage(info["turn_usage"], step.get("usage"))
            if step.get("step_type") == "agent_response" and step.get("text_delta"):
                info["text"] += step["text_delta"]
            if step.get("step_type") == "tool":
                tool_info = step.get("tool_info") or {}
                entry = info["tools"].setdefault(step.get("step_index"), {})
                entry["name"] = step.get("tool_name") or tool_info.get("name") or entry.get("name")
                if tool_info.get("parameters") is not None:
                    entry["parameters"] = tool_info["parameters"]
                if tool_info.get("error"):
                    entry["error"] = tool_info["error"]
                entry["state"] = step.get("state")
        elif kind == "result":
            info["result"] = event.get("result") or {}
            info["conversation_id"] = info["result"].get("conversation_id") or info["conversation_id"]
    info["tool_calls"] = [info["tools"][k] for k in sorted(info["tools"], key=lambda x: (x is None, x))]
    return info


def tool_target(call):
    params = call.get("parameters") or {}
    for key in ("AbsolutePath", "TargetFile", "NotebookPath", "DirectoryPath", "SearchPath", "SearchDirectory", "Url",
                "CommandLine", "query", "Query"):
        if params.get(key):
            return str(params[key])
    return json.dumps(params, ensure_ascii=False)[:200] if params else ""


def describe_denials(denied, tool_calls):
    parts = []
    for item in denied:
        action = item.get("action") or "?"
        parts.append(f"{action} ({item.get('display_name') or '?'}): {DENIAL_HINTS.get(action, 'needs approval')}")
    # A denial ends the turn, so the denied call is the last call of a matching
    # tool. Its step may still reach DONE (with no output), so state cannot tell.
    attempted = []
    for item in denied:
        names = ACTION_TOOLS.get(item.get("action"), ())
        match = [c for c in tool_calls if c.get("name") in names]
        if match and match[-1] not in attempted:
            attempted.append(match[-1])
    if attempted:
        parts.append("attempted: " + "; ".join(f"{c.get('name')} {tool_target(c)}" for c in attempted))
    return "; ".join(parts)


def check_turn(code, out, err, allowed_tools):
    """Turn agy's output into (info, response) or raise AgyError with a readable reason."""
    info = parse_stream(out)
    result = info["result"]
    stderr_tail = clip(err.strip(), 800) if err.strip() else ""
    if PRINT_TIMEOUT_NOTICE.search(err):
        raise AgyError("agy hit --print-timeout with the turn still running; partial output discarded "
                       f"({len((result or {}).get('response') or info['text'])} chars)", kind="timeout")
    if code != 0:
        match = AGY_ERROR_LINE.search(err)
        detail = match.group(1) if match else ((result or {}).get("error") or stderr_tail or out[-800:])
        raise AgyError(f"agy exited {code}: {clip(detail)}", kind="api" if code == 3 else "error")
    if result is None:
        raise AgyError(f"agy produced no result event: {stderr_tail or clip(out)}")
    status = result.get("status")
    if status != "SUCCESS":
        raise AgyError(f"agy status {status}: {clip(result.get('error') or stderr_tail)}")
    denied = result.get("denied_actions") or []
    if denied:
        raise AgyError("agy soft-denied a tool and ended the turn (headless mode cannot ask): "
                       + describe_denials(denied, info["tool_calls"]), kind="denied")
    allowed = set(allowed_tools) | INTERNAL_TOOLS
    bad = [c for c in info["tool_calls"] if c.get("name") not in allowed]
    if bad:
        raise AgyError("agy called tools outside this preset: "
                       + "; ".join(f"{c.get('name')} {tool_target(c)}" for c in bad), kind="tool")
    response = result.get("response") or ""
    if FILTER_NOTICE in response:
        raise AgyError("Gemini's safety filter blocked the answer (agy wrote its notice into the reply)",
                       kind="filtered")
    if not response.strip():
        reason = "agy returned an empty answer"
        if NO_OUTPUT_NOTICE in err:
            reason += ": " + stderr_tail
        raise AgyError(reason)
    return info, response


def turn(agent, prompt, cwd, *, allowed_tools, model=None, effort=None, conversation=None,
         add_dirs=(), extra_flags=(), timeout=600.0, env=None):
    """Run and check one turn. Returns a dict with response, conversation_id, usage and tool calls."""
    cmd = build_command(agent, model, effort, conversation, add_dirs, extra_flags, timeout)
    started = time.monotonic()
    code, out, err = run_agy(cmd, prompt, cwd, timeout, env)
    info, response = check_turn(code, out, err, allowed_tools)
    if not info["conversation_id"]:
        raise AgyError("agy did not report a conversation id")
    if conversation and info["conversation_id"] != conversation:
        raise AgyError(f"agy answered in conversation {info['conversation_id']}, not {conversation}")
    return {
        "response": response,
        "conversation_id": info["conversation_id"],
        "model": (info["init"] or {}).get("model") or model,
        "turn_usage": info["turn_usage"],
        "conversation_usage": (info["result"] or {}).get("usage") or {},
        "tool_calls": info["tool_calls"],
        "seconds": round(time.monotonic() - started, 1),
    }


def file_grants():
    """read_file(...) / write_file(...) rules found in agy's permission files.

    A plain scan for such strings anywhere in those files: cheap, and errs on
    the side of reporting. (`agy -p /permissions` would be exact but takes ~8s.)"""
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
            elif isinstance(item, str) and re.match(r"(read_file|write_file)\(", item):
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
    """Claude Code's project memory directory for cwd, or None when there is none.

    Claude names project folders after the cwd with every non-alphanumeric
    character turned into '-'. Tries the path as given, then its realpath."""
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
