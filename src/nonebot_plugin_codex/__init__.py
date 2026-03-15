from __future__ import annotations

from pathlib import Path

from nonebot import get_plugin_config, on_command, on_message, on_type, require
from nonebot.drivers import Driver
from nonebot.log import logger
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg
from nonebot.adapters.telegram import Bot
from nonebot.adapters.telegram.message import Message
from nonebot.adapters.telegram.event import MessageEvent, CallbackQueryEvent
from nonebot.adapters.telegram.model import (
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

from .config import Config
from .telegram import TelegramHandlers
from .telegram_commands import build_plugin_usage, build_telegram_commands
from .native_client import NativeCodexClient
from .runtime import build_service_settings
from .service import CodexBridgeService

__plugin_meta__ = PluginMetadata(
    name="Codex",
    description="Telegram bridge plugin for driving Codex from NoneBot",
    usage=build_plugin_usage(),
    homepage="https://github.com/ttiee/nonebot-plugin-codex",
    type="application",
    config=Config,
    supported_adapters={"~telegram"},
)

try:
    plugin_config = get_plugin_config(Config)
    _runtime_ready = True
except ValueError:
    plugin_config = Config()
    _runtime_ready = False


def _get_plugin_data_dir() -> Path:
    try:
        require("nonebot_plugin_localstore")
        import nonebot_plugin_localstore as store

        return store.get_plugin_data_dir()
    except Exception:
        return Path("data") / "nonebot_plugin_codex"


service = CodexBridgeService(
    build_service_settings(
        plugin_config,
        plugin_data_dir=_get_plugin_data_dir(),
    ),
    native_client=NativeCodexClient(
        binary=plugin_config.codex_binary,
        stream_read_limit=plugin_config.codex_stream_read_limit,
    ),
)
handlers = TelegramHandlers(service)


async def sync_telegram_commands(bot: Bot) -> bool:
    synced = True
    scopes = (
        BotCommandScopeAllPrivateChats(),
        BotCommandScopeAllGroupChats(),
    )
    commands = build_telegram_commands()
    for scope in scopes:
        try:
            await bot.set_my_commands(commands, scope=scope)
        except Exception as exc:
            logger.warning(f"Telegram 命令菜单同步失败（{scope.type}）：{exc}")
            synced = False
    return synced

if _runtime_ready:
    @Driver.on_bot_connect
    async def _sync_telegram_commands(bot: Bot) -> None:
        if not isinstance(bot, Bot):
            return
        await sync_telegram_commands(bot)

    codex_cmd = on_command("codex", priority=10, block=True)
    help_cmd = on_command("help", priority=10, block=True)
    start_cmd = on_command("start", priority=10, block=True)
    mode_cmd = on_command("mode", priority=10, block=True)
    exec_cmd = on_command("exec", priority=10, block=True)
    new_cmd = on_command("new", priority=10, block=True)
    stop_cmd = on_command("stop", priority=10, block=True)
    models_cmd = on_command("models", priority=10, block=True)
    model_cmd = on_command("model", priority=10, block=True)
    effort_cmd = on_command("effort", priority=10, block=True)
    permission_cmd = on_command("permission", priority=10, block=True)
    pwd_cmd = on_command("pwd", priority=10, block=True)
    cd_cmd = on_command("cd", priority=10, block=True)
    home_cmd = on_command("home", priority=10, block=True)
    sessions_cmd = on_command("sessions", priority=10, block=True)
    follow_up = on_message(priority=20, block=True, rule=handlers.is_active_follow_up)
    browser_callback = on_type(
        CallbackQueryEvent,
        priority=10,
        block=True,
        rule=handlers.is_browser_callback,
    )
    history_callback = on_type(
        CallbackQueryEvent,
        priority=10,
        block=True,
        rule=handlers.is_history_callback,
    )
    setting_callback = on_type(
        CallbackQueryEvent,
        priority=10,
        block=True,
        rule=handlers.is_setting_callback,
    )
    onboarding_callback = on_type(
        CallbackQueryEvent,
        priority=10,
        block=True,
        rule=handlers.is_onboarding_callback,
    )

    @codex_cmd.handle()
    async def _handle_codex(
        bot: Bot, event: MessageEvent, args: Message = CommandArg()
    ) -> None:
        await handlers.handle_codex(bot, event, args)

    @help_cmd.handle()
    async def _handle_help(bot: Bot, event: MessageEvent) -> None:
        await handlers.handle_help(bot, event)

    @start_cmd.handle()
    async def _handle_start(bot: Bot, event: MessageEvent) -> None:
        await handlers.handle_start(bot, event)

    @mode_cmd.handle()
    async def _handle_mode(
        bot: Bot, event: MessageEvent, args: Message = CommandArg()
    ) -> None:
        await handlers.handle_mode(bot, event, args)

    @exec_cmd.handle()
    async def _handle_exec(
        bot: Bot, event: MessageEvent, args: Message = CommandArg()
    ) -> None:
        await handlers.handle_exec(bot, event, args)

    @new_cmd.handle()
    async def _handle_new(bot: Bot, event: MessageEvent) -> None:
        await handlers.handle_new(bot, event)

    @stop_cmd.handle()
    async def _handle_stop(bot: Bot, event: MessageEvent) -> None:
        await handlers.handle_stop(bot, event)

    @models_cmd.handle()
    async def _handle_models(bot: Bot, event: MessageEvent) -> None:
        await handlers.handle_models(bot, event)

    @model_cmd.handle()
    async def _handle_model(
        bot: Bot, event: MessageEvent, args: Message = CommandArg()
    ) -> None:
        await handlers.handle_model(bot, event, args)

    @effort_cmd.handle()
    async def _handle_effort(
        bot: Bot, event: MessageEvent, args: Message = CommandArg()
    ) -> None:
        await handlers.handle_effort(bot, event, args)

    @permission_cmd.handle()
    async def _handle_permission(
        bot: Bot,
        event: MessageEvent,
        args: Message = CommandArg(),
    ) -> None:
        await handlers.handle_permission(bot, event, args)

    @pwd_cmd.handle()
    async def _handle_pwd(bot: Bot, event: MessageEvent) -> None:
        await handlers.handle_pwd(bot, event)

    @cd_cmd.handle()
    async def _handle_cd(
        bot: Bot, event: MessageEvent, args: Message = CommandArg()
    ) -> None:
        await handlers.handle_cd(bot, event, args)

    @home_cmd.handle()
    async def _handle_home(bot: Bot, event: MessageEvent) -> None:
        await handlers.handle_home(bot, event)

    @sessions_cmd.handle()
    async def _handle_sessions(bot: Bot, event: MessageEvent) -> None:
        await handlers.handle_sessions(bot, event)

    @browser_callback.handle()
    async def _handle_browser_callback(bot: Bot, event: CallbackQueryEvent) -> None:
        await handlers.handle_browser_callback(bot, event)

    @history_callback.handle()
    async def _handle_history_callback(bot: Bot, event: CallbackQueryEvent) -> None:
        await handlers.handle_history_callback(bot, event)

    @setting_callback.handle()
    async def _handle_setting_callback(bot: Bot, event: CallbackQueryEvent) -> None:
        await handlers.handle_setting_callback(bot, event)

    @onboarding_callback.handle()
    async def _handle_onboarding_callback(
        bot: Bot, event: CallbackQueryEvent
    ) -> None:
        await handlers.handle_onboarding_callback(bot, event)

    @follow_up.handle()
    async def _handle_follow_up(bot: Bot, event: MessageEvent) -> None:
        await handlers.handle_follow_up(bot, event)
