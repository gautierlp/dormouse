import unittest
from datetime import datetime, timezone

from rules import final_decision, pre_decision

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
OLD = "2026-10-04T10:00:00Z"     # 26 hours before NOW
RECENT = "2026-10-05T01:00:00Z"  # 11 hours before NOW


def chat(**overrides):
    base = {
        "id": "c1",
        "title": "Alice",
        "type": "single",
        "isArchived": False,
        "isPinned": False,
        "lastActivity": OLD,
        "preview": {"text": "ok thanks", "isSender": False, "senderName": "Alice"},
    }
    base.update(overrides)
    return base


class PreDecisionTest(unittest.TestCase):
    def test_archived_is_skipped(self):
        self.assertEqual(pre_decision(chat(isArchived=True), NOW), ("skip", "archived-or-pinned"))

    def test_pinned_is_skipped(self):
        self.assertEqual(pre_decision(chat(isPinned=True), NOW), ("skip", "archived-or-pinned"))

    def test_recent_is_kept(self):
        self.assertEqual(pre_decision(chat(lastActivity=RECENT), NOW), ("keep", "recent"))

    def test_quiet_after_12_hours(self):
        thirteen_hours = "2026-10-04T23:00:00Z"  # 13 hours before NOW
        self.assertEqual(pre_decision(chat(lastActivity=thirteen_hours), NOW), ("ask", "needs-model"))

    def test_missing_activity_is_kept(self):
        self.assertEqual(pre_decision(chat(lastActivity=None), NOW), ("keep", "no-activity"))

    def test_sent_by_me_is_archived(self):
        c = chat(preview={"text": "see you", "isSender": True, "senderName": "Me"})
        self.assertEqual(pre_decision(c, NOW), ("archive", "sent-by-me"))

    def test_incoming_without_text_asks_the_model(self):
        # A reaction or a photo: the runner decides from the message history.
        c = chat(preview={"isSender": False, "senderName": "Alice"})
        self.assertEqual(pre_decision(c, NOW), ("ask", "needs-model"))

    def test_incoming_with_text_asks_the_model(self):
        self.assertEqual(pre_decision(chat(), NOW), ("ask", "needs-model"))


class FinalDecisionTest(unittest.TestCase):
    def test_verdicts(self):
        self.assertEqual(final_decision(False), ("archive", "no-reply-needed"))
        self.assertEqual(final_decision(True), ("keep", "reply-needed"))

    def test_model_error_keeps(self):
        self.assertEqual(final_decision(None), ("keep", "model-error"))


if __name__ == "__main__":
    unittest.main()
