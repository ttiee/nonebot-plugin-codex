from __future__ import annotations

from nonebot import get_plugin_config, on_command, on_message, on_type
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg
from nonebot.adapters.telegram import Bot
from nonebot.adapters.telegram.message import Message
from nonebot.adapters.telegram.event import MessageEvent, CallbackQueryEvent

from .config import Config
from .telegram import TelegramHandlers
from .native_client import NativeCodexClient
from .service import CodexBridgeService, CodexBridgeSettings

__plugin_meta__ = PluginMetadata(
    name="Codex",
    description="Telegram bridge plugin for driving Codex from NoneBot",
    usage=(
        "/codex [prompt], /mode, /exec, /new, /stop, /models, /model, /effort, "
        "/permission, /pwd, /cd, /home, /sessions"
    ),
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

service = CodexBridgeService(
    CodexBridgeSettings(
        binary=plugin_config.codex_binary,
        workdir=str(plugin_config.codex_workdir),
        kill_timeout=plugin_config.codex_kill_timeout,
        progress_history=plugin_config.codex_progress_history,
        diagnostic_history=plugin_config.codex_diagnostic_history,
        chunk_size=plugin_config.codex_chunk_size,
        stream_read_limit=plugin_config.codex_stream_read_limit,
        models_cache_path=plugin_config.codex_models_cache_path,
        codex_config_path=plugin_config.codex_codex_config_path,
        preferences_path=plugin_config.codex_preferences_path,
        session_index_path=plugin_config.codex_session_index_path,
        sessions_dir=plugin_config.codex_sessions_dir,
        archived_sessions_dir=plugin_config.codex_archived_sessions_dir,
    ),
    native_client=NativeCodexClient(
        binary=plugin_config.codex_binary,
        stream_read_limit=plugin_config.codex_stream_read_limit,
    ),
)
handlers = TelegramHandlers(service)

if _runtime_ready:
    codex_cmd = on_command("codex", priority=10, block=True)
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

    @codex_cmd.handle()
    async def _handle_codex(
        bot: Bot, event: MessageEvent, args: Message = CommandArg()
    ) -> None:
        await handlers.handle_codex(bot, event, args)

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

    @follow_up.handle()
    async def _handle_follow_up(bot: Bot, event: MessageEvent) -> None:
        await handlers.handle_follow_up(bot, event)
