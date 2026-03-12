from __future__ import annotations

import json
from pathlib import Path

import pytest

from nonebot_plugin_codex.native_client import NativeThreadSummary
from nonebot_plugin_codex.service import (
    CodexBridgeService,
    CodexBridgeSettings,
    HistoricalSessionSummary,
    build_exec_argv,
)


class DummyNativeClient:
    def __init__(self, threads: list[NativeThreadSummary] | None = None) -> None:
        self._threads = threads or []

    def clone(self) -> DummyNativeClient:
        return DummyNativeClient(list(self._threads))

    async def close(self, timeout: float = 5.0) -> None:
        return None

    async def list_threads(self) -> list[NativeThreadSummary]:
        return list(self._threads)


def make_service(
    tmp_path: Path,
    model_cache_file: Path,
    *,
    threads: list[NativeThreadSummary] | None = None,
) -> CodexBridgeService:
    codex_config = tmp_path / "config.toml"
    codex_config.write_text('model = "gpt-5"\nmodel_reasoning_effort = "xhigh"\n')
    return CodexBridgeService(
        CodexBridgeSettings(
            binary="codex",
            workdir=str(tmp_path),
            models_cache_path=model_cache_file,
            codex_config_path=codex_config,
            preferences_path=tmp_path / "data" / "codex_bridge" / "preferences.json",
            session_index_path=tmp_path / ".codex" / "session_index.jsonl",
            sessions_dir=tmp_path / ".codex" / "sessions",
            archived_sessions_dir=tmp_path / ".codex" / "archived_sessions",
        ),
        native_client=DummyNativeClient(threads),
        which_resolver=lambda _: "/usr/bin/codex",
    )


def make_service_without_model_cache(tmp_path: Path) -> CodexBridgeService:
    codex_config = tmp_path / "config.toml"
    codex_config.write_text('model = "gpt-5"\nmodel_reasoning_effort = "xhigh"\n')
    return CodexBridgeService(
        CodexBridgeSettings(
            binary="codex",
            workdir=str(tmp_path),
            models_cache_path=tmp_path / "missing-models.json",
            codex_config_path=codex_config,
            preferences_path=tmp_path / "data" / "codex_bridge" / "preferences.json",
            session_index_path=tmp_path / ".codex" / "session_index.jsonl",
            sessions_dir=tmp_path / ".codex" / "sessions",
            archived_sessions_dir=tmp_path / ".codex" / "archived_sessions",
        ),
        which_resolver=lambda _: "/usr/bin/codex",
    )


def test_build_exec_argv_for_safe_and_resume_mode() -> None:
    argv = build_exec_argv(
        "codex",
        "/tmp/work",
        "hello",
        model="gpt-5",
        reasoning_effort="xhigh",
        permission_mode="safe",
        thread_id="thread-1",
    )

    assert argv[:3] == ["codex", "exec", "resume"]
    assert "--full-auto" in argv
    assert "--sandbox" not in argv
    assert argv[-2:] == ["thread-1", "hello"]


def test_default_preferences_use_configured_workdir(
    tmp_path: Path, model_cache_file: Path
) -> None:
    service = make_service(tmp_path, model_cache_file)

    preferences = service.get_preferences("private_1")

    assert preferences.workdir == str(tmp_path.resolve())


def test_default_preferences_use_codex_config_when_model_cache_is_missing(
    tmp_path: Path,
) -> None:
    service = make_service_without_model_cache(tmp_path)

    preferences = service.get_preferences("private_1")

    assert preferences.model == "gpt-5"
    assert preferences.reasoning_effort == "xhigh"
    assert preferences.workdir == str(tmp_path.resolve())


def test_directory_browser_home_uses_configured_workdir(
    tmp_path: Path, model_cache_file: Path
) -> None:
    service = make_service(tmp_path, model_cache_file)
    outside_dir = tmp_path.parent

    browser = service._replace_browser_state(  # noqa: SLF001
        "private_1",
        str(outside_dir),
        page=0,
    )

    browser = service.navigate_directory_browser(
        "private_1",
        browser.token,
        browser.version,
        "home",
    )

    assert browser.current_path == str(tmp_path.resolve())


