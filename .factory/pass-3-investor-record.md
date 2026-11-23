# Pass 3, Investor mode: record

Round three, the Investor mode items: watchlists and alerts in one place, Portfolio with one meaning, the Markets
calendar, the first visit at Beginner, the owner report, the sign-up questions, and the carried items (the saved line,
the source lines, the owner shape on watchlists and saved research, the three accessibility items). Built on the
shared ground in `.factory/pass-3-plan.md`. Every test named here runs in `python -m pytest -q` with outbound HTTP
pinned to a closed port.

## What was built, item by item

| Item | What it does now | Files | Tests |
| --- | --- | --- | --- |
| Watchlists and alerts in one place | Watchlist (`#/watchlist`) shows each name's alerts of all three kinds beside it: yours ("1 alert", "2 fired today"), "1 from Optic's book", "1 from your brokerage", read into the row's accessible name. `#/alerts` is the Alerts view of the same place, headed Watchlist, and starts with "All alerts": every alert of the three kinds in one list, one way of drawing them (who it is from, the company, what happened, when), filterable by kind, with the sections that keep each kind's own tools below. The three stores are only read (`core/allalerts.js`); none is changed. A guest's lists stay in the browser as before | `static/v2/js/core/allalerts.js`, `pages/alerts.js`, `pages/watchlist.js`, `pages/tabs.js`, `nav.js`, `css/pages.css` | `tests/test_pass3_investor_frontend.py::test_the_three_kinds_of_alert_are_drawn_one_way_and_counted_per_name`; `tests/e2e/test_pass3_investor_journeys.py::test_watchlist_rows_carry_each_names_alerts_of_every_kind_and_alerts_is_a_view_of_watchlist`, `::test_a_guests_lists_stay_in_the_browser` |
| Portfolio with one meaning | `#/portfolio` is the reader's own books: a linked brokerage first, the Paper Desk second on the same page (never hidden), Optic's three model books last under "Optic's model portfolios", named as Optic's, with their full page at `#/models`. A plain line says which books are the reader's. The diversification figure (the measure the model books used, `app/analytics/portfolio_risk.py`) follows the book chosen, including the Paper Desk, measured by a new open route that stores nothing. Retirement is linked. The group reads Portfolio in the rail, the tabs and the phone bar | `pages/portfolio.js`, `app/investor.py`, `app/investor_routes.py` (`POST /api/portfolio-risk/positions`), `nav.js`, `core/milo-text.js` | `::test_the_readers_books_come_first_brokerage_then_the_paper_desk`; journeys `::test_portfolio_is_the_readers_book_first_and_the_diversification_follows_the_book_in_view`, `::test_a_linked_brokerage_comes_first_and_the_paper_desk_stays_beside_it`; `tests/test_pass3_investor_server.py::test_paper_positions_are_checked_before_any_market_call` |
| The setting for the old pages | `OPTIC_SEPARATE_ALERTS_AND_MODELS=on` (off by default) heads `#/alerts` Alerts again and opens Optic's model books at `#/portfolio`, as before round three. Named on `/api/health` (`modes.investor_pages`), on the owner's Metrics page, in `.env.example` and in DEPLOY.md | `app/investor.py`, `core/investorpages.js`, `pages/portfolio.js`, `pages/alerts.js` | `::test_the_separate_pages_setting_is_off_by_default_and_named_on_health`; journey `::test_the_setting_restores_the_old_separate_pages`; `::test_the_separate_pages_setting_is_read_from_health_and_restores_both_pages` |
| Markets calendar | Markets gains Calendar (`#/calendar`): two weeks of sessions from the rules `app/session.py` already models (open, a holiday, a 1:00 pm close, the weekend) in the reader's own time zone, the economic releases (`app/events.py`, best effort and named when it cannot be read), the week's earnings, and a link to the Read for what moved today. "Futures holidays are not modelled" is said on the page | `pages/calendar.js`, `app/investor.py` `session_days`, `app/investor_routes.py` (`GET /api/markets/calendar`, open) | `::test_the_calendar_marks_thanksgiving_closed_and_the_day_after_a_one_oclock_close`, `::test_the_calendar_marks_christmas_eve_short_and_christmas_closed`, `::test_the_calendar_route_is_open_and_states_the_futures_limit`, `::test_the_calendar_says_so_when_the_release_calendar_cannot_be_read`, `::test_the_calendar_says_each_session_in_the_readers_zone`; journey `::test_the_calendar_shows_a_holiday_and_a_half_day_in_the_readers_time_zone` |
| First visit at Beginner | A browser with no level chosen opens Home at Beginner with the onboarding band and the first-visit card; a signed-in reader keeps the account's level on a new browser. The default is Beginner in both `core/prefs.js` and `app/knowledge.py`; Classic's own default is unchanged | `core/prefs.js`, `app/knowledge.py` | journeys `::test_a_first_visit_lands_on_home_at_beginner_with_the_band_and_the_card[desktop/phone]`, `::test_a_signed_in_reader_keeps_the_accounts_level_on_a_new_browser[desktop/phone]`; the Pass 1 level matrix journeys unchanged and passing |
| The owner report | `#/owner-report` (owner only, the Metrics guard): the three signals over the last 30 days and per week for 12 weeks, which level readers use, the screens the events happen on, the stocks opened from Home, and came back within a week per weekly group, all counts, never a percentage or a rate; the owner's own signed-in activity left out. The address and the API take `owner_kind` and `owner_id`; today any group is accepted, named on the page as not applied, and every count is everyone's | `app/investor.py` `owner_report`, `app/investor_routes.py` (`GET /api/admin/owner-report`), `pages/reports.js`, `nav.js` | `::test_no_user_is_refused_the_owner_report` (401), `::test_the_wrong_user_is_refused_the_owner_report` (403), `::test_the_wrong_role_an_unverified_owner_address_is_refused_the_owner_report` (403), `::test_the_owner_reads_counts_per_week_and_over_thirty_days`, `::test_the_owner_report_never_shows_a_percentage_or_a_rate`, `::test_the_owners_own_accounts_are_left_out_of_the_report`, `::test_the_group_filter_is_accepted_and_today_reads_everyone`, `::test_the_owner_report_answers_in_under_two_seconds_on_fifty_thousand_rows`; journeys `::test_the_owner_report_reads_counts_by_week_and_names_the_group_it_read`, `::test_the_owner_report_is_refused_to_a_reader_who_is_not_the_owner` |
| The owner Metrics page's modes | "How this site is set" lists every mode `/api/health` reports under `modes` (whatever is registered in `app/health_extra.py`), so billing, the legal text, alert delivery, the chart history and Milo's off-topic set show there when their owners register them | `pages/reports.js` `modesBlock` | `::test_the_owner_report_page_draws_counts_only`; the owner report journey reads `investor_pages` on Metrics |
| Sign-up questions | Six optional questions after the sign-up form, and once on a band above the page for any account that has never seen them (Google, Apple, passkey, or any account before round three). Skip is the same size as Continue. A suggested level with one sentence of why; written to the account only on "Use", changeable after in Settings and on Home. The answers are scored by the server and forgotten: only the suggested level, the outcome and that the questions were shown are kept (`user_preferences.level_quiz`). No modal | `pages/levelquiz.js`, `pages/signin.js`, `app.js`, `app/investor.py`, `app/investor_routes.py` | `::test_the_questions_are_five_to_eight_each_optional_and_each_suggests_a_level`, `::test_questions_need_a_reader`, `::test_answers_are_never_stored_and_accept_writes_the_level` (reads every table), `::test_skip_writes_only_that_the_questions_were_skipped`, `::test_the_level_stays_changeable_after_the_questions`, `::test_offered_after_a_password_sign_up`, `::test_offered_after_a_google_or_apple_sign_up[google]` (through the real callback, exchange stubbed), `[apple]` (through the linking path the callback uses; Apple's callback needs a paid membership configured), `::test_offered_after_a_first_passkey_sign_in` (real WebAuthn verification); journeys `::test_the_sign_up_form_leads_to_the_questions_and_accepting_writes_only_the_level` (keyboard only, reads every table), `::test_an_account_made_another_way_is_offered_the_questions_once_on_a_band` |
| Owner shape on watchlists and saved research | Every new watchlist and saved research item is written with `owner_kind` 'user' and `owner_id` the person (migrations 23 and 24 set every existing row); reads unchanged; no sharing | `app/account.py`, `app/library.py`, `app/investigation.py` | `::test_new_watchlists_and_saved_research_carry_their_owner`; `tests/test_pass3_migrations.py` |
| The saved line (F2) | A plain "Saved: Morning check is on your account." line beside the layout form when a save lands, kept until the next change to the form; the toast stays as the second signal | `pages/workspace.js` (the named-layout form only), `css/pages.css` | `::test_the_saved_line_sits_beside_the_layout_form_until_the_next_change`; journey `::test_a_saved_layout_says_so_beside_the_form_until_the_next_change` |
| Source lines as sentences (O3) | Every Financials source line reads as a sentence after "Source:", whatever case the feed sent | `pages/financials.js` (`sourceText`) | `::test_the_source_lines_read_as_sentences`; `tests/test_pass2_provenance.py` updated |
| Accessibility, the three items | The Earnings estimate revisions table is a named keyboard stop with a caption at every width; the failure toast has its own colour at 7.3:1 against its text in every theme (the dark themes measured 2.41:1); scrolling table boxes get distinct names (a fold's "View data" is named with the heading before it; any still-shared name is numbered "2 of 3") | `pages/earnings.js`, `css/tokens.css`, `css/pages.css`, `ui/align.js` | `::test_the_three_accessibility_items`, `::test_toast_failure_kind_contrast_is_aa_against_its_text`; journeys `::test_the_earnings_revisions_table_is_a_named_keyboard_stop_at_phone_width`, `::test_the_failure_toast_meets_aa_contrast_in_the_dark_theme`, `::test_the_financials_table_boxes_have_distinct_names` |
| axe on the changed screens | WCAG 2.1 A and AA, zero violations at 1440 and 390 on Watchlist, Alerts, Portfolio, Calendar, the questions, the owner report and Earnings. Found and fixed on the way: the shell's search button and account button named by words that did not contain what they show, and the watchlist row named by a summary that did not contain its visible words (axe `label-content-name-mismatch`, seen once signed in) | `ui/shell.js`, `pages/watchlist.js`, `css/pages.css` | `::test_the_changed_screens_have_no_axe_violation[...]` (10 cases), the owner report and Earnings journeys |

## The sign-up questions, exactly

1. How long have you been investing? Not yet / Less than a year / One to five years / More than five years
2. What brings you to Optic most? Learning how markets work / Researching companies I might own / Planning and tracking trades
3. How long do you usually hold an investment? Not sure yet / Years / Months / Days or weeks
4. What do you use today? Nothing yet / A brokerage app / Spreadsheets or a stock screener / Charting or options tools
5. When you look at a price chart, what do you read? Mostly whether it went up or down / Trends and moving averages / Indicators, volume and patterns
6. What would you most like from Milo? Plain explanations of the terms / A second opinion on my research / Fast answers with the figures

Each answer scores 0, 1 or 2; the average of what was answered suggests Beginner (under 0.75), Intermediate (under 1.5)
or Advanced. Nothing answered suggests nothing.

## The owner report's response time

Measured on the ops Mac, `app/investor.py` `owner_report` over seeded `usage_event` rows: about 700 rows (the
evaluation copy's size) median 0.007 s, worst 0.025 s; 50,000 rows median 0.26 s. The suite asserts under two seconds
on 50,000 rows through the route, and the journey under two seconds for the page on 700 rows. To be measured again on
the copy's own data after the redeploy.

## Decisions (each reversible)

- "What people open" is read from the three events already recorded (the screen each happened on, and the stocks
  opened from Home). Nothing new is counted: the round says the activity monitoring is unchanged, so per-screen page
  views are not recorded and the report says what is counted.
- The group filter answers 200 for any of everyone, user or org, names the group asked for and says it was not applied;
  an unknown kind is a 400. The organization round makes it apply.
- The questions are offered once to every account with no record of them, including accounts made before round three:
  the band appears once on their next signed-in visit and "Not now" records a skip.
- The questions' band is a section above the page, not a dialog.
- The model books' tab is "Optic’s model portfolios" (a typographic apostrophe, as the page names them); the
  group is Portfolio. Classic keeps its own names.
- A guest's Paper Desk kept in a browser is counted as an account's only after the reader brings it in (the existing
  "Keep what you made?" rule); until then a signed-in reader's Portfolio shows the Paper Desk as empty on that browser.

## Existing tests changed on purpose, with the reason in each

`tests/test_frontend_v2.py` (Positions reads Portfolio; the model books' new name), `tests/test_v2_beginner.py` (the
same names), `tests/test_knowledge_modes.py`, `tests/test_pass1_levels.py`, `tests/test_v2_knowledge_level.py` and
`tests/e2e/test_pass1_journeys.py` (the first visit at Beginner), `tests/test_pass2_provenance.py` (the source line as a
sentence).

## Not done here, and why

- The rail's Charts & Technicals preset targets and the trading layouts are the charts work's; the chart widgets'
  "Open Optic Portfolio" link (`pages/chart-widgets.js`) still points at `#/portfolio` and should point at `#/models`.
- The inline Milo panel is the Milo work's; the pages here only provide their context as before.
