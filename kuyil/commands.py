"""Command handling and the in-memory key-value store for Kuyil."""

import time

# Each entry maps a key to (value, expires_at_epoch_or_None).
_STORE: dict[str, tuple[object, float | None]] = {}


def _get_live_entry(key: object) -> tuple[object, float | None] | None:
    """Return the stored entry, evicting the key first if it has expired."""
    entry = _STORE.get(key)  # type: ignore[arg-type]
    if entry is None:
        return None

    expires_at = entry[1]
    if expires_at is not None and expires_at <= time.time():
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

    _STORE[key] = (value, expires_at)
    return "OK"


def _handle_get(request: list) -> object:
    """GET key"""
    if len(request) != 2:
        return "ERR wrong number of arguments for 'get' command"

    entry = _get_live_entry(request[1])
    if entry is None:
        return None
    return entry[0]


def _handle_ttl(request: list) -> object:
    """TTL key — seconds remaining, -1 if no expiry, -2 if missing."""
    if len(request) != 2:
        return "ERR wrong number of arguments for 'ttl' command"

    entry = _get_live_entry(request[1])
    if entry is None:
        return -2
    if entry[1] is None:
        return -1
    return int(entry[1] - time.time())


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
