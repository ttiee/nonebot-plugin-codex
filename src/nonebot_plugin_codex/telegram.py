from __future__ import annotations

import re
import time
import asyncio
from typing import Any

from nonebot.adapters.telegram import Bot
from nonebot.adapters.telegram.message import Message
from nonebot.adapters.telegram.exception import ActionFailed, NetworkError
from nonebot.adapters.telegram.event import MessageEvent, CallbackQueryEvent

from .service import (
    AgentPanelState,
    BROWSER_STALE_MESSAGE,
    HISTORY_STALE_MESSAGE,
    BROWSER_CALLBACK_PREFIX,
    HISTORY_CALLBACK_PREFIX,
    ONBOARDING_STALE_MESSAGE,
    ONBOARDING_CALLBACK_PREFIX,
    SETTING_STALE_MESSAGE,
    SETTING_CALLBACK_PREFIX,
    WORKSPACE_STALE_MESSAGE,
    WORKSPACE_CALLBACK_PREFIX,
    AgentPanelUpdate,
    CodexBridgeService,
    chunk_text,
    build_chat_key,
    decode_onboarding_callback,
    decode_workspace_callback,
    format_result_text,
    decode_browser_callback,
    decode_history_callback,
    decode_setting_callback,
    should_forward_follow_up,
)
from .telegram_rendering import render_telegram_html

RETRY_AFTER_PATTERN = re.compile(r"retry after (\d+(?:\.\d+)?)", re.IGNORECASE)
PARSE_ENTITIES_ERROR = "can't parse entities"
# Telegram 在编辑后的文本和按钮都没变化时，会返回这个错误。
MESSAGE_NOT_MODIFIED_ERROR = "message is not modified"


