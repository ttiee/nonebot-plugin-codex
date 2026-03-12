# Home And Effort Regression Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix `/home` to return to the normalized configured workdir and make effort panel submission accept any reasoning level supported by the selected model.

**Architecture:** Keep both behaviors owned by `CodexBridgeService`. Telegram should call a public service helper for the configured workdir, and effort validation should derive allowed values from model metadata so rendering and submission share one source of truth.

**Tech Stack:** Python, NoneBot plugin service layer, pytest, PDM

---

### Task 1: Lock In The `/home` Regression

**Files:**
- Modify: `tests/test_telegram_handlers.py`
- Modify: `src/nonebot_plugin_codex/telegram.py`
- Modify: `src/nonebot_plugin_codex/service.py`

**Step 1: Write the failing test**

Add a test that uses a real `CodexBridgeService` with:
- `settings.workdir="workspace/default"`
- current chat workdir changed to another absolute path first
- `/home` invoked through `TelegramHandlers`

Assert the resulting message points to `tmp_path / "workspace" / "default"` instead of resolving relative to the current chat workdir.

**Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_telegram_handlers.py::test_handle_home_resolves_relative_configured_workdir -q`

Expected: FAIL because `/home` still passes the raw relative config value.

**Step 3: Write minimal implementation**

- Add a public `configured_workdir()` helper to `CodexBridgeService`.
- Update `/home` in `TelegramHandlers` to use the normalized configured workdir.
- Reuse the same helper anywhere service-owned "home" navigation already exists.

**Step 4: Run test to verify it passes**

Run: `pdm run pytest tests/test_telegram_handlers.py::test_handle_home_resolves_relative_configured_workdir -q`

Expected: PASS

**Step 5: Commit**

```bash
git add docs/plans/2026-03-12-home-effort-regression-design.md \
  docs/plans/2026-03-12-home-effort-regression.md \
  tests/test_telegram_handlers.py \
  src/nonebot_plugin_codex/telegram.py \
  src/nonebot_plugin_codex/service.py
git commit -m "fix: normalize configured home workdir"
```

### Task 2: Lock In Dynamic Effort Validation

**Files:**
- Modify: `tests/test_service.py`
- Modify: `src/nonebot_plugin_codex/service.py`

**Step 1: Write the failing test**

Add a service test that creates model metadata with a model supporting `medium`, opens the effort panel, applies `medium`, and asserts the preference is updated.

**Step 2: Run test to verify it fails**

Run: `pdm run pytest tests/test_service.py::test_apply_effort_setting_panel_accepts_model_supported_medium -q`

Expected: FAIL because `update_reasoning_effort()` still rejects non-`high`/`xhigh` values.

**Step 3: Write minimal implementation**

- Remove the static effort allowlist dependency from `update_reasoning_effort()`.
- Validate the submitted effort against the selected model's `supported_reasoning_levels`.
- Keep the existing missing-model and unsupported-effort error paths.

**Step 4: Run test to verify it passes**

Run: `pdm run pytest tests/test_service.py::test_apply_effort_setting_panel_accepts_model_supported_medium -q`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_service.py src/nonebot_plugin_codex/service.py
git commit -m "fix: align effort validation with model metadata"
```

### Task 3: Run Focused And Full Verification

**Files:**
- Modify: `tests/test_service.py`
- Modify: `tests/test_telegram_handlers.py`
- Modify: `src/nonebot_plugin_codex/service.py`
- Modify: `src/nonebot_plugin_codex/telegram.py`

**Step 1: Run focused regressions**

Run: `pdm run pytest tests/test_service.py tests/test_telegram_handlers.py -q`

Expected: PASS

**Step 2: Run full test suite**

Run: `pdm run pytest -q`

Expected: PASS

**Step 3: Run lint**

Run: `pdm run ruff check .`

Expected: PASS

**Step 4: Review diff for scope**

Run: `git diff -- src/nonebot_plugin_codex/service.py src/nonebot_plugin_codex/telegram.py tests/test_service.py tests/test_telegram_handlers.py`

Expected: Only `/home` normalization, dynamic effort validation, and regression tests are included.

**Step 5: Commit**

```bash
git add src/nonebot_plugin_codex/service.py \
  src/nonebot_plugin_codex/telegram.py \
  tests/test_service.py \
  tests/test_telegram_handlers.py
git commit -m "test: cover home and effort regressions"
```
