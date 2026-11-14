"""Command handling for Kuyil."""

import time

from kuyil.store import store


def _parse_expiry_seconds(value: object) -> float | None:
    """Return the expiry duration in seconds, or None if invalid."""
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return float(value)


def _handle_set(request: list) -> object:
    """SET key value [EX seconds] — options parsed pairwise after the value."""
    if len(request) < 3:
        return "ERR wrong number of arguments for 'set' command"

    key, value = request[1], request[2]
    if not isinstance(key, str):
        return "ERR key must be a string"

    expires_at = None
    i = 3
    while i < len(request):
        option = request[i]
        if not isinstance(option, str):
            return "ERR syntax error"
        option = option.upper()

        if option == "EX":
            if i + 1 >= len(request):
                return "ERR syntax error"
            seconds = _parse_expiry_seconds(request[i + 1])
            if seconds is None:
                return "ERR invalid expire time in 'set' command"
            expires_at = time.time() + seconds
            i += 2
        else:
            return "ERR syntax error"

    store.set(key, value, expires_at=expires_at)
    return "OK"


def _handle_get(request: list) -> object:
    """GET key"""
    if len(request) != 2:
        return "ERR wrong number of arguments for 'get' command"

    entry = store.get(request[1])
    if entry is None:
        return None
    return entry.value


def _handle_ttl(request: list) -> object:
    """TTL key — seconds remaining, -1 if no expiry, -2 if missing."""
    if len(request) != 2:
        return "ERR wrong number of arguments for 'ttl' command"

    entry = store.get(request[1])
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
