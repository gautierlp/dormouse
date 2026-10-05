"""Pure decision rule: which Beeper chats to archive. No I/O here."""
from datetime import datetime, timedelta

QUIET_PERIOD = timedelta(hours=12)

SKIP = "skip"
KEEP = "keep"
ARCHIVE = "archive"
ASK = "ask"


def parse_ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def pre_decision(chat, now):
    """Decide what can be decided without the model. Returns (action, reason)."""
    if chat.get("isArchived") or chat.get("isPinned"):
        return SKIP, "archived-or-pinned"
    last = chat.get("lastActivity")
    if not last:
        return KEEP, "no-activity"
    if now - parse_ts(last) < QUIET_PERIOD:
        return KEEP, "recent"
    preview = chat.get("preview") or {}
    if preview.get("isSender"):
        return ARCHIVE, "sent-by-me"
    if not (preview.get("text") or "").strip():
        # A photo, voice note or sticker: the model cannot judge it.
        return KEEP, "no-text"
    return ASK, "needs-model"


def final_decision(needs_reply):
    """Map the model verdict to an action. None means the model failed: keep."""
    if needs_reply is False:
        return ARCHIVE, "no-reply-needed"
    if needs_reply is True:
        return KEEP, "reply-needed"
    return KEEP, "model-error"
