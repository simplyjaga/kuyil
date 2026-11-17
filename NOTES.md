# Kuyil Notes

Learnings collected while reimplementing Redis internals.

## Divergences from the Redis Internals series

- **Python instead of Go** — the course implements in Go; Kuyil is Python.
- **MessagePack instead of RESP** — typed wire protocol, so command args
  may arrive as real ints/floats, not just bytes. Consequence: Kuyil is
  not a drop-in Redis replacement and needs its own client.
- **Radix tree for key eviction/expiry** — keys approaching their
  deadline are kept ordered in a compressed radix tree so the sweep
  walks the nearest deadlines first. Sampling still runs (as in
  Redis 6); the tree supplements it with hints, it does not replace it.

## Topic notes

### Variadic command parsing

- Real Redis `SET` takes variadic options:
  `SET key value [NX|XX] [GET] [EX s|PX ms|EXAT t|PXAT t|KEEPTTL]`.
- Parsed by walking argv in a loop — each option consumes itself plus
  however many arguments it needs (`NX` takes 0, `EX` takes 1). Fixed
  arity checks can't express this.

### Expiry

- **Lazy (passive):** on access, if `expires_at <= now`, evict and report
  missing. Implemented in `Store.get()`.
- **Active (implemented, Redis 6 model):** three structures —
  `_data` (pairs), `_expires` (authoritative deadlines), and a radix
  `_hints` tree. Every ~100ms the event loop runs a bounded cycle:
  drain due hints, then sample up to 20 keys from the expires table,
  deleting dead ones and recording near-dead ones as hints. Repeats
  while >25% of a sample was dead or the time budget is spent.
  Hints are verified against `_expires` before deleting, so stale
  hints (updated TTL, deleted keys) can never kill a live key.
- `EXPIRE key 0` (or negative) deletes immediately, as in Redis.
- `TTL` sentinels: `-2` missing, `-1` no expiry. `int()` truncation can
  report 0 for sub-second keys — faithful to Redis.
- `SET` without an expiry option clears an existing TTL on the key.

### Stored values as objects

- Values are stored as `StoreEntry` (value + metadata) rather than bare
  values — the seed of Redis's `robj`, which carries type, encoding,
  and LRU metadata alongside the value.

### Event loop & concurrency

- Single-threaded: Linux `epoll` watches the listen socket plus every
  client fd; readable events drive per-client `ClientConnection` state
  machines. `EPOLLOUT` is watched only while response bytes are pending.

### Pipelining

- The server already supports client pipelining for free: msgpack frames
  are self-delimiting and `MessageDecoder.feed()` returns all complete
  messages per `recv()`, so N commands in one write produce N buffered
  responses in one read.
- Missing piece: `cli.py` sends one command per prompt. Client-side
  batching is the remaining work for the pipelining episode.
