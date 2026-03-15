# Telegram Onboarding Guided Entry Design

## Goal

Add a lightweight onboarding entry panel for Telegram users so first-time and returning users can understand the current chat state and reach the most common next actions without memorizing commands.

## Problem

The plugin already supports a Telegram command menu, `/codex`, directory browsing, settings selectors, and history browsing. However, the first-run flow is still fragmented:

- `/codex` without a prompt only sends a plain status message.
- There is no explicit `/help` or `/start` entrypoint.
- Common next actions are spread across separate commands and panels.
- Telegram mobile users pay a high cost for command recall and repeated command entry.

This leaves the plugin functional but not well-oriented for first-time use.

## Constraints

- Preserve existing command semantics, especially `/codex <prompt>`.
- Keep onboarding lightweight; do not build a multi-step wizard.
- Reuse existing callback and stale-panel patterns.
- Avoid bundling the separate "unified settings panel" issue into this work.
- Keep button labels and body copy concise for Telegram mobile screens.

## Approaches Considered

### 1. Improve `/codex` plain text only

Revise the existing `/codex` no-argument response text without adding buttons or new commands.

Pros:

- Minimal code change
- Almost no new state handling

Cons:

- Still command-centric
- Limited improvement for mobile users
- No obvious path from status to action

### 2. Unified onboarding panel for `/codex`, `/help`, and `/start`

Route `/codex` without a prompt, `/help`, and `/start` to the same lightweight onboarding panel with summary text and a few high-frequency buttons.

Pros:

- Matches Telegram expectations for `/start`
- Preserves current `/codex` behavior for prompted runs
- Reuses existing panel/callback model cleanly
- Delivers a meaningful first-run UX improvement without over-design

Cons:

- Requires new callback plumbing and tests

### 3. Multi-step onboarding wizard

Guide users through connection, workdir selection, and settings step by step.

Pros:

- Strongest hand-holding for first-time users

Cons:

- Too much interaction state
- Higher implementation and maintenance cost
- Over-scoped relative to current issue

## Recommended Approach

Use approach 2.

Implement one onboarding panel shared by `/codex` without a prompt, `/help`, and `/start`. Keep `/codex <prompt>` unchanged. The panel should summarize current state and provide direct entry to a small set of common next actions by reusing existing flows.

## User-Facing Behavior

### Entry points

- `/codex <prompt>`: unchanged, immediately executes the prompt
- `/codex`: opens onboarding panel
- `/help`: opens onboarding panel
- `/start`: opens onboarding panel

### Panel content

The panel body should show:

- a short title indicating this is the getting-started entry
- current mode
- current workdir
- current settings summary
- whether the current chat already has an active/bound session
- a very short recommended workflow

### Panel actions

Buttons should cover only high-frequency actions:

- open directory browser
- open settings entry
- open history sessions
- start a fresh session
- close panel

The panel should not introduce a new multi-step workflow or persistent onboarding state.

## Architecture

Add a new onboarding panel flow parallel to the existing directory, history, and setting panel flows.

### Service layer

Add onboarding panel state management in `src/nonebot_plugin_codex/service.py`:

- onboarding callback prefix constant
- stale message constant
- onboarding panel state dataclass
- open/get/remember/close methods
- callback encoding and decoding helpers
- rendering function returning body text and inline keyboard markup

The state should use the same token/version/message-id pattern already used by other Telegram panels.

### Telegram handler layer

Add onboarding-specific methods in `src/nonebot_plugin_codex/telegram.py`:

- send onboarding panel
- edit or resend onboarding panel
- `/help` handler
- `/start` handler
- onboarding callback predicate and callback handler

The callback handler should mostly delegate to existing flows:

- directory button -> existing directory browser send flow
- settings button -> existing setting panel entry
- history button -> existing history browser flow
- new session button -> existing reset chat logic
- close button -> close onboarding panel message

### Plugin registration

Update `src/nonebot_plugin_codex/__init__.py` and `src/nonebot_plugin_codex/telegram_commands.py` to register:

- `/help`
- `/start`

The command metadata should remain centralized in `telegram_commands.py`.

## Data Flow

1. User sends `/codex`, `/help`, or `/start`.
2. Handler activates the chat when appropriate and asks service to open onboarding panel state.
3. Service renders summary text and inline keyboard.
4. Telegram handler sends the panel and remembers its message ID.
5. User presses a button.
6. Callback handler validates token/version, then delegates to the corresponding existing flow or closes the panel.

## Error Handling

- Invalid or stale callback payload returns a stale-panel callback alert, matching existing panel behavior.
- If editing the original panel fails, handlers resend the panel and store the new message ID.
- Existing delegated flows keep their current error handling and user-facing wording.

## Testing Strategy

Add or update tests for:

- `/codex` without a prompt now sends onboarding panel markup
- `/help` and `/start` open the same onboarding panel
- onboarding callback dispatch to directory, settings, history, and new-session actions
- stale callback handling
- command metadata includes `help` and `start`

Run:

- `pdm run pytest -q`
- `pdm run ruff check .`

## Risks

- The panel can become too dense if too many actions are added.
- The onboarding issue can accidentally absorb the separate unified settings issue.
- New text can drift from command metadata if command descriptions are duplicated manually.

## Mitigations

- Keep panel scope intentionally narrow.
- Reuse existing panels instead of creating new selector logic.
- Continue using centralized command metadata for slash-command registration and usage text.
