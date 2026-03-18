from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from dataclasses import dataclass

import pytest

from nonebot_plugin_codex.native_client import NativeCodexClient


class FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._lines = [line.encode("utf-8") for line in lines]

    async def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        await asyncio.sleep(0)
        return b""

    async def read(self, _size: int = -1) -> bytes:
        return await self.readline()


class FakeStdin:
    def __init__(self) -> None:
        self.buffer: list[str] = []

    def write(self, data: bytes) -> None:
        self.buffer.append(data.decode("utf-8"))

    async def drain(self) -> None:
        return None


@dataclass
class FakeProcess:
    stdout: FakeStdout
    stdin: FakeStdin
    stderr: FakeStdout | None = None
    returncode: int | None = None

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        self.returncode = self.returncode or 0
        return self.returncode


@pytest.mark.asyncio
async def test_native_client_start_resume_and_stream_text() -> None:
    requests: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    process = FakeProcess(
        stdout=FakeStdout(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "thread": {
                                "id": "thread-1",
                                "name": "Thread One",
                                "updatedAt": "2025-03-01T00:00:00Z",
                                "cwd": "/tmp/work",
                                "source": "cli",
                            }
                        },
                    }
                )
                + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 3, "result": {}}) + "\n",
                json.dumps({"jsonrpc": "2.0", "method": "turn/started", "params": {}})
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/agentMessage/delta",
                        "params": {"delta": "hello"},
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-1",
                            "turn": {"status": "completed", "error": None},
                        },
                    }
                )
                + "\n",
            ]
        ),
        stdin=FakeStdin(),
    )

    async def launcher(*args: Any, **kwargs: Any) -> FakeProcess:
        requests.append((args, kwargs))
        return process

    client = NativeCodexClient(binary="codex", launcher=launcher)
    progress: list[Any] = []
    streamed: list[Any] = []

    thread = await client.start_thread(
        workdir="/tmp/work",
        model="gpt-5",
        reasoning_effort="xhigh",
        permission_mode="safe",
    )
    result = await client.run_turn(
        thread.thread_id,
        "hello",
        on_progress=progress.append,
        on_stream_text=streamed.append,
    )

    assert requests[0][0][:3] == ("codex", "app-server", "--listen")
    assert thread.thread_id == "thread-1"
    assert [(entry.agent_key, entry.text) for entry in progress] == [
        ("main", "开始处理请求")
    ]
    assert [(entry.agent_key, entry.text) for entry in streamed] == [
        ("main", "hello")
    ]
    assert result.exit_code == 0
    assert result.final_text == "hello"


@pytest.mark.asyncio
async def test_native_client_run_turn_reports_context_compaction_progress() -> None:
    process = FakeProcess(
        stdout=FakeStdout(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 2, "result": {}}) + "\n",
                json.dumps({"jsonrpc": "2.0", "method": "turn/started", "params": {}})
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-1",
                            "item": {
                                "id": "compact-1",
                                "type": "contextCompaction",
                                "summary": "已压缩较早对话上下文。",
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/agentMessage/delta",
                        "params": {"delta": "hello"},
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-1",
                            "turn": {"status": "completed", "error": None},
                        },
                    }
                )
                + "\n",
            ]
        ),
        stdin=FakeStdin(),
    )

    async def launcher(*_args: Any, **_kwargs: Any) -> FakeProcess:
        return process

    client = NativeCodexClient(binary="codex", launcher=launcher)
    progress: list[Any] = []

    result = await client.run_turn(
        "thread-1",
        "hello",
        on_progress=progress.append,
    )

    assert [(entry.agent_key, entry.text) for entry in progress] == [
        ("main", "开始处理请求"),
        ("main", "已压缩较早对话上下文。"),
    ]
    assert result.exit_code == 0
    assert result.final_text == "hello"


