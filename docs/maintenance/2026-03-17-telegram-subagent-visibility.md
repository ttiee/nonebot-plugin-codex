# Telegram Native Subagent Visibility Bug

## Summary

When the plugin uses the native `codex app-server` lane and Codex delegates work to a subagent, the Telegram bridge can surface intermediate agent-message text to the end user as if it were the main agent's final reply. At the same time, the progress panel does not explain the collaboration flow, so users cannot tell what the main agent is doing versus what the subagent is doing.

## Reproduction Shape

1. Start a Telegram chat in the native resume mode.
2. Send a prompt that causes Codex to call a subagent.
3. Observe the native protocol emitting:
   - `item/agentMessage/delta`
   - `item/completed` for `agentMessage` with `phase: "commentary"`
   - `item/started` or `item/completed` for `collabAgentToolCall`
4. Observe the Telegram bridge showing the commentary/subagent text as a user-visible assistant reply.

## Expected Behavior

- Only the main agent's final answer should be user-visible in Telegram.
- Commentary or subagent-related intermediate text should stay out of the final reply stream.
- Telegram progress text should explain:
  - what the main agent is doing
  - which subagent is running
  - the current subagent state when available
- Main agent and each spawned subagent should keep independent Telegram message pairs:
  - one progress/status message
  - one temporary reply message
- Subagent panels should be appended after the main agent in first-seen creation order and stay stable for the rest of the run.

## Actual Behavior

- The native client forwarded all `agentMessage` deltas and completed texts without checking `phase`.
- Commentary text could therefore appear in the stream/final reply path.
- Collaboration tool calls were ignored, so the Telegram progress panel lacked main-agent/subagent context.
- In follow-up testing, main-agent final text could still be lost when it only existed in
  `item/agentMessage/delta` frames, because the native fallback looked up the wrong
  buffered key on `turn/completed`.
- Another follow-up issue appeared after multi-agent support landed: the native runner
  treated any `turn/completed` as the end of the active run, including subagent turns.
  That could bind later follow-up prompts to the subagent thread instead of the main
  thread, and it also made the bridge vulnerable to leaking subagent result text into
  the main-agent final-answer path.
- When that happened, Telegram could still finalize the main progress panel as
  `Codex 已完成。`, then separately send `Codex 已完成，但没有返回可展示的最终文本。`,
  which made successful-looking runs appear to stop right after a subagent failure.

## Affected Modules

- `src/nonebot_plugin_codex/native_client.py`
- `src/nonebot_plugin_codex/service.py`
- `src/nonebot_plugin_codex/telegram.py`
- `tests/test_native_client.py`

## Verification

- Add a native-client regression test that includes:
  - commentary `agentMessage`
  - `collabAgentToolCall`
  - final-answer `agentMessage`
- Confirm that only the final answer reaches `on_stream_text`.
- Confirm that progress updates mention both the main agent and the subagent state.
- Add a native-client regression where a subagent reports `errored` but the main agent
  still produces a final answer through delta-only fallback.
- Add a native-client regression where a subagent emits its own `turn/completed`
  before the main thread finishes, and confirm the client waits for the main
  `turn/completed` before returning or updating the stored thread id.
- Confirm that Telegram uses `Codex 已完成，但没有返回可展示的最终文本。` for the main
  progress panel instead of a plain `Codex 已完成。` when no final text is available.
