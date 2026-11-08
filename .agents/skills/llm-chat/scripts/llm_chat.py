#!/usr/bin/env python3
"""Plain-text multi-turn chat with any model (no tools, not an agent run).

Standard library only. The user message comes from stdin, the answer goes to
stdout, and one metadata line (prefixed ``LLM_CHAT_META``) goes to stderr.
Every failure is loud: a message on stderr and a non-zero exit, no retries.
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_ENDPOINTS_URL = "https://openrouter.ai/api/v1/models/{}/endpoints"
DEEPSEEK_CHAT_URL = "https://api.deepseek.com/chat/completions"
KEY_ENV = {
    "openrouter": ("API_KEY_OPENROUTER", "OPENROUTER_API_KEY"),
    "deepseek": ("API_KEY_DEEPSEEK", "DEEPSEEK_API_KEY"),
}
# DeepSeek official API model names mapped to active OpenRouter model slugs when
# falling back to OpenRouter (deepseek-flash -> deepseek/deepseek-v4.1-flash and
# deepseek-v4-pro -> deepseek/deepseek-v4-pro; legacy aliases deepseek-chat and
# deepseek-reasoner are also mapped for compatibility).
DEEPSEEK_OPENROUTER_MODELS = {
    "deepseek": "deepseek/deepseek-v4-pro",
    "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
    "deepseek-reasoner": "deepseek/deepseek-v4-pro",
    "deepseek-flash": "deepseek/deepseek-v4.1-flash",
    "deepseek-chat": "deepseek/deepseek-v4.1-flash",
}
DEFAULT_TIMEOUT = 600.0
META_PREFIX = "LLM_CHAT_META "
# Verified OpenRouter provider slugs for a vendor prefix. Only add entries
# after checking the real slug; unknown vendors go through the endpoint lookup.
# DeepSeek has no first-party endpoint tag on OpenRouter (all are third-party providers).
KNOWN_PROVIDER_SLUGS = {"x-ai": "xai", "google": "google-ai-studio", "deepseek": None}
CLAUDE_ALIAS = re.compile(r"(opus|sonnet|haiku|fable)(\[1m\])?\Z")
EFFORT_PATTERN = re.compile(r"[a-z]+\Z")
SESSION_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
# GPT-6 models are forced into code mode: they see exec-like tools that fail
# when called. Tell them plainly that nothing is available.
NO_TOOLS_NOTE = "\n\nYou have no tools available. Answer directly in plain text."
CODEX_ISOLATION = [
    "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
    "-c", "web_search=disabled", "-c", "project_doc_max_bytes=0",
    "-c", "project_root_markers=[]", "-c", "skills.include_instructions=false",
    "-c", "include_environment_context=false",
    "-c", "include_permissions_instructions=false",
    "-c", "include_collaboration_mode_instructions=false",
    "-c", "include_apps_instructions=false", "-c", "agents.enabled=false",
    "-c", "tools.experimental_request_user_input.enabled=false",
    "-c", "tools.update_plan.enabled=false",
    "--disable", "code_mode_host", "--disable", "shell_tool",
    "--disable", "unified_exec", "--disable", "multi_agent",
    "--disable", "multi_agent_v2", "--disable", "image_generation",
    "--disable", "apps", "--disable", "plugins", "--disable", "computer_use",
    "--disable", "browser_use", "--disable", "goals", "--disable", "skill_search",
    "--disable", "tool_suggest", "--disable", "memories", "--disable", "hooks",
    "--disable", "view_image",
]
CLAUDE_ISOLATION = [
    "--safe-mode", "--setting-sources", "", "--tools", "", "--strict-mcp-config",
    "--disallowedTools", "mcp__*", "--disable-slash-commands",
]
# Environment handed to the CLIs. Deliberately a whitelist: variables such as
# ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY / CLAUDE_CODE_USE_BEDROCK or
# OPENAI_BASE_URL / OPENAI_API_KEY would move the call off the subscription.
ENV_KEEP = {"HOME", "PATH", "USER", "LOGNAME", "SHELL", "LANG", "TMPDIR", "TERM",
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
            "http_proxy", "https_proxy", "all_proxy", "no_proxy",
            "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS"}
FAMILY = {"openrouter": "http", "deepseek": "http", "claude": "claude", "codex": "codex", "agy": "agy"}
# The agy route uses agy_core.py from the same directory when bundled with a
# repository skill, or falls back to the sibling agy-run skill directory.
_SCRIPT_DIR = Path(__file__).resolve().parent
AGY_CORE_DIR = (
    _SCRIPT_DIR
    if (_SCRIPT_DIR / "agy_core.py").is_file()
    else Path(__file__).resolve().parents[2] / "agy-run" / "scripts"
)
AGY_AGENT = "llm-chat-session"
# Content blocks removed from claude's session transcript under --drop-thinking,
# and the record fields that point at another record's uuid.
THINKING_BLOCKS = ("thinking", "redacted_thinking")
UUID_LINKS = ("parentUuid", "leafUuid", "logicalParentUuid")


class ChatError(Exception):
    """A user-facing failure; the process exits non-zero."""


class SessionBusy(ChatError):
    """Another process holds this session's lock."""


