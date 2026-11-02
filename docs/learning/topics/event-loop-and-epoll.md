# Event Loop and epoll

This note explains the event-driven server concepts being introduced in Kuyil. It uses Python and Linux terminology and builds on our existing TCP server and MessagePack protocol.

> **Core idea:** An event loop lets one thread manage many connections without waiting for any individual connection to send or receive data.

This is a conceptual guide to the design. It is not a claim that the event-driven server implementation is complete.

## 1. Start with the two kinds of sockets

Our TCP server works with two distinct kinds of sockets:

- **Listening socket:** waits for incoming connections. We call `accept()` on it.
- **Client connection socket:** represents an accepted client connection. We call `recv()` and `send()` on it.

When a client connects, the operating system establishes the TCP connection and `accept()` returns a new socket for that client. The listening socket remains available to accept more clients.

This distinction matters because epoll monitors both kinds of sockets, but readiness means something different for each:

- Listening socket is readable → a connection can be accepted.
- Client socket is readable → data can be received, or the connection state has changed.

## 2. Blocking and non-blocking sockets

Consider:

```python
data = client_socket.recv(4096)
```

With a blocking socket, if no data is available, `recv()` waits. The thread cannot move on to another client until the call returns.

That is the limitation in our initial server: its inner receive loop serves one client, so it cannot return to the outer `accept()` loop while that client remains connected.

A non-blocking socket behaves differently:

```python
client_socket.setblocking(False)
```

If an operation cannot make progress immediately, it raises `BlockingIOError` instead of waiting:

```python
try:
    data = client_socket.recv(4096)
except BlockingIOError:
    # No data is available right now; return to the event loop.
    pass
```

Non-blocking mode does not itself tell us which socket needs attention. It only ensures that an attempted operation does not unexpectedly wait.

Both the listening socket and accepted client sockets must be non-blocking in this event-loop design. Otherwise, `accept()`, `recv()`, or `send()` could stall the single event-loop thread.

## 3. What epoll does

Linux epoll is a kernel-provided readiness notification mechanism.

Instead of repeatedly checking every client socket, our application tells the kernel which file descriptors it is interested in and which events it wants to hear about. The application then waits for notifications.

In Python:

```python
import select

epoll = select.epoll()
```

Creating the epoll instance does **not** automatically monitor any socket. We must register each socket.

The epoll instance tracks the file descriptors we register, the events we are interested in, and which registered descriptors are ready.

## 4. Readiness events

The main events in our initial design are:

| Event | Meaning |
|---|---|
| `select.EPOLLIN` | The socket is ready for reading |
| `select.EPOLLOUT` | The socket is ready for writing |

### `EPOLLIN`

For a listening socket, `EPOLLIN` means a connection is ready to be accepted.

For a client socket, it means a read can make progress. We still need to call `recv()` to retrieve the bytes.

Epoll does not read the bytes, decode MessagePack, or execute a command. It only reports readiness.

### `EPOLLOUT`

A socket is writable when it can currently accept outgoing data. This does not mean the remote client has received or processed the data.

A non-blocking `send()` may send fewer bytes than requested. If bytes remain, we keep them in an output buffer and wait for the socket to become writable again.

A socket is commonly writable when there is no pending output, so we should not monitor `EPOLLOUT` permanently. Enable it while a connection has pending output, then disable it when the output buffer is empty.

## 5. File descriptors and registration

A socket's `fileno()` method returns the file descriptor used by the operating system to identify it:

```python
fd = server.fileno()
```

There are three distinct operations to remember:

- **`register(fd, events)`:** initially adds a file descriptor to the epoll instance and tells epoll which events to monitor for it.
- **`modify(fd, events)`:** changes the event mask for a file descriptor that is already registered. It does not add a new descriptor.
- **`unregister(fd)`:** removes the descriptor from the epoll instance when we no longer want to monitor it.

Register the listening socket for readability:

```python
epoll.register(server.fileno(), select.EPOLLIN)
```

When a client has pending output, modify its existing registration to monitor both reading and writing:

```python
epoll.modify(
    client_socket.fileno(),
    select.EPOLLIN | select.EPOLLOUT,
)
```

