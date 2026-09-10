"""Small in-memory cooldown guard for public generation endpoints."""

from __future__ import annotations

import threading
import time


class SubmissionCooldown:
    def __init__(self, cooldown_seconds: float) -> None:
        self.cooldown_seconds = max(0.0, cooldown_seconds)
        self._last_submission: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, client_key: str, now: float | None = None) -> float:
        """Record an allowed request or return remaining seconds for a blocked one."""
        current = time.monotonic() if now is None else now
        with self._lock:
            previous = self._last_submission.get(client_key)
            if previous is not None:
                remaining = self.cooldown_seconds - (current - previous)
                if remaining > 0:
                    return remaining
            self._last_submission[client_key] = current
        return 0.0

    def clear(self) -> None:
        with self._lock:
            self._last_submission.clear()
