# Pass 3, Milo hardened: what was built and how it is tested

Branch `p3/ws-c2` over the shared ground (bdb0571). Round three's item 7 (Milo trusted further) and the two carried
items that are Milo's: item 2 (Investing and Earnings tell Milo the chart in view) and item 3 (the Read page's Desk).

## Per item

| Item | Built | Tests |
| --- | --- | --- |
| Off-topic set | 24 cases in `tests/milo_eval/offtopic.py` (general chat 8, other products and tasks 5, personal advice outside investing 5, code 6) and 10 near misses (market questions that borrow an off-topic word). `app/ai_policy.py` `classify_offtopic`: an off-topic question is declined before any model call; a question that names the market, a company or a filing is never caught for general chat or personal advice | `tests/test_pass3_milo_refusals.py`: each case declined with no model call, the quality set (181 cases), the advice set E (120) and the near misses never caught |
| One refusal composer (A9) | `ai_policy.refusal_line`: "Milo can't <the policy's reason first, then the off-topic reason>; it can <what Optic can do on this screen>." One sentence, one shape (`REFUSAL_SHAPE`); `reader_line` is its policy-only case, so the existing policy line keeps its words | every off-topic case, every hostile (INJ-01 to INJ-14) and advisory case, and set E: exactly one refusal sentence of the shape when declined, none when not |
| Grounding: tools per screen | `app/milo_tools.py` `SCREEN_TOOLS`: research screens allow every market tool and the reader's own tools (under their existing rules); account, legal and owner screens allow `lookup_company`, `get_quote`, `get_market`, `get_news` and the reader's watchlists. `Toolbox.run` refuses a tool not offered before reading its input | `tests/test_pass3_milo_grounding.py`: every route in app.js's route table is named in the list (enumerated, not hand kept); a model that asks for the screener on Settings never runs it |
| Grounding: figures cited | `ai_policy.ground`: each money figure in an answer must match the page's figures or a lookup at the precision written (0.5 percent for rounding and units); the lookup behind each matched figure is sent as `cited` and shown under the answer ("Figures from: $199.04 from AAPL quote (Yahoo Finance)"); a sentence with a money figure nothing supports is taken out with a note, as an advice sentence is | grounding tests: cited with the tool, unsupported removed with `GROUND_NOTE`, units and rounding |
| Named stances | the five personas in `app/ai.py` are stances labelled in plain words (below), sent as a `stance` event before the answer and kept with it; picked for one answer in the compose row or kept from Response settings; signed in, kept on the account (`GET` and `PUT /api/milo/stance`, `user_preferences.milo_stance`); the chat route uses the account's stance when a page sends none | `tests/test_pass3_milo_stances.py`: each stance through the advice set E (policy text in every request, the declined-question block after the stance's block, no stance text breaking the policy), the label before the text, the route's three legs (no user 401, no CSRF 403, another reader's stance never read or written), the kept stance used by the chat route |
| Streamed steps | `step` events: each source the research pack was read from, then each lookup as it is called and what it returned ("Read AAPL quote", "Could not read ...", "Not run: that lookup is not available on this screen"); the panel lists them above the answer while it streams and folds them under it after ("Steps Milo took (n)"). Text only; nothing animates, so reduced motion changes nothing | stream tests (order: steps before text); journey against the recording stub's new `tool` mode (a lookup round, then the answer held 1.5 s), with and without reduced motion |
| Milo on every screen | `ui/milo-inline.js`: a strip under the top bar on every route (drawn by the shell outside `#main`, repainted by app.js on each route) with one offer naming what is on the screen and a toggle that opens Milo beside the page (the docked panel of `ui/milo.js`, a sheet on a phone) or collapses it back, `aria-expanded` kept true to the panel | journey: a walk of every route in the route table finds the strip and its screen's offer; the offer asks with the chart in view; the toggle opens and collapses from the keyboard with focus kept; axe at 1440 and 390, collapsed and open, on Home, Financials and the chart page |
| Carried item 2 | `pages/investing.js` and `pages/earnings.js` watch the section in view (`ui/inview.js`) and send it as `in_view`, as Financials does | `tests/test_pass3_milo_carried.py`; journeys for both tabs (the section pressed is the one Milo is told) |
| Carried item 3 | `pages/read.js` draws the shared `PANELS.desk` panel from `pages/workspace.js` with `/api/home`'s Desk, the full written edition with its cited sources folded under it | text contract; journey (the shared panel's main and side columns on the Read page) |
| Health | `modes.milo_offtopic` on `/api/health`: the patterns' version, the kinds, and the size of the set they were held to in the suite (24) | `tests/test_pass3_milo_carried.py` |
| The live runner | `tests/milo_eval/run_live.py` points the off-topic set, the hostile set and a sample of the quality set at a deployed copy through its gate, signed in; values only from the environment, never printed | offline judge tests; refuses to start without its variables and prints none of their values |

