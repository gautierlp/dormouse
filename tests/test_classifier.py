import http.client
import io
import json
import unittest
import urllib.error

from classifier import OllamaClassifier, build_prompt, parse_response

CHAT = {
    "id": "c1",
    "title": "Alice",
    "type": "single",
    "preview": {"text": "ok thanks!", "isSender": False, "senderName": "Alice"},
}


def ollama_body(content):
    return json.dumps({"message": {"role": "assistant", "content": content}}).encode()


class ParseResponseTest(unittest.TestCase):
    def test_valid(self):
        self.assertIs(parse_response(ollama_body('{"needs_reply": false}').decode()), False)
        self.assertIs(parse_response(ollama_body('{"needs_reply": true}').decode()), True)

    def test_invalid_outer_json(self):
        self.assertIsNone(parse_response("not json"))

    def test_invalid_inner_json(self):
        self.assertIsNone(parse_response(ollama_body("yes").decode()))

    def test_missing_key_or_wrong_type(self):
        self.assertIsNone(parse_response(ollama_body('{"answer": true}').decode()))
        self.assertIsNone(parse_response(ollama_body('{"needs_reply": "no"}').decode()))


class PromptTest(unittest.TestCase):
    def test_prompt_has_type_sender_and_text(self):
        prompt = build_prompt(CHAT)
        self.assertIn("single", prompt)
        self.assertIn("Alice", prompt)
        self.assertIn("ok thanks!", prompt)


HISTORY = [
    {"isSender": False, "senderName": "Alice", "text": "tu viens samedi ?", "type": "TEXT"},
    {"isSender": True, "senderName": "Sam", "text": "je regarde", "type": "TEXT"},
    {"isSender": False, "senderName": "Alice", "text": "", "type": "IMAGE"},
    {"isSender": False, "senderName": "Alice", "text": "haha\nok", "type": "TEXT"},
]


class HistoryPromptTest(unittest.TestCase):
    def test_history_is_listed_oldest_first_with_me(self):
        prompt = build_prompt(CHAT, HISTORY)
        lines = [l for l in prompt.splitlines() if ": " in l and not l.startswith("Chat type")]
        self.assertEqual(lines, [
            "Alice: tu viens samedi ?",
            "Me: je regarde",
            "Alice: [image]",
            "Alice: haha ok",
        ])

    def test_long_message_is_cut(self):
        prompt = build_prompt(CHAT, [{"isSender": False, "senderName": "A", "text": "x" * 500}])
        self.assertIn("A: " + "x" * 300 + "\n", prompt + "\n")
        self.assertNotIn("x" * 301, prompt)

    def test_payload_carries_history(self):
        seen = {}

        def opener(req, timeout):
            seen["payload"] = json.loads(req.data)
            return io.BytesIO(ollama_body('{"needs_reply": true}'))

        self.assertIs(OllamaClassifier("m", opener=opener).needs_reply(CHAT, HISTORY), True)
        self.assertIn("Me: je regarde", seen["payload"]["messages"][1]["content"])


class PromptNullTest(unittest.TestCase):
    def test_null_sender_and_text(self):
        prompt = build_prompt({"type": "single", "preview": {"senderName": None, "text": None}})
        self.assertIn("Sender: unknown", prompt)
        self.assertTrue(prompt.endswith("Last message: "))


class OllamaClassifierTest(unittest.TestCase):
    def test_sends_expected_payload(self):
        seen = {}

        def opener(req, timeout):
            seen["url"] = req.full_url
            seen["payload"] = json.loads(req.data)
            seen["timeout"] = timeout
            return io.BytesIO(ollama_body('{"needs_reply": false}'))

        clf = OllamaClassifier("qwen3.5:4b", opener=opener)
        self.assertIs(clf.needs_reply(CHAT), False)
        self.assertEqual(seen["url"], "http://127.0.0.1:11434/api/chat")
        self.assertEqual(seen["timeout"], 60)
        p = seen["payload"]
        self.assertEqual(p["model"], "qwen3.5:4b")
        self.assertIs(p["stream"], False)
        self.assertIs(p["think"], False)
        self.assertEqual(p["options"], {"temperature": 0})
        self.assertEqual(p["format"]["required"], ["needs_reply"])
        self.assertEqual(p["format"]["properties"]["needs_reply"], {"type": "boolean"})

    def test_timeout_returns_none(self):
        def opener(req, timeout):
            raise TimeoutError("timed out")

        self.assertIsNone(OllamaClassifier("m", opener=opener).needs_reply(CHAT))

    def test_http_exception_returns_none(self):
        def opener(req, timeout):
            raise http.client.IncompleteRead(b"")

        self.assertIsNone(OllamaClassifier("m", opener=opener).needs_reply(CHAT))

    def test_connection_error_returns_none(self):
        def opener(req, timeout):
            raise urllib.error.URLError("connection refused")

        self.assertIsNone(OllamaClassifier("m", opener=opener).needs_reply(CHAT))


if __name__ == "__main__":
    unittest.main()
