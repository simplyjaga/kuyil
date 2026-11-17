"""In-memory key-value store for Kuyil.

Mirrors Redis 6's expiration architecture:

- ``_data``    — the actual key-value pairs (Redis's ``dict``)
- ``_expires`` — authoritative key -> deadline mapping (Redis's ``expires``)
- ``_hints``   — radix tree of expiration hints found while sampling
- ``_ttl_keys``— cheap sampling pool over keys that carry a deadline
"""

import random
import time
from dataclasses import dataclass

from kuyil.radix import ExpiryHintTree

# Tuned to Redis 6's activeExpireCycle: ~20 sampled keys per round,
# repeat while more than a quarter of them were already dead, and stop
# once the cycle's time budget is spent.
SAMPLE_SIZE = 20
DEAD_FRACTION = 0.25
CYCLE_BUDGET_SECONDS = 0.01
# Sampled keys expiring within this window are recorded as hints.
HINT_WINDOW_SECONDS = 1.0


@dataclass
class StoreEntry:
    """A stored value plus its metadata.

    Extensible: future attributes (encoding, last-access time for LRU,
    type information) become new fields here.
    """

    value: object


class Store:
    """Key-value store with lazy expiry plus periodic active expiry."""

    def __init__(self) -> None:
        self._data: dict[str, StoreEntry] = {}
        self._expires: dict[str, float] = {}
        self._hints = ExpiryHintTree()
        self._ttl_keys: list[str] = []

    def set(
        self, key: str, value: object, expires_at: float | None = None
    ) -> None:
        """Store a value under key; a call without expiry clears any TTL."""
        self._data[key] = StoreEntry(value=value)
        had_expiry = self._expires.pop(key, None) is not None
        if expires_at is not None:
            self._expires[key] = expires_at
            if not had_expiry:
                self._track_expiring(key)

    def get(self, key: str) -> StoreEntry | None:
        """Return a live entry, or None if missing or expired."""
        entry = self._data.get(key)
        if entry is None:
            return None

        deadline = self._expires.get(key)
        if deadline is not None and deadline <= time.time():
            self._evict(key)
            return None

        return entry

    def delete(self, key: str) -> bool:
        """Remove a live key; return True if one existed."""
        if self.get(key) is None:
            return False
        self._evict(key)
        return True

    def set_expiry(self, key: str, expires_at: float) -> bool:
        """Set an expiry timestamp on a live key; return True if it exists."""
        if self.get(key) is None:
            return False
        if key not in self._expires:
            self._track_expiring(key)
        self._expires[key] = expires_at
        return True

    def expire_cycle(self) -> int:
        """Run one bounded active-expiration pass; return keys deleted.

        First drains radix hints whose deadline has passed, then samples
        the expires table — deleting dead keys and recording near-dead
        ones as hints for later cycles. Stops on the Redis-style
        sampling condition and the cycle's time budget.
        """
        start = time.monotonic()
        removed = 0

        # Hints are not authoritative: a hint only deletes a key when
        # _expires still carries the same deadline (covers TTL updates
        # and deletes that made the hint stale).
        while True:
            hint = self._hints.peek_earliest()
            if hint is None or hint[1] > time.time():
                break
            self._hints.pop_earliest()
            key, deadline = hint
            if self._expires.get(key) == deadline:
                self._evict(key)
                removed += 1
            if time.monotonic() - start > CYCLE_BUDGET_SECONDS:
                return removed

        while time.monotonic() - start <= CYCLE_BUDGET_SECONDS:
            if not self._expires:
                break

            sample = random.sample(
                self._ttl_keys, min(SAMPLE_SIZE, len(self._ttl_keys))
            )
            dead = 0
            checked = 0
            stale = []
            now = time.time()

            for key in sample:
                deadline = self._expires.get(key)
                if deadline is None:
                    stale.append(key)
                    continue
                checked += 1
                if deadline <= now:
                    self._evict(key)
                    dead += 1
                    removed += 1
                elif deadline - now <= HINT_WINDOW_SECONDS:
                    self._hints.insert(key, deadline)

            for key in stale:
                self._ttl_keys.remove(key)

            if checked == 0 or dead <= checked * DEAD_FRACTION:
                break

        return removed

    def _evict(self, key: str) -> None:
        """Remove a key and its deadline; hint/pool entries stay lazy."""
        del self._data[key]
        self._expires.pop(key, None)

    def _track_expiring(self, key: str) -> None:
        """Add a key to the sampling pool once."""
        self._ttl_keys.append(key)


store = Store()
