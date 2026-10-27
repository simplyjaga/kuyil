import socket

HOST = "127.0.0.1"
PORT = 6380


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind((HOST, PORT))
        server.listen()

        print(f"Kuyil listening on {HOST}:{PORT}")

        while True:
            conn, addr = server.accept()
            print(f"Connected: {addr}...")

            with conn:
                while True:
                    data = conn.recv(1024)

                    if not data:
                        break

                    print(f"\nCommand: {data}")
                    conn.sendall(data)
            print("Connection Terminated...")


if __name__ == "__main__":
    main()
