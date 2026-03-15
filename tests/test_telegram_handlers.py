from __future__ import annotations

from pathlib import Path
from typing import Any
from types import SimpleNamespace
from dataclasses import field, dataclass

import pytest

from nonebot.adapters.telegram.exception import ActionFailed
from nonebot_plugin_codex.telegram import TelegramHandlers
from nonebot_plugin_codex.service import (
    ChatSession,
    CodexBridgeService,
    CodexBridgeSettings,
    encode_browser_callback,
    encode_history_callback,
    encode_setting_callback,
)


@dataclass
class FakeMessage:
    text: str = ""

    def extract_plain_text(self) -> str:
        return self.text


@dataclass
class FakeChat:
    type: str = "private"
    id: int = 1


@dataclass
class FakeEvent:
    text: str = ""
    chat: FakeChat = field(default_factory=FakeChat)

    def get_plaintext(self) -> str:
        return self.text


@dataclass
class FakeCallbackEvent:
    data: str
    id: str = "callback-1"
    chat: FakeChat = field(default_factory=FakeChat)
    message: Any = field(default_factory=lambda: SimpleNamespace(message_id=1))


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.edited: list[dict[str, Any]] = []
        self.answered: list[dict[str, Any]] = []

    async def send(self, event: FakeEvent, text: str, **kwargs: Any) -> SimpleNamespace:
        payload = {"chat_id": event.chat.id, "text": text, **kwargs}
        self.sent.append(payload)
        return SimpleNamespace(message_id=len(self.sent))

    async def send_message(
        self, *, chat_id: int, text: str, **kwargs: Any
    ) -> SimpleNamespace:
        payload = {"chat_id": chat_id, "text": text, **kwargs}
        self.sent.append(payload)
        return SimpleNamespace(message_id=len(self.sent))

    async def edit_message_text(
        self, *, chat_id: int, message_id: int, text: str, **kwargs: Any
    ) -> None:
        self.edited.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                **kwargs,
            }
        )

    async def answer_callback_query(self, callback_id: str, **kwargs: Any) -> None:
        self.answered.append({"id": callback_id, **kwargs})


class HtmlFailingBot(FakeBot):
    async def send(self, event: FakeEvent, text: str, **kwargs: Any) -> SimpleNamespace:
        payload = {"chat_id": event.chat.id, "text": text, **kwargs}
        self.sent.append(payload)
        if kwargs.get("parse_mode") == "HTML":
            raise ActionFailed(
                "Bad Request: can't parse entities: Unsupported start tag"
            )
        return SimpleNamespace(message_id=len(self.sent))

    async def send_message(
        self, *, chat_id: int, text: str, **kwargs: Any
    ) -> SimpleNamespace:
        payload = {"chat_id": chat_id, "text": text, **kwargs}
        self.sent.append(payload)
        if kwargs.get("parse_mode") == "HTML":
            raise ActionFailed(
                "Bad Request: can't parse entities: Unsupported start tag"
            )
        return SimpleNamespace(message_id=len(self.sent))

    async def edit_message_text(
        self, *, chat_id: int, message_id: int, text: str, **kwargs: Any
    ) -> None:
        self.edited.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                **kwargs,
            }
        )
        if kwargs.get("parse_mode") == "HTML":
            raise ActionFailed(
                "Bad Request: can't parse entities: Unsupported start tag"
            )


class MessageNotModifiedBot(FakeBot):
    async def edit_message_text(
        self, *, chat_id: int, message_id: int, text: str, **kwargs: Any
    ) -> None:
        self.edited.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                **kwargs,
            }
        )
        raise ActionFailed("Bad Request: message is not modified")


