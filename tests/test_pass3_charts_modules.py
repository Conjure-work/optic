"""Round three, the charts' pure parts (Pass 3, 2026-11-23), run in JavaScriptCore as the project's other front-end
module tests are: the chart layout (one, two or four, a phone's one or two), the favourite bar sizes, the drawings bus,
the dock's accordion, the Fibonacci labels, the dock's option templates, the sector treemap and the holdings donut.
The browser journeys are in tests/e2e/test_pass3_charts_*.py."""
from tests.test_frontend_v2_stage0 import V2
from tests.test_v2_p3 import _run

JS = V2 / "js"
GRID = (JS / "pages/chart-grid.js").as_posix()
OPTS = (JS / "pages/chart-options.js").as_posix()
PC = (JS / "ui/pricechart.js").as_posix()
TM = (JS / "ui/treemap.js").as_posix()
CH = (JS / "pages/chart.js").read_text()
CW = (JS / "pages/chart-widgets.js").read_text()
NAV = (JS / "nav.js").read_text()
WS = (JS / "pages/workspace.js").read_text()


def test_a_layout_is_one_two_or_four_charts_and_the_first_is_the_pages_own(tmp_path):
    got = _run(tmp_path, f"""
      const G = await import('{GRID}');
      const a = G.sanitizeLayout({{ count: 4, slots: [{{ symbol: 'MSFT', interval: '60', range: '1Y' }}, {{ symbol: 'nvda', interval: 'bogus', range: 'x' }}, {{ symbol: '<b>' }}] }}, 'AAPL');
      const b = G.sanitizeLayout({{ count: 3, slots: [] }}, 'AAPL');
      const c = G.sanitizeLayout(null, 'SPY');
      const kept = G.withCount(a, 2, 'AAPL');
      print(JSON.stringify({{ a, b, c, kept }}));
    """)
    a = got["a"]
    assert a["count"] == 4 and [s["symbol"] for s in a["slots"]] == ["AAPL", "NVDA", "QQQ", "IWM"], "the first is the page's; a bad ticker is filled"
    assert a["slots"][0]["interval"] == "60" and a["slots"][1] == {"symbol": "NVDA", "interval": "daily", "range": "6M"}
    assert got["b"]["count"] == 1, "three charts is not a layout"
    assert got["c"]["slots"] == [{"symbol": "SPY", "interval": "daily", "range": "6M"}]
    assert got["kept"]["count"] == 2 and got["kept"]["slots"][1]["symbol"] == "NVDA", "fewer charts keep the ones there"


def test_a_phone_shows_at_most_two_and_says_so_for_four(tmp_path):
    got = _run(tmp_path, f"""
      const G = await import('{GRID}');
      const four = G.sanitizeLayout({{ count: 4, slots: [] }}, 'AAPL'), two = G.sanitizeLayout({{ count: 2, slots: [] }}, 'AAPL');
      print(JSON.stringify({{ wide: G.forWidth(four, false), phone: G.forWidth(four, true), two: G.forWidth(two, true), counts: [G.COUNTS, G.PHONE_COUNTS] }}));
    """)
    assert got["wide"]["count"] == 4 and got["wide"]["note"] == ""
    assert got["phone"]["count"] == 2 and len(got["phone"]["slots"]) == 2
    assert got["phone"]["note"] == "This layout has 4 charts; a screen this narrow shows the first two, stacked. A wider window shows all 4."
    assert got["two"]["count"] == 2 and got["two"]["note"] == ""
    assert got["counts"] == [[1, 2, 4], [1, 2]]


