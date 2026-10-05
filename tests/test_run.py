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
            return [{"text": "hi"}]

        clf = FakeClassifier(False)
        mine = chat("mine", "bye", True)
        theirs = chat("theirs", "ok", False)
        for _ in range(2):
            run.run_once([mine, theirs], clf, store, "m", None, NOW, lambda l: None, history_fn)
        self.assertEqual(fetched, ["theirs"])
        self.assertEqual(clf.history, [{"text": "hi"}])


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
