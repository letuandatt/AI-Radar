"""Own a Uvicorn daemon thread and drain it before repository shutdown."""

import logging
import socket
import threading
import time

import uvicorn
from fastapi import FastAPI

from app.api.config import WebConfig


class WebServer:
    """Bind synchronously, report startup failure, and wait for workers on shutdown."""

    def __init__(self, app: FastAPI, config: WebConfig) -> None:
        self.config = config
        self.server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=config.host,
                port=config.port,
                access_log=False,
                proxy_headers=False,
                server_header=False,
                limit_concurrency=32,
            )
        )
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._failed = threading.Event()

    def start(self) -> "WebServer":
        """Return only after the ASGI application is listening."""
        sock = socket.socket(socket.AF_INET6 if ":" in self.config.host else socket.AF_INET)
        try:
            sock.bind((self.config.host, self.config.port))
            sock.listen(128)
            self._socket = sock

            def run() -> None:
                try:
                    self.server.run(sockets=[sock])
                except BaseException:
                    self._failed.set()

            self._thread = threading.Thread(target=run, name="ai-radar-api", daemon=True)
            self._thread.start()
            deadline = time.monotonic() + self.config.startup_timeout
            while not self.server.started:
                if self._failed.is_set() or not self._thread.is_alive():
                    raise RuntimeError("Web server startup failed")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Web server startup timed out")
                time.sleep(0.01)
            logging.getLogger(__name__).info("Web API ready on port %d", self.config.port)
            return self
        except BaseException:
            self.stop()
            sock.close()
            raise

    def stop(self) -> None:
        """Drain pending requests and executor work before releasing dependencies."""
        self.server.should_exit = True
        if self._thread is not None:
            self._thread.join()
        if self._socket is not None:
            self._socket.close()
