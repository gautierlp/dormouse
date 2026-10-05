import io
import json
import unittest
import urllib.parse

from beeper import BeeperClient


class FakeOpener:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        return io.BytesIO(self.bodies.pop(0))


class BeeperClientTest(unittest.TestCase):
    def test_iter_chats_follows_pages(self):
        pages = [
            {"items": [{"id": "a"}, {"id": "b"}], "hasMore": True, "oldestCursor": "CUR1"},
            {"items": [{"id": "c"}], "hasMore": False, "oldestCursor": "CUR2"},
        ]
        opener = FakeOpener([json.dumps(p).encode() for p in pages])
        client = BeeperClient("tok", opener=opener)
        self.assertEqual([c["id"] for c in client.iter_chats()], ["a", "b", "c"])
        first, second = opener.requests
        self.assertEqual(first.get_header("Authorization"), "Bearer tok")
        q1 = urllib.parse.parse_qs(urllib.parse.urlsplit(first.full_url).query)
        q2 = urllib.parse.parse_qs(urllib.parse.urlsplit(second.full_url).query)
        self.assertEqual(q1["limit"], ["200"])
        self.assertNotIn("cursor", q1)
        self.assertEqual(q2["cursor"], ["CUR1"])
        self.assertEqual(q2["direction"], ["before"])

    def test_set_archived(self):
        opener = FakeOpener([b""])
        BeeperClient("tok", opener=opener).set_archived("a/b", True)
        req = opener.requests[0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.full_url, "http://127.0.0.1:23373/v1/chats/a%2Fb/archive")
        self.assertEqual(json.loads(req.data), {"archived": True})

    def test_recent_messages_oldest_first_without_deleted(self):
        newest_first = [{"id": f"m{i}", "text": f"t{i}", "isDeleted": i == 3} for i in range(12, 0, -1)]
        opener = FakeOpener([json.dumps({"items": newest_first, "hasMore": True}).encode()])
        msgs = BeeperClient("tok", opener=opener).recent_messages("a/b", 10)
        self.assertEqual([m["id"] for m in msgs], [f"m{i}" for i in (2, 4, 5, 6, 7, 8, 9, 10, 11, 12)])
        url = urllib.parse.urlsplit(opener.requests[0].full_url)
        self.assertEqual(url.path, "/v1/chats/a%2Fb/messages")
        self.assertEqual(urllib.parse.parse_qs(url.query)["limit"], ["10"])

    def test_recent_messages_skip_reactions_and_hidden(self):
        newest_first = [
            {"id": "r", "type": "REACTION", "isHidden": True},
            {"id": "h", "type": "TEXT", "text": "x", "isHidden": True},
            {"id": "b", "type": "TEXT", "text": "merci"},
            {"id": "a", "type": "IMAGE", "text": ""},
        ]
        opener = FakeOpener([json.dumps({"items": newest_first}).encode()])
        msgs = BeeperClient("tok", opener=opener).recent_messages("c", 10)
        self.assertEqual([m["id"] for m in msgs], ["a", "b"])

    def test_empty_page(self):
        opener = FakeOpener([json.dumps({"items": [], "hasMore": False}).encode()])
        self.assertEqual(list(BeeperClient("tok", opener=opener).iter_chats()), [])


if __name__ == "__main__":
    unittest.main()
