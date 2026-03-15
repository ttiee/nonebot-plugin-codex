from __future__ import annotations

from dataclasses import dataclass

from nonebot.adapters.telegram.model import BotCommand


@dataclass(frozen=True)
class TelegramCommandSpec:
    name: str
    description: str
    usage: str


TELEGRAM_COMMAND_SPECS: tuple[TelegramCommandSpec, ...] = (
    TelegramCommandSpec(
        name="codex",
        description="连接 Codex 并可附带首条任务",
        usage="/codex [prompt]",
    ),
    TelegramCommandSpec(
        name="help",
        description="打开使用引导面板",
        usage="/help",
    ),
    TelegramCommandSpec(
        name="start",
        description="打开使用引导面板",
        usage="/start",
    ),
    TelegramCommandSpec(
        name="panel",
        description="打开当前工作台",
        usage="/panel",
    ),
    TelegramCommandSpec(
        name="status",
        description="打开当前工作台",
        usage="/status",
    ),
    TelegramCommandSpec(
        name="mode",
        description="查看或切换默认模式",
        usage="/mode",
    ),
    TelegramCommandSpec(
        name="exec",
        description="以一次性 exec 模式执行任务",
        usage="/exec",
    ),
    TelegramCommandSpec(
        name="new",
        description="新建当前聊天会话",
        usage="/new",
    ),
    TelegramCommandSpec(
        name="stop",
        description="停止当前聊天中的 Codex",
        usage="/stop",
    ),
    TelegramCommandSpec(
        name="models",
        description="查看可用模型列表",
        usage="/models",
    ),
    TelegramCommandSpec(
        name="model",
        description="查看或切换当前模型",
        usage="/model",
    ),
    TelegramCommandSpec(
        name="effort",
        description="查看或切换推理强度",
        usage="/effort",
    ),
    TelegramCommandSpec(
        name="permission",
        description="查看或切换权限模式",
        usage="/permission",
    ),
    TelegramCommandSpec(
        name="pwd",
        description="查看当前工作目录和设置",
        usage="/pwd",
    ),
    TelegramCommandSpec(
        name="cd",
        description="切换目录或打开目录浏览器",
        usage="/cd",
    ),
    TelegramCommandSpec(
        name="home",
        description="把工作目录重置到 Home",
        usage="/home",
    ),
    TelegramCommandSpec(
        name="sessions",
        description="打开历史会话浏览器",
        usage="/sessions",
    ),
)


def build_plugin_usage() -> str:
    return ", ".join(spec.usage for spec in TELEGRAM_COMMAND_SPECS)


def build_telegram_commands() -> list[BotCommand]:
    return [
        BotCommand(command=spec.name, description=spec.description)
        for spec in TELEGRAM_COMMAND_SPECS
    ]