@pytest.mark.asyncio
async def test_native_client_reports_thread_token_usage_updates() -> None:
    process = FakeProcess(
        stdout=FakeStdout(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "thread": {
                                "id": "thread-1",
                                "name": "Thread One",
                                "updatedAt": "2025-03-01T00:00:00Z",
                                "cwd": "/tmp/work",
                                "source": "cli",
                            }
                        },
                    }
                )
                + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 3, "result": {}}) + "\n",
                json.dumps({"jsonrpc": "2.0", "method": "turn/started", "params": {}})
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "thread/tokenUsage/updated",
                        "params": {
                            "threadId": "thread-1",
                            "turnId": "turn-1",
                            "tokenUsage": {
                                "modelContextWindow": 200000,
                                "total": {"totalTokens": 12345},
                                "last": {
                                    "cachedInputTokens": 0,
                                    "inputTokens": 100,
                                    "outputTokens": 20,
                                    "reasoningOutputTokens": 30,
                                    "totalTokens": 150,
                                },
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-1",
                            "turn": {"status": "completed", "error": None},
                        },
                    }
                )
                + "\n",
            ]
        ),
        stdin=FakeStdin(),
    )

    async def launcher(*_args: Any, **_kwargs: Any) -> FakeProcess:
        return process

    client = NativeCodexClient(binary="codex", launcher=launcher)
    thread = await client.start_thread(
        workdir="/tmp/work",
        model="gpt-5",
        reasoning_effort="xhigh",
        permission_mode="safe",
    )
    token_usage_updates: list[tuple[int, int | None]] = []

    await client.run_turn(
        thread.thread_id,
        "hello",
        on_token_usage=lambda update: token_usage_updates.append(
            (update.total_tokens, update.model_context_window)
        ),
    )

    assert token_usage_updates == [(12345, 200000)]


@pytest.mark.asyncio
async def test_native_client_ignores_subagent_thread_token_usage_updates() -> None:
    process = FakeProcess(
        stdout=FakeStdout(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "thread": {
                                "id": "thread-main",
                                "name": "Main Thread",
                                "updatedAt": "2025-03-01T00:00:00Z",
                                "cwd": "/tmp/work",
                                "source": "cli",
                            }
                        },
                    }
                )
                + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 3, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "thread/tokenUsage/updated",
                        "params": {
                            "threadId": "thread-sub-1",
                            "turnId": "turn-1",
                            "tokenUsage": {
                                "modelContextWindow": 999999,
                                "total": {"totalTokens": 55555},
                                "last": {
                                    "cachedInputTokens": 0,
                                    "inputTokens": 100,
                                    "outputTokens": 20,
                                    "reasoningOutputTokens": 30,
                                    "totalTokens": 150,
                                },
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "thread/tokenUsage/updated",
                        "params": {
                            "threadId": "thread-main",
                            "turnId": "turn-1",
                            "tokenUsage": {
                                "modelContextWindow": 200000,
                                "total": {"totalTokens": 12345},
                                "last": {
                                    "cachedInputTokens": 0,
                                    "inputTokens": 100,
                                    "outputTokens": 20,
                                    "reasoningOutputTokens": 30,
                                    "totalTokens": 150,
                                },
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-main",
                            "turn": {"status": "completed", "error": None},
                        },
                    }
                )
                + "\n",
            ]
        ),
        stdin=FakeStdin(),
    )

    async def launcher(*_args: Any, **_kwargs: Any) -> FakeProcess:
        return process

    client = NativeCodexClient(binary="codex", launcher=launcher)
    thread = await client.start_thread(
        workdir="/tmp/work",
        model="gpt-5",
        reasoning_effort="xhigh",
        permission_mode="safe",
    )
    token_usage_updates: list[tuple[int, int | None]] = []

    await client.run_turn(
        thread.thread_id,
        "hello",
        on_token_usage=lambda update: token_usage_updates.append(
            (update.total_tokens, update.model_context_window)
        ),
    )

    assert token_usage_updates == [(12345, 200000)]


