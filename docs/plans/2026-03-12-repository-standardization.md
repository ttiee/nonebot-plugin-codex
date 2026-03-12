# Repository Standardization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Standardize repository collaboration flow, file a tracked maintenance issue, fix `codex_workdir`, and convert selector commands to button-driven Telegram panels with regression tests.

**Architecture:** Reuse the existing Telegram callback/browser architecture already used by directory and history browsing. Keep text commands backward-compatible while adding button panels and make `CodexBridgeSettings.workdir` the single configured home/default path used across service and handler flows.

**Tech Stack:** Python 3.10+, NoneBot2, nonebot-adapter-telegram, pytest, GitHub CLI

---

### Task 1: Add Repository Collaboration Files

**Files:**
- Create: `AGENTS.md`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/pull_request_template.md`

**Step 1: Add the repository-level guidance files**

Write concise repository instructions covering structure, test/lint commands, issue/PR expectations, and change safety.

**Step 2: Review templates for repository fit**

Check that templates reference the actual commands and project structure in this repo.

**Step 3: Verify the files exist and are readable**

Run: `rg --files AGENTS.md .github`
Expected: new repository guidance and GitHub template files are listed

### Task 2: Capture Backlog And Open GitHub Issue

**Files:**
- Create: `docs/maintenance/2026-03-12-repository-follow-ups.md`

**Step 1: Write the backlog markdown**

Capture the confirmed bugs and UX improvements in issue-ready wording.

**Step 2: Attempt GitHub issue creation**

Run: `gh issue create --title "<title>" --body-file docs/maintenance/2026-03-12-repository-follow-ups.md`
Expected: returns an issue URL

**Step 3: If creation fails, record the blocker**

Do not drop the markdown file; use it as the fallback deliverable.

### Task 3: Write Failing Tests For `codex_workdir`

**Files:**
- Modify: `tests/test_service.py`
- Modify: `tests/test_telegram_handlers.py`

**Step 1: Add tests for configured workdir defaults**

Add tests asserting:
- default preferences use `CodexBridgeSettings.workdir`
- directory browser `home` action uses configured workdir
- `/home` uses configured workdir rather than OS home

**Step 2: Run targeted tests and confirm failure**

Run: `pdm run pytest tests/test_service.py tests/test_telegram_handlers.py -q`
Expected: new tests fail because current code still uses `Path.home()`

### Task 4: Implement `codex_workdir` Runtime Fix

**Files:**
- Modify: `src/nonebot_plugin_codex/service.py`
- Modify: `src/nonebot_plugin_codex/telegram.py`

**Step 1: Replace hard-coded `Path.home()` defaults with configured workdir**

Keep stored per-chat overrides intact; only change defaults and "home" semantics.

**Step 2: Re-run the targeted tests**

Run: `pdm run pytest tests/test_service.py tests/test_telegram_handlers.py -q`
Expected: the new workdir tests pass

### Task 5: Write Failing Tests For Button Panels

**Files:**
- Modify: `tests/test_service.py`
- Modify: `tests/test_telegram_handlers.py`

**Step 1: Add service/handler tests for new selector panels**

Cover:
- panel rendering for mode/model/effort/permission
- callback handling updates the right preference
- legacy text arguments still work

**Step 2: Run focused tests and confirm failure**

Run: `pdm run pytest tests/test_service.py tests/test_telegram_handlers.py -q`
Expected: failures because selector panel state and callbacks do not exist yet

### Task 6: Implement Button-Driven Selector Panels

**Files:**
- Modify: `src/nonebot_plugin_codex/service.py`
- Modify: `src/nonebot_plugin_codex/telegram.py`
- Modify: `src/nonebot_plugin_codex/__init__.py`

**Step 1: Add callback encoding/state/rendering for selector panels**

Follow the same general pattern as directory/history browsers.

**Step 2: Update handlers to open panels when no argument is supplied**

Keep argument-based command handling intact for compatibility.

**Step 3: Add callback routing for selector interactions**

Ensure stale-panel handling mirrors existing callback flows.

**Step 4: Re-run focused tests**

Run: `pdm run pytest tests/test_service.py tests/test_telegram_handlers.py -q`
Expected: selector panel tests pass

### Task 7: Full Verification And GitHub PR

**Files:**
- Modify: any files touched above as needed

**Step 1: Run full verification**

Run: `pdm run pytest -q`
Expected: all tests pass

Run: `pdm run ruff check .`
Expected: all checks pass

**Step 2: Review diff and create a branch if needed**

Ensure the issue reference appears in commit/PR metadata.

**Step 3: Create PR linked to the issue**

Run: `gh pr create --fill --body-file <prepared pr body file>`
Expected: returns a PR URL linked to the created issue
