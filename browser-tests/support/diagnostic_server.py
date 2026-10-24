"""Opt-in LOCAL test diagnostics. No headers, query strings or bodies are recorded."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path.cwd()))
import uvicorn
from uvicorn.protocols.http.auto import AutoHTTPProtocol
from app.main import create_app

stream = None
def record(event, **fields):
    stream.write(json.dumps(dict(event=event, pid=os.getpid(), at=time.time(), **fields)) + "\n")

class Protocol(AutoHTTPProtocol):
    def connection_made(self, transport):
        super().connection_made(transport)
        record("connection_open", peer=self.client, protocol=AutoHTTPProtocol.__name__, keepalive_seconds=self.timeout_keep_alive)
    def connection_lost(self, exc):
        record("connection_lost", peer=self.client, error=type(exc).__name__ if exc else None)
        return super().connection_lost(exc)
    def timeout_keep_alive_handler(self):
        record("keepalive_timeout", peer=self.client)
        return super().timeout_keep_alive_handler()
    def shutdown(self):
        record("connection_shutdown", peer=self.client)
        return super().shutdown()
    def data_received(self, data):
        record("connection_data", peer=self.client, size=len(data))
        return super().data_received(data)

class Application:
    def __init__(self):
        self.app = create_app()
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        method, path, peer = scope["method"], scope["path"], scope.get("client")
        record("request_start", method=method, path=path, peer=peer)
        status = None
        async def traced_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                record("response_start", method=method, path=path, peer=peer, status=status)
            elif message["type"] == "http.response.body" and not message.get("more_body", False):
                record("response_end", method=method, path=path, peer=peer, status=status)
            await send(message)
        async def traced_receive():
            message = await receive()
            if message["type"] == "http.disconnect":
                record("request_disconnect", method=method, path=path, peer=peer)
            return message
        try:
            await self.app(scope, traced_receive, traced_send)
        except BaseException as error:
            record("request_error", method=method, path=path, peer=peer, error=type(error).__name__)
            raise
        finally:
            record("request_end", method=method, path=path, peer=peer, status=status)

def main():
    global stream
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    stream = (output / f"server-{os.getpid()}.jsonl").open("a", encoding="utf-8", buffering=1)
    record("server_start", protocol=AutoHTTPProtocol.__name__, default_keepalive_seconds=5)
    try:
        uvicorn.run(Application(), host="127.0.0.1", port=int(sys.argv[2]), http=Protocol, access_log=False, timeout_keep_alive=int(sys.argv[3]) if len(sys.argv) > 3 else 5)
    finally:
        record("server_stop")
        stream.close()

if __name__ == "__main__":
    main()
