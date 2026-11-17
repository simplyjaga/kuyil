"""Compressed radix tree for expiration hints.

Hints are stored under the byte string ``pack(">d", deadline) + key``.
Positive IEEE-754 doubles have monotonically increasing bit patterns,
so the 8-byte big-endian encoding sorts lexicographically the same way
deadlines sort numerically — the leftmost leaf is always the nearest
deadline.
"""

import struct


class _Node:
    __slots__ = ("prefix", "children", "leaf")

    def __init__(self, prefix: bytes, leaf=None) -> None:
        self.prefix = prefix            # edge label from the parent
        self.children: dict[int, _Node] = {}
        self.leaf = leaf                # (key, deadline) on terminal nodes


def _encode(key: str, deadline: float) -> bytes:
    return struct.pack(">d", deadline) + key.encode()


class ExpiryHintTree:
    """Deadline-ordered hints of keys approaching expiration."""

    def __init__(self) -> None:
        self._root = _Node(b"")
        self._by_key: dict[str, float] = {}

    def __len__(self) -> int:
        return len(self._by_key)

    def insert(self, key: str, deadline: float) -> None:
        """Add or refresh a hint; a newer deadline replaces the old one."""
        old = self._by_key.get(key)
        if old == deadline:
            return
        if old is not None:
            self.remove(key)
        self._insert(self._root, _encode(key, deadline), (key, deadline))
        self._by_key[key] = deadline

    def _insert(self, node: _Node, s: bytes, leaf) -> None:
        if not s:
            node.leaf = leaf
            return

        child = node.children.get(s[0])
        if child is None:
            node.children[s[0]] = _Node(s, leaf)
            return

        i = 0
        limit = min(len(child.prefix), len(s))
        while i < limit and child.prefix[i] == s[i]:
            i += 1

        if i == len(child.prefix):
            self._insert(child, s[i:], leaf)
            return

        # Divergence inside the edge label: split it.
        mid = _Node(child.prefix[:i])
        child.prefix = child.prefix[i:]
        mid.children[child.prefix[0]] = child
        node.children[s[0]] = mid
        self._insert(mid, s[i:], leaf)

    def peek_earliest(self):
        """Return the (key, deadline) with the nearest deadline, or None."""
        node = self._root
        while node.leaf is None:
            if not node.children:
                return None
            node = node.children[min(node.children)]
        return node.leaf

    def pop_earliest(self):
        """Remove and return the (key, deadline) with the nearest deadline."""
        path = []
        node = self._root
        while node.leaf is None:
            if not node.children:
                return None
            b = min(node.children)
            path.append((node, b))
            node = node.children[b]

        leaf = node.leaf
        node.leaf = None
        self._prune(path)
        del self._by_key[leaf[0]]
        return leaf

    def remove(self, key: str) -> None:
        """Drop a hint by key, if present."""
        deadline = self._by_key.get(key)
        if deadline is None:
            return

        s = _encode(key, deadline)
        node = self._root
        path = []
        while s:
            child = node.children.get(s[0])
            if child is None or not s.startswith(child.prefix):
                return
            path.append((node, s[0]))
            s = s[len(child.prefix):]
            node = child

        node.leaf = None
        self._prune(path)
        del self._by_key[key]

    @staticmethod
    def _prune(path: list) -> None:
        """Remove now-empty nodes walking back up the descent path."""
        for parent, b in reversed(path):
            child = parent.children[b]
            if child.leaf is not None or child.children:
                break
            del parent.children[b]
