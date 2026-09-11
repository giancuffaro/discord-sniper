"""Durable alert reservations. An unresolved submission is never replayed."""
import json
import sqlite3
import time


class RequestJournal:
    """Claim each client order id once, including across process restarts."""

    def __init__(self, path):
        self.path = str(path)

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("CREATE TABLE IF NOT EXISTS requests "
                     "(coid TEXT PRIMARY KEY, created REAL NOT NULL, result TEXT)")
        return conn

    def begin(self, coid):
        conn = self._connect()
        try:
            with conn:
                added = conn.execute(
                    "INSERT OR IGNORE INTO requests VALUES (?, ?, NULL)",
                    (coid, time.time())).rowcount
                row = conn.execute(
                    "SELECT result FROM requests WHERE coid=?", (coid,)).fetchone()
            if added:
                return True, None
            return False, (tuple(json.loads(row[0])) if row and row[0] else
                           (False, "This alert has an unresolved earlier submission; "
                            "no duplicate order sent. Check the original order at the broker."))
        finally:
            conn.close()

    def finish(self, coid, result):
        conn = self._connect()
        try:
            with conn:
                conn.execute("UPDATE requests SET result=? WHERE coid=?",
                             (json.dumps(result), coid))
        finally:
            conn.close()
