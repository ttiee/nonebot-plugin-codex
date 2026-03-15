# Telegram Unified Workspace Panel Design

## Goal

Add a dedicated Telegram workspace panel for day-to-day use so users can inspect the current chat state and reach the most common runtime controls from one screen.

## Problem

The plugin already supports individual settings selectors, a workdir browser, and a history browser, but the operational surface is still fragmented:

- `/mode`, `/model`, `/effort`, and `/permission` are separate entrypoints.
- `/pwd`, `/cd`, and `/sessions` expose adjacent state from different commands.
- The new onboarding panel is helpful for first-run guidance, but it is intentionally narrow and should not become the permanent control surface.
- Telegram mobile users pay a high cost when they need several command round-trips just to inspect state and make one or two adjustments.

This leaves the plugin functionally complete but operationally scattered.

## Constraints

- Preserve all existing commands for backward compatibility.
- Keep onboarding and daily workspace control as separate concepts.
- Reuse the existing panel token/version/message-id pattern.
- Reuse existing setting, directory, and history flows rather than duplicating their selector logic.
- Keep the panel compact enough for Telegram mobile screens.
- Do not change session persistence format or migration behavior.

## Approaches Considered

### 1. Thin navigation wrapper

Add `/panel` as a summary page that only links to existing panels.

Pros:

- Smallest code change
- Maximum reuse of existing flows

Cons:

- Still requires multiple message hops
- Does not meaningfully deliver the "current workspace" control surface from issue #5

### 2. Dedicated workspace panel

Add a new workspace panel state machine that summarizes the current chat state and exposes high-frequency actions, while delegating detailed selection to the existing panels and browsers.

Pros:

- Matches the issue goal directly
- Keeps onboarding and daily control separate
- Reuses the existing panel architecture cleanly

Cons:

- Requires one more panel type and callback namespace

### 3. Expand onboarding into the daily control surface

Reuse the onboarding panel for `/panel` and `/status`, adding more controls until it becomes the general workspace UI.

Pros:

- Fewer top-level panel concepts

Cons:

- Mixes first-run guidance with daily controls
- Makes onboarding harder to keep concise
- Increases the risk of a crowded panel with conflicting responsibilities

## Recommended Approach

Use approach 2.

Implement a dedicated workspace panel for `/panel` and `/status`. Keep onboarding focused on first-run guidance, and keep the existing setting, directory, and history flows intact as reusable sub-surfaces.

## User-Facing Behavior

### Entry points

- `/panel`: open the workspace panel
- `/status`: open the same workspace panel
- Existing commands remain unchanged:
  - `/mode`
  - `/model`
  - `/effort`
  - `/permission`
  - `/pwd`
  - `/cd`
  - `/sessions`
- `/help`, `/start`, and `/codex` without a prompt continue to open the onboarding panel, not the workspace panel

### Panel content

The panel body should show three compact sections:

1. Current runtime settings
   - mode
   - model
   - effort
   - permission
2. Current work context
   - workdir
   - whether the current chat has an active or bound session
   - a short session/thread summary when available
3. Recent history summary
   - up to the two most recent history entries
   - short label only, enough to hint whether recent context exists

### Panel actions

Buttons are grouped into four rows:

- `模式` `模型` `强度` `权限`
- `目录` `历史`
- `新会话` `停止`
- `刷新` `关闭`

Interaction rules:

- `模式` `模型` `强度` `权限` open the existing setting panels.
- `目录` opens the existing directory browser.
- `历史` opens the existing history browser.
- `新会话` resets the current chat while keeping it active for the next prompt.
- `停止` disconnects the current chat from Codex.
- `刷新` re-renders the workspace panel with fresh state.
- `关闭` closes the panel message.

The workspace panel does not perform direct history restore in its first version. Recent history is informative only; recovery still happens inside the history browser.

## Architecture

Add a new workspace panel flow parallel to the existing onboarding, setting, history, and directory flows.

### Service layer

In `src/nonebot_plugin_codex/service.py` add:

- workspace callback prefix constant
- workspace stale-message constant
- `WorkspacePanelState`
- callback encode/decode helpers
- `open_workspace_panel(...)`
- `get_workspace_panel(...)`
- `remember_workspace_panel_message(...)`
- `close_workspace_panel(...)`
- `navigate_workspace_panel(...)`
- `render_workspace_panel(...)`

The rendering path should reuse existing preference, session, and history accessors. It should not embed detailed selector logic already handled by the setting, directory, or history flows.

### Telegram handler layer

In `src/nonebot_plugin_codex/telegram.py` add:

- workspace callback predicate
- send workspace panel helpers
- edit-or-resend helper for workspace panels
- `/panel` handler
- `/status` handler
- workspace callback handler

The callback handler should delegate to existing `send_*_to_chat(...)` methods where possible and only own workspace-specific actions such as refresh, close, new, and stop.

### Plugin registration and command metadata

Update:

- `src/nonebot_plugin_codex/__init__.py`
- `src/nonebot_plugin_codex/telegram_commands.py`

Register:

- `/panel`
- `/status`
- workspace callback matcher

Keep command metadata centralized in `telegram_commands.py`.

## Data Flow

1. User sends `/panel` or `/status`.
2. Handler opens workspace panel state in the service layer.
3. Service renders summary text and inline keyboard.
4. Telegram handler sends the message and records the panel message ID.
5. User presses a button.
6. Callback handler validates token and version, then either:
   - opens an existing sub-panel/browser, or
   - applies a workspace-specific action and refreshes/closes the panel.

## Error Handling

- Invalid or stale callback payloads show a stale-panel alert, matching existing panel behavior.
- If editing the original workspace panel fails, resend it and remember the new message ID.
- Delegated sub-panels retain their existing behavior and wording.
- `停止` should remain safe even when no session is currently bound.

## Testing Strategy

Add tests for:

- `/panel` and `/status` command metadata
- `/panel` and `/status` handlers opening the workspace panel
- workspace callback dispatch to:
  - settings
  - directory browser
  - history browser
  - new session
  - stop
  - refresh
  - close
- recent history summary appearing in rendered panel text
- stale callback behavior
- no regression in existing commands and existing panel handlers

Run:

- `pdm run pytest -q`
- `pdm run ruff check .`

## Risks

- The panel can become too dense if more controls are added casually.
- Session summary text can become noisy if full thread identifiers are rendered verbosely.
- Pulling in too much history detail can duplicate the history browser instead of complementing it.

## Mitigations

- Keep the first version focused on summary plus high-frequency actions.
- Limit recent-history display to two compact entries.
- Keep deep navigation inside the existing dedicated panels.
