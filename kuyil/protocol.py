"""MessagePack helpers for Kuyil's wire protocol."""

import msgpack


def encode_message(message: object) -> bytes:
    """Serialize one Python value into a MessagePack byte sequence."""
    return msgpack.packb(message, use_bin_type=True)


class MessageDecoder:
    """Incrementally decode MessagePack messages received over TCP."""

    def __init__(self) -> None:
        self._unpacker = msgpack.Unpacker(raw=False)

    def feed(self, data: bytes) -> list[object]:
        """Feed received bytes and return every complete decoded message."""
        self._unpacker.feed(data)
        return list(self._unpacker)
