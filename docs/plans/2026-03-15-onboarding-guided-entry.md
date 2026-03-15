# Onboarding Guided Entry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a shared Telegram onboarding panel for `/codex`, `/help`, and `/start` that shows current state and links users into the existing high-frequency workflows.

**Architecture:** Reuse the existing Telegram panel model used by directory, history, and settings flows. Add one lightweight onboarding panel state machine in the service layer, route three commands to the same rendering path, and keep button actions delegated to the already-existing browser and session flows.

**Tech Stack:** Python 3.10+, NoneBot 2, nonebot-adapter-telegram, pytest, Pydantic dataclasses

---

### Task 1: Lock onboarding command metadata with tests

**Files:**
- Modify: `tests/test_telegram_commands.py`
- Modify: `src/nonebot_plugin_codex/telegram_commands.py`

**Step 1: Write the failing test**

Add assertions that:

- `help` and `start` appear in `TELEGRAM_COMMAND_SPECS`
- `build_telegram_commands()` includes both commands with Chinese descriptions
- `build_plugin_usage()` includes `/help` and `/start`

**Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_telegram_commands.py -q`
Expected: FAIL because the command metadata does not include `help` or `start`

**Step 3: Write minimal implementation**

Update `src/nonebot_plugin_codex/telegram_commands.py` to add:

- `help`: "打开使用引导面板"
- `start`: "打开使用引导面板"

Keep metadata centralized in the existing tuple.

**Step 4: Run test to verify it passes**

Run: `pdm run pytest tests/test_telegram_commands.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_telegram_commands.py src/nonebot_plugin_codex/telegram_commands.py
git commit -m "test: cover onboarding command metadata"
```

### Task 2: Lock `/codex` no-argument onboarding behavior in handler tests

**Files:**
- Modify: `tests/test_telegram_handlers.py`

**Step 1: Write the failing test**

Add tests that:

- `/codex` without a prompt sends an onboarding panel instead of plain status-only text
- the sent payload includes inline keyboard markup
- `/help` and `/start` call the same onboarding panel flow

Extend `FakeService` only as needed for new onboarding methods and data.

**Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_telegram_handlers.py -q`
Expected: FAIL because `TelegramHandlers` has no onboarding panel behavior or `/help` and `/start` handlers

**Step 3: Write minimal implementation**

Implement only enough test scaffolding to support the new expectations after production code is added.

**Step 4: Run test to verify it still fails for the right reason**

Run: `pdm run pytest tests/test_telegram_handlers.py -q`
Expected: FAIL due to missing production methods, not broken test setup

**Step 5: Commit**

```bash
git add tests/test_telegram_handlers.py
git commit -m "test: define onboarding handler expectations"
```

### Task 3: Add onboarding panel state and rendering in service layer

**Files:**
- Modify: `src/nonebot_plugin_codex/service.py`
- Test: `tests/test_telegram_handlers.py`

**Step 1: Write the failing test**

Add focused handler tests that depend on service capabilities:

- onboarding panel can be opened and remembered
- callback payloads can be dispatched for supported actions
- stale callback payloads surface the onboarding stale message

**Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_telegram_handlers.py -q`
Expected: FAIL because onboarding callback prefix/state/rendering helpers do not exist

**Step 3: Write minimal implementation**

In `src/nonebot_plugin_codex/service.py`, add:

- `ONBOARDING_CALLBACK_PREFIX`
- `ONBOARDING_STALE_MESSAGE`
- `OnboardingPanelState`
- `encode_onboarding_callback(...)`
- `decode_onboarding_callback(...)`
- `open_onboarding_panel(...)`
- `get_onboarding_panel(...)`
- `remember_onboarding_panel_message(...)`
- `close_onboarding_panel(...)`
- `render_onboarding_panel(...)`

Keep text generation compact and reuse existing preference/session accessors.

**Step 4: Run test to verify it passes**

Run: `pdm run pytest tests/test_telegram_handlers.py -q`
Expected: PASS for onboarding state/rendering expectations

**Step 5: Commit**

```bash
git add src/nonebot_plugin_codex/service.py tests/test_telegram_handlers.py
git commit -m "feat: add onboarding panel state and rendering"
```

### Task 4: Wire onboarding handlers and callback routing

**Files:**
- Modify: `src/nonebot_plugin_codex/telegram.py`
- Modify: `src/nonebot_plugin_codex/__init__.py`
- Test: `tests/test_telegram_handlers.py`

**Step 1: Write the failing test**

Add or extend tests for:

- `handle_help()` opens onboarding panel
- `handle_start()` opens onboarding panel
- onboarding callback actions:
  - `browse` opens directory browser
  - `history` opens history browser
  - `settings` opens mode/settings panel entry
  - `new` resets chat and returns the expected notice
  - `close` closes the panel message

**Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_telegram_handlers.py -q`
Expected: FAIL because handlers and callback routing are missing

**Step 3: Write minimal implementation**

Update `src/nonebot_plugin_codex/telegram.py` and `src/nonebot_plugin_codex/__init__.py` to:

- register `/help` and `/start`
- route `/codex` without a prompt to the onboarding panel
- add onboarding callback detection and handling
- delegate actions to existing send/reset flows

Do not alter `/codex <prompt>` execution behavior.

**Step 4: Run test to verify it passes**

Run: `pdm run pytest tests/test_telegram_handlers.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/nonebot_plugin_codex/telegram.py src/nonebot_plugin_codex/__init__.py tests/test_telegram_handlers.py
git commit -m "feat: wire telegram onboarding entry panel"
```

### Task 5: Update README and final verification

**Files:**
- Modify: `README.md`
- Modify: `tests/test_telegram_commands.py`
- Modify: `tests/test_telegram_handlers.py`

**Step 1: Write the failing test**

If needed, tighten command usage assertions so README-facing command metadata stays aligned with `/help` and `/start`.

**Step 2: Run targeted tests**

Run:

- `pdm run pytest tests/test_telegram_commands.py -q`
- `pdm run pytest tests/test_telegram_handlers.py -q`

Expected: PASS before docs update

**Step 3: Write minimal implementation**

Update `README.md` command and usage sections to mention:

- `/help`
- `/start`
- `/codex` as the primary onboarding entry without a prompt

Keep the docs concise.

**Step 4: Run full verification**

Run:

- `pdm run pytest -q`
- `pdm run ruff check .`

Expected: PASS

**Step 5: Commit**

```bash
git add README.md tests/test_telegram_commands.py tests/test_telegram_handlers.py
git commit -m "docs: document telegram onboarding entry points"
```

Plan complete and saved to `docs/plans/2026-03-15-onboarding-guided-entry.md`.

Two execution options:

1. Subagent-Driven (this session) - I dispatch fresh subagent per task, review between tasks, fast iteration
2. Parallel Session (separate) - Open new session with executing-plans, batch execution with checkpoints

The user already asked to continue to implementation and final PR, so execute in this session.