class FakeService:
    def __init__(self) -> None:
        self.session = ChatSession()
        self.settings = SimpleNamespace(chunk_size=3500, workdir="/tmp/configured-home")
        self.browser_text = "目录浏览"
        self.history_text = "Codex 历史会话"
        self.setting_text = "模式设置"
        self.onboarding_text = "开始使用 Codex"
        self.onboarding_markup = SimpleNamespace(name="onboarding")
        self.default_mode = "resume"
        self.execute_calls: list[tuple[str, str | None]] = []
        self.browser_token = "token"
        self.browser_version = 1
        self.browser_applied = False
        self.history_token = "history"
        self.history_version = 1
        self.history_applied = False
        self.setting_token = "setting"
        self.setting_version = 1
        self.setting_kind = "mode"
        self.setting_updates: list[str] = []
        self.updated_workdirs: list[str] = []
        self.onboarding_token = "onboarding"
        self.onboarding_version = 1
        self.onboarding_closed = False

    def get_session(self, chat_key: str) -> ChatSession:
        return self.session

    def activate_chat(self, chat_key: str) -> ChatSession:
        self.session.active = True
        return self.session

    def get_preferences(self, chat_key: str) -> SimpleNamespace:
        return SimpleNamespace(default_mode=self.default_mode)

    def describe_preferences(self, chat_key: str) -> str:
        return "模型: gpt-5 | 推理: xhigh | 权限: safe"

    def configured_workdir(self) -> str:
        return self.settings.workdir

    async def run_prompt(
        self,
        chat_key: str,
        prompt: str,
        *,
        mode_override: str | None = None,
        on_progress=None,
        on_stream_text=None,
    ):  # noqa: ANN001,E501
        self.execute_calls.append((prompt, mode_override))
        return SimpleNamespace(
            cancelled=False,
            exit_code=0,
            final_text="完成",
            notice="",
            diagnostics=[],
        )

    async def reset_chat(self, chat_key: str, *, keep_active: bool) -> ChatSession:
        self.session = ChatSession(active=keep_active)
        return self.session

    def open_directory_browser(self, chat_key: str) -> SimpleNamespace:
        return SimpleNamespace(token="token")

    def render_directory_browser(self, chat_key: str) -> tuple[str, None]:
        return self.browser_text, None

    def remember_browser_message(
        self, chat_key: str, token: str, message_id: int | None
    ) -> None:
        return None

    async def update_workdir(self, chat_key: str, target: str) -> str:
        self.updated_workdirs.append(target)
        return f"当前工作目录：{target}"

    def get_browser(self, chat_key: str) -> SimpleNamespace:
        return SimpleNamespace(
            token=self.browser_token, version=self.browser_version, message_id=1
        )

    async def apply_browser_directory(
        self, chat_key: str, token: str, version: int
    ) -> str:
        self.browser_applied = True
        return "当前工作目录：/tmp/work"

    def navigate_directory_browser(
        self,
        chat_key: str,
        token: str,
        version: int,
        action: str,
        index: int | None = None,
    ) -> None:
        return None

    def close_directory_browser(self, chat_key: str, token: str, version: int) -> None:
        return None

    async def refresh_history_sessions(self) -> list[Any]:
        return []

    def open_history_browser(self, chat_key: str) -> SimpleNamespace:
        return SimpleNamespace(token="history")

    def render_history_browser(self, chat_key: str) -> tuple[str, None]:
        return self.history_text, None

    def remember_history_browser_message(
        self, chat_key: str, token: str, message_id: int | None
    ) -> None:
        return None

    def get_history_browser(self, chat_key: str) -> SimpleNamespace:
        return SimpleNamespace(
            token=self.history_token,
            version=self.history_version,
            message_id=1,
        )

    async def apply_history_session(
        self, chat_key: str, token: str, version: int
    ) -> str:
        self.history_applied = True
        return "已切换到历史会话（native）：Test Session"

    def navigate_history_browser(
        self,
        chat_key: str,
        token: str,
        version: int,
        action: str,
        index: int | None = None,
    ) -> None:
        return None

    def close_history_browser(self, chat_key: str, token: str, version: int) -> None:
        return None

    def open_setting_panel(self, chat_key: str, kind: str) -> SimpleNamespace:
        self.setting_kind = kind
        return SimpleNamespace(token=self.setting_token)

    def render_setting_panel(self, chat_key: str) -> tuple[str, None]:
        texts = {
            "mode": "模式设置",
            "model": "模型设置",
            "effort": "推理强度设置",
            "permission": "权限模式设置",
        }
        return texts[self.setting_kind], None

    def remember_setting_panel_message(
        self, chat_key: str, token: str, message_id: int | None
    ) -> None:
        return None

    def get_setting_panel(self, chat_key: str) -> SimpleNamespace:
        return SimpleNamespace(
            token=self.setting_token,
            version=self.setting_version,
            kind=self.setting_kind,
            message_id=1,
        )

    def navigate_setting_panel(
        self,
        chat_key: str,
        token: str,
        version: int,
        action: str,
    ) -> None:
        return None

    async def apply_setting_panel_selection(
        self,
        chat_key: str,
        token: str,
        version: int,
        value: str,
    ) -> str:
        self.setting_updates.append(value)
        return f"当前设置：{value}"

    def close_setting_panel(self, chat_key: str, token: str, version: int) -> None:
        return None

    async def update_default_mode(self, chat_key: str, mode: str) -> str:
        self.setting_updates.append(mode)
        return f"当前默认模式：{mode}"

    def open_onboarding_panel(self, chat_key: str) -> SimpleNamespace:
        return SimpleNamespace(token=self.onboarding_token)

    def render_onboarding_panel(self, chat_key: str) -> tuple[str, Any]:
        return self.onboarding_text, self.onboarding_markup

    def remember_onboarding_panel_message(
        self, chat_key: str, token: str, message_id: int | None
    ) -> None:
        return None

    def get_onboarding_panel(
        self,
        chat_key: str,
        token: str | None = None,
        version: int | None = None,
    ) -> SimpleNamespace:
        if token is not None and token != self.onboarding_token:
            raise ValueError("引导面板已失效，请重新执行 /codex")
        if version is not None and version != self.onboarding_version:
            raise ValueError("引导面板已失效，请重新执行 /codex")
        return SimpleNamespace(
            token=self.onboarding_token,
            version=self.onboarding_version,
            message_id=1,
        )

    def close_onboarding_panel(self, chat_key: str, token: str, version: int) -> None:
        self.onboarding_closed = True


