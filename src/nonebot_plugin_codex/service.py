from __future__ import annotations

import json
import shutil
import asyncio
import inspect
import secrets
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from collections.abc import Callable, Awaitable
from dataclasses import field, asdict, dataclass

from nonebot.adapters.telegram.model import InlineKeyboardButton, InlineKeyboardMarkup

from .native_client import NativeCodexClient

ProgressCallback = Callable[[str], Awaitable[None]]
StreamTextCallback = Callable[[str], Awaitable[None]]
ProcessLauncher = Callable[..., Awaitable[Any]]
WhichResolver = Callable[[str], str | None]

VISIBLE_MODEL = "list"
SUPPORTED_EFFORT_COMMANDS = {"high", "xhigh"}
SUPPORTED_PERMISSION_MODES = {"safe", "danger"}
FALLBACK_MODEL = "gpt-5"
FALLBACK_REASONING_EFFORT = "high"
BROWSER_CALLBACK_PREFIX = "cdb"
BROWSER_PAGE_SIZE = 8
BROWSER_FILE_SUMMARY_LIMIT = 10
BROWSER_STALE_MESSAGE = "目录面板已失效，请重新执行 /cd"
HISTORY_CALLBACK_PREFIX = "chs"
HISTORY_PAGE_SIZE = 6
HISTORY_STALE_MESSAGE = "历史会话面板已失效，请重新执行 /sessions"
SETTING_CALLBACK_PREFIX = "csp"
SETTING_STALE_MESSAGE = "设置面板已失效，请重新执行对应命令"
SUPPORTED_SETTING_PANELS = {"mode", "model", "effort", "permission"}


@dataclass(slots=True)
class CodexBridgeSettings:
    binary: str = "codex"
    workdir: str = field(default_factory=lambda: str(Path.home()))
    kill_timeout: float = 5.0
    progress_history: int = 6
    diagnostic_history: int = 20
    chunk_size: int = 3500
    stream_read_limit: int = 1024 * 1024
    models_cache_path: Path = field(
        default_factory=lambda: Path.home() / ".codex" / "models_cache.json"
    )
    codex_config_path: Path = field(
        default_factory=lambda: Path.home() / ".codex" / "config.toml"
    )
    preferences_path: Path = field(
        default_factory=lambda: Path("data") / "codex_bridge" / "preferences.json"
    )
    session_index_path: Path = field(
        default_factory=lambda: Path.home() / ".codex" / "session_index.jsonl"
    )
    sessions_dir: Path = field(
        default_factory=lambda: Path.home() / ".codex" / "sessions"
    )
    archived_sessions_dir: Path = field(
        default_factory=lambda: Path.home() / ".codex" / "archived_sessions"
    )


@dataclass(slots=True)
class ModelInfo:
    slug: str
    display_name: str
    visibility: str
    priority: int
    default_reasoning_level: str
    supported_reasoning_levels: list[str]


@dataclass(slots=True)
class ChatPreferences:
    model: str
    reasoning_effort: str
    permission_mode: str = "safe"
    workdir: str = field(default_factory=lambda: str(Path.home()))
    default_mode: str = "resume"


@dataclass(slots=True)
class ChatSession:
    active: bool = False
    active_mode: str = "resume"
    native_thread_id: str | None = None
    exec_thread_id: str | None = None
    thread_id: str | None = None
    strict_resume: bool = False
    running: bool = False
    process: Any = None
    native_runner: Any = None
    runner_task: asyncio.Task[Any] | None = None
    progress_message_id: int | None = None
    stream_message_id: int | None = None
    last_agent_message: str = ""
    last_stream_text: str = ""
    last_stream_rendered_text: str = ""
    stream_message_truncated: bool = False
    progress_lines: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    cancel_requested: bool = False


@dataclass(slots=True)
class RunResult:
    exit_code: int
    final_text: str = ""
    thread_id: str | None = None
    notice: str = ""
    diagnostics: list[str] = field(default_factory=list)
    cancelled: bool = False


@dataclass(slots=True)
class DirectoryEntry:
    name: str
    path: str
    is_dir: bool = True


@dataclass(slots=True)
class HistoricalSessionSummary:
    session_id: str
    thread_name: str
    updated_at: str
    kind: str = "exec"
    cwd: str | None = None
    source_kind: str | None = None
    source_path: str | None = None
    archived: bool = False
    missing: bool = False
    preview: str | None = None
    last_user_text: str | None = None
    last_assistant_text: str | None = None


@dataclass(slots=True)
class HistoryBrowserState:
    chat_key: str
    page: int
    token: str
    version: int
    entries: list[HistoricalSessionSummary]
    scope: str = "menu"
    selected_session_id: str | None = None
    message_id: int | None = None


@dataclass(slots=True)
class DirectoryBrowserState:
    chat_key: str
    current_path: str
    page: int
    token: str
    version: int
    entries: list[DirectoryEntry]
    show_hidden: bool = False
    files: list[str] = field(default_factory=list)
    message_id: int | None = None


@dataclass(slots=True)
class SettingPanelState:
    chat_key: str
    kind: str
    token: str
    version: int
    message_id: int | None = None


def build_chat_key(chat_type: str, chat_id: int) -> str:
    if chat_type == "private":
        return f"private_{chat_id}"
    return f"group_{chat_id}"


def build_exec_argv(
    binary: str,
    workdir: str,
    prompt: str,
    *,
    model: str,
    reasoning_effort: str,
    permission_mode: str,
    thread_id: str | None = None,
) -> list[str]:
    base_args = [
        binary,
        "exec",
    ]
    if thread_id:
        base_args.extend(["resume"])
    base_args.extend(
        [
            "--json",
            "--skip-git-repo-check",
        ]
    )
    if not thread_id:
        base_args.extend(["-C", workdir])
    base_args.extend(
        [
            "-m",
            model,
            "-c",
            f'model_reasoning_effort="{reasoning_effort}"',
        ]
    )
    if permission_mode == "safe":
        if thread_id:
            base_args.append("--full-auto")
        else:
            base_args.extend(["--sandbox", "workspace-write"])
    elif permission_mode == "danger":
        base_args.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        raise ValueError(f"Unsupported permission mode: {permission_mode}")
    if thread_id:
        base_args.append(thread_id)
    base_args.append(prompt)
    return base_args


def encode_browser_callback(
    token: str,
    version: int,
    action: str,
    index: int | None = None,
) -> str:
    suffix = "" if index is None else f":{index}"
    return f"{BROWSER_CALLBACK_PREFIX}:{token}:{version}:{action}{suffix}"


def decode_browser_callback(payload: str) -> tuple[str, int, str, int | None]:
    parts = payload.split(":")
    if len(parts) not in {4, 5} or parts[0] != BROWSER_CALLBACK_PREFIX:
        raise ValueError("无效的目录回调。")
    token = parts[1]
    try:
        version = int(parts[2])
    except ValueError as exc:
        raise ValueError("无效的目录回调。") from exc
    action = parts[3]
    index: int | None = None
    if len(parts) == 5:
        try:
            index = int(parts[4])
        except ValueError as exc:
            raise ValueError("无效的目录回调。") from exc
    return token, version, action, index


def encode_history_callback(
    token: str,
    version: int,
    action: str,
    index: int | None = None,
) -> str:
    suffix = "" if index is None else f":{index}"
    return f"{HISTORY_CALLBACK_PREFIX}:{token}:{version}:{action}{suffix}"


def decode_history_callback(payload: str) -> tuple[str, int, str, int | None]:
    parts = payload.split(":")
    if len(parts) not in {4, 5} or parts[0] != HISTORY_CALLBACK_PREFIX:
        raise ValueError("无效的历史会话回调。")
    token = parts[1]
    try:
        version = int(parts[2])
    except ValueError as exc:
        raise ValueError("无效的历史会话回调。") from exc
    action = parts[3]
    index: int | None = None
    if len(parts) == 5:
        try:
            index = int(parts[4])
        except ValueError as exc:
            raise ValueError("无效的历史会话回调。") from exc
    return token, version, action, index


def encode_setting_callback(
    token: str,
    version: int,
    action: str,
    value: str | None = None,
) -> str:
    suffix = "" if value is None else f":{value}"
    return f"{SETTING_CALLBACK_PREFIX}:{token}:{version}:{action}{suffix}"


def decode_setting_callback(payload: str) -> tuple[str, int, str, str | None]:
    parts = payload.split(":")
    if len(parts) not in {4, 5} or parts[0] != SETTING_CALLBACK_PREFIX:
        raise ValueError("无效的设置回调。")
    token = parts[1]
    try:
        version = int(parts[2])
    except ValueError as exc:
        raise ValueError("无效的设置回调。") from exc
    action = parts[3]
    value = parts[4] if len(parts) == 5 else None
    return token, version, action, value


def parse_event_line(line: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict) and isinstance(payload.get("type"), str):
        return payload
    return None


def should_forward_follow_up(session: ChatSession | None, text: str) -> bool:
    if session is None or not session.active or session.running:
        return False
    plain = text.strip()
    return bool(plain and not plain.startswith("/"))


