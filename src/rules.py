"""Pure decision rule: which Beeper chats to archive. No I/O here."""
import re
from datetime import date, datetime, timedelta

QUIET_PERIOD = timedelta(hours=12)
# A day/month/year date in a chat title, as in event groups: "Party 09/10/26".
TITLE_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})\b")

SKIP = "skip"
KEEP = "keep"
ARCHIVE = "archive"
ASK = "ask"


def parse_ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def event_date(title):
    """The day/month/year date in a title, or None."""
    match = TITLE_DATE.search(title or "")
    if not match:
        return None
    day, month, year = (int(g) for g in match.groups())
    try:
        return date(year if year >= 100 else 2000 + year, month, day)
    except ValueError:
        return None


def pre_decision(chat, now, always_archive=frozenset()):
    """Decide what can be decided without the model. Returns (action, reason).
    always_archive holds lowercase chat titles that never need a reply, such as bots."""
    if chat.get("isArchived") or chat.get("isPinned"):
        return SKIP, "archived-or-pinned"
    when = event_date(chat.get("title"))
    if when and when >= now.date():
        # The event has not happened yet: the group is still live.
        return KEEP, "upcoming-event"
    last = chat.get("lastActivity")
    if not last:
        return KEEP, "no-activity"
    if now - parse_ts(last) < QUIET_PERIOD:
        return KEEP, "recent"
    if (chat.get("title") or "").strip().lower() in always_archive:
        return ARCHIVE, "always-archive"
    preview = chat.get("preview") or {}
    if preview.get("isSender"):
        return ARCHIVE, "sent-by-me"
    # The other side acted last. That can be a reaction or a photo with no text:
    # the runner looks at the last real messages before it decides.
    return ASK, "needs-model"


def final_decision(needs_reply):
    """Map the model verdict to an action. None means the model failed: keep."""
    if needs_reply is False:
        return ARCHIVE, "no-reply-needed"
    if needs_reply is True:
        return KEEP, "reply-needed"
    return KEEP, "model-error"
