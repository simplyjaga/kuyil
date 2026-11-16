# Kuyil Notes

Learnings collected while reimplementing Redis internals.

## Divergences from the Redis Internals series

- **Python instead of Go** — the course implements in Go; Kuyil is Python.
- **MessagePack instead of RESP** — typed wire protocol, so command args
  may arrive as real ints/floats, not just bytes. Consequence: Kuyil is
  not a drop-in Redis replacement and needs its own client.
- **Radix tree for key eviction/expiry** — upcoming deviation: keys with
  deadlines kept ordered by expiry instead of random sampling, so the
  sweep walks the oldest deadlines and stops at the first live key.

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
- **Active:** Redis samples ~20 keys that have TTLs every 100ms, deletes
  dead ones, resamples if >25% were dead — lazy expiry alone can't
  reclaim keys nobody touches. Kuyil will use a radix tree instead
  (see divergences).
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
