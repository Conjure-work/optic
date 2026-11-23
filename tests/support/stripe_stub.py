"""A recording stand-in for Stripe's API, on a local port (round three, 2026-11-23).

Stubs record, they do not pretend: every request is kept (method, path, the form body; the Authorization header is
recorded only as whether one was sent, never its value), so a test can assert what Optic asked Stripe for. It plays
the behaviours a test asks for:

* ``ok``: Checkout and portal sessions with stripe.com URLs, prices from ``prices``, subscriptions from
  ``subscriptions``, a deleted subscription for DELETE.
* ``error``: HTTP 500 with Stripe's error shape.
* ``timeout``: holds the request past the client's timeout (STRIPE_TIMEOUT_SECONDS) and never answers.

The base address is a setting (STRIPE_API_BASE) that the tests point here; nothing reaches api.stripe.com. Values are
invented and labelled; the session URLs are never opened.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List
from urllib.parse import parse_qs


class StripeStub:
    def __init__(self) -> None:
        self.requests: List[Dict[str, Any]] = []
        self.mode = "ok"
        self.hold = 10.0
        self.prices: Dict[str, Dict[str, Any]] = {}
        self.subscriptions: Dict[str, Dict[str, Any]] = {}
        self._n = 0
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a: Any) -> None:
                return

            def _send(self, status: int, payload: Dict[str, Any]) -> None:
                out = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def _handle(self, method: str) -> None:
                n = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(n).decode() if n else ""
                form = {k: v[0] for k, v in parse_qs(raw).items()}
                path = self.path.split("?", 1)[0]
                stub.requests.append({"method": method, "path": path, "form": form,
                                      "authorized": bool(self.headers.get("authorization")),
                                      "idempotency_key": self.headers.get("idempotency-key")})
                if stub.mode == "timeout":
                    time.sleep(stub.hold)
                    return
                if stub.mode == "error":
                    self._send(500, {"error": {"type": "api_error", "message": "stub error"}})
                    return
                stub._n += 1
                if path.endswith("/checkout/sessions") and method == "POST":
                    sid = "cs_test_stub_{}".format(stub._n)
                    self._send(200, {"id": sid, "object": "checkout.session",
                                     "url": "https://checkout.stripe.com/c/pay/" + sid})
                elif path.endswith("/billing_portal/sessions") and method == "POST":
                    self._send(200, {"id": "bps_stub_{}".format(stub._n), "object": "billing_portal.session",
                                     "url": "https://billing.stripe.com/p/session/stub_{}".format(stub._n)})
                elif "/prices/" in path and method == "GET":
                    pid = path.rsplit("/", 1)[1]
                    found = stub.prices.get(pid)
                    self._send(200, found) if found else self._send(404, {"error": {"type": "invalid_request_error"}})
                elif "/subscriptions/" in path:
                    sid = path.rsplit("/", 1)[1]
                    found = stub.subscriptions.get(sid)
                    if not found:
                        self._send(404, {"error": {"type": "invalid_request_error"}})
                    elif method == "DELETE":
                        self._send(200, dict(found, status="canceled"))
                    else:
                        self._send(200, found)
                else:
                    self._send(404, {"error": {"type": "invalid_request_error"}})

            def do_GET(self) -> None:
                self._handle("GET")

            def do_POST(self) -> None:
                self._handle("POST")

            def do_DELETE(self) -> None:
                self._handle("DELETE")

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.url = "http://127.0.0.1:{}/v1".format(self._server.server_address[1])

    def start(self) -> "StripeStub":
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def reset(self) -> None:
        self.requests.clear()
        self.mode = "ok"
