"""In-memory key-value store with passive and active expiration."""

import random
import time
from dataclasses import dataclass


@dataclass
class StoreEntry:
    """A stored value.

    Expiration metadata lives separately in Store._expires, mirroring Redis's
    keyspace dictionary and secondary expires dictionary.
    """

    value: object


class Store:
    """Key-value store with Redis-style sampled active expiration."""

    def __init__(self) -> None:
        self._data: dict[str, StoreEntry] = {}

        # Authoritative key -> absolute expiration timestamp (Unix seconds).
        self._expires: dict[str, float] = {}

        # Python dictionaries do not expose an O(1) random-entry operation.
        # Keep a dense list plus positions so sampling and removal are O(1)
        # per key, without copying every key on each expiration cycle.
        self._expiry_keys: list[str] = []
        self._expiry_positions: dict[str, int] = {}

    def set(
        self, key: str, value: object, expires_at: float | None = None
    ) -> None:
        """Store a value and replace any previous expiration metadata."""
        self._data[key] = StoreEntry(value=value)

        if expires_at is None:
            self._remove_expiry(key)
        else:
            self._set_expiry_index(key, expires_at)

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

        self._set_expiry_index(key, expires_at)
        return True

    def active_expire_cycle(
        self,
        time_budget: float = 0.025,
        sample_size: int = 20,
        acceptable_stale: int = 10,
    ) -> tuple[int, int, float]:
        """Run one bounded, adaptive active-expiration cycle.

        Each iteration samples up to sample_size keys with TTLs. Expired
        entries are deleted immediately. If the expired share is greater
        than acceptable_stale, another sample is taken; otherwise the cycle
        stops. The time budget bounds how long this maintenance can occupy
        the event-loop thread.

        Returns (sampled_count, expired_count, elapsed_seconds).
        """
        started_at = time.monotonic()
        sampled_total = 0
        expired_total = 0

        while time.monotonic() - started_at < time_budget:
            if not self._expiry_keys:
                break

            count = min(sample_size, len(self._expiry_keys))
            sample = random.sample(self._expiry_keys, count)
            if not sample:
                break

            now = time.time()
            expired_in_sample = 0

            for key in sample:
                expires_at = self._expires.get(key)
                if expires_at is not None and expires_at <= now:
                    self._delete_key(key)
                    expired_in_sample += 1

            sampled_total += len(sample)
            expired_total += expired_in_sample

            stale_percentage = expired_in_sample * 100 / len(sample)
            if stale_percentage <= acceptable_stale:
                break

        elapsed = time.monotonic() - started_at
        return sampled_total, expired_total, elapsed

    def _set_expiry_index(self, key: str, expires_at: float) -> None:
        """Update the expiry dictionary and add new keys to the sample set."""
        self._expires[key] = expires_at

        if key not in self._expiry_positions:
            self._expiry_positions[key] = len(self._expiry_keys)
            self._expiry_keys.append(key)

    def _remove_expiry(self, key: str) -> None:
        """Remove expiry metadata and its random-sampling index entry."""
        self._expires.pop(key, None)

        index = self._expiry_positions.pop(key, None)
        if index is None:
            return

        last_key = self._expiry_keys.pop()
        if index < len(self._expiry_keys):
            self._expiry_keys[index] = last_key
            self._expiry_positions[last_key] = index

    def _delete_key(self, key: str) -> None:
        """Delete a key from the keyspace and every expiry structure."""
        self._data.pop(key, None)
        self._remove_expiry(key)


store = Store()
