"""Interactive command-line client for Kuyil."""

import shlex
import socket

from kuyil.protocol import MessageDecoder, encode_message

HOST = "127.0.0.1"
PORT = 6380
RECV_SIZE = 4096


def main() -> None:
    decoder = MessageDecoder()

    try:
        with socket.create_connection((HOST, PORT)) as conn:
            print(f"Connected to Kuyil at {HOST}:{PORT}")
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
