# Kuyil Notes

Learnings collected while reimplementing Redis internals.

## Divergences from the Redis Internals series

- **Python instead of Go** — the course implements in Go; Kuyil is Python.
- **MessagePack instead of RESP** — typed wire protocol, so command args
  may arrive as real ints/floats, not just bytes. Consequence: Kuyil is
  not a drop-in Redis replacement and needs its own client.
- **`kuyil://` connection URLs** — like `redis://`/`rediss://`, the CLI
  takes a scheme-prefixed URL (`kuyil://host[:port]`). It is a
  client-side convention only: the URL is parsed into host/port before
  opening the socket; nothing goes on the wire. No `kuyils://` — that
  would mean TLS.
- **Expires index instead of radix tree** — Kuyil samples TTL keys via a
  dense list + position map (O(1) sample and delete). A compressed radix
  tree keyed by name (the Redis 7 `db->expires` design) was also
  implemented and evaluated — it folds dict and index into one structure
  and samples via random walks — but the simpler list index was kept;
  the rax work remains in git history.

## Topic notes

### Variadic command parsing

- Real Redis SET takes variadic options:
  SET key value [NX|XX] [GET] [EX s|PX ms|EXAT t|PXAT t|KEEPTTL].
- Parsed by walking argv in a loop — each option consumes itself plus
  however many arguments it needs (NX takes 0, EX takes 1). Fixed
  arity checks can't express this.

### Expiry

- **Lazy (passive):** on access, if expires_at <= now, evict and report
  missing. Implemented in Store.get().
- **Active:** Redis samples keys from its secondary expires dictionary.
  In Redis 6.0/6.2, the default batch is 20 keys and the cycle repeats
  while more than 10% of the sampled keys are expired, subject to a
  time budget. This is adaptive cleanup, not a full scan.
- Redis stores expiration metadata separately from the main keyspace.
  Kuyil mirrors this with Store._expires.
- Kuyil maintains a dense list and key-to-position map alongside the
  expires dictionary. Python dict has no O(1) random-entry operation;
  this index lets us sample keys without copying the entire dictionary.
- **Time budget:** Redis 6's slow cycle uses up to 25% of the server.hz
  period. At the default 10 Hz, that is 25 ms per 100 ms period. Kuyil
  uses the same starting values in its epoll event loop.
- **Scope:** Kuyil currently implements the slow cycle only. Redis also
  has a fast cycle, multiple databases, tunable active-expire effort,
  and replication/AOF propagation, which are outside this step.
- **Why no GC/sweeper thread:** single-threaded is the value — every
  command runs atomically with zero locking. A sweeper thread touching
  dict/expires would force locks around every command and concurrent
  data structures throughout. Expiry is also only an optimization
  (passive expiry already guarantees correctness), so it can be
  best-effort sampling rather than a thorough scan, bounded by a time
  budget for predictable tail latency. Same pattern as incremental
  rehashing and active defrag. Redis does use BIO threads, but only
  for offloadable blocking work (UNLINK, fsync) — never core state.
- EXPIRE key 0 (or negative) deletes immediately.
- TTL sentinels: -2 missing, -1 no expiry. int() truncation can report
  0 for sub-second keys — faithful to Redis.
- SET without an expiry option clears an existing TTL on the key.

### Stored values as objects

- Values are stored as StoreEntry (value + future metadata) rather than
  bare values — the seed of Redis's robj, which carries type, encoding,
  and LRU metadata alongside the value.

### Event loop & concurrency

- Single-threaded: Linux epoll watches the listen socket plus every
  client fd; readable events drive per-client ClientConnection state
  machines. EPOLLOUT is watched only while response bytes are pending.

### Pipelining

- The server already supports client pipelining for free: msgpack frames
  are self-delimiting and MessageDecoder.feed() returns all complete
  messages per recv(), so N commands in one write produce N buffered
  responses in one read.
- Missing piece: cli.py sends one command per prompt. Client-side
  batching is the remaining work for the pipelining episode.
