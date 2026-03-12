# Repository Guidelines

## Project Scope

`nonebot-plugin-codex` is a NoneBot plugin that exposes local Codex CLI workflows through Telegram. The repository is a Python package using a `src/` layout and PDM for dependency management.

## Repository Layout

- `src/nonebot_plugin_codex/`: plugin source code
- `tests/`: pytest-based automated tests
- `docs/plans/`: design and implementation planning documents
- `docs/maintenance/`: tracked maintenance items and issue-ready notes

## Working Norms

- Keep changes aligned with the current plugin architecture and configuration compatibility.
- Prefer small, reviewable changes with explicit tests for behavior changes.
- Do not silently change documented config semantics; update docs and tests together.
- Preserve backward compatibility for user-facing commands unless the change is explicitly intentional and documented.

## Development Commands

- Install dependencies: `pdm sync -G:all`
- Run tests: `pdm run pytest -q`
- Run focused tests: `pdm run pytest tests/test_service.py tests/test_telegram_handlers.py -q`
- Run lint: `pdm run ruff check .`

Use `pdm run ...` for repository commands so the project environment and `src/` import path are configured correctly.

## Code Change Expectations

- Follow TDD for behavior changes: write or update the failing test first, verify the failure, then implement the minimum fix.
- Reuse existing callback/state patterns before adding new interaction mechanisms.
- Keep repository files ASCII unless an existing file already uses non-ASCII content and it is appropriate to match it.
- Avoid unrelated refactors while fixing a bug or delivering a scoped improvement.

## Issue Expectations

- Every non-trivial change should be traceable to an issue or a documented maintenance note.
- Issue reports should include reproduction steps, expected behavior, actual behavior, and the affected files or commands.
- Use `docs/maintenance/` markdown files as durable issue drafts when preparing GitHub issues from local work.

## Pull Request Expectations

- Link the PR to the relevant issue.
- Summarize user-visible behavior changes and internal refactors separately.
- Include fresh verification evidence, at minimum:
  - `pdm run pytest -q`
  - `pdm run ruff check .`
- Call out any unverified areas or follow-up work explicitly.

## Safety Notes

- Respect persisted compatibility paths such as `data/codex_bridge/preferences.json` and `~/.codex/*` unless the change explicitly updates migration behavior.
- Do not remove or rewrite user-authored documents under `docs/` unless the task requires it.
