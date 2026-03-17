# Telegram Context Compaction Follow-Up

## Summary

`nonebot-plugin-codex` currently supports long-lived `resume` conversations in Telegram, but it does not expose Codex's transcript compaction workflow.

OpenAI's current Codex CLI documentation includes a `/compact` slash command for summarizing earlier conversation history to free context, while this plugin currently offers no Telegram equivalent and does not surface automatic compaction notices from the underlying Codex session.

This leaves long-running Telegram conversations behind the current Codex UX available in the CLI and IDE surfaces.

Reference docs:

- CLI slash commands: `https://developers.openai.com/codex/cli/slash-commands`
- Local verification target: `codex-cli 0.105.0`

## Reproduction Steps

1. Configure the plugin and connect it to a local Codex CLI installation.
2. Start a persistent chat in Telegram with `/codex`.
3. Continue the same `resume` conversation for enough turns that context management matters.
4. Try to manually compact the current conversation from Telegram.
5. Compare that workflow with current Codex CLI behavior, which documents `/compact`.

## Expected Behavior

- Telegram users can manually compact the current `resume` conversation from the bot, ideally with a `/compact` command.
- When Codex compacts context automatically, Telegram users receive a visible notice similar to the CLI and IDE experience.
- The feature stays scoped to conversations where compaction is meaningful and supported, especially the active `resume` thread.
- Command documentation and tests cover the new behavior.

## Actual Behavior

- The plugin command menu does not include `/compact`.
- The NoneBot command registration layer does not handle a `compact` command.
- The service layer does not expose a public API for compacting the current chat session.
- The native Codex client wrapper does not surface compaction-related notifications to Telegram progress output.
- As a result, long Telegram sessions can continue to reuse context, but users do not have a manual compaction path and do not get explicit compaction feedback.

## Affected Commands And Files

Commands:

- `/codex`
- `/exec`
- `/sessions`
- desired new command: `/compact`

Primary files:

- `src/nonebot_plugin_codex/telegram_commands.py`
- `src/nonebot_plugin_codex/__init__.py`
- `src/nonebot_plugin_codex/telegram.py`
- `src/nonebot_plugin_codex/service.py`
- `src/nonebot_plugin_codex/native_client.py`
- `tests/test_telegram_commands.py`
- `tests/test_telegram_handlers.py`
- `tests/test_service.py`
- `tests/test_native_client.py`
- `README.md`

## Proposed Scope

1. Add a Telegram `/compact` command and register it in the synced Telegram command menu.
2. Implement service-layer compaction for the active `resume` thread, with clear user-facing errors when no resumable thread is bound.
3. Extend the native Codex client wrapper so compaction events from the app-server are surfaced as progress or notice text.
4. Add tests for command registration, handler behavior, service behavior, and native client event handling.
5. Update README command documentation to mention Telegram-side transcript compaction support and any mode limitations.

## Verification Targets

- `pdm run pytest -q`
- `pdm run ruff check .`
- focused tests for:
  - Telegram command menu generation
  - Telegram handler compaction flow
  - service-level session compaction
  - native client compaction event handling

## Notes

- Local focused regression baseline currently passes without this feature:
  - `pdm run pytest tests/test_native_client.py tests/test_service.py tests/test_telegram_commands.py tests/test_telegram_handlers.py -q`
- Manual local CLI inspection confirms this repository currently lacks `/compact` wiring, while the local Codex CLI installation advertises compaction-related capability.
