# Repository Follow-Ups

## Summary

The repository has a confirmed configuration bug around `codex_workdir`, several selector commands that still rely on manual argument entry instead of button-driven Telegram UX, and missing repository-level collaboration templates.

## Confirmed Problems

### 1. `codex_workdir` does not actually drive runtime defaults

The README documents `codex_workdir` as:

- the default workdir
- the base for relative `/cd`
- the Home target in the directory browser

Current runtime behavior does not match that contract:

- default chat preferences fall back to the OS home directory
- `/home` resets to the OS home directory
- directory browser `Home` jumps to the OS home directory

Affected files:

- `src/nonebot_plugin_codex/service.py`
- `src/nonebot_plugin_codex/telegram.py`
- `README.md`

### 2. Selection-heavy commands still require manual text input

The repository already uses inline keyboard flows for `/cd` and `/sessions`, but these commands still depend on remembering arguments:

- `/mode`
- `/model`
- `/effort`
- `/permission`

This is inconsistent with the current UX direction and increases input friction on Telegram.

### 3. Repository collaboration standards are not yet codified

The project does not currently provide repository-level contribution guidance or GitHub issue/PR templates aligned with the existing stack and verification commands.

## Proposed Follow-Up Work

1. Add `AGENTS.md` and GitHub issue/PR templates.
2. Fix `codex_workdir` so the configured path is the runtime default home/workdir baseline.
3. Convert `/mode`, `/model`, `/effort`, and `/permission` to button panels while keeping existing text arguments compatible.
4. Add regression tests for all of the above behavior.

## Verification Targets

- `pdm run pytest -q`
- `pdm run ruff check .`
- focused tests covering service and Telegram handler behavior for the new workdir and selector panel flows
