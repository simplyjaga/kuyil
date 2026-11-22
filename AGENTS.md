# Kuyil

Redis-inspired server built from scratch in Python, following Arpit
Bhayani's Redis Internals series.

## Environment

- Python lives in an isolated venv at `.venv/` — never install into
  system Python. Install deps: `.venv/bin/pip install -r requirements.txt`
- Run from the repo root (package imports require it):
  - `.venv/bin/python -m kuyil.epoll_server` — epoll server on :6380
  - `.venv/bin/python -m kuyil.server` — blocking server variant
  - `.venv/bin/python -m kuyil.cli [kuyil://host[:port]]` — interactive
    `kuyil>` client
- For ad-hoc testing, a tmux session named `kuyil` may hold a 4-pane
  layout: server + 3 clients.

## Wire protocol

- MessagePack over TCP on `127.0.0.1:6380` — NOT RESP. `redis-cli` will
  not work; test via the kuyil CLI or a raw `msgpack.packb([...])` socket.
- Commands arrive as MessagePack lists, e.g. `["SET", "k", "v", "EX", 5]`;
  args may be native ints/floats, not just strings.

## Conventions

- Feature work goes on a branch, opened as a PR, and squash-merged to
  `master`. Never merge without the user's explicit go-ahead.
- Both servers share `kuyil.commands.handle_command` — new commands are
  implemented there; storage lives behind `kuyil.store`.
- Design decisions and divergences from the series (MessagePack vs RESP,
  expiry internals, etc.) are journaled in `NOTES.md` — update it when a
  noteworthy decision is made.
- User-facing docs (commands, usage) go in `README.md`.

## Verification

- No test suite yet. Verify end-to-end by starting the epoll server and
  sending MessagePack commands over a raw socket; check expiry behavior
  with `time.sleep` between commands.
