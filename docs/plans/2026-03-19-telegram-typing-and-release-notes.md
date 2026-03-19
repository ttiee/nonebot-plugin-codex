# Telegram Typing And Release Notes Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Telegram typing feedback during long-running Codex requests and harden release note generation for GitHub releases.

**Architecture:** Keep typing feedback inside the Telegram handler lifecycle so it is scoped to prompt execution and isolated from message rendering. Extend the release notes script with stronger commit parsing and rendering helpers while preserving the existing CLI surface used by the release workflow.

**Tech Stack:** Python 3.10+, NoneBot 2, nonebot-adapter-telegram, pytest

---

### Task 1: Add Telegram typing heartbeat coverage

**Files:**
- Modify: `tests/test_telegram_handlers.py`
- Modify: `src/nonebot_plugin_codex/telegram.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_execute_prompt_sends_typing_actions_until_completion() -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_telegram_handlers.py::test_execute_prompt_sends_typing_actions_until_completion -q`
Expected: FAIL because TelegramHandlers does not emit `send_chat_action`.

- [ ] **Step 3: Write minimal implementation**

```python
async def send_typing_action(...): ...
async def typing_heartbeat(...): ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pdm run pytest tests/test_telegram_handlers.py::test_execute_prompt_sends_typing_actions_until_completion -q`
Expected: PASS

### Task 2: Harden release note parsing and rendering

**Files:**
- Modify: `tests/test_release_notes.py`
- Modify: `tools/release_notes.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_parse_commit_subject_supports_breaking_changes() -> None:
    ...

def test_render_release_notes_adds_links_and_breaking_changes() -> None:
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pdm run pytest tests/test_release_notes.py -q`
Expected: FAIL because the script does not expose the richer parsing/rendering behavior yet.

- [ ] **Step 3: Write minimal implementation**

```python
def parse_commit_subject(...): ...
def render_release_notes(...): ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pdm run pytest tests/test_release_notes.py -q`
Expected: PASS

### Task 3: Verify integrated behavior

**Files:**
- Modify: `src/nonebot_plugin_codex/telegram.py`
- Modify: `tools/release_notes.py`
- Test: `tests/test_telegram_handlers.py`
- Test: `tests/test_release_notes.py`

- [ ] **Step 1: Run targeted regression suite**

Run: `pdm run pytest tests/test_telegram_handlers.py tests/test_release_notes.py -q`
Expected: PASS

- [ ] **Step 2: Run repository verification**

Run: `pdm run pytest -q`
Expected: PASS

- [ ] **Step 3: Run lint**

Run: `pdm run ruff check .`
Expected: PASS
