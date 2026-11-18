# Step 0: spec conformance, CON-54 Pass 2: Optic

Kind of document: the Step 0 traceability table of the delivery kit, internal (never shown to the customer). Product Optic, issue CON-54 "Pass 2: Optic", Pass 2, NEW BUILD lane on the customer's inherited repository, full lane (deck, video, two diagrams), free round (label Free, students offer, free pass 2 of 3). Written 2026-11-18 by the delivery kit session.

**Gate.** Read from Linear on 2026-11-18 at about 14:35 ET through the API: CON-54 state Gauntlet, labels Artifacts and Free. The Artifacts label went on under card D-54-1 (`Conjure/handoffs/optic-pass-2/D-54-1-card.md`). Billing shape: new build, per-round delivery (issue description, Commercial: "Free pass 2 of 3 on this order... Nothing is priced").

**Source of the agreed spec.** CON-54's description, section Spec: the nine Round 2 items of "Optic: what each round delivers" (sent by the operator as a PDF on 2026-11-17; source `Conjure/customers/optic/pass-summary-2026-11-17.md`, section Round 2), with the customer's written approval to start of 2026-11-17 and the operator's go. Section "Scope carried in" of the same description lists the free update's held-back items and the round-one review fixes. The build's reading: the factory prompt and the eight refinement amendments on the issue (2026-11-18 14:29 UTC comments). Customer text is quoted as data.

**Commit delivered and tested.** Fork sidprobstein/optic, branch `factory/pass-2-works-data-workspace`, code head **34a30b71c56866c8c41f62e1c922f0555c5f1f7c** (branch tip 92dbcca adds only the round-three gauntlet record in `.factory/gauntlet-2.md`). Evaluation copy: Railway project `conjure-optic-eval`, environment `production`, service `optic` behind `edge-optic`, deployment f33bedf0-b97c-480a-b293-e577e671b930, page build id 7689d8061f5e, DEPLOY VERIFIED (quoted in `.factory/gauntlet-2.md`, round three, from `Conjure/handoffs/optic-pass-2/deploy-verify-CON-54-round3.md`). Suite from clean on 34a30b7: 9,174 passed, 0 failed, 1 skipped (round three). Human half: 31 of 32 asks walked, ask 27 SKIP (L1); D4 and D5 fixed and re-walked PASS (`Conjure/handoffs/optic-pass-2/gauntlet-CON-54-human-half.md`).

## Outcome of the review: CONFORMS, with deferrals on the operator's call (not halted)

Every one of the nine Round 2 items is DELIVERED or DELIVERED DIFFERENTLY with evidence. Five pieces of the request were not built this round and are recorded as limit L4 by the build plan (`.factory/pass-2-plan.md`, Status) and every gauntlet round. The operator gave the Artifacts verdict knowing them (human-half record, "Limits carried"; card D-54-1) and the delivery brief names them as limits to state in the deck's "what is next" and in the message. They are resolved here as **DEFERRED, OPERATOR'S CALL, to round 3** under QUOTE ONCE (folded into the next free round at no change in price). They have NOT yet been agreed with the customer in writing; the deck and the delivery message state each one plainly so the customer reads them before the review window. The strict reading of the HALT RULE treats rows A6b and A7b (the donut and the treemap, which the 2026-11-13 reply named as "round two") as undelivered agreed items; this is the judgement call the operator should confirm on the deck card. If the operator reads it the other way, the kit is held and the gap list below is the comment to post.

Counts over sections A to C: DELIVERED 24, DELIVERED DIFFERENTLY 4, DEFERRED (operator's call, round 3) 5, DEFERRED BY AGREEMENT 3, NOT TESTABLE ON THE COPY 1 (the brokerage link, its off state delivered), OPEN QUESTION TO THE CUSTOMER 1 (the alert email recipient), PENDING AT SEND 2 (A2g the six results, carried by the message; A10 the Pass 2 pull request on the customer's repository, not yet opened). Named outcome (row D): DELIVERED. Eval sets (row E): DELIVERED, counted on 34a30b7.

## A. The nine Round 2 items, one row per requesting sentence

