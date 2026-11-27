"""A recording stand-in for the Anthropic API, on a local port (Pass 1, 2026-11-09).

Stubs record, they do not pretend: every request is kept (path, the JSON body, never the key), so a test can
assert what Milo was sent, and the stub plays the provider's behaviours a test asks for:

* ``ok``: a streamed answer, the Messages API's own server-sent events, a short fixed text.
* ``error``: HTTP 529 overloaded, with ``x-should-retry: false`` so the SDK reports it at once.
* ``timeout``: holds the request open past the client's timeout and never answers.
* ``tool`` (round three, 2026-11-23): the first round asks for one tool (``tool_name`` with ``tool_input``, a quote by
  default), and the round after the tool result waits ``text_delay`` seconds before the answer, so a journey can see
  Milo's steps arrive before any answer text.
* ``script`` (audit F04, 2026-11-27): ``stub.script`` is a list of answers, one returned per request in order (the
  last repeats when the list runs out); every request is still recorded, so a journey can see how many were made and
  what the later ones carried.

The base address is a setting (ANTHROPIC_BASE_URL) that the tests point here; nothing reaches the real host.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List

ANSWER = "Stand-in answer from the recording stub. No model wrote this."


def _sse(event: str, data: Dict[str, Any]) -> bytes:
    return "event: {}\ndata: {}\n\n".format(event, json.dumps(data)).encode()


class AnthropicStub:
    def __init__(self) -> None:
        self.requests: List[Dict[str, Any]] = []
        self.mode = "ok"
        self.hold = 30.0
        self.tool_name = "get_quote"
        self.tool_input: Dict[str, Any] = {"ticker": "AAPL"}
        self.text_delay = 1.5
        self.script: List[str] = []
        self._lock = threading.Lock()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a: Any) -> None:            # quiet
                return

            def _body(self) -> Dict[str, Any]:
                n = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(n) if n else b""
                try:
                    return json.loads(raw or b"{}")
                except ValueError:
                    return {"_raw": raw.decode("utf-8", "replace")}

            def _send(self, status: int, payload: Dict[str, Any], headers: Dict[str, str] = None) -> None:
                out = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(out)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(out)

            def do_GET(self) -> None:
                stub._record("GET", self.path, {})
                if self.path.startswith("/v1/models"):
                    self._send(200, {"data": [{"id": "claude-stub", "type": "model", "display_name": "Stub",
                                               "created_at": "2026-01-01T00:00:00Z"}],
                                     "has_more": False, "first_id": "claude-stub", "last_id": "claude-stub"})
                    return
                self._send(404, {"type": "error", "error": {"type": "not_found_error", "message": "stub"}})

            def do_POST(self) -> None:
                body = self._body()
                stub._record("POST", self.path, body)
                if not self.path.startswith("/v1/messages"):
                    self._send(404, {"type": "error", "error": {"type": "not_found_error", "message": "stub"}})
                    return
                if self.path.startswith("/v1/messages/count_tokens"):
                    self._send(200, {"input_tokens": 100})
                    return
                mode = stub.mode
                if mode == "timeout":
                    time.sleep(stub.hold)
                    return
                if mode == "error":
                    self._send(529, {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
                               {"x-should-retry": "false"})
                    return
                if not body.get("stream"):
                    self._send(200, {"id": "msg_stub", "type": "message", "role": "assistant", "model": body.get("model", "claude-stub"),
                                     "content": [{"type": "text", "text": ANSWER}], "stop_reason": "end_turn",
                                     "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 10}})
                    return
                answered_tool = any(isinstance(m.get("content"), list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"])
                    for m in body.get("messages") or [] if isinstance(m, dict))
                if mode == "tool" and not answered_tool and any(t.get("name") == stub.tool_name for t in body.get("tools") or []):
                    self._stream_tool(body)
                    return
                if mode == "tool":
                    time.sleep(stub.text_delay)
                text = stub._next_scripted() if mode == "script" else ANSWER
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("cache-control", "no-cache")
                self.send_header("connection", "close")
                self.end_headers()
                model = body.get("model", "claude-stub")
                for chunk in (
                    _sse("message_start", {"type": "message_start", "message": {"id": "msg_stub", "type": "message", "role": "assistant",
                                                                             "model": model, "content": [], "stop_reason": None,
                                                                             "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 1}}}),
                    _sse("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
                    _sse("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}),
                    _sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
                    _sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                                           "usage": {"output_tokens": 12}}),
                    _sse("message_stop", {"type": "message_stop"}),
                ):
                    self.wfile.write(chunk)
                    self.wfile.flush()
                self.close_connection = True

            def _stream_tool(self, body: Dict[str, Any]) -> None:
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("cache-control", "no-cache")
                self.send_header("connection", "close")
                self.end_headers()
                model = body.get("model", "claude-stub")
                for chunk in (
                    _sse("message_start", {"type": "message_start", "message": {"id": "msg_stub_t", "type": "message", "role": "assistant",
                                                                             "model": model, "content": [], "stop_reason": None,
                                                                             "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 1}}}),
                    _sse("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {
                        "type": "tool_use", "id": "toolu_stub_1", "name": stub.tool_name, "input": {}}}),
                    _sse("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {
                        "type": "input_json_delta", "partial_json": json.dumps(stub.tool_input)}}),
                    _sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
                    _sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                                           "usage": {"output_tokens": 12}}),
                    _sse("message_stop", {"type": "message_stop"}),
                ):
                    self.wfile.write(chunk)
                    self.wfile.flush()
                self.close_connection = True

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.url = "http://127.0.0.1:{}".format(self.port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def _record(self, method: str, path: str, body: Dict[str, Any]) -> None:
        with self._lock:
            self.requests.append({"method": method, "path": path, "body": body})

    def _next_scripted(self) -> str:
        with self._lock:
            n = len([r for r in self.requests if r["method"] == "POST" and r["path"].startswith("/v1/messages")
                     and not r["path"].startswith("/v1/messages/count_tokens") and r["body"].get("stream")])
            if not self.script:
                return ANSWER
            return self.script[min(n - 1, len(self.script) - 1)]

    def messages(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [r for r in self.requests if r["method"] == "POST" and r["path"].startswith("/v1/messages")
                    and not r["path"].startswith("/v1/messages/count_tokens")]

    def reset(self, mode: str = "ok") -> None:
        with self._lock:
            self.requests.clear()
        self.mode = mode
        self.script = []

    def start(self) -> "AnthropicStub":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
