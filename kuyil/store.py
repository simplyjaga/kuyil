"""In-memory key-value store with passive and active expiration."""

import time
from dataclasses import dataclass

from kuyil.rax import ExpiryTree


@dataclass
class StoreEntry:
    """A stored value.

    Expiration metadata lives separately in Store._expires, mirroring Redis's
    keyspace dictionary and secondary expires table.
    """

    value: object


class Store:
    """Key-value store with sampled active expiration.

    The expires table is a compressed radix tree (``ExpiryTree``), the
    Redis 7 design: deadlines are stored by key name, and active
    expiration draws random samples by walking random edges down to a
    leaf — no auxiliary sampling index required.
    """

    def __init__(self) -> None:
        self._data: dict[str, StoreEntry] = {}

        # Authoritative key -> absolute expiration timestamp (Unix seconds).
        self._expires = ExpiryTree()

    def set(
        self, key: str, value: object, expires_at: float | None = None
    ) -> None:
        """Store a value and replace any previous expiration metadata."""
        self._data[key] = StoreEntry(value=value)

        if expires_at is None:
            self._expires.remove(key)
        else:
            self._expires.set(key, expires_at)

    def get(self, key: str) -> StoreEntry | None:
        """Return a live entry, passively deleting it if already expired."""
        entry = self._data.get(key)
        if entry is None:
            return None

        expires_at = self._expires.get(key)
        if expires_at is not None and expires_at <= time.time():
            self._delete_key(key)
            return None

        return entry

    def get_expiry(self, key: str) -> float | None:
        """Return the authoritative expiry timestamp for a live key."""
        return self._expires.get(key)

    def delete(self, key: str) -> bool:
        """Remove a live key; return True if one existed."""
        if self.get(key) is None:
            return False

        self._delete_key(key)
        return True

    def set_expiry(self, key: str, expires_at: float) -> bool:
        """Set or replace a key's expiry; return False if the key is missing."""
        if self.get(key) is None:
            return False

        if expires_at <= time.time():
            self._delete_key(key)
            return True

        self._expires.set(key, expires_at)
        return True

    def active_expire_cycle(
        self,
        time_budget: float = 0.025,
        sample_size: int = 20,
        acceptable_stale: int = 10,
    ) -> tuple[int, int, float]:
        """Run one bounded, adaptive active-expiration cycle.

        Each iteration draws up to sample_size random leaves from the
        expires radix tree. Expired entries are deleted immediately. If
        the expired share is greater than acceptable_stale percent,
        another sample round is taken; otherwise the cycle stops. The
        time budget bounds how long this maintenance can occupy the
        event-loop thread.

        Returns (sampled_count, expired_count, elapsed_seconds).
        """
        started_at = time.monotonic()
        sampled_total = 0
        expired_total = 0

        while time.monotonic() - started_at < time_budget:
            if len(self._expires) == 0:
                break

            count = min(sample_size, len(self._expires))
            now = time.time()
            expired_in_sample = 0

            for _ in range(count):
                item = self._expires.sample()
                if item is None:
                    break
                key, expires_at = item
                if expires_at <= now:
                    self._delete_key(key)
                    expired_in_sample += 1

            sampled_total += count
            expired_total += expired_in_sample

            stale_percentage = expired_in_sample * 100 / count
            if stale_percentage <= acceptable_stale:
                break

        elapsed = time.monotonic() - started_at
        return sampled_total, expired_total, elapsed

    def _delete_key(self, key: str) -> None:
        """Delete a key from the keyspace and the expires tree."""
        self._data.pop(key, None)
        self._expires.remove(key)


store = Store()
