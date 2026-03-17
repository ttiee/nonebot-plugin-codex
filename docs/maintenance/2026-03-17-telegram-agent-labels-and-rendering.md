# Telegram Agent Labels And Rendering Gaps

## Summary

Telegram output still had two presentation issues after the multi-agent panel split:

- single-agent runs always showed `主 agent` labels, which added noise
- the Markdown-to-Telegram renderer still left common block syntax such as `##` and `---` unrendered

## Reproduction Shape

1. Start a normal Telegram run that does not spawn any subagent.
2. Observe the progress and temporary reply messages showing a `主 agent` title even though there is only one panel.
3. Start a run that spawns a subagent and observe that the visual distinction between main and subagent panels could be more prominent.
4. Send or stream content containing Markdown headings or thematic breaks, for example:
   - `## 二级标题`
   - `---`
5. Observe Telegram rendering these lines as plain text instead of styled blocks.

## Expected Behavior

- Single-agent runs should keep the original unlabeled message style.
- Once a subagent appears, main and subagent panels should switch to explicit emoji-prefixed titles:
  - `🧠 主 agent`
  - `🛠️ 子 agent N`
- Existing main-agent messages should be refreshed when the first subagent appears.
- Markdown headings should render as visible section titles.
- Markdown thematic breaks should render as a visible separator line.

## Actual Behavior

- Agent titles were always rendered, even when there was only one agent panel.
- Panel titles used plain text only, which was less noticeable in Telegram.
- `telegram_rendering.py` converted lists and tables, but left headings and thematic breaks untouched.

## Affected Modules

- `src/nonebot_plugin_codex/service.py`
- `src/nonebot_plugin_codex/telegram.py`
- `src/nonebot_plugin_codex/telegram_rendering.py`
- `tests/test_telegram_handlers.py`
- `tests/test_telegram_rendering.py`

## Verification

- `pdm run pytest tests/test_telegram_rendering.py tests/test_telegram_handlers.py -q`
- `pdm run pytest tests/test_service.py -q`
- `pdm run pytest -q`
- `pdm run ruff check .`
