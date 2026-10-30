"""Per-client state and non-blocking socket operations."""

import socket

from kuyil.commands import handle_command
from kuyil.protocol import MessageDecoder, encode_message

RECV_SIZE = 4096


class ClientConnection:
    """Own the protocol and buffered I/O state for one client."""

    def __init__(self, sock: socket.socket) -> None:
        self.socket = sock
        self.decoder = MessageDecoder()
        self.output_buffer = bytearray()
        self.read_closed = False

    def receive_available(self) -> bool:
        """Read available bytes and queue responses; return False on failure."""
        while True:
            try:
                data = self.socket.recv(RECV_SIZE)
            except BlockingIOError:
                return True
            except OSError:
                return False

            if not data:
                self.read_closed = True
                return True

            try:
                requests = self.decoder.feed(data)
            except Exception:
                return False

            for request in requests:
                print(f"Command: {request}")
                response = handle_command(request)
                self.output_buffer.extend(encode_message(response))

    def send_pending(self) -> bool:
        """Send queued bytes; retain unsent bytes for the next writable event."""
        while self.output_buffer:
            try:
                sent = self.socket.send(self.output_buffer)
            except BlockingIOError:
                return True
            except OSError:
                return False

            if sent == 0:
                return False

            del self.output_buffer[:sent]

        return True

    @property
    def wants_write(self) -> bool:
        return bool(self.output_buffer)

    @property
    def is_finished(self) -> bool:
        return self.read_closed and not self.output_buffer
