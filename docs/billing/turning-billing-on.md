# Turning billing on

Optic's billing is off until its variables are set on the platform (Railway: the `optic` service's Variables).
With none of them set, no reader sees anything about plans or prices; the owner's Settings page, `/api/health`
(signed in as the owner) and the owner Metrics page name the variables still missing. Names only here: the values
live in Railway's variables and your Stripe account, never in this repository. Conjure never holds your keys.

## The plan ladder

The plans are the three already in `app/auth/store.py` (`PLANS`): Free, Pro and Enterprise, each with its caps
(assistant messages a day and in 30 days, watchlists, saved items, brokerage connections and accounts, manual syncs).
A paid plan is on sale when its Stripe price id is set; leave Enterprise's unset and only Pro is offered. The plan a
reader is on is derived from the price Stripe is billing, never from anything written at Checkout, so a change made
in Stripe's customer portal or Dashboard moves the plan too. Caps are enforced the same way whether billing is on or
off: off, plans are what the stored rows say (as before round three); on, Stripe's webhook writes the rows.

Changing a plan's price is a new Stripe price and a new variable value, no code change. Renaming a plan on screen is
`BILLING_PLAN_LABEL_<PLAN>`. A new tier with its own caps is a row in `PLANS` and one more price variable.

## What you need first

- A Stripe account in your company's name, with its bank account connected.
- One Product per paid plan (for example "Optic Pro" and "Optic Enterprise"), each with one recurring Price. A price
  id starts with `price_`.
- A restricted key rather than the account's secret key, with only these permissions: Checkout Sessions write,
  Customers write, Subscriptions read, Prices read, Customer portal write. Test mode first.
- The customer portal turned on in Stripe (Settings, Billing, Customer portal), with the plans readers may switch
  between listed there.
- A webhook endpoint in Stripe pointing at `https://<your domain>/api/billing/webhook`, sending
  `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`,
  `customer.subscription.deleted`, `customer.subscription.paused`, `customer.subscription.resumed`,
  `invoice.paid` and `invoice.payment_failed`. Stripe shows its signing secret once; it starts with `whsec_`. The
  route needs no sign-in and no browser cookie: Stripe's signature is its authentication, so a gate in front of the
  site must let that one path through.
- Your terms of use and privacy policy from counsel, in `legal/terms.md` and `legal/privacy.md` (see below):
  Checkout stays closed while they are the placeholder.

## The variables

| Name | What it holds | Required |
| --- | --- | --- |
| `STRIPE_SECRET_KEY` | the restricted key above; test mode first | yes |
| `STRIPE_WEBHOOK_SECRET` | the webhook's signing secret | yes |
| `STRIPE_PRICE_ID_PRO` | the Pro price id (`STRIPE_PRICE_ID` is still read as the Pro price if this is unset) | at least one paid price |
| `STRIPE_PRICE_ID_ENTERPRISE` | the Enterprise price id | no |
| `STRIPE_PRICE_ID` | the Pro price id, the name used before round three | no, if `STRIPE_PRICE_ID_PRO` is set |
| `BILLING_LIVE_APPROVED` | `true` only when you switch to live keys; a live key without it is refused | for live only |
| `BILLING_PRICE_LABEL` | the words beside the Pro button, if you want your own; otherwise Optic reads the amount and interval from the Stripe price | no |
| `BILLING_PRICE_LABEL_<PLAN>` | the same for another plan, for example `BILLING_PRICE_LABEL_ENTERPRISE` | no |
| `BILLING_PLAN_LABEL_<PLAN>` | a plan's name on screen, if not the one in `PLANS` | no |
| `BILLING_TEST_IGNORE_LEGAL_PLACEHOLDER` | `true` opens Checkout before counsel's text is in place, on a test key only; a live key ignores it. For proving the round trip on a test copy | no, never on your live site |

Partly set (a key but no price, say) reads as off: readers see nothing, and the owner sees the missing names.

## The terms and privacy text

`legal/terms.md` and `legal/privacy.md` start as placeholders, each with the line `optic-legal: placeholder`. While
either holds it, the Terms and Privacy pages say the text is being prepared with counsel above the draft published on
October 19, 2026, `/api/health` reports `legal_text: placeholder`, and Checkout is refused with that sentence. Replace
each file's whole content with counsel's text in Markdown (headings with `#`, paragraphs, `-` lists, links as
`[words](https://...)`) and deploy: the pages render it, and Checkout opens.

## Order

1. Set `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` and `STRIPE_PRICE_ID_PRO` (and `STRIPE_PRICE_ID_ENTERPRISE` if
   you sell it) with test-mode values. Railway redeploys the service.
2. Open Settings signed in as a reader: the Plan section lists each plan with what it allows and its price. Until the
   legal files hold counsel's text it says so instead of offering Checkout.
3. With counsel's text deployed, subscribe with Stripe's test card 4242 4242 4242 4242 and check the plan changes only
   after the webhook arrives; open Manage billing and change plan in the portal, and check Settings follows.
4. When the test run is right, replace the key, the webhook secret and the price ids with live values and set
   `BILLING_LIVE_APPROVED=true`.

To switch billing off again, remove `STRIPE_SECRET_KEY`. Readers see no plans; existing paid rows stay as they are.

## What Stripe shows

Checkout, receipts and the customer portal show your Stripe account's name and branding, set in Stripe's own
settings (Settings, Branding). Refunds are made in the Stripe Dashboard; Settings in Optic sends readers to the portal
for receipts and changes.
