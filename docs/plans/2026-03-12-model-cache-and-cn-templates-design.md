# Model Cache Fallback And Chinese Templates Design

## Background

The repository still has one confirmed runtime defect: if the configured model cache file is missing, `get_preferences()` currently tries to build default preferences via `load_models()`, which makes non-model commands fail early. At the same time, the repository's new GitHub issue templates and PR template are still written in English, while the project's user-facing language and maintainer preference are Chinese.

## Goals

- Fix the remaining bug where non-model commands fail when the model cache file is missing.
- Keep model-specific commands honest: they may still require model metadata, but generic commands should not.
- Localize the GitHub issue templates into Chinese.
- Localize the PR template into Chinese as well for consistency.

## Non-Goals

- Do not redesign the Telegram command flow again.
- Do not add external configuration discovery beyond the current Codex config and existing settings.
- Do not change issue labels or broader repo governance.

## Root Cause

`CodexBridgeService.get_preferences()` lazily creates default preferences through `_default_preferences()`. That method currently loads the model cache first, even though many call sites only need a summary of current settings or the current workdir. As a result, commands like `/pwd`, `/codex` without a prompt, and `/new` can fail with `FileNotFoundError` before the user reaches any model-specific operation.

## Approach Options

### Option 1: Catch FileNotFoundError in handlers

Wrap more handlers in `FileNotFoundError` handling and keep the service logic unchanged.

- Pros: very small code diff
- Cons: symptom fix only; the service still couples generic preference creation to model metadata

### Option 2: Decouple default preferences from model cache

Make `_default_preferences()` prefer `~/.codex/config.toml` values first, then safe fallback defaults, and only consult the model cache when available for normalization.

- Pros: fixes the root cause at the service layer, keeps generic commands usable, preserves existing behavior when metadata exists
- Cons: needs careful tests so model-specific commands still behave intentionally

### Option 3: Allow missing model in preferences

Let preferences hold `model=None` and push the requirement down to execution-time paths only.

- Pros: semantically explicit
- Cons: much wider type and formatting churn than necessary

## Recommended Design

Use Option 2.

### Service Behavior

- `_default_preferences()` should stop hard-requiring `load_models()`.
- It should:
  - read `codex_config_path` first
  - if the model cache is available, preserve the current normalization behavior
  - if the model cache is missing or invalid, fall back to the configured model/effort from `config.toml`
  - if even that is missing, use a small internal default such as `gpt-5` and `high`

This keeps generic preference creation stable while avoiding a large `None`-propagation refactor.

### Command Expectations

- These should work even if the model cache file is absent:
  - `/pwd`
  - `/codex` without prompt
  - `/new`
- These may still require model metadata and can continue to error clearly if it is missing:
  - `/models`
  - `/model`
  - `/effort`
  - model and effort selector panels

### Template Localization

Translate the current GitHub-facing templates to Chinese:

- `.github/ISSUE_TEMPLATE/bug_report.yml`
- `.github/ISSUE_TEMPLATE/feature_request.yml`
- `.github/ISSUE_TEMPLATE/config.yml`
- `.github/pull_request_template.md`

The structure should remain the same; only the repository-facing language and helper copy need localization.

### Testing

Add failing tests first for:

- service default preferences without a model cache
- handler paths that should stay usable without a model cache
- presence of Chinese wording in the issue and PR templates

## Risks And Mitigations

- Risk: fallback defaults may diverge from an individual user's actual Codex defaults.
  Mitigation: prefer `codex_config_path` values before any hardcoded fallback.

- Risk: a broad fallback could accidentally hide model-metadata errors everywhere.
  Mitigation: keep `load_models()`-dependent commands unchanged; only decouple generic preference creation.
