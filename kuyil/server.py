import socket

from kuyil.commands import handle_command
from kuyil.protocol import MessageDecoder, encode_message

HOST = "127.0.0.1"
PORT = 6380
RECV_SIZE = 4096


def main() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind((HOST, PORT))
        server.listen()

        print(f"Kuyil listening on {HOST}:{PORT}")

        while True:
            conn, addr = server.accept()
            print(f"Connected: {addr}")

            with conn:
                decoder = MessageDecoder()

                while True:
                    data = conn.recv(RECV_SIZE)

                    if not data:
                        break

                    for request in decoder.feed(data):
                        print(f"Command: {request}")
                        response = handle_command(request)
                        conn.sendall(encode_message(response))

            print("Connection terminated")


if __name__ == "__main__":
    main()