def make_real_service(
    tmp_path: Path,
    model_cache_file: Path,
    *,
    workdir: str | None = None,
) -> CodexBridgeService:
    codex_config = tmp_path / "config.toml"
    codex_config.write_text('model = "gpt-5"\nmodel_reasoning_effort = "xhigh"\n')
    return CodexBridgeService(
        CodexBridgeSettings(
            binary="codex",
            workdir=workdir or str(tmp_path),
            models_cache_path=model_cache_file,
            codex_config_path=codex_config,
            preferences_path=(
                tmp_path / "data" / "nonebot_plugin_codex" / "preferences.json"
            ),
            session_index_path=tmp_path / ".codex" / "session_index.jsonl",
            sessions_dir=tmp_path / ".codex" / "sessions",
            archived_sessions_dir=tmp_path / ".codex" / "archived_sessions",
        ),
        which_resolver=lambda _: "/usr/bin/codex",
    )


def make_real_service_without_model_cache(tmp_path: Path) -> CodexBridgeService:
    codex_config = tmp_path / "config.toml"
    codex_config.write_text('model = "gpt-5"\nmodel_reasoning_effort = "xhigh"\n')
    return CodexBridgeService(
        CodexBridgeSettings(
            binary="codex",
            workdir=str(tmp_path),
            models_cache_path=tmp_path / "missing-models.json",
            codex_config_path=codex_config,
            preferences_path=(
                tmp_path / "data" / "nonebot_plugin_codex" / "preferences.json"
            ),
            session_index_path=tmp_path / ".codex" / "session_index.jsonl",
            sessions_dir=tmp_path / ".codex" / "sessions",
            archived_sessions_dir=tmp_path / ".codex" / "archived_sessions",
        ),
        which_resolver=lambda _: "/usr/bin/codex",
    )


