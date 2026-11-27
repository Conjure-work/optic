"""The soak's walk over HTTP against a local server, as one signed-in reader (audit round, package E).

One cycle: Home's reads; for each symbol of a set, the stock page's reads, plus the Financials, Earnings, Options and
Insiders reads; one Milo question and one deep-research request (Anthropic is the recording stub); one earnings brief;
the Markets pages' reads. Eight requests at a time, as tests/support/memprobe.py does. Answers are counted by status
and never judged: the soak measures memory, not correctness (a refused request still exercises the path).
"""
from __future__ import annotations

import http.cookiejar
import json
import sqlite3
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List

from tests.support.memprobe import PER_SYMBOL

HOME = ["/api/home", "/api/market", "/api/indices", "/api/sectors", "/api/macro", "/api/watchlist", "/api/session",
        "/api/delays", "/api/ai-allowance", "/api/build"]
MARKETS = ["/api/indices/board", "/api/sectors/board", "/api/markets/calendar?days=14", "/api/earnings-week?offset=0&quick=1",
           "/api/insiders/latest", "/api/analysts/latest", "/api/shortlist"]
# What the stock page, Financials, Earnings, Options and Insiders ask for per symbol, beyond memprobe.PER_SYMBOL.
STOCK = PER_SYMBOL + [
    "/api/ticker/{s}?max_expiries=4&macro=true", "/api/framework/{s}?mode=combined", "/api/fair-value/{s}",
    "/api/longterm/{s}?indices=false", "/api/digest/{s}", "/api/segments/{s}", "/api/extras/{s}?benchmark=SPY",
    "/api/stage?symbol={s}", "/api/intraday/{s}", "/api/weekly-bars/{s}", "/api/analysts/{s}",
    "/api/insiders/{s}/history?years=2", "/api/options/{s}/research?side=call", "/api/chain/{s}",
    "/api/valuation-inputs/{s}", "/api/indicators/{s}?ids=rsi", "/api/pe-history/{s}",
]


def symbol_set(k: int, size: int) -> List[str]:
    """`size` symbols for set number `k`: always the same names for the same k, never the same for two k."""
    out = []
    for i in range(size):
        n = k * size + i
        out.append("Z" + chr(65 + n // 676 % 26) + chr(65 + n // 26 % 26) + chr(65 + n % 26))
    return out


class Reader:
    """A signed-in account made by the run (the owner, so the assistant's daily allowance does not end the walk)."""

    def __init__(self, base: str, data: Path, email: str = "soak-reader@example.com", password: str = "tungsten-carbide-9"):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.codes: Dict[int, int] = {}
        body = json.dumps({"first_name": "Soak", "last_name": "Reader", "email": email, "password": password,
                           "confirm_password": password}).encode()
        req = urllib.request.Request(base + "/api/auth/register", data=body, headers={"Content-Type": "application/json"})
        self.opener.open(req, timeout=20).read()
        with sqlite3.connect(str(data / "accounts.db")) as c:
            c.execute("UPDATE users SET email_verified = 1 WHERE email = ?", (email,))

    def _csrf(self) -> str:
        return next((c.value for c in self.jar if c.name == "optic_csrf"), "")

    def request(self, path: str, body=None, timeout: float = 60) -> int:
        headers = {"X-Forwarded-For": "198.51.100.7"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers.update({"Content-Type": "application/json", "X-Optic-CSRF": self._csrf()})
        try:
            with self.opener.open(urllib.request.Request(self.base + path, data=data, headers=headers), timeout=timeout) as r:
                r.read()                                          # a streamed answer is read to its end
                code = r.status
        except urllib.error.HTTPError as e:
            e.read()
            code = e.code
        except Exception:                                         # noqa: BLE001 - a timeout counts as an answer
            code = 0
        self.codes[code] = self.codes.get(code, 0) + 1
        return code


def cycle(reader: Reader, symbols: List[str], workers: int = 8) -> Dict[int, int]:
    """One cycle of the walk; the status counts of this cycle."""
    before = dict(reader.codes)
    gets = list(HOME)
    for s in symbols:
        gets.extend(p.format(s=s) for p in STOCK)
    gets.extend(MARKETS)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(reader.request, gets))
        first = symbols[0]
        posts = [("/api/chat", {"messages": [{"role": "user", "content": "How is %s doing this quarter?" % first}],
                                "context": {"ticker": first}}),
                 ("/api/research", {"ticker": first, "question": "What changed for %s this year?" % first}),
                 ("/api/earnings/%s/brief" % first, {})]
        list(pool.map(lambda p: reader.request(p[0], p[1], timeout=90), posts))
    return {c: n - before.get(c, 0) for c, n in reader.codes.items() if n - before.get(c, 0)}