@pytest.mark.asyncio
async def test_native_client_compact_thread_waits_for_compaction_notice() -> None:
    process = FakeProcess(
        stdout=FakeStdout(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 2, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "thread/compacted",
                        "params": {
                            "threadId": "thread-1",
                            "summary": "已压缩当前 resume 会话上下文。",
                        },
                    }
                )
                + "\n",
            ]
        ),
        stdin=FakeStdin(),
    )

    async def launcher(*_args: Any, **_kwargs: Any) -> FakeProcess:
        return process

    client = NativeCodexClient(binary="codex", launcher=launcher)
    progress: list[Any] = []

    notice = await client.compact_thread("thread-1", on_progress=progress.append)

    assert notice == "已压缩当前 resume 会话上下文。"
    assert [(entry.agent_key, entry.text) for entry in progress] == [
        ("main", "已压缩当前 resume 会话上下文。"),
    ]


@pytest.mark.asyncio
async def test_native_client_ignores_commentary_text_and_reports_subagent_progress(
) -> None:
    process = FakeProcess(
        stdout=FakeStdout(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "thread": {
                                "id": "thread-1",
                                "name": "Thread One",
                                "updatedAt": "2025-03-01T00:00:00Z",
                                "cwd": "/tmp/work",
                                "source": "cli",
                            }
                        },
                    }
                )
                + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 3, "result": {}}) + "\n",
                json.dumps({"jsonrpc": "2.0", "method": "turn/started", "params": {}})
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/agentMessage/delta",
                        "params": {"itemId": "msg-1", "delta": "main planning note"},
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-1",
                            "item": {
                                "id": "msg-1",
                                "type": "agentMessage",
                                "text": "main planning note",
                                "phase": "commentary",
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/started",
                        "params": {
                            "threadId": "thread-1",
                            "item": {
                                "id": "collab-1",
                                "type": "collabAgentToolCall",
                                "tool": "spawnAgent",
                                "status": "inProgress",
                                "prompt": (
                                    "Write regression tests "
                                    "for the Telegram bridge"
                                ),
                                "senderThreadId": "thread-1",
                                "receiverThreadIds": ["agent-1"],
                                "agentsStates": {
                                    "agent-1": {
                                        "status": "running",
                                        "message": "writing tests",
                                    }
                                },
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/completed",
                        "params": {
                            "threadId": "agent-1",
                            "item": {
                                "id": "msg-raw-child",
                                "type": "agentMessage",
                                "text": "raw child answer",
                                "phase": "commentary",
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-1",
                            "item": {
                                "id": "collab-1",
                                "type": "collabAgentToolCall",
                                "tool": "wait",
                                "status": "completed",
                                "prompt": None,
                                "senderThreadId": "thread-1",
                                "receiverThreadIds": ["agent-1"],
                                "agentsStates": {
                                    "agent-1": {
                                        "status": "completed",
                                        "message": "tests ready",
                                    }
                                },
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/agentMessage/delta",
                        "params": {"itemId": "msg-2", "delta": "main final"},
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-1",
                            "item": {
                                "id": "msg-2",
                                "type": "agentMessage",
                                "text": "main final",
                                "phase": "final_answer",
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-1",
                            "turn": {"status": "completed", "error": None},
                        },
                    }
                )
                + "\n",
            ]
        ),
        stdin=FakeStdin(),
    )

    async def launcher(*_args: Any, **_kwargs: Any) -> FakeProcess:
        return process

    client = NativeCodexClient(binary="codex", launcher=launcher)
    progress: list[Any] = []
    streamed: list[Any] = []

    thread = await client.start_thread(
        workdir="/tmp/work",
        model="gpt-5",
        reasoning_effort="xhigh",
        permission_mode="safe",
    )
    result = await client.run_turn(
        thread.thread_id,
        "hello",
        on_progress=progress.append,
        on_stream_text=streamed.append,
    )

    progress_items = [(entry.agent_key, entry.text) for entry in progress]
    streamed_items = [(entry.agent_key, entry.text) for entry in streamed]

    assert result.exit_code == 0
    assert result.final_text == "main final"
    assert streamed_items[0] == ("main", "main planning note")
    assert (
        "main",
        "正在分派子 agent 任务 - Write regression tests for the Telegram bridge",
    ) in progress_items
    assert ("agent-1", "运行中（writing tests）") in progress_items
    assert ("agent-1", "raw child answer") in streamed_items
    assert ("main", "main final") == streamed_items[-1]
    assert progress_items[0] == ("main", "开始处理请求")
    assert ("main", "正在等待子 agent，现已收到结果") in progress_items
    assert ("agent-1", "已完成（tests ready）") in progress_items


@pytest.mark.asyncio
async def test_native_client_emits_per_agent_updates_for_spawned_subagent() -> None:
    process = FakeProcess(
        stdout=FakeStdout(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "thread": {
                                "id": "thread-main",
                                "name": "Main Thread",
                                "updatedAt": "2025-03-01T00:00:00Z",
                                "cwd": "/tmp/work",
                                "source": "cli",
                            }
                        },
                    }
                )
                + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 3, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/started",
                        "params": {"threadId": "thread-main"},
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/agentMessage/delta",
                        "params": {
                            "threadId": "thread-main",
                            "itemId": "msg-main-1",
                            "delta": "main commentary",
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/started",
                        "params": {
                            "threadId": "thread-main",
                            "item": {
                                "id": "collab-1",
                                "type": "collabAgentToolCall",
                                "tool": "spawnAgent",
                                "status": "inProgress",
                                "senderThreadId": "thread-main",
                                "receiverThreadIds": ["thread-sub-1"],
                                "agentsStates": {
                                    "thread-sub-1": {
                                        "status": "running",
                                        "message": "writing tests",
                                    }
                                },
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/agentMessage/delta",
                        "params": {
                            "threadId": "thread-sub-1",
                            "itemId": "msg-sub-1",
                            "delta": "sub commentary",
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-sub-1",
                            "item": {
                                "id": "msg-sub-2",
                                "type": "agentMessage",
                                "text": "sub final",
                                "phase": "final_answer",
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-main",
                            "item": {
                                "id": "msg-main-2",
                                "type": "agentMessage",
                                "text": "main final",
                                "phase": "final_answer",
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-main",
                            "turn": {"status": "completed", "error": None},
                        },
                    }
                )
                + "\n",
            ]
        ),
        stdin=FakeStdin(),
    )

    async def launcher(*_args: Any, **_kwargs: Any) -> FakeProcess:
        return process

    client = NativeCodexClient(binary="codex", launcher=launcher)
    progress: list[Any] = []
    streamed: list[Any] = []

    thread = await client.start_thread(
        workdir="/tmp/work",
        model="gpt-5",
        reasoning_effort="xhigh",
        permission_mode="safe",
    )
    result = await client.run_turn(
        thread.thread_id,
        "hello",
        on_progress=progress.append,
        on_stream_text=streamed.append,
    )

    assert result.exit_code == 0
    assert result.final_text == "main final"
    assert [(entry.agent_key, entry.text) for entry in progress[:2]] == [
        ("main", "开始处理请求"),
        ("main", "正在分派子 agent 任务"),
    ]
    assert ("thread-sub-1", "运行中（writing tests）") in [
        (entry.agent_key, entry.text) for entry in progress
    ]
    assert ("main", "main commentary") in [
        (entry.agent_key, entry.text) for entry in streamed
    ]
    assert ("thread-sub-1", "sub commentary") in [
        (entry.agent_key, entry.text) for entry in streamed
    ]
    assert ("thread-sub-1", "sub final") in [
        (entry.agent_key, entry.text) for entry in streamed
    ]
    assert streamed[-1].agent_key == "main"
    assert streamed[-1].text == "main final"


