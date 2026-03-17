from __future__ import annotations

import json
import asyncio
import inspect
from dataclasses import field, dataclass
from typing import Any
from collections.abc import Callable, Awaitable

from .protocol_io import NdjsonProcessReader, ProtocolStreamError

@dataclass(slots=True)
class NativeAgentUpdate:
    agent_key: str
    text: str


Callback = Callable[[NativeAgentUpdate], object]
ProcessLauncher = Callable[..., Awaitable[Any]]


@dataclass(slots=True)
class NativeThreadSummary:
    thread_id: str
    thread_name: str
    updated_at: str
    cwd: str | None
    source_kind: str
    preview: str | None = None


@dataclass(slots=True)
class NativeRunResult:
    exit_code: int
    final_text: str = ""
    thread_id: str | None = None
    diagnostics: list[str] = field(default_factory=list)


def _normalize_source_kind(source: object) -> str:
    if isinstance(source, str) and source:
        return source
    if isinstance(source, dict) and "subAgent" in source:
        sub_agent = source["subAgent"]
        if isinstance(sub_agent, str) and sub_agent:
            return f"subAgent:{sub_agent}"
        if isinstance(sub_agent, dict):
            return "subAgent"
    return "unknown"


def _thread_summary_from_payload(thread: dict[str, Any]) -> NativeThreadSummary:
    thread_id = str(thread.get("id") or "")
    thread_name = str(thread.get("name") or thread.get("preview") or thread_id)
    updated_at = str(thread.get("updatedAt") or thread.get("updated_at") or "")
    cwd = thread.get("cwd")
    preview = thread.get("preview")
    return NativeThreadSummary(
        thread_id=thread_id,
        thread_name=thread_name,
        updated_at=updated_at,
        cwd=cwd if isinstance(cwd, str) else None,
        source_kind=_normalize_source_kind(thread.get("source")),
        preview=preview if isinstance(preview, str) and preview.strip() else None,
    )


async def _maybe_call(callback: Callback | None, update: NativeAgentUpdate) -> None:
    if callback is None:
        return
    result = callback(update)
    if inspect.isawaitable(result):
        await result


