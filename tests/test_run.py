import unittest
from datetime import datetime, timezone

import dormouse as run
from state import DecisionStore

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
OLD = "2026-10-04T10:00:00Z"


def chat(cid, text, is_sender, title=None):
    return {
        "id": cid,
        "title": title or cid,
        "type": "single",
        "isArchived": False,
        "isPinned": False,
        "lastActivity": OLD,
        "preview": {"text": text, "isSender": is_sender, "senderName": "X"},
    }


class FakeClassifier:
    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = 0

    def needs_reply(self, chat, history=None):
        self.calls += 1
        self.history = history
        return self.verdict


class RunOnceTest(unittest.TestCase):
    def setUp(self):
        self.lines = []
        self.store = DecisionStore(":memory:")

    def go(self, chats, clf, archive_fn=None):
        return run.run_once(chats, clf, self.store, "m", archive_fn, NOW, self.lines.append)

    def test_dry_run_logs_and_never_archives(self):
        chats = [chat("mine", "see you", True, "Bob"), chat("theirs", "ok thanks", False, "Alice")]
        self.go(chats, FakeClassifier(False))
        self.assertEqual(self.lines, [
            "WOULD-ARCHIVE [sent-by-me] Bob | see you",
            "WOULD-ARCHIVE [no-reply-needed] Alice | ok thanks",
        ])

    def test_live_archives(self):
        archived = []
        self.go([chat("mine", "see you", True, "Bob")], FakeClassifier(False), archived.append)
        self.assertEqual(archived, ["mine"])
        self.assertEqual(self.lines, ["ARCHIVE [sent-by-me] Bob | see you"])

    def test_reply_needed_is_kept_and_text_is_truncated(self):
        long_text = "x" * 200 + "?"
        self.go([chat("q", long_text, False)], FakeClassifier(True))
        self.assertEqual(self.lines, [])
        self.go([chat("n", long_text, False, "N")], FakeClassifier(False))
        self.assertEqual(self.lines, ["WOULD-ARCHIVE [no-reply-needed] N | " + "x" * 80])

    def test_cache_hit_and_errors_not_cached(self):
        clf = FakeClassifier(False)
        c = chat("t", "ok", False)
        self.go([c], clf)
        self.go([c], clf)
        self.assertEqual(clf.calls, 1)
        failing = FakeClassifier(None)
        e = chat("e", "hmm", False)
        self.go([e], failing)
        self.go([e], failing)
        self.assertEqual(failing.calls, 2)

    def test_archive_error_continues(self):
        done = []

        def archive_fn(cid):
            if cid == "a":
                raise OSError("boom")
            done.append(cid)

        self.go([chat("a", "bye", True), chat("b", "bye", True)], FakeClassifier(False), archive_fn)
        self.assertEqual(done, ["b"])
        self.assertTrue(any(l.startswith("ERROR archiving a") for l in self.lines))

    def test_bad_chat_does_not_abort_the_run(self):
        bad = chat("bad", "x", False)
        bad["lastActivity"] = "garbage"
        self.go([bad, chat("good", "see you", True, "Bob")], FakeClassifier(False))
        self.assertTrue(any(l.startswith("ERROR bad") for l in self.lines))
        self.assertIn("WOULD-ARCHIVE [sent-by-me] Bob | see you", self.lines)

    def test_newline_in_text_cannot_split_the_log_line(self):
        self.go([chat("mine", "a\nb", True, "Bob")], FakeClassifier(False))
        self.assertEqual(self.lines, ["WOULD-ARCHIVE [sent-by-me] Bob | a b"])


class HistoryTest(unittest.TestCase):
    def test_history_fetched_on_cache_miss_only(self):
        store = DecisionStore(":memory:")
        fetched = []

        def history_fn(cid):
            fetched.append(cid)
            return [{"isSender": True, "text": "hey"}, {"text": "hi"}]

        clf = FakeClassifier(False)
        mine = chat("mine", "bye", True)
        theirs = chat("theirs", "ok", False)
        for _ in range(2):
            run.run_once([mine, theirs], clf, store, "m", None, NOW, lambda l: None, history_fn)
        self.assertEqual(fetched, ["theirs"])
        self.assertEqual(clf.history, [{"isSender": True, "text": "hey"}, {"text": "hi"}])