class Cancelled(BaseException):
    """SIGINT/SIGTERM arrived; unwinds past normal error handling."""

    def __init__(self, signum):
        super().__init__(signum)
        self.signum = signum


def raise_cancelled(signum, _frame):
    # The first cancel wins: later signals are ignored until main() restores the
    # handlers, so a second Ctrl-C cannot cut short the reaping of the child.
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal.SIG_IGN)
    raise Cancelled(signum)


# ---------------------------------------------------------------- helpers

def key_env_names(backend):
    names = KEY_ENV[backend]
    return names if isinstance(names, tuple) else (names,)


def find_api_key(backend):
    for name in key_env_names(backend):
        value = os.environ.get(name, "")
        if value:
            return value
    return ""


def sanitize(text):
    """Remove any known API key value from text that may reach stderr."""
    text = str(text)
    for backend in KEY_ENV:
        for name in key_env_names(backend):
            value = os.environ.get(name)
            if value and len(value) >= 8:
                text = text.replace(value, "[REDACTED]")
    return text


def clip(text, limit=2000):
    # Redact the full text first: cutting first could leave a key's tail behind.
    text = sanitize(text)
    return text if len(text) <= limit else "..." + text[-limit:]


def deepseek_openrouter_model(name):
    bare = name.split("/", 1)[1] if "/" in name else name
    return DEEPSEEK_OPENROUTER_MODELS.get(bare.lower(), f"deepseek/{bare}")


def route(model):
    """Map a model id to (backend, backend_model). Rules are documented in SKILL.md."""
    name = model.strip()
    low = name.lower()
    if not name:
        raise ChatError("model id is empty")
    bare = low.lstrip("~")
    if bare.startswith("anthropic/"):
        return "claude", name.lstrip("~").split("/", 1)[1]
    if low.startswith("claude-") or CLAUDE_ALIAS.match(low):
        return "claude", name
    if bare.startswith("openai/"):
        return "codex", name.lstrip("~").split("/", 1)[1]
    if low.startswith("gpt-"):
        return "codex", name
    if low.startswith("agy/"):
        return "agy", name.split("/", 1)[1]
    if low.startswith("gemini-"):
        return "agy", name
    if low.startswith("deepseek/") or low.startswith("deepseek"):
        ds_model = name.split("/", 1)[1] if "/" in name else name
        if ds_model.lower() == "deepseek":
            ds_model = "deepseek-v4-pro"
        if not find_api_key("deepseek") and find_api_key("openrouter"):
            return "openrouter", deepseek_openrouter_model(ds_model)
        return "deepseek", ds_model
    if "/" in name or name.startswith("@"):
        assert_openrouter_allowed(name)
        return "openrouter", name
    raise ChatError(f"unrecognized model id {name!r}: OpenRouter models need a vendor/name id")


def assert_openrouter_allowed(model):
    """Hard guarantee: Claude and GPT never go to OpenRouter (subscriptions cover them).

    Also refuses meta-routers (openrouter/auto and other openrouter/* ids) and
    presets (@...), since they may pick a Claude or GPT model on their own.
    """
    low = model.lower().lstrip("~")
    vendor = low.split("/", 1)[0]
    if vendor in ("anthropic", "openai") or "claude" in low or "gpt-" in low:
        raise ChatError(f"refusing to send {model!r} to OpenRouter: Claude/GPT use the local CLIs")
    if vendor == "openrouter" or low.startswith("@") or "/" not in low:
        raise ChatError(f"refusing {model!r}: only concrete vendor/model ids go to OpenRouter, "
                        "not routers or presets that may choose Claude/GPT")
    # No tools, no web: ":online" turns on web search, and the other variant
    # suffixes (:free, :nitro, :floor, :exacto, ...) re-route providers, which
    # fights the provider pin. Multi-agent models run tools server-side.
    if ":" in low:
        raise ChatError(f"refusing {model!r}: variant suffixes (':online', ':free', ...) are not allowed")
    if "multi-agent" in low:
        raise ChatError(f"refusing {model!r}: multi-agent models use tools")


def state_dir():
    base = os.environ.get("XDG_STATE_HOME", "")
    root = Path(base) if base and os.path.isabs(base) else Path.home() / ".local" / "state"
    return root / "llm-chat"


def ensure_state():
    root = state_dir()
    for sub in ("sessions", "codex-home", "empty", "agy"):
        (root / sub).mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


class SessionLock:
    """Exclusive, non-blocking flock on sessions/<id>.lock for one whole turn."""

    def __init__(self, root, session_id):
        self.path = root / "sessions" / f"{session_id}.lock"
        self.handle = None

    def __enter__(self):
        self.handle = open(self.path, "a")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close()
            raise SessionBusy(f"session {self.path.stem} is in use by another llm-chat process")
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()