def test_favourite_bar_sizes_are_the_charts_own_in_its_order(tmp_path):
    got = _run(tmp_path, f"""
      const G = await import('{GRID}');
      print(JSON.stringify({{ clean: G.cleanFavs(['1d', '5m', '7m', '1d', '1wk']), none: G.cleanFavs('x'), keys: ['5m', '1h', '1d', '1wk', '9m'].map(G.favToKey),
        back: ['5', '60', 'daily', 'weekly'].map(G.keyToFav), def: G.DEFAULT_FAVS, key: G.INTERVALS_KEY }}));
    """)
    assert got["clean"] == ["5m", "1d", "1wk"] and got["none"] is None
    assert got["keys"] == ["5", "60", "daily", "weekly", None] and got["back"] == ["5m", "1h", "1d", "1wk"]
    assert got["def"] == ["5m", "1h", "1d"] and got["key"] == "optic.v2.chart.intervals.v1"


def test_the_bus_hands_a_drawing_to_every_other_chart_in_the_same_task(tmp_path):
    got = _run(tmp_path, f"""
      const G = await import('{GRID}');
      const bus = G.createBus(), heard = [];
      const off = bus.subscribe((sym, list, from) => heard.push(['a', sym, list.length, from]));
      bus.subscribe((sym, list, from) => heard.push(['b', sym, list.length, from]));
      bus.publish('AAPL', [{{ kind: 'hline' }}], 'main');
      const sync = heard.length;
      off(); bus.publish('MSFT', [], 'slot1');
      print(JSON.stringify({{ sync, heard, size: bus.size() }}));
    """)
    assert got["sync"] == 2, "both heard before publish returned: no frame between them"
    assert got["heard"][:2] == [["a", "AAPL", 1, "main"], ["b", "AAPL", 1, "main"]] and got["heard"][2] == ["b", "MSFT", 0, "slot1"]
    assert got["size"] == 1


def test_the_dock_keeps_pinned_widgets_and_the_last_one_opened():
    i = CH.index("export function openAfter(")
    body = CH[i:CH.index("\n}\n", i) + 2]
    assert "const loose = dock.filter((id) => !pinned.includes(id)), last = loose[loose.length - 1];" in body
    assert "openAfter([...V.dock.filter((x) => x !== id), id], V.pinned)" in CH, "opening a widget closes the unpinned others"
    assert "pinned: V.pinned" in CH, "the pins kept with the chart's view"
    assert 'data-chw-pin="${id}" aria-pressed="${!!pinned}"' in CW


def test_fibonacci_labels_are_ratios_and_the_golden_pair_is_marked(tmp_path):
    got = _run(tmp_path, f"""
      const P = await import('{PC}');
      print(JSON.stringify({{
        labels: [P.fibLabel({{ ratio: 0.5, price: 230.125 }}), P.fibLabel({{ ratio: 0.618, price: 221.4 }}), P.fibLabel({{ label: '61.8%', price: 10 }}), P.fibLabel({{ ratio: 1.618, label: '161.8% ext', price: 300 }})],
        gold: [P.isGolden({{ ratio: 0.5 }}), P.isGolden({{ ratio: 0.618 }}), P.isGolden({{ ratio: 0.382 }}), P.isGolden({{ is_golden: true }})],
        ratios: [0, 0.236, 0.5, 0.618, 1].map(P.fibRatio),
      }}));
    """)
    assert got["labels"][0].startswith("0.5 ") and got["labels"][1].startswith("0.618 ")
    assert got["labels"][2].startswith("0.618 ") and got["labels"][3].startswith("1.618 ext ")
    assert got["gold"] == [True, True, False, True]
    assert got["ratios"] == ["0", "0.236", "0.5", "0.618", "1"]
    src = (JS / "ui/pricechart.js").read_text()
    assert "fibLabel(f), { end: true }" in src, "the levels' labels at the right edge"


