"""A stand-in model for round three's Milo tests: it records every request and plays scripted rounds (text, a tool
call), so a test can assert what was sent and the order of the events the reader sees. Never a success mock: each
round's request is kept in `sent`."""
import asyncio
import json
import types

from app import ai


class _Stream:
    def __init__(self, events, final):
        self.events, self.final = events, final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        async def gen():
            for e in self.events:
                yield e
        return gen()

    async def get_final_message(self):
        return self.final


def delta(t):
    return types.SimpleNamespace(type="content_block_delta", delta=types.SimpleNamespace(type="text_delta", text=t))


def tool_start():
    return types.SimpleNamespace(type="content_block_start", content_block=types.SimpleNamespace(type="tool_use"))


def _usage():
    return types.SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0)


def text_round(*chunks):
    return [delta(c) for c in chunks], types.SimpleNamespace(model=ai.PULSE_MODEL, stop_reason="end_turn", content=[],
                                                             usage=_usage())


def tool_round(name, args, tid="t1"):
    use = types.SimpleNamespace(type="tool_use", id=tid, name=name, input=args)
    return [tool_start()], types.SimpleNamespace(model=ai.PULSE_MODEL, stop_reason="tool_use", content=[use],
                                                 usage=_usage())


class _Raises(_Stream):
    """A round whose request fails when it is opened (a timeout, the API down); the request is still recorded."""
    def __init__(self, exc):
        super().__init__([], None)
        self.exc = exc

    async def __aenter__(self):
        raise self.exc


def failing_round(exc=None):
    return _Raises(exc or RuntimeError("the rewrite call failed"))


def install(monkeypatch, rounds):
    """Replace the client with one that plays `rounds` in order; returns the list each request is appended to.
    A round made with `failing_round()` raises when its request is opened."""
    sent, queue = [], list(rounds)

    def stream(**kw):
        sent.append(kw)
        item = queue.pop(0) if queue else text_round("")
        if isinstance(item, _Raises):
            return item
        events, final = item
        return _Stream(events, final)
    monkeypatch.setattr(ai, "_client", lambda: types.SimpleNamespace(
        beta=types.SimpleNamespace(messages=types.SimpleNamespace(stream=stream))))
    return sent


def parse(raw):
    out = []
    for e in raw:
        head, _, data = e.partition("\ndata: ")
        out.append((head.replace("event: ", "").strip(), json.loads(data.strip() or "{}")))
    return out


def run(question, **kw):
    async def go():
        return [e async for e in ai.stream_chat([{"role": "user", "content": question}], **kw)]
    return parse(asyncio.run(go()))