def chunk_text(text: str, limit: int) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return [chunk for chunk in chunks if chunk]


def format_result_text(result: RunResult) -> str:
    parts: list[str] = []
    if result.notice:
        parts.append(result.notice)
    if result.cancelled:
        parts.append("Codex 已中断。")
    elif result.final_text:
        parts.append(result.final_text)
    elif result.exit_code == 0:
        parts.append("Codex 已完成，但没有返回可展示的最终文本。")
    else:
        parts.append("Codex 执行失败。")
        if result.diagnostics:
            parts.append("\n".join(result.diagnostics[-5:]))
    return "\n\n".join(parts)


def format_preferences_summary(preferences: ChatPreferences) -> str:
    return (
        f"模型: {preferences.model} | 推理: {preferences.reasoning_effort} | "
        f"权限: {preferences.permission_mode}"
    )


def format_file_summary(files: list[str]) -> str:
    if not files:
        return "文件：无"
    preview = "，".join(files[:BROWSER_FILE_SUMMARY_LIMIT])
    remaining = len(files) - BROWSER_FILE_SUMMARY_LIMIT
    suffix = f" 等 {len(files)} 个" if remaining > 0 else ""
    return f"文件：{preview}{suffix}"


def _trim_command(command: str, limit: int = 120) -> str:
    compact = " ".join(command.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _append_progress_line(session: ChatSession, line: str, limit: int) -> None:
    session.progress_lines.append(line)
    if len(session.progress_lines) > limit:
        del session.progress_lines[:-limit]


def _append_diagnostic(session: ChatSession, line: str, limit: int) -> None:
    session.diagnostics.append(line)
    if len(session.diagnostics) > limit:
        del session.diagnostics[:-limit]


def _apply_event(
    session: ChatSession,
    event: dict[str, Any],
    *,
    progress_history: int,
) -> tuple[bool, str | None]:
    event_type = event["type"]
    if event_type == "thread.started":
        thread_id = event.get("thread_id")
        if isinstance(thread_id, str) and thread_id:
            session.thread_id = thread_id
        return True, None
    if event_type == "turn.started":
        _append_progress_line(session, "开始处理请求", progress_history)
        return True, None
    if event_type not in {"item.started", "item.completed"}:
        return False, None

    item = event.get("item")
    if not isinstance(item, dict):
        return False, None

    item_type = item.get("type")
    if item_type == "command_execution":
        command = _trim_command(str(item.get("command", "")))
        prefix = "执行" if event_type == "item.started" else "完成"
        _append_progress_line(session, f"{prefix}: {command}", progress_history)
        return True, None

    if item_type == "agent_message":
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            stripped = text.strip()
            session.last_agent_message = stripped
            if stripped != session.last_stream_text:
                session.last_stream_text = stripped
                return False, stripped
        return False, None

    return False, None


def render_progress_text(session: ChatSession, *, header: str | None = None) -> str:
    parts: list[str] = []
    if header:
        parts.append(header)
    if not session.progress_lines:
        parts.append("Codex 运行中…")
    else:
        body = "\n".join(f"- {line}" for line in session.progress_lines)
        parts.append(f"Codex 运行中…\n{body}")
    return "\n".join(parts)


async def terminate_process(process: Any, timeout: float) -> None:
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


class CodexBridgeService:
    def __init__(
        self,
        settings: CodexBridgeSettings,
        *,
        launcher: ProcessLauncher | None = None,
        native_client: NativeCodexClient | None = None,
        which_resolver: WhichResolver = shutil.which,
    ) -> None:
        self.settings = settings
        self.launcher = launcher or asyncio.create_subprocess_exec
        self.native_client = native_client
        self.which_resolver = which_resolver
        self.sessions: dict[str, ChatSession] = {}
        self.preference_overrides = self._load_preferences()
        self.directory_browsers: dict[str, DirectoryBrowserState] = {}
        self.history_browsers: dict[str, HistoryBrowserState] = {}
        self.setting_panels: dict[str, SettingPanelState] = {}
        self._native_history_entries: list[HistoricalSessionSummary] = []
        self._native_history_loaded = False

    def _configured_workdir(self) -> str:
        configured = Path(self.settings.workdir).expanduser()
        try:
            return str(configured.resolve())
        except OSError:
            return str(configured)

    def _spawn_native_client(self) -> Any:
        if self.native_client is None:
            return None
        if isinstance(self.native_client, NativeCodexClient):
            return self.native_client.clone()
        return self.native_client

    async def _close_native_runner(self, runner: Any) -> None:
        if runner is None:
            return
        close = getattr(runner, "close", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result

    def _load_history_index(self) -> tuple[dict[str, tuple[str, str]], bool]:
        path = self.settings.session_index_path
        try:
            raw_lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return {}, False
        except OSError as exc:
            raise ValueError("无法读取 Codex 历史会话索引。") from exc

        indexed: dict[str, tuple[str, str]] = {}
        for line in raw_lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            session_id = payload.get("id")
            thread_name = payload.get("thread_name")
            updated_at = payload.get("updated_at")
            if not all(
                isinstance(value, str) and value
                for value in (session_id, thread_name, updated_at)
            ):
                continue
            indexed[session_id] = (thread_name, updated_at)
        return indexed, True

    def _normalize_history_title(self, text: str) -> str | None:
        plain = " ".join(text.split())
        if not plain:
            return None
        if plain.startswith("# AGENTS.md instructions"):
            return None
        if plain.startswith("<environment_context>"):
            return None
        if self._is_noise_history_text(plain):
            return None
        if len(plain) <= 120:
            return plain
        return f"{plain[:117]}..."

    def _normalize_history_preview(self, text: str) -> str | None:
        plain = " ".join(text.split())
        if not plain or self._is_noise_history_text(plain):
            return None
        if len(plain) <= 240:
            return plain
        return f"{plain[:237]}..."

    def _parse_history_time(self, value: str) -> datetime | None:
        plain = value.strip()
        if not plain:
            return None

        try:
            timestamp = float(plain)
        except ValueError:
            timestamp = None
        if timestamp is not None:
            if abs(timestamp) >= 1_000_000_000_000:
                timestamp /= 1000
            try:
                return datetime.fromtimestamp(timestamp, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None

        normalized = plain
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _format_history_relative_time(self, value: str) -> str:
        parsed = self._parse_history_time(value)
        if parsed is None:
            return value

        elapsed_seconds = max(
            0,
            int((datetime.now(timezone.utc) - parsed).total_seconds()),
        )
        if elapsed_seconds < 60:
            return "刚刚"

        minutes = elapsed_seconds // 60
        if minutes < 60:
            return f"{minutes} 分钟前"

        hours = elapsed_seconds // 3600
        if hours < 24:
            return f"{hours} 小时前"

        days = elapsed_seconds // 86400
        if days < 7:
            return f"{days} 天前"

        weeks = days // 7
        if days < 30:
            return f"{weeks} 周前"

        months = days // 30
        if days < 365:
            return f"{months} 个月前"

        years = days // 365
        return f"{years} 年前"

    def _format_history_local_time(self, value: str) -> str:
        parsed = self._parse_history_time(value)
        if parsed is None:
            return value
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    def _is_noise_history_text(self, text: str) -> bool:
        lowered = text.strip().lower()
        if not lowered:
            return True
        if lowered.startswith("# agents.md instructions"):
            return True
        if lowered.startswith("<environment_context>"):
            return True
        if "you are a helpful assistant" in lowered and (
            "generate a concise ui title" in lowered
            or "you will be presented with a user prompt" in lowered
            or "generate a clear, informative task title" in lowered
        ):
            return True
        return False

    def _extract_history_title(self, payload: dict[str, Any]) -> str | None:
        payload_type = payload.get("type")
        if payload_type == "event_msg":
            event = payload.get("payload")
            if not isinstance(event, dict) or event.get("type") != "user_message":
                return None
            message = event.get("message")
            if isinstance(message, str):
                return self._normalize_history_title(message)
            return None

        if payload_type != "response_item":
            return None
        item = payload.get("payload")
        if not isinstance(item, dict):
            return None
        if item.get("type") != "message" or item.get("role") != "user":
            return None
        content = item.get("content")
        if not isinstance(content, list):
            return None
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "input_text":
                continue
            text = part.get("text")
            if isinstance(text, str):
                title = self._normalize_history_title(text)
                if title:
                    return title
        return None

    def _extract_history_message(
        self,
        payload: dict[str, Any],
    ) -> tuple[str, str] | None:
        payload_type = payload.get("type")
        if payload_type == "event_msg":
            event = payload.get("payload")
            if not isinstance(event, dict) or event.get("type") != "user_message":
                return None
            message = event.get("message")
            if not isinstance(message, str):
                return None
            normalized = self._normalize_history_preview(message)
            if normalized is None:
                return None
            return "user", normalized

        if payload_type != "response_item":
            return None
        item = payload.get("payload")
        if not isinstance(item, dict):
            return None
        if item.get("type") != "message":
            return None
        role = item.get("role")
        if role not in {"user", "assistant"}:
            return None
        content = item.get("content")
        if not isinstance(content, list):
            return None
        supported_types = {"input_text"} if role == "user" else {"output_text"}
        texts: list[str] = []
        for part in content:
            if not isinstance(part, dict) or part.get("type") not in supported_types:
                continue
            text = part.get("text")
            if isinstance(text, str):
                normalized = self._normalize_history_preview(text)
                if normalized:
                    texts.append(normalized)
        if not texts:
            return None
        return role, " ".join(texts)

    def _parse_history_session_file(
        self,
        path: Path,
        *,
        archived: bool,
        indexed: tuple[str, str] | None,
    ) -> HistoricalSessionSummary | None:
        session_id: str | None = None
        cwd: str | None = None
        source_kind: str | None = None
        discovered_title: str | None = None
        discovered_updated_at: str | None = None
        last_user_text: str | None = None
        last_assistant_text: str | None = None

        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    timestamp = payload.get("timestamp")
                    if isinstance(timestamp, str) and timestamp:
                        discovered_updated_at = timestamp
                    if discovered_title is None:
                        discovered_title = self._extract_history_title(payload)
                    extracted_message = self._extract_history_message(payload)
                    if extracted_message is not None:
                        role, text = extracted_message
                        if role == "user":
                            last_user_text = text
                        elif role == "assistant":
                            last_assistant_text = text
                    if payload.get("type") != "session_meta":
                        continue
                    meta = payload.get("payload")
                    if not isinstance(meta, dict):
                        continue
                    meta_session_id = meta.get("id")
                    if isinstance(meta_session_id, str) and meta_session_id:
                        session_id = meta_session_id
                    meta_cwd = meta.get("cwd")
                    if isinstance(meta_cwd, str) and meta_cwd:
                        cwd = meta_cwd
                    meta_source = meta.get("source")
                    if isinstance(meta_source, str) and meta_source:
                        source_kind = meta_source
                    meta_updated_at = meta.get("timestamp")
                    if isinstance(meta_updated_at, str) and meta_updated_at:
                        discovered_updated_at = meta_updated_at
        except OSError:
            if indexed is None:
                return None
            return HistoricalSessionSummary(
                session_id=session_id or path.stem,
                thread_name=indexed[0],
                updated_at=indexed[1],
                kind="exec",
                source_path=str(path),
                archived=archived,
                missing=True,
                preview=indexed[0],
            )

        if not session_id:
            return None

        if indexed is not None:
            thread_name, updated_at = indexed
        else:
            thread_name = discovered_title or session_id
            updated_at = discovered_updated_at or ""

        preview = last_assistant_text or last_user_text or thread_name
        return HistoricalSessionSummary(
            session_id=session_id,
            thread_name=thread_name,
            updated_at=updated_at,
            kind="exec",
            cwd=cwd,
            source_kind=source_kind or "exec",
            source_path=str(path),
            archived=archived,
            missing=False,
            preview=preview,
            last_user_text=last_user_text,
            last_assistant_text=last_assistant_text,
        )

    def _collect_history_log_summaries(self) -> dict[str, HistoricalSessionSummary]:
        collected: dict[str, HistoricalSessionSummary] = {}
        for path, archived in self._iter_history_files():
            summary = self._parse_history_session_file(
                path,
                archived=archived,
                indexed=None,
            )
            if summary is None:
                continue
            existing = collected.get(summary.session_id)
            if existing is None or (existing.archived and not summary.archived):
                collected[summary.session_id] = summary
        return collected

    def _enrich_history_summary_from_log(
        self,
        summary: HistoricalSessionSummary,
        log_summary: HistoricalSessionSummary | None,
    ) -> HistoricalSessionSummary:
        if log_summary is None:
            return summary

        if summary.cwd is None:
            summary.cwd = log_summary.cwd
        if summary.source_kind is None:
            summary.source_kind = log_summary.source_kind
        summary.source_path = log_summary.source_path
        summary.archived = log_summary.archived
        summary.missing = log_summary.missing
        summary.last_user_text = log_summary.last_user_text
        summary.last_assistant_text = log_summary.last_assistant_text
        if log_summary.last_assistant_text or log_summary.last_user_text:
            summary.preview = (
                log_summary.last_assistant_text or log_summary.last_user_text
            )
        elif summary.preview is None and log_summary.preview is not None:
            summary.preview = log_summary.preview
        return summary

    def _iter_history_files(self) -> list[tuple[Path, bool]]:
        files: list[tuple[Path, bool]] = []
        if self.settings.sessions_dir.exists():
            files.extend(
                (path, False) for path in self.settings.sessions_dir.rglob("*.jsonl")
            )
        if self.settings.archived_sessions_dir.exists():
            files.extend(
                (path, True)
                for path in self.settings.archived_sessions_dir.rglob("*.jsonl")
            )
        return sorted(files, key=lambda item: str(item[0]))

    def _collect_exec_history_sessions(
        self,
        index_entries: dict[str, tuple[str, str]],
    ) -> list[HistoricalSessionSummary]:
        collected = self._collect_history_log_summaries()
        for summary in collected.values():
            indexed = index_entries.get(summary.session_id)
            if indexed is not None:
                summary.thread_name = indexed[0]
                summary.updated_at = indexed[1]
                if summary.last_user_text is None and summary.last_assistant_text is None:
                    summary.preview = summary.thread_name

        for session_id, (thread_name, updated_at) in index_entries.items():
            if session_id in collected:
                continue
            collected[session_id] = HistoricalSessionSummary(
                session_id=session_id,
                thread_name=thread_name,
                updated_at=updated_at,
                kind="exec",
                source_kind="exec",
                missing=True,
                preview=thread_name,
            )

        return sorted(
            collected.values(),
            key=lambda session: session.updated_at,
            reverse=True,
        )

    async def _load_native_history_sessions(self) -> list[HistoricalSessionSummary]:
        if self.native_client is None:
            return []
        history_logs = self._collect_history_log_summaries()
        client = self._spawn_native_client()
        try:
            threads = await client.list_threads()
        except Exception:
            return []
        finally:
            await self._close_native_runner(client)
        entries = []
        for thread in threads:
            entry = HistoricalSessionSummary(
                session_id=thread.thread_id,
                thread_name=thread.thread_name,
                updated_at=thread.updated_at,
                kind="native",
                cwd=thread.cwd,
                source_kind=thread.source_kind,
                preview=thread.preview,
            )
            entries.append(
                self._enrich_history_summary_from_log(
                    entry,
                    history_logs.get(thread.thread_id),
                )
            )
        return sorted(entries, key=lambda session: session.updated_at, reverse=True)

    def _get_native_history_sessions(self) -> list[HistoricalSessionSummary]:
        if self.native_client is None:
            return []
        if not self._native_history_loaded:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                self._native_history_entries = asyncio.run(
                    self._load_native_history_sessions()
                )
                self._native_history_loaded = True
            else:
                return list(self._native_history_entries)
        return list(self._native_history_entries)

    async def refresh_history_sessions(self) -> list[HistoricalSessionSummary]:
        self._native_history_entries = await self._load_native_history_sessions()
        self._native_history_loaded = True
        return self.list_history_sessions()

    def list_history_sessions(self) -> list[HistoricalSessionSummary]:
        index_entries, has_index = self._load_history_index()
        native_entries = self._get_native_history_sessions()
        native_ids = {entry.session_id for entry in native_entries}
        exec_entries = [
            entry
            for entry in self._collect_exec_history_sessions(index_entries)
            if entry.session_id not in native_ids
        ]
        if native_entries or exec_entries:
            return native_entries + exec_entries
        if not has_index:
            raise ValueError("未找到 Codex 历史会话索引。")
        raise ValueError("未找到 Codex 历史会话。")

    def get_history_session(self, session_id: str) -> HistoricalSessionSummary:
        for session in self.list_history_sessions():
            if session.session_id == session_id:
                return session
        raise ValueError("未找到指定历史会话。")

    def _history_total_pages(self, entries: list[HistoricalSessionSummary]) -> int:
        return max(1, (len(entries) + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE)

    def _clamp_history_page(
        self, entries: list[HistoricalSessionSummary], page: int
    ) -> int:
        total_pages = self._history_total_pages(entries)
        return max(0, min(page, total_pages - 1))

    def _history_entries_for_scope(self, scope: str) -> list[HistoricalSessionSummary]:
        entries = self.list_history_sessions()
        if scope == "menu":
            return entries
        if scope == "resume":
            return [entry for entry in entries if entry.kind == "native"]
        if scope == "exec":
            return [entry for entry in entries if entry.kind == "exec"]
        raise ValueError("未知历史会话模式。")

    def _replace_history_browser_state(
        self,
        chat_key: str,
        *,
        page: int,
        scope: str = "menu",
        selected_session_id: str | None = None,
        previous: HistoryBrowserState | None = None,
    ) -> HistoryBrowserState:
        entries = self._history_entries_for_scope(scope)
        state = HistoryBrowserState(
            chat_key=chat_key,
            page=self._clamp_history_page(entries, page),
            token=previous.token if previous else self._make_browser_token(),
            version=(previous.version + 1) if previous else 1,
            entries=entries,
            scope=scope,
            selected_session_id=selected_session_id,
            message_id=previous.message_id if previous else None,
        )
        self.history_browsers[chat_key] = state
        return state

    def open_history_browser(self, chat_key: str) -> HistoryBrowserState:
        return self._replace_history_browser_state(chat_key, page=0, scope="menu")

    def get_history_browser(
        self,
        chat_key: str,
        token: str | None = None,
        version: int | None = None,
    ) -> HistoryBrowserState:
        state = self.history_browsers.get(chat_key)
        if state is None:
            raise ValueError(HISTORY_STALE_MESSAGE)
        if token is not None and state.token != token:
            raise ValueError(HISTORY_STALE_MESSAGE)
        if version is not None and state.version != version:
            raise ValueError(HISTORY_STALE_MESSAGE)
        return state

    def remember_history_browser_message(
        self,
        chat_key: str,
        token: str,
        message_id: int | None,
    ) -> None:
        if message_id is None:
            return
        browser = self.get_history_browser(chat_key, token=token)
        browser.message_id = message_id

    def close_history_browser(self, chat_key: str, token: str, version: int) -> None:
        self.get_history_browser(chat_key, token=token, version=version)
        self.history_browsers.pop(chat_key, None)

    def navigate_history_browser(
        self,
        chat_key: str,
        token: str,
        version: int,
        action: str,
        index: int | None = None,
    ) -> HistoryBrowserState:
        browser = self.get_history_browser(chat_key, token=token, version=version)
        if action == "scope_resume":
            return self._replace_history_browser_state(
                chat_key,
                page=0,
                scope="resume",
                previous=browser,
            )
        if action == "scope_exec":
            return self._replace_history_browser_state(
                chat_key,
                page=0,
                scope="exec",
                previous=browser,
            )
        if action == "menu":
            return self._replace_history_browser_state(
                chat_key,
                page=0,
                scope="menu",
                previous=browser,
            )
        if action == "open":
            if index is None or not 0 <= index < len(browser.entries):
                raise ValueError("历史会话不存在。")
            return self._replace_history_browser_state(
                chat_key,
                page=browser.page,
                scope=browser.scope,
                selected_session_id=browser.entries[index].session_id,
                previous=browser,
            )
        if action == "back":
            return self._replace_history_browser_state(
                chat_key,
                page=browser.page,
                scope=browser.scope,
                previous=browser,
            )
        if action == "refresh":
            return self._replace_history_browser_state(
                chat_key,
                page=browser.page,
                scope=browser.scope,
                selected_session_id=browser.selected_session_id,
                previous=browser,
            )
        if action == "prev":
            return self._replace_history_browser_state(
                chat_key,
                page=browser.page - 1,
                scope=browser.scope,
                previous=browser,
            )
        if action == "next":
            return self._replace_history_browser_state(
                chat_key,
                page=browser.page + 1,
                scope=browser.scope,
                previous=browser,
            )
        raise ValueError("未知历史会话操作。")

    def render_history_browser(self, chat_key: str) -> tuple[str, InlineKeyboardMarkup]:
        browser = self.get_history_browser(chat_key)
        preferences = self.get_preferences(chat_key)
        session = self.sessions.get(chat_key)
        current_mode = session.active_mode if session else preferences.default_mode
        if session is None:
            current_thread = "未绑定"
        elif current_mode == "exec":
            current_thread = self._current_exec_thread_id(session) or "未绑定"
        elif self.native_client is not None:
            current_thread = session.native_thread_id or "未绑定"
        else:
            current_thread = session.thread_id or "未绑定"

        if browser.scope == "menu":
            resume_count = sum(1 for entry in browser.entries if entry.kind == "native")
            exec_count = sum(1 for entry in browser.entries if entry.kind == "exec")
            lines = [
                "Codex 历史会话",
                f"当前模式：{current_mode}",
                f"当前绑定：{current_thread}",
                f"当前工作目录：{preferences.workdir}",
                f"resume：{resume_count}",
                f"exec：{exec_count}",
            ]
            keyboard = [
                [
                    InlineKeyboardButton(
                        text=f"resume ({resume_count})",
                        callback_data=encode_history_callback(
                            browser.token,
                            browser.version,
                            "scope_resume",
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=f"exec ({exec_count})",
                        callback_data=encode_history_callback(
                            browser.token,
                            browser.version,
                            "scope_exec",
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="关闭",
                        callback_data=encode_history_callback(
                            browser.token,
                            browser.version,
                            "close",
                        ),
                    )
                ],
            ]
            return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard)

        if browser.selected_session_id is not None:
            selected = next(
                (
                    entry
                    for entry in browser.entries
                    if entry.session_id == browser.selected_session_id
                ),
                None,
            )
            if selected is None:
                raise ValueError("未找到指定历史会话。")
            lines = [
                "Codex 历史会话",
                f"类型：{selected.kind}",
                f"标题：{selected.thread_name}",
                f"更新时间：{self._format_history_local_time(selected.updated_at)}",
                f"原始工作目录：{selected.cwd or '未知'}",
                f"归档：{'是' if selected.archived else '否'}",
                f"上次对话概览：{selected.preview or selected.thread_name}",
            ]
            if selected.last_user_text:
                lines.append(f"上次用户输入：{selected.last_user_text}")
            if selected.last_assistant_text:
                lines.append(f"上次助手回复：{selected.last_assistant_text}")
            if selected.missing:
                lines.append("源会话文件缺失，无法继续该对话。")
            can_continue = not (
                selected.kind == "exec"
                and (selected.missing or selected.source_path is None)
            )
            keyboard: list[list[InlineKeyboardButton]] = []
            if can_continue:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            text="续聊",
                            callback_data=encode_history_callback(
                                browser.token,
                                browser.version,
                                "apply",
                            ),
                        )
                    ]
                )
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text="返回列表",
                        callback_data=encode_history_callback(
                            browser.token,
                            browser.version,
                            "back",
                        ),
                    ),
                    InlineKeyboardButton(
                        text="返回模式选择",
                        callback_data=encode_history_callback(
                            browser.token,
                            browser.version,
                            "menu",
                        ),
                    ),
                    InlineKeyboardButton(
                        text="关闭",
                        callback_data=encode_history_callback(
                            browser.token,
                            browser.version,
                            "close",
                        ),
                    ),
                ]
            )
            return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard)

        total_pages = self._history_total_pages(browser.entries)
        start = browser.page * HISTORY_PAGE_SIZE
        end = start + HISTORY_PAGE_SIZE
        current_entries = browser.entries[start:end]
        lines = [
            "Codex 历史会话",
            f"当前浏览模式：{browser.scope}",
            f"当前模式：{current_mode}",
            f"当前绑定：{current_thread}",
            f"当前工作目录：{preferences.workdir}",
            f"总数：{len(browser.entries)}",
            f"第 {browser.page + 1}/{total_pages} 页",
        ]
        keyboard: list[list[InlineKeyboardButton]] = []
        for offset, entry in enumerate(current_entries):
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text=(
                            f"{entry.thread_name} | "
                            f"{self._format_history_relative_time(entry.updated_at)}"
                        ),
                        callback_data=encode_history_callback(
                            browser.token,
                            browser.version,
                            "open",
                            start + offset,
                        ),
                    )
                ]
            )

        nav_buttons: list[InlineKeyboardButton] = []
        if browser.page > 0:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="上一页",
                    callback_data=encode_history_callback(
                        browser.token,
                        browser.version,
                        "prev",
                    ),
                )
            )
        if browser.page + 1 < total_pages:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="下一页",
                    callback_data=encode_history_callback(
                        browser.token,
                        browser.version,
                        "next",
                    ),
                )
            )
        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append(
            [
                InlineKeyboardButton(
                    text="返回模式选择",
                    callback_data=encode_history_callback(
                        browser.token,
                        browser.version,
                        "menu",
                    ),
                ),
                InlineKeyboardButton(
                    text="刷新",
                    callback_data=encode_history_callback(
                        browser.token,
                        browser.version,
                        "refresh",
                    ),
                ),
                InlineKeyboardButton(
                    text="关闭",
                    callback_data=encode_history_callback(
                        browser.token,
                        browser.version,
                        "close",
                    ),
                ),
            ]
        )
        return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard)

    async def apply_history_session(self, chat_key: str, token: str, version: int) -> str:
        self._ensure_not_running(chat_key)
        browser = self.get_history_browser(chat_key, token=token, version=version)
        if browser.selected_session_id is None:
            raise ValueError("请先选择一个历史会话。")

        selected = next(
            (
                entry
                for entry in browser.entries
                if entry.session_id == browser.selected_session_id
            ),
            None,
        )
        if selected is None:
            raise ValueError("未找到指定历史会话。")
        if selected.kind == "exec" and (selected.missing or selected.source_path is None):
            raise ValueError("源会话文件不存在，无法继续。")

        session = self.activate_chat(chat_key)
        if selected.kind == "native":
            session.active_mode = "resume"
            self._set_native_thread_id(session, selected.session_id)
        else:
            session.active_mode = "exec"
            self._set_exec_thread_id(session, selected.session_id)
        self._sync_legacy_thread_id(session)
        session.strict_resume = True

        current = self.get_preferences(chat_key)
        notice_lines = [
            f"已切换到历史会话（{selected.kind}）：{selected.thread_name}",
            f"当前模式：{'resume' if selected.kind == 'native' else 'exec'}",
        ]
        if selected.cwd:
            target = Path(selected.cwd).expanduser()
            if target.exists() and target.is_dir():
                self.preference_overrides[chat_key] = ChatPreferences(
                    model=current.model,
                    reasoning_effort=current.reasoning_effort,
                    permission_mode=current.permission_mode,
                    workdir=str(target.resolve()),
                    default_mode=current.default_mode,
                )
                self._persist_preferences()
            else:
                notice_lines.append("原工作目录不存在，已保留当前工作目录。")
        notice_lines.append(f"当前工作目录：{self.get_preferences(chat_key).workdir}")
        notice_lines.append("下一条普通消息会继续该会话。")
        return "\n".join(notice_lines)

    def _replace_setting_panel_state(
        self,
        chat_key: str,
        kind: str,
        *,
        previous: SettingPanelState | None = None,
    ) -> SettingPanelState:
        if kind not in SUPPORTED_SETTING_PANELS:
            raise ValueError("未知设置面板。")
        state = SettingPanelState(
            chat_key=chat_key,
            kind=kind,
            token=previous.token if previous else self._make_browser_token(),
            version=(previous.version + 1) if previous else 1,
            message_id=previous.message_id if previous else None,
        )
        self.setting_panels[chat_key] = state
        return state

    def open_setting_panel(self, chat_key: str, kind: str) -> SettingPanelState:
        self._ensure_not_running(chat_key)
        self.get_preferences(chat_key)
        return self._replace_setting_panel_state(chat_key, kind)

    def get_setting_panel(
        self,
        chat_key: str,
        token: str | None = None,
        version: int | None = None,
    ) -> SettingPanelState:
        state = self.setting_panels.get(chat_key)
        if state is None:
            raise ValueError(SETTING_STALE_MESSAGE)
        if token is not None and state.token != token:
            raise ValueError(SETTING_STALE_MESSAGE)
        if version is not None and state.version != version:
            raise ValueError(SETTING_STALE_MESSAGE)
        return state

    def remember_setting_panel_message(
        self,
        chat_key: str,
        token: str,
        message_id: int | None,
    ) -> None:
        if message_id is None:
            return
        panel = self.get_setting_panel(chat_key, token=token)
        panel.message_id = message_id

    def close_setting_panel(self, chat_key: str, token: str, version: int) -> None:
        self.get_setting_panel(chat_key, token=token, version=version)
        self.setting_panels.pop(chat_key, None)

    def navigate_setting_panel(
        self,
        chat_key: str,
        token: str,
        version: int,
        action: str,
    ) -> SettingPanelState:
        panel = self.get_setting_panel(chat_key, token=token, version=version)
        if action != "refresh":
            raise ValueError("未知设置操作。")
        return self._replace_setting_panel_state(chat_key, panel.kind, previous=panel)

    def render_setting_panel(self, chat_key: str) -> tuple[str, InlineKeyboardMarkup]:
        panel = self.get_setting_panel(chat_key)
        preferences = self.get_preferences(chat_key)
        lines: list[str]
        options: list[tuple[str, str]]

        if panel.kind == "mode":
            session = self.sessions.get(chat_key)
            active_mode = session.active_mode if session else preferences.default_mode
            lines = [
                "模式设置",
                f"当前默认模式：{preferences.default_mode}",
                f"当前活跃模式：{active_mode}",
            ]
            options = [
                (
                    "resume",
                    "✓ resume" if preferences.default_mode == "resume" else "resume",
                ),
                ("exec", "✓ exec" if preferences.default_mode == "exec" else "exec"),
            ]
        elif panel.kind == "model":
            lines = [
                "模型设置",
                f"当前设置：{format_preferences_summary(preferences)}",
            ]
            options = [
                (
                    model.slug,
                    f"{'✓ ' if model.slug == preferences.model else ''}{model.slug}",
                )
                for model in self.list_models()
            ]
        elif panel.kind == "effort":
            supported = self.get_supported_efforts(preferences.model)
            lines = [
                "推理强度设置",
                f"当前模型：{preferences.model}",
                f"当前推理强度：{preferences.reasoning_effort}",
                f"支持：{' / '.join(supported)}",
            ]
            options = [
                (
                    effort,
                    (
                        f"✓ {effort}"
                        if effort == preferences.reasoning_effort
                        else effort
                    ),
                )
                for effort in supported
            ]
        elif panel.kind == "permission":
            lines = [
                "权限模式设置",
                f"当前权限模式：{preferences.permission_mode}",
                "safe = workspace-write",
                "danger = 绕过审批与沙箱",
            ]
            options = [
                (
                    "safe",
                    "✓ safe" if preferences.permission_mode == "safe" else "safe",
                ),
                (
                    "danger",
                    (
                        "✓ danger"
                        if preferences.permission_mode == "danger"
                        else "danger"
                    ),
                ),
            ]
        else:
            raise ValueError("未知设置面板。")

        keyboard = [
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=encode_setting_callback(
                        panel.token,
                        panel.version,
                        "set",
                        value,
                    ),
                )
            ]
            for value, label in options
        ]
        keyboard.append(
            [
                InlineKeyboardButton(
                    text="刷新",
                    callback_data=encode_setting_callback(
                        panel.token,
                        panel.version,
                        "refresh",
                    ),
                ),
                InlineKeyboardButton(
                    text="关闭",
                    callback_data=encode_setting_callback(
                        panel.token,
                        panel.version,
                        "close",
                    ),
                ),
            ]
        )
        return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard)

    async def apply_setting_panel_selection(
        self,
        chat_key: str,
        token: str,
        version: int,
        value: str,
    ) -> str:
        panel = self.get_setting_panel(chat_key, token=token, version=version)
        if panel.kind == "mode":
            notice = await self.update_default_mode(chat_key, value)
        elif panel.kind == "model":
            notice = await self.update_model(chat_key, value)
        elif panel.kind == "effort":
            notice = await self.update_reasoning_effort(chat_key, value)
        elif panel.kind == "permission":
            notice = await self.update_permission_mode(chat_key, value)
        else:
            raise ValueError("未知设置面板。")
        self._replace_setting_panel_state(chat_key, panel.kind, previous=panel)
        return notice

    def load_models(self) -> dict[str, ModelInfo]:
        try:
            payload = json.loads(
                self.settings.models_cache_path.read_text(encoding="utf-8")
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError("未找到 Codex 模型缓存文件。") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("Codex 模型缓存文件损坏，无法解析。") from exc

        models = payload.get("models")
        if not isinstance(models, list):
            raise ValueError("Codex 模型缓存文件格式不正确。")

        parsed: dict[str, ModelInfo] = {}
        for item in models:
            if not isinstance(item, dict):
                continue
            slug = item.get("slug")
            if not isinstance(slug, str) or not slug:
                continue
            supported = [
                level.get("effort")
                for level in item.get("supported_reasoning_levels", [])
                if isinstance(level, dict) and isinstance(level.get("effort"), str)
            ]
            parsed[slug] = ModelInfo(
                slug=slug,
                display_name=str(item.get("display_name") or slug),
                visibility=str(item.get("visibility") or ""),
                priority=int(item.get("priority") or 0),
                default_reasoning_level=str(
                    item.get("default_reasoning_level") or "medium"
                ),
                supported_reasoning_levels=supported,
            )
        if not parsed:
            raise ValueError("Codex 模型缓存中没有可用模型。")
        return parsed

    def list_models(self) -> list[ModelInfo]:
        visible = [
            model
            for model in self.load_models().values()
            if model.visibility == VISIBLE_MODEL
        ]
        return sorted(visible, key=lambda model: (model.priority, model.slug))

    def _load_preferences(self) -> dict[str, ChatPreferences]:
        path = self.settings.preferences_path
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        loaded: dict[str, ChatPreferences] = {}
        for chat_key, value in raw.items():
            if not isinstance(chat_key, str) or not isinstance(value, dict):
                continue
            model = value.get("model")
            reasoning_effort = value.get("reasoning_effort")
            permission_mode = value.get("permission_mode")
            workdir = value.get("workdir")
            default_mode = value.get("default_mode")
            if not all(
                isinstance(field, str)
                for field in (model, reasoning_effort, permission_mode)
            ):
                continue
            loaded[chat_key] = ChatPreferences(
                model=model,
                reasoning_effort=reasoning_effort,
                permission_mode=permission_mode,
                workdir=(
                    workdir
                    if isinstance(workdir, str) and workdir
                    else self._configured_workdir()
                ),
                default_mode=(
                    default_mode
                    if isinstance(default_mode, str)
                    and default_mode in {"resume", "exec"}
                    else "resume"
                ),
            )
        return loaded

    def _persist_preferences(self) -> None:
        self.settings.preferences_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = {
            chat_key: asdict(preferences)
            for chat_key, preferences in self.preference_overrides.items()
        }
        self.settings.preferences_path.write_text(
            json.dumps(serialized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_codex_defaults(self) -> tuple[str | None, str | None]:
        path = self.settings.codex_config_path
        if not path.exists():
            return None, None
        try:
            config = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return None, None
        model = config.get("model")
        effort = config.get("model_reasoning_effort")
        return (
            model if isinstance(model, str) else None,
            effort if isinstance(effort, str) else None,
        )

    def _pick_default_model(self, models: dict[str, ModelInfo]) -> ModelInfo:
        configured_model, _ = self._load_codex_defaults()
        if configured_model and configured_model in models:
            return models[configured_model]
        visible = [
            model for model in models.values() if model.visibility == VISIBLE_MODEL
        ]
        ranked = sorted(
            visible or list(models.values()),
            key=lambda model: (model.priority, model.slug),
        )
        return ranked[0]

    def _normalize_effort(self, model: ModelInfo, effort: str | None) -> str:
        supported = set(model.supported_reasoning_levels)
        if effort and effort in supported:
            return effort
        if "high" in supported:
            return "high"
        if model.default_reasoning_level in supported:
            return model.default_reasoning_level
        if model.supported_reasoning_levels:
            return model.supported_reasoning_levels[0]
        return model.default_reasoning_level

    def _default_preferences(self) -> ChatPreferences:
        configured_model, configured_effort = self._load_codex_defaults()
        try:
            models = self.load_models()
        except (FileNotFoundError, ValueError):
            model_slug = configured_model or FALLBACK_MODEL
            effort = configured_effort or FALLBACK_REASONING_EFFORT
        else:
            model = self._pick_default_model(models)
            effort = self._normalize_effort(model, configured_effort)
            model_slug = model.slug
        return ChatPreferences(
            model=model_slug,
            reasoning_effort=effort,
            permission_mode="safe",
            workdir=self._configured_workdir(),
            default_mode="resume",
        )

    def get_session(self, chat_key: str) -> ChatSession:
        return self.sessions.setdefault(chat_key, ChatSession())

    def get_preferences(self, chat_key: str) -> ChatPreferences:
        preferences = self.preference_overrides.get(chat_key)
        if preferences is None:
            preferences = self._default_preferences()
            self.preference_overrides[chat_key] = preferences
            self._persist_preferences()
        return preferences

    def describe_preferences(self, chat_key: str) -> str:
        return format_preferences_summary(self.get_preferences(chat_key))

    def describe_workdir(self, chat_key: str) -> str:
        preferences = self.get_preferences(chat_key)
        session = self.sessions.get(chat_key)
        next_step = "继续当前会话" if session and session.thread_id else "新开会话"
        return (
            f"当前工作目录：{preferences.workdir}\n"
            f"当前设置：{format_preferences_summary(preferences)}\n"
            f"下一条普通消息：{next_step}"
        )

    def _make_browser_token(self) -> str:
        return secrets.token_hex(4)

    def activate_chat(self, chat_key: str) -> ChatSession:
        session = self.get_session(chat_key)
        if not session.active or session.active_mode not in {"resume", "exec"}:
            session.active_mode = self.get_preferences(chat_key).default_mode
        session.active = True
        self._sync_legacy_thread_id(session)
        return session

    def _ensure_not_running(self, chat_key: str) -> None:
        session = self.sessions.get(chat_key)
        if session and session.running:
            raise RuntimeError("Codex is already running for this chat")

    def _sync_legacy_thread_id(self, session: ChatSession) -> None:
        if session.active_mode == "exec":
            session.thread_id = session.exec_thread_id or session.thread_id
            return
        if self.native_client is not None:
            session.thread_id = session.native_thread_id
            return
        session.thread_id = session.exec_thread_id or session.thread_id

    def _current_exec_thread_id(self, session: ChatSession) -> str | None:
        return session.exec_thread_id or session.thread_id

    def _set_exec_thread_id(self, session: ChatSession, thread_id: str | None) -> None:
        session.exec_thread_id = thread_id
        if session.active_mode == "exec" or self.native_client is None:
            session.thread_id = thread_id

    def _set_native_thread_id(self, session: ChatSession, thread_id: str | None) -> None:
        session.native_thread_id = thread_id
        if session.active_mode == "resume":
            session.thread_id = thread_id

    def _clear_thread_only(self, chat_key: str) -> None:
        session = self.get_session(chat_key)
        session.native_thread_id = None
        session.thread_id = None
        session.exec_thread_id = None
        session.strict_resume = False

    def _browser_total_pages(self, entries: list[DirectoryEntry]) -> int:
        return max(1, (len(entries) + BROWSER_PAGE_SIZE - 1) // BROWSER_PAGE_SIZE)

    def _clamp_browser_page(self, entries: list[DirectoryEntry], page: int) -> int:
        total_pages = self._browser_total_pages(entries)
        return max(0, min(page, total_pages - 1))

    def _resolve_directory_path(self, chat_key: str, raw_path: str) -> str:
        base = Path(self.get_preferences(chat_key).workdir)
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = base / candidate
        resolved = candidate.resolve()
        if not resolved.exists():
            raise ValueError("目录不存在。")
        if not resolved.is_dir():
            raise ValueError("目标不是目录。")
        return str(resolved)

    def _list_directory_entries(
        self,
        path: str,
        *,
        show_hidden: bool,
    ) -> tuple[list[DirectoryEntry], list[str]]:
        directory = Path(path)
        try:
            children = list(directory.iterdir())
        except OSError as exc:
            raise ValueError("目录无法读取。") from exc

        directories: list[DirectoryEntry] = []
        files: list[str] = []
        for child in children:
            if not show_hidden and child.name.startswith("."):
                continue
            try:
                if child.is_dir():
                    directories.append(
                        DirectoryEntry(name=child.name, path=str(child.resolve()))
                    )
                else:
                    files.append(child.name)
            except OSError:
                continue

        directories.sort(key=lambda entry: entry.name.casefold())
        files.sort(key=str.casefold)
        return directories, files

    def _replace_browser_state(
        self,
        chat_key: str,
        path: str,
        *,
        page: int,
        show_hidden: bool | None = None,
        previous: DirectoryBrowserState | None = None,
    ) -> DirectoryBrowserState:
        resolved = str(Path(path).expanduser().resolve())
        effective_show_hidden = (
            previous.show_hidden
            if show_hidden is None and previous is not None
            else bool(show_hidden)
        )
        entries, files = self._list_directory_entries(
            resolved,
            show_hidden=effective_show_hidden,
        )
        state = DirectoryBrowserState(
            chat_key=chat_key,
            current_path=resolved,
            page=self._clamp_browser_page(entries, page),
            token=previous.token if previous else self._make_browser_token(),
            version=(previous.version + 1) if previous else 1,
            entries=entries,
            show_hidden=effective_show_hidden,
            files=files,
            message_id=previous.message_id if previous else None,
        )
        self.directory_browsers[chat_key] = state
        return state

    def open_directory_browser(self, chat_key: str) -> DirectoryBrowserState:
        self._ensure_not_running(chat_key)
        return self._replace_browser_state(
            chat_key,
            self.get_preferences(chat_key).workdir,
            page=0,
        )

    def get_browser(
        self,
        chat_key: str,
        token: str | None = None,
        version: int | None = None,
    ) -> DirectoryBrowserState:
        state = self.directory_browsers.get(chat_key)
        if state is None:
            raise ValueError(BROWSER_STALE_MESSAGE)
        if token is not None and state.token != token:
            raise ValueError(BROWSER_STALE_MESSAGE)
        if version is not None and state.version != version:
            raise ValueError(BROWSER_STALE_MESSAGE)
        return state

    def remember_browser_message(
        self, chat_key: str, token: str, message_id: int | None
    ) -> None:
        if message_id is None:
            return
        browser = self.get_browser(chat_key, token=token)
        browser.message_id = message_id

    def close_directory_browser(self, chat_key: str, token: str, version: int) -> None:
        self.get_browser(chat_key, token=token, version=version)
        self.directory_browsers.pop(chat_key, None)

    def navigate_directory_browser(
        self,
        chat_key: str,
        token: str,
        version: int,
        action: str,
        index: int | None = None,
    ) -> DirectoryBrowserState:
        browser = self.get_browser(chat_key, token=token, version=version)
        if action == "open":
            if index is None or not 0 <= index < len(browser.entries):
                raise ValueError("目录项不存在。")
            return self._replace_browser_state(
                chat_key,
                browser.entries[index].path,
                page=0,
                previous=browser,
            )
        if action == "up":
            return self._replace_browser_state(
                chat_key,
                str(Path(browser.current_path).parent),
                page=0,
                previous=browser,
            )
        if action == "root":
            root = Path(browser.current_path).anchor or "/"
            return self._replace_browser_state(
                chat_key,
                root,
                page=0,
                previous=browser,
            )
        if action == "home":
            return self._replace_browser_state(
                chat_key,
                self._configured_workdir(),
                page=0,
                previous=browser,
            )
        if action == "refresh":
            return self._replace_browser_state(
                chat_key,
                browser.current_path,
                page=browser.page,
                previous=browser,
            )
        if action == "toggle_hidden":
            return self._replace_browser_state(
                chat_key,
                browser.current_path,
                page=browser.page,
                show_hidden=not browser.show_hidden,
                previous=browser,
            )
        if action == "prev":
            return self._replace_browser_state(
                chat_key,
                browser.current_path,
                page=browser.page - 1,
                previous=browser,
            )
        if action == "next":
            return self._replace_browser_state(
                chat_key,
                browser.current_path,
                page=browser.page + 1,
                previous=browser,
            )
        raise ValueError("未知目录操作。")

    async def apply_browser_directory(
        self, chat_key: str, token: str, version: int
    ) -> str:
        browser = self.get_browser(chat_key, token=token, version=version)
        notice = await self.update_workdir(chat_key, browser.current_path)
        self._replace_browser_state(
            chat_key,
            browser.current_path,
            page=browser.page,
            previous=browser,
        )
        return notice

    def render_directory_browser(self, chat_key: str) -> tuple[str, InlineKeyboardMarkup]:
        browser = self.get_browser(chat_key)
        preferences = self.get_preferences(chat_key)
        total_pages = self._browser_total_pages(browser.entries)
        start = browser.page * BROWSER_PAGE_SIZE
        end = start + BROWSER_PAGE_SIZE
        current_entries = browser.entries[start:end]

        lines = [
            "目录浏览",
            f"浏览路径：{browser.current_path}",
            f"当前工作目录：{preferences.workdir}",
            f"子目录：{len(browser.entries)}",
            format_file_summary(browser.files),
        ]
        if total_pages > 1:
            lines.append(f"第 {browser.page + 1}/{total_pages} 页")
        if not browser.entries:
            lines.append("当前目录没有子目录。")

        keyboard: list[list[InlineKeyboardButton]] = []
        for offset, entry in enumerate(current_entries):
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text=entry.name,
                        callback_data=encode_browser_callback(
                            browser.token,
                            browser.version,
                            "open",
                            start + offset,
                        ),
                    )
                ]
            )

        if total_pages > 1:
            page_buttons: list[InlineKeyboardButton] = []
            if browser.page > 0:
                page_buttons.append(
                    InlineKeyboardButton(
                        text="上一页",
                        callback_data=encode_browser_callback(
                            browser.token,
                            browser.version,
                            "prev",
                        ),
                    )
                )
            if browser.page + 1 < total_pages:
                page_buttons.append(
                    InlineKeyboardButton(
                        text="下一页",
                        callback_data=encode_browser_callback(
                            browser.token,
                            browser.version,
                            "next",
                        ),
                    )
                )
            if page_buttons:
                keyboard.append(page_buttons)

        keyboard.append(
            [
                InlineKeyboardButton(
                    text="上一级",
                    callback_data=encode_browser_callback(
                        browser.token, browser.version, "up"
                    ),
                ),
                InlineKeyboardButton(
                    text="根目录 /",
                    callback_data=encode_browser_callback(
                        browser.token, browser.version, "root"
                    ),
                ),
                InlineKeyboardButton(
                    text="Home",
                    callback_data=encode_browser_callback(
                        browser.token, browser.version, "home"
                    ),
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    text="隐藏 .开头项" if browser.show_hidden else "显示 .开头项",
                    callback_data=encode_browser_callback(
                        browser.token,
                        browser.version,
                        "toggle_hidden",
                    ),
                )
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    text="设为当前工作目录",
                    callback_data=encode_browser_callback(
                        browser.token,
                        browser.version,
                        "apply",
                    ),
                ),
                InlineKeyboardButton(
                    text="刷新",
                    callback_data=encode_browser_callback(
                        browser.token,
                        browser.version,
                        "refresh",
                    ),
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    text="关闭",
                    callback_data=encode_browser_callback(
                        browser.token, browser.version, "close"
                    ),
                )
            ]
        )
        return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard)

    async def reset_chat(self, chat_key: str, *, keep_active: bool) -> ChatSession:
        session = self.get_session(chat_key)
        session.cancel_requested = True
        runner_task = session.runner_task
        await self._close_native_runner(session.native_runner)
        await terminate_process(session.process, self.settings.kill_timeout)
        current_task = asyncio.current_task()
        if runner_task is not None and runner_task is not current_task:
            try:
                await asyncio.wait_for(
                    asyncio.shield(runner_task), timeout=self.settings.kill_timeout
                )
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass
        session.active = keep_active
        preferences = self.preference_overrides.get(chat_key)
        if preferences is not None:
            session.active_mode = preferences.default_mode
        elif session.active_mode not in {"resume", "exec"}:
            session.active_mode = "resume"
        session.native_thread_id = None
        session.exec_thread_id = None
        session.thread_id = None
        session.strict_resume = False
        session.running = False
        session.process = None
        session.native_runner = None
        session.runner_task = None
        session.progress_message_id = None
        session.stream_message_id = None
        session.last_agent_message = ""
        session.last_stream_text = ""
        session.last_stream_rendered_text = ""
        session.stream_message_truncated = False
        session.progress_lines.clear()
        session.diagnostics.clear()
        session.cancel_requested = False
        return session

    async def update_model(self, chat_key: str, slug: str) -> str:
        self._ensure_not_running(chat_key)
        models = self.load_models()
        if slug not in models:
            raise ValueError("未找到指定模型。")

        current = self.get_preferences(chat_key)
        model = models[slug]
        next_effort = current.reasoning_effort
        notice = ""
        if next_effort not in model.supported_reasoning_levels:
            downgraded = self._normalize_effort(model, "high")
            next_effort = downgraded
            notice = f"推理强度已自动降级为 {downgraded}。"

        self.preference_overrides[chat_key] = ChatPreferences(
            model=slug,
            reasoning_effort=next_effort,
            permission_mode=current.permission_mode,
            workdir=current.workdir,
            default_mode=current.default_mode,
        )
        self._persist_preferences()
        self._clear_thread_only(chat_key)
        if notice:
            return f"{notice}\n当前设置：{self.describe_preferences(chat_key)}"
        return f"当前设置：{self.describe_preferences(chat_key)}"

    async def update_reasoning_effort(self, chat_key: str, effort: str) -> str:
        self._ensure_not_running(chat_key)
        if effort not in SUPPORTED_EFFORT_COMMANDS:
            raise ValueError("仅支持 high 或 xhigh。")

        current = self.get_preferences(chat_key)
        model = self.load_models().get(current.model)
        if model is None:
            raise ValueError("当前模型不在本地缓存中。")
        if effort not in model.supported_reasoning_levels:
            supported = ", ".join(model.supported_reasoning_levels)
            raise ValueError(f"当前模型仅支持：{supported}")

        self.preference_overrides[chat_key] = ChatPreferences(
            model=current.model,
            reasoning_effort=effort,
            permission_mode=current.permission_mode,
            workdir=current.workdir,
            default_mode=current.default_mode,
        )
        self._persist_preferences()
        self._clear_thread_only(chat_key)
        return f"当前设置：{self.describe_preferences(chat_key)}"

    async def update_permission_mode(self, chat_key: str, permission_mode: str) -> str:
        self._ensure_not_running(chat_key)
        if permission_mode not in SUPPORTED_PERMISSION_MODES:
            raise ValueError("仅支持 safe 或 danger。")

        current = self.get_preferences(chat_key)
        self.preference_overrides[chat_key] = ChatPreferences(
            model=current.model,
            reasoning_effort=current.reasoning_effort,
            permission_mode=permission_mode,
            workdir=current.workdir,
            default_mode=current.default_mode,
        )
        self._persist_preferences()
        self._clear_thread_only(chat_key)
        return f"当前设置：{self.describe_preferences(chat_key)}"

    async def update_workdir(self, chat_key: str, workdir: str) -> str:
        self._ensure_not_running(chat_key)
        resolved = self._resolve_directory_path(chat_key, workdir)
        current = self.get_preferences(chat_key)
        self.preference_overrides[chat_key] = ChatPreferences(
            model=current.model,
            reasoning_effort=current.reasoning_effort,
            permission_mode=current.permission_mode,
            workdir=resolved,
            default_mode=current.default_mode,
        )
        self._persist_preferences()
        self._clear_thread_only(chat_key)
        return self.describe_workdir(chat_key)

    async def update_default_mode(self, chat_key: str, mode: str) -> str:
        self._ensure_not_running(chat_key)
        if mode not in {"resume", "exec"}:
            raise ValueError("仅支持 resume 或 exec。")

        current = self.get_preferences(chat_key)
        self.preference_overrides[chat_key] = ChatPreferences(
            model=current.model,
            reasoning_effort=current.reasoning_effort,
            permission_mode=current.permission_mode,
            workdir=current.workdir,
            default_mode=mode,
        )
        self._persist_preferences()
        session = self.get_session(chat_key)
        session.active_mode = mode
        self._sync_legacy_thread_id(session)
        return f"当前默认模式：{mode}"

    def get_supported_efforts(self, model_slug: str) -> list[str]:
        model = self.load_models().get(model_slug)
        if model is None:
            raise ValueError("未找到指定模型。")
        return model.supported_reasoning_levels

    async def run_prompt(
        self,
        chat_key: str,
        prompt: str,
        *,
        mode_override: str | None = None,
        on_progress: ProgressCallback | None = None,
        on_stream_text: StreamTextCallback | None = None,
    ) -> RunResult:
        session = self.activate_chat(chat_key)
        if session.running:
            raise RuntimeError("Codex is already running for this chat")
        if not self.which_resolver(self.settings.binary):
            raise FileNotFoundError(self.settings.binary)

        clean_prompt = prompt.strip()
        if not clean_prompt:
            return RunResult(exit_code=0, notice="输入为空，未发送到 Codex。")

        preferences = self.get_preferences(chat_key)
        mode = mode_override or session.active_mode or preferences.default_mode
        if mode == "resume" and self.native_client is not None:
            result = await self._run_native_prompt(
                session,
                clean_prompt,
                preferences=preferences,
                on_progress=on_progress,
                on_stream_text=on_stream_text,
            )
            return result

        result = await self._run_exec_prompt(
            session,
            clean_prompt,
            previous_thread=self._current_exec_thread_id(session),
            preferences=preferences,
            on_progress=on_progress,
            on_stream_text=on_stream_text,
        )
        return result

    async def _run_exec_prompt(
        self,
        session: ChatSession,
        prompt: str,
        *,
        previous_thread: str | None,
        preferences: ChatPreferences,
        on_progress: ProgressCallback | None,
        on_stream_text: StreamTextCallback | None,
    ) -> RunResult:
        result = await self._run_exec_once(
            session,
            prompt,
            preferences=preferences,
            on_progress=on_progress,
            on_stream_text=on_stream_text,
        )
        if result.cancelled:
            return result

        if (
            previous_thread
            and result.exit_code != 0
            and not result.final_text
            and not session.strict_resume
        ):
            self._set_exec_thread_id(session, None)
            self._sync_legacy_thread_id(session)
            if on_progress is not None:
                await on_progress("原会话恢复失败，正在新开会话…")
            result = await self._run_exec_once(
                session,
                prompt,
                preferences=preferences,
                on_progress=on_progress,
                on_stream_text=on_stream_text,
            )
            result.notice = "原会话未成功恢复，已新开会话。"
            return result

        if previous_thread and result.thread_id and result.thread_id != previous_thread:
            result.notice = "原会话未成功恢复，已自动切换到新会话。"
        return result

    async def _run_exec_once(
        self,
        session: ChatSession,
        prompt: str,
        *,
        preferences: ChatPreferences,
        on_progress: ProgressCallback | None,
        on_stream_text: StreamTextCallback | None,
    ) -> RunResult:
        session.running = True
        session.cancel_requested = False
        session.last_agent_message = ""
        session.last_stream_text = ""
        session.last_stream_rendered_text = ""
        session.stream_message_truncated = False
        session.progress_lines.clear()
        session.diagnostics.clear()

        exec_thread_id = self._current_exec_thread_id(session)
        starting_new_thread = exec_thread_id is None
        argv = build_exec_argv(
            self.settings.binary,
            preferences.workdir,
            prompt,
            model=preferences.model,
            reasoning_effort=preferences.reasoning_effort,
            permission_mode=preferences.permission_mode,
            thread_id=exec_thread_id,
        )
        process = await self.launcher(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=preferences.workdir,
            limit=self.settings.stream_read_limit,
        )
        session.process = process

        if on_progress is not None:
            await on_progress(
                render_progress_text(
                    session,
                    header=(
                        format_preferences_summary(preferences)
                        if starting_new_thread
                        else None
                    ),
                )
            )

        stdout = getattr(process, "stdout", None)
        try:
            while stdout is not None:
                raw_line = await stdout.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                event = parse_event_line(line)
                if event is None:
                    _append_diagnostic(session, line, self.settings.diagnostic_history)
                    continue
                changed, stream_text = _apply_event(
                    session,
                    event,
                    progress_history=self.settings.progress_history,
                )
                if event.get("type") == "thread.started":
                    thread_id = event.get("thread_id")
                    if isinstance(thread_id, str) and thread_id:
                        self._set_exec_thread_id(session, thread_id)
                        self._sync_legacy_thread_id(session)
                if changed and on_progress is not None:
                    await on_progress(render_progress_text(session))
                if stream_text is not None and on_stream_text is not None:
                    await on_stream_text(stream_text)

            exit_code = await process.wait()
            cancelled = session.cancel_requested
        except Exception:
            await terminate_process(process, self.settings.kill_timeout)
            raise
        finally:
            session.running = False
            session.process = None
            session.cancel_requested = False

        return RunResult(
            exit_code=exit_code,
            final_text=session.last_agent_message,
            thread_id=self._current_exec_thread_id(session),
            diagnostics=list(session.diagnostics),
            cancelled=cancelled,
        )

    async def _run_native_prompt(
        self,
        session: ChatSession,
        prompt: str,
        *,
        preferences: ChatPreferences,
        on_progress: ProgressCallback | None,
        on_stream_text: StreamTextCallback | None,
    ) -> RunResult:
        if self.native_client is None:
            raise RuntimeError("Native Codex client is not configured.")

        native_runner = self._spawn_native_client()
        if native_runner is None:
            raise RuntimeError("Native Codex client is not configured.")

        session.running = True
        session.cancel_requested = False
        session.native_runner = native_runner
        session.runner_task = asyncio.current_task()
        session.last_agent_message = ""
        session.last_stream_text = ""
        session.last_stream_rendered_text = ""
        session.stream_message_truncated = False
        session.progress_lines.clear()
        session.diagnostics.clear()

        starting_new_thread = session.native_thread_id is None
        if on_progress is not None:
            await on_progress(
                render_progress_text(
                    session,
                    header=(
                        format_preferences_summary(preferences)
                        if starting_new_thread
                        else None
                    ),
                )
            )

        async def forward_progress(line: str) -> None:
            _append_progress_line(session, line, self.settings.progress_history)
            if on_progress is not None:
                await on_progress(render_progress_text(session))

        async def forward_stream_text(text: str) -> None:
            stripped = text.strip()
            if not stripped:
                return
            session.last_agent_message = stripped
            session.last_stream_text = stripped
            if on_stream_text is not None:
                await on_stream_text(stripped)

        try:
            if session.native_thread_id is None:
                thread = await native_runner.start_thread(
                    workdir=preferences.workdir,
                    model=preferences.model,
                    reasoning_effort=preferences.reasoning_effort,
                    permission_mode=preferences.permission_mode,
                )
            else:
                thread = await native_runner.resume_thread(
                    session.native_thread_id,
                    workdir=preferences.workdir,
                    model=preferences.model,
                    reasoning_effort=preferences.reasoning_effort,
                    permission_mode=preferences.permission_mode,
                )
            self._set_native_thread_id(session, thread.thread_id)
            native_result = await native_runner.run_turn(
                thread.thread_id,
                prompt,
                cwd=preferences.workdir,
                model=preferences.model,
                reasoning_effort=preferences.reasoning_effort,
                on_progress=forward_progress,
                on_stream_text=forward_stream_text,
            )
            final_thread_id = native_result.thread_id or thread.thread_id
            self._set_native_thread_id(session, final_thread_id)
            if native_result.final_text.strip():
                session.last_agent_message = native_result.final_text.strip()
                session.last_stream_text = native_result.final_text.strip()
            return RunResult(
                exit_code=native_result.exit_code,
                final_text=session.last_agent_message,
                thread_id=final_thread_id,
                diagnostics=list(native_result.diagnostics),
                cancelled=session.cancel_requested,
            )
        except Exception as exc:
            if session.cancel_requested:
                return RunResult(
                    exit_code=1,
                    thread_id=session.native_thread_id,
                    diagnostics=list(session.diagnostics),
                    cancelled=True,
                )
            _append_diagnostic(session, str(exc), self.settings.diagnostic_history)
            return RunResult(
                exit_code=1,
                thread_id=session.native_thread_id,
                diagnostics=list(session.diagnostics),
            )
        finally:
            await self._close_native_runner(session.native_runner)
            session.running = False
            session.process = None
            session.native_runner = None
            session.runner_task = None
            session.cancel_requested = False
