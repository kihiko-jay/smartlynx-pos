"""Shared token revocation and WebSocket ticket storage.

Uses Redis when configured so multi-worker deployments stay consistent. Falls
back to in-process dictionaries for local development and tests.
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Optional

logger = logging.getLogger("dukapos.auth_state")

try:
    import redis
except Exception:  # pragma: no cover
    redis = None


class DistributedAuthState:
    def __init__(self) -> None:
        self._client = None
        self._revoked_fallback: dict[str, float] = {}
        self._ticket_fallback: dict[str, dict] = {}
        self._lock = Lock()

    def init(self, redis_client) -> None:
        """Accept an already-established Redis client. Called at startup after ping succeeds."""
        self._client = redis_client
        logger.info("Distributed auth state initialised via Redis")

    def _get_client(self):
        """Return the Redis client if initialised, else None (triggers in-process fallback)."""
        return self._client

    def revoke_jti(self, jti: str, exp_epoch: float) -> None:
        ttl = max(1, int(exp_epoch - time.time()))
        client = self._get_client()
        if client is not None:
            try:
                client.setex(f"auth:revoked:{jti}", ttl, "1")
                return
            except Exception as exc:
                logger.warning("Redis revoke_jti failed, falling back: %s", exc)
        with self._lock:
            self._prune_revoked_locked()
            self._revoked_fallback[jti] = exp_epoch

    def is_jti_revoked(self, jti: str) -> bool:
        client = self._get_client()
        if client is not None:
            try:
                return bool(client.exists(f"auth:revoked:{jti}"))
            except Exception as exc:
                logger.warning("Redis is_jti_revoked failed, falling back: %s", exc)
        with self._lock:
            exp = self._revoked_fallback.get(jti)
            if exp is None:
                return False
            if exp < time.time():
                self._revoked_fallback.pop(jti, None)
                return False
            return True

    def issue_ws_ticket(self, ticket: str, employee_id: int, ttl_seconds: int) -> None:
        client = self._get_client()
        if client is not None:
            try:
                client.setex(f"auth:ws_ticket:{ticket}", ttl_seconds, str(employee_id))
                return
            except Exception as exc:
                logger.warning("Redis issue_ws_ticket failed, falling back: %s", exc)
        with self._lock:
            self._prune_tickets_locked()
            self._ticket_fallback[ticket] = {"employee_id": employee_id, "expires": time.monotonic() + ttl_seconds}

    def consume_ws_ticket(self, ticket: str) -> Optional[int]:
        client = self._get_client()
        if client is not None:
            try:
                key = f"auth:ws_ticket:{ticket}"
                pipe = client.pipeline()
                pipe.get(key)
                pipe.delete(key)
                value, _ = pipe.execute()
                return int(value) if value is not None else None
            except Exception as exc:
                logger.warning("Redis consume_ws_ticket failed, falling back: %s", exc)
        with self._lock:
            entry = self._ticket_fallback.pop(ticket, None)
            if entry is None or entry["expires"] < time.monotonic():
                return None
            return int(entry["employee_id"])

    def _prune_revoked_locked(self) -> None:
        now = time.time()
        expired = [j for j, exp in self._revoked_fallback.items() if exp < now]
        for j in expired:
            self._revoked_fallback.pop(j, None)

    def _prune_tickets_locked(self) -> None:
        now = time.monotonic()
        expired = [k for k, v in self._ticket_fallback.items() if v["expires"] < now]
        for k in expired:
            self._ticket_fallback.pop(k, None)


auth_state = DistributedAuthState()
