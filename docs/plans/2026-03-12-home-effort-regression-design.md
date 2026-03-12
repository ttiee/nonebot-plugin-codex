# Home And Effort Regression Design

## Context

Two regressions were introduced by the recent workdir and settings panel changes:

1. `/home` still passes the raw `settings.workdir` string into `update_workdir()`. When the configured value is relative, `update_workdir()` resolves it against the current chat workdir instead of the configured default directory.
2. The effort settings panel renders every model-declared reasoning level, but `update_reasoning_effort()` still rejects anything outside a hard-coded `high` / `xhigh` allowlist.

Both problems are consistency bugs. The user-visible entry points already imply a single source of truth, but the code currently applies different rules at render time and at submit time.

## Options

### Option 1: Localized Fixes

- Patch `telegram.handle_home()` to normalize `settings.workdir` before calling `update_workdir()`.
- Extend the hard-coded effort allowlist to include `medium`.

This is small, but it keeps the code fragile. Any future caller can repeat the same `/home` bug, and the effort logic would still require code changes whenever Codex adds a new reasoning level.

### Option 2: Centralize Both Behaviors

- Expose a public `configured_workdir()` helper from `CodexBridgeService` and route all "go home" flows through it.
- Remove the static effort allowlist and validate submitted effort values against the currently selected model's declared capabilities.

This keeps the behavior aligned with existing service semantics and future-proofs the effort panel for new model metadata.

## Decision

Use Option 2.

## Design

### Configured Workdir

- Promote the existing private normalization logic into a public service method.
- Keep the implementation in `CodexBridgeService`, because the configured workdir semantics belong to service state rather than Telegram transport code.
- Update both the directory browser "home" path and Telegram `/home` command to use the same public method.

### Effort Validation

- Treat model metadata as the source of truth for allowed effort values.
- `render_setting_panel("effort")` already reads model capabilities; `update_reasoning_effort()` should validate against the same model metadata instead of a static constant.
- Preserve existing error behavior when the current model is missing or when the submitted effort is unsupported for that model.

### Testing

- Add a Telegram handler regression test where `codex_workdir` is relative and the chat has moved to another directory; `/home` must resolve back to the configured directory.
- Add a service test showing that the effort panel can successfully apply `medium` when the selected model declares it.
- Keep the tests narrow so they prove the regression before the implementation change.
