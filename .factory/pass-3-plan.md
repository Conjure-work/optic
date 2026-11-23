# Pass 3 plan: the rest of Investor mode, charts in depth, billing live, and Milo hardened

Branch `factory/pass-3-investor-charts-billing-milo` on the fork, cut from `factory/pass-2-works-data-workspace` at
92dbcca (the Pass 1 and Pass 2 pull requests, #19 and #20, are open and unmerged as of 2026-11-23, so this branch
carries both underneath it; its pull request is stacked on #20). Scope: the seven items of round 3 in "Optic: what each
round delivers" (2026-11-17) and the twelve items stated as round three on 2026-11-18 and 2026-11-20. The suite stays
green before and after every merge: `python -m pytest -q` with outbound HTTP pinned to a closed port (TESTING.md).

## Shared ground, laid first (this commit)

So that five pieces of work can run side by side without editing the same lines:

- Migrations 23 to 27 in `app/db.py`, all additive (`tests/test_pass3_migrations.py` builds a database at 22 with rows,
  migrates, and asserts every old value unchanged): 23 and 24 give watchlists and saved research the owner shape
  (`owner_kind`, `owner_id`) that saved layouts have, every row set to its own user; 25 adds four reader preferences
  (`favourite_intervals`, `milo_stance`, `level_quiz`, `alert_email`); 26 `chart_layouts`; 27 `watch_delivery`.
- `app/auth/store.py` `round_three_preferences` and `set_round_three_preferences`: the four preferences validated in
  one place (unknown values dropped, the sign-up answers never stored).
- `app/health_extra.py`: each mode round three adds (billing, legal text, alert delivery, the chart feed's history
  limit, Milo's off-topic set) is reported on `/api/health` under `modes` by the module that decides it, and the owner
  Metrics page reads the same snapshot.
- `app/investor_routes.py`, `app/chart_routes.py`, `app/milo_routes.py`: empty routers already included by main.py, so
  new routes land in their own module.

## The five pieces and the files each owns

| Piece | Items | Owns |
| --- | --- | --- |
| D, health | memory and open files at rest; the suite on GitHub in parallel jobs; the brokerage sandbox's untested state | `.github/workflows/tests.yml`, the client and cache modules (`app/ai.py`'s client factory only, `app/contracts.py`, `app/replays.py`, `app/valuation/service.py`, `app/analytics/screen.py`, `app/research/service.py`), the brokerage test |
| A, Investor mode | watchlists and alerts in one place; Portfolio with one meaning; Markets calendar; first visit at Beginner; owner report; sign-up questions; owner shape; the saved line; source-line capitals; the three accessibility items | `pages/watchlist.js`, `alerts.js`, `tracker.js`, `paper.js`, `read.js`, `macro.js`, `signin.js`, `reports.js`, `nav.js`, `app/metrics.py`, `app/account.py`, `app/investor_routes.py` |
| B, Charts | the Charting dock; two or four charts with live drawings and favourite intervals; the November chart changes; the three trading layouts; holdings donut and sector treemap; the company grid tab | `pages/chart*.js`, `ui/pricechart.js`, `ui/drawings.js`, `options*.js`, `workspace.js` presets, `ui/glance.js`, `app/chart_routes.py` |
| C1, billing and legal | the plan ladder, Checkout, portal, webhook, plan access; terms and privacy pages; alert delivery per reader behind the owner's switch | `app/billing.py`, `legalpages.js`, `app/alerts.py`, `pages/settings.js` |
| C2, Milo | off-topic set; grounding per screen; named stances; the streamed steps; Milo inline on every screen with offers; Milo told the chart in view on Investing and Earnings; the Read page's Desk | `app/ai.py` (outside D's client factory), `app/ai_policy.py`, `app/research/milo.py`, `ui/milo*.js`, `ui/drawer.js`, `ui/miloprompt.js`, `app/milo_routes.py` |

Interfaces: C2 mounts the inline Milo panel from the shell on every route, so pages do not call it; B names the three
trading layouts' preset ids and may change only the Research group's targets in `nav.js`; A's owner Metrics page shows
the `modes` snapshot. Anything outside these goes through the integration.

Integration order: D, A, B, C1, C2, each over the last, with the whole suite green after every merge and the running
count stated.

## Defaults this pass builds on (each reversible)

- One draft pull request from the fork, stacked on #20.
- Billing reads a plan ladder from variables: the three plans already in `app/auth/store.py` (free, pro, enterprise)
  with their caps, one price id per paid plan (`STRIPE_PRICE_ID_PRO`, `STRIPE_PRICE_ID_ENTERPRISE`; `STRIPE_PRICE_ID`
  kept as the pro price). With nothing set, nothing shows. Caps apply only while billing is on.
- Terms and privacy render from `legal/terms.md` and `legal/privacy.md`; until those hold the owner's counsel's text a
  placeholder says the terms are being prepared and Checkout is refused with that sentence.
- Alert delivery per reader ships behind `ALERT_DELIVERY_READERS` (off): the owner summary stays as built until the
  owner chooses.
- Drawings stay in the browser per symbol; the redraw across charts is in the page.
- The old Alerts page and the model portfolios page can be shown as separate pages again with one setting.
