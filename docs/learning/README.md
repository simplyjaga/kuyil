# Kuyil Learning Guide

This directory tracks the concepts explored while building Kuyil. It is intended to serve two purposes:

- **Quick revision:** revisit the systems and networking ideas behind each implementation.
- **A learning path:** help another contributor understand the concepts in sequence before changing the code.

The guide is separate from implementation documentation. The server code explains *what Kuyil does*; these notes explain *why it is designed that way* and the concepts we learned along the way.

## How to use this guide

1. Follow the topics in the order below.
2. Read the concept notes before studying the related implementation.
3. Treat status as a learning/project milestone, not as a claim that every production concern is solved.
4. Add a new topic page when a topic needs more than a short summary. Link it here.

## Learning path

| Order | Topic | What to understand | Status | Notes |
|---:|---|---|---|---|
| 1 | TCP server and socket lifecycle | TCP sockets, `bind`, `listen`, `accept`, `recv`, `sendall`, connection closure, and blocking behavior | Completed | Covered during the initial echo-server milestone |
| 2 | MessagePack protocol | Why Kuyil uses MessagePack, encoding/decoding, incremental decoding, and TCP read boundaries | Implemented / learning notes to expand | See the protocol and decoder implementation |
| 3 | Command handling: PING | Separating protocol handling from command dispatch; `PING` → `PONG` | Implemented | PING handler merged |
| 4 | Interactive CLI | A Redis-like command interface and parsing user input with `shlex` | Implemented / learning notes to expand | CLI milestone |
| 5 | Event loop and epoll | Non-blocking sockets, readiness notifications, registering file descriptors, and handling multiple clients in one thread | Learning / implementation next | [Event loop and epoll](topics/event-loop-and-epoll.md) |
| 6 | Partial reads and writes | TCP can deliver partial application messages; `send` can write only part of a response | Covered in event-loop design; implementation detail to verify | Included in the event-loop notes |
| 7 | Data structures and commands | Redis-like data types and command behavior | Planned | Add a page when this work begins |
| 8 | Expiration and key lifecycle | TTL, expiration checks, and cleanup strategies | Planned | Add a page when this work begins |
| 9 | Persistence | Saving and recovering server state | Planned | Add a page when this work begins |
| 10 | Eviction | Memory limits and eviction policies | Planned | Add a page when this work begins |

## Architecture milestones

### Initial TCP echo server

The first server is intentionally blocking and handles one client at a time. Its basic lifecycle is:

`socket()` → `bind()` → `listen()` → `accept()` → `recv()` / `sendall()` → close

The outer loop accepts a client; the inner receive loop serves that client. While the server is waiting on that client, it does not return to `accept()` to serve another one. Other connection attempts may complete their TCP handshake and wait in the operating system's listen backlog, but that does not mean the application has accepted or processed them.

### MessagePack request path

The protocol direction chosen for Kuyil is MessagePack rather than Redis RESP. This means the regular `redis-cli` is not a compatible client; Kuyil needs its own client/CLI.

The intended request path is:

`TCP bytes` → `incremental MessagePack decoder` → `command handler` → `MessagePack encoder` → `TCP response`

The decoder must preserve incomplete data between reads and may produce multiple complete messages from buffered input. Protocol handling, command handling, server connection management, and the CLI should remain separate responsibilities.

### Event-driven server

The next server milestone introduces a separate event-driven implementation rather than changing the original blocking server. On Linux, Python's `select.epoll()` interface can monitor registered file descriptors and report readiness events. The detailed concepts and planned flow are documented in [Event loop and epoll](topics/event-loop-and-epoll.md).

## Adding future topics

Keep pages focused. A useful topic page generally contains:

1. **Problem:** what limitation or question led us to this concept?
2. **Mental model:** explain the operating-system or programming concept in plain language.
3. **Kuyil connection:** where it appears in our architecture.
4. **Important distinctions:** common misconceptions and edge cases.
5. **Implementation flow:** how the concept maps to the code.
6. **Revision checklist:** a few questions to test understanding.
7. **References:** links to the relevant source files or learning material.

Prefer one page per substantial topic over continually appending long explanations to this index. Update the table above whenever a topic is added or its status changes.

## Learning source

Kuyil's main learning sequence is guided by Arpit Bhayani's Redis Internals playlist:

https://youtube.com/playlist?list=PLsdq-3Z1EPT0eElcdOON9fdaeaQjlyXDt