@pytest.mark.asyncio
async def test_native_client_uses_main_delta_fallback_for_final_text() -> None:
    process = FakeProcess(
        stdout=FakeStdout(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "thread": {
                                "id": "thread-1",
                                "name": "Thread One",
                                "updatedAt": "2025-03-01T00:00:00Z",
                                "cwd": "/tmp/work",
                                "source": "cli",
                            }
                        },
                    }
                )
                + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 3, "result": {}}) + "\n",
                json.dumps({"jsonrpc": "2.0", "method": "turn/started", "params": {}})
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/agentMessage/delta",
                        "params": {
                            "threadId": "thread-1",
                            "itemId": "msg-main-final",
                            "delta": "main final only from delta",
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-1",
                            "turn": {"status": "completed", "error": None},
                        },
                    }
                )
                + "\n",
            ]
        ),
        stdin=FakeStdin(),
    )

    async def launcher(*_args: Any, **_kwargs: Any) -> FakeProcess:
        return process

    client = NativeCodexClient(binary="codex", launcher=launcher)

    thread = await client.start_thread(
        workdir="/tmp/work",
        model="gpt-5",
        reasoning_effort="xhigh",
        permission_mode="safe",
    )
    result = await client.run_turn(thread.thread_id, "hello")

    assert result.exit_code == 0
    assert result.final_text == "main final only from delta"


