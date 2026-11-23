# Pass 3, the charts: what was built and how it is tested

Round three's charts piece (items 2 and 3 of "Optic: what each round delivers", 2026-11-17, and the trading screens of
item 4), with two items carried in from round two: the holdings donut and the sector treemap, and the company grid as
its own tab. Built on `factory/pass-3-investor-charts-billing-milo` from bdb0571. Every test named here runs in the
suite with outbound HTTP pinned to the closed port; bars, chains, maps and books in the browser journeys are fixtures
(invented values, labelled as test data).

## 1. The Charting dock

- Built: the side widgets are an accordion, one open at a time; a widget's pin (in its header, beside Close) keeps it
  open when the next one opens, so several stack when pinned. With none open the plot takes the full width (the dock's
  column is hidden). The tool rail is unchanged. Options inside Charting: the Options widget keeps its figures at the top
  and adds five views of the same ticker, Readings, Chain, Builder, Gamma and Flow, built from the Options tab's own
  panels and endpoints (no model call); the Builder fills a long call, long put, bull call or bear put spread from the
  nearest expiry by delta, as the Options tab's builder does, and the server prices it. Ask Milo stays in the top bar.
  A view saved before, with several widgets open and none pinned, opens on the last one opened.
- Files: `pages/chart.js` (openAfter, togglePin), `pages/chart-widgets.js` (the pin, the Options views), new
  `pages/chart-options.js`, `ui/icons.js` (pin), `css/pages.css`.
- Tests: `tests/e2e/test_pass3_charts_dock.py` (accordion and pins, the width, the rail, Ask Milo; the five Options
  views with the chain and a priced bull call spread; the keyboard; axe at 1440 and 390),
  `tests/test_pass3_charts_modules.py` (openAfter, the templates' strikes by delta).

## 2. Two or four charts, favourite bar sizes, drawings across charts

- Built: a control for one, two or four charts above the chart. The first chart is the page's own (its rails, menus
  and dock); the others sit under it, each with its own ticker, bar size and range. Below the 860 px breakpoint the
  control offers one or two, stacked; a saved four opens as its first two with the line "This layout has 4 charts; a
  screen this narrow shows the first two, stacked. A wider window shows all 4." The layout on screen is kept in the
  browser (`optic.v2.chart.layout.v1`); signed in, Layouts names one and keeps it on the account (at most 20, private
  to the reader) and opens it in any browser.
