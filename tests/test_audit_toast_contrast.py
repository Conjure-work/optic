"""The shared toast, the "saved" confirmation, meets WCAG AA text contrast in every theme (audit round, 2026-11-27).

Read from the stylesheets, not hand-written: the colours come from static/v2/css/tokens.css as the toast's own rules
use them (components.css: background --c-scene, text --c-on-scene; pages.css: the failure kind's --c-toast-bad). The
browser's computed values for a real toast, with its Undo button, are pinned in tests/e2e/test_audit_brief_contrast.py.
"""
import re
from pathlib import Path

import pytest

CSS = Path(__file__).resolve().parent.parent / "static" / "v2" / "css"
AA = 4.5


def _block(text, opener):
    """The body of the first rule whose selector starts with `opener`, braces matched."""
    start = text.index(opener)
    i = text.index("{", start)
    depth, j = 0, i
    while True:
        depth += text[j] == "{"
        depth -= text[j] == "}"
        if depth == 0:
            return text[i + 1:j]
        j += 1


def _vars(block):
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})\b", block))


def themes():
    t = (CSS / "tokens.css").read_text()
    light = _vars(_block(t, ":root {"))
    dark = {**light, **_vars(_block(t, ':root[data-theme="charcoal"]'))}
    system = _vars(_block(_block(t, "@media (prefers-color-scheme: dark)"), ":root:not([data-theme])"))
    system = {**light, **system}
    return {"light": light, "dark (chosen)": dark, "dark (system)": system}


def lum(hx):
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = [int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    hi, lo = sorted([lum(a), lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_the_toast_rules_still_use_the_tokens_measured_here():
    comp, pages = (CSS / "components.css").read_text(), (CSS / "pages.css").read_text()
    assert re.search(r"\.toast \{[^}]*background: var\(--c-scene\); color: var\(--c-on-scene\)", comp)
    assert '.toast[data-kind="bad"] { background: var(--c-toast-bad); color: var(--c-on-scene); }' in pages
    assert re.search(r"\.toast-act \{[^}]*background: transparent; color: inherit", pages)


@pytest.mark.parametrize("name", ["light", "dark (chosen)", "dark (system)"])
def test_the_default_and_failure_toast_text_is_at_least_aa(name):
    v = themes()[name]
    default, failure = ratio(v["--c-on-scene"], v["--c-scene"]), ratio(v["--c-on-scene"], v["--c-toast-bad"])
    print("toast contrast [{}]: default {:.2f}:1, failure {:.2f}:1".format(name, default, failure))
    assert default >= AA and failure >= AA, (name, default, failure)
    assert failure >= 7.0, "the failure kind was lifted to 7.3:1 in round three and stays there"
