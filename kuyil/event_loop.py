"""Linux epoll event loop for Kuyil's TCP server."""

import select
import socket

from kuyil.client import ClientConnection

HOST = "127.0.0.1"
PORT = 6380
MAX_EVENTS = 100
POLL_TIMEOUT = 1.0


class EpollServer:
    """Accept clients and dispatch their socket readiness events."""

    def __init__(self) -> None:
        if not hasattr(select, "epoll"):
            raise RuntimeError("Kuyil's epoll server is supported on Linux only.")

        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.setblocking(False)
        self._server.bind((HOST, PORT))
        self._server.listen()

        self._epoll = select.epoll()
        self._clients: dict[int, ClientConnection] = {}
        self._closed = False
        self._epoll.register(self._server.fileno(), select.EPOLLIN)

        print(f"Kuyil epoll server listening on {HOST}:{PORT}")

    def run(self) -> None:
        """Wait for readiness events until interrupted."""
        try:
            while True:
                try:
                    events = self._epoll.poll(POLL_TIMEOUT, MAX_EVENTS)
                except InterruptedError:
                    continue

                for fd, event_mask in events:
                    if fd == self._server.fileno():
                        self._accept_connections()
                    else:
                        self._handle_client_event(fd, event_mask)
        finally:
            self.close()

    def _accept_connections(self) -> None:
        """Accept all connections currently waiting in the listen queue."""
        while True:
            try:
                client_socket, address = self._server.accept()
            except BlockingIOError:
                return
            except OSError as exc:
                print(f"Accept failed: {exc}")
                return

            client_socket.setblocking(False)
            fd = client_socket.fileno()
            self._clients[fd] = ClientConnection(client_socket)

            try:
                self._epoll.register(fd, select.EPOLLIN)
            except OSError as exc:
                print(f"Could not register {address}: {exc}")
                self._close_client(fd)
                continue

            print(f"Connected: {address}")

    def _handle_client_event(self, fd: int, event_mask: int) -> None:
        connection = self._clients.get(fd)
        if connection is None:
            return

        read_events = select.EPOLLIN | select.EPOLLRDHUP | select.EPOLLHUP

        if event_mask & read_events:
            if not connection.receive_available():
                self._close_client(fd)
                return

        if event_mask & select.EPOLLOUT:
            if not connection.send_pending():
                self._close_client(fd)
                return

        if event_mask & (select.EPOLLERR | select.EPOLLHUP):
            self._close_client(fd)
            return

        if connection.is_finished:
            self._close_client(fd)
            return

        self._update_interest(fd, connection)

    def _update_interest(self, fd: int, connection: ClientConnection) -> None:
        """Watch writes only while there are response bytes waiting."""
        events = 0

        if not connection.read_closed:
            events |= select.EPOLLIN

        if connection.wants_write:
            events |= select.EPOLLOUT

        if not events:
            self._close_client(fd)
            return

        try:
            self._epoll.modify(fd, events)
        except OSError as exc:
            print(f"Could not update epoll interest for fd {fd}: {exc}")
            self._close_client(fd)

    def _close_client(self, fd: int) -> None:
        """Unregister and close a client connection."""
        connection = self._clients.pop(fd, None)
        if connection is None:
            return

        try:
            self._epoll.unregister(fd)
        except OSError:
            pass

        connection.socket.close()
        print(f"Connection closed: fd {fd}")

    def close(self) -> None:
        """Close all client sockets, the listening socket, and epoll."""
        if self._closed:
            return

        self._closed = True

        for fd in list(self._clients):
            self._close_client(fd)

        try:
            self._epoll.unregister(self._server.fileno())
        except OSError:
            pass

        self._epoll.close()
        self._server.close()