When the output buffer becomes empty, modify the registration again to monitor only reading:

```python
epoll.modify(client_socket.fileno(), select.EPOLLIN)
```

When the connection is being removed, unregister its descriptor:

```python
epoll.unregister(client_socket.fileno())
```

**Quick distinction:** use `register()` once when adding a descriptor; use `modify()` later when changing the events of that already-registered descriptor.

## 6. Waiting for events with `poll()`

```python
events = epoll.poll(timeout=1.0, maxevents=100)
```

This waits for up to one second and returns at most 100 ready events. Each returned item contains a file descriptor and an event mask, for example:

```python
[
    (5, select.EPOLLIN),
]
```

This means file descriptor `5` is ready for reading.

### One descriptor can have multiple events at once

A single `poll()` result can report more than one readiness condition for the same file descriptor. For example:

```python
[
    (client1_fd, select.EPOLLIN | select.EPOLLOUT),
]
```

This is **one event tuple for one client descriptor**, with a combined bitmask:

- `EPOLLIN`: the client socket is ready for reading.
- `EPOLLOUT`: the client socket is ready for writing.

Both conditions are reported together. The event loop should inspect the mask and handle each relevant condition; it should not assume that a returned tuple represents exactly one event.

Use bitwise checks because the mask can contain multiple flags:

```python
for fd, event_mask in epoll.poll():
    if event_mask & select.EPOLLIN:
        handle_readable(fd)

    if event_mask & select.EPOLLOUT:
        handle_writable(fd)
```

The two checks are independent, so both handlers can run for the same descriptor during one iteration. In the real server, look up the connection state for `fd` and pass that connection to the relevant read/write handling logic.

The important distinction:

- `client_socket.recv(...)` waits for that particular socket when it is blocking.
- `epoll.poll(...)` waits for activity on any registered socket.

Waiting in `epoll.poll()` is intentional. The thread can sleep until one of the monitored sockets becomes ready instead of repeatedly polling every client in Python.

## 7. Why we need both epoll and non-blocking sockets

Epoll readiness is not a promise that an entire application message is available or that a later operation can never encounter `BlockingIOError`.

For example, a MessagePack message may arrive across multiple TCP reads. A readable notification means reading can make progress; it does not mean the full MessagePack message has arrived.

There can also be less data available by the time our code performs the read. Non-blocking mode ensures that the event loop can handle this safely rather than getting stuck.

Remember:

- **Epoll:** tells us which registered sockets are ready to make progress.
- **Non-blocking mode:** ensures an I/O operation returns control instead of waiting when it cannot make progress.

They solve different problems and work together.

## 8. Per-client connection state

Each client needs independent protocol and output state. One client may have sent only part of a MessagePack message while another has sent a complete one. One client may also have pending response bytes while another has nothing to send.

A connection object can hold that state:

```python
class ClientConnection:
    def __init__(self, sock):
        self.socket = sock
        self.decoder = MessagePackDecoder()
        self.output_buffer = bytearray()
```

The event loop can keep a mapping from file descriptor to connection:

```python
clients = {
    client_socket.fileno(): ClientConnection(client_socket)
}
```

This keeps each client's decoder buffer and pending output separate.

## 9. Event-loop lifecycle

The intended high-level flow is:

1. Create the listening TCP socket.
2. Set it to non-blocking mode.
3. Bind and listen.
4. Create an epoll instance.
5. Register the listening socket for `EPOLLIN`.
6. Repeatedly call `epoll.poll()`.
7. For a listening-socket event, accept pending connections.
8. Set each accepted socket to non-blocking mode, create its connection state, and register it.
9. For a client `EPOLLIN` event, read available bytes, feed the incremental MessagePack decoder, and dispatch complete messages to command handlers.
10. Encode responses and add them to that client's output buffer.
11. Attempt to send pending bytes. If bytes remain, use `modify()` to include `EPOLLOUT`; when the buffer empties, use `modify()` to remove it.
12. On disconnect or error, unregister the descriptor, remove its connection state, and close the socket.

### Accepting pending connections

When the listening socket is reported readable, accept repeatedly until `BlockingIOError`:

```python
while True:
    try:
        client_socket, address = server.accept()
    except BlockingIOError:
        break

    client_socket.setblocking(False)
    # Create connection state and register the client.
```

This drains the currently pending connections rather than accepting only one.

### Reading client data

```python
try:
    data = connection.socket.recv(4096)
except BlockingIOError:
    data = None

if data == b"":
    # The peer has closed its connection.
    ...
elif data:
    messages = connection.decoder.feed(data)
    for message in messages:
        response = handle_command(message)
        connection.output_buffer.extend(encode_message(response))
```

Keep these cases distinct:

- `BlockingIOError`: no bytes can be read right now.
- `b""`: the peer has closed its writing side / the connection has reached EOF.
- Non-empty bytes: feed them to the incremental decoder.

### Writing responses

`send()` may write only part of the supplied buffer:

```python
sent = connection.socket.send(connection.output_buffer)
del connection.output_buffer[:sent]
```

Only remove the bytes that were actually sent. If `send()` raises `BlockingIOError`, retain the remaining bytes and wait for `EPOLLOUT`.

Try sending immediately after generating a response; do not wait for a writable notification if the socket can already accept the data.

Once the output buffer is empty, use `modify()` to monitor `EPOLLIN` only. Keeping `EPOLLOUT` enabled all the time can cause unnecessary repeated notifications because sockets are usually writable.

## 10. Disconnects and cleanup

Relevant epoll flags include:

| Event | Meaning |
|---|---|
| `select.EPOLLHUP` | The connection has hung up |
| `select.EPOLLERR` | A socket error occurred |
| `select.EPOLLRDHUP` | The peer closed its writing side |

A client disconnect can also be detected when `recv()` returns `b""`.

Cleanup should unregister the descriptor, remove the connection from the client mapping, and close the socket. Make cleanup safe to call only once. Also, do not blindly discard readable data just because a hangup-related flag is present; unread data may still need to be processed.

## 11. Where this fits in Kuyil

The event loop should manage sockets and connection state, not command semantics.

The responsibilities remain separate:

- **Event loop / server:** accept connections, read and write bytes, manage client state.
- **Protocol decoder/encoder:** convert between TCP bytes and MessagePack messages.
- **Command handler:** process commands such as `PING`.
- **CLI:** let a user interact with Kuyil.

The existing blocking server should remain intact while the event-driven implementation is introduced separately.

## 12. Implementation checklist

- [ ] Create a separate event-driven server module.
- [ ] Set the listening socket and accepted client sockets to non-blocking mode.
- [ ] Create an epoll instance and register the listening socket.
- [ ] Accept all currently pending connections when notified.
- [ ] Maintain independent decoder and output-buffer state per client.
- [ ] Handle partial reads and multiple decoded messages.
- [ ] Handle partial writes and `BlockingIOError`.
- [ ] Enable `EPOLLOUT` only while output is pending, using `modify()` for existing registrations.
- [ ] Handle combined readiness masks (for example, `EPOLLIN | EPOLLOUT`) by checking each flag independently.
- [ ] Handle EOF, hangup, and socket errors safely.
- [ ] Close all client sockets and the epoll instance during shutdown.

## 13. Quick revision questions

1. Why does the listening socket need to be non-blocking?
2. What is the difference between `EPOLLIN` and calling `recv()`?
3. Why does epoll readiness not guarantee a complete MessagePack message?
4. What is the difference between `register()` and `modify()`?
5. Can one `epoll.poll()` result contain both `EPOLLIN` and `EPOLLOUT` for the same descriptor?
6. Why should we use bitwise checks on the returned event mask?
7. Why does each client need its own decoder state?
8. Why must we preserve bytes that `send()` did not write?
9. Why should `EPOLLOUT` be disabled when the output buffer is empty?
10. What is the difference between `BlockingIOError` and `recv()` returning `b""`?

## Further reading

- [Python `select` documentation](https://docs.python.org/3/library/select.html)
- [Python socket documentation](https://docs.python.org/3/library/socket.html)
- [Arpit Bhayani — Redis Internals playlist](https://youtube.com/playlist?list=PLsdq-3Z1EPT0eElcdOON9fdaeaQjlyXDt)
