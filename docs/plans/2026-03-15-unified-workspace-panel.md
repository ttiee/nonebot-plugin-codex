# Unified Workspace Panel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a dedicated Telegram workspace panel for `/panel` and `/status` that centralizes the current chat state and exposes one-tap entry to the existing runtime controls.

**Architecture:** Reuse the existing Telegram panel architecture already used by onboarding, settings, directory browsing, and history browsing. Add one new workspace panel state machine in the service layer, wire two new commands and a callback namespace in the Telegram layer, and keep detailed selection delegated to the already-existing panels.

**Tech Stack:** Python 3.10+, NoneBot 2, nonebot-adapter-telegram, pytest, Pydantic/dataclasses

---

### Task 1: Lock command metadata for `/panel` and `/status`

**Files:**
- Modify: `tests/test_telegram_commands.py`
- Modify: `src/nonebot_plugin_codex/telegram_commands.py`

**Step 1: Write the failing test**

Add assertions that:

- `panel` and `status` appear in `TELEGRAM_COMMAND_SPECS`
- `build_telegram_commands()` includes both commands with Chinese descriptions
- `build_plugin_usage()` includes `/panel` and `/status`

**Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_telegram_commands.py -q`
Expected: FAIL because the command metadata does not include `panel` or `status`

**Step 3: Write minimal implementation**

Update `src/nonebot_plugin_codex/telegram_commands.py` to add:

- `panel`: "打开当前工作台"
- `status`: "打开当前工作台"

Keep metadata centralized in the existing tuple.

**Step 4: Run test to verify it passes**

Run: `pdm run pytest tests/test_telegram_commands.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_telegram_commands.py src/nonebot_plugin_codex/telegram_commands.py
git commit -m "✅ test(telegram): 补充工作台命令元数据断言"
```

### Task 2: Define workspace handler expectations first

**Files:**
- Modify: `tests/test_telegram_handlers.py`

**Step 1: Write the failing test**

Add tests that:

- `handle_panel()` opens the workspace panel
- `handle_status()` opens the same workspace panel
- the sent payload includes inline keyboard markup

Extend `FakeService` only as needed for new workspace methods and state.

**Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_telegram_handlers.py -q`
Expected: FAIL because `TelegramHandlers` has no workspace-panel handlers or service calls

**Step 3: Write minimal implementation**

Update only the test scaffolding needed to support the new expectations after production code is added.

**Step 4: Run test to verify it still fails for the right reason**

Run: `pdm run pytest tests/test_telegram_handlers.py -q`
Expected: FAIL due to missing production behavior, not broken test scaffolding

**Step 5: Commit**

```bash
git add tests/test_telegram_handlers.py
git commit -m "✅ test(telegram): 定义工作台入口行为"
```

### Task 3: Add workspace panel state and rendering in the service layer

**Files:**
- Modify: `src/nonebot_plugin_codex/service.py`
- Modify: `tests/test_service.py`

**Step 1: Write the failing test**

Add focused service tests that cover:

- opening and rendering the workspace panel
- summary text for mode, model, effort, permission, workdir, and session state
- recent history summary limited to the newest one or two entries
- refresh navigation returning a new panel version

**Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_service.py -q`
Expected: FAIL because workspace panel state/rendering helpers do not exist

**Step 3: Write minimal implementation**

In `src/nonebot_plugin_codex/service.py`, add:

- `WORKSPACE_CALLBACK_PREFIX`
- `WORKSPACE_STALE_MESSAGE`
- `WorkspacePanelState`
- `encode_workspace_callback(...)`
- `decode_workspace_callback(...)`
- `open_workspace_panel(...)`
- `get_workspace_panel(...)`
- `remember_workspace_panel_message(...)`
- `close_workspace_panel(...)`
- `navigate_workspace_panel(...)`
- `render_workspace_panel(...)`

Reuse existing preference, session, and history data. Keep the panel compact and delegate deep actions elsewhere.

**Step 4: Run test to verify it passes**

Run: `pdm run pytest tests/test_service.py -q`
Expected: PASS for the new workspace-panel coverage

**Step 5: Commit**

```bash
git add src/nonebot_plugin_codex/service.py tests/test_service.py
git commit -m "✨ feat(service): 添加工作台面板状态与渲染"
```

### Task 4: Wire workspace handlers and callback routing

**Files:**
- Modify: `src/nonebot_plugin_codex/telegram.py`
- Modify: `src/nonebot_plugin_codex/__init__.py`
- Modify: `tests/test_telegram_handlers.py`

**Step 1: Write the failing test**

Add or extend tests for workspace callback actions:

- `mode`, `model`, `effort`, `permission` open the corresponding setting panels
- `browse` opens the directory browser
- `history` opens the history browser
- `new` resets chat and returns the expected notice
- `stop` disconnects the current chat
- `refresh` re-renders the workspace panel
- `close` closes the panel message
- stale callback payloads return the workspace stale message

**Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_telegram_handlers.py -q`
Expected: FAIL because workspace callbacks are not registered or handled

**Step 3: Write minimal implementation**

Update `src/nonebot_plugin_codex/telegram.py` and `src/nonebot_plugin_codex/__init__.py` to:

- register `/panel` and `/status`
- add workspace callback detection and handling
- delegate to existing sub-panels and browsers
- support direct `new`, `stop`, `refresh`, and `close` actions

Do not change existing onboarding behavior.

**Step 4: Run test to verify it passes**

Run: `pdm run pytest tests/test_telegram_handlers.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/nonebot_plugin_codex/telegram.py src/nonebot_plugin_codex/__init__.py tests/test_telegram_handlers.py
git commit -m "✨ feat(telegram): 接入统一工作台面板"
```

### Task 5: Update README and run final verification

**Files:**
- Modify: `README.md`
- Modify: `tests/test_telegram_commands.py`
- Modify: `tests/test_telegram_handlers.py`
- Modify: `tests/test_service.py`

**Step 1: Tighten any missing assertions**

Ensure command usage and handler tests still cover the documented `/panel` and `/status` behavior.

**Step 2: Run targeted tests**

Run:

- `pdm run pytest tests/test_telegram_commands.py -q`
- `pdm run pytest tests/test_service.py -q`
- `pdm run pytest tests/test_telegram_handlers.py -q`

Expected: PASS before docs update

**Step 3: Write minimal documentation**

Update `README.md` command and workflow sections to mention:

- `/panel`
- `/status`
- the unified workspace panel as the day-to-day control surface

Keep docs concise and aligned with the issue scope.

**Step 4: Run full verification**

Run:

- `pdm run pytest -q`
- `pdm run ruff check .`

Expected: PASS

**Step 5: Commit**

```bash
git add README.md tests/test_telegram_commands.py tests/test_service.py tests/test_telegram_handlers.py
git commit -m "📝 docs(readme): 补充统一工作台面板说明"
```

Plan complete and saved to `docs/plans/2026-03-15-unified-workspace-panel.md`.

Two execution options:

1. Subagent-Driven (this session) - I dispatch fresh subagent per task, review between tasks, fast iteration
2. Parallel Session (separate) - Open new session with executing-plans, batch execution with checkpoints

The user already asked to continue to implementation and final PR, so execute in this session.