- Favourite bar sizes: a row of buttons above each chart, chosen in Favourites; kept in the browser
  (`optic.v2.chart.intervals.v1`) and, signed in, on the account, mirrored on sign-in as the level is (the account's
  win; an account with none takes the browser's).
- Drawings stay in the browser per ticker (the classic key). A drawing made or moved on any chart is handed to every
  other chart of that ticker in the same task, so all of them draw it on the same frame.
- Files: new `pages/chart-grid.js`, `pages/chart.js`, `app/chart_routes.py` (layouts and favourites), migration 26's
  `chart_layouts` and migration 25's `favourite_intervals` (both laid down in the shared ground).
- Tests: `tests/test_pass3_charts_routes.py` (layouts kept, read from another session, at most 20, only 1, 2 or 4;
  favourites kept and private; no user, another user and no CSRF refused on every route),
  `tests/e2e/test_pass3_charts_layouts.py` (1, 2 and 4 with their own ticker, bar size and range, kept across a reload;
  a drawing on AAPL drawn on both other AAPL charts in the first frame and not on MSFT's; favourites signed out and
  following the account to another browser; a saved layout opened in another browser; the phone's stacked two and the
  line; the keyboard; axe with four charts at 1440 and two at 390), `tests/test_pass3_charts_modules.py`.

## 3. The November chart changes

- Fibonacci labels sit at the right edge beside the price scale, as ratios (0.5, 0.618, ...) with the price; the golden
  pair is set heavier. The drawn Fibonacci tool labels the same way.
- The animated draw on the two line graphs: Line and Area trace themselves in on first draw (this existed in
  `ui/drawon.js`); still under reduced motion. Read as the two line styles of the price chart (decision below).
- History back to the IPO: All asks `/api/daily-bars` (period=max). The answer now carries a `history` block and the
  chart says, from the bars it drew, where the free feed's history starts, that the bars before it are not in the
  free feed when the listing is earlier, and that prices are split-adjusted; the old line "Every daily bar since the
  listing" claimed more than the feed has. `/api/health` names the limit (`modes.chart_history`).
- The layout closer to the mockup: the chart controls in one row above the plot, the dock as an accordion, more than
  one chart; colours stay his visual update's.
- Files: `ui/pricechart.js` (fibLabel, isGolden), `app/chart_routes.py` (history_limit), `app/main.py` (one block in
  daily_bars), `pages/chart.js`.
- Tests: `tests/e2e/test_pass3_charts_november.py` (labels anchored right with 0.5 and 0.618, the golden pair; the
  draw-on counted as it starts for Line and Area and none under reduced motion; All's request and its sentence),
  `tests/test_pass3_charts_routes.py` (the sentence, the later-than-listing case, health),
  `tests/test_pass3_charts_modules.py` (the labels).

## 4. The three trading screens

- Built as layouts on Home's panel grid, so link groups, Customize and the account's saved layouts work on them:
  `technicals` (Charts and Technicals: the chart, Setup, Plan, Expression, the watchlist, Earnings), `derivatives`
  (Options and Derivatives: the chart, Volatility for the readings, Contracts for the chain, Expression, Positioning for
  gamma, Flow) and `positions` (Portfolio: Your portfolio, Your book, Positions and plans, Setups on your lists,
  alerts, the watchlist). New panels: setup, plan, expression, oflow, plans, listsetups, bookmix, kept out of the level
  matrix's Show more lists. A trading layout opened by name shows whole at every level.
- The rail's Research labels Charts & Technicals and Options & Derivatives open `#/?preset=technicals&symbol=SYM` and
  `#/?preset=derivatives&symbol=SYM`; the Chart and Options tabs stay on the company's tabs. Portfolio's layout is on
  Home's layout tabs and at `#/?preset=positions` (the Portfolio page is the Investor piece's).
- Files: `pages/workspace.js` (TRADING, the three presets, the panels), `nav.js` (the two Research targets only).
- Tests: `tests/e2e/test_pass3_charts_presets.py` (each layout by name with its panels; on the two linked layouts the
  panels follow the rail's ticker and a typed one, and the chart moved to Gold keeps its ticker; the rail's labels;
  a technicals layout saved on the account opened in another browser; axe at both widths on all three).

## 5. Carried in: the donut, the treemap, the grid tab

- Holdings donut: the Paper Desk book by value (at entry prices), largest four and Other, for a reader with no linked
  brokerage, in the Portfolio layout's Your book panel; the legend states every share; the total is in the caption.
  `ui/treemap.js` `holdingsDonut(positions, opts)` and `paperBook()` for the Portfolio page.
- Sector treemap: the eleven sector funds from `/api/stockmap?template=sector-today`, coloured by today's move, with a
  one-sentence summary on the picture and the full table under it. On Financials as "The market around it". For the
  Portfolio page: `renderSectorTreemap(host, { heading })` from `ui/treemap.js`.
- The company grid as its own tab: Panels on every company's tabs (`#/SYM/workspace`), with the company's tabs drawn on
  the grid page.
- Tests: `tests/e2e/test_pass3_charts_presets.py` (the donut's words and legend; the treemap's summary, table and the
  sizing sentence on Financials with axe at both widths; the Panels tab), `tests/test_pass3_charts_modules.py`.

## Acceptance

- 9 (the dock): met.
- 10 (two or four charts): met, including A1 (the browser key mirrored to the account) and A2 (the phone's one or two,
  the saved four and its line, a journey at 390). Drawings in the same frame: asserted on both other canvases.
- 11 (the November changes): met.
- 12 (three trading presets): met; the saved-layout journey runs on Charts and Technicals, the link-group journey on the
  two layouts that have linked panels (Portfolio's panels are about the reader's whole book and have no linked ticker).
- 19, this piece's parts (donut, treemap, grid tab): met, with text alternatives.
- 24 for these screens: axe at WCAG A and AA, zero violations, at 1440 and 390 on the chart page with four and two
  charts and with the dock and Options open, on Financials with the treemap, on the three layouts; keyboard journeys for
  the accordion and the chart layout control.

## Decisions (each reversible in review)

- "The two line graphs" read as the price chart's Line and Area styles, which already drew themselves in; nothing else
  in his November notes names two line graphs.
- "Market-weighted": the free feed reports no index weights, so the treemap's tiles are sized by the money traded
  through each sector fund a day, the nearest stand-in, and the caption says exactly that. Exact weights wait for
  licensed data (round 5).
- Charts and Technicals' chart is the grid's Quote and chart panel (daily closes with levels); the full chart with its
  tools is the Chart tab, one link away.
- The extra charts take their drawings from the first chart's tool rail; on them a drawing can be selected and moved.
- Opening a saved chart layout keeps the page's ticker as the first chart and says so when it was saved with another.

## Outside this piece's files, and why

- `ui/shell.js`: the search button's accessible name now starts with its visible words (axe-core 4.14, which the test
  tools now install, fails `label-content-name-mismatch` on it at desktop width on every page; it failed the round two
  axe journeys too before this change).
- `pages/workspace.js` (the sector heat map) and `ui/glance.js` (the donut): the same axe-core 4.14 found two more on
  screens round three does not otherwise change, which failed the visual update's axe journeys at the Pass 2 head too:
  a heat-map tile's name did not start with the words on its face, and the figure in a donut's middle, laid over the
  ring as HTML, had no background a contrast check could read. The tile's name now starts with its face; the figure is
  drawn in the picture, hidden from a screen reader as before (its words are in the picture's label and legend).
- `pages/financials.js`: the treemap section (item 13.1 names Financials).
- `tests/test_device_session.py` (the two new browser keys classed as settings), `docs/frontend-v2/COVERAGE.md` (the
  Panels tab), `tests/test_visual_update_figures.py` (the heat-map tile's new name), each changed because the behaviour
  changed on purpose, with the reason beside it.
- `nav.js`: the Panels tab added to the company's tabs, and the two Research targets.
