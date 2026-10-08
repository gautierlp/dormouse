"""Archive quiet Beeper chats where no reply is owed. Started hourly by systemd."""
import argparse
import os
import sys
from datetime import datetime, timezone

from beeper import BeeperClient
from classifier import OllamaClassifier
from rules import ARCHIVE, ASK, KEEP, SKIP, final_decision, pre_decision
from state import DecisionStore

DEFAULT_MODEL = "qwen3.5:4b"
DEFAULT_STATE = "~/.local/state/dormouse/state.db"
HISTORY_SIZE = 10


def decide_with_model(chat, classifier, store, model, history_fn):
    """The other side acted last. Decide from the last real messages."""
    verdict = store.get(chat["id"], chat["lastActivity"], model)
    if verdict is not None:
        return final_decision(verdict)
    history = history_fn(chat["id"]) if history_fn else None
    if history and history[-1].get("isSender"):
        # Their last action was a reaction to my message: the ball is in their court.
        return ARCHIVE, "sent-by-me"
    if (chat.get("type") == "single" and history
            and not any(m.get("isSender") for m in history)):
        # I wrote nothing in the recent messages: the other side waits on me,
        # even when their last message is only an emoji.
        return KEEP, "unanswered"
    if (chat.get("type") == "single" and history
            and not (history[-1].get("text") or "").strip()):
        # Their last message is a photo or a file with no text. The model sees
        # only "[image]" and reads it as nothing to answer, but they wait on me.
        return KEEP, "attachment"
    preview_text = ((chat.get("preview") or {}).get("text") or "").strip()
    if not history and not preview_text:
        # Nothing the model can read.
        return KEEP, "no-text"
    verdict = classifier.needs_reply(chat, history)
    if verdict is not None:
        store.put(chat["id"], chat["lastActivity"], model, verdict)
    return final_decision(verdict)


def always_archive_names(env):
    """The comma-separated chat titles of ALWAYS_ARCHIVE, lowercase."""
    names = (n.strip().lower() for n in env.get("ALWAYS_ARCHIVE", "").split(","))
    return {n for n in names if n}


def run_once(chats, classifier, store, model, archive_fn, now, log, history_fn=None,
             always_archive=frozenset()):
    """Decide every chat. archive_fn is None in dry run. history_fn(chat_id) gives the
    recent messages for the model. Returns the archived count."""
    count = 0
    for chat in chats:
        try:
            action, reason = pre_decision(chat, now, always_archive)
            if action != SKIP and store.was_archived(chat["id"], chat["lastActivity"]):
                # I archived it and the owner moved it back, with nothing new said.
                continue
            if action == ASK:
                action, reason = decide_with_model(chat, classifier, store, model, history_fn)
            if action != ARCHIVE:
                continue
            text = " ".join(((chat.get("preview") or {}).get("text") or "").split())[:80]
            title = chat.get("title") or chat["id"]
            prefix = "WOULD-ARCHIVE" if archive_fn is None else "ARCHIVE"
            if archive_fn is not None:
                try:
                    archive_fn(chat["id"])
                except OSError as exc:
                    log(f"ERROR archiving {chat['id']}: {exc}")
                    continue
                store.mark_archived(chat["id"], chat["lastActivity"])
            log(f"{prefix} [{reason}] {title} | {text}")
            count += 1
        except Exception as exc:
            log(f"ERROR {chat.get('id')}: {exc}")
            continue
    return count


def main(argv=None, env=None, client=None, store=None, log=print):
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=env.get("BEEPER_ARCHIVE_MODEL", DEFAULT_MODEL))
    args = parser.parse_args(argv)

    live = env.get("ARCHIVE_ENABLED") == "1"
    client = client or BeeperClient(env["BEEPER_ACCESS_TOKEN"])
    store = store or DecisionStore(os.path.expanduser(env.get("STATE_DB", DEFAULT_STATE)))
    classifier = OllamaClassifier(args.model)

    try:
        chats = list(client.iter_chats())
    except (OSError, ValueError) as exc:
        log(f"ERROR beeper api unreachable: {exc}")
        return 1

    archive_fn = (lambda cid: client.set_archived(cid, True)) if live else None
    # The cache key names the history size, so verdicts made from the preview
    # alone are not reused for the history-based prompt.
    cache_key = f"{args.model}+history{HISTORY_SIZE}"
    count = run_once(chats, classifier, store, cache_key, archive_fn,
                     datetime.now(timezone.utc), log,
                     lambda cid: client.recent_messages(cid, HISTORY_SIZE),
                     always_archive_names(env))
    mode = "live" if live else "dry-run"
    log(f"done: {len(chats)} chats, {count} archived ({mode}, model {args.model})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
