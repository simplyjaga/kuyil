"""Start Kuyil's Linux epoll-based server."""

from kuyil.event_loop import EpollServer


def main() -> None:
    server = EpollServer()
    try:
        server.run()
    except KeyboardInterrupt:
        print("\nKuyil epoll server stopped.")


if __name__ == "__main__":
    main()
