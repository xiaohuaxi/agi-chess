"""仓内 llm-chat 的 agy acp 路径完整离线测试：
- stdio JSON-RPC 2.0 多轮 session/new 与 session/resume、--sessions-dir
- configOptions model + thought_level 与内置档位 slug（如 gpt-oss-120b-medium + --effort medium）
- ACP usage（inputTokens 不含缓存 → LLM_CHAT_META.input_tokens 补齐含缓存总输入）与 agi_chess.chat.usage 对齐
- 默认零工具 tools: [] 与 --attach / --allow-attach read_file(Path=...) 范围门禁、越界阻断与全局权限检查
- session/request_permission -> reject_once 事前拒绝 -> agi_chess 停赛工具锁（零重试）
- 安全过滤与防思维链泄露拒答原样透传 -> agi_chess 拒答停赛锁（零重试）
- 传输错误重试分类、--accept-recovered 与 stale SHA-256 防复读
- 认证环境变量白名单透传与密钥脱敏（agy_core.redact + llm_chat.sanitize）
全部通过本地假 agy 脚本执行，不调真实模型；每个用例使用独立临时目录。
"""
import contextlib
import errno
import importlib.util
import io
import json
import os
import pathlib
import queue
import resource
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from agi_chess import chat, claude_cli, cli, records

CONV_1 = "11111111-2222-3333-4444-555555555555"
CONV_2 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

FAKE_AGY_SCRIPT = r'''#!%s
import json
import os
import select
import signal
import sys
import time

state_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fake_agy_state.json")
with open(state_file, "r", encoding="utf-8") as f:
    state = json.load(f)

calls = state.setdefault("calls", [])
queue = state.get("queue") or [{}]
plan = queue.pop(0) if len(queue) > 1 else queue[0]

call_rec = {
    "pid": os.getpid(),
    "argv": sys.argv[1:],
    "cwd": os.getcwd(),
    "env_keys": sorted(os.environ.keys()),
    "gemini_key_present": "GEMINI_API_KEY" in os.environ,
    "rpc": [],
    "permission_outcomes": [],
}
calls.append(call_rec)

def save():
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)

save()

if plan.get("stderr"):
    sys.stderr.write(plan["stderr"] + "\n")
    sys.stderr.flush()

if plan.get("sleep"):
    time.sleep(float(plan["sleep"]))

if plan.get("exit_immediately") is not None:
    sys.exit(int(plan["exit_immediately"]))

MODELS = plan.get("models") or [
    "gemini-4-carbon",
    "gemini-4-argon",
    "gemini-4-hydrogen",
    "gemini-pro-orchestrator",
    "gemini-3.8-flash",
    "claude-opus-5-5",
    "gpt-oss-120b-medium",
]
NO_TL_MODELS = set(plan.get("no_thought_level_models") or ["gemini-pro-orchestrator", "gpt-oss-120b-medium"])
cur_model = plan.get("initial_model") or "gemini-4-carbon"
cur_tl = plan.get("initial_tl") or "high"
sid = plan.get("session_id") or "%s"

def make_config(model_val, tl_val):
    cfg = [{
        "id": "model",
        "category": "model",
        "currentValue": model_val,
        "options": [{"value": m, "name": m} for m in MODELS],
    }]
    if model_val not in NO_TL_MODELS:
        tl_opts = ["low", "medium", "high", "xhigh"] if model_val == "gemini-4-hydrogen" else ["low", "medium", "high"]
        cfg.append({
            "id": "thought_level",
            "category": "thought_level",
            "currentValue": tl_val if tl_val in tl_opts else tl_opts[-1],
            "options": [{"value": v, "name": v} for v in tl_opts],
        })
    return cfg

def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()

while True:
    raw = sys.stdin.readline()
    if not raw:
        break
    raw = raw.strip()
    if not raw:
        continue
    msg = json.loads(raw)
    call_rec["rpc"].append(msg)
    save()
    req_id = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}

    if method == "initialize":
        send({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": 1}})
    elif method in ("session/new", "session/resume"):
        if plan.get("resume_error") and method == "session/resume":
            send({"jsonrpc": "2.0", "id": req_id, "error": plan["resume_error"]})
            continue
        res_sid = plan.get("override_session_id") or (params.get("sessionId") if method == "session/resume" else sid)
        send({"jsonrpc": "2.0", "id": req_id, "result": {
            "sessionId": res_sid,
            "configOptions": make_config(cur_model, cur_tl),
        }})
        if plan.get("hang_after_session"):
            time.sleep(float(plan["hang_after_session"]))
            sys.exit(0)
    elif method == "session/set_config_option":
        cid = params.get("configId")
        val = params.get("value")
        if cid == "model":
            cur_model = val
        elif cid == "thought_level":
            cur_tl = val
        send({"jsonrpc": "2.0", "id": req_id, "result": {"configOptions": make_config(cur_model, cur_tl)}})
        if plan.get("hang_after_config") and cid == "thought_level":
            time.sleep(float(plan["hang_after_config"]))
            sys.exit(0)
    elif method == "session/prompt":
        if plan.get("ignore_sigint_flush_on_sigterm"):
            late_obj = dict(plan["ignore_sigint_flush_on_sigterm"])
            if "id" not in late_obj and "method" not in late_obj:
                late_obj["id"] = req_id
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            def _on_sigterm(_signum, _frame):
                send(late_obj)
                sys.exit(0)
            signal.signal(signal.SIGTERM, _on_sigterm)
            while True:
                time.sleep(1.0)
        if plan.get("eof_on_prompt"):
            sys.exit(int(plan.get("eof_rc", 0)))
        if plan.get("sleep_on_prompt"):
            time.sleep(float(plan["sleep_on_prompt"]))
        for tc in plan.get("tool_calls") or ():
            tc_args = tc["args"] if "args" in tc else {}
            tc_raw = tc["rawInput"] if "rawInput" in tc else tc_args
            send({
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "sessionId": sid,
                    "update": {
                        "sessionUpdate": "tool_call",
                        "toolCallId": tc.get("id", "call_1"),
                        "name": tc.get("name"),
                        "args": tc_args,
                        "rawInput": tc_raw,
                        "status": "in_progress",
                    },
                },
            })
            send({
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "sessionId": sid,
                    "update": {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": tc.get("id", "call_1"),
                        "status": "completed",
                    },
                },
            })
        if plan.get("request_permission"):
            perm = plan["request_permission"]
            opts = perm["options"] if "options" in perm else [
                {"optionId": "allow_once", "kind": "allow_once"},
                {"optionId": "reject_once", "kind": "reject_once"},
            ]
            p_args = perm["args"] if "args" in perm else {"Path": "/etc/hosts"}
            p_raw = perm["rawInput"] if "rawInput" in perm else p_args
            old_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
            try:
                send({
                    "jsonrpc": "2.0",
                    "id": 900,
                    "method": "session/request_permission",
                    "params": {
                        "sessionId": sid,
                        "options": opts,
                        "toolCall": {
                            "toolCallId": "perm_1",
                            "name": perm.get("name", "read_file"),
                            "args": p_args,
                            "rawInput": p_raw,
                        },
                    },
                })
                rlist, _, _ = select.select([sys.stdin], [], [], 2.0)
                if rlist:
                    reply_line = sys.stdin.readline().strip()
                    if reply_line:
                        call_rec["permission_outcomes"].append(json.loads(reply_line))
                        save()
            finally:
                signal.signal(signal.SIGINT, old_int)
            if perm.get("try_execute_after_reply"):
                time.sleep(0.5)
                call_rec["tool_executed_after_cancel"] = True
                save()
        for chunk in plan.get("chunks", ["着法: e2e4"]):
            if chunk:
                send({
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": sid,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": chunk},
                        },
                    },
                })
        if plan.get("sleep_after_chunks"):
            time.sleep(float(plan["sleep_after_chunks"]))
        if plan.get("eof_after_chunks"):
            sys.exit(int(plan.get("eof_rc", 0)))
        if plan.get("prompt_error"):
            send({"jsonrpc": "2.0", "id": req_id, "error": plan["prompt_error"]})
            continue
        res = {
            "stopReason": plan.get("stopReason", "end_turn"),
        }
        if "usage" in plan:
            res["usage"] = plan["usage"]
        else:
            res["usage"] = {
                "inputTokens": 400,
                "cachedReadTokens": 100,
                "cachedWriteTokens": 0,
                "outputTokens": 25,
                "thoughtTokens": 15,
                "totalTokens": 525,
            }
        if "result_response" in plan:
            res["response"] = plan["result_response"]
        if "result_error" in plan:
            res["error"] = plan["result_error"]
        send({"jsonrpc": "2.0", "id": req_id, "result": res})
''' % (sys.executable, CONV_1)


