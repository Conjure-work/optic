# Pass 3 record: billing on the owner's Stripe, the terms and privacy pages, and readers' alert emails

Round 3 items 6 (payments, plan access, portal, terms and privacy) and the carried-in alert delivery per reader.
Route-level and browser-journey record from the build; the proof against Stripe's real test mode is the evaluation
copy's run, not this file.

## What was built

| Piece | Where | Tests |
| --- | --- | --- |
| The plan ladder: the three plans in `PLANS` with one price id per paid plan (`STRIPE_PRICE_ID_PRO`, `STRIPE_PRICE_ID_ENTERPRISE`; `STRIPE_PRICE_ID` still the Pro price); labels and prices are variables | `app/billing.py` | `tests/test_pass3_billing_ladder.py` |
| The plan follows the price Stripe bills, never metadata; the highest plan among the items wins; a foreign price grants nothing; `invoice.paid` re-reads the subscription and derives again | `app/billing.py` `plan_of`, `apply_event` | the same file: portal upgrade and downgrade, cancel at period end, resume, deletion, the metadata mismatch, invoice.paid with Stripe up and down, duplicates |
| Checkout sells the plan asked for at its own price; a reader on any paid plan is sent to the portal instead | `POST /api/billing/checkout` with `{"plan": ...}` | the same file, and the browser journey |
| Off, partial, live refusal: nothing set shows nothing; a partial set reads as off and names the missing variables to the owner; a live key still needs `BILLING_LIVE_APPROVED` | `status()`, `missing()` | the same file |
| Health: `modes.billing` (on or off, mode, plan count, how caps are decided) for everyone; `modes.billing_setup` (missing names, the copy's legal switch) for the owner | `app/health_extra.py` readers registered by `app/billing.py` | the same file |
| Terms and privacy from `legal/terms.md` and `legal/privacy.md`; placeholder until counsel's text; Checkout refused with the pages' sentence meanwhile | `app/legal_text.py`, `pages/legalpages.js`, `legal/`, the Dockerfile copies `legal/` | `tests/test_pass3_legal.py`, journeys |
| Settings: one row per plan with what it allows and its price, one button each; the refusal sentence instead while the terms are the placeholder; Manage billing for a paying reader | `pages/settings.js` | journeys and axe |
| Alert emails to readers behind `ALERT_DELIVERY_READERS` (off): one digest per pass of a reader's own watch hits at their own address, each hit once (`watch_delivery`), pending when the relay refuses; the owner summary unchanged | `app/alerts.py` `deliver_to_readers`, `/api/alert-delivery/me`, called at the end of `watch_runner.run_once` | `tests/test_pass3_alert_delivery.py`, journeys |
| Stripe in the suite: a recording stub on a local port (`STRIPE_API_BASE`, `STRIPE_TIMEOUT_SECONDS`) | `tests/support/stripe_stub.py` | every billing test |

## Decisions taken in the build (each reversible in review)

- **The published terms stay readable under the placeholder.** The pages already carried terms and a privacy policy
  in force since October 19, 2026 (drafted for the owner, not reviewed by counsel). Taking them down for a one-line
  placeholder would leave a site that collects accounts with no privacy policy at all. So while the files hold the
  placeholder, each page shows "being prepared with counsel" above that draft, and Checkout stays closed; counsel's
  text in the files replaces both.
- **Caps.** What each plan allows was already enforced in one place (`auth.store.subscription`, read by Milo's spend
  guard and the brokerage entitlement), from the stored plan, whether or not billing was on. That is unchanged in
  both states: off, plans are the stored rows (granted by the owner); on, Stripe's webhook writes them. Health says
  which.
- **One switch for a test copy.** `BILLING_TEST_IGNORE_LEGAL_PLACEHOLDER=true` opens Checkout before counsel's text
  exists, on a test key only, so the Checkout and webhook round trip can be proved on an evaluation copy. A live key
  ignores it.
- **Not added:** Stripe metadata tagging per store and Checkout branding settings, which are defaults for products a
  factory hosts on its own Stripe account; this is the owner's own account and code.
- The brokerage page no longer tells a reader that "linking is part of the paid plan" while nothing is on sale; the
  owner still sees why.
- The top bar's search and account buttons now carry names that start with the words on them (WCAG 2.5.3, label in
  name). The installed axe-core 4.14 flagged both on every screen, the Pass 2 accessibility journeys included.

## The webhook behind a gate

`POST /api/billing/webhook` reads no session and no CSRF token: Stripe's signature over the raw body is its whole
authentication (five-minute tolerance, each event id once). A basic-auth gate in front of a test copy therefore needs
exactly that one path let through for Stripe's test-mode events to arrive.

## Left for the evaluation copy

Checkout completed with a published test card at Stripe's hosted page, the webhook arriving from Stripe's test mode
and moving the reader's plan, a plan change made in the customer portal, and a reader's alert digest arriving in the
mail sink with the switch on, then off.
