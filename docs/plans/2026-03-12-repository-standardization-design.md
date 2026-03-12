# Repository Standardization Design

## Background

This repository already has working code and a basic test suite, but it lacks repository-level contribution guidance and reusable GitHub issue/PR templates. The current Telegram UX also mixes button-driven flows (`/cd`, `/sessions`) with manual argument entry (`/mode`, `/model`, `/effort`, `/permission`), and the documented `codex_workdir` setting does not actually drive runtime defaults.

## Goals

- Add repository-level collaboration guidance with a focused `AGENTS.md`.
- Add GitHub issue and PR templates so maintenance work is repeatable and reviewable.
- Write a tracked markdown backlog item for the currently identified problems, and open a GitHub issue from it if the CLI environment allows.
- Fix `codex_workdir` so documented behavior matches runtime behavior.
- Convert `/mode`, `/model`, `/effort`, and `/permission` from manual-argument commands into button-driven panels, consistent with the existing directory/session browsers.
- Add regression tests that lock in the new behavior.

## Non-Goals

- No broad redesign of the plugin command set beyond the four selection-heavy commands above.
- No new external dependencies.
- No addition of broader community docs such as `CONTRIBUTING.md` in this pass.

## Approach Options

### Option 1: Minimal fixes only

Add the missing docs, fix `codex_workdir`, and leave the command UX unchanged.

- Pros: smallest diff
- Cons: leaves obvious UX inconsistency in place

### Option 2: Standardize workflow and command selection UX

Add repository/process docs, file the issue, fix `codex_workdir`, and convert the four selector commands to button panels built on the existing callback pattern.

- Pros: matches the user's stated goal, keeps architecture consistent, and improves both maintainer workflow and Telegram usability
- Cons: touches both docs and interaction code in one change set

### Option 3: Full maintainer-doc expansion

Do Option 2 plus add `CONTRIBUTING.md`, labels guidance, and a broader governance layer.

- Pros: more complete project scaffolding
- Cons: wider scope than necessary for the current repository size

## Recommended Design

Use Option 2.

### Repository Guidance

Add a top-level `AGENTS.md` aimed at repository contributors and AI agents. It should define:

- project purpose and stack
- where code lives
- required verification commands
- expectations for tests, issue references, and PR descriptions
- guardrails around touching user data/config-compatible paths

### GitHub Templates

Add:

- `.github/ISSUE_TEMPLATE/bug_report.yml`
- `.github/ISSUE_TEMPLATE/feature_request.yml`
- `.github/ISSUE_TEMPLATE/config.yml`
- `.github/pull_request_template.md`

The templates should bias toward reproducibility, expected/actual behavior, verification evidence, and linked issues.

### Backlog And Issue Workflow

Create a markdown file under `docs/` that captures the identified bugs and improvements in repository language. Use that as the source of truth for a GitHub issue body and then create the issue with `gh issue create`.

### `codex_workdir` Fix

The service currently defaults to `Path.home()` in places where the documented configured workdir should be used. The fix is to make the configured `CodexBridgeSettings.workdir` the single default "workspace home" used by:

- new chat preferences
- `/home`
- directory browser `Home`
- any fallback that currently assumes the OS home directory

This should remain compatible with explicit per-chat overrides saved in preferences.

### Button Panels For Selection Commands

Reuse the existing callback-driven browser pattern rather than inventing a second interaction system.

Add a lightweight settings browser state that can render and handle button panels for:

- mode
- model
- effort
- permission

The panel should show current values and let the user change them by tapping buttons. Existing text-argument usage should continue to work for backward compatibility.

### Testing Strategy

Use TDD:

- write failing tests for `codex_workdir` default/home behavior
- write failing tests for the new button-panel rendering and callback handling
- then implement the minimum service and handler changes

Tests should cover both service-level behavior and Telegram handler-level interaction where appropriate.

## Risks And Mitigations

- Risk: callback state becomes more fragmented.
  Mitigation: follow the existing browser/history callback structure and naming conventions.

- Risk: fixing `codex_workdir` breaks persisted preference behavior.
  Mitigation: only use configured workdir for defaults/fallbacks, not to overwrite explicit stored chat preferences.

- Risk: issue/PR automation may fail due to repo permissions or branch state.
  Mitigation: keep the markdown source file regardless of CLI outcome and report any GitHub-side blocker explicitly.