@pytest.mark.asyncio
async def test_handle_codex_without_prompt_sends_onboarding_panel() -> None:
    service = FakeService()
    handlers = TelegramHandlers(service)
    bot = FakeBot()
    event = FakeEvent("")

    await handlers.handle_codex(bot, event, FakeMessage(""))

    assert bot.sent[0]["text"] == "开始使用 Codex"
    assert bot.sent[0]["reply_markup"] is service.onboarding_markup


@pytest.mark.asyncio
@pytest.mark.parametrize("handler_name", ["handle_help", "handle_start"])
async def test_help_and_start_open_onboarding_panel(handler_name: str) -> None:
    service = FakeService()
    handlers = TelegramHandlers(service)
    bot = FakeBot()

    await getattr(handlers, handler_name)(bot, FakeEvent(""))

    assert bot.sent[0]["text"] == "开始使用 Codex"
    assert bot.sent[0]["reply_markup"] is service.onboarding_markup


@pytest.mark.asyncio
async def test_handle_exec_requires_prompt() -> None:
    handlers = TelegramHandlers(FakeService())
    bot = FakeBot()

    await handlers.handle_exec(bot, FakeEvent(""), FakeMessage(""))

    assert bot.sent[0]["text"] == "请在 /exec 后输入要执行的内容。"


@pytest.mark.asyncio
async def test_send_event_message_uses_html_parse_mode_and_renders_text() -> None:
    handlers = TelegramHandlers(FakeService())
    bot = FakeBot()
    event = FakeEvent("")

    await handlers.send_event_message(bot, event, "**bold**")

    assert bot.sent[0]["parse_mode"] == "HTML"
    assert bot.sent[0]["text"] == "<b>bold</b>"


@pytest.mark.asyncio
async def test_edit_message_uses_html_parse_mode_and_renders_text() -> None:
    handlers = TelegramHandlers(FakeService())
    bot = FakeBot()

    await handlers.edit_message(bot, chat_id=1, message_id=2, text="**bold**")

    assert bot.edited[0]["parse_mode"] == "HTML"
    assert bot.edited[0]["text"] == "<b>bold</b>"


@pytest.mark.asyncio
async def test_send_event_message_falls_back_to_plain_text_when_html_fails() -> None:
    handlers = TelegramHandlers(FakeService())
    bot = HtmlFailingBot()
    event = FakeEvent("")

    await handlers.send_event_message(bot, event, "**bold**")

    assert bot.sent[0]["parse_mode"] == "HTML"
    assert bot.sent[0]["text"] == "<b>bold</b>"
    assert "parse_mode" not in bot.sent[1]
    assert bot.sent[1]["text"] == "**bold**"


@pytest.mark.asyncio
async def test_send_chat_message_falls_back_to_plain_text_when_html_fails() -> None:
    handlers = TelegramHandlers(FakeService())
    bot = HtmlFailingBot()

    await handlers.send_chat_message(bot, 1, "**bold**")

    assert bot.sent[0]["parse_mode"] == "HTML"
    assert bot.sent[0]["text"] == "<b>bold</b>"
    assert "parse_mode" not in bot.sent[1]
    assert bot.sent[1]["text"] == "**bold**"


@pytest.mark.asyncio
async def test_edit_message_falls_back_to_plain_text_when_html_fails() -> None:
    handlers = TelegramHandlers(FakeService())
    bot = HtmlFailingBot()

    await handlers.edit_message(bot, chat_id=1, message_id=2, text="**bold**")

    assert bot.edited[0]["parse_mode"] == "HTML"
    assert bot.edited[0]["text"] == "<b>bold</b>"
    assert "parse_mode" not in bot.edited[1]
    assert bot.edited[1]["text"] == "**bold**"


@pytest.mark.asyncio
async def test_handle_cd_without_target_opens_browser() -> None:
    handlers = TelegramHandlers(FakeService())
    bot = FakeBot()

    await handlers.handle_cd(bot, FakeEvent(""), FakeMessage(""))

    assert bot.sent[0]["text"] == "目录浏览"