@pytest.mark.asyncio
async def test_native_client_does_not_use_commentary_delta_as_main_final_text() -> None:
    process = FakeProcess(
        stdout=FakeStdout(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "thread": {
                                "id": "thread-1",
                                "name": "Thread One",
                                "updatedAt": "2025-03-01T00:00:00Z",
                                "cwd": "/tmp/work",
                                "source": "cli",
                            }
                        },
                    }
                )
                + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 3, "result": {}}) + "\n",
                json.dumps({"jsonrpc": "2.0", "method": "turn/started", "params": {}})
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/started",
                        "params": {
                            "threadId": "thread-1",
                            "item": {
                                "id": "msg-main-commentary",
                                "type": "agentMessage",
                                "text": "",
                                "phase": "commentary",
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/agentMessage/delta",
                        "params": {
                            "threadId": "thread-1",
                            "itemId": "msg-main-commentary",
                            "delta": "main commentary only",
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-1",
                            "turn": {"status": "completed", "error": None},
                        },
                    }
                )
                + "\n",
            ]
        ),
        stdin=FakeStdin(),
    )

    async def launcher(*_args: Any, **_kwargs: Any) -> FakeProcess:
        return process

    client = NativeCodexClient(binary="codex", launcher=launcher)
    thread = await client.start_thread(
        workdir="/tmp/work",
        model="gpt-5",
        reasoning_effort="xhigh",
        permission_mode="safe",
    )
    result = await client.run_turn(thread.thread_id, "hello")

    assert result.exit_code == 0
    assert result.final_text == ""


@pytest.mark.asyncio
async def test_native_client_keeps_main_final_text_after_subagent_error() -> None:
    process = FakeProcess(
        stdout=FakeStdout(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "thread": {
                                "id": "thread-main",
                                "name": "Main Thread",
                                "updatedAt": "2025-03-01T00:00:00Z",
                                "cwd": "/tmp/work",
                                "source": "cli",
                            }
                        },
                    }
                )
                + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 3, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/started",
                        "params": {"threadId": "thread-main"},
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-main",
                            "item": {
                                "id": "collab-1",
                                "type": "collabAgentToolCall",
                                "tool": "wait",
                                "status": "completed",
                                "senderThreadId": "thread-main",
                                "receiverThreadIds": ["thread-sub-1"],
                                "agentsStates": {
                                    "thread-sub-1": {
                                        "status": "errored",
                                        "message": "tests failed",
                                    }
                                },
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/agentMessage/delta",
                        "params": {
                            "threadId": "thread-main",
                            "itemId": "msg-main-final",
                            "delta": "main recovered after child failure",
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-main",
                            "turn": {"status": "completed", "error": None},
                        },
                    }
                )
                + "\n",
            ]
        ),
        stdin=FakeStdin(),
    )

    async def launcher(*_args: Any, **_kwargs: Any) -> FakeProcess:
        return process

    client = NativeCodexClient(binary="codex", launcher=launcher)
    progress: list[Any] = []

    thread = await client.start_thread(
        workdir="/tmp/work",
        model="gpt-5",
        reasoning_effort="xhigh",
        permission_mode="safe",
    )
    result = await client.run_turn(
        thread.thread_id,
        "hello",
        on_progress=progress.append,
    )

    assert ("thread-sub-1", "出错（tests failed）") in [
        (entry.agent_key, entry.text) for entry in progress
    ]
    assert result.exit_code == 0
    assert result.final_text == "main recovered after child failure"


