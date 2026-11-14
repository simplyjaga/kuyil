"""Command handling and the in-memory key-value store for Kuyil."""

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


_STORE: dict[str, StoreEntry] = {}


def _get_live_entry(key: object) -> StoreEntry | None:
    """Return the stored entry, evicting the key first if it has expired."""
    entry = _STORE.get(key)  # type: ignore[arg-type]
    if entry is None:
        return None

    if entry.expires_at is not None and entry.expires_at <= time.time():
        del _STORE[key]  # type: ignore[arg-type]
        return None

    return entry


def _handle_set(request: list) -> object:
    """SET key value [EX seconds]"""
    if len(request) not in (3, 5):
        return "ERR wrong number of arguments for 'set' command"

    key, value = request[1], request[2]
    if not isinstance(key, str):
        return "ERR key must be a string"

    expires_at = None
    if len(request) == 5:
        option = request[3]
        if not isinstance(option, str) or option.upper() != "EX":
            return "ERR syntax error"

        seconds = request[4]
        if isinstance(seconds, str):
            try:
                seconds = float(seconds)
            except ValueError:
                return "ERR invalid expire time in 'set' command"
        if not isinstance(seconds, (int, float)) or seconds <= 0:
            return "ERR invalid expire time in 'set' command"

        expires_at = time.time() + seconds

    _STORE[key] = StoreEntry(value=value, expires_at=expires_at)
    return "OK"


def _handle_get(request: list) -> object:
    """GET key"""
    if len(request) != 2:
        return "ERR wrong number of arguments for 'get' command"

    entry = _get_live_entry(request[1])
    if entry is None:
        return None
    return entry.value


def _handle_ttl(request: list) -> object:
    """TTL key — seconds remaining, -1 if no expiry, -2 if missing."""
    if len(request) != 2:
        return "ERR wrong number of arguments for 'ttl' command"

    entry = _get_live_entry(request[1])
    if entry is None:
        return -2
    if entry.expires_at is None:
        return -1
    return int(entry.expires_at - time.time())


def handle_command(request: object) -> object:
    """Execute a decoded command and return its response value."""
    if not isinstance(request, list) or not request:
        return "ERR invalid command"

    name = request[0]
    if not isinstance(name, str):
        return "ERR command name must be a string"

    name = name.upper()

    if name == "PING":
        if len(request) != 1:
            return "ERR wrong number of arguments for PING"
        return "PONG"

    if name == "SET":
        return _handle_set(request)

    if name == "GET":
        return _handle_get(request)

    if name == "TTL":
        return _handle_ttl(request)

    return f"ERR unknown command '{name}'"