@pytest.mark.asyncio
async def test_handle_sessions_opens_history_browser() -> None:
    handlers = TelegramHandlers(FakeService())
    bot = FakeBot()

    await handlers.handle_sessions(bot, FakeEvent(""))

    assert bot.sent[0]["text"] == "Codex 历史会话"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_text"),
    [
        ("cop:onboarding:1:browse", "目录浏览"),
        ("cop:onboarding:1:history", "Codex 历史会话"),
        ("cop:onboarding:1:settings", "模式设置"),
    ],
)
async def test_handle_onboarding_callback_opens_existing_panels(
    payload: str,
    expected_text: str,
) -> None:
    service = FakeService()
    handlers = TelegramHandlers(service)
    bot = FakeBot()

    await handlers.handle_onboarding_callback(bot, FakeCallbackEvent(payload))

    assert bot.sent[0]["text"] == expected_text


@pytest.mark.asyncio
async def test_handle_onboarding_callback_new_resets_chat() -> None:
    service = FakeService()
    service.session.thread_id = "thread-1"
    handlers = TelegramHandlers(service)
    bot = FakeBot()

    await handlers.handle_onboarding_callback(
        bot, FakeCallbackEvent("cop:onboarding:1:new")
    )

    assert "已清空当前 Codex 会话" in bot.sent[0]["text"]
    assert bot.answered[0]["text"] == "已新开会话。"


@pytest.mark.asyncio
async def test_handle_onboarding_callback_close_closes_panel() -> None:
    service = FakeService()
    handlers = TelegramHandlers(service)
    bot = FakeBot()

    await handlers.handle_onboarding_callback(
        bot, FakeCallbackEvent("cop:onboarding:1:close")
    )

    assert service.onboarding_closed is True
    assert bot.edited[0]["text"] == "使用引导已关闭。"
    assert bot.answered[0]["text"] == "已关闭。"


@pytest.mark.asyncio
async def test_handle_onboarding_callback_rejects_stale_payload() -> None:
    handlers = TelegramHandlers(FakeService())
    bot = FakeBot()

    await handlers.handle_onboarding_callback(
        bot, FakeCallbackEvent("cop:stale:1:browse")
    )

    assert bot.answered[0]["text"] == "引导面板已失效，请重新执行 /codex"
    assert bot.answered[0]["show_alert"] is True


@pytest.mark.asyncio
async def test_handle_follow_up_rejects_when_running() -> None:
    service = FakeService()
    service.session.active = True
    service.session.running = True
    handlers = TelegramHandlers(service)
    bot = FakeBot()

    await handlers.handle_follow_up(bot, FakeEvent("继续"))

    assert bot.sent[0]["text"] == "Codex 正在运行中，请等待完成或使用 /stop。"


@pytest.mark.asyncio
async def test_handle_browser_callback_apply_updates_directory() -> None:
    service = FakeService()
    handlers = TelegramHandlers(service)
    bot = FakeBot()
    event = FakeCallbackEvent(
        encode_browser_callback(service.browser_token, service.browser_version, "apply")
    )

    await handlers.handle_browser_callback(bot, event)

    assert service.browser_applied is True
    assert bot.answered[0]["text"] == "工作目录已更新。"


@pytest.mark.asyncio
async def test_handle_history_callback_apply_keeps_notice_without_resending_menu(
) -> None:
    service = FakeService()
    handlers = TelegramHandlers(service)
    bot = MessageNotModifiedBot()
    event = FakeCallbackEvent(
        encode_history_callback(service.history_token, service.history_version, "apply")
    )

    await handlers.handle_history_callback(bot, event)

    assert service.history_applied is True
    assert bot.answered[0]["text"] == "已切换到历史会话。"
    assert [payload["text"] for payload in bot.sent] == [
        "已切换到历史会话（native）：Test Session"
    ]


@pytest.mark.asyncio
async def test_handle_home_uses_configured_workdir() -> None:
    service = FakeService()
    handlers = TelegramHandlers(service)
    bot = FakeBot()

    await handlers.handle_home(bot, FakeEvent(""))

    assert service.updated_workdirs == [service.settings.workdir]