@pytest.mark.asyncio
async def test_native_client_does_not_use_subagent_final_answer_as_main_final_text(
) -> None:
    process = FakeProcess(
        stdout=FakeStdout(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "thread": {
                                "id": "thread-main",
                                "name": "Main Thread",
                                "updatedAt": "2025-03-01T00:00:00Z",
                                "cwd": "/tmp/work",
                                "source": "cli",
                            }
                        },
                    }
                )
                + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 3, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/started",
                        "params": {"threadId": "thread-main"},
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-sub-1",
                            "item": {
                                "id": "msg-sub-final",
                                "type": "agentMessage",
                                "text": "subagent final answer",
                                "phase": "final_answer",
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-main",
                            "item": {
                                "id": "collab-1",
                                "type": "collabAgentToolCall",
                                "tool": "wait",
                                "status": "completed",
                                "senderThreadId": "thread-main",
                                "receiverThreadIds": ["thread-sub-1"],
                                "agentsStates": {
                                    "thread-sub-1": {
                                        "status": "completed",
                                        "message": "subagent final answer",
                                    }
                                },
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-main",
                            "turn": {"status": "completed", "error": None},
                        },
                    }
                )
                + "\n",
            ]
        ),
        stdin=FakeStdin(),
    )

    async def launcher(*_args: Any, **_kwargs: Any) -> FakeProcess:
        return process

    client = NativeCodexClient(binary="codex", launcher=launcher)

    thread = await client.start_thread(
        workdir="/tmp/work",
        model="gpt-5",
        reasoning_effort="xhigh",
        permission_mode="safe",
    )
    result = await client.run_turn(thread.thread_id, "hello")

    assert result.exit_code == 0
    assert result.final_text == ""


@pytest.mark.asyncio
async def test_native_client_does_not_use_wait_status_message_as_main_final_text(
) -> None:
    process = FakeProcess(
        stdout=FakeStdout(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "thread": {
                                "id": "thread-main",
                                "name": "Main Thread",
                                "updatedAt": "2025-03-01T00:00:00Z",
                                "cwd": "/tmp/work",
                                "source": "cli",
                            }
                        },
                    }
                )
                + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 3, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/started",
                        "params": {"threadId": "thread-main"},
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-main",
                            "item": {
                                "id": "collab-1",
                                "type": "collabAgentToolCall",
                                "tool": "wait",
                                "status": "completed",
                                "senderThreadId": "thread-main",
                                "receiverThreadIds": ["thread-sub-1"],
                                "agentsStates": {
                                    "thread-sub-1": {
                                        "status": "completed",
                                        "message": "tests ready",
                                    }
                                },
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-main",
                            "turn": {"status": "completed", "error": None},
                        },
                    }
                )
                + "\n",
            ]
        ),
        stdin=FakeStdin(),
    )

    async def launcher(*_args: Any, **_kwargs: Any) -> FakeProcess:
        return process

    client = NativeCodexClient(binary="codex", launcher=launcher)

    thread = await client.start_thread(
        workdir="/tmp/work",
        model="gpt-5",
        reasoning_effort="xhigh",
        permission_mode="safe",
    )
    result = await client.run_turn(thread.thread_id, "hello")

    assert result.exit_code == 0
    assert result.final_text == ""