def session_path(root, session_id):
    return root / "sessions" / f"{session_id}.json"


def load_session(root, session_id):
    path = session_path(root, session_id)
    if not path.exists():
        raise ChatError(f"session {session_id} not found in {path.parent}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ChatError(f"session file {path} is unreadable: {exc}")


def save_session(root, session):
    session["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    atomic_write(session_path(root, session["id"]), json.dumps(session, ensure_ascii=False, indent=1))


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- HTTP backends

def http_request(url, key, body=None, timeout=DEFAULT_TIMEOUT):
    """POST (or GET when body is None) JSON; return the parsed object or raise."""
    headers = {"Authorization": "Bearer " + key, "User-Agent": "llm-chat/1.0"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise ChatError(f"HTTP {exc.code} from {url}: {clip(detail)}")
    except (urllib.error.URLError, OSError) as exc:
        raise ChatError(f"request to {url} failed: {exc}")
    return parse_json_response(raw, url)


def parse_json_response(raw, url):
    # A 200 can still carry an error body, sometimes padded with whitespace.
    text = raw.strip()
    try:
        obj = json.loads(text)
    except ValueError:
        raise ChatError(f"non-JSON response from {url}: {clip(text)}")
    if not isinstance(obj, dict):
        raise ChatError(f"unexpected response from {url}: {clip(text)}")
    if obj.get("error"):
        raise ChatError(f"API error from {url}: {clip(json.dumps(obj['error'], ensure_ascii=False))}")
    return obj


def api_key(backend):
    value = find_api_key(backend)
    if not value:
        if backend == "deepseek":
            raise ChatError(
                "missing API key: set API_KEY_DEEPSEEK (or API_KEY_OPENROUTER to route DeepSeek via OpenRouter)"
            )
        names = " or ".join(key_env_names(backend))
        raise ChatError(f"environment variable {names} is not set")
    return value


def resolve_provider_slug(model, key, timeout):
    """Pick the official provider slug to pin, or None when there is none."""
    vendor = model.lower().lstrip("~").split("/", 1)[0]
    if vendor in KNOWN_PROVIDER_SLUGS:
        return KNOWN_PROVIDER_SLUGS[vendor]
    url = OPENROUTER_ENDPOINTS_URL.format(urllib.parse.quote(model, safe="/:~"))
    data = http_request(url, key, timeout=timeout).get("data") or {}
    tags = {ep.get("tag") for ep in data.get("endpoints") or []}
    return vendor if vendor in tags else None


def with_breakpoint(message):
    """Copy a message with an ephemeral cache breakpoint on its (only) text block."""
    out = dict(message)
    out["content"] = [{"type": "text", "text": message["content"], "cache_control": {"type": "ephemeral"}}]
    return out


def openrouter_messages(system, history, user_text):
    # Breakpoint on the last block of the stable prefix (system on the first
    # turn, else the last history message). Gemini only honours the last
    # breakpoint and ignores one placed on the new user message.
    prefix = [{"role": "system", "content": system}] + list(history)
    prefix[-1] = with_breakpoint(prefix[-1])
    return prefix + [{"role": "user", "content": user_text}]


def deepseek_messages(system, history, user_text):
    # Plain-text chat: DeepSeek ignores replayed reasoning_content, so replay content only.
    msgs = [{"role": "system", "content": system}]
    msgs += [{"role": m["role"], "content": m["content"]} for m in history]
    return msgs + [{"role": "user", "content": user_text}]


def server_tool_uses(usage, path=""):
    """Positive counters for server-side tools or search anywhere in a usage object."""
    found = []
    if isinstance(usage, dict):
        for key, value in usage.items():
            found += server_tool_uses(value, f"{path}.{key}" if path else key)
    elif isinstance(usage, (int, float)) and not isinstance(usage, bool) and usage > 0:
        low = path.lower()
        if any(word in low for word in ("server_tool", "tool_use", "search", "fetch")):
            found.append(f"{path}={usage}")
    return found


def check_no_tools(usage):
    used = server_tool_uses(usage or {})
    if used:
        raise ChatError("the model used server-side tools (" + ", ".join(used) + "); plain chat allows none")


def check_choice(resp):
    choices = resp.get("choices") or []
    if not choices or not isinstance(choices[0].get("message"), dict):
        check_no_tools(resp.get("usage"))
        raise ChatError(f"response has no message: {clip(json.dumps(resp, ensure_ascii=False))}")
    choice = choices[0]
    message = choice["message"]
    text = message.get("content") or ""
    finish = choice.get("finish_reason")
    if message.get("tool_calls") or finish == "tool_calls":
        raise ChatError("the model called a tool; plain chat allows none")
    if message.get("annotations"):
        raise ChatError("the answer carries annotations (web citations); plain chat allows no web access")
    check_no_tools(resp.get("usage"))
    if not text.strip():
        raise ChatError(f"empty answer (finish_reason={finish}); reasoning tokens count toward "
                        "--max-tokens, raise it or lower --effort")
    if finish == "length":
        raise ChatError("answer truncated by the token limit (finish_reason=length); raise --max-tokens")
    return message, text


def call_openrouter(session, user_text, opts):
    model = session["model"]
    assert_openrouter_allowed(model)
    key = api_key("openrouter")
    if "provider_only" not in session:
        session["provider_only"] = resolve_provider_slug(model, key, opts.timeout)
    history = session["messages"]
    if session.get("drop_thinking"):
        # Earlier answers go back as visible text only; the saved history keeps the reasoning.
        history = [{"role": m["role"], "content": m["content"]} for m in history]
    body = {"model": model, "messages": openrouter_messages(session["system"], history, user_text)}
    if session["provider_only"]:
        body["provider"] = {"only": [session["provider_only"]], "allow_fallbacks": False}
    # Override any account-wide default that turns the web plugin on.
    body["plugins"] = [{"id": "web", "enabled": False}]
    if opts.effort:
        body["reasoning"] = {"effort": opts.effort}
    if opts.max_tokens:
        body["max_tokens"] = opts.max_tokens
    resp = http_request(OPENROUTER_CHAT_URL, key, body, opts.timeout)
    message, text = check_choice(resp)
    check_no_tools(resp.get("usage"))
    kept = {"role": "assistant", "content": text}
    for field in ("reasoning", "reasoning_details"):
        if message.get(field) is not None:
            kept[field] = message[field]
    usage = resp.get("usage") or {}
    ptd = usage.get("prompt_tokens_details") or {}
    ctd = usage.get("completion_tokens_details") or {}
    return {
        "text": text, "assistant": kept, "model": resp.get("model") or model,
        "provider": resp.get("provider"), "cost_usd": usage.get("cost"), "cost_basis": "billed",
        "cache_read": ptd.get("cached_tokens", 0), "cache_write": ptd.get("cache_write_tokens", 0),
        "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": ctd.get("reasoning_tokens"),
    }


def call_deepseek(session, user_text, opts):
    key = api_key("deepseek")
    body = {"model": session["model"], "messages": deepseek_messages(session["system"], session["messages"], user_text)}
    if opts.effort:
        body["reasoning_effort"] = opts.effort
    if opts.max_tokens:
        body["max_tokens"] = opts.max_tokens
    resp = http_request(DEEPSEEK_CHAT_URL, key, body, opts.timeout)
    _, text = check_choice(resp)
    check_no_tools(resp.get("usage"))
    usage = resp.get("usage") or {}
    ctd = usage.get("completion_tokens_details") or {}
    return {
        "text": text, "assistant": {"role": "assistant", "content": text},
        "model": resp.get("model") or session["model"], "provider": "DeepSeek",
        "cost_usd": None, "cost_basis": None,
        "cache_read": usage.get("prompt_cache_hit_tokens", 0),
        "cache_write": None,  # DeepSeek reports hits/misses only, not writes.
        "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": ctd.get("reasoning_tokens"),
    }


# ---------------------------------------------------------------- CLI backends

def run_process(cmd, stdin_text, cwd, env, timeout):
    """Run a child in its own process group; return (code, stdout, stderr)."""
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=str(cwd), env=env, start_new_session=True, text=True)
    except FileNotFoundError:
        raise ChatError(f"{cmd[0]} CLI not found in PATH")
    try:
        out, err = proc.communicate(stdin_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        stop_group(proc)
        raise ChatError(f"{cmd[0]} timed out after {timeout:.0f}s")
    except BaseException:
        # Cancelled (or anything else): reap the whole group before the caller
        # releases the session lock.
        stop_group(proc)
        raise
    stop_group(proc)  # leftover descendants, if any
    return proc.returncode, out, err


def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def stop_group(proc, grace=3.0):
    """SIGTERM the child's process group, then SIGKILL; wait until it is gone."""
    pgid = proc.pid
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 5.0)):
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
        raise ChatError(f"could not stop process group {pgid}")


def cli_env(**extra):
    env = {k: v for k, v in os.environ.items() if k in ENV_KEEP or k.startswith("LC_")}
    env.update(extra)
    return env


def check_empty_dir(path):
    if any(path.iterdir()):
        raise ChatError(f"working directory {path} must stay empty (it isolates the CLI from project files)")


def claude_transcript(workdir, backend_session):
    """Where claude keeps a session: ~/.claude/projects/<cwd with each non-alphanumeric
    character turned into '-'>/<session id>.jsonl. That naming is claude's, not a
    contract (very long paths may be named differently), so when the guess misses,
    look the session id up across all projects and require exactly one hit."""
    projects = Path.home() / ".claude" / "projects"
    name = f"{backend_session}.jsonl"
    guess = projects / re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(str(workdir))) / name
    if guess.is_file():
        return guess
    hits = [p for p in projects.glob("*/" + name) if p.is_file()]
    if len(hits) == 1:
        return hits[0]
    raise ChatError(f"cannot find claude's transcript {name} under {projects} ({len(hits)} matches); "
                    "--drop-thinking needs it")