## The stance labels

| Stance | Its name in Response settings | The label on an answer |
| --- | --- | --- |
| neutral | Neutral analyst | A neutral analyst's reading |
| longterm | Long-term investor | A long-term investor's reading |
| stoic | Risk and process | A conservative investor's reading |
| quant | Statistician | A statistician's reading |
| skeptic | Devil's advocate | A skeptic's reading |

## The offer per screen

Home "Explain what moved on Home today"; a company's Overview "Explain why AAPL is moving today"; Financials "Explain
the chart in view on AAPL's Financials"; Investing "Explain the chart in view on AAPL's Investing page"; Earnings
"Explain AAPL's latest report and the chart in view"; Chart "Read this AAPL chart: its trend, levels and studies";
Options "Explain AAPL's options chain and expected move"; News "What changed in AAPL's latest news"; Read "Explain
today's Read and what moved"; Macro "Explain the macro picture on this page"; Indices "Explain how the major indexes
are trending"; Watchlist "What moved on my watchlist today?"; Alerts "Explain the alerts that fired"; Brokerage
"Describe the holdings in my linked accounts"; Paper Desk "Explain the positions in my Paper Desk"; Optic's model
portfolio "Explain the positions in Optic's model portfolio"; Settings "Explain what each of these settings changes";
every other screen as listed in `ui/milo-inline.js` OFFERS, and "Explain what is on this page" for a screen with none.

## Decisions

- Five stances, not four: Milo has five personas (the skeptic is the fifth), so `app/auth/store.py` STANCES gained
  "skeptic".
- An off-topic question is declined by the server before any model call and costs the reader one question of the
  allowance (counted as a Milo question, the owner's signal).
- Percentages are cited when they match but never removed: a change worked out from two figures in the evidence is
  research, and a pattern cannot tell it from an invented one. Money figures are held to the evidence.
- The strip starts collapsed; Milo opens beside the page on a press and stays open from page to page, as the docked
  panel already did. It is not opened on every page load, so focus is never taken from the page.
- The Read page keeps the full written edition (its sections and cited sources) folded under the shared panel, so
  nothing the Read showed is lost.

## Acceptance (items 15 to 18, the Read Desk part of 19, 24 for the strip, panel and stance picker)

- 15: met in the suite. Hostile set 14 of 14 and the red team 38 of 38 unchanged and passing; off-topic set 24 of 24
  declined in the one shape; per-screen allow-list enforced and tested; figures cited with their lookup.
- 16: met (journey and unit).
- 17: met against the recording stub with timed events; reduced motion checked.
- 18: met: every route walked from the route table, the strip and its offer on each; the chart in view carried on
  Financials, Investing and Earnings.
- 19 (Read Desk): met.
- 24: no axe violation on Milo's strip or panel, collapsed and open, at 1440 and 390, on Home, Financials and the
  chart page; keyboard journeys for the strip's toggle and the stance picker. Limit: in this suite's environment axe
  also reports `label-content-name-mismatch` on the top bar's search and account buttons and Home's sector picks. They
  are present on the Pass 2 head (the clean run of 92dbcca fails 23 axe journeys of Pass 1, Pass 2 and the visual
  update for this reason), outside this work, and are left to the integration.
