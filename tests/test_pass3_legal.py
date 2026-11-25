"""Terms and privacy from two files (round three, card D): counsel's text when it is there, the placeholder until it
is, and Checkout refused while the placeholder stands. The placeholder state is reported on /api/health and read by
the owner Metrics page through app/health_extra.py.

The repository ships the placeholder: these tests read the real legal/ directory for that, and temporary directories
for the other states. No test writes legal text; the "counsel" fixtures say they are fixtures.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import health_extra, legal_text

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "static" / "v2" / "js" / "pages" / "legalpages.js"


def _dir(tmp_path, terms, privacy):
    d = tmp_path / "legal"
    d.mkdir(exist_ok=True)
    if terms is not None:
        (d / "terms.md").write_text(terms)
    if privacy is not None:
        (d / "privacy.md").write_text(privacy)
    return d


def test_the_repository_ships_both_files_as_the_placeholder_and_no_legal_text(monkeypatch):
    monkeypatch.delenv("LEGAL_TEXT_DIR", raising=False)
    for doc in ("terms", "privacy"):
        text = (ROOT / "legal" / (doc + ".md")).read_text()
        assert legal_text.MARKER in text
        assert len([l for l in text.splitlines() if l.strip() and not l.startswith("<!--")]) == 1
        assert legal_text.read(doc)["state"] == "placeholder"
    assert legal_text.placeholder() is True
    assert legal_text.health() == {"state": "placeholder", "terms": "placeholder", "privacy": "placeholder"}


def test_counsels_text_is_served_as_written_once_the_marker_is_gone(monkeypatch, tmp_path):
    d = _dir(tmp_path, "# Terms (fixture)\n\nFixture paragraph.\n", "# Privacy (fixture)\n\n- a fixture item\n")
    monkeypatch.setenv("LEGAL_TEXT_DIR", str(d))
    assert legal_text.placeholder() is False and legal_text.health()["state"] == "counsel"
    r = TestClient(main.app).get("/api/legal-text/terms").json()
    assert r == {"state": "counsel", "markdown": "# Terms (fixture)\n\nFixture paragraph.\n", "pending": None}


@pytest.mark.parametrize("terms,privacy", [(None, None), ("", ""), ("   \n", "# Privacy (fixture)\n\nText.\n"),
                                           ("# T\n\n<!-- optic-legal: placeholder -->\n", "# P\n\nText.\n")])
def test_a_missing_empty_or_marked_file_is_the_placeholder_never_final_text(monkeypatch, tmp_path, terms, privacy):
    monkeypatch.setenv("LEGAL_TEXT_DIR", str(_dir(tmp_path, terms, privacy)))
    assert legal_text.read("terms")["state"] == "placeholder"
    assert legal_text.placeholder() is True
    body = TestClient(main.app).get("/api/legal-text/terms").json()
    assert body["markdown"] is None and body["pending"] == legal_text.PENDING


def test_the_route_serves_only_the_two_documents(monkeypatch):
    monkeypatch.delenv("LEGAL_TEXT_DIR", raising=False)
    c = TestClient(main.app)
    assert c.get("/api/legal-text/secrets").json()["state"] == "unknown"
    assert c.get("/api/legal-text/..%2F.env").status_code in (200, 404)
    assert c.get("/api/legal-text/..%2F.env").json().get("markdown") is None
    with pytest.raises(ValueError):
        legal_text.read("../.env")


def test_health_and_the_owner_snapshot_say_which(monkeypatch, tmp_path):
    monkeypatch.delenv("LEGAL_TEXT_DIR", raising=False)
    assert TestClient(main.app).get("/api/health").json()["modes"]["legal_text"]["state"] == "placeholder"
    monkeypatch.setenv("LEGAL_TEXT_DIR", str(_dir(tmp_path, "# T (fixture)\n", "# P (fixture)\n")))
    assert TestClient(main.app).get("/api/health").json()["modes"]["legal_text"]["state"] == "counsel"
    assert health_extra.snapshot(operator=True)["legal_text"]["state"] == "counsel"


def test_the_page_renders_the_file_or_the_notice_above_the_published_draft():
    src = PAGE.read_text()
    assert "/api/legal-text/${which}" in src
    assert 'data-v2-legal="counsel"' in src and "fromMarkdown(text.markdown)" in src
    # the placeholder keeps the draft of October 19 readable under the notice: nothing public is taken down
    assert 'data-v2-legal="placeholder"' in src and "doc.sections.map" in src
    assert "The version below was written before that review." in src


def test_counsels_markdown_is_escaped_and_only_https_or_mailto_links_survive():
    from tests.support.jsc import JSC as jsc
    if not jsc:
        pytest.skip("no JavaScriptCore on this machine")
    src = PAGE.read_text()
    m = re.search(r"const LINK = .*?\nexport function fromMarkdown\(md\) \{.*?\n\}\n", src, re.S)
    assert m
    harness = (
        "function raw(s){return {__html:s};}\n"
        "function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;');}\n"
        "function flat(v){if(v==null)return '';if(Array.isArray(v))return v.map(flat).join('');if(v&&v.__html!==undefined)return v.__html;return esc(v);}\n"
        "function html(strs,...vals){let o='';strs.forEach((s,i)=>{o+=s;if(i<vals.length)o+=flat(vals[i]);});return raw(o);}\n"
        "function out(href,label){return html`<a href=\"${href}\">${label}</a>`;}\n"
        + m.group(0).replace("export function", "function") +
        "const md = '<!-- optic-legal -->\\n# Heading <b>\\n\\nPara with [ok](https://example.com/t) and [bad](javascript:alert(1)).\\n- item <script>\\n- two';\n"
        "print(flat(fromMarkdown(md)));\n")
    script = Path(__file__).with_name("_legal_md_harness.js")
    try:
        script.write_text(harness)
        out = subprocess.run([str(jsc), str(script)], capture_output=True, text=True, timeout=20).stdout
    finally:
        script.unlink()
    assert "<h2>Heading &lt;b&gt;</h2>" in out
    assert '<a href="https://example.com/t">ok</a>' in out
    assert "javascript:" not in out.split("[bad]")[0] and "<a href=\"javascript" not in out
    assert "<li>item &lt;script&gt;</li>" in out and "<li>two</li>" in out
    assert "optic-legal" not in out
