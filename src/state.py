"""SQLite cache of model verdicts, keyed by chat, last activity and model, and the
record of what dormouse archived."""
import os
import sqlite3
from datetime import datetime, timezone


class DecisionStore:
    def __init__(self, path):
        parent = os.path.dirname(path)
        if path != ":memory:" and parent:
            os.makedirs(parent, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS decisions ("
            " chat_id TEXT NOT NULL,"
            " last_activity TEXT NOT NULL,"
            " model TEXT NOT NULL,"
            " needs_reply INTEGER NOT NULL,"
            " decided_at TEXT NOT NULL,"
            " PRIMARY KEY (chat_id, last_activity, model))"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS archived ("
            " chat_id TEXT NOT NULL,"
            " last_activity TEXT NOT NULL,"
            " archived_at TEXT NOT NULL,"
            " PRIMARY KEY (chat_id, last_activity))"
        )
        self.db.commit()

    def get(self, chat_id, last_activity, model):
        row = self.db.execute(
            "SELECT needs_reply FROM decisions"
            " WHERE chat_id = ? AND last_activity = ? AND model = ?",
            (chat_id, last_activity, model),
        ).fetchone()
        return None if row is None else bool(row[0])

    def put(self, chat_id, last_activity, model, needs_reply):
        self.db.execute(
            "INSERT OR REPLACE INTO decisions VALUES (?, ?, ?, ?, ?)",
            (chat_id, last_activity, model, int(needs_reply),
             datetime.now(timezone.utc).isoformat()),
        )
        self.db.commit()

    def mark_archived(self, chat_id, last_activity):
        self.db.execute(
            "INSERT OR REPLACE INTO archived VALUES (?, ?, ?)",
            (chat_id, last_activity, datetime.now(timezone.utc).isoformat()),
        )
        self.db.commit()

    def was_archived(self, chat_id, last_activity):
        row = self.db.execute(
            "SELECT 1 FROM archived WHERE chat_id = ? AND last_activity = ?",
            (chat_id, last_activity),
        ).fetchone()
        return row is not None
