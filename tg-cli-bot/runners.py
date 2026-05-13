import os
import json
import subprocess
import tempfile
from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple

from config import CLAUDE_BIN, CODEX_BIN, WORK_DIR, STATE_DIR

# --- state management ---

@dataclass
class ChatSession:
    chat_id: int
    claude_session_id: str = ""
    codex_thread_id: str = ""

def load_state() -> Dict[int, ChatSession]:
    path = os.path.join(STATE_DIR, "chat_state.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {int(k): ChatSession(**v) for k, v in data.items()}

def save_state(sessions: Dict[int, ChatSession]):
    path = os.path.join(STATE_DIR, "chat_state.json")
    data = {str(k): asdict(v) for k, v in sessions.items()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_session(chat_id: int) -> ChatSession:
    sessions = load_state()
    if chat_id not in sessions:
        sessions[chat_id] = ChatSession(chat_id=chat_id)
        save_state(sessions)
    return sessions[chat_id]

# --- Claude Runner ---

def _find_string(node: Any, preferred_keys: tuple) -> str:
    if isinstance(node, str) and node.strip():
        return node.strip()
    if isinstance(node, list):
        for item in node:
            result = _find_string(item, preferred_keys)
            if result:
                return result
        return ""
    if not isinstance(node, dict):
        return ""

    for key in preferred_keys:
        if key in node:
            result = _find_string(node[key], preferred_keys)
            if result:
                return result
    for value in node.values():
        result = _find_string(value, preferred_keys)
        if result:
            return result
    return ""

def _extract_claude_session(jsonl_path: str) -> str:
    if not os.path.exists(jsonl_path): return ""
    with open(jsonl_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip(): continue
            try:
                obj = json.loads(line.strip())
                session_id = _find_string(obj, ("session_id", "sessionId"))
                if session_id: return session_id
            except json.JSONDecodeError:
                continue
    return ""

def _extract_claude_result(jsonl_path: str) -> str:
    if not os.path.exists(jsonl_path): return ""
    result_text = ""
    assistant_blocks = []

    with open(jsonl_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip(): continue
            try:
                obj = json.loads(line.strip())
                # capture assistant text just in case result is missing
                if obj.get("type") == "assistant":
                    msg = obj.get("message")
                    if isinstance(msg, dict) and str(msg.get("role", "")).lower() == "assistant":
                        content = msg.get("content")
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    text = str(item.get("text", "")).strip()
                                    if text: assistant_blocks.append(text)

                # capture final result
                if obj.get("type") == "result":
                    res = obj.get("result")
                    if isinstance(res, str) and res.strip():
                        result_text = res.strip()
                    elif isinstance(res, dict):
                        response = _find_string(res, ("response", "text", "content", "output", "result"))
                        if response: result_text = response
            except json.JSONDecodeError:
                continue

    if result_text:
        return result_text
    return "\n\n".join(assistant_blocks).strip()

def run_claude(chat_id: int, prompt: str) -> Tuple[bool, str]:
    session = get_session(chat_id)
    cmd = [
        CLAUDE_BIN,
        "-p",
        "--verbose",
        "--output-format",
        "stream-json",
        "--permission-mode",
        "acceptEdits",
    ]
    if session.claude_session_id:
        cmd.extend(["-r", session.claude_session_id])

    cmd.append(prompt)

    env = os.environ.copy()
    env["NO_COLOR"] = "1"

    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = os.path.join(tmpdir, "claude-events.jsonl")

        with open(jsonl_path, "w", encoding="utf-8") as jsonl:
            proc = subprocess.run(
                cmd, cwd=WORK_DIR, env=env, stdout=jsonl, stderr=subprocess.PIPE, text=True
            )

        final_output = _extract_claude_result(jsonl_path)
        current_session_id = _extract_claude_session(jsonl_path)

        # Check if missing session
        stderr_text = (proc.stderr or "").strip()
        failure_text = "\n".join([stderr_text, final_output])
        if "no conversation found with session id" in failure_text.lower():
            # Session expired or not found, clear it and return error telling user to try again
            sessions = load_state()
            sessions[chat_id].claude_session_id = ""
            save_state(sessions)
            return False, "会话已失效，历史记录已被清除，请重新发送您的指令作为新会话的开始。"

        if current_session_id:
            sessions = load_state()
            sessions[chat_id].claude_session_id = current_session_id
            save_state(sessions)

        if proc.returncode != 0 and not final_output:
            return False, f"运行失败 (Exit code {proc.returncode}):\n{stderr_text}"

        return True, final_output

# --- Codex Runner ---

def _extract_codex_thread(jsonl_path: str) -> str:
    if not os.path.exists(jsonl_path): return ""
    with open(jsonl_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip(): continue
            try:
                obj = json.loads(line.strip())
                if obj.get("type") == "thread.started" and obj.get("thread_id"):
                    return str(obj["thread_id"])
            except json.JSONDecodeError:
                continue
    return ""

def run_codex(chat_id: int, prompt: str) -> Tuple[bool, str]:
    session = get_session(chat_id)

    with tempfile.TemporaryDirectory() as tmpdir:
        final_output_path = os.path.join(tmpdir, "codex-last.txt")
        jsonl_path = os.path.join(tmpdir, "codex-events.jsonl")

        if not session.codex_thread_id:
            cmd = [
                CODEX_BIN, "exec", "-C", WORK_DIR, "-s", "workspace-write",
                "--dangerously-bypass-approvals-and-sandbox", "--color", "never",
                "--json", "-o", final_output_path, prompt
            ]
        else:
            cmd = [
                CODEX_BIN, "exec", "resume",
                "--dangerously-bypass-approvals-and-sandbox",
                "--json", "-o", final_output_path, session.codex_thread_id, prompt
            ]

        with open(jsonl_path, "w", encoding="utf-8") as jsonl:
            proc = subprocess.run(
                cmd, cwd=WORK_DIR, stdout=jsonl, stderr=subprocess.PIPE, text=True
            )

        final_output = ""
        if os.path.exists(final_output_path):
            with open(final_output_path, "r", encoding="utf-8", errors="ignore") as f:
                final_output = f.read().strip()

        stderr_text = (proc.stderr or "").strip()
        missing_thread = "thread" in stderr_text.lower() and "not found" in stderr_text.lower()

        if missing_thread:
            sessions = load_state()
            sessions[chat_id].codex_thread_id = ""
            save_state(sessions)
            return False, "会话线程已失效或未找到，历史记录已被清除，请重新发送指令作为新会话的开始。"

        current_thread_id = session.codex_thread_id
        if not current_thread_id:
            current_thread_id = _extract_codex_thread(jsonl_path)
            if current_thread_id:
                sessions = load_state()
                sessions[chat_id].codex_thread_id = current_thread_id
                save_state(sessions)

        if proc.returncode != 0 and not final_output:
            return False, f"运行失败 (Exit code {proc.returncode}):\n{stderr_text}"

        return True, final_output

def reset_session(chat_id: int) -> str:
    sessions = load_state()
    if chat_id in sessions:
        sessions[chat_id].claude_session_id = ""
        sessions[chat_id].codex_thread_id = ""
        save_state(sessions)
    return "已成功重置您当前聊天的所有会话记录 (claude 和 codex 均开启新会话)。"