| # | The agreed text (Round 2) | Resolution | Evidence |
|---|---|---|---|
| A1a | 1. "Walk the eight workflows we agreed end to end in a real browser with no dead ends" | DELIVERED | `tests/e2e/test_pass2_workflows.py` (one journey per workflow); `.factory/pass-2-workflow-record.md` (defects W1 to W6 fixed); gauntlet round one item 19 (every screen of the eight, signed in, live feeds, Ask Milo on each, no dead end); human asks 3 to 5 |
| A1b | 1. "each one tested, defects fixed" | DELIVERED | workflow record W1 to W6; gauntlet D1 to D5 fixed across rounds two and three; suite from clean green on 34a30b7 |
| A1c | 1. "the same loading, empty, stale and failed states everywhere, with loading placeholders and brief transitions" | DELIVERED | `static/v2/js/ui/states.js`; `tests/test_pass2_states_contract.py`; workflow record W5 (fifteen hand-written failed blocks moved to the shared look) |
| A2a | 2. Deep Research custom question tested | DELIVERED | suite journey `test_deep_research_sends_the_readers_own_question_and_shows_the_answer`; on the copy, gauntlet round one item 14 (the typed question verbatim, answer labelled deep research); human ask 23 |
| A2b | 2. Index Read tested | DELIVERED | `test_the_index_read_is_asked_from_the_board_and_answers_in_place` (10 of 10 alone, round two); copy item 16; human ask 25 |
| A2c | 2. Exports tested | DELIVERED (after D4) | research sheet to PDF: round three R1 to R5 (two pages at Letter and A4, no overlap); `tests/e2e/test_pass2_print.py`; human ask 26 PASS on re-walk |
| A2d | 2. Passkeys tested | DELIVERED | journey through Chromium's virtual authenticator; on the copy round one item 15 and round two P1 to P3; human ask 24 |
| A2e | 2. Brokerage link tested | NOT TESTABLE ON THE COPY; off state DELIVERED | no SnapTrade test keys exist (L1, owner the customer); off state "Brokerage linking is not switched on for this deployment." with the watchlist and Paper Desk offered (workflow record W4; round one 17c; human ask 29). Stated in the deck and message |
| A2f | 2. Alert delivery tested | DELIVERED as built; recipient an OPEN QUESTION | route-level delivery tests in `tests/test_alerts.py`; on the copy email delivery is off ("These alerts are shown in Optic; email delivery is not set up for readers."). As built, one digest goes to one configured address, the owner's (L2): a product question for the customer, not decided |
| A2g | 2. "with the results sent to him" | PENDING AT SEND | `.factory/pass-2-six-features-record.md` updated by the gauntlet rounds; the delivery message carries the six results in plain words |
| A3a | 3. "Keep his ticker and his place as he moves between tabs" | DELIVERED | `core/store.js`, `core/scrollmem.js`; `tests/test_pass2_place.py`; round one item 3c (same heading in view, scroll 4,579 px both times); human asks 7 and 8 |
| A3b | 3. "with Milo given the chart, timeframe or metric he is looking at" | DELIVERED on Financials and Chart; DEFERRED (operator's call, round 3) on Investing and Earnings | `ui/inview.js` (D1 fix 785f01d), journey `test_a_chart_pressed_before_milo_opens_from_the_top_bar_is_the_one_milo_is_told`; copy D1 a/b in rounds two and three; human ask 6. Investing and Earnings send their tab, not the chart in view (L4) |
| A4a | 4. "Find the source and timestamp of every figure" | DELIVERED (per panel where one source feeds it, per figure where sources mix: Card B, recommended option) | `app/figures/registry.py`, `ui/figure.js`; `tests/test_pass2_provenance.py`; D5 fix 34a30b7 (a source line under every Financials chart, round three S1, S2); human ask 11 PASS on re-walk |
| A4b | 4. "with reported facts marked apart from Milo's reading" | DELIVERED | round one item 4 (figures underlined with their source, the line "Underlined figures are reported, from the source beside them; the rest is Milo's reading of them."); human ask 9 |
| A4c | 4. "read the full insider history from the SEC rather than the last batch the free feed lists" | DELIVERED | `app/insider_fill.py`, `app/form4_store.py`, `/api/insiders/{T}/history` (2, 5, 10 years); round one item 5 (SEC Form 4 rows with accession links); human ask 10 |
| A5a | 5. "intraday sparklines in Home's ticker rows, red or green by the day's direction, refreshed through the session at the free feed's delay" | DELIVERED | `app/sparklines.py` (REFRESH_SECONDS 300, daily fallback), `/api/sparklines`; `tests/test_pass2_sparklines.py`; closed half on the copy round one 7a; in-session half human ask 14 (market open) |
| A5b | 5. "built so a licensed feed slots in later" | DELIVERED | `app/sparklines.py` `SOURCES`, `OPTIC_INTRADAY_SOURCE` (one class for a licensed vendor) |
| A5c | 5. "a one-day range on Home's headline chart" | DELIVERED | `[data-hm-span='1d']`; round one 7b (closed state worded); human ask 15 (in session) |
| A5d | 5. "the live price dot with a clear delayed or closed status" | DELIVERED | `ui/pricechart.js`, `app/delays.py`; human ask 15 |
| A6a | 6. "Read Financials as charts: revenue, margins and cash flow by period, the balance sheet's shape" | DELIVERED | `pages/financials.js`, `ui/finfigs.js`; round one item 8 (10 charts by year, 12 by quarter); axe clean both widths (rounds two and three); human ask 12 |
| A6b | 6. "and the other series the free update held back": quarterly balance sheet and cash flow; analyst target ranges | DELIVERED | Cash flow by quarter, Cash and debt by quarter (round one 8); analyst targets drawn as a range with the price as a dot on Earnings (round one 8b; human ask 13; Card D) |
| A6c | 6. (held back, same item): a sector or holdings donut for readers with no linked brokerage | DEFERRED (operator's call, round 3); not agreed with the customer yet | plan Status item 6; L4. The customer was told on 2026-11-13 that the Portfolio donut is round two (`customers/optic/reply-draft-2026-11-13.md`, line 26). Stated in the deck and message |
| A6d | 6. (held back, same item): a market-weighted sector treemap | DEFERRED (operator's call, round 3); not agreed with the customer yet | plan Status item 6; L4. Home's sector heat map (equal tiles) is what exists. Stated in the deck and message |
| A6e | 6. (held back, same item): dates under sparklines | DELIVERED | ticker rows and tiles carry their span ("past 30 sessions", "today") (round one 7a, 7c) |
| A7a | 7. "Use the Optic Desk right side for sources, saved research and Milo follow-ups" | DELIVERED on Home | round one item 9 (Built from, Your saved research, Ask Milo); `tests/e2e/test_pass2_desk.py`; human ask 16 |
| A7b | 7. "with less scrolling on Home and Desk" | DELIVERED on Home; DEFERRED (operator's call, round 3) for the Read page's Desk | Home measured in `test_pass2_desk.py`; the Read page's Desk keeps its own layout (L4) |
| A8a | 8. "Put panels into colour-coded link groups, so a ticker chosen in one panel changes every panel in its group and leaves the others alone" | DELIVERED (Blue, Gold, Teal) | `pages/workspace.js`; journey in `tests/e2e/test_pass2_workspace.py`; round one item 10; human ask 17 |
| A8b | 8. "name a layout, save it on his account, come back to it from any browser, and reset to the default" | DELIVERED | `app/layouts.py` (20 per account, names to 40 characters, 32 KB), `/api/layouts`; `tests/test_pass2_layouts.py` (no user, wrong user, owner); round one 12, round two L1 to L3; human asks 19 to 21 |
| A8c | 8. "with feedback when a save lands" | DELIVERED (the saved list refreshes and a five-second toast) | human ask 19 passed with observation F2 (toast not noticed; under L3); an inline "saved" line is proposed for round 3 |
| A8d | 8. "use the same grid of panels on the stock page as on Home" | DELIVERED DIFFERENTLY | `#/AAPL/workspace`, the company grid, reached by "Open as panels" from the stock page's More menu at Advanced rather than a tab, so the stock page's tabs are unchanged (plan Status item 8; L4); round one 13; human ask 22 |
| A8e | 8. "Saved layouts, watchlists and research are built so that later they can be shared with a group" | DELIVERED (shape only; no sharing behaviour) | `app/layouts.py` owner kind and id; plan item 8 |
| A9 | 9. "Switch billing on later without a code change: the billing code reads his Stripe keys and prices from the platform's variables; with nothing set, nothing shows" | DELIVERED | `app/billing.py` (STRIPE_SECRET_KEY, STRIPE_PRICE_ID, BILLING_PRICE_LABEL, BILLING_LIVE_APPROVED by name); `docs/turning-billing-on.md`; `tests/test_billing.py`; round one 11 (no Upgrade, no price; owner reads "Plans are not on sale yet. Every account is on Free."); human ask 29. Several prices (tiers) are round 3 by the summary |
| A10 | Factory prompt: "Delivered as a draft pull request from the Conjure fork into his repository" (DD-14), stacked on PR 19 (Card A) | PENDING AT SEND | Read 2026-11-18 with `gh pr list` on the customer's repository (upstream of the fork): only PR 19 (Pass 1, draft, open) exists; no Pass 2 pull request is open on the customer's repository yet. Opening it is outside this kit's allowed mutations; it must exist before the send, because the delivery message says this round reaches the repository as a second pull request on top of 19 |

## B. Scope carried in (issue description, "Scope carried in")

| # | Item | Resolution | Evidence |
|---|---|---|---|
| B1 | Round-one review fixes: routing (unknown paths no longer read as tickers), earnings headings, Home card wording and a visible retry, Weinstein stage, MSFT resistance, global search, the explanations rule | DELIVERED | not-found page (`pages/notfound.js`, `core/router.js`); human ask 5; suite green on 34a30b7 |
| B2 | Markets tiles with sparklines (six-screen sketch) | DELIVERED | Home "Markets at a glance" tiles with their lines (deck screenshot) |
| B3 | Milo's source badges | DELIVERED | as A4b |
| B4 | The intraday feed labelled delayed though current to the minute | DELIVERED (as recorded on Pass 1) | "Yahoo Finance, delayed up to 20 minutes" on every price panel |
| B5 | Advice policy unchanged | DELIVERED | `app/ai_policy.py` unchanged; eval sets (row E) |

## C. Deferred by agreement (later rounds, by the Round 3 to 6 text the customer received)

| # | Item | Resolution | Where agreed |
|---|---|---|---|
| C1 | Several prices (tiers), payments live | DEFERRED BY AGREEMENT | Round 3 "Take payments on your own Stripe account... against the tiers you choose" |
| C2 | The owner report page for the three signals | DEFERRED BY AGREEMENT | issue Outcome block ("Pass 3 builds the report page"); Round 3 |
| C3 | Brokerage linked live | DEFERRED BY AGREEMENT | Round 5 "Link a brokerage account live on SnapTrade once you have the agreement" |

Broader than agreed: none found. No plan tier gained anything; the evaluator account's Enterprise plan on the copy is data on our copy only (gauntlet O2), not a product change.

## D. The named outcome

| Outcome, in the customer's words | Resolution | What is counted, and where | Proof |
|---|---|---|---|
| "whether people open a stock from Home, ask Milo a question, and come back within a week" (2026-11-07) | DELIVERED (this round keeps the counts recording; the report page is round 3, as the Outcome block says) | `home_stock_open`, `milo_question` and `visit` in `usage_event` (`app/usage.py`), raw counts on the owner's Metrics page (`#/metrics`), counting since 2026-11-10 on the copy | Pass 1 tests unchanged and green inside the suite on 34a30b7 (`tests/test_pass1_usage.py`, `tests/e2e/test_pass1_journeys.py`); `tests/test_pass2_desk.py` (Milo questions from the Desk); round one item 18 (Metrics draws the signal counts as the owner); round three leave-as-found (milo_question and usage_event rows written through the changed flows). The gauntlet records wrote OUTCOME INSTRUMENTED as NOT APPLICABLE "no outcome named"; the issue does carry a `## Outcome` block, so this row resolves it from the records above instead. Noted for the retro |

## E. Milo's eval sets (internal only; never in the deck, the narration or the message)

| Set | Result on 34a30b7 | Source |
|---|---|---|
| Quality set, `tests/test_milo_eval.py` | 221 of 221 passed (181 cases plus coverage checks) | `.factory/gauntlet-2.md`, round three counts block |
| Injection set INJ-01 to INJ-14 | 14 of 14 | same |
| Red team `tests/test_milo_redteam.py` | 38 of 38 | same |
| Live smoke | not run (no key in the suite's shell); Milo answered live on the copy in rounds one to three | same |

`app/` is unchanged between 620c6d4 and 34a30b7 (`git diff --stat 620c6d4..34a30b7 -- app/` empty); the only model-facing change this round is the `in_view` field the page sends, checked and capped in `app/ai.py`; no eval case was added for it (round one note).

## Gap list, if the operator reads the HALT RULE strictly

1. A6c, the sector or holdings donut for readers with no linked brokerage (named "round two" to the customer on 2026-11-13).
2. A6d, the market-weighted sector treemap.
3. A3b, Milo given the chart in view on Investing and Earnings (they send their tab).
4. A7b, less scrolling on the Read page's Desk.
5. A8d, the company grid as a tab on the stock page (delivered by "Open as panels").
