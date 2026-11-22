"""Interactive command-line client for Kuyil."""

import shlex
import socket
import sys
from urllib.parse import urlparse

from kuyil.protocol import MessageDecoder, encode_message

HOST = "127.0.0.1"
PORT = 6380
RECV_SIZE = 4096
SCHEME = "kuyil"


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
            print("Type PING or QUIT to exit.")

            while True:
                try:
                    line = input("kuyil> ").strip()
                except EOFError:
                    break

                if not line:
                    continue

                try:
                    command = shlex.split(line)
                except ValueError as exc:
                    print(f"Input error: {exc}")
                    continue

                if not command:
                    continue

                if command[0].upper() == "QUIT":
                    break

                conn.sendall(encode_message(command))

                while True:
                    data = conn.recv(RECV_SIZE)

                    if not data:
                        print("Server disconnected.")
                        return

                    responses = decoder.feed(data)

                    if responses:
                        for response in responses:
                            print(response)
                        break

    except ConnectionRefusedError:
        print("Could not connect. Is the Kuyil server running?")


if __name__ == "__main__":
    main()
