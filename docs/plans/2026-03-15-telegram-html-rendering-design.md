# Telegram HTML Rendering Design

## Goal

Replace direct Telegram Markdown delivery with a safe, repository-local rendering layer that converts outbound text into Telegram-compatible HTML while preserving a useful subset of Markdown formatting.

## Problem

The plugin currently emits raw strings from multiple code paths, then relies on Telegram parse modes at send time. Direct `Markdown` delivery is unsafe because:

- Telegram Markdown syntax differs from common Markdown produced by Codex.
- Historical session and settings text contain underscores, backticks, paths, and other characters that Telegram can misinterpret as entities.
- Failures occur in both `sendMessage` and `editMessageText`, which can break callback flows such as `/sessions`.

## Constraints

- Existing service code should continue returning plain strings.
- User-visible command semantics must remain stable.
- The solution must handle all outgoing text, not just Codex result messages.
- Unsupported Markdown must degrade to safe plain text instead of raising Telegram entity errors.

## Proposed Approach

Add a Telegram rendering helper that converts arbitrary text into safe HTML plus `parse_mode="HTML"`. The renderer will:

- HTML-escape all content by default.
- Recognize a conservative Markdown subset:
  - bold: `**text**`, `__text__`
  - italic: `*text*`, `_text_`
  - inline code: `` `code` ``
  - fenced code blocks: triple backticks
  - links: `[label](url)`
- Preserve line breaks and paragraphs.
- Leave list markers and headings as escaped plain text.
- Treat malformed or ambiguous markup as plain text.

`TelegramHandlers` will route every text send/edit operation through the renderer before calling Telegram APIs. If Telegram still rejects the rendered HTML with an entity parsing error, handlers will retry once with fully escaped plain text and no parse mode.

## Why HTML

Telegram HTML is easier to generate safely than `MarkdownV2`, especially for mixed content such as file paths, shell commands, and historical conversation snippets. It also keeps the conversion logic readable and localized.

## Affected Areas

- `src/nonebot_plugin_codex/telegram.py`
  - replace default Markdown parse mode behavior
  - centralize render-before-send behavior
- new renderer module in `src/nonebot_plugin_codex/`
  - Markdown subset to Telegram HTML conversion
- tests
  - renderer unit tests
  - handler tests for HTML send/edit and fallback behavior

## Testing Strategy

- Unit test conversion for supported formatting and malformed input.
- Verify handlers send `parse_mode="HTML"` after conversion.
- Verify handlers retry with plain text when Telegram rejects HTML entities.
- Run full `pytest` and `ruff`.

## Risks

- Partial Markdown support may not preserve every Codex formatting nuance.
- Regex-only parsing can mis-handle nested markup if the rule set grows too far.

## Mitigation

Keep the renderer intentionally small and conservative. Unsupported or ambiguous patterns should remain escaped text rather than attempting broad Markdown compatibility.
