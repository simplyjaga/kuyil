"""Append-only file (AOF) persistence.

Every mutating command is buffered after it executes, flushed to the OS
once per event-loop iteration (Redis's beforeSleep), and fsynced to disk
about once a second by a dedicated thread — Redis's appendfsync everysec,
where fsync is the only work offloaded to a BIO-style thread.
"""

import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

from kuyil.protocol import MessageDecoder, encode_message

# Anchored to the repo root, not the process cwd — a server launched from
# elsewhere still reads and writes the same kuyil.aof.
AOF_PATH = Path(__file__).parent.parent / "kuyil.aof"
FSYNC_INTERVAL = 1.0


class Aof:
    """Append-only command log with buffered writes and periodic fsync."""

    def __init__(self, path: Path = AOF_PATH) -> None:
        self._path = path
        self._buffer = bytearray()
        self._replaying = False
        self._file = open(path, "ab")
        threading.Thread(target=self._fsync_loop, daemon=True).start()

    def record(self, command: list) -> None:
        """Buffer a mutating command; flushed once per event-loop iteration."""
        if self._replaying:
            return
        self._buffer += encode_message(command)

    def flush(self) -> None:
        """Write buffered commands to the OS page cache (beforeSleep)."""
        if not self._buffer:
            return
        self._file.write(self._buffer)
        self._buffer.clear()
        self._file.flush()

    def load(self, replay: Callable[[list], object]) -> int:
        """Replay every logged command; a torn final frame stops the replay.

        Reads in chunks rather than slurping the whole file — a multi-GB
        AOF must not need multi-GB of RAM to load. Split frames simply
        stay buffered in the decoder until the rest arrives.
        """
        self._replaying = True
        decoder = MessageDecoder()
        count = 0
        try:
            with open(self._path, "rb") as file:
                while chunk := file.read(64 * 1024):
                    for command in decoder.feed(chunk):
                        replay(command)
                        count += 1
        finally:
            self._replaying = False
        return count

    def _fsync_loop(self) -> None:
        """fsync the AOF fd roughly once a second — never touches our state."""
        while True:
            time.sleep(FSYNC_INTERVAL)
            os.fsync(self._file.fileno())


aof = Aof()