def is_thinking(block):
    return isinstance(block, dict) and block.get("type") in THINKING_BLOCKS


def strip_thinking_lines(lines):
    """Remove thinking blocks from the assistant records of a claude transcript.

    claude writes one record per content block, so a thinking block usually is a
    record of its own; such a record is dropped and whatever pointed at it is
    re-linked to its parent, keeping the conversation chain intact. Every other
    line is kept byte for byte. Returns (new lines, number of blocks removed).
    """
    parsed = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            parsed.append([line, json.loads(line)])
        except ValueError:
            raise ChatError(f"claude transcript line {number} is not JSON; not touching it")
    gone, removed = {}, 0
    for item in parsed:
        rec = item[1]
        content = (rec.get("message") or {}).get("content") if rec.get("type") == "assistant" else None
        if not isinstance(content, list) or not any(is_thinking(b) for b in content):
            continue
        rest = [b for b in content if not is_thinking(b)]
        removed += len(content) - len(rest)
        if rest:
            rec["message"]["content"] = rest
            item[0] = None  # re-serialize
        else:
            if not rec.get("uuid"):
                raise ChatError("claude transcript has a thinking record without a uuid; not touching it")
            gone[rec["uuid"]] = rec.get("parentUuid")
            item[1] = None

    def survivor(uuid_):
        while uuid_ in gone:
            uuid_ = gone[uuid_]
        return uuid_

    out = []
    for line, rec in parsed:
        if rec is None:
            continue
        for key in UUID_LINKS:
            if rec.get(key) and rec[key] in gone:
                rec[key] = survivor(rec[key])
                line = None
        out.append(line if line is not None else json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
    return out, removed


def drop_claude_thinking(workdir, backend_session):
    """Rewrite the transcript that --resume reads so earlier turns carry no thinking."""
    path = claude_transcript(workdir, backend_session)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ChatError(f"cannot read claude transcript {path}: {exc}")
    out, removed = strip_thinking_lines(lines)
    if removed:
        atomic_write(path, "".join(line + "\n" for line in out))
    return removed


def call_claude(session, user_text, opts, root):
    workdir = root / "empty"
    check_empty_dir(workdir)
    dropped = None
    if session.get("drop_thinking"):
        dropped = drop_claude_thinking(workdir, session["backend_session"]) if session.get("backend_session") else 0
    cmd = ["claude", "-p", *CLAUDE_ISOLATION, "--system-prompt", session["system"],
           "--model", session["model"], "--output-format", "json"]
    if opts.effort:
        cmd += ["--effort", opts.effort]
    if session.get("backend_session"):
        cmd += ["--resume", session["backend_session"]]
    else:
        session["pending_backend_session"] = str(uuid.uuid4())
        cmd += ["--session-id", session["pending_backend_session"]]
    env = cli_env()
    if opts.max_tokens:
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(opts.max_tokens)
    code, out, err = run_process(cmd, user_text, workdir, env, opts.timeout)
    try:
        data = json.loads(out.strip())
    except ValueError:
        raise ChatError(f"claude exited {code} without JSON output: {clip(err or out)}")
    if code != 0 or data.get("is_error") or data.get("subtype") != "success":
        raise ChatError(f"claude failed (exit {code}): {clip(data.get('result') or err or out)}")
    check_no_tools(data.get("usage"))
    text = data.get("result") or ""
    if not text.strip():
        raise ChatError("claude returned an empty answer")
    usage = data.get("usage") or {}
    model_usage = data.get("modelUsage") or {}
    actual = max(model_usage, key=lambda k: model_usage[k].get("outputTokens", 0)) if model_usage else session["model"]
    session["backend_session"] = data.get("session_id") or session.get("backend_session") \
        or session.get("pending_backend_session")
    session.pop("pending_backend_session", None)
    cost = claude_turn_cost(session, data.get("total_cost_usd"))
    result = {
        "text": text, "model": actual, "provider": "anthropic (claude subscription)",
        "cost_usd": cost, "cost_basis": "list-price estimate, not charged on subscription",
        "cache_read": usage.get("cache_read_input_tokens", 0),
        "cache_write": usage.get("cache_creation_input_tokens", 0),
        "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": (usage.get("output_tokens_details") or {}).get("thinking_tokens"),
    }
    if dropped is not None:
        result["thinking_dropped"] = dropped
    return result


def claude_turn_cost(session, total):
    """claude -p reports total_cost_usd (and modelUsage) summed over the whole
    session, while `usage` is this turn only. Return this turn's cost and keep
    the running total as the next turn's baseline. A total that drops (e.g.
    after compaction) is taken as this turn's cost.
    """
    if total is None:
        return None
    before = session.get("claude_cost_total") or 0.0
    session["claude_cost_total"] = total
    return round(total - before, 10) if total >= before else total


def main_codex_home():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def ensure_codex_auth(codex_home):
    """auth.json must be a symlink to the main login; a copy would steal token refreshes."""
    target = main_codex_home() / "auth.json"
    if not target.exists():
        if not shutil.which("codex"):
            raise ChatError(f"codex CLI not found in PATH (and {target} is missing)")
        raise ChatError(f"codex is not logged in: {target} is missing")
    link = codex_home / "auth.json"
    with open(codex_home / ".auth-link.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # shared by every llm-chat process
        try:
            if not os.path.lexists(link):
                os.symlink(str(target), str(link))
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
    if not link.is_symlink():
        raise ChatError(f"{link} is not a symlink; replace it with a symlink to {target} (never copy credentials)")
    if os.readlink(link) != str(target):
        raise ChatError(f"{link} points to {os.readlink(link)}, expected {target}; fix it by hand")


# The one error item codex emits on every GPT-6 turn here, captured verbatim
# (codex-cli 0.158.0). Only this exact text, as an item.completed error item,
# is ignored; any other error, or this text in another event, fails the turn.
# If a codex upgrade rewords it, turns fail loudly until this is updated.
CODE_MODE_NOTICE = ("Code Mode is unavailable because code-mode host is disabled. Code mode will fail "
                    "closed; enable `features.code_mode_host` and install `codex-code-mode-host`.")


# Items allowed in a plain chat turn ("reasoning" is a summary, not a tool).
# Error items are handled separately: only the exact code-mode notice passes.
CODEX_ITEM_OK = ("agent_message", "reasoning")


def parse_codex_events(out):
    thread_id, texts, usage, errors = None, [], None, []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("type")
        item = event.get("item") or {}
        if kind == "item.completed" and item.get("type") == "error" and item.get("message") == CODE_MODE_NOTICE:
            continue
        if kind in ("item.started", "item.updated", "item.completed") and item.get("type") == "error":
            errors.append(item.get("message") or json.dumps(item, ensure_ascii=False))
            continue
        if kind in ("item.started", "item.updated", "item.completed") and item.get("type") not in CODEX_ITEM_OK:
            # Any other item is a tool call, web search, command, patch, plan...
            errors.append(f"unexpected codex item {item.get('type')!r}; plain chat allows no tools")
            continue
        if kind == "thread.started":
            thread_id = event.get("thread_id")
        elif kind == "item.completed" and item.get("type") == "agent_message":
            texts.append(item.get("text") or "")
        elif kind == "error":
            errors.append(event.get("message") or json.dumps(event, ensure_ascii=False))
        elif kind == "turn.failed":
            errors.append(json.dumps(event.get("error") or event, ensure_ascii=False))
        elif kind == "turn.completed":
            usage = event.get("usage") or {}
    return thread_id, texts, usage, errors


CODEX_USAGE_KEYS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                    "output_tokens", "reasoning_output_tokens")


def codex_turn_usage(session, totals):
    """codex reports thread-cumulative usage; return this turn's share.

    The running totals are kept in the session as the next turn's baseline. If a
    total ever drops (the thread was compacted or reset) the reported value is
    taken as this turn's usage.
    """
    base = session.get("codex_usage_total") or {}
    turn = {}
    for key in CODEX_USAGE_KEYS:
        now = totals.get(key) or 0
        before = base.get(key) or 0
        turn[key] = now - before if now >= before else now
    session["codex_usage_total"] = {k: totals.get(k) or 0 for k in CODEX_USAGE_KEYS}
    return turn


def call_codex(session, user_text, opts, root):
    if opts.max_tokens:
        raise ChatError("--max-tokens is not supported for GPT models (codex exec has no such setting)")
    codex_home = root / "codex-home"
    ensure_codex_auth(codex_home)
    workdir = root / "empty"
    check_empty_dir(workdir)
    instructions = root / "sessions" / f"{session['id']}.instructions.md"
    atomic_write(instructions, session["system"] + NO_TOOLS_NOTE)
    common = ["--json", *CODEX_ISOLATION, "-c", "model_instructions_file=" + json.dumps(str(instructions)),
              "-m", session["model"]]
    if opts.effort:
        common += ["-c", f'model_reasoning_effort="{opts.effort}"']
    if session.get("thread_id"):
        cmd = ["codex", "exec", "resume", *common, "-c", 'sandbox_mode="read-only"', session["thread_id"], "-"]
    else:
        cmd = ["codex", "exec", *common, "-s", "read-only", "-C", str(workdir), "-"]
    env = cli_env(CODEX_HOME=str(codex_home))
    code, out, err = run_process(cmd, user_text, workdir, env, opts.timeout)
    thread_id, texts, usage, errors = parse_codex_events(out)
    if errors:
        raise ChatError("codex reported an error: " + clip(" | ".join(str(e) for e in errors)))
    if code != 0:
        raise ChatError(f"codex exited {code}: {clip(err or out)}")
    if usage is None:
        raise ChatError(f"codex did not complete the turn: {clip(err or out)}")
    text = texts[-1] if texts else ""
    if not text.strip():
        raise ChatError("codex returned an empty answer")
    if not session.get("thread_id"):
        if not thread_id:
            raise ChatError("codex did not report a thread id")
        session["thread_id"] = thread_id
    usage = codex_turn_usage(session, usage)
    return {
        "text": text, "model": session["model"], "provider": "openai (codex subscription)",
        "cost_usd": None, "cost_basis": None,
        "cache_read": usage.get("cached_input_tokens", 0), "cache_write": usage.get("cache_write_input_tokens", 0),
        "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": usage.get("reasoning_output_tokens"),
    }


# ---------------------------------------------------------------- agy (Gemini via Antigravity CLI)

def agy_core():
    if str(AGY_CORE_DIR) not in sys.path:
        sys.path.insert(0, str(AGY_CORE_DIR))
    import agy_core
    return agy_core


def agy_workspace(root, session, core):
    """Per-session agy workspace: the session agent (system message as its prompt) and attachments.

    The agent gets view_file and nothing else, inherits no rules, skills or MCP
    servers, and cannot be called as a subagent. agy fixes an agent's tools when
    the conversation starts, so view_file is there from the first turn even
    when no file is ever attached.
    """
    workdir = root / "agy" / session["id"]
    agent_file = workdir / ".agents" / "agents" / f"{AGY_AGENT}.md"
    if not agent_file.exists():
        agent_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write(agent_file, core.agent_markdown(
            AGY_AGENT, "llm-chat session agent", ["view_file"], False, session["system"]))
    return workdir


def stage_attachments(workdir, turn_index, paths, core):
    """Hard-link (or copy) each attachment into the workspace; return the staged paths."""
    staged = []
    target_dir = workdir / "files" / f"turn-{turn_index}"
    try:
        for number, raw in enumerate(paths, 1):
            src = Path(raw).expanduser()
            if not src.is_file():
                raise ChatError(f"attachment is not a readable file: {raw}")
            dst = target_dir / f"{number}-{src.name}"
            if dst.exists():
                dst.unlink()
            core.link_or_copy(src, dst)
            staged.append(dst)
    except BaseException:
        for path in staged:
            path.unlink(missing_ok=True)
        raise
    return staged


def call_agy(session, user_text, opts, root):
    if opts.max_tokens:
        raise ChatError("--max-tokens is not supported for agy models (agy has no such setting)")
    core = agy_core()
    workdir = agy_workspace(root, session, core)
    staged = []
    try:
        staged = stage_attachments(workdir, len(session["turns"]) + 1, opts.attach or [], core)
        prompt = user_text
        if staged:
            prompt += "\n\nAttached files (open each one with view_file before answering):\n" + \
                "".join(f"- {p}\n" for p in staged)
        try:
            result = core.turn(AGY_AGENT, prompt, workdir, allowed_tools=("view_file",), model=session["model"],
                               effort=opts.effort, conversation=session.get("conversation_id"),
                               timeout=opts.timeout)
        except core.AgyError as exc:
            raise ChatError(str(exc))
        # Only files attached on a saved turn or on this one may be opened.
        allowed = {os.path.realpath(p) for p in session.get("agy_files", [])} | \
            {os.path.realpath(str(p)) for p in staged}
        stray = [core.tool_target(c) for c in result["tool_calls"]
                 if c.get("name") == "view_file" and os.path.realpath(core.tool_target(c)) not in allowed]
        if stray:
            raise ChatError("the model opened files that were not attached: " + "; ".join(stray))
    except BaseException:
        for path in staged:  # a failed turn leaves no attachment behind
            path.unlink(missing_ok=True)
        raise
    session["conversation_id"] = result["conversation_id"]
    session["agy_files"] = session.get("agy_files", []) + [str(p) for p in staged]
    usage = result["turn_usage"]
    return {
        "text": result["response"], "model": result["model"] or session["model"],
        "provider": "google (agy subscription)", "cost_usd": None, "cost_basis": None,
        "cache_read": usage.get("cache_read_tokens", 0), "cache_write": None,
        "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": usage.get("thinking_tokens"), "attachments": len(staged),
    }


# ---------------------------------------------------------------- main flow

def build_parser():
    parser = argparse.ArgumentParser(prog="llm_chat.py", description=__doc__.splitlines()[0])
    parser.add_argument("--model", "-m", required=True, help="model id; routing rules in SKILL.md")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--system", help="system message text (required on the first turn)")
    group.add_argument("--system-file", help="file holding the system message (UTF-8)")
    parser.add_argument("--session", help="session id to continue")
    parser.add_argument("--effort", "-e", help="reasoning effort, e.g. low / medium / high")
    parser.add_argument("--max-tokens", type=int, help="output token cap (reasoning counts toward it)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="seconds, default 600")
    parser.add_argument("--drop-thinking", action="store_true",
                        help="resend earlier turns without their thinking (fixed on the first turn)")
    parser.add_argument("--attach", action="append", metavar="PATH",
                        help="file for the model to read (audio, video, image, PDF, text); agy models only, repeatable")
    return parser


def read_system(opts):
    if opts.system_file:
        try:
            return Path(opts.system_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise ChatError(f"cannot read --system-file: {exc}")
    return opts.system


def new_session(opts, backend, backend_model, system):
    if not system or not system.strip():
        raise ChatError("a new session needs a non-empty --system or --system-file")
    return {"version": 1, "id": str(uuid.uuid4()), "backend": backend,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "system": system,
            "system_sha256": sha256(system), "model_requested": opts.model, "model": backend_model,
            "drop_thinking": bool(opts.drop_thinking), "messages": [], "turns": []}


def continue_session(session, opts, backend, backend_model, system):
    if system is not None and sha256(system) != session["system_sha256"]:
        raise ChatError("system message differs from the one fixed on this session's first turn; "
                        "omit it or pass the identical text")
    if opts.drop_thinking and not session.get("drop_thinking"):
        # Fixed on the first turn: once earlier thinking has been resent, it
        # cannot be taken back, and switching mid-way would mix two conditions.
        raise ChatError("--drop-thinking is fixed on a session's first turn; this session was started without it")
    if FAMILY[backend] != FAMILY[session["backend"]]:
        raise ChatError(f"session {session['id']} runs on {session['backend']}; "
                        f"model {opts.model!r} routes to {backend}")
    if opts.model != session["model_requested"] or backend != session["backend"]:
        # Switching model or HTTP route inside the same backend family: resolve afresh.
        session.update(backend=backend, model_requested=opts.model, model=backend_model)
        session.pop("provider_only", None)


def run_turn(opts, user_text, root):
    backend, backend_model = route(opts.model)
    system = read_system(opts)
    if opts.effort and not EFFORT_PATTERN.match(opts.effort):
        raise ChatError(f"invalid --effort {opts.effort!r}")
    if opts.max_tokens is not None and opts.max_tokens <= 0:
        raise ChatError("--max-tokens must be positive")
    if opts.drop_thinking and FAMILY[backend] == "codex":
        raise ChatError("--drop-thinking is not supported for GPT models: codex keeps each thread's "
                        "reasoning in its own state and offers no way to leave it out")
    if opts.drop_thinking and FAMILY[backend] == "agy":
        raise ChatError("--drop-thinking is not supported for agy models: agy keeps the conversation "
                        "in its own state and offers no way to leave thinking out")
    if opts.attach and FAMILY[backend] != "agy":
        raise ChatError("--attach is supported only on agy models (gemini-* or agy/<slug>)")
    if opts.session:
        if not SESSION_PATTERN.match(opts.session):
            raise ChatError(f"invalid session id {opts.session!r}")
        sid = opts.session
        if not session_path(root, sid).exists():
            raise ChatError(f"session {sid} not found in {root / 'sessions'}")
    else:
        session = new_session(opts, backend, backend_model, system)
        sid = session["id"]
    with SessionLock(root, sid):
        if opts.session:
            session = load_session(root, sid)
            continue_session(session, opts, backend, backend_model, system)
        backend = session["backend"]
        if backend == "openrouter":
            result = call_openrouter(session, user_text, opts)
        elif backend == "deepseek":
            result = call_deepseek(session, user_text, opts)
        elif backend == "claude":
            result = call_claude(session, user_text, opts, root)
        elif backend == "agy":
            result = call_agy(session, user_text, opts, root)
        else:
            result = call_codex(session, user_text, opts, root)
        assistant = result.pop("assistant", None)
        if FAMILY[backend] == "http":
            session["messages"] += [{"role": "user", "content": user_text}, assistant]
        # Lock the concrete id the backend answered with (aliases change over time).
        session["model"] = result["model"]
        meta = {"session": sid, **{k: v for k, v in result.items() if k != "text"}}
        session["turns"].append({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **meta})
        save_session(root, session)
    return result["text"], meta


def main(argv=None, stdin=None, stdout=None, stderr=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    opts = build_parser().parse_args(argv)
    previous = {sig: signal.signal(sig, raise_cancelled) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        if stdin.isatty():
            raise ChatError("pipe the user message through stdin")
        user_text = stdin.read()
        if not user_text.strip():
            raise ChatError("user message on stdin is empty")
        root = ensure_state()
        text, meta = run_turn(opts, user_text, root)
    except ChatError as exc:
        print("llm-chat: error: " + sanitize(exc), file=stderr)
        return 1
    except Cancelled as exc:
        print(f"llm-chat: error: cancelled by signal {exc.signum}; nothing saved for this turn", file=stderr)
        return 130
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    stdout.write(text if text.endswith("\n") else text + "\n")
    stdout.flush()
    print(META_PREFIX + json.dumps(meta, ensure_ascii=False), file=stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
