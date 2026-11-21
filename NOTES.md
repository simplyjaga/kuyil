# Kuyil Notes

Learnings collected while reimplementing Redis internals.

## Divergences from the Redis Internals series

- **Python instead of Go** — the course implements in Go; Kuyil is Python.
- **MessagePack instead of RESP** — typed wire protocol, so command args
  may arrive as real ints/floats, not just bytes. Consequence: Kuyil is
  not a drop-in Redis replacement and needs its own client.
- **Radix tree for the expires table** — Kuyil stores `Store._expires`
  as a compressed radix tree keyed by key name (the Redis 7 design),
  sampled via random walks to leaves. The series' Redis-6 model uses a
  plain hash table plus adaptive sampling.

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
- Kuyil's expires table is a compressed radix tree (kuyil/rax.py) keyed
  by key name — the Redis 7 approach. A leaf holds the authoritative
  deadline; sampling descends random child edges to a leaf, so no
  auxiliary index or key-list copy is needed.
- **Time budget:** Redis 6's slow cycle uses up to 25% of the server.hz
  period. At the default 10 Hz, that is 25 ms per 100 ms period. Kuyil
  uses the same starting values in its epoll event loop.
- **Scope:** Kuyil currently implements the slow cycle only. Redis also
  has a fast cycle, multiple databases, tunable active-expire effort,
  and replication/AOF propagation, which are outside this step.
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
