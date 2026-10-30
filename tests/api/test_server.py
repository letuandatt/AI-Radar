"""Actual HTTP start, bind errors and ordered request draining."""

import asyncio
import socket
import threading
import time

import httpx
import pytest
from fastapi import FastAPI

from app.api.config import WebConfig
from app.api.factory import create_app
from app.api.server import WebServer
from app.core.registry import ComponentRegistry


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_actual_http_and_graceful_drain():
    port = free_port()
    app = FastAPI()
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def slow():
        started.set()
        release.wait(5)
        finished.set()

    @app.get("/slow")
    async def route():
        await asyncio.to_thread(slow)
        return {"done": True}

    server = WebServer(app, WebConfig(_env_file=None, port=port)).start()
    results = []
    request = threading.Thread(
        target=lambda: results.append(httpx.get(f"http://127.0.0.1:{port}/slow"))
    )
    request.start()
    assert started.wait(3)
    stopper = threading.Thread(target=server.stop)
    stopper.start()
    time.sleep(0.1)
    assert stopper.is_alive()
    release.set()
    request.join(5)
    stopper.join(5)
    assert finished.is_set() and not stopper.is_alive()
    assert results[0].status_code == 200


def test_port_failure_rolls_back_registry():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = occupied.getsockname()[1]
        closed = []
        registry = ComponentRegistry()
        registry.register(
            "dependency", lambda: "db", lambda value: closed.append(value), priority=15
        )
        registry.register(
            "web",
            lambda: WebServer(create_app(), WebConfig(_env_file=None, port=port)).start(),
            lambda value: value.stop(),
            priority=70,
        )
        with pytest.raises(OSError):
            registry.start_all()
        assert closed == ["db"]