@pytest.mark.asyncio
async def test_native_client_ignores_subagent_turn_completed_until_main_turn_finishes(
) -> None:
    process = FakeProcess(
        stdout=FakeStdout(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "thread": {
                                "id": "thread-main",
                                "name": "Main Thread",
                                "updatedAt": "2025-03-01T00:00:00Z",
                                "cwd": "/tmp/work",
                                "source": "cli",
                            }
                        },
                    }
                )
                + "\n",
                json.dumps({"jsonrpc": "2.0", "id": 3, "result": {}}) + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/started",
                        "params": {"threadId": "thread-main"},
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-sub-1",
                            "item": {
                                "id": "msg-sub-final",
                                "type": "agentMessage",
                                "text": "subagent final answer",
                                "phase": "final_answer",
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-sub-1",
                            "turn": {"status": "completed", "error": None},
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "item/completed",
                        "params": {
                            "threadId": "thread-main",
                            "item": {
                                "id": "msg-main-final",
                                "type": "agentMessage",
                                "text": "main final answer",
                                "phase": "final_answer",
                            },
                        },
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-main",
                            "turn": {"status": "completed", "error": None},
                        },
                    }
                )
                + "\n",
            ]
        ),
        stdin=FakeStdin(),
    )

    async def launcher(*_args: Any, **_kwargs: Any) -> FakeProcess:
        return process

    client = NativeCodexClient(binary="codex", launcher=launcher)

    thread = await client.start_thread(
        workdir="/tmp/work",
        model="gpt-5",
        reasoning_effort="xhigh",
        permission_mode="safe",
    )
    result = await client.run_turn(thread.thread_id, "hello")

    assert result.exit_code == 0
    assert result.thread_id == "thread-main"
    assert result.final_text == "main final answer"


