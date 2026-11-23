"""Round three's carried items owned by the Milo work, as text contracts (the journeys in
tests/e2e/test_pass3_milo_inline.py drive them in a browser):

* item 2: Investing and Earnings tell Milo the chart in view, as Financials does (ui/inview.js), and stop watching
  when the page goes;
* item 3: the Read page's Desk is the shared Optic Desk panel (pages/workspace.js PANELS.desk), not a drawing of its
  own, with the full written edition kept one press away;
* Milo on every screen: the shell holds the strip outside #main and app.js repaints it on every route;
* /api/health names the off-topic set's version and size.
"""
from pathlib import Path

from fastapi.testclient import TestClient

V2 = Path(__file__).resolve().parent.parent / "static" / "v2" / "js"


def _src(rel):
    return (V2 / rel).read_text()


def test_carried_item_2_investing_and_earnings_tell_milo_the_chart_in_view():
    for page in ("pages/investing.js", "pages/earnings.js"):
        s = _src(page)
        assert "import { watchInView } from '../ui/inview.js';" in s, page
        assert "seen = watchInView(main);" in s and "in_view: inView()" in s, page
        assert "if (seen) { seen.stop(); seen = null; }" in s, "stops watching when the page goes: " + page
        assert s.count('data-v2-metric=""') >= 6, "the sections are marked so the one in view can be named: " + page


def test_carried_item_3_the_read_pages_desk_is_the_shared_desk_panel():
    s = _src("pages/read.js")
    assert "import { PANELS } from './workspace.js';" in s
    assert "P.body(D.home)" in s and "const P = PANELS.desk;" in s
    assert "api.get('/api/home'" in s, "the panel's own data"
    assert 'data-v2-desk="shared"' in s and "The full edition, with its sources" in s


def test_the_strip_is_drawn_by_the_shell_outside_main_and_repainted_on_every_route():
    shell, app = _src("ui/shell.js"), _src("app.js")
    assert shell.index('id="milo-inline"') < shell.index('<main id="main"')
    assert "miloInline.paint(route);" in app and "miloInline.wire();" in app
    inline = _src("ui/milo-inline.js")
    assert "aria-expanded" in inline and "Open Milo" in inline and "Collapse Milo" in inline


def test_health_names_the_offtopic_set():
    import app.main as main
    from app import ai_policy, milo_routes
    from tests.milo_eval.offtopic import OFFTOPIC
    modes = TestClient(main.app).get("/api/health").json()["modes"]
    got = modes["milo_offtopic"]
    assert got["version"] == ai_policy.OFFTOPIC_VERSION and got["set_cases_refused_in_suite"] == len(OFFTOPIC)
    assert milo_routes.OFFTOPIC_SET_SIZE == len(OFFTOPIC)
