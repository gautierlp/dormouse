"""Ask a local Ollama model whether a chat still expects a reply from the owner."""
import http.client
import json
import urllib.request

SCHEMA = {
    "type": "object",
    "properties": {"needs_reply": {"type": "boolean"}},
    "required": ["needs_reply"],
}

SYSTEM_PROMPT = (
    "You triage a personal messaging inbox. You get the recent messages of a chat, "
    "oldest first. 'Me' is the owner of the inbox. The last message was sent by "
    "someone else. Decide if the owner still owes an answer. Questions, requests, "
    "invitations and anything left open expect an answer, even when a short "
    "message such as 'haha' or an emoji came after the question. "
    "Acknowledgements ('ok', 'thanks', a thumbs up), closings, automated "
    "notifications and group chatter not aimed at the owner do not. Messages can "
    "be in French or English. Answer only with the JSON object."
)

MAX_MESSAGE_CHARS = 300


def format_message(message):
    who = "Me" if message.get("isSender") else (message.get("senderName") or "unknown")
    text = " ".join((message.get("text") or "").split())[:MAX_MESSAGE_CHARS]
    if not text:
        text = f"[{(message.get('type') or 'attachment').lower()}]"
    return f"{who}: {text}"


def build_prompt(chat, history=None):
    """history: recent messages, oldest first. Without it, only the chat preview is used."""
    preview = chat.get("preview") or {}
    header = f"Chat type: {chat.get('type', 'unknown')}\n"
    if history:
        return header + "Recent messages, oldest first:\n" + "\n".join(
            format_message(m) for m in history)
    return (
        header
        + f"Sender: {preview.get('senderName') or 'unknown'}\n"
        + f"Last message: {preview.get('text') or ''}"
    )


def parse_response(body):
    """Return the needs_reply boolean, or None if the response is not usable."""
    try:
        content = json.loads(body)["message"]["content"]
        data = json.loads(content)
    except (ValueError, KeyError, TypeError):
        return None
    value = data.get("needs_reply") if isinstance(data, dict) else None
    return value if isinstance(value, bool) else None


class OllamaClassifier:
    def __init__(self, model, base_url="http://127.0.0.1:11434", timeout=60,
                 opener=urllib.request.urlopen):
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.opener = opener

    def needs_reply(self, chat, history=None):
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "options": {"temperature": 0},
            "format": SCHEMA,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(chat, history)},
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener(req, timeout=self.timeout) as resp:
                body = resp.read().decode()
        except (OSError, ValueError, http.client.HTTPException):
            # URLError and TimeoutError are both OSError. Any failure means "keep".
            return None
        return parse_response(body)
