"""Interactive command-line client for Kuyil."""

import shlex
import socket
import sys
from urllib.parse import urlparse

from kuyil import HOST, PORT
from kuyil.protocol import MessageDecoder, encode_message

RECV_SIZE = 4096
SCHEME = "kuyil"
PIPE_SEPARATOR = "|"


def parse_target(argv: list[str]) -> tuple[str, int]:
    """Resolve the server address from an optional kuyil:// URL argument."""
    if len(argv) < 2:
        return HOST, PORT

    parsed = urlparse(argv[1])
    if parsed.scheme != SCHEME:
        sys.exit(
            f"unsupported scheme '{parsed.scheme or argv[1]}' — "
            f"expected {SCHEME}://host[:port]"
        )
    return parsed.hostname or HOST, parsed.port or PORT


def main() -> None:
    host, port = parse_target(sys.argv)
    decoder = MessageDecoder()

    try:
        with socket.create_connection((host, port)) as conn:
            print(f"Connected to Kuyil at {host}:{port}")
            print("Type commands, QUIT to exit. Separate commands with | to pipeline.")

            while True:
                try:
                    line = input("kuyil> ").strip()
                except EOFError:
                    break

                if not line:
                    continue

                try:
                    commands = [shlex.split(part) for part in line.split(PIPE_SEPARATOR)]
                except ValueError as exc:
                    print(f"Input error: {exc}")
                    continue

                commands = [command for command in commands if command]

                if not commands:
                    continue

                if len(commands) == 1 and commands[0][0].upper() == "QUIT":
                    break

                conn.sendall(b"".join(encode_message(command) for command in commands))

                received = 0
                while received < len(commands):
                    data = conn.recv(RECV_SIZE)

                    if not data:
                        print("Server disconnected.")
                        return

                    for response in decoder.feed(data):
                        received += 1
                        print(response)

    except ConnectionRefusedError:
        print("Could not connect. Is the Kuyil server running?")


if __name__ == "__main__":
    main()