class TelegramHandlers:
    def __init__(self, service: CodexBridgeService) -> None:
        self.service = service

    def event_chat(self, event: MessageEvent | CallbackQueryEvent) -> Any:
        chat = getattr(event, "chat", None)
        if chat is not None:
            return chat
        message = getattr(event, "message", None)
        message_chat = getattr(message, "chat", None)
        if message_chat is not None:
            return message_chat
        raise ValueError("无法确定当前聊天上下文。")

    def chat_key(self, event: MessageEvent | CallbackQueryEvent) -> str:
        chat = self.event_chat(event)
        return build_chat_key(chat.type, chat.id)

    def telegram_retry_after(self, exc: Exception) -> float | None:
        if not isinstance(exc, NetworkError):
            return None
        message = getattr(exc, "msg", None) or str(exc)
        match = RETRY_AFTER_PATTERN.search(message)
        if match is None:
            return None
        return float(match.group(1))

    async def retry_telegram_call(self, operation):
        while True:
            try:
                return await operation()
            except Exception as exc:
                retry_after = self.telegram_retry_after(exc)
                if retry_after is None:
                    raise
                await asyncio.sleep(retry_after)

    def is_parse_entities_error(self, exc: Exception) -> bool:
        return isinstance(exc, ActionFailed) and PARSE_ENTITIES_ERROR in str(exc).lower()

    def is_message_not_modified_error(self, exc: Exception) -> bool:
        return isinstance(exc, ActionFailed) and MESSAGE_NOT_MODIFIED_ERROR in str(
            exc
        ).lower()

    async def send_event_message(
        self, bot: Bot, event: MessageEvent, text: str, **kwargs: object
    ):
        rendered_kwargs = dict(kwargs)
        rendered_kwargs["parse_mode"] = "HTML"
        rendered_text = render_telegram_html(text)
        try:
            return await self.retry_telegram_call(
                lambda: bot.send(event, rendered_text, **rendered_kwargs)
            )
        except Exception as exc:
            if not self.is_parse_entities_error(exc):
                raise
            plain_kwargs = dict(kwargs)
            plain_kwargs.pop("parse_mode", None)
            return await self.retry_telegram_call(
                lambda: bot.send(event, text, **plain_kwargs)
            )

    async def send_chat_message(
        self, bot: Bot, chat_id: int, text: str, **kwargs: object
    ):
        rendered_kwargs = dict(kwargs)
        rendered_kwargs["parse_mode"] = "HTML"
        rendered_text = render_telegram_html(text)
        try:
            return await self.retry_telegram_call(
                lambda: bot.send_message(
                    chat_id=chat_id,
                    text=rendered_text,
                    **rendered_kwargs,
                )
            )
        except Exception as exc:
            if not self.is_parse_entities_error(exc):
                raise
            plain_kwargs = dict(kwargs)
            plain_kwargs.pop("parse_mode", None)
            return await self.retry_telegram_call(
                lambda: bot.send_message(chat_id=chat_id, text=text, **plain_kwargs)
            )

    async def edit_message(
        self,
        bot: Bot,
        *,
        chat_id: int,
        message_id: int,
        text: str,
        **kwargs: object,
    ):
        rendered_kwargs = dict(kwargs)
        rendered_kwargs["parse_mode"] = "HTML"
        rendered_text = render_telegram_html(text)
        try:
            return await self.retry_telegram_call(
                lambda: bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=rendered_text,
                    **rendered_kwargs,
                )
            )
        except Exception as exc:
            if not self.is_parse_entities_error(exc):
                raise
            plain_kwargs = dict(kwargs)
            plain_kwargs.pop("parse_mode", None)
            return await self.retry_telegram_call(
                lambda: bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    **plain_kwargs,
                )
            )

    def format_agent_title(self, panel: AgentPanelState) -> str:
        icon = "🧠" if panel.agent_key == "main" else "🛠️"
        return f"{icon} {panel.agent_label}"

    def render_agent_panel_text(
        self,
        session,
        panel: AgentPanelState,
        text: str,
    ) -> str:
        if len(session.agent_order) <= 1:
            return text
        title = self.format_agent_title(panel)
        return f"{title}\n{text}" if text else title

    async def refresh_agent_panel_headers(
        self,
        bot: Bot,
        event: MessageEvent,
        session,
    ) -> None:
        if len(session.agent_order) <= 1:
            return
        for agent_key in session.agent_order:
            panel = session.agent_panels.get(agent_key)
            if panel is None:
                continue
            if panel.progress_message_id is not None and panel.last_progress_text:
                try:
                    await self.edit_message(
                        bot,
                        chat_id=event.chat.id,
                        message_id=panel.progress_message_id,
                        text=self.render_agent_panel_text(
                            session,
                            panel,
                            panel.last_progress_text,
                        ),
                    )
                except Exception as exc:
                    if not self.is_message_not_modified_error(exc):
                        pass
            if panel.stream_message_id is not None and panel.last_stream_text:
                try:
                    rendered_text, truncated = self.render_stream_text(
                        self.render_agent_panel_text(
                            session,
                            panel,
                            panel.last_stream_text,
                        )
                    )
                    if not rendered_text:
                        continue
                    panel.stream_message_truncated = truncated
                    await self.edit_message(
                        bot,
                        chat_id=event.chat.id,
                        message_id=panel.stream_message_id,
                        text=rendered_text,
                    )
                    panel.last_stream_rendered_text = rendered_text
                except Exception as exc:
                    if not self.is_message_not_modified_error(exc):
                        pass

    def ensure_agent_panel(
        self,
        event: MessageEvent,
        *,
        agent_key: str,
        agent_label: str,
    ) -> AgentPanelState:
        session = self.service.get_session(self.chat_key(event))
        panel = session.agent_panels.get(agent_key)
        if panel is not None:
            return panel
        panel = AgentPanelState(agent_key=agent_key, agent_label=agent_label)
        session.agent_panels[agent_key] = panel
        session.agent_order.append(agent_key)
        return panel

    def reset_agent_panels(self, event: MessageEvent) -> None:
        session = self.service.get_session(self.chat_key(event))
        if not session.agent_order:
            panel = AgentPanelState(agent_key="main", agent_label="主 agent")
            session.agent_panels["main"] = panel
            session.agent_order.append("main")
        for panel in session.agent_panels.values():
            panel.progress_message_id = None
            panel.stream_message_id = None
            panel.last_progress_text = ""
            panel.last_stream_rendered_text = ""
            panel.stream_message_truncated = False

    async def update_progress(
        self,
        bot: Bot,
        event: MessageEvent,
        update: AgentPanelUpdate,
    ) -> None:
        session = self.service.get_session(self.chat_key(event))
        created_panel = update.agent_key not in session.agent_panels
        panel = self.ensure_agent_panel(
            event,
            agent_key=update.agent_key,
            agent_label=update.agent_label,
        )
        panel.last_progress_text = update.text
        if created_panel and panel.agent_key != "main" and len(session.agent_order) == 2:
            await self.refresh_agent_panel_headers(bot, event, session)
        text = self.render_agent_panel_text(session, panel, update.text)
        if panel.progress_message_id is None:
            message = await self.send_event_message(bot, event, text)
            panel.progress_message_id = getattr(message, "message_id", None)
            return
        try:
            await self.edit_message(
                bot,
                chat_id=event.chat.id,
                message_id=panel.progress_message_id,
                text=text,
            )
        except Exception:
            message = await self.send_event_message(bot, event, text)
            panel.progress_message_id = getattr(message, "message_id", None)

    def render_stream_text(self, text: str) -> tuple[str, bool]:
        chunks = chunk_text(text, self.service.settings.chunk_size)
        if not chunks:
            return "", False
        if len(chunks) == 1:
            return chunks[0], False
        return chunks[-1], True

    async def update_stream_text(
        self,
        bot: Bot,
        event: MessageEvent,
        update: AgentPanelUpdate,
    ) -> None:
        session = self.service.get_session(self.chat_key(event))
        created_panel = update.agent_key not in session.agent_panels
        panel = self.ensure_agent_panel(
            event,
            agent_key=update.agent_key,
            agent_label=update.agent_label,
        )
        if created_panel and panel.agent_key != "main" and len(session.agent_order) == 2:
            await self.refresh_agent_panel_headers(bot, event, session)
        text = self.render_agent_panel_text(session, panel, update.text)
        rendered_text, truncated = self.render_stream_text(text)
        if not rendered_text:
            return
        panel.stream_message_truncated = truncated
        panel.last_stream_text = update.text
        if rendered_text == panel.last_stream_rendered_text:
            return
        if panel.stream_message_id is None:
            message = await self.send_event_message(bot, event, rendered_text)
            panel.stream_message_id = getattr(message, "message_id", None)
        else:
            try:
                await self.edit_message(
                    bot,
                    chat_id=event.chat.id,
                    message_id=panel.stream_message_id,
                    text=rendered_text,
                )
            except Exception:
                message = await self.send_event_message(bot, event, rendered_text)
                panel.stream_message_id = getattr(message, "message_id", None)
        panel.last_stream_rendered_text = rendered_text

    async def finalize_agent_progress(
        self,
        bot: Bot,
        event: MessageEvent,
        *,
        agent_key: str,
        agent_label: str,
        text: str,
    ) -> None:
        session = self.service.get_session(self.chat_key(event))
        panel = self.ensure_agent_panel(
            event,
            agent_key=agent_key,
            agent_label=agent_label,
        )
        if panel.progress_message_id is None:
            return
        try:
            await self.edit_message(
                bot,
                chat_id=event.chat.id,
                message_id=panel.progress_message_id,
                text=self.render_agent_panel_text(session, panel, text),
            )
        except Exception:
            pass
        finally:
            panel.progress_message_id = None

    async def send_result(self, bot: Bot, event: MessageEvent, text: str) -> None:
        for chunk in chunk_text(text, self.service.settings.chunk_size):
            await self.send_event_message(bot, event, chunk)

    def error_text(self, exc: Exception) -> str:
        if (
            isinstance(exc, FileNotFoundError)
            and exc.args
            and exc.args[0] == self.service.settings.binary
        ):
            return "未找到本机 `codex` CLI，请确认它已经安装并且在 PATH 中。"
        if (
            isinstance(exc, RuntimeError)
            and str(exc) == "Codex is already running for this chat"
        ):
            return "Codex 正在运行中，请等待完成或使用 /stop。"
        return str(exc) or "发生了未知错误。"

    def current_summary(self, chat_key: str) -> str:
        return self.service.describe_preferences(chat_key)

    def format_models(self, chat_key: str) -> str:
        current_model = self.service.get_preferences(chat_key).model
        lines = [f"当前设置：{self.current_summary(chat_key)}", "可用模型："]
        for model in self.service.list_models():
            efforts = "/".join(model.supported_reasoning_levels)
            suffix = " (当前)" if model.slug == current_model else ""
            lines.append(f"- {model.slug} [{efforts}]{suffix}")
        return "\n".join(lines)

    async def execute_prompt(
        self,
        bot: Bot,
        event: MessageEvent,
        prompt: str,
        *,
        mode_override: str | None = None,
    ) -> None:
        chat_key = self.chat_key(event)
        session = self.service.get_session(chat_key)
        session.progress_message_id = None
        session.stream_message_id = None
        session.last_stream_rendered_text = ""
        session.stream_message_truncated = False
        self.reset_agent_panels(event)
        last_stream_update_at: dict[str, float] = {}
        pending_stream_updates: dict[str, AgentPanelUpdate] = {}

        async def on_progress(update: AgentPanelUpdate) -> None:
            await self.update_progress(bot, event, update)

        async def flush_stream_text(agent_key: str | None = None) -> None:
            keys = [agent_key] if agent_key is not None else list(pending_stream_updates)
            for key in keys:
                update = pending_stream_updates.pop(key, None)
                if update is None:
                    continue
                await self.update_stream_text(bot, event, update)
                last_stream_update_at[key] = time.monotonic()

        async def on_stream_text(update: AgentPanelUpdate) -> None:
            pending_stream_updates[update.agent_key] = update
            if time.monotonic() - last_stream_update_at.get(update.agent_key, 0.0) < 0.5:
                return
            await flush_stream_text(update.agent_key)

        try:
            result = await self.service.run_prompt(
                chat_key,
                prompt,
                mode_override=mode_override,
                on_progress=on_progress,
                on_stream_text=on_stream_text,
            )
        except (FileNotFoundError, ValueError) as exc:
            await self.send_event_message(bot, event, self.error_text(exc))
            return
        except RuntimeError:
            await self.send_event_message(
                bot, event, "Codex 正在运行中，请等待完成或使用 /stop。"
            )
            return

        await flush_stream_text()
        if result.cancelled:
            for panel in (
                session.agent_panels[agent_key]
                for agent_key in session.agent_order
                if agent_key in session.agent_panels
            ):
                await self.finalize_agent_progress(
                    bot,
                    event,
                    agent_key=panel.agent_key,
                    agent_label=panel.agent_label,
                    text=f"{panel.agent_label} 已中断。",
                )
            return

        status = "Codex 已完成。" if result.exit_code == 0 else "Codex 执行失败。"
        for panel in (
            session.agent_panels[agent_key]
            for agent_key in session.agent_order
            if agent_key in session.agent_panels
        ):
            panel_status = (
                status
                if panel.agent_key == "main"
                else f"{panel.agent_label} 已完成。"
            )
            await self.finalize_agent_progress(
                bot,
                event,
                agent_key=panel.agent_key,
                agent_label=panel.agent_label,
                text=panel_status,
            )
        main_panel = session.agent_panels.get("main")
        if (
            main_panel is not None
            and
            result.final_text
            and result.final_text == main_panel.last_stream_text
            and not main_panel.stream_message_truncated
        ):
            if result.notice:
                await self.send_result(bot, event, result.notice)
            return
        await self.send_result(bot, event, format_result_text(result))

    async def is_active_follow_up(self, event: MessageEvent) -> bool:
        chat_key = self.chat_key(event)
        session = self.service.sessions.get(chat_key)
        text = event.get_plaintext()
        return bool(
            session
            and session.active
            and text.strip()
            and not text.strip().startswith("/")
        )

    async def is_browser_callback(self, event: CallbackQueryEvent) -> bool:
        return isinstance(event.data, str) and event.data.startswith(
            f"{BROWSER_CALLBACK_PREFIX}:"
        )

    async def is_history_callback(self, event: CallbackQueryEvent) -> bool:
        return isinstance(event.data, str) and event.data.startswith(
            f"{HISTORY_CALLBACK_PREFIX}:"
        )

    async def is_setting_callback(self, event: CallbackQueryEvent) -> bool:
        return isinstance(event.data, str) and event.data.startswith(
            f"{SETTING_CALLBACK_PREFIX}:"
        )

    async def is_onboarding_callback(self, event: CallbackQueryEvent) -> bool:
        return isinstance(event.data, str) and event.data.startswith(
            f"{ONBOARDING_CALLBACK_PREFIX}:"
        )

    async def is_workspace_callback(self, event: CallbackQueryEvent) -> bool:
        return isinstance(event.data, str) and event.data.startswith(
            f"{WORKSPACE_CALLBACK_PREFIX}:"
        )

    def callback_message_id(self, event: CallbackQueryEvent) -> int | None:
        message = getattr(event, "message", None)
        return getattr(message, "message_id", None)

    async def send_browser(self, bot: Bot, event: MessageEvent, chat_key: str) -> None:
        browser = self.service.open_directory_browser(chat_key)
        text, markup = self.service.render_directory_browser(chat_key)
        message = await self.send_event_message(bot, event, text, reply_markup=markup)
        self.service.remember_browser_message(
            chat_key, browser.token, getattr(message, "message_id", None)
        )

    async def send_browser_to_chat(
        self, bot: Bot, chat_id: int, chat_key: str
    ) -> None:
        browser = self.service.open_directory_browser(chat_key)
        text, markup = self.service.render_directory_browser(chat_key)
        message = await self.send_chat_message(bot, chat_id, text, reply_markup=markup)
        self.service.remember_browser_message(
            chat_key, browser.token, getattr(message, "message_id", None)
        )

    async def send_history_browser(
        self, bot: Bot, event: MessageEvent, chat_key: str
    ) -> None:
        await self.service.refresh_history_sessions()
        browser = self.service.open_history_browser(chat_key)
        text, markup = self.service.render_history_browser(chat_key)
        message = await self.send_event_message(bot, event, text, reply_markup=markup)
        self.service.remember_history_browser_message(
            chat_key,
            browser.token,
            getattr(message, "message_id", None),
        )

    async def send_history_browser_to_chat(
        self, bot: Bot, chat_id: int, chat_key: str
    ) -> None:
        await self.service.refresh_history_sessions()
        browser = self.service.open_history_browser(chat_key)
        text, markup = self.service.render_history_browser(chat_key)
        message = await self.send_chat_message(bot, chat_id, text, reply_markup=markup)
        self.service.remember_history_browser_message(
            chat_key,
            browser.token,
            getattr(message, "message_id", None),
        )

    async def send_setting_panel(
        self,
        bot: Bot,
        event: MessageEvent,
        chat_key: str,
        kind: str,
    ) -> None:
        panel = self.service.open_setting_panel(chat_key, kind)
        text, markup = self.service.render_setting_panel(chat_key)
        message = await self.send_event_message(bot, event, text, reply_markup=markup)
        self.service.remember_setting_panel_message(
            chat_key,
            panel.token,
            getattr(message, "message_id", None),
        )

    async def send_setting_panel_to_chat(
        self,
        bot: Bot,
        chat_id: int,
        chat_key: str,
        kind: str,
    ) -> None:
        panel = self.service.open_setting_panel(chat_key, kind)
        text, markup = self.service.render_setting_panel(chat_key)
        message = await self.send_chat_message(bot, chat_id, text, reply_markup=markup)
        self.service.remember_setting_panel_message(
            chat_key,
            panel.token,
            getattr(message, "message_id", None),
        )

    async def send_onboarding_panel(
        self, bot: Bot, event: MessageEvent, chat_key: str
    ) -> None:
        panel = self.service.open_onboarding_panel(chat_key)
        text, markup = self.service.render_onboarding_panel(chat_key)
        message = await self.send_event_message(bot, event, text, reply_markup=markup)
        self.service.remember_onboarding_panel_message(
            chat_key,
            panel.token,
            getattr(message, "message_id", None),
        )

    async def send_workspace_panel(
        self, bot: Bot, event: MessageEvent, chat_key: str
    ) -> None:
        panel = self.service.open_workspace_panel(chat_key)
        text, markup = self.service.render_workspace_panel(chat_key)
        message = await self.send_event_message(bot, event, text, reply_markup=markup)
        self.service.remember_workspace_panel_message(
            chat_key,
            panel.token,
            getattr(message, "message_id", None),
        )

    async def edit_or_resend_browser(
        self,
        bot: Bot,
        event: CallbackQueryEvent,
        chat_key: str,
    ) -> None:
        browser = self.service.get_browser(chat_key)
        text, markup = self.service.render_directory_browser(chat_key)
        message_id = self.callback_message_id(event) or browser.message_id
        chat_id = self.event_chat(event).id
        try:
            if message_id is None:
                raise ValueError("missing message id")
            await self.edit_message(
                bot,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=markup,
            )
            self.service.remember_browser_message(chat_key, browser.token, message_id)
        except Exception:
            message = await self.send_chat_message(
                bot, chat_id, text, reply_markup=markup
            )
            self.service.remember_browser_message(
                chat_key,
                browser.token,
                getattr(message, "message_id", None),
            )

    async def edit_or_resend_history_browser(
        self,
        bot: Bot,
        event: CallbackQueryEvent,
        chat_key: str,
    ) -> None:
        browser = self.service.get_history_browser(chat_key)
        text, markup = self.service.render_history_browser(chat_key)
        message_id = self.callback_message_id(event) or browser.message_id
        chat_id = self.event_chat(event).id
        try:
            if message_id is None:
                raise ValueError("missing message id")
            await self.edit_message(
                bot,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=markup,
            )
            self.service.remember_history_browser_message(
                chat_key, browser.token, message_id
            )
        except Exception as exc:
            if self.is_message_not_modified_error(exc):
                # 原消息内容未变化时不需要补发，否则会把同一个历史面板再发一遍。
                self.service.remember_history_browser_message(
                    chat_key, browser.token, message_id
                )
                return
            message = await self.send_chat_message(
                bot, chat_id, text, reply_markup=markup
            )
            self.service.remember_history_browser_message(
                chat_key,
                browser.token,
                getattr(message, "message_id", None),
            )

    async def edit_or_resend_setting_panel(
        self,
        bot: Bot,
        event: CallbackQueryEvent,
        chat_key: str,
    ) -> None:
        panel = self.service.get_setting_panel(chat_key)
        text, markup = self.service.render_setting_panel(chat_key)
        message_id = self.callback_message_id(event) or panel.message_id
        chat_id = self.event_chat(event).id
        try:
            if message_id is None:
                raise ValueError("missing message id")
            await self.edit_message(
                bot,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=markup,
            )
            self.service.remember_setting_panel_message(chat_key, panel.token, message_id)
        except Exception:
            message = await self.send_chat_message(
                bot, chat_id, text, reply_markup=markup
            )
            self.service.remember_setting_panel_message(
                chat_key,
                panel.token,
                getattr(message, "message_id", None),
            )

    async def edit_or_resend_workspace_panel(
        self,
        bot: Bot,
        event: CallbackQueryEvent,
        chat_key: str,
    ) -> None:
        panel = self.service.get_workspace_panel(chat_key)
        text, markup = self.service.render_workspace_panel(chat_key)
        message_id = self.callback_message_id(event) or panel.message_id
        chat_id = self.event_chat(event).id
        try:
            if message_id is None:
                raise ValueError("missing message id")
            await self.edit_message(
                bot,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=markup,
            )
            self.service.remember_workspace_panel_message(
                chat_key, panel.token, message_id
            )
        except Exception:
            message = await self.send_chat_message(
                bot, chat_id, text, reply_markup=markup
            )
            self.service.remember_workspace_panel_message(
                chat_key,
                panel.token,
                getattr(message, "message_id", None),
            )

    async def handle_codex(self, bot: Bot, event: MessageEvent, args: Message) -> None:
        chat_key = self.chat_key(event)
        session = self.service.activate_chat(chat_key)
        if session.running:
            await self.send_event_message(
                bot, event, "Codex 正在运行中，请等待完成或使用 /stop。"
            )
            return

        prompt = args.extract_plain_text().strip()
        if prompt:
            await self.execute_prompt(bot, event, prompt)
            return

        await self.send_onboarding_panel(bot, event, chat_key)

    async def handle_help(self, bot: Bot, event: MessageEvent) -> None:
        await self.send_onboarding_panel(bot, event, self.chat_key(event))

    async def handle_start(self, bot: Bot, event: MessageEvent) -> None:
        await self.send_onboarding_panel(bot, event, self.chat_key(event))

    async def handle_panel(self, bot: Bot, event: MessageEvent) -> None:
        await self.send_workspace_panel(bot, event, self.chat_key(event))

    async def handle_status(self, bot: Bot, event: MessageEvent) -> None:
        await self.send_workspace_panel(bot, event, self.chat_key(event))

    async def handle_mode(self, bot: Bot, event: MessageEvent, args: Message) -> None:
        chat_key = self.chat_key(event)
        mode = args.extract_plain_text().strip()
        try:
            if not mode:
                await self.send_setting_panel(bot, event, chat_key, "mode")
                return
            notice = await self.service.update_default_mode(chat_key, mode)
            await self.send_event_message(bot, event, notice)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            await self.send_event_message(bot, event, self.error_text(exc))

    async def handle_exec(self, bot: Bot, event: MessageEvent, args: Message) -> None:
        prompt = args.extract_plain_text().strip()
        if not prompt:
            await self.send_event_message(bot, event, "请在 /exec 后输入要执行的内容。")
            return
        await self.execute_prompt(bot, event, prompt, mode_override="exec")

    async def handle_new(self, bot: Bot, event: MessageEvent) -> None:
        chat_key = self.chat_key(event)
        await self.service.reset_chat(chat_key, keep_active=True)
        await self.send_event_message(
            bot,
            event,
            (
                "已清空当前 Codex 会话。下一条普通消息会按以下设置新开会话：\n"
                f"{self.current_summary(chat_key)}"
            ),
        )

    async def handle_stop(self, bot: Bot, event: MessageEvent) -> None:
        await self.service.reset_chat(self.chat_key(event), keep_active=False)
        await self.send_event_message(bot, event, "已断开当前聊天窗口的 Codex 会话。")

    async def handle_models(self, bot: Bot, event: MessageEvent) -> None:
        chat_key = self.chat_key(event)
        try:
            await self.send_event_message(bot, event, self.format_models(chat_key))
        except (FileNotFoundError, ValueError) as exc:
            await self.send_event_message(bot, event, self.error_text(exc))

    async def handle_model(self, bot: Bot, event: MessageEvent, args: Message) -> None:
        chat_key = self.chat_key(event)
        slug = args.extract_plain_text().strip()
        try:
            if not slug:
                await self.send_setting_panel(bot, event, chat_key, "model")
                return
            notice = await self.service.update_model(chat_key, slug)
            await self.send_event_message(bot, event, notice)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            await self.send_event_message(bot, event, self.error_text(exc))

    async def handle_effort(self, bot: Bot, event: MessageEvent, args: Message) -> None:
        chat_key = self.chat_key(event)
        effort = args.extract_plain_text().strip()
        try:
            if not effort:
                await self.send_setting_panel(bot, event, chat_key, "effort")
                return
            notice = await self.service.update_reasoning_effort(chat_key, effort)
            await self.send_event_message(bot, event, notice)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            await self.send_event_message(bot, event, self.error_text(exc))

    async def handle_permission(
        self, bot: Bot, event: MessageEvent, args: Message
    ) -> None:
        chat_key = self.chat_key(event)
        permission = args.extract_plain_text().strip()
        try:
            if not permission:
                await self.send_setting_panel(bot, event, chat_key, "permission")
                return
            notice = await self.service.update_permission_mode(chat_key, permission)
            await self.send_event_message(bot, event, notice)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            await self.send_event_message(bot, event, self.error_text(exc))

    async def handle_pwd(self, bot: Bot, event: MessageEvent) -> None:
        await self.send_event_message(
            bot, event, self.service.describe_workdir(self.chat_key(event))
        )

    async def handle_cd(self, bot: Bot, event: MessageEvent, args: Message) -> None:
        chat_key = self.chat_key(event)
        target = args.extract_plain_text().strip()
        try:
            if not target:
                await self.send_browser(bot, event, chat_key)
                return
            await self.send_event_message(
                bot, event, await self.service.update_workdir(chat_key, target)
            )
        except (ValueError, RuntimeError) as exc:
            await self.send_event_message(bot, event, self.error_text(exc))

    async def handle_home(self, bot: Bot, event: MessageEvent) -> None:
        try:
            notice = await self.service.update_workdir(
                self.chat_key(event),
                self.service.configured_workdir(),
            )
            await self.send_event_message(bot, event, notice)
        except (ValueError, RuntimeError) as exc:
            await self.send_event_message(bot, event, self.error_text(exc))

    async def handle_sessions(self, bot: Bot, event: MessageEvent) -> None:
        try:
            await self.send_history_browser(bot, event, self.chat_key(event))
        except (ValueError, RuntimeError) as exc:
            await self.send_event_message(bot, event, self.error_text(exc))

    async def handle_compact(self, bot: Bot, event: MessageEvent) -> None:
        try:
            notice = await self.service.compact_chat(self.chat_key(event))
            await self.send_event_message(bot, event, notice)
        except (ValueError, RuntimeError) as exc:
            await self.send_event_message(bot, event, self.error_text(exc))

    async def handle_browser_callback(self, bot: Bot, event: CallbackQueryEvent) -> None:
        if not isinstance(event.data, str):
            await bot.answer_callback_query(
                event.id, text=BROWSER_STALE_MESSAGE, show_alert=True
            )
            return

        try:
            chat_key = self.chat_key(event)
            chat_id = self.event_chat(event).id
            token, version, action, index = decode_browser_callback(event.data)
            if action == "apply":
                await self.service.apply_browser_directory(chat_key, token, version)
                await self.edit_or_resend_browser(bot, event, chat_key)
                await bot.answer_callback_query(event.id, text="工作目录已更新。")
                return
            if action == "close":
                self.service.close_directory_browser(chat_key, token, version)
                message_id = self.callback_message_id(event)
                if message_id is not None:
                    await self.edit_message(
                        bot,
                        chat_id=chat_id,
                        message_id=message_id,
                        text="目录浏览已关闭。",
                        reply_markup=None,
                    )
                await bot.answer_callback_query(event.id, text="已关闭。")
                return
            self.service.navigate_directory_browser(
                chat_key, token, version, action, index
            )
            await self.edit_or_resend_browser(bot, event, chat_key)
            await bot.answer_callback_query(event.id)
        except ValueError as exc:
            text = str(exc) or BROWSER_STALE_MESSAGE
            await bot.answer_callback_query(
                event.id,
                text=text,
                show_alert=text == BROWSER_STALE_MESSAGE,
            )
        except RuntimeError as exc:
            await bot.answer_callback_query(
                event.id, text=self.error_text(exc), show_alert=True
            )

    async def handle_history_callback(self, bot: Bot, event: CallbackQueryEvent) -> None:
        if not isinstance(event.data, str):
            await bot.answer_callback_query(
                event.id, text=HISTORY_STALE_MESSAGE, show_alert=True
            )
            return

        try:
            chat_key = self.chat_key(event)
            chat_id = self.event_chat(event).id
            token, version, action, index = decode_history_callback(event.data)
            if action == "apply":
                notice = await self.service.apply_history_session(
                    chat_key, token, version
                )
                await self.edit_or_resend_history_browser(bot, event, chat_key)
                await bot.answer_callback_query(event.id, text="已切换到历史会话。")
                await self.send_chat_message(bot, chat_id, notice)
                return
            if action == "close":
                self.service.close_history_browser(chat_key, token, version)
                message_id = self.callback_message_id(event)
                if message_id is not None:
                    await self.edit_message(
                        bot,
                        chat_id=chat_id,
                        message_id=message_id,
                        text="历史会话浏览已关闭。",
                        reply_markup=None,
                    )
                await bot.answer_callback_query(event.id, text="已关闭。")
                return
            if action == "refresh":
                await self.service.refresh_history_sessions()
            self.service.navigate_history_browser(chat_key, token, version, action, index)
            await self.edit_or_resend_history_browser(bot, event, chat_key)
            await bot.answer_callback_query(event.id)
        except ValueError as exc:
            text = str(exc) or HISTORY_STALE_MESSAGE
            await bot.answer_callback_query(
                event.id,
                text=text,
                show_alert=text == HISTORY_STALE_MESSAGE,
            )
        except RuntimeError as exc:
            await bot.answer_callback_query(
                event.id, text=self.error_text(exc), show_alert=True
            )

    async def handle_setting_callback(self, bot: Bot, event: CallbackQueryEvent) -> None:
        if not isinstance(event.data, str):
            await bot.answer_callback_query(
                event.id, text=SETTING_STALE_MESSAGE, show_alert=True
            )
            return

        try:
            chat_key = self.chat_key(event)
            chat_id = self.event_chat(event).id
            token, version, action, value = decode_setting_callback(event.data)
            if action == "set":
                if not value:
                    raise ValueError("设置值无效。")
                await self.service.apply_setting_panel_selection(
                    chat_key, token, version, value
                )
                await self.edit_or_resend_setting_panel(bot, event, chat_key)
                await bot.answer_callback_query(event.id, text="已更新。")
                return
            if action == "close":
                self.service.close_setting_panel(chat_key, token, version)
                message_id = self.callback_message_id(event)
                if message_id is not None:
                    await self.edit_message(
                        bot,
                        chat_id=chat_id,
                        message_id=message_id,
                        text="设置面板已关闭。",
                        reply_markup=None,
                    )
                await bot.answer_callback_query(event.id, text="已关闭。")
                return
            self.service.navigate_setting_panel(chat_key, token, version, action)
            await self.edit_or_resend_setting_panel(bot, event, chat_key)
            await bot.answer_callback_query(event.id)
        except ValueError as exc:
            text = str(exc) or SETTING_STALE_MESSAGE
            await bot.answer_callback_query(
                event.id,
                text=text,
                show_alert=text == SETTING_STALE_MESSAGE,
            )
        except RuntimeError as exc:
            await bot.answer_callback_query(
                event.id, text=self.error_text(exc), show_alert=True
            )

    async def handle_onboarding_callback(
        self, bot: Bot, event: CallbackQueryEvent
    ) -> None:
        if not isinstance(event.data, str):
            await bot.answer_callback_query(
                event.id, text=ONBOARDING_STALE_MESSAGE, show_alert=True
            )
            return

        try:
            chat_key = self.chat_key(event)
            chat_id = self.event_chat(event).id
            token, version, action = decode_onboarding_callback(event.data)
            self.service.get_onboarding_panel(chat_key, token=token, version=version)
            if action == "browse":
                await self.send_browser_to_chat(bot, chat_id, chat_key)
                await bot.answer_callback_query(event.id)
                return
            if action == "history":
                await self.send_history_browser_to_chat(bot, chat_id, chat_key)
                await bot.answer_callback_query(event.id)
                return
            if action == "settings":
                await self.send_setting_panel_to_chat(bot, chat_id, chat_key, "mode")
                await bot.answer_callback_query(event.id)
                return
            if action == "new":
                await self.service.reset_chat(chat_key, keep_active=True)
                await self.send_chat_message(
                    bot,
                    chat_id,
                    (
                        "已清空当前 Codex 会话。下一条普通消息会按以下设置新开会话：\n"
                        f"{self.current_summary(chat_key)}"
                    ),
                )
                await bot.answer_callback_query(event.id, text="已新开会话。")
                return
            if action == "close":
                self.service.close_onboarding_panel(chat_key, token, version)
                message_id = self.callback_message_id(event)
                if message_id is not None:
                    await self.edit_message(
                        bot,
                        chat_id=chat_id,
                        message_id=message_id,
                        text="使用引导已关闭。",
                        reply_markup=None,
                    )
                await bot.answer_callback_query(event.id, text="已关闭。")
                return
            raise ValueError("未知引导操作。")
        except ValueError as exc:
            text = str(exc) or ONBOARDING_STALE_MESSAGE
            await bot.answer_callback_query(
                event.id,
                text=text,
                show_alert=text == ONBOARDING_STALE_MESSAGE,
            )
        except RuntimeError as exc:
            await bot.answer_callback_query(
                event.id, text=self.error_text(exc), show_alert=True
            )

    async def handle_workspace_callback(
        self, bot: Bot, event: CallbackQueryEvent
    ) -> None:
        if not isinstance(event.data, str):
            await bot.answer_callback_query(
                event.id, text=WORKSPACE_STALE_MESSAGE, show_alert=True
            )
            return

        try:
            chat_key = self.chat_key(event)
            chat_id = self.event_chat(event).id
            token, version, action = decode_workspace_callback(event.data)
            self.service.get_workspace_panel(chat_key, token=token, version=version)
            if action in {"mode", "model", "effort", "permission"}:
                await self.send_setting_panel_to_chat(bot, chat_id, chat_key, action)
                await bot.answer_callback_query(event.id)
                return
            if action == "browse":
                await self.send_browser_to_chat(bot, chat_id, chat_key)
                await bot.answer_callback_query(event.id)
                return
            if action == "history":
                await self.send_history_browser_to_chat(bot, chat_id, chat_key)
                await bot.answer_callback_query(event.id)
                return
            if action == "new":
                await self.service.reset_chat(chat_key, keep_active=True)
                await self.send_chat_message(
                    bot,
                    chat_id,
                    (
                        "已清空当前 Codex 会话。下一条普通消息会按以下设置新开会话：\n"
                        f"{self.current_summary(chat_key)}"
                    ),
                )
                await bot.answer_callback_query(event.id, text="已新开会话。")
                return
            if action == "stop":
                await self.service.reset_chat(chat_key, keep_active=False)
                await self.send_chat_message(
                    bot, chat_id, "已断开当前聊天窗口的 Codex 会话。"
                )
                await bot.answer_callback_query(event.id, text="已停止。")
                return
            if action == "close":
                self.service.close_workspace_panel(chat_key, token, version)
                message_id = self.callback_message_id(event)
                if message_id is not None:
                    await self.edit_message(
                        bot,
                        chat_id=chat_id,
                        message_id=message_id,
                        text="工作台已关闭。",
                        reply_markup=None,
                    )
                await bot.answer_callback_query(event.id, text="已关闭。")
                return
            self.service.navigate_workspace_panel(chat_key, token, version, action)
            await self.edit_or_resend_workspace_panel(bot, event, chat_key)
            await bot.answer_callback_query(event.id)
        except ValueError as exc:
            text = str(exc) or WORKSPACE_STALE_MESSAGE
            await bot.answer_callback_query(
                event.id,
                text=text,
                show_alert=text == WORKSPACE_STALE_MESSAGE,
            )
        except RuntimeError as exc:
            await bot.answer_callback_query(
                event.id, text=self.error_text(exc), show_alert=True
            )

    async def handle_follow_up(self, bot: Bot, event: MessageEvent) -> None:
        chat_key = self.chat_key(event)
        session = self.service.get_session(chat_key)
        text = event.get_plaintext().strip()

        if not should_forward_follow_up(session, text):
            await self.send_event_message(
                bot, event, "Codex 正在运行中，请等待完成或使用 /stop。"
            )
            return

        await self.execute_prompt(bot, event, text)