def test_the_docks_templates_pick_strikes_by_delta_in_order(tmp_path):
    got = _run(tmp_path, f"""
      const O = await import('{OPTS}');
      const row = (type, strike, delta) => ({{ type, strike, delta, mid: 2, expiry: '2026-12-18', liquidity: {{ grade: 'tradable' }} }});
      const calls = [row('call', 240, 0.62), row('call', 245, 0.51), row('call', 250, 0.41), row('call', 255, 0.31), row('call', 260, 0.22)];
      const puts = [row('put', 240, -0.33), row('put', 245, -0.42), row('put', 250, -0.5), row('put', 255, -0.6)];
      print(JSON.stringify({{ lc: O.legsFor('long_call', calls, puts), bc: O.legsFor('bull_call', calls, puts), bp: O.legsFor('bear_put', calls, puts),
        none: O.legsFor('long_call', [], puts), views: O.VIEWS.map((v) => v[0]) }}));
    """)
    assert got["lc"] == [{"type": "call", "side": "long", "qty": 1, "strike": 245, "expiry": "2026-12-18"}]
    assert [(l["side"], l["strike"]) for l in got["bc"]] == [("long", 245), ("short", 255)]
    assert [(l["side"], l["strike"]) for l in got["bp"]] == [("long", 250), ("short", 240)]
    assert got["none"] is None
    assert got["views"] == ["readings", "chain", "builder", "gamma", "flow"]


def test_the_sector_treemap_and_the_holdings_donut_carry_their_words(tmp_path):
    got = _run(tmp_path, f"""
      const T = await import('{TM}');
      const map = {{ template: {{ color: 'chg_1d', size: 'dollar_volume' }}, colour_domain: {{ min: -1, max: 1 }},
        layout: [{{ symbol: 'XLK', name: 'Technology', x: 0, y: 0, w: 60, h: 100, values: {{ chg_1d: 1.2 }} }}, {{ symbol: 'XLE', name: 'Energy', x: 60, y: 0, w: 40, h: 100, values: {{ chg_1d: -0.5 }} }}] }};
      const svg = T.treemapSVG(map, 600);
      const parts = T.holdingsParts([{{ ticker: 'aapl', qty: 10, price: 200 }}, {{ ticker: 'MSFT', qty: 1, price: 500 }}, {{ ticker: 'AAPL', qty: 1, price: 200 }},
        {{ ticker: 'A', qty: 1, price: 50 }}, {{ ticker: 'B', qty: 1, price: 40 }}, {{ ticker: 'C', qty: 1, price: 30 }}, {{ ticker: 'X', qty: 0, price: 9 }}]);
      print(JSON.stringify({{ img: svg.includes('role="img"'), words: T.summary(map), parts, empty: T.treemapSVG({{ layout: [] }}, 600) }}));
    """)
    assert got["img"] and got["empty"] == ""
    assert got["words"].startswith("Sector funds sized by daily dollar volume, coloured by today's move. Largest: Technology +1.20%, Energy ")
    assert got["words"].endswith("0.50%. The full table follows.")
    assert got["parts"] == [{"label": "AAPL", "v": 2200}, {"label": "MSFT", "v": 500}, {"label": "A", "v": 50}, {"label": "B", "v": 40}, {"label": "Other", "v": 30}]


def test_the_rails_research_labels_open_the_trading_layouts_and_the_grid_is_a_tab():
    assert "{ label: 'Charts & Technicals', view: 'chart', preset: 'technicals', icon: 'research' }" in NAV
    assert "{ label: 'Options & Derivatives', view: 'swing', preset: 'derivatives', icon: 'optionsCurve' }" in NAV
    assert "if (entry.preset) return `#/?preset=${entry.preset}" in NAV
    assert "{ view: 'stockgrid', label: 'Panels', slug: 'workspace', v2: true }" in NAV
    assert "export const TRADING = ['technicals', 'derivatives', 'positions'];" in WS
    for pid in ("setup", "plan", "expression", "oflow", "plans", "listsetups", "bookmix"):
        assert f"  {pid}: {{\n    title: " in WS and "presetOnly: true" in WS[WS.index(f"  {pid}: {{\n"):WS.index(f"  {pid}: {{\n") + 200], pid
