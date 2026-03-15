# Telegram HTML Rendering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Route every outbound Telegram text message through a safe Markdown-to-HTML conversion layer and fall back to plain text when Telegram rejects the rendered entities.

**Architecture:** Keep service-layer text generation unchanged. Add a small renderer module that converts a limited Markdown subset to Telegram HTML, then have `TelegramHandlers` call that renderer before all text send/edit operations. Preserve a final plain-text retry path for Telegram entity errors.

**Tech Stack:** Python 3.11+, NoneBot, nonebot-adapter-telegram, pytest, ruff

---

### Task 1: Add renderer tests

**Files:**
- Create: `tests/test_telegram_rendering.py`

**Step 1: Write the failing test**

Add tests for:
- bold conversion
- italic conversion
- inline code conversion
- fenced code block conversion
- link conversion
- malformed markdown remaining escaped text
- underscores and file paths remaining safe

**Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_telegram_rendering.py -q`
Expected: FAIL because the renderer module does not exist yet.

**Step 3: Write minimal implementation**

Create a renderer module that exposes a function returning rendered HTML text and parse mode metadata.

**Step 4: Run test to verify it passes**

Run: `pdm run pytest tests/test_telegram_rendering.py -q`
Expected: PASS

### Task 2: Update Telegram handler tests

**Files:**
- Modify: `tests/test_telegram_handlers.py`

**Step 1: Write the failing test**

Adjust handler tests to assert:
- send/edit helpers use `parse_mode="HTML"`
- outgoing text is rendered before sending
- HTML parsing failures retry once without parse mode

**Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_telegram_handlers.py -q`
Expected: FAIL because handlers still use Markdown behavior.

**Step 3: Write minimal implementation**

Wire the renderer into handler send/edit helpers and keep a plain-text fallback on parse failures.

**Step 4: Run test to verify it passes**

Run: `pdm run pytest tests/test_telegram_handlers.py -q`
Expected: PASS

### Task 3: Verify the full integration

**Files:**
- Modify: `src/nonebot_plugin_codex/telegram.py`
- Create: `src/nonebot_plugin_codex/telegram_rendering.py`
- Test: `tests/test_telegram_rendering.py`
- Test: `tests/test_telegram_handlers.py`

**Step 1: Run the focused tests**

Run: `pdm run pytest tests/test_telegram_rendering.py tests/test_telegram_handlers.py -q`
Expected: PASS

**Step 2: Run full verification**

Run: `pdm run pytest -q`
Expected: PASS

Run: `pdm run ruff check .`
Expected: PASS

**Step 3: Build distributable**

Run: `pdm build`
Expected: wheel created under `dist/`
