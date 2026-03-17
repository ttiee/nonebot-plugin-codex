<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <a href="https://nonebot.dev/"><img src="https://nonebot.dev/logo.png" width="200" height="200" alt="nonebot"></a>
</p>

<div align="center">

# nonebot-plugin-codex

_✨ 在 Telegram 里驱动 Codex CLI 的 NoneBot 插件 ✨_
<!-- **把本机 Codex CLI 接入 Telegram 的 NoneBot 插件** -->

让你直接在 Telegram 里发起 Codex 会话、续聊上下文、切换工作目录、浏览历史会话，把本地开发工作流搬进聊天窗口。

<p>
  <a href="https://github.com/ttiee/nonebot-plugin-codex/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/ttiee/nonebot-plugin-codex.svg" alt="license">
  </a>
  <a href="https://pypi.org/project/nonebot-plugin-codex/">
    <img src="https://img.shields.io/pypi/v/nonebot-plugin-codex.svg" alt="pypi">
  </a>
  <img src="https://img.shields.io/badge/python-3.10+-3776AB.svg" alt="python">
  <img src="https://img.shields.io/badge/NoneBot-2.4.4+-00A7E1.svg" alt="nonebot">
  <img src="https://img.shields.io/badge/adapter-Telegram-26A5E4.svg" alt="telegram">
  <img src="https://img.shields.io/github/actions/workflow/status/ttiee/nonebot-plugin-codex/test.yml?branch=main&label=test" alt="test">
</p>

</div>

<p align="center">
  <img src="docs/images/readme/1.jpg" width="24%" alt="nonebot-plugin-codex screenshot 1">
  <img src="docs/images/readme/2.jpg" width="24%" alt="nonebot-plugin-codex screenshot 2">
  <img src="docs/images/readme/3.jpg" width="24%" alt="nonebot-plugin-codex screenshot 3">
  <img src="docs/images/readme/4.jpg" width="24%" alt="nonebot-plugin-codex screenshot 4">
</p>

## 项目介绍

`nonebot-plugin-codex` 是一个面向 Telegram 场景的 NoneBot 插件，用来把本机 `codex` CLI 暴露为可对话、可续聊、可管理工作目录的聊天式开发助手。

它不是简单地把命令行输出转发到聊天窗口，而是围绕实际使用场景补齐了会话管理与状态管理能力：

- 同一聊天内持续续聊，保留上下文
- 支持 `resume` 与 `exec` 两种运行模式
- 每个聊天独立维护模型、推理强度、权限模式和工作目录
- 可视化浏览目录与历史会话
- 插件自身状态使用 localstore 管理，本地 Codex 历史读取 `~/.codex/*`

如果你已经习惯在本机使用 Codex，又希望通过 Telegram 远程发起编码、排查、审阅或文档整理任务，这个插件就是为这个场景设计的。

## 核心特性

- **聊天即入口**：`/codex` 连接后，普通文本消息可直接续聊当前会话。
- **双模式工作流**：持续对话用 `resume`，一次性任务用 `exec`。
- **细粒度会话隔离**：不同聊天各自持有模型、权限、工作目录与历史绑定。
- **目录浏览能力**：支持在 Telegram 内切换目录、设定 Home、查看隐藏目录。
- **历史会话恢复**：可浏览 native 与 exec 历史，并尽量恢复原始工作目录。
- **兼容迁移**：可以沿用旧配置文件与 Codex 历史目录，减少迁移成本。

## 快速开始

### 1. 准备运行环境

确保满足以下条件：

- Python `3.10+`
- NoneBot `2.4.4+`
- 已安装 `nonebot-adapter-telegram`
- 目标主机上已安装并可直接调用 `codex`

### 2. 安装插件

在 NoneBot 项目根目录中执行其一：

```bash
nb plugin install nonebot-plugin-codex
```

或：

```bash
pip install nonebot-plugin-codex
```

或：

```bash
pdm add nonebot-plugin-codex
```

### 3. 启用插件

在 `pyproject.toml` 中启用：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_codex"]
```

### 4. 写入最小可用配置

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_codex"]

[tool.nonebot.plugin_config]
codex_binary = "codex"
codex_workdir = "/home/yourname"
```

如果你的 `codex` 不在 `PATH` 中，把 `codex_binary` 改成绝对路径即可。

## 使用方式

一个典型工作流通常是这样的：

```text
/codex
/panel
/cd /home/yourname/projects/demo
/mode resume
然后继续直接发送普通文本消息续聊
```

`/codex` 不带参数时会打开一个 Telegram 内的使用引导面板，方便你直接查看当前模式、工作目录、设置摘要，并进入目录浏览、设置面板或历史会话。

`/panel` 和 `/status` 会打开统一的“当前工作台”面板，把模式、模型、推理强度、权限、工作目录、当前会话状态和最近历史摘要放在同一屏里，并提供进入设置、目录、历史、新会话和停止会话的快捷操作。

你也可以直接把首条任务跟在 `/codex` 后面：

