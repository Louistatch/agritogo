"""Bounded ephemeral history, isolated by an opaque signed session identifier."""
from collections import OrderedDict
from datetime import datetime, timezone
from secrets import token_urlsafe
from threading import Lock
from time import monotonic
from flask import session


def session_id():
    value = session.get("_id")
    if not isinstance(value, str) or len(value) < 32:
        value = token_urlsafe(32)
        session["_id"] = value
    return value


class SessionHistory:
    """Worker-local cache; expires and may disappear after restart."""
    def __init__(self, capacity=100, max_messages=20, ttl=1800, clock=monotonic):
        self.capacity, self.max_messages, self.ttl = capacity, max_messages, ttl
        self.clock, self._rows, self._lock = clock, OrderedDict(), Lock()

    def _expire(self):
        for key, (seen, _) in list(self._rows.items()):
            if self.clock() - seen >= self.ttl:
                del self._rows[key]

    def read(self, key):
        with self._lock:
            self._expire()
            value = self._rows.get(key)
            if not value:
                return []
            self._rows.move_to_end(key)
            return [dict(row) for row in value[1]]

    def append(self, key, role, content):
        if role not in ("user", "assistant"):
            raise ValueError("Invalid conversation role")
        with self._lock:
            self._expire()
            rows = self._rows.pop(key, (0, []))[1]
            rows.append({"role": role, "contenu": str(content)[:6000],
                         "timestamp": datetime.now(timezone.utc).isoformat()})
            self._rows[key] = (self.clock(), rows[-self.max_messages:])
            while len(self._rows) > self.capacity:
                self._rows.popitem(last=False)

    def clear(self, key):
        with self._lock:
            self._rows.pop(key, None)


browser_history = SessionHistory()
