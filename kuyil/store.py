"""In-memory key-value store for Kuyil."""

import time
from dataclasses import dataclass


@dataclass
class StoreEntry:
    """A stored value plus its metadata.

    Extensible: future attributes (encoding, last-access time for LRU,
    type information) become new fields here.
    """

    value: object
    expires_at: float | None = None


class Store:
    """Key-value store with lazy expiry of dead entries."""

    def __init__(self) -> None:
        self._data: dict[str, StoreEntry] = {}

    def set(
        self, key: str, value: object, expires_at: float | None = None
    ) -> None:
        """Store a value under key with an optional expiry timestamp."""
        self._data[key] = StoreEntry(value=value, expires_at=expires_at)

    def get(self, key: str) -> StoreEntry | None:
        """Return a live entry, or None if missing or expired."""
        entry = self._data.get(key)
        if entry is None:
            return None

        if entry.expires_at is not None and entry.expires_at <= time.time():
            del self._data[key]
            return None

        return entry


store = Store()
