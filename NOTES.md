# Kuyil Notes

Design and protocol learnings collected while reimplementing Redis internals.

## Wire protocol: MessagePack vs RESP

- RESP is a string protocol — every command arrives as an array of bulk
  strings. `EXPIRE foo 10` reaches the server as `["EXPIRE", "foo", "10"]`
  with `10` as bytes, not a number.
- Redis converts each argument lazily at the command layer
  (`getLongLongFromObjectOrReply` and friends). Same pattern Kuyil uses.
- MessagePack is typed: clients may send real ints/floats. Handlers must
  accept `"10"` and `10` uniformly — `float(value)` in a try/except
  covers both without isinstance chains.
- RESP3 (Redis 6+) added typed replies (numbers, booleans, nulls) but
  commands are still sent as string arrays.

## Variadic command parsing

- Real Redis `SET` takes variadic trailing options:
  `SET key value [NX|XX] [GET] [EX s|PX ms|EXAT t|PXAT t|KEEPTTL]`.
- It walks argv in a loop — each option consumes itself plus however many
  arguments it needs (`NX` takes 0, `EX` takes 1). Kuyil mirrors this:
  fixed-arity checks like `len(request) == 5` can't express this.

## Expiry

- Two mechanisms, like real Redis:
  - **Lazy (passive):** on every access, if `expires_at <= now`, evict and
    report the key as missing. Implemented in `Store.get()`.
  - **Active:** Redis samples ~20 keys that have TTLs every 100ms and
    deletes dead ones; if >25% of the sample was dead it resamples
    immediately. Lazy expiry alone can't reclaim keys nobody touches.
    (Not yet implemented — natural fit for the epoll loop's poll timeout.)
- `EXPIRE key 0` (or negative) deletes the key immediately, as in Redis.
- `TTL` sentinels: `-2` missing, `-1` no expiry. `int()` truncation can
  report 0 for sub-second keys — faithful to Redis's own behavior.

## Stored values as objects

- Values are stored as `StoreEntry` (value + expires_at) rather than bare
  values or positional tuples — the seed of Redis's `robj`, which carries
  type, encoding, and LRU metadata alongside the value.

## Event loop & concurrency

- The server is single-threaded: Linux `epoll` watches the listen socket
  plus every client fd; readable events drive per-client
  `ClientConnection` state machines with an output buffer watched via
  `EPOLLOUT` only when data is pending.

## Pipelining

- The server already supports client pipelining for free: msgpack frames
  are self-delimiting and `MessageDecoder.feed()` returns all complete
  messages per `recv()`, so N commands in one write produce N buffered
  responses in one read.
- Missing piece: `cli.py` sends one command per prompt. Client-side
  batching is the remaining work for the pipelining episode.
