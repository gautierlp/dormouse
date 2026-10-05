# Beeper auto-archive on jarvis: design

**Date:** 2026-10-05
**Status:** Approved (design), pending implementation plan
**Host:** `jarvis` (a small home server, CPU only)

## Goal

Keep the Beeper inbox down to the conversations that still need something from me. Once an
hour, a script on jarvis archives every chat where the ball is not in my court and nothing
happened for 12 hours (24 hours until 2026-10-05, changed the day it went live). A chat where the other person is waiting for an answer is never archived.

## Decisions (locked during brainstorm)

| Decision | Choice | Rationale |
|---|---|---|
| Access to the chats | Beeper Desktop API, local on jarvis | The only official Beeper API. It needs the desktop app running, and jarvis is always on. |
| Archive rule | Last message older than 12 h, and either sent by me or judged as not needing a reply | "If an answer is still expected from me, don't archive." |
| "Needs a reply?" judge | Local model through Ollama, `qwen3.5:4b` first | Private messages never leave jarvis. Free. Supports French. |
| Fallback model | `gemma4:e4b` | Compared against Qwen3.5 during the dry run. |
| Cloud models (Haiku, Jev) | Rejected | Every incoming message would go to a third party. |
| Rollout | 7 days in dry-run mode before any real archive | A wrong archive hides a message I owe an answer to. |
| Code location | `scripts/beeper-auto-archive/` in this repo, Python 3.12 stdlib only | jarvis has Python 3.12 and no `uv`. No dependencies means nothing to install or update. |

## Architecture

Three pieces, all user-level on jarvis (with linger on for the service user):

1. **Beeper Desktop**, Linux AppImage, in `~/apps/beeper/`. Runs under a virtual X display
   (`Xvfb :99`) as the user service `beeper-desktop.service`, `Restart=always`. jarvis has no
   desktop session, so a real screen is never involved.
2. **Ollama** (already in Docker, `127.0.0.1:11434`). The old models were removed on
   2026-10-05; the plan pulls `qwen3.5:4b` and `gemma4:e4b`.
3. **The script**, `beeper-auto-archive.py`, started by `beeper-auto-archive.timer` every hour
   at `:17`.

### One-time setup (manual, needs a screen once)

- Start `x11vnc` on display `:99`, bound to `127.0.0.1` only, and reach it through an SSH
  tunnel from the Mac. Sign in to Beeper, verify jarvis as a new device, wait for the chats
  to sync. Stop `x11vnc` afterwards; it is not left running.
- In Beeper: Settings, Integrations, "+" next to Approved connections. Create a token for the
  script. It goes in `~/.config/beeper-auto-archive/env` (`chmod 600`), never in this repo.
- Check in Beeper settings whether the app auto-updates. Prefer manual updates: an update
  prompt on a screen nobody looks at can block the app.

## Decision rule

For each chat from `GET /v1/chats` (paginated, `limit=200`, all accounts):

1. Already archived (`isArchived`) or pinned (`isPinned`): skip.
2. `lastActivity` less than 12 hours ago: keep.
3. `preview.isSender` is true (I sent the last message): archive.
4. The other side sent the last message:
   - No `preview.text` (a photo, a voice note, a sticker): keep. The model cannot judge it.
   - Otherwise ask the model. `needs_reply: false` means archive, `true` means keep.
5. Any error while asking the model (timeout, bad JSON, Ollama down): keep. Every failure
   leaves the chat in the inbox.

Muted chats and group chats follow the same rule. The model is told the chat type and the
sender's name, because "ok" from one person in a 40-person group almost never needs a reply.

### The model call

`POST /api/chat` on Ollama with `"format"` set to the JSON schema
`{"needs_reply": boolean}`, `"think": false`, `temperature` 0, and a 60-second timeout. The
prompt contains the chat type and the last 10 messages of the chat, oldest first
(`GET /v1/chats/{chatID}/messages?limit=10`), each as `Me: ...` or `<sender>: ...`, cut to
300 characters, with `[image]`-style markers for messages without text. The history catches
a question followed by "haha" or an emoji, which the last message alone would miss. Changed
from "last message only" on 2026-10-05, the day the job went live. A decision takes about
10 to 20 seconds on the CPU; each hourly run only judges new messages.

### Memory

SQLite file `~/.local/state/beeper-auto-archive/state.db`, one table:

`decisions(chat_id, last_activity, model, needs_reply, decided_at)`, primary key
`(chat_id, last_activity, model)`.

The `model` column holds the model name plus `+history10`, so verdicts made from the
preview alone are never reused. A decision is reused as long as the chat's `lastActivity` has not changed, so each new
message is judged once per model, not once per hour.

## Modes

- `ARCHIVE_ENABLED=0` (default, dry run): decides everything, archives nothing. For each
  chat it would archive, it logs the chat name, the reason (`sent-by-me` or `no-reply-needed`),
  and the first 80 characters of the last message, to the systemd journal on jarvis (it does
  not leave the machine).
- `ARCHIVE_ENABLED=1`: calls `POST /v1/chats/{chatID}/archive` with `archived: true` and logs
  the same line.
- `--model <name>` overrides the model for one run, used to compare Qwen3.5 and Gemma 4.

## New message in an archived chat

To verify during setup: does Beeper move an archived chat back to the inbox when a new
message arrives? If yes, nothing to build. If no, the script adds a step: an archived chat
whose last message is from the other side, newer than 24 hours, and judged
`needs_reply: true` is unarchived (`archived: false`).

## Error handling

- Beeper API unreachable or a 401: the run exits non-zero with a clear log line and archives
  nothing. `beeper-desktop.service` restarts the app on a crash.
- A failure while archiving one chat is logged and the run continues with the next chat.

## Testing

Stdlib `unittest`, in `scripts/beeper-auto-archive/tests/`, runnable on the Mac and on
jarvis with `python3 -m unittest`:

- The decision rule as a pure function: each branch above, with chat dicts as input.
- The model response parsing: valid JSON, invalid JSON, missing key, timeout (all of the
  last three must mean "keep").
- The memory: a decision is reused for the same `lastActivity` and asked again when it
  changes.

The Beeper and Ollama calls are behind two small client classes, faked in the tests.

## Rollout and success criteria

1. Dry run for 7 days on `qwen3.5:4b`.
2. Once, during that week, a dry run with `--model gemma4:e4b` on the same chats.
3. I review 50 "would archive" lines from the log. Go live when at most 1 of the 50 is a
   chat I still owed an answer to. If Qwen3.5 misses that bar and Gemma 4 meets it, switch.
4. Set `ARCHIVE_ENABLED=1`.

## Out of scope

- Sending messages. Separate spec later.
- Reaching the Beeper API from the Mac.
- Alerts when the job fails. The journal is enough until the job has run for a few weeks.