def _trim_progress_command(command: str, limit: int = 120) -> str:
    compact = " ".join(command.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _trim_progress_text(text: str, limit: int = 80) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _normalize_agent_key(agent_key: object, *, main_thread_id: str) -> str:
    if not isinstance(agent_key, str) or not agent_key:
        return "main"
    return "main" if agent_key == main_thread_id else agent_key


def _extract_compaction_notice(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in (
        "summary",
        "summaryText",
        "text",
        "compactionSummary",
        "compaction_summary",
        "notice",
        "message",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    item = payload.get("item")
    if isinstance(item, dict):
        return _extract_compaction_notice(item)
    return None


def _format_collab_tool_progress(
    item: dict[str, Any],
    *,
    main_thread_id: str,
    started: bool,
) -> list[NativeAgentUpdate]:
    tool = str(item.get("tool") or "")
    prompt = item.get("prompt")
    receiver_ids = item.get("receiverThreadIds")
    agent_states = item.get("agentsStates")

    action_labels = {
        "spawnAgent": (
            "正在分派子 agent 任务",
            "子 agent 任务已分派",
        ),
        "sendInput": (
            "正在向子 agent 发送补充指令",
            "已向子 agent 发送补充指令",
        ),
        "resumeAgent": (
            "正在恢复子 agent",
            "已恢复子 agent",
        ),
        "wait": (
            "正在等待子 agent",
            "正在等待子 agent，现已收到结果",
        ),
        "closeAgent": (
            "正在关闭子 agent",
            "已关闭子 agent",
        ),
    }
    default_start, default_done = (
        "正在处理子 agent 协作",
        "子 agent 协作已更新",
    )
    start_text, done_text = action_labels.get(tool, (default_start, default_done))
    updates = [
        NativeAgentUpdate(
            agent_key="main",
            text=start_text if started else done_text,
        )
    ]

    if isinstance(prompt, str) and prompt.strip() and tool in {"spawnAgent", "sendInput"}:
        updates[0].text = f"{updates[0].text} - {_trim_progress_text(prompt)}"

    status_labels = {
        "pendingInit": "初始化中",
        "running": "运行中",
        "completed": "已完成",
        "errored": "出错",
        "shutdown": "已关闭",
        "notFound": "未找到",
    }

    ordered_ids: list[str] = []
    if isinstance(receiver_ids, list):
        for entry in receiver_ids:
            if isinstance(entry, str) and entry and entry not in ordered_ids:
                ordered_ids.append(entry)
    if isinstance(agent_states, dict):
        for entry in agent_states:
            if isinstance(entry, str) and entry and entry not in ordered_ids:
                ordered_ids.append(entry)

    if not isinstance(agent_states, dict):
        agent_states = {}

    for agent_id in ordered_ids:
        state = agent_states.get(agent_id)
        if not isinstance(state, dict):
            updates.append(
                NativeAgentUpdate(
                    agent_key=_normalize_agent_key(
                        agent_id,
                        main_thread_id=main_thread_id,
                    ),
                    text="状态未知",
                )
            )
            continue
        status = status_labels.get(str(state.get("status") or ""), "状态未知")
        message = state.get("message")
        line = status
        if isinstance(message, str) and message.strip():
            line = f"{line}（{_trim_progress_text(message, 60)}）"
        updates.append(
            NativeAgentUpdate(
                agent_key=_normalize_agent_key(agent_id, main_thread_id=main_thread_id),
                text=line,
            )
        )

    return updates


async def _terminate_process(process: Any, timeout: float) -> None:
    if process is None:
        return
    if getattr(process, "returncode", None) is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


class NativeCodexClient:
    def __init__(
        self,
        *,
        binary: str = "codex",
        launcher: ProcessLauncher | None = None,
        client_name: str = "tg_bot",
        client_version: str = "0",
        stream_read_limit: int = 8 * 1024 * 1024,
    ) -> None:
        self.binary = binary
        self.launcher = launcher or asyncio.create_subprocess_exec
        self.client_name = client_name
        self.client_version = client_version
        self.stream_read_limit = stream_read_limit
        self._process: Any = None
        self._reader: NdjsonProcessReader | None = None
        self._initialized = False
        self._next_request_id = 1

    def clone(self) -> NativeCodexClient:
        return NativeCodexClient(
            binary=self.binary,
            launcher=self.launcher,
            client_name=self.client_name,
            client_version=self.client_version,
            stream_read_limit=self.stream_read_limit,
        )

    async def close(self, timeout: float = 5.0) -> None:
        process = self._process
        reader = self._reader
        self._process = None
        self._reader = None
        self._initialized = False
        self._next_request_id = 1
        await _terminate_process(process, timeout)
        if reader is not None:
            await reader.wait_closed()

    async def start_thread(
        self,
        *,
        workdir: str,
        model: str,
        reasoning_effort: str,
        permission_mode: str,
    ) -> NativeThreadSummary:
        result = await self._request(
            "thread/start",
            {
                "cwd": workdir,
                "model": model,
                "config": {"model_reasoning_effort": reasoning_effort},
                **self._permission_params(permission_mode),
            },
        )
        thread = result.get("thread")
        if not isinstance(thread, dict):
            raise RuntimeError("thread/start 缺少 thread 响应。")
        return _thread_summary_from_payload(thread)

    async def resume_thread(
        self,
        thread_id: str,
        *,
        workdir: str,
        model: str,
        reasoning_effort: str,
        permission_mode: str,
    ) -> NativeThreadSummary:
        result = await self._request(
            "thread/resume",
            {
                "threadId": thread_id,
                "cwd": workdir,
                "model": model,
                "config": {"model_reasoning_effort": reasoning_effort},
                **self._permission_params(permission_mode),
            },
        )
        thread = result.get("thread")
        if not isinstance(thread, dict):
            raise RuntimeError("thread/resume 缺少 thread 响应。")
        return _thread_summary_from_payload(thread)

    async def run_turn(
        self,
        thread_id: str,
        prompt: str,
        *,
        cwd: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        on_progress: Callback | None = None,
        on_stream_text: Callback | None = None,
    ) -> NativeRunResult:
        diagnostics: list[str] = []
        final_text = ""
        pending_agent_messages: dict[str, str] = {}
        last_streamed_text: dict[str, str] = {}
        last_compaction_notice: dict[str, str] = {}

        async def emit_stream_update(agent_key: str, text: str) -> None:
            if last_streamed_text.get(agent_key) == text:
                return
            last_streamed_text[agent_key] = text
            await _maybe_call(
                on_stream_text,
                NativeAgentUpdate(agent_key=agent_key, text=text),
            )

        async def emit_compaction_notice(agent_key: str, text: str) -> None:
            if last_compaction_notice.get(agent_key) == text:
                return
            last_compaction_notice[agent_key] = text
            await _maybe_call(
                on_progress,
                NativeAgentUpdate(agent_key=agent_key, text=text),
            )

        await self._request(
            "turn/start",
            self._turn_start_params(
                thread_id=thread_id,
                prompt=prompt,
                cwd=cwd,
                model=model,
                reasoning_effort=reasoning_effort,
            ),
            diagnostics=diagnostics,
        )

        while True:
            message = await self._read_message(diagnostics)
            if message is None:
                continue

            method = message.get("method")
            params = message.get("params")
            if not isinstance(method, str) or not isinstance(params, dict):
                continue

            if method == "turn/started":
                await _maybe_call(
                    on_progress,
                    NativeAgentUpdate(agent_key="main", text="开始处理请求"),
                )
                continue

            if method in {"item/started", "item/completed"}:
                item = params.get("item")
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                agent_key = _normalize_agent_key(
                    params.get("threadId"),
                    main_thread_id=thread_id,
                )
                if item_type == "commandExecution":
                    command = _trim_progress_command(str(item.get("command") or ""))
                    prefix = "执行" if method == "item/started" else "完成"
                    await _maybe_call(
                        on_progress,
                        NativeAgentUpdate(
                            agent_key=agent_key,
                            text=f"{prefix}: {command}",
                        ),
                    )
                    continue
                if item_type == "collabAgentToolCall":
                    collab_updates = _format_collab_tool_progress(
                        item,
                        main_thread_id=thread_id,
                        started=method == "item/started",
                    )
                    for update in collab_updates:
                        await _maybe_call(on_progress, update)
                    continue
                if item_type == "contextCompaction":
                    notice = _extract_compaction_notice(item) or (
                        "正在压缩较早对话上下文…"
                        if method == "item/started"
                        else "已压缩较早对话上下文。"
                    )
                    await emit_compaction_notice(agent_key, notice)
                    continue
                if item_type == "agentMessage":
                    item_id = item.get("id")
                    if isinstance(item_id, str) and item_id:
                        pending_agent_messages.pop(f"{agent_key}:{item_id}", None)
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        phase = item.get("phase")
                        stripped = text.strip()
                        await emit_stream_update(agent_key, stripped)
                        if phase != "commentary" and agent_key == "main":
                            final_text = stripped
                    continue

            if method == "item/agentMessage/delta":
                item_id = params.get("itemId")
                delta = params.get("delta")
                agent_key = _normalize_agent_key(
                    params.get("threadId"),
                    main_thread_id=thread_id,
                )
                if isinstance(delta, str) and delta:
                    item_key = (
                        f"{agent_key}:{item_id}"
                        if isinstance(item_id, str) and item_id
                        else f"__legacy__:{agent_key}"
                    )
                    pending_agent_messages[item_key] = (
                        pending_agent_messages.get(item_key, "") + delta
                    )
                    await emit_stream_update(
                        agent_key,
                        pending_agent_messages[item_key],
                    )
                continue

            if method == "thread/compacted":
                agent_key = _normalize_agent_key(
                    params.get("threadId"),
                    main_thread_id=thread_id,
                )
                notice = _extract_compaction_notice(params) or "已压缩较早对话上下文。"
                await emit_compaction_notice(agent_key, notice)
                continue

            if method == "turn/completed":
                turn = params.get("turn")
                if not isinstance(turn, dict):
                    return NativeRunResult(
                        exit_code=1,
                        final_text=final_text,
                        thread_id=thread_id,
                        diagnostics=diagnostics,
                    )
                if not final_text and pending_agent_messages:
                    fallback_key = next(
                        (
                            key
                            for key in reversed(list(pending_agent_messages))
                            if key.endswith(":main") or key == "__legacy__:main"
                        ),
                        None,
                    )
                    if fallback_key is not None:
                        buffered_text = pending_agent_messages[fallback_key].strip()
                        if buffered_text:
                            final_text = buffered_text
                            await emit_stream_update("main", final_text)
                status = turn.get("status")
                error = turn.get("error")
                exit_code = 0 if status == "completed" and error is None else 1
                return NativeRunResult(
                    exit_code=exit_code,
                    final_text=final_text,
                    thread_id=str(params.get("threadId") or thread_id),
                    diagnostics=diagnostics,
                )

    async def compact_thread(
        self,
        thread_id: str,
        *,
        on_progress: Callback | None = None,
        timeout: float = 30.0,
    ) -> str:
        diagnostics: list[str] = []
        last_notice = ""

        async def emit_notice(notice: str) -> None:
            nonlocal last_notice
            if last_notice == notice:
                return
            last_notice = notice
            await _maybe_call(
                on_progress,
                NativeAgentUpdate(agent_key="main", text=notice),
            )

        await self._request(
            "thread/compact/start",
            {"threadId": thread_id},
            diagnostics=diagnostics,
        )

        while True:
            try:
                message = await asyncio.wait_for(
                    self._read_message(diagnostics),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                return last_notice or "已开始压缩当前 resume 会话上下文。"

            if message is None:
                continue

            method = message.get("method")
            params = message.get("params")
            if not isinstance(method, str) or not isinstance(params, dict):
                continue

            if method in {"item/started", "item/completed"}:
                item = params.get("item")
                if not isinstance(item, dict) or item.get("type") != "contextCompaction":
                    continue
                notice = _extract_compaction_notice(item) or (
                    "正在压缩当前 resume 会话上下文…"
                    if method == "item/started"
                    else "已压缩当前 resume 会话上下文。"
                )
                await emit_notice(notice)
                continue

            if method == "thread/compacted":
                notice = _extract_compaction_notice(params) or last_notice
                final_notice = notice or "已压缩当前 resume 会话上下文。"
                await emit_notice(final_notice)
                return final_notice

    async def list_threads(self) -> list[NativeThreadSummary]:
        threads: list[NativeThreadSummary] = []
        cursor: str | None = None

        while True:
            params: dict[str, Any] = {
                "sortKey": "updated_at",
                "sourceKinds": ["cli", "vscode", "appServer"],
                "limit": 100,
            }
            if cursor is not None:
                params["cursor"] = cursor

            result = await self._request("thread/list", params)
            entries = result.get("data")
            if not isinstance(entries, list):
                raise RuntimeError("thread/list 缺少 data 响应。")
            threads.extend(
                _thread_summary_from_payload(thread)
                for thread in entries
                if isinstance(thread, dict)
            )

            next_cursor = result.get("nextCursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                break
            cursor = next_cursor

        return threads

    def _permission_params(self, permission_mode: str) -> dict[str, str]:
        if permission_mode == "safe":
            return {"approvalPolicy": "never", "sandbox": "workspace-write"}
        if permission_mode == "danger":
            return {
                "approvalPolicy": "never",
                "sandbox": "danger-full-access",
            }
        raise ValueError(f"Unsupported permission mode: {permission_mode}")

    def _turn_start_params(
        self,
        *,
        thread_id: str,
        prompt: str,
        cwd: str | None,
        model: str | None,
        reasoning_effort: str | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "threadId": thread_id,
            "input": [{"type": "text", "text": prompt}],
        }
        if cwd is not None:
            params["cwd"] = cwd
        if model is not None:
            params["model"] = model
        if reasoning_effort is not None:
            params["effort"] = reasoning_effort
        return params

    async def _ensure_initialized(self) -> None:
        if self._initialized and self._process is not None:
            return
        self._process = await self.launcher(
            self.binary,
            "app-server",
            "--listen",
            "stdio://",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=self.stream_read_limit,
        )
        self._reader = NdjsonProcessReader(
            self._process,
            frame_limit=self.stream_read_limit,
        )
        request_id = self._allocate_request_id()
        await self._write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": self.client_name,
                        "version": self.client_version,
                    }
                },
            }
        )
        await self._read_response(request_id, diagnostics=[])
        await self._write_message(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }
        )
        self._initialized = True

    async def _request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        diagnostics: list[str] | None = None,
    ) -> dict[str, Any]:
        await self._ensure_initialized()
        request_id = self._allocate_request_id()
        await self._write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        return await self._read_response(request_id, diagnostics=diagnostics or [])

    async def _write_message(self, payload: dict[str, Any]) -> None:
        if self._process is None or getattr(self._process, "stdin", None) is None:
            raise RuntimeError("Codex app-server 尚未启动。")
        data = json.dumps(payload, ensure_ascii=False) + "\n"
        self._process.stdin.write(data.encode("utf-8"))
        await self._process.stdin.drain()

    async def _read_response(
        self,
        request_id: int,
        *,
        diagnostics: list[str],
    ) -> dict[str, Any]:
        while True:
            message = await self._read_message(diagnostics)
            if message is None:
                continue
            if message.get("id") != request_id:
                continue
            error = message.get("error")
            if isinstance(error, dict):
                raise RuntimeError(
                    str(error.get("message") or "Codex app-server 请求失败。")
                )
            result = message.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("Codex app-server 返回了无效响应。")
            return result

    async def _read_message(self, diagnostics: list[str]) -> dict[str, Any] | None:
        if self._process is None or self._reader is None:
            raise RuntimeError("Codex app-server 尚未启动。")

        diagnostics.extend(self._reader.drain_stderr_lines())
        try:
            line = await self._reader.read_stdout_line()
        except ProtocolStreamError as exc:
            diagnostics.extend(self._reader.drain_stderr_lines())
            raise RuntimeError(str(exc)) from exc
        diagnostics.extend(self._reader.drain_stderr_lines())

        if line is None:
            raise RuntimeError("Codex app-server 已提前退出。")
        if not line:
            return None
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            diagnostics.append(line)
            return None
        return message if isinstance(message, dict) else None

    def _allocate_request_id(self) -> int:
        request_id = self._next_request_id
        self._next_request_id += 1
        return request_id
