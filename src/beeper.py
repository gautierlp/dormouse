"""Minimal client for the local Beeper Desktop API (v1)."""
import json
import urllib.parse
import urllib.request


class BeeperClient:
    def __init__(self, token, base_url="http://127.0.0.1:23373", timeout=30,
                 opener=urllib.request.urlopen):
        self.token = token
        self.base_url = base_url
        self.timeout = timeout
        self.opener = opener

    def _request(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(f"{self.base_url}{path}", data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with self.opener(req, timeout=self.timeout) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else {}

    def iter_chats(self):
        cursor = None
        while True:
            params = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
                params["direction"] = "before"
            page = self._request("GET", "/v1/chats?" + urllib.parse.urlencode(params))
            yield from page.get("items", [])
            if not page.get("hasMore") or not page.get("oldestCursor"):
                return
            cursor = page["oldestCursor"]

    def recent_messages(self, chat_id, limit):
        """The last `limit` messages of a chat, oldest first, deleted ones left out."""
        path = f"/v1/chats/{urllib.parse.quote(chat_id, safe='')}/messages?limit={limit}"
        items = self._request("GET", path).get("items", [])
        # The API returns newest first, and sometimes one more than `limit`.
        kept = [m for m in items if not m.get("isDeleted")][:limit]
        return list(reversed(kept))

    def set_archived(self, chat_id, archived):
        path = f"/v1/chats/{urllib.parse.quote(chat_id, safe='')}/archive"
        self._request("POST", path, {"archived": archived})
