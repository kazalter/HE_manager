#!/usr/bin/env python3
"""Relay Nginx upstream TCP connections through a shared Unix socket."""

import argparse
import os
from pathlib import Path
import socket
import threading


def pump(source: socket.socket, target: socket.socket) -> None:
    try:
        while True:
            chunk = source.recv(64 * 1024)
            if not chunk:
                break
            target.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            target.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def handle(client: socket.socket, port: int) -> None:
    upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        upstream.connect(("127.0.0.1", port))
        threads = [
            threading.Thread(target=pump, args=(client, upstream), daemon=True),
            threading.Thread(target=pump, args=(upstream, client), daemon=True),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    except OSError:
        pass
    finally:
        client.close()
        upstream.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args()

    socket_path = Path(args.socket)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        socket_path.unlink()
    except FileNotFoundError:
        pass

    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    os.chmod(socket_path, 0o666)
    listener.listen(64)
    try:
        while True:
            client, _ = listener.accept()
            threading.Thread(target=handle, args=(client, args.port), daemon=True).start()
    finally:
        listener.close()
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
