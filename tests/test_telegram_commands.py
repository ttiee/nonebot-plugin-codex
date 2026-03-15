from __future__ import annotations

from nonebot_plugin_codex.telegram_commands import (
    TELEGRAM_COMMAND_SPECS,
    build_plugin_usage,
    build_telegram_commands,
)


def test_build_telegram_commands_uses_expected_order_and_chinese_descriptions() -> None:
    assert [spec.name for spec in TELEGRAM_COMMAND_SPECS] == [
        "codex",
        "help",
        "start",
        "mode",
        "exec",
        "new",
        "stop",
        "models",
        "model",
        "effort",
        "permission",
        "pwd",
        "cd",
        "home",
        "sessions",
    ]

    assert [command.model_dump() for command in build_telegram_commands()] == [
        {"command": "codex", "description": "连接 Codex 并可附带首条任务"},
        {"command": "help", "description": "打开使用引导面板"},
        {"command": "start", "description": "打开使用引导面板"},
        {"command": "mode", "description": "查看或切换默认模式"},
        {"command": "exec", "description": "以一次性 exec 模式执行任务"},
        {"command": "new", "description": "新建当前聊天会话"},
        {"command": "stop", "description": "停止当前聊天中的 Codex"},
        {"command": "models", "description": "查看可用模型列表"},
        {"command": "model", "description": "查看或切换当前模型"},
        {"command": "effort", "description": "查看或切换推理强度"},
        {"command": "permission", "description": "查看或切换权限模式"},
        {"command": "pwd", "description": "查看当前工作目录和设置"},
        {"command": "cd", "description": "切换目录或打开目录浏览器"},
        {"command": "home", "description": "把工作目录重置到 Home"},
        {"command": "sessions", "description": "打开历史会话浏览器"},
    ]


def test_build_plugin_usage_lists_all_commands() -> None:
    assert build_plugin_usage() == (
        "/codex [prompt], /help, /start, /mode, /exec, /new, /stop, /models, "
        "/model, /effort, /permission, /pwd, /cd, /home, /sessions"
    )