def load_llm_chat():
    spec = importlib.util.spec_from_file_location("repo_llm_chat_agy_test", chat._REPO_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeIn(io.StringIO):
    def isatty(self):
        return False


class AgyAcpHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="llm-chat-acp-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        claude_cli.STOP.clear()
        self.addCleanup(claude_cli.STOP.clear)

        self.home = os.path.join(self.tmp, "home")
        self.state_home = os.path.join(self.tmp, "state")
        self.bin_dir = os.path.join(self.tmp, "bin")
        os.makedirs(self.home)
        os.makedirs(self.state_home)
        os.makedirs(self.bin_dir)

        self.fake_agy = os.path.join(self.bin_dir, "agy")
        with open(self.fake_agy, "w", encoding="utf-8") as f:
            f.write(FAKE_AGY_SCRIPT)
        os.chmod(self.fake_agy, 0o755)

        self.state_file = os.path.join(self.tmp, "fake_agy_state.json")
        self.set_plans([{}])

        env_patch = mock.patch.dict(
            os.environ,
            {
                "HOME": self.home,
                "XDG_STATE_HOME": self.state_home,
                "PATH": self.bin_dir + os.pathsep + os.environ.get("PATH", ""),
                "AGY_BIN": self.fake_agy,
                "FAKE_AGY_STATE": self.state_file,
            },
        )
        env_patch.start()
        self.addCleanup(env_patch.stop)

        for p in (mock.patch.object(sys, "path", list(sys.path)), mock.patch.dict(sys.modules)):
            p.start()
            self.addCleanup(p.stop)
        sys.modules.pop("agy_core", None)
        self.mod = load_llm_chat()
        self.core = self.mod.agy_core()

    def set_plans(self, plans):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump({"queue": list(plans), "calls": []}, f, ensure_ascii=False)

    def agy_calls(self):
        with open(self.state_file, "r", encoding="utf-8") as f:
            return json.load(f).get("calls", [])

    def invoke(self, argv, text="着法？"):
        out, err = io.StringIO(), io.StringIO()
        rc = self.mod.main(argv, FakeIn(text), out, err)
        return rc, out.getvalue(), err.getvalue()

    # -------------------------------------------------------- 1. 多轮 ACP 续接、模型档位与 Token 口径

    def test_multiturn_acp_session_resume_and_token_accounting(self):
        sdir = os.path.join(self.tmp, "run", ".llm-chat", "sessions")
        self.set_plans([
            {
                "session_id": CONV_1,
                "chunks": ["理由：中心控制\n", "着法: e2e4"],
                "usage": {
                    "inputTokens": 12986,
                    "cachedReadTokens": 0,
                    "cachedWriteTokens": 0,
                    "outputTokens": 47,
                    "thoughtTokens": 30,
                    "totalTokens": 13033,
                },
            },
            {
                "session_id": CONV_1,
                "chunks": ["着法: g1f3"],
                "usage": {
                    "inputTokens": 5342,
                    "cachedReadTokens": 8154,
                    "cachedWriteTokens": 0,
                    "outputTokens": 19,
                    "thoughtTokens": 18,
                    "totalTokens": 13515,
                },
            },
        ])

        rc1, out1, err1 = self.invoke(
            ["-m", "gemini-4-carbon", "--effort", "medium", "--sessions-dir", sdir, "--system", "你是棋手"]
        )
        self.assertEqual(rc1, 0, err1)
        self.assertEqual(out1, "理由：中心控制\n着法: e2e4\n")
        meta1 = json.loads(err1.split(self.mod.META_PREFIX, 1)[1])
        self.assertEqual(meta1["input_tokens"], 12986)
        self.assertEqual(meta1["cache_read"], 0)
        self.assertEqual(meta1["cache_write"], 0)
        self.assertEqual(meta1["output_tokens"], 47)
        self.assertEqual(meta1["reasoning_tokens"], 30)

        # 首轮默认零工具：agent 定义写 tools: []，且绝不传 --dangerously-skip-permissions 或 --sandbox
        agent_md = pathlib.Path(self.state_home) / "llm-chat" / "agy" / meta1["session"] / ".agents" / "agents" / "llm-chat-session.md"
        fm = self.core.parse_agent_frontmatter(agent_md.read_text(encoding="utf-8"))
        self.assertEqual(fm["tools"], [])
        call1 = self.agy_calls()[0]
        self.assertEqual(call1["argv"], ["acp", "--agent", "llm-chat-session"])
        self.assertNotIn("--dangerously-skip-permissions", call1["argv"])
        self.assertNotIn("--sandbox", call1["argv"])

        new_rpc = next(m for m in call1["rpc"] if m.get("method") == "session/new")
        self.assertEqual(new_rpc["params"]["mcpServers"], [])
        tl_rpc = [m for m in call1["rpc"] if m.get("method") == "session/set_config_option"]
        self.assertEqual([(m["params"]["configId"], m["params"]["value"]) for m in tl_rpc], [("thought_level", "medium")])

        # 第二轮走 session/resume，且 ACP inputTokens(5342) + cachedReadTokens(8154) = 13496
        rc2, out2, err2 = self.invoke(
            ["-m", "gemini-4-carbon", "--effort", "medium", "--sessions-dir", sdir, "--session", meta1["session"]]
        )
        self.assertEqual(rc2, 0, err2)
        self.assertEqual(out2, "着法: g1f3\n")
        meta2 = json.loads(err2.split(self.mod.META_PREFIX, 1)[1])
        self.assertEqual(meta2["input_tokens"], 13496)
        self.assertEqual(meta2["cache_read"], 8154)
        self.assertEqual(meta2["output_tokens"], 19)
        self.assertEqual(meta2["reasoning_tokens"], 18)

        # 与 agi_chess/chat.py:usage() 对接后，in 精确还原为未命中缓存的 5342
        u = chat.usage({"result": "着法: g1f3", "meta": meta2}, "agy")
        self.assertEqual(u["in"], 5342)
        self.assertEqual(u["cache_read"], 8154)
        self.assertEqual(u["cache_write"], 0)
        self.assertEqual(u["out"], 19)
        self.assertEqual(u["think"], 18)
        self.assertEqual(u["text_out"], 1)

        call2 = self.agy_calls()[1]
        res_rpc = next(m for m in call2["rpc"] if m.get("method") == "session/resume")
        self.assertEqual(res_rpc["params"]["sessionId"], CONV_1)
        self.assertEqual(res_rpc["params"]["mcpServers"], [])

    def test_model_and_effort_combinations_including_fixed_effort_slug(self):
        # 1) 带档位后缀的模型名 + 显式同档 --effort（如 agy/claude-opus-5-5-high --effort high）
        self.set_plans([{"session_id": CONV_1, "chunks": ["OK"]}, {"session_id": CONV_1, "chunks": ["OK2"]}])
        rc, _, err = self.invoke(["-m", "agy/claude-opus-5-5-high", "--effort", "high", "--system", "sys"])
        self.assertEqual(rc, 0, err)
        meta = json.loads(err.split(self.mod.META_PREFIX, 1)[1])
        self.assertEqual(meta["model"], "claude-opus-5-5")
        cfgs = [m["params"] for m in self.agy_calls()[0]["rpc"] if m.get("method") == "session/set_config_option"]
        self.assertEqual(cfgs[0]["configId"], "model")
        self.assertEqual(cfgs[0]["value"], "claude-opus-5-5")

        # 省略 --effort 续跑带后缀 slug 时，隐含档位不会丢失
        self.set_plans([{"session_id": CONV_1, "initial_tl": "low", "chunks": ["OK2"]}])
        rc2, _, err2 = self.invoke(["-m", "agy/claude-opus-5-5-high", "--session", meta["session"]])
        self.assertEqual(rc2, 0, err2)
        cfgs2 = [(m["params"]["configId"], m["params"]["value"])
                 for m in self.agy_calls()[0]["rpc"] if m.get("method") == "session/set_config_option"]
        self.assertIn(("thought_level", "high"), cfgs2)

        # 2) 内置固定档位且无 thought_level 选项的模型：gpt-oss-120b-medium + --effort medium 放行
        self.set_plans([{"session_id": CONV_2, "chunks": ["OK"]}])
        rc3, _, err3 = self.invoke(["-m", "agy/gpt-oss-120b-medium", "--effort", "medium", "--system", "sys"])
        self.assertEqual(rc3, 0, err3)
        cfgs3 = [(m["params"]["configId"], m["params"]["value"])
                 for m in self.agy_calls()[0]["rpc"] if m.get("method") == "session/set_config_option"]
        self.assertEqual(cfgs3, [("model", "gpt-oss-120b-medium")])

        # 3) 无 thought_level 且名字不含对应后缀（如 gemini-pro-orchestrator + --effort medium）报 config 错误且不算传输失败
        self.set_plans([{"session_id": CONV_2, "chunks": ["OK"]}])
        rc4, out4, err4 = self.invoke(["-m", "agy/gemini-pro-orchestrator", "--effort", "medium", "--system", "sys"])
        self.assertEqual(rc4, 1)
        detail4 = json.loads(err4.split(self.mod.ERROR_PREFIX, 1)[1])
        self.assertEqual(detail4, {"backend": "agy", "kind": "config", "source": "config"})
        self.assertFalse(chat.transport_failure(out4, err4, rc4, False))

    # -------------------------------------------------------- 2. 零工具默认与 --attach / --allow-attach

    def test_zero_tool_default_blocks_any_tool_and_rejects_later_attach(self):
        self.set_plans([{"session_id": CONV_1, "chunks": ["OK"]}])
        rc, _, err = self.invoke(["-m", "gemini-3.8-flash", "--effort", "medium", "--system", "sys"])
        self.assertEqual(rc, 0, err)
        sid = json.loads(err.split(self.mod.META_PREFIX, 1)[1])["session"]

        # 在 allow_attach=false 的会话后续传 --attach：立即报 config 错且不起 agy
        att = os.path.join(self.tmp, "note.txt")
        pathlib.Path(att).write_text("hello", encoding="utf-8")
        self.set_plans([{"session_id": CONV_1, "chunks": ["NO"]}])
        rc2, _, err2 = self.invoke(
            ["-m", "gemini-3.8-flash", "--effort", "medium", "--session", sid, "--attach", att]
        )
        self.assertEqual(rc2, 1)
        self.assertIn("--allow-attach", err2)
        self.assertEqual(len(self.agy_calls()), 0)

        # 默认纯文本会话里即便后端返回 read_file 工具事件，也因不在 allowed_tools=() 而判越权工具
        self.set_plans([{
            "session_id": CONV_1,
            "tool_calls": [{"name": "read_file", "args": {"Path": att}}],
            "chunks": ["sneaky"],
        }])
        rc3, out3, err3 = self.invoke(["-m", "gemini-3.8-flash", "--effort", "medium", "--session", sid])
        self.assertEqual(rc3, 1)
        self.assertIn("agy called tools outside this preset:", err3)
        self.assertTrue(claude_cli.tool_error_text(err3))
        self.assertFalse(chat.transport_failure(out3, err3, rc3, False))

    def test_attach_and_allow_attach_valid_read_and_out_of_bounds_rejection(self):
        att1 = os.path.join(self.tmp, "a.txt")
        att2 = os.path.join(self.tmp, "b.txt")
        unattached = os.path.join(self.tmp, "secret.txt")
        for p, content in ((att1, "A"), (att2, "B"), (unattached, "S")):
            pathlib.Path(p).write_text(content, encoding="utf-8")

        # 首轮 --allow-attach 预留附件能力，次轮传 --attach 读取合法附件成功
        self.set_plans([{"session_id": CONV_1, "chunks": ["ready"]}])
        rc1, _, err1 = self.invoke(
            ["-m", "gemini-3.8-flash", "--effort", "medium", "--allow-attach", "--system", "sys"]
        )
        self.assertEqual(rc1, 0, err1)
        sid = json.loads(err1.split(self.mod.META_PREFIX, 1)[1])["session"]
        agent_md = pathlib.Path(self.state_home) / "llm-chat" / "agy" / sid / ".agents" / "agents" / "llm-chat-session.md"
        self.assertEqual(self.core.parse_agent_frontmatter(agent_md.read_text(encoding="utf-8"))["tools"], ["read_file"])

        staged_expected = pathlib.Path(self.state_home) / "llm-chat" / "agy" / sid / "files" / "turn-2" / "1-a.txt"
        self.set_plans([{
            "session_id": CONV_1,
            "tool_calls": [{"name": "read_file", "args": {"Path": str(staged_expected)}}],
            "chunks": ["read A"],
        }])
        rc2, out2, err2 = self.invoke(
            ["-m", "gemini-3.8-flash", "--effort", "medium", "--session", sid, "--attach", att1]
        )
        self.assertEqual((rc2, out2), (0, "read A\n"), err2)
        self.assertEqual(json.loads(err2.split(self.mod.META_PREFIX, 1)[1])["attachments"], 1)

        # 第 3 轮：模型用 read_file(Path=...) 读未附加文件（或空路径）-> 报 'agy called tools besides attached view_file' 且清理当轮附件
        staged_turn3 = pathlib.Path(self.state_home) / "llm-chat" / "agy" / sid / "files" / "turn-3" / "1-b.txt"
        self.set_plans([{
            "session_id": CONV_1,
            "tool_calls": [{"name": "read_file", "args": {"Path": unattached}}],
            "chunks": ["bad read"],
        }])
        rc3, out3, err3 = self.invoke(
            ["-m", "gemini-3.8-flash", "--effort", "medium", "--session", sid, "--attach", att2]
        )
        self.assertEqual(rc3, 1)
        self.assertIn("agy called tools besides attached view_file:", err3)
        detail3 = json.loads(err3.split(self.mod.ERROR_PREFIX, 1)[1])
        self.assertEqual(detail3, {"backend": "agy", "kind": "tool", "source": "tool"})
        self.assertFalse(staged_turn3.exists())
        self.assertTrue(claude_cli.tool_error_text(err3))
        self.assertFalse(chat.transport_failure(out3, err3, rc3, False))

    def test_legacy_session_without_allow_attach_tightens_to_zero_tools_and_file_grants_checked(self):
        # 模拟旧版 <sid>.json（无 allow_attach 键，且旧版工作区留有 tools: [view_file]）
        self.set_plans([{"session_id": CONV_1, "chunks": ["init"]}])
        rc, _, err = self.invoke(["-m", "gemini-3.8-flash", "--effort", "medium", "--allow-attach", "--system", "sys"])
        self.assertEqual(rc, 0, err)
        sid = json.loads(err.split(self.mod.META_PREFIX, 1)[1])["session"]
        sfile = pathlib.Path(self.state_home) / "llm-chat" / "sessions" / f"{sid}.json"
        sdata = json.loads(sfile.read_text(encoding="utf-8"))
        sdata.pop("allow_attach", None)
        sfile.write_text(json.dumps(sdata), encoding="utf-8")
        agent_md = pathlib.Path(self.state_home) / "llm-chat" / "agy" / sid / ".agents" / "agents" / "llm-chat-session.md"
        agent_md.write_text(self.core.agent_markdown("llm-chat-session", "old", ["view_file"], False, "sys"), encoding="utf-8")

        self.set_plans([{"session_id": CONV_1, "chunks": ["resumed"]}])
        rc2, _, err2 = self.invoke(["-m", "gemini-3.8-flash", "--effort", "medium", "--session", sid])
        self.assertEqual(rc2, 0, err2)
        self.assertEqual(self.core.parse_agent_frontmatter(agent_md.read_text(encoding="utf-8"))["tools"], [])

        # 用户全局 settings.json 若放宽了 read_file(...) 权限，附件会话直接拒跑
        settings_dir = pathlib.Path(self.home) / ".gemini" / "antigravity-cli"
        settings_dir.mkdir(parents=True, exist_ok=True)
        (settings_dir / "settings.json").write_text(json.dumps({"permissions": {"allow": ["read_file(/**)"]}}), encoding="utf-8")
        rc3, _, err3 = self.invoke(["-m", "gemini-3.8-flash", "--effort", "medium", "--allow-attach", "--system", "sys"])
        self.assertEqual(rc3, 1)
        self.assertIn("widen file access", err3)

    # -------------------------------------------------------- 3. 权限事前拒绝与 agi_chess 工具锁 / 拒答锁联动

    def test_permission_request_rejected_with_reject_once_and_locks_agi_chess_game(self):
        self.set_plans([{
            "session_id": CONV_1,
            "request_permission": {
                "name": "read_file",
                "args": {"Path": "/etc/passwd"},
                "options": [
                    {"optionId": "opt_allow", "kind": "allow_once"},
                    {"optionId": "opt_reject", "kind": "reject_once"},
                ],
            },
            "chunks": ["着法: e2e4"],
        }])
        runs_out = os.path.join(self.tmp, "runs")
        with mock.patch.object(chat, "SCRIPT", str(chat._REPO_SCRIPT)), \
                mock.patch.object(cli, "commit", return_value="test"), \
                mock.patch.object(claude_cli, "_wait") as wait_mock, \
                contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main([
                "play", "--game", "chess", "--tag", "perm-lock", "--out", runs_out,
                "--white", "agy:gemini-3.8-flash", "--black", "random",
                "--effort", "medium", "--max-plies", "2", "--agy-retries", "2",
            ])
            self.assertEqual(rc, 3)
            # 核实假 agy 只被调了 1 次（绝不触发 agy 传输重发），且收到了同步回复的 opt_reject
            calls = self.agy_calls()
            self.assertEqual(len(calls), 1)
            wait_mock.assert_not_called()
            self.assertEqual(
                calls[0]["permission_outcomes"],
                [{"jsonrpc": "2.0", "id": 900, "result": {"outcome": {"outcome": "selected", "optionId": "opt_reject"}}}],
            )
            # 再次 resume 被工具锁挡住
            gdir = os.path.join(runs_out, "perm-lock")
            self.assertEqual(cli.main(["resume", gdir]), 3)
            self.assertEqual(len(self.agy_calls()), 1)

        rows = cli.records.read(os.path.join(runs_out, "perm-lock", "game.jsonl"))
        tool_rec = cli.runner.tool_record(rows)
        self.assertIsNotNone(tool_rec)
        self.assertEqual((tool_rec["type"], tool_rec["source"]), ("flag", "tool_call"))

        # 双保险核验：即便错误文案改变，仅凭结构化 LLM_CHAT_ERROR source in ('tool', 'denied') 也认作工具事件
        for src, kind in (("denied", "permission"), ("tool", "tool")):
            synthetic = 'llm-chat: error: future wording\nLLM_CHAT_ERROR {"backend": "agy", "kind": "%s", "source": "%s"}\n' % (kind, src)
            self.assertTrue(claude_cli.tool_error_text(synthetic))
            self.assertFalse(chat.transport_failure("", synthetic, 1, False))

    def test_safety_filter_and_refusal_pass_through_and_lock_agi_chess(self):
        for plan in (
            {"session_id": CONV_1, "chunks": ["This request was blocked by Gemini's filters."]},
            {"session_id": CONV_1, "prompt_error": {"code": -32603, "message": "I cannot reveal hidden chain-of-thought reasoning."}},
        ):
            with self.subTest(plan=plan):
                self.set_plans([plan])
                tag = "flt-" + ("notice" if "chunks" in plan else "cot")
                runs_out = os.path.join(self.tmp, tag)
                with mock.patch.object(chat, "SCRIPT", str(chat._REPO_SCRIPT)), \
                        mock.patch.object(cli, "commit", return_value="test"), \
                        mock.patch.object(claude_cli, "_wait") as wait_mock, \
                        contextlib.redirect_stdout(io.StringIO()):
                    rc = cli.main([
                        "play", "--game", "chess", "--tag", "g", "--out", runs_out,
                        "--white", "agy:gemini-3.8-flash", "--black", "random",
                        "--effort", "medium", "--max-plies", "1", "--agy-retries", "2",
                    ])
                    self.assertEqual(rc, 3)
                    self.assertEqual(len(self.agy_calls()), 1)
                    wait_mock.assert_not_called()
                    self.assertEqual(cli.main(["resume", os.path.join(runs_out, "g")]), 3)
                rows = cli.records.read(os.path.join(runs_out, "g", "game.jsonl"))
                self.assertEqual(rows[-1]["type"], "refusal")

    # -------------------------------------------------------- 4. 传输错误分类与 --accept-recovered / stale

    def test_transport_classification_and_accept_recovered(self):
        sdir = os.path.join(self.tmp, "rec-sessions")
        self.set_plans([{"session_id": CONV_1, "chunks": ["着法: e2e4"]}])
        rc, _, err = self.invoke(["-m", "gemini-4-carbon", "--effort", "high", "--sessions-dir", sdir, "--system", "sys"])
        self.assertEqual(rc, 0, err)
        sid = json.loads(err.split(self.mod.META_PREFIX, 1)[1])["session"]

        # 传输类 source：exit / no_result / status / print_timeout / hard_timeout -> transport_failure 为 True
        transport_plans = [
            ({"exit_immediately": 3, "stderr": 'AGY_ERROR: {"code": 503}'}, "exit", ["--timeout", "5"]),
            ({"session_id": CONV_1, "eof_on_prompt": True, "eof_rc": 0}, "no_result", ["--timeout", "5"]),
            ({"session_id": CONV_1, "prompt_error": {"code": -32603, "message": "The stream was interrupted."}}, "status", ["--timeout", "5"]),
            ({"session_id": CONV_1, "eof_on_prompt": True, "eof_rc": 0, "stderr": "print timeout after 5s with turn in progress"}, "print_timeout", ["--timeout", "5"]),
            ({"session_id": CONV_1, "sleep_on_prompt": 5.0}, "hard_timeout", ["--timeout", "1"]),
        ]
        for plan, expected_src, extra_args in transport_plans:
            with self.subTest(source=expected_src):
                self.set_plans([plan])
                rc_t, out_t, err_t = self.invoke(
                    ["-m", "gemini-4-carbon", "--effort", "high", "--sessions-dir", sdir, "--session", sid, *extra_args]
                )
                self.assertEqual(rc_t, 1)
                detail = json.loads(err_t.split(self.mod.ERROR_PREFIX, 1)[1])
                self.assertEqual(detail["source"], expected_src)
                self.assertTrue(chat.transport_failure(out_t, err_t, rc_t, False))

        # 非传输类 source：empty / conversation -> transport_failure 为 False
        for plan, expected_src in (
            ({"session_id": CONV_1, "chunks": ["   "]}, "empty"),
            ({"override_session_id": CONV_2, "chunks": ["着法: d2d4"]}, "conversation"),
        ):
            with self.subTest(source=expected_src):
                self.set_plans([plan])
                rc_n, out_n, err_n = self.invoke(
                    ["-m", "gemini-4-carbon", "--effort", "high", "--sessions-dir", sdir, "--session", sid]
                )
                self.assertEqual(rc_n, 1)
                self.assertEqual(json.loads(err_n.split(self.mod.ERROR_PREFIX, 1)[1])["source"], expected_src)
                self.assertFalse(chat.transport_failure(out_n, err_n, rc_n, False))

        # --accept-recovered：stopReason 非 end_turn 但返回完整新答复时采用，重复上一轮答复则按 stale 拒收
        rec_plan = {
            "session_id": CONV_1,
            "chunks": ["着法: d2d4"],
            "stopReason": "ERROR",
            "result_response": "着法: d2d4",
            "result_error": "The stream was interrupted.",
        }
        self.set_plans([rec_plan])
        rc_r1, out_r1, err_r1 = self.invoke(
            ["-m", "gemini-4-carbon", "--effort", "high", "--sessions-dir", sdir, "--session", sid, "--accept-recovered"]
        )
        self.assertEqual((rc_r1, out_r1), (0, "着法: d2d4\n"), err_r1)
        self.assertEqual(json.loads(err_r1.split(self.mod.META_PREFIX, 1)[1])["recovered"]["status"], "ERROR")

        self.set_plans([rec_plan])
        rc_r2, out_r2, err_r2 = self.invoke(
            ["-m", "gemini-4-carbon", "--effort", "high", "--sessions-dir", sdir, "--session", sid, "--accept-recovered"]
        )
        self.assertEqual(rc_r2, 1)
        self.assertEqual(json.loads(err_r2.split(self.mod.ERROR_PREFIX, 1)[1])["source"], "stale")
        self.assertFalse(chat.transport_failure(out_r2, err_r2, rc_r2, False))

    def test_only_agy_supports_allow_attach_and_accept_recovered(self):
        with mock.patch.dict(os.environ, {"API_KEY_OPENROUTER": "fake-key-for-test"}):
            for flag in ("--accept-recovered", "--allow-attach"):
                rc, _, err = self.invoke(["-m", "openrouter:openai/gpt-5", "--system", "s", flag])
                self.assertEqual(rc, 1)
                self.assertIn(f"{flag} is supported only on agy", err)

    # -------------------------------------------------------- 5. 审查回归用例（P0 / P1 全覆盖）

    def test_permission_request_option_order_allow_only_and_empty_options(self):
        # 1) allow_once 排在末尾、reject_always 在前，且 args={}、真实路径在 rawInput -> 必须选 reject_always，绝不点末尾 allow_once
        self.set_plans([{
            "session_id": CONV_1,
            "request_permission": {
                "name": "read_file",
                "args": {},
                "rawInput": {"Path": "/etc/shadow"},
                "options": [
                    {"optionId": "deny_all", "kind": "reject_always"},
                    {"optionId": "allow_1", "kind": "allow_once"},
                ],
            },
            "chunks": ["着法: e2e4"],
        }])
        rc1, out1, err1 = self.invoke(["-m", "gemini-3.8-flash", "--effort", "medium", "--system", "sys"])
        self.assertEqual((rc1, out1), (1, ""))
        self.assertIn("/etc/shadow", err1)
        self.assertEqual(
            self.agy_calls()[0]["permission_outcomes"],
            [{"jsonrpc": "2.0", "id": 900, "result": {"outcome": {"outcome": "selected", "optionId": "deny_all"}}}],
        )
        self.assertEqual(json.loads(err1.split(self.mod.ERROR_PREFIX, 1)[1])["source"], "denied")

        # 2) 仅含允许项、空 options、缺失或非标准未知 kind（只认 reject_once / reject_always）：
        #    必须回 {"outcome": {"outcome": "cancelled"}} 并立即终止子进程组，工具没机会在回复后执行
        core = self.mod.agy_core()
        self.assertIsNone(core._select_reject_option_id([{"optionId": "reject_custom", "kind": None}]))
        self.assertIsNone(core._select_reject_option_id([{"optionId": "deny_once", "kind": ""}]))
        self.assertIsNone(core._select_reject_option_id([{"optionId": "opt_x", "kind": "deny_once"}]))
        self.assertIsNone(core._select_reject_option_id([{"optionId": "opt_u", "kind": "reject_unknown"}]))
        self.assertEqual(core._select_reject_option_id([{"optionId": "opt_r1", "kind": "reject_once"}]), "opt_r1")
        self.assertEqual(core._select_reject_option_id([{"optionId": "opt_ra", "kind": "reject_always"}]), "opt_ra")

        for case_name, opts in (
            ("allow_only", [{"optionId": "allow_1", "kind": "allow_once"}, {"optionId": "allow_2", "kind": "allow_always"}]),
            ("empty_opts", []),
            ("disguised_allow", [{"optionId": "allow_secretly", "kind": "reject_once"}]),
            ("missing_kind_reject_id", [{"optionId": "reject_custom", "kind": None}]),
            ("empty_kind_deny_id", [{"optionId": "deny_once", "kind": ""}]),
            ("unknown_reject_kind", [{"optionId": "opt_u", "kind": "reject_unknown"}]),
        ):
            with self.subTest(case=case_name):
                self.set_plans([{
                    "session_id": CONV_1,
                    "request_permission": {
                        "name": "run_command",
                        "args": {"CommandLine": "stockfish"},
                        "options": opts,
                        "try_execute_after_reply": True,
                    },
                    "chunks": ["着法: e2e4"],
                }])
                rc_c, out_c, err_c = self.invoke(["-m", "gemini-3.8-flash", "--effort", "medium", "--system", "sys"])
                self.assertEqual((rc_c, out_c), (1, ""))
                call_rec = self.agy_calls()[0]
                self.assertEqual(
                    call_rec["permission_outcomes"],
                    [{"jsonrpc": "2.0", "id": 900, "result": {"outcome": {"outcome": "cancelled"}}}],
                )
                self.assertFalse(call_rec.get("tool_executed_after_cancel", False))
                self.assertEqual(json.loads(err_c.split(self.mod.ERROR_PREFIX, 1)[1])["source"], "denied")
                self.assertTrue(claude_cli.tool_error_text(err_c))
                self.assertFalse(chat.transport_failure(out_c, err_c, rc_c, False))

    def test_streamed_refusal_filter_and_stop_reason_refusal_never_retry(self):
        cot_text = "Sorry, I cannot share my internal chain-of-thought reasoning with you. " + ("x" * 900)
        cases = [
            (
                "stream_cot_then_rpc_error",
                {
                    "session_id": CONV_1,
                    "chunks": [cot_text],
                    "prompt_error": {"code": -32603, "message": "The stream was interrupted."},
                },
                "refusal",
            ),
            (
                "stream_cot_then_timeout",
                {
                    "session_id": CONV_1,
                    "chunks": [cot_text],
                    "sleep_after_chunks": 4.0,
                },
                "refusal",
            ),
            (
                "filter_notice_with_cancelled",
                {
                    "session_id": CONV_1,
                    "chunks": ["This request was blocked by Gemini's filters."],
                    "stopReason": "cancelled",
                },
                "filtered",
            ),
            (
                "stop_reason_refusal_with_plain_text",
                {
                    "session_id": CONV_1,
                    "chunks": ["着法: e2e4"],
                    "result_response": "着法: e2e4",
                    "stopReason": "refusal",
                },
                "refusal",
            ),
            (
                "stop_reason_refusal_empty_text",
                {
                    "session_id": CONV_1,
                    "chunks": [""],
                    "stopReason": "refusal",
                },
                "refusal",
            ),
        ]
        for label, plan, expected_src in cases:
            with self.subTest(case=label):
                self.set_plans([plan])
                runs_out = os.path.join(self.tmp, "ref-" + label)
                with mock.patch.object(chat, "SCRIPT", str(chat._REPO_SCRIPT)), \
                        mock.patch.object(cli, "commit", return_value="test"), \
                        mock.patch.object(claude_cli, "_wait") as wait_mock, \
                        contextlib.redirect_stdout(io.StringIO()):
                    rc = cli.main([
                        "play", "--game", "chess", "--tag", "g", "--out", runs_out,
                        "--white", "agy:gemini-3.8-flash", "--black", "random",
                        "--effort", "medium", "--max-plies", "1", "--agy-retries", "2",
                        "--timeout", "1",
                    ])
                    self.assertEqual(rc, 3)
                    self.assertEqual(len(self.agy_calls()), 1)
                    wait_mock.assert_not_called()
                    self.assertEqual(cli.main(["resume", os.path.join(runs_out, "g")]), 3)
                rows = cli.records.read(os.path.join(runs_out, "g", "game.jsonl"))
                self.assertEqual(rows[-1]["type"], "refusal")
                ev_err = rows[-1]["evidence"]["response"]["refusal_evidence"]["stderr"]
                detail = json.loads(ev_err.split(self.mod.ERROR_PREFIX, 1)[1])
                self.assertEqual(detail["source"], expected_src)

        # 双保险：即便错误文案完全不带关键字，LLM_CHAT_ERROR 的 source/kind 为 refusal 或 filtered 也被 refusal_text 识别
        for src in ("refusal", "filtered"):
            synthetic = 'llm-chat: error: opaque refusal\nLLM_CHAT_ERROR {"backend": "agy", "kind": "%s", "source": "%s"}\n' % (src, src)
            self.assertTrue(claude_cli.refusal_text(synthetic))
            self.assertFalse(chat.transport_failure("", synthetic, 1, False))

        # 非拒答流式文本后接 RPC 错误时，流式残片也拼入报错供诊断，但仍属 status 传输失败
        self.set_plans([{
            "session_id": CONV_1,
            "chunks": ["正在思考中心控制……"],
            "prompt_error": {"code": -32603, "message": "The stream was interrupted."},
        }])
        rc_s, out_s, err_s = self.invoke(["-m", "gemini-3.8-flash", "--effort", "medium", "--system", "sys"])
        self.assertEqual(rc_s, 1)
        self.assertIn("streamed: 正在思考中心控制", err_s)
        self.assertFalse(claude_cli.refusal_text(err_s))
        self.assertTrue(chat.transport_failure(out_s, err_s, rc_s, False))

    def test_accept_recovered_rejects_partial_stream_and_mismatched_end_turn(self):
        reject_plans = [
            (
                "cancelled_partial_stream",
                {"session_id": CONV_1, "chunks": ["着法: e2e4"], "stopReason": "cancelled"},
                "cancelled",
                False,
            ),
            (
                "cancelled_even_with_resp",
                {"session_id": CONV_1, "chunks": ["着法: e2e4"], "result_response": "着法: e2e4", "stopReason": "cancelled"},
                "cancelled",
                False,
            ),
            (
                "error_partial_stream_no_resp",
                {"session_id": CONV_1, "chunks": ["着法: e2e4"], "stopReason": "ERROR"},
                "status",
                True,
            ),
            (
                "error_mismatched_stream_vs_resp",
                {"session_id": CONV_1, "chunks": ["着法: e2e4"], "result_response": "着法: d2d4", "stopReason": "ERROR"},
                "protocol",
                False,
            ),
            (
                "max_turn_requests_with_resp",
                {"session_id": CONV_1, "chunks": ["着法: e2e4"], "result_response": "着法: e2e4", "stopReason": "max_turn_requests"},
                "max_turn_requests",
                False,
            ),
            (
                "rpc_error_edata_cancelled",
                {
                    "session_id": CONV_1,
                    "chunks": ["着法: e2e4"],
                    "prompt_error": {"code": -32000, "message": "Turn cancelled", "data": {"stopReason": "cancelled"}},
                },
                "cancelled",
                False,
            ),
            (
                "end_turn_disagrees",
                {"session_id": CONV_1, "chunks": ["着法: e2e4"], "result_response": "着法: d2d4", "stopReason": "end_turn"},
                "protocol",
                False,
            ),
        ]
        for label, plan, exp_source, exp_transport in reject_plans:
            with self.subTest(case=label):
                self.set_plans([plan])
                rc, out, err = self.invoke(
                    ["-m", "gemini-4-carbon", "--effort", "high", "--system", "sys", "--accept-recovered"]
                )
                self.assertEqual((rc, out), (1, ""), err)
                detail = json.loads(err.split(self.mod.ERROR_PREFIX, 1)[1])
                self.assertEqual(detail["source"], exp_source)
                self.assertEqual(chat.transport_failure(out, err, rc, False), exp_transport)

        # 端到端对局验证：cancelled 与流/结果矛盾均不进 --agy-retries 自动重发（只调 1 次即暂停）
        for e2e_label, e2e_plan in (
            ("cancelled_no_retry", {"session_id": CONV_1, "chunks": ["着法: e2e4"], "stopReason": "cancelled"}),
            ("disagree_no_retry", {"session_id": CONV_1, "chunks": ["着法: e2e4"], "result_response": "着法: d2d4", "stopReason": "end_turn"}),
        ):
            with self.subTest(e2e=e2e_label):
                self.set_plans([
                    e2e_plan,
                    {"session_id": CONV_1, "chunks": ["着法: e2e4"]},
                ])
                runs_out = os.path.join(self.tmp, "noret-" + e2e_label)
                with mock.patch.object(chat, "SCRIPT", str(chat._REPO_SCRIPT)), \
                        mock.patch.object(cli, "commit", return_value="test"), \
                        mock.patch.object(claude_cli, "_wait") as wait_mock, \
                        contextlib.redirect_stdout(io.StringIO()):
                    rc = cli.main([
                        "play", "--game", "chess", "--tag", "g", "--out", runs_out,
                        "--white", "agy:gemini-3.8-flash", "--black", "random",
                        "--effort", "medium", "--max-plies", "1", "--agy-retries", "2",
                    ])
                self.assertEqual(rc, 3)
                self.assertEqual(len(self.agy_calls()), 1)
                wait_mock.assert_not_called()

    def test_cached_write_tokens_and_missing_usage_none_semantics(self):
        # 1) 非零 cachedWriteTokens 精确进入 META -> chat.usage -> records._known
        self.set_plans([{
            "session_id": CONV_1,
            "chunks": ["着法: e2e4"],
            "usage": {
                "inputTokens": 10,
                "cachedReadTokens": 20,
                "cachedWriteTokens": 30,
                "outputTokens": 5,
                "thoughtTokens": 2,
                "totalTokens": 65,
            },
        }])
        rc1, _, err1 = self.invoke(["-m", "gemini-4-carbon", "--effort", "medium", "--system", "sys"])
        self.assertEqual(rc1, 0, err1)
        meta1 = json.loads(err1.split(self.mod.META_PREFIX, 1)[1])
        self.assertEqual(meta1["input_tokens"], 30)
        self.assertEqual(meta1["cache_read"], 20)
        self.assertEqual(meta1["cache_write"], 30)
        self.assertEqual(meta1["output_tokens"], 5)
        self.assertEqual(meta1["reasoning_tokens"], 2)

        u1 = chat.usage({"result": "着法: e2e4", "meta": meta1}, "agy")
        self.assertEqual(
            {k: u1[k] for k in ("in", "out", "think", "text_out", "cache_read", "cache_write")},
            {"in": 10, "out": 5, "think": 2, "text_out": 3, "cache_read": 20, "cache_write": 30},
        )
        known1 = records._known({"usage": u1, "claude": {"meta": meta1}})
        self.assertEqual(known1, {"in": True, "out": True, "think": True, "cache_read": True, "cache_write": True})

        # 2) usage 缺失字段时返回 None（不伪造为 0），records._known 识别为 False
        self.set_plans([{"session_id": CONV_2, "chunks": ["着法: d2d4"], "usage": {}}])
        rc2, _, err2 = self.invoke(["-m", "gemini-4-carbon", "--effort", "medium", "--system", "sys"])
        self.assertEqual(rc2, 0, err2)
        meta2 = json.loads(err2.split(self.mod.META_PREFIX, 1)[1])
        for key in ("input_tokens", "cache_read", "cache_write", "output_tokens", "reasoning_tokens"):
            self.assertIsNone(meta2[key], key)
        u2 = chat.usage({"result": "着法: d2d4", "meta": meta2}, "agy")
        known2 = records._known({"usage": u2, "claude": {"meta": meta2}})
        self.assertEqual(known2, {"in": False, "out": False, "think": False, "cache_read": False, "cache_write": False})

    def test_large_prompt_backpressure_timeout_kills_hung_child_cleanly(self):
        # 假 agy 在设置 thought_level 后完全不读 stdin 睡 12 秒，喂入 >200KB 大 prompt，--timeout 1 应按时超时返回并收割子进程
        self.set_plans([{"session_id": CONV_1, "initial_tl": "low", "hang_after_config": 12.0}])
        t0 = time.monotonic()
        rc, out, err = self.invoke(
            ["-m", "gemini-3.8-flash", "--effort", "medium", "--timeout", "1", "--system", "sys"],
            text="P" * 220000,
        )
        elapsed = time.monotonic() - t0
        self.assertEqual((rc, out), (1, ""))
        self.assertLess(elapsed, 7.0, f"send_rpc hung on full stdin pipe ({elapsed:.2f}s)")
        detail = json.loads(err.split(self.mod.ERROR_PREFIX, 1)[1])
        self.assertEqual(detail["source"], "hard_timeout")
        child_pid = self.agy_calls()[0]["pid"]
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid, 0)

    def test_attach_case_alias_samefile_and_raw_input_merge(self):
        att = os.path.join(self.tmp, "board.txt")
        other = os.path.join(self.tmp, "other.txt")
        pathlib.Path(att).write_text("FEN", encoding="utf-8")
        pathlib.Path(other).write_text("NO", encoding="utf-8")

        self.set_plans([{"session_id": CONV_1, "chunks": ["ready"]}])
        rc1, _, err1 = self.invoke(
            ["-m", "gemini-3.8-flash", "--effort", "medium", "--allow-attach", "--system", "sys"]
        )
        self.assertEqual(rc1, 0, err1)
        sid = json.loads(err1.split(self.mod.META_PREFIX, 1)[1])["session"]

        staged = pathlib.Path(self.state_home) / "llm-chat" / "agy" / sid / "files" / "turn-2" / "1-board.txt"
        upper_alias = staged.parent / "1-BOARD.TXT"

        # args={} 为空字典而真实路径在 rawInput，且用大小写别名引用附件：通过 samefile 核验合法放行
        self.set_plans([{
            "session_id": CONV_1,
            "tool_calls": [{"name": "read_file", "args": {}, "rawInput": {"Path": str(upper_alias)}}],
            "chunks": ["read via alias"],
        }])
        real_exists = os.path.exists
        real_samefile = os.path.samefile

        def fake_exists(p):
            return True if str(p).endswith("1-BOARD.TXT") else real_exists(p)

        def fake_samefile(p1, p2):
            if str(p1).endswith("1-BOARD.TXT") and str(p2) == os.path.realpath(str(staged)):
                return True
            return real_samefile(p1, p2)

        # 若宿主 APFS 原生大小写不敏感则直跑真实 OS，否则用精准桩覆盖跨文件系统分支
        probe_lower = os.path.join(self.tmp, "case_probe.txt")
        probe_upper = os.path.join(self.tmp, "CASE_PROBE.TXT")
        pathlib.Path(probe_lower).write_text("1", encoding="utf-8")
        fs_case_insensitive = os.path.exists(probe_upper) and os.path.samefile(probe_lower, probe_upper)

        if fs_case_insensitive:
            rc2, out2, err2 = self.invoke(
                ["-m", "gemini-3.8-flash", "--effort", "medium", "--session", sid, "--attach", att]
            )
        else:
            with mock.patch("os.path.exists", side_effect=fake_exists), \
                    mock.patch("os.path.samefile", side_effect=fake_samefile):
                rc2, out2, err2 = self.invoke(
                    ["-m", "gemini-3.8-flash", "--effort", "medium", "--session", sid, "--attach", att]
                )
        self.assertEqual((rc2, out2), (0, "read via alias\n"), err2)

        # 读取另一个真实存在的未附加文件：samefile 为 False，照常拦截
        self.set_plans([{
            "session_id": CONV_1,
            "tool_calls": [{"name": "read_file", "args": {}, "rawInput": {"Path": other}}],
            "chunks": ["nope"],
        }])
        rc3, _, err3 = self.invoke(["-m", "gemini-3.8-flash", "--effort", "medium", "--session", sid])
        self.assertEqual(rc3, 1)
        self.assertIn("agy called tools besides attached view_file:", err3)

    def test_timeout_drains_queued_security_events_and_preserves_mid_text_refusal(self):
        # 1) 确定性复现队列积压竞态：当安全事件（拒答 / 越权工具 / 权限弹窗）已进入 events 队列但尚未被主线程消费时
        #    恰好同时触发 timed_out，raise_timeout() 必须先纯审计排空队列，绝不能漏判成可重试的 hard_timeout！
        queued_cases = [
            (
                "queued_refusal",
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": CONV_1,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": "I cannot share my internal reasoning."},
                        },
                    },
                }),
                "refusal",
            ),
            (
                "queued_tool_call",
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": CONV_1,
                        "update": {
                            "sessionUpdate": "tool_call",
                            "toolCallId": "race_tc",
                            "name": "run_command",
                            "rawInput": {"CommandLine": "stockfish"},
                            "status": "in_progress",
                        },
                    },
                }),
                "tool",
            ),
            (
                "queued_permission_request",
                json.dumps({
                    "jsonrpc": "2.0",
                    "id": 999,
                    "method": "session/request_permission",
                    "params": {
                        "sessionId": CONV_1,
                        "options": [],
                        "toolCall": {"toolCallId": "p1", "name": "read_file", "rawInput": {"Path": "/etc/passwd"}},
                    },
                }),
                "denied",
            ),
            (
                "queued_rpc_result_refusal",
                json.dumps({
                    "jsonrpc": "2.0",
                    "id": 99,
                    "result": {"stopReason": "refusal"},
                }),
                "refusal",
            ),
            (
                "queued_rpc_error_refusal",
                json.dumps({
                    "jsonrpc": "2.0",
                    "id": 99,
                    "error": {"code": -32000, "message": "I cannot share my internal reasoning."},
                }),
                "refusal",
            ),
            (
                "queued_rpc_result_cancelled",
                json.dumps({
                    "jsonrpc": "2.0",
                    "id": 99,
                    "result": {"stopReason": "cancelled"},
                }),
                "cancelled",
            ),
        ]
        orig_queue_cls = queue.Queue

        for label, queued_json_line, expected_src in queued_cases:
            with self.subTest(race=label):
                self.set_plans([{"session_id": CONV_1, "sleep_on_prompt": 5.0}])

                class RaceQueue(orig_queue_cls):
                    def __init__(self, *a, **kw):
                        super().__init__(*a, **kw)
                        self._prompt_waits = 0

                    def get(self, block=True, timeout=None):
                        try:
                            item = super().get(block=block, timeout=timeout)
                        except queue.Empty:
                            if self._prompt_waits == 0:
                                self._prompt_waits += 1
                                self.put(("stdout", queued_json_line + "\n"))
                            raise
                        if item[0] == "timeout" and self._prompt_waits == 0:
                            self._prompt_waits += 1
                            self.put(("stdout", queued_json_line + "\n"))
                        return item

                with mock.patch("queue.Queue", RaceQueue):
                    rc, out, err = self.invoke(
                        ["-m", "gemini-3.8-flash", "--effort", "medium", "--timeout", "1", "--system", "sys"]
                    )
                self.assertEqual((rc, out), (1, ""), err)
                detail = json.loads(err.split(self.mod.ERROR_PREFIX, 1)[1])
                self.assertEqual(detail["source"], expected_src, err)
                self.assertFalse(chat.transport_failure(out, err, rc, False))
                if expected_src == "refusal":
                    self.assertTrue(claude_cli.refusal_text(err))
                elif expected_src in ("tool", "denied"):
                    self.assertTrue(claude_cli.tool_error_text(err))

        # 2) 子进程完全忽略 SIGINT，直到 stop_group 升级 SIGTERM 时才临终吐出无 method 的 RPC result(stopReason=refusal)：
        #    raise_timeout 必须等 stop_group 终止进程组且 stdout reader 收敛后再排空审计，绝不漏判为 hard_timeout！
        core = self.mod.agy_core()
        self.set_plans([{
            "session_id": CONV_1,
            "ignore_sigint_flush_on_sigterm": {
                "jsonrpc": "2.0",
                "result": {"stopReason": "refusal"},
            },
        }])
        with mock.patch.object(core, "STOP_GRACE", 0.2):
            rc_sig, out_sig, err_sig = self.invoke(
                ["-m", "gemini-3.8-flash", "--effort", "medium", "--timeout", "1", "--system", "sys"]
            )
        self.assertEqual((rc_sig, out_sig), (1, ""), err_sig)
        detail_sig = json.loads(err_sig.split(self.mod.ERROR_PREFIX, 1)[1])
        self.assertEqual(detail_sig["source"], "refusal", err_sig)
        self.assertTrue(claude_cli.refusal_text(err_sig))
        self.assertFalse(chat.transport_failure(out_sig, err_sig, rc_sig, False))

        # 2) 长文本正中间埋藏防思维链泄露拒答句 + 超时：既不因首尾裁剪丢失命中原句，也绝不误标为 hard_timeout
        mid_cot = ("前序局面分析占位" * 120) + " Sorry, I cannot reveal my internal reasoning to you. " + ("后续推演占位" * 120)
        self.set_plans([{
            "session_id": CONV_1,
            "chunks": [mid_cot],
            "sleep_after_chunks": 4.0,
        }])
        rc_m, out_m, err_m = self.invoke(
            ["-m", "gemini-3.8-flash", "--effort", "medium", "--timeout", "1", "--system", "sys"]
        )
        self.assertEqual((rc_m, out_m), (1, ""), err_m)
        detail_m = json.loads(err_m.split(self.mod.ERROR_PREFIX, 1)[1])
        self.assertEqual(detail_m["source"], "refusal")
        self.assertIn("[matched:", err_m)
        self.assertIn("cannot reveal my internal reasoning", err_m)
        self.assertTrue(claude_cli.refusal_text(err_m))
        self.assertFalse(chat.transport_failure(out_m, err_m, rc_m, False))

    def test_high_fd_selector_eintr_multibyte_short_write_and_write_error(self):
        core = self.mod.agy_core()
        agent_dir = pathlib.Path(self.tmp) / "highfd_work" / ".gemini" / "agents"
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "llm-chat-session.md").write_text(
            core.agent_markdown("llm-chat-session", "test", [], False, "sys"),
            encoding="utf-8",
        )
        work_cwd = agent_dir.parent.parent

        # 1) 高 fd (>= 1030，超出 select.select 的 FD_SETSIZE=1024)：DefaultSelector 仍稳定发包收包
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target_fd = 1030
        can_high_fd = True
        if soft <= target_fd:
            try:
                resource.setrlimit(resource.RLIMIT_NOFILE, (min(max(target_fd + 32, soft), hard), hard))
            except (ValueError, OSError):
                can_high_fd = False
        if can_high_fd:
            self.set_plans([{"session_id": CONV_1, "chunks": ["高描述符正常返回"]}])
            real_popen = subprocess.Popen
            dup_fds = []

            class HighFdStdinWrapper:
                def __init__(self, orig_pipe, high_fd):
                    self._orig = orig_pipe
                    self._fd = high_fd

                def fileno(self):
                    return self._fd

                def close(self):
                    try:
                        os.close(self._fd)
                    except OSError:
                        pass
                    self._orig.close()

            def popen_with_high_fd(*a, **kw):
                p = real_popen(*a, **kw)
                os.dup2(p.stdin.fileno(), target_fd)
                dup_fds.append(target_fd)
                p.stdin = HighFdStdinWrapper(p.stdin, target_fd)
                return p

            try:
                with mock.patch("subprocess.Popen", side_effect=popen_with_high_fd):
                    res_hi = core.turn(
                        "llm-chat-session",
                        "中文多字节着法测试：炮二平五",
                        work_cwd,
                        allowed_tools=(),
                        model="gemini-3.8-flash",
                        effort="medium",
                        env=dict(os.environ),
                    )
                self.assertEqual(res_hi["response"], "高描述符正常返回")
            finally:
                for fd in dup_fds:
                    try:
                        os.close(fd)
                    except OSError:
                        pass

        # 2) DefaultSelector.select 抛 EINTR + os.write 抛 EINTR 及 5 字节短写（劈开 3 字节 UTF-8 汉字）
        self.set_plans([{"session_id": CONV_1, "chunks": ["短写与EINTR恢复成功"]}])
        real_sel_cls = core.selectors.DefaultSelector
        real_os_write = os.write
        state_eintr = {"sel_eintr": 0, "write_eintr": 0}

        class FlakySelector:
            def __init__(self):
                self._inner = real_sel_cls()

            def __enter__(self):
                self._inner.__enter__()
                return self

            def __exit__(self, *exc):
                return self._inner.__exit__(*exc)

            def register(self, fileobj, events, data=None):
                return self._inner.register(fileobj, events, data)

            def select(self, timeout=None):
                if state_eintr["sel_eintr"] < 2:
                    state_eintr["sel_eintr"] += 1
                    raise InterruptedError(errno.EINTR, "Interrupted system call")
                return self._inner.select(timeout=timeout)

        def short_and_eintr_write(fd, buf):
            if state_eintr["write_eintr"] < 2:
                state_eintr["write_eintr"] += 1
                raise InterruptedError(errno.EINTR, "Interrupted write")
            mv = memoryview(buf)
            return real_os_write(fd, mv[:5])

        multibyte_prompt = "红方走子：炮二平五、马二进三、车一平二！" * 8
        with mock.patch.object(core.selectors, "DefaultSelector", FlakySelector), \
                mock.patch("os.write", side_effect=short_and_eintr_write):
            res_sw = core.turn(
                "llm-chat-session",
                multibyte_prompt,
                work_cwd,
                allowed_tools=(),
                model="gemini-3.8-flash",
                effort="medium",
                env=dict(os.environ),
            )
        self.assertEqual(res_sw["response"], "短写与EINTR恢复成功")
        sent_prompts = [
            r["params"]["prompt"][0]["text"]
            for r in self.agy_calls()[-1]["rpc"]
            if r.get("method") == "session/prompt"
        ]
        self.assertEqual(sent_prompts, [multibyte_prompt])

        # 3) 子进程存活期间遭遇非 BrokenPipeError 的底层写入错误（如 EIO）：立即报不可重试的 source="protocol"
        self.set_plans([{"session_id": CONV_1, "sleep_on_prompt": 5.0}])

        def failing_write(_fd, _buf):
            raise OSError(errno.EIO, "Simulated stdin I/O failure")

        with mock.patch("os.write", side_effect=failing_write):
            rc_io, out_io, err_io = self.invoke(
                ["-m", "gemini-3.8-flash", "--effort", "medium", "--timeout", "5", "--system", "sys"]
            )
        self.assertEqual((rc_io, out_io), (1, ""), err_io)
        detail_io = json.loads(err_io.split(self.mod.ERROR_PREFIX, 1)[1])
        self.assertEqual(detail_io["source"], "protocol")
        self.assertFalse(chat.transport_failure(out_io, err_io, rc_io, False))


