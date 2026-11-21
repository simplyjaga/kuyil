"""Compressed radix tree mapping expiring key names to deadlines.

Mirrors Redis 7's ``db->expires`` rax: keys are stored by name (so
shared prefixes compress), each leaf carries the authoritative
deadline, and active expiration draws random samples by walking down
random child edges to a leaf.
"""

import random


class _Node:
    __slots__ = ("prefix", "children", "leaf")

    def __init__(self, prefix: bytes, leaf=None) -> None:
        self.prefix = prefix            # edge label from the parent
        self.children: dict[int, _Node] = {}
        self.leaf = leaf                # (key, deadline) on terminal nodes


class ExpiryTree:
    """Name-keyed radix tree of key -> absolute expiration timestamp."""

    def __init__(self) -> None:
        self._root = _Node(b"")
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def set(self, key: str, deadline: float) -> None:
        """Insert or overwrite the deadline for a key."""
        self._insert(self._root, key.encode(), (key, deadline))

    def get(self, key: str) -> float | None:
        """Return the deadline for a key, or None if it has none."""
        node = self._descend(key.encode())
        if node is None or node.leaf is None:
            return None
        return node.leaf[1]

    def sample(self) -> tuple[str, float] | None:
        """Return a random (key, deadline) leaf, or None when empty."""
        node = self._root
        while True:
            if node.leaf is not None and not node.children:
                return node.leaf
            if not node.children:
                return None

            # A leaf that shares a node with children competes as one option.
            options = list(node.children)
            if node.leaf is not None:
                options.append(-1)
            pick = random.choice(options)

            if pick == -1:
                return node.leaf
            node = node.children[pick]

    def remove(self, key: str) -> None:
        """Drop a key's deadline entry, if present."""
        encoded = key.encode()
        node = self._root
        path = []
        while encoded:
            child = node.children.get(encoded[0])
            if child is None or not encoded.startswith(child.prefix):
                return
            path.append((node, encoded[0]))
            encoded = encoded[len(child.prefix):]
            node = child

        if node.leaf is None:
            return

        node.leaf = None
        self._size -= 1
        self._prune(path)

    def _insert(self, node: _Node, s: bytes, leaf) -> None:
        if not s:
            if node.leaf is None:
                self._size += 1
            node.leaf = leaf
            return

        child = node.children.get(s[0])
        if child is None:
            node.children[s[0]] = _Node(s, leaf)
            self._size += 1
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

    def _descend(self, encoded: bytes) -> _Node | None:
        """Walk edge labels to the node that would hold a key."""
        node = self._root
        while encoded:
            child = node.children.get(encoded[0])
            if child is None or not encoded.startswith(child.prefix):
                return None
            encoded = encoded[len(child.prefix):]
            node = child
        return node

    @staticmethod
    def _prune(path: list) -> None:
        """Remove now-empty nodes walking back up the descent path."""
        for parent, b in reversed(path):
            child = parent.children[b]
            if child.leaf is not None or child.children:
                break
            del parent.children[b]
