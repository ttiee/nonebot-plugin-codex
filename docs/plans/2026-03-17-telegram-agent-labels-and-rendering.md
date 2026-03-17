# Telegram Agent Labels And Rendering Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve Telegram agent panel visibility and render more Markdown block syntax correctly in Telegram HTML output.

**Architecture:** Keep agent identity and Markdown normalization in the existing service and Telegram rendering layers. Only enable labeled agent headers after a subagent appears, then re-render existing main-agent messages with emoji-prefixed titles for clarity. Extend the block renderer to convert headings and thematic breaks before inline formatting runs.

**Tech Stack:** Python 3.10+, NoneBot 2, nonebot-adapter-telegram, pytest

---

### Task 1: Lock agent header behavior with tests

**Files:**
- Modify: `tests/test_telegram_handlers.py`
- Modify: `src/nonebot_plugin_codex/telegram.py`
- Modify: `src/nonebot_plugin_codex/service.py`

- [x] **Step 1: Write the failing test**

Add one test that keeps single-agent progress/stream messages unlabeled and another that verifies multi-agent mode upgrades the main panel to `🧠 主 agent` and gives spawned subagents `🛠️ 子 agent N`.

- [x] **Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_telegram_handlers.py -q`
Expected: FAIL because the handler always prefixes agent labels, even in single-agent mode.

- [x] **Step 3: Write minimal implementation**

Track the last progress text per agent panel, render emoji-prefixed titles only when more than one panel exists, and refresh existing main-agent messages when the first subagent is created.

- [x] **Step 4: Run test to verify it passes**

Run: `pdm run pytest tests/test_telegram_handlers.py -q`
Expected: PASS

### Task 2: Lock Markdown heading and separator rendering

**Files:**
- Modify: `tests/test_telegram_rendering.py`
- Modify: `src/nonebot_plugin_codex/telegram_rendering.py`

- [x] **Step 1: Write the failing test**

Add focused tests for `#`/`##`/`###` headings and `---` thematic breaks.

- [x] **Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_telegram_rendering.py -q`
Expected: FAIL because the current renderer leaves these blocks as plain text.

- [x] **Step 3: Write minimal implementation**

Teach `_render_blocks` to rewrite headings into bold lines and thematic breaks into a visual separator before HTML escaping and inline Markdown conversion.

- [x] **Step 4: Run test to verify it passes**

Run: `pdm run pytest tests/test_telegram_rendering.py -q`
Expected: PASS

### Task 3: Verify integrated behavior

**Files:**
- Create: `docs/maintenance/2026-03-17-telegram-agent-labels-and-rendering.md`

- [x] **Step 1: Update maintenance note**

Capture the display issue, expected behavior, affected files, and verification commands.

- [x] **Step 2: Run targeted verification**

Run:

- `pdm run pytest tests/test_telegram_rendering.py tests/test_telegram_handlers.py -q`
- `pdm run pytest tests/test_service.py -q`

Expected: PASS

- [ ] **Step 3: Run full verification**

Run:

- `pdm run pytest -q`
- `pdm run ruff check .`

Expected: PASS
