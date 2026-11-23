# The brokerage link: tested and untested

State on 2026-11-23: **the SnapTrade flow is untested end to end on the private test site.** The reason is the one
missing input: the SnapTrade sandbox Client ID and Consumer Key, which only the account holder can create in the
SnapTrade dashboard. Everything up to the provider is tested in the suite (`tests/test_brokerage*.py`: the link
state, consent, the callback, holdings, the purge, the plan limits, the webhook signature), against recorded
responses and the built-in development sandbox; the real SnapTrade sandbox has never answered this code.

## Where the state is read

`/api/health` carries a `modes.brokerage` line:

| `snaptrade` reads | Meaning |
| --- | --- |
| `not configured` | Neither or only one of `SNAPTRADE_CLIENT_ID` and `SNAPTRADE_CONSUMER_KEY` is set. The flow cannot run. |
| `configured (sandbox)` | Both are set and `SNAPTRADE_ENV` is not `production`. The flow can be run against SnapTrade's sandbox. |
| `configured (production)` | Both are set and `SNAPTRADE_ENV=production`. |

`provider` is `BROKERAGE_PROVIDER` (`off` when unset) and `enabled` is whether linking is open, from
`app/brokerage/service.py` `status()`. Values are never shown, only whether they are set.

## Turning the sandbox on for a test

1. In the SnapTrade dashboard, create sandbox credentials (Client ID and Consumer Key).
2. Set, on the service: `BROKERAGE_PROVIDER=snaptrade`, `SNAPTRADE_CLIENT_ID`, `SNAPTRADE_CONSUMER_KEY`,
   `SNAPTRADE_TERMS_URL`, and `BROKERAGE_OWNER_ONLY=1` while only the owner tests it. `OPTIC_DATA_KEY` must already
   be set (it encrypts the link's secrets).
3. `/api/health` should read `configured (sandbox)` and `enabled: true` for the owner.
4. Walk Brokerage: Connect, the SnapTrade sandbox brokerage, back to Optic, holdings shown, Disconnect, the purge.

The live link on the owner's own SnapTrade agreement is a later round.