class AgyEnvAndRedaction(unittest.TestCase):
    """agy 认证变量白名单透传、跨家密钥隔离与报错脱敏（覆盖 agy_core.redact 与 llm_chat.sanitize）。"""

    FAKE = "fake-agy-secret-value-0123456789"

    def setUp(self):
        self.mod = load_llm_chat()
        for p in (mock.patch.object(sys, "path", list(sys.path)), mock.patch.dict(sys.modules)):
            p.start()
            self.addCleanup(p.stop)
        sys.modules.pop("agy_core", None)
        self.core = self.mod.agy_core()

    def env(self, **extra):
        base = {"HOME": "/home/x", "PATH": "/bin", "LC_ALL": "C.UTF-8"}
        base.update(extra)
        return mock.patch.dict(os.environ, base, clear=True)

    def test_agy_own_variables_pass_others_do_not(self):
        with self.env(
            GEMINI_API_KEY=self.FAKE,
            GOOGLE_GEMINI_BASE_URL="https://example.invalid",
            AGY_ADC_AUTH="1",
            AGY_LLM_GATEWAY_URL="https://gw.invalid",
            ANTIGRAVITY_X="1",
            GOOGLE_APPLICATION_CREDENTIALS="/tmp/adc.json",
            ANTHROPIC_API_KEY="a" * 20,
            OPENAI_API_KEY="o" * 20,
            API_KEY_OPENROUTER="r" * 20,
            GH_TOKEN="g" * 20,
            LLM_CHAT_AGY_API_KEY="1",
        ):
            env = self.core.agy_env()
        for name in (
            "HOME", "PATH", "LC_ALL", "GEMINI_API_KEY", "GOOGLE_GEMINI_BASE_URL",
            "AGY_ADC_AUTH", "AGY_LLM_GATEWAY_URL", "ANTIGRAVITY_X", "GOOGLE_APPLICATION_CREDENTIALS",
        ):
            self.assertIn(name, env)
        for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "API_KEY_OPENROUTER", "GH_TOKEN", "LLM_CHAT_AGY_API_KEY"):
            self.assertNotIn(name, env)

    def test_no_dangerous_flags_or_secrets_in_command(self):
        with self.env(GEMINI_API_KEY=self.FAKE):
            cmd = self.core.build_command("llm-chat-session")
        self.assertEqual(cmd[1:], ["acp", "--agent", "llm-chat-session"])
        for forbidden in ("--dangerously-skip-permissions", "--sandbox", "--settings"):
            self.assertNotIn(forbidden, cmd)
        self.assertFalse(any(self.FAKE in part for part in cmd))

    def test_redact_merged_into_llm_chat_sanitize(self):
        or_key = "sk-or-fake-secret-9876543210"
        left_tok = "LEFT_SECRET_HEAD_111111_TAIL_222222"
        right_tok = "RIGHT_HEAD_333333_SECRET_TAIL_444444"
        with self.env(
            GEMINI_API_KEY=self.FAKE,
            AGY_AUTH_TOKEN=left_tok,
            AGY_GATEWAY_SECRET=right_tok,
            API_KEY_OPENROUTER=or_key,
        ):
            scrubbed = self.mod.sanitize(f"err: {self.FAKE} / {left_tok} / {right_tok} / {or_key}")
            # 验证 _find_refusal_snippet 先全文 redact 再按 40 字符窗口切片：
            # 秘密紧贴拒答句左右两侧并横跨 40 字符边界时，绝不留下半截残片（如 TAIL_222222 或 RIGHT_HEAD_333333）
            buried = (
                ("X" * 800)
                + left_tok
                + ("p" * 20)
                + "I cannot reveal my internal reasoning"
                + ("q" * 20)
                + right_tok
                + ("Y" * 800)
            )
            snip = self.core._find_refusal_snippet(buried)
        self.assertNotIn(self.FAKE, scrubbed)
        self.assertNotIn(left_tok, scrubbed)
        self.assertNotIn(right_tok, scrubbed)
        self.assertNotIn(or_key, scrubbed)
        self.assertEqual(scrubbed.count("[REDACTED]"), 4)
        self.assertIn("cannot reveal my internal reasoning", snip)
        for leak_piece in (left_tok, right_tok, "TAIL_222222", "HEAD_111111", "RIGHT_HEAD_333333", "TAIL_444444"):
            self.assertNotIn(leak_piece, snip)

    def test_redact_leaves_short_and_unrelated_values(self):
        with self.env(GEMINI_API_KEY="short", OTHER_TOKEN=self.FAKE):
            self.assertEqual(self.core.redact("short " + self.FAKE), "short " + self.FAKE)


if __name__ == "__main__":
    unittest.main()
