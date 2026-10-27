"""Command handling for Kuyil."""

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

    return f"ERR unknown command '{name}'"
