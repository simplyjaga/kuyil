# Kuyil 🐦

A Redis-inspired server built from scratch in Python,
following Arpit Bhayani's Redis Internals series.

Uses MessagePack as its wire protocol on `127.0.0.1:6380`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Running

```bash
.venv/bin/python -m kuyil.epoll_server   # epoll-based server (recommended)
.venv/bin/python -m kuyil.server         # simple blocking server
.venv/bin/python -m kuyil.cli            # interactive client (localhost)
.venv/bin/python -m kuyil.cli kuyil://localhost:6380   # explicit target
```

The client accepts a `kuyil://host[:port]` URL, like `redis://` in the
Redis ecosystem — host defaults to `127.0.0.1`, port to `6380`.

## Commands

| Command | Description |
| --- | --- |
| `PING` | Returns `PONG` |
| `SET key value [EX seconds]` | Store a value, optionally with expiry |
| `GET key` | Return the value, or nil if missing/expired |
| `TTL key` | Seconds until expiry; `-1` no expiry, `-2` missing |
| `EXPIRE key seconds` | Set a deadline on an existing key (`1`/`0`) |
| `EXPIREAT key unix-seconds` | Set an absolute deadline (`1`/`0`) |
| `DEL key [key ...]` | Delete keys; returns count removed |

### Example session

```
kuyil> SET name jaga
OK
kuyil> GET name
jaga
kuyil> SET session abc123 EX 60
OK
kuyil> TTL session
59
kuyil> DEL session
1
```

### Pipelining

Separate commands with `|` to send them in a single round trip:

```
kuyil> PING | SET batch 1 | GET batch
PONG
OK
1
```

## Persistence

Every mutating command is appended to `kuyil.aof` (msgpack frames) and
replayed on startup — roughly Redis's `appendfsync everysec`: writes are
buffered and flushed once per event-loop iteration, while a background
thread `fsync`s about once a second.

```
kuyil> SET name jaga
OK          # restart the server here
kuyil> GET name
jaga        # restored from kuyil.aof
```

`SET ... EX` and `EXPIRE` are logged as `EXPIREAT` with the absolute
deadline so a replay doesn't restart the clock. `kuyil.aof` is
gitignored — delete it to start clean.