class LastRealMessageTest(unittest.TestCase):
    def setUp(self):
        self.lines = []
        self.store = DecisionStore(":memory:")

    def go(self, c, clf, history):
        run.run_once([c], clf, self.store, "m", None, NOW, self.lines.append,
                     lambda cid: history)

    def test_their_reaction_after_my_message_is_sent_by_me(self):
        reaction_preview = chat("r", None, False, "Florian")
        clf = FakeClassifier(True)
        self.go(reaction_preview, clf, [{"isSender": False, "text": "dispo ?"},
                                        {"isSender": True, "text": "oui, samedi"}])
        self.assertEqual(clf.calls, 0)
        self.assertEqual(self.lines, ["WOULD-ARCHIVE [sent-by-me] Florian | "])

    def test_no_text_with_history_asks_the_model(self):
        clf = FakeClassifier(False)
        self.go(chat("p", None, False, "P"), clf, [{"isSender": True, "text": "photo ?"},
                                                   {"isSender": False, "type": "IMAGE"}])
        self.assertEqual(clf.calls, 1)
        self.assertEqual(self.lines, ["WOULD-ARCHIVE [no-reply-needed] P | "])

    def test_no_text_without_history_is_kept(self):
        clf = FakeClassifier(False)
        self.go(chat("n", None, False), clf, [])
        self.assertEqual(clf.calls, 0)
        self.assertEqual(self.lines, [])


class UnansweredTest(unittest.TestCase):
    def setUp(self):
        self.lines = []
        self.store = DecisionStore(":memory:")

    def go(self, c, clf, history):
        run.run_once([c], clf, self.store, "m", None, NOW, self.lines.append,
                     lambda cid: history)

    def test_one_to_one_chat_i_never_answered_is_kept(self):
        # A small model reads a final emoji as a closing. If I wrote nothing in
        # the recent messages, the other side is waiting on me.
        clf = FakeClassifier(False)
        self.go(chat("u", "lol", False), clf, [{"isSender": False, "text": "you there?"},
                                              {"isSender": False, "text": "lol"}])
        self.assertEqual(clf.calls, 0)
        self.assertEqual(self.lines, [])

    def test_group_chat_without_my_messages_still_asks_the_model(self):
        clf = FakeClassifier(False)
        g = chat("g", "lol", False, "G")
        g["type"] = "group"
        self.go(g, clf, [{"isSender": False, "text": "lol"}])
        self.assertEqual(clf.calls, 1)
        self.assertEqual(self.lines, ["WOULD-ARCHIVE [no-reply-needed] G | lol"])


class RestoredTest(unittest.TestCase):
    def test_chat_the_owner_unarchived_is_not_archived_again(self):
        store = DecisionStore(":memory:")
        archived = []
        c = chat("r", "ok", False, "R")
        history = lambda cid: [{"isSender": True, "text": "hi"}, {"isSender": False, "text": "ok"}]
        run.run_once([c], FakeClassifier(False), store, "m", archived.append, NOW,
                     lambda l: None, history)
        self.assertEqual(archived, ["r"])
        # The owner moves it back to the inbox. Nothing new was said.
        run.run_once([c], FakeClassifier(False), store, "m", archived.append, NOW,
                     lambda l: None, history)
        self.assertEqual(archived, ["r"])

    def test_restored_chat_with_new_activity_is_decided_again(self):
        store = DecisionStore(":memory:")
        archived = []
        c = chat("r", "bye", True, "R")
        run.run_once([c], FakeClassifier(False), store, "m", archived.append, NOW, lambda l: None)
        c = dict(c, lastActivity="2026-10-04T11:00:00Z")
        run.run_once([c], FakeClassifier(False), store, "m", archived.append, NOW, lambda l: None)
        self.assertEqual(archived, ["r", "r"])

    def test_dry_run_records_nothing(self):
        store = DecisionStore(":memory:")
        c = chat("d", "bye", True)
        run.run_once([c], FakeClassifier(False), store, "m", None, NOW, lambda l: None)
        self.assertFalse(store.was_archived("d", c["lastActivity"]))


class MainTest(unittest.TestCase):
    def test_unreachable_api_exits_1(self):
        class DownClient:
            def iter_chats(self):
                raise OSError("connection refused")

        lines = []
        code = run.main([], env={"BEEPER_ACCESS_TOKEN": "t"}, client=DownClient(),
                        store=DecisionStore(":memory:"), log=lines.append)
        self.assertEqual(code, 1)
        self.assertTrue(any("beeper api unreachable" in l for l in lines))

    def test_bad_listing_payload_exits_1(self):
        class BadClient:
            def iter_chats(self):
                raise ValueError("bad json")

        lines = []
        code = run.main([], env={"BEEPER_ACCESS_TOKEN": "t"}, client=BadClient(),
                        store=DecisionStore(":memory:"), log=lines.append)
        self.assertEqual(code, 1)
        self.assertTrue(any("beeper api unreachable" in l for l in lines))


if __name__ == "__main__":
    unittest.main()