@pytest.mark.asyncio
async def test_handle_home_resolves_relative_configured_workdir(
    tmp_path: Path,
    model_cache_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    configured_home = tmp_path / "workspace" / "default"
    configured_home.mkdir(parents=True)
    moved_dir = tmp_path / "workspace" / "other"
    moved_dir.mkdir(parents=True)
    service = make_real_service(
        tmp_path,
        model_cache_file,
        workdir="workspace/default",
    )
    handlers = TelegramHandlers(service)
    bot = FakeBot()
    await service.update_workdir("private_1", str(moved_dir))

    await handlers.handle_home(bot, FakeEvent(""))

    assert bot.sent[0]["text"].startswith(f"当前工作目录：{configured_home.resolve()}")
    assert service.get_preferences("private_1").workdir == str(
        configured_home.resolve()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "kind", "expected_text"),
    [
        ("handle_mode", "mode", "模式设置"),
        ("handle_model", "model", "模型设置"),
        ("handle_effort", "effort", "推理强度设置"),
        ("handle_permission", "permission", "权限模式设置"),
    ],
)
async def test_selection_commands_without_argument_open_setting_panels(
    handler_name: str,
    kind: str,
    expected_text: str,
) -> None:
    service = FakeService()
    handlers = TelegramHandlers(service)
    bot = FakeBot()

    await getattr(handlers, handler_name)(bot, FakeEvent(""), FakeMessage(""))

    assert service.setting_kind == kind
    assert bot.sent[0]["text"] == expected_text


@pytest.mark.asyncio
async def test_handle_mode_with_argument_still_updates_default_mode() -> None:
    service = FakeService()
    handlers = TelegramHandlers(service)
    bot = FakeBot()

    await handlers.handle_mode(bot, FakeEvent(""), FakeMessage("exec"))

    assert service.setting_updates == ["exec"]


@pytest.mark.asyncio
async def test_handle_setting_callback_updates_setting() -> None:
    service = FakeService()
    handlers = TelegramHandlers(service)
    bot = FakeBot()
    event = FakeCallbackEvent("csp:setting:1:set:danger")

    await handlers.handle_setting_callback(bot, event)

    assert service.setting_updates == ["danger"]
    assert bot.answered[0]["text"] == "已更新。"


@pytest.mark.asyncio
async def test_handle_setting_callback_updates_effort_when_model_supports_medium(
    tmp_path: Path,
    model_cache_with_medium_file: Path,
) -> None:
    service = make_real_service(tmp_path, model_cache_with_medium_file)
    handlers = TelegramHandlers(service)
    bot = FakeBot()
    panel = service.open_setting_panel("private_1", "effort")
    event = FakeCallbackEvent(
        encode_setting_callback(panel.token, panel.version, "set", "medium")
    )

    await handlers.handle_setting_callback(bot, event)

    assert bot.answered[0]["text"] == "已更新。"
    assert service.get_preferences("private_1").reasoning_effort == "medium"
    assert "当前推理强度：medium" in bot.edited[0]["text"]


@pytest.mark.asyncio
async def test_handle_pwd_works_when_model_cache_is_missing(tmp_path: Path) -> None:
    service = make_real_service_without_model_cache(tmp_path)
    handlers = TelegramHandlers(service)
    bot = FakeBot()

    await handlers.handle_pwd(bot, FakeEvent(""))

    assert "当前工作目录" in bot.sent[0]["text"]
    assert "模型: gpt-5" in bot.sent[0]["text"]


@pytest.mark.asyncio
async def test_handle_codex_without_prompt_works_when_model_cache_is_missing(
    tmp_path: Path,
) -> None:
    service = make_real_service_without_model_cache(tmp_path)
    handlers = TelegramHandlers(service)
    bot = FakeBot()

    await handlers.handle_codex(bot, FakeEvent(""), FakeMessage(""))

    assert "开始使用" in bot.sent[0]["text"]
    assert "模型: gpt-5" in bot.sent[0]["text"]