```text
/codex 帮我检查当前仓库为什么测试失败
/permission danger
```

你也可以把一次性任务交给 `exec` 模式：

```text
/exec 用三点总结这个仓库 README 还缺什么
```

如果你希望显式打开引导入口，也可以使用：

```text
/help
/start
/panel
```

## 配置说明

完整配置如下，配置名与当前实现保持一致：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_codex"]

[tool.nonebot.plugin_config]
# Codex 可执行文件名或绝对路径，默认直接调用 PATH 中的 `codex`
codex_binary = "codex"

# 默认工作目录；新会话、目录浏览器 Home 入口、相对路径解析都基于它
codex_workdir = "/home/yourname"

# `/stop` 或重置会话时，等待 Codex 子进程退出的超时时间，单位秒
codex_kill_timeout = 5.0

# 运行中在 Telegram 中保留的进度消息条数
codex_progress_history = 6

# 运行失败时最多保留多少条诊断输出
codex_diagnostic_history = 20

# 单条 Telegram 消息的分片长度，过长回复会自动拆分
codex_chunk_size = 3500

# 单条 Codex 协议消息允许的最大字节数
codex_stream_read_limit = 8388608

```

几个最关键的配置项：

- `codex_binary`：如果宿主机不是直接执行 `codex`，改成实际绝对路径。
- `codex_workdir`：默认工作目录，也是 `/cd` 相对路径解析与目录浏览器 Home 的基准。
- `codex_stream_read_limit`：限制单条 Codex 协议帧的最大字节数，不是 Telegram 消息分片长度。
- 其余项分别控制停止超时、进度保留条数、诊断输出条数和 Telegram 分片长度。
- 插件自己的配置数据由 `nonebot-plugin-localstore` 自动管理。
- 模型缓存、Codex CLI 配置和历史会话目录默认读取 `~/.codex/*`，属于插件内部实现路径。

## 命令一览

| 命令 | 说明 |
| --- | --- |
| `/codex [prompt]` | 打开引导面板，或直接附带首条任务连接 Codex |
| `/help` | 打开使用引导面板 |
| `/start` | 打开使用引导面板 |
| `/panel` | 打开统一工作台面板 |
| `/status` | 打开统一工作台面板 |
| `/mode [resume\|exec]` | 查看或切换默认模式 |
| `/exec <prompt>` | 以一次性 `exec` 模式执行任务 |
| `/new` | 新建当前聊天会话 |
| `/stop` | 停止当前聊天中的 Codex |
| `/models` | 查看可用模型列表 |
| `/model [slug]` | 查看或切换当前模型 |
| `/effort [high\|xhigh]` | 查看或切换推理强度 |
| `/permission [safe\|danger]` | 查看或切换权限模式 |
| `/pwd` | 查看当前工作目录和设置 |
| `/cd [path]` | 切换目录或打开目录浏览器 |
| `/home` | 将工作目录重置到 Home |
| `/sessions` | 打开历史会话浏览器 |
| `/compact` | 压缩当前 `resume` 会话上下文 |

## 模式说明

### `resume`

适合需要持续上下文的对话式场景：

- 优先使用 `codex app-server`
- 为同一聊天维持 native thread
- 更适合连续编码、持续追问和多轮调试
- 支持在 Telegram 中用 `/compact` 压缩较早对话上下文

### `exec`

适合一次性任务或脚本式调用：

- 使用 `codex exec --json`
- 支持恢复已有 exec thread
- 恢复失败时会自动新开会话并提示

## 目录与历史会话

- `/panel` 或 `/status` 会打开统一工作台，一屏查看当前设置、工作目录、会话状态和最近历史，并跳转到常用控制面板。
- `/cd` 可打开目录浏览器，逐级进入目录、切换 Home、显示隐藏目录，并把当前浏览目录设置为工作目录。
- `/sessions` 会列出 native 与 exec 历史会话，便于恢复此前任务。
- 历史会话恢复时会尝试切回原始工作目录；如果原目录不存在，会保留当前目录并给出提示。

## 发布说明

仓库已包含基础发布流程：

- `test.yml`：安装依赖并运行测试
- `release.yml`：在推送 `v*` 标签时执行 `pdm publish`、生成两个版本间的结构化发布说明，并上传构建产物

Release 说明会按 tag 区间内的 Conventional Commits 自动分组，例如 `feat`、`fix`、`docs`、`chore` 等，并附上 compare 链接，避免每次手工整理改动列表。

如果你要启用 PyPI Trusted Publishing，请在 PyPI 项目设置中添加以下信息：

- Project name: `nonebot-plugin-codex`
- Owner: `ttiee`
- Repository name: `nonebot-plugin-codex`
- Workflow name: `release.yml`

## 本地开发

```bash
pdm sync -G:all
pdm run pytest
pdm run ruff check .
pdm build
```

## License

本项目使用 [GPL-3.0-or-later](https://github.com/ttiee/nonebot-plugin-codex/blob/main/LICENSE) 许可证。