@pytest.mark.asyncio
async def test_native_client_reads_large_stdout_frame_without_readline_limit(
    tmp_path: Path,
) -> None:
    long_text = "A" * (2 * 1024 * 1024)
    thread_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "thread": {
                "id": "thread-1",
                "name": "Thread One",
                "updatedAt": "2025-03-01T00:00:00Z",
                "cwd": "/tmp/work",
                "source": "cli",
            }
        },
    }
    item_payload = {
        "jsonrpc": "2.0",
        "method": "item/completed",
        "params": {
            "threadId": "thread-1",
            "item": {
                "id": "msg-1",
                "type": "agentMessage",
                "text": long_text,
            },
        },
    }
    completed_payload = {
        "jsonrpc": "2.0",
        "method": "turn/completed",
        "params": {
            "threadId": "thread-1",
            "turn": {"status": "completed", "error": None},
        },
    }
    script = (
        "import json, sys\n"
        f"long_text = {long_text!r}\n"
        "messages = [\n"
        "    {'jsonrpc': '2.0', 'id': 1, 'result': {}},\n"
        f"    {thread_payload!r},\n"
        "    {'jsonrpc': '2.0', 'id': 3, 'result': {}},\n"
        f"    {item_payload!r},\n"
        f"    {completed_payload!r},\n"
        "]\n"
        "for message in messages:\n"
        "    sys.stdout.write(json.dumps(message) + '\\n')\n"
        "    sys.stdout.flush()\n"
    )
    script_path = tmp_path / "large_native_stdout.py"
    script_path.write_text(script, encoding="utf-8")

    async def launcher(*_args: Any, **_kwargs: Any):
        return await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1024,
        )

    client = NativeCodexClient(
        binary="codex",
        launcher=launcher,
        stream_read_limit=8 * 1024 * 1024,
    )
    try:
        thread = await client.start_thread(
            workdir="/tmp/work",
            model="gpt-5",
            reasoning_effort="xhigh",
            permission_mode="safe",
        )
        result = await client.run_turn(thread.thread_id, "hello")

        assert result.exit_code == 0
        assert result.final_text == long_text
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_native_client_ignores_large_stderr_frames() -> None:
    huge_stderr = "E" * 4096
    thread_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "thread": {
                "id": "thread-1",
                "name": "Thread One",
                "updatedAt": "2025-03-01T00:00:00Z",
                "cwd": "/tmp/work",
                "source": "cli",
            }
        },
    }
    script = (
        "import json, sys\n"
        f"huge_stderr = {huge_stderr!r}\n"
        "sys.stdout.write("
        "json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {}}) + '\\n'"
        ")\n"
        "sys.stdout.flush()\n"
        "sys.stderr.write(huge_stderr + '\\n')\n"
        "sys.stderr.flush()\n"
        f"sys.stdout.write(json.dumps({thread_payload!r}) + '\\n')\n"
        "sys.stdout.flush()\n"
    )

    async def launcher(*_args: Any, **kwargs: Any):
        return await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=kwargs.get("stderr", asyncio.subprocess.PIPE),
            limit=int(kwargs.get("limit", 1024)),
    )

    client = NativeCodexClient(binary="codex", launcher=launcher, stream_read_limit=1024)
    try:
        thread = await client.start_thread(
            workdir="/tmp/work",
            model="gpt-5",
            reasoning_effort="xhigh",
            permission_mode="safe",
        )

        assert thread.thread_id == "thread-1"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_native_client_reports_friendly_error_for_oversized_frame() -> None:
    long_text = "A" * 4096
    thread_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "thread": {
                "id": "thread-1",
                "name": "Thread One",
                "updatedAt": "2025-03-01T00:00:00Z",
                "cwd": "/tmp/work",
                "source": "cli",
            }
        },
    }
    item_payload = {
        "jsonrpc": "2.0",
        "method": "item/completed",
        "params": {
            "threadId": "thread-1",
            "item": {
                "id": "msg-1",
                "type": "agentMessage",
                "text": long_text,
            },
        },
    }
    script = (
        "import json, sys\n"
        f"long_text = {long_text!r}\n"
        "sys.stdout.write("
        "json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {}}) + '\\n'"
        ")\n"
        "sys.stdout.flush()\n"
        f"sys.stdout.write(json.dumps({thread_payload!r}) + '\\n')\n"
        "sys.stdout.flush()\n"
        "sys.stdout.write("
        "json.dumps({'jsonrpc': '2.0', 'id': 3, 'result': {}}) + '\\n'"
        ")\n"
        "sys.stdout.flush()\n"
        f"sys.stdout.write(json.dumps({item_payload!r}) + '\\n')\n"
        "sys.stdout.flush()\n"
    )

    async def launcher(*_args: Any, **kwargs: Any):
        return await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=kwargs.get("stderr", asyncio.subprocess.PIPE),
            limit=int(kwargs.get("limit", 1024)),
        )

    client = NativeCodexClient(binary="codex", launcher=launcher, stream_read_limit=1024)
    try:
        thread = await client.start_thread(
            workdir="/tmp/work",
            model="gpt-5",
            reasoning_effort="xhigh",
            permission_mode="safe",
        )

        with pytest.raises(RuntimeError, match="codex_stream_read_limit"):
            await client.run_turn(thread.thread_id, "hello")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_native_client_reports_incomplete_protocol_frame() -> None:
    thread_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "thread": {
                "id": "thread-1",
                "name": "Thread One",
                "updatedAt": "2025-03-01T00:00:00Z",
                "cwd": "/tmp/work",
                "source": "cli",
            }
        },
    }
    script = (
        "import json, sys\n"
        "sys.stdout.write("
        "json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {}}) + '\\n'"
        ")\n"
        "sys.stdout.flush()\n"
        f"sys.stdout.write(json.dumps({thread_payload!r}) + '\\n')\n"
        "sys.stdout.flush()\n"
        "sys.stdout.write("
        "json.dumps({'jsonrpc': '2.0', 'id': 3, 'result': {}}) + '\\n'"
        ")\n"
        "sys.stdout.flush()\n"
        "sys.stdout.write('{\"jsonrpc\":\"2.0\",\"method\":\"turn/completed\"')\n"
        "sys.stdout.flush()\n"
    )

    async def launcher(*_args: Any, **kwargs: Any):
        return await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=kwargs.get("stderr", asyncio.subprocess.PIPE),
            limit=int(kwargs.get("limit", 1024)),
        )

    client = NativeCodexClient(binary="codex", launcher=launcher, stream_read_limit=1024)
    try:
        thread = await client.start_thread(
            workdir="/tmp/work",
            model="gpt-5",
            reasoning_effort="xhigh",
            permission_mode="safe",
        )

        with pytest.raises(RuntimeError, match="不完整的协议消息"):
            await client.run_turn(thread.thread_id, "hello")
    finally:
        await client.close()
