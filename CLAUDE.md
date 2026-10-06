# CLAUDE.md

dormouse: an hourly job that archives the Beeper chats where nobody is waiting on the
owner. A local Ollama model judges the last 10 messages when the other side wrote last.
Spec: `docs/superpowers/specs/2026-10-05-dormouse-design.md` (written when this lived in
the owner's homelab repo as "beeper-auto-archive"; it still names that server).

## Commands

    just test       # full suite (PYTHONPATH=src python3 -m unittest discover -s tests -v)
    just run        # one run with ~/.config/dormouse/env, dry unless ARCHIVE_ENABLED=1

Stdlib only, tests included. Imports are flat (`import rules`) with `src/` on the path.

## Rules

- Public repo: no personal value in code, tests, units, specs or the README.
- Every failure path keeps the chat in the inbox. Nothing can delete a chat.
- No cloud model: messages never leave the machine.
- TDD, one test file per module. No em dashes anywhere.