@pytest.mark.asyncio
async def test_update_default_mode_persists_preference_and_switches_active_mode(
    tmp_path: Path, model_cache_file: Path
) -> None:
    service = make_service(tmp_path, model_cache_file)
    session = service.activate_chat("private_1")
    session.thread_id = "legacy"
    session.exec_thread_id = "exec-1"
    session.native_thread_id = "native-1"

    notice = await service.update_default_mode("private_1", "exec")

    assert notice == "当前默认模式：exec"
    assert session.thread_id == "exec-1"
    assert session.native_thread_id == "native-1"
    stored = json.loads(service.settings.preferences_path.read_text(encoding="utf-8"))
    assert stored["private_1"]["default_mode"] == "exec"


@pytest.mark.asyncio
async def test_update_workdir_clears_bound_threads(
    tmp_path: Path, model_cache_file: Path
) -> None:
    service = make_service(
        tmp_path,
        model_cache_file,
        threads=[
            NativeThreadSummary(
                thread_id="native-1",
                thread_name="Native Session",
                updated_at="2025-03-01T00:00:00Z",
                cwd=str(tmp_path / "missing"),
                source_kind="cli",
            )
        ],
    )
    target_dir = tmp_path / "workspace"
    target_dir.mkdir()
    session = service.activate_chat("private_1")
    session.thread_id = "legacy"
    session.exec_thread_id = "exec-1"
    session.native_thread_id = "native-1"

    notice = await service.update_workdir("private_1", str(target_dir))

    assert str(target_dir.resolve()) in notice
    assert session.thread_id is None
    assert session.exec_thread_id is None
    assert session.native_thread_id is None


@pytest.mark.asyncio
async def test_apply_history_session_uses_existing_cwd_when_original_missing(
    tmp_path: Path, model_cache_file: Path
) -> None:
    service = make_service(
        tmp_path,
        model_cache_file,
        threads=[
            NativeThreadSummary(
                thread_id="native-1",
                thread_name="Native Session",
                updated_at="2025-03-01T00:00:00Z",
                cwd=str(tmp_path / "missing"),
                source_kind="cli",
            )
        ],
    )
    current_dir = tmp_path / "current"
    current_dir.mkdir()
    await service.update_workdir("private_1", str(current_dir))
    await service.refresh_history_sessions()
    browser = service._replace_history_browser_state(  # noqa: SLF001
        "private_1",
        page=0,
        scope="resume",
        selected_session_id="native-1",
    )
    browser.entries = [
        HistoricalSessionSummary(
            session_id="native-1",
            thread_name="Native Session",
            updated_at="2025-03-01T00:00:00Z",
            kind="native",
            cwd=str(tmp_path / "missing"),
        )
    ]
    notice = await service.apply_history_session(
        "private_1", browser.token, browser.version
    )

    assert "原工作目录不存在，已保留当前工作目录。" in notice
    assert f"当前工作目录：{current_dir.resolve()}" in notice


@pytest.mark.parametrize(
    ("kind", "expected_heading"),
    [
        ("mode", "模式设置"),
        ("model", "模型设置"),
        ("effort", "推理强度设置"),
        ("permission", "权限模式设置"),
    ],
)
def test_render_setting_panels_show_expected_headings(
    tmp_path: Path,
    model_cache_file: Path,
    kind: str,
    expected_heading: str,
) -> None:
    service = make_service(tmp_path, model_cache_file)
    service.activate_chat("private_1")

    service.open_setting_panel("private_1", kind)
    text, markup = service.render_setting_panel("private_1")

    assert expected_heading in text
    assert markup.inline_keyboard


@pytest.mark.asyncio
async def test_apply_permission_setting_panel_updates_preference(
    tmp_path: Path, model_cache_file: Path
) -> None:
    service = make_service(tmp_path, model_cache_file)
    panel = service.open_setting_panel("private_1", "permission")

    notice = await service.apply_setting_panel_selection(
        "private_1",
        panel.token,
        panel.version,
        "danger",
    )

    assert "danger" in notice
    assert service.get_preferences("private_1").permission_mode == "danger"
