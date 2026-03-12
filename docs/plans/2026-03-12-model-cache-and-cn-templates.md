# Model Cache Fallback And Chinese Templates Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the model-cache-dependent command failure path and localize the repository's GitHub issue and PR templates into Chinese.

**Architecture:** Remove the root-cause dependency between generic preference creation and model metadata by making default preferences derive from Codex config plus safe fallback values. Keep model-specific commands dependent on explicit model metadata, and update the GitHub-facing templates in place without changing their structural purpose.

**Tech Stack:** Python 3.10+, NoneBot2, nonebot-adapter-telegram, pytest, GitHub issue/PR templates

---

### Task 1: Add Failing Tests For Model Cache Fallback

**Files:**
- Modify: `tests/test_service.py`
- Modify: `tests/test_telegram_handlers.py`

**Step 1: Write the failing tests**

Add tests asserting:
- `get_preferences()` works without a model cache when `config.toml` provides model defaults
- `/pwd` works without a model cache
- `/codex` without a prompt works without a model cache

**Step 2: Run the focused tests to verify failure**

Run: `pdm run pytest tests/test_service.py tests/test_telegram_handlers.py -q`
Expected: FAIL on the new no-model-cache cases

### Task 2: Implement The Root-Cause Fix

**Files:**
- Modify: `src/nonebot_plugin_codex/service.py`

**Step 1: Implement minimal fallback logic**

Change default preference construction so it:
- prefers `codex_config_path`
- uses model cache normalization only when metadata is available
- falls back to internal defaults when both model cache and config are absent

**Step 2: Re-run the focused tests**

Run: `pdm run pytest tests/test_service.py tests/test_telegram_handlers.py -q`
Expected: PASS for the new fallback tests

### Task 3: Add Failing Checks For Chinese Templates

**Files:**
- Modify: `tests/test_plugin_meta.py`

**Step 1: Add tests or file-content assertions for template wording**

Assert the issue and PR templates contain Chinese labels/headings expected by the new repository standard.

**Step 2: Run the focused tests to verify failure**

Run: `pdm run pytest tests/test_plugin_meta.py -q`
Expected: FAIL because templates are still English

### Task 4: Localize GitHub Templates

**Files:**
- Modify: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Modify: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Modify: `.github/ISSUE_TEMPLATE/config.yml`
- Modify: `.github/pull_request_template.md`

**Step 1: Translate the templates to Chinese**

Keep field structure and intent, but localize headings, descriptions, placeholders, and helper text.

**Step 2: Re-run the focused tests**

Run: `pdm run pytest tests/test_plugin_meta.py -q`
Expected: PASS

### Task 5: Full Verification

**Files:**
- Modify: any touched files above as needed

**Step 1: Run the full test suite**

Run: `pdm run pytest -q`
Expected: all tests pass

**Step 2: Run lint**

Run: `pdm run ruff check .`
Expected: all checks pass

**Step 3: Update GitHub artifacts if needed**

If the template language change should be reflected in the existing issue/PR descriptions, update them after code verification.
