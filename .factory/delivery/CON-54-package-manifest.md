# Package manifest, CON-54 Pass 2: Optic

Kind of document: the delivery kit's package manifest, an internal comment body, minus all secrets. Product Optic; issue CON-54 "Pass 2: Optic", Pass 2; free round (Free label, students offer, free pass 2 of 3: no invoice, no money in anything the customer reads); full lane (deck, video, two diagrams). Evaluation environment: Railway project `conjure-optic-eval`, environment `production`, service `optic` behind `edge-optic`, mail sink behind `edge-optic-mail`. Written 2026-11-18 by the delivery kit session.

**KIT STATUS: built, not sent.** Every artifact is in hand. Two things stand before the send card: machine check 5 is RED (CI's suite job times out, below) and Step 0 row A10 (the Pass 2 draft pull request on the customer's repository does not exist yet).

## Gate

Read from Linear through the API on 2026-11-18 at about 14:35 ET: CON-54 in Gauntlet with labels Artifacts and Free. The label went on under card D-54-1 (`Conjure/handoffs/optic-pass-2/D-54-1-card.md`). This session made no Linear write, no console or `scripts/ops-write.sh` call, no Railway call (so no `railway auth` mode to report), and posted nothing.

## Commit delivered and tested

- Fork sidprobstein/optic, branch `factory/pass-2-works-data-workspace`, code **34a30b71c56866c8c41f62e1c922f0555c5f1f7c**; branch tip 92dbcca adds only the round-three gauntlet record. The fork has no main of ours: its `main` mirrors the customer's, so the delivery branch was cut from the pass branch.
- Deployment f33bedf0-b97c-480a-b293-e577e671b930, page build id 7689d8061f5e, DEPLOY VERIFIED (round three). Confirmed again from outside on 2026-11-18: build id 7689d8061f5e served through the gate; 401 without it.
- Suite from clean on 34a30b7: 9,174 passed, 0 failed, 1 skipped (internal only).

## Step 0 outcome

CONFORMS, with five deferrals on the operator's call to round 3 (the holdings donut, the sector treemap, Milo told the chart in view on Investing and Earnings, the Read page's Desk, the company grid as a tab), recorded as L4 by the plan and every gauntlet round and named by the operator's brief as limits to state. They are not yet agreed with the customer in writing; the deck (page 18) and the message state each one. A strict reading of the HALT RULE treats the donut and the treemap as undelivered agreed items (the customer was told on 2026-11-13 the donut is round two): for the operator to confirm on the deck card. DELIVERED 24, DELIVERED DIFFERENTLY 4, DEFERRED (operator's call) 5, DEFERRED BY AGREEMENT 3, NOT TESTABLE ON THE COPY 1 (brokerage link), OPEN QUESTION 1 (alert email recipient), PENDING AT SEND 2 (the six results, carried by the message; the Pass 2 pull request). Named outcome: DELIVERED (the three signals keep recording; the report page is round 3). Note for the retro: the gauntlet records wrote OUTCOME INSTRUMENTED "NOT APPLICABLE: no outcome named" though the issue carries a `## Outcome` block. Eval sets on 34a30b7 (internal only): quality 221 of 221, injection 14 of 14, red team 38 of 38; live smoke not run. Broader than agreed: none. Table: `.factory/delivery/CON-54-step0-conformance.md`.

## Files

| File | Bytes | md5 | Committed | Notes |
|---|---|---|---|---|
| `CON-54-step0-conformance.md` | about 17 KB | | yes | Step 0 table |
| `CON-54-optic-architecture.json` | 17,141 | | yes | 25 components, 31 paths, 4 traces (21 steps), validated clean |
| `CON-54-optic-workflow.json` | 7,493 | | yes | 5 lanes (2 of them people), 15 steps, 14 flows, one journey, validated clean |
| `CON-54-optic-architecture.html` | 95,759 | 1b3f40f9a135fcb6790a07ec28de8450 | no (regenerable) | canvas 2216 x 1200 units; attach |
| `CON-54-optic-workflow.html` | 75,649 | 7a8cd9bdb4d482511e1f796a1e4e6087 | no (regenerable) | canvas 3586 x 798 units; attach |
| `CON-54-optic-pass2-delivery-deck.pdf` | 3,558,878 (3.6 MB) | fca42722a738192dacbbd05c0d67d27b | yes | 24 pages, 960 x 540 pt, 4 reviewer pages after one divider; attach |
| `CON-54-optic-pass2-delivery-narration.md` | 6,348 | | yes | 12 beats, clips measured |
| `CON-54-optic-pass2-delivery-video.srt` | 3,843 | | yes | 12 captions from the measured clip timings |
| `CON-54-optic-pass2-delivery-video.mp4` | 15,578,055 (15.6 MB) | 57b2fa85f7645bccedfe846a81efa12a | no (media) | 720p web encode; attach |
| `CON-54-checks.md`, `CON-54-pre-send-checklist.md`, this file | small | | yes | |

All of the above under `/Users/sid/Code/claude_work/optic-wt-delivery-pass-2/.factory/delivery/` (worktree of the fork on branch `factory/delivery-optic-pass-2`).

Outside the repositories: the 1080p master `/Users/sid/Code/claude_work/Conjure/handoffs/CON-54-optic-pass2-delivery-video-1080p.mp4` (40,631,424 bytes) and its .srt; the per-beat takes `/Users/sid/Code/claude_work/Conjure/handoffs/CON-54-recording/` (eleven .webm and `rec-log.json` with each take's start offset; 63 MB); the narration clips `marketing/videos/build/audio/optic2_s01.wav` to `optic2_s12.wav` (measured 15.48, 25.58, 21.96, 20.98, 17.47, 15.84, 17.14, 17.06, 9.12, 20.04, 17.33, 7.06 s), the segments in `marketing/videos/build/seg/` and the closing card `marketing/videos/build/frames/optic2_close.png`, all in `/Users/sid/Code/claude_work/Conjure-wt-delivery-optic-pass-2/` (untracked); the build manifests `marketing/videos/build/optic-pass2.json` and `optic-pass2.rec.json` (committed in the Conjure branch). The deck's HTML source and images: `/Users/sid/Code/claude_work/Conjure/customers/optic/pass-2/deck-source/` (gitignored). The deck was authored as HTML and printed to PDF by Chromium; there is no PPTX. The recorder and capture scripts: `/private/tmp/claude-501/-Users-sid-Code-claude-work/af39d319-3b3e-44e2-8ba0-0f7137191302/scratchpad/k54/` (`record.py`, `cap/cap.py`, `undo.py`, `pdf.py`).

## The video, ffprobe on the exact file to attach

```
ffprobe -v error -show_entries format=size,duration:stream=codec_name,bit_rate -of default=noprint_wrappers=1 CON-54-optic-pass2-delivery-video.mp4
codec_name=h264
bit_rate=444771
codec_name=aac
bit_rate=119364
duration=217.615333
size=15578055
```

1280 x 720, 30 fps, H.264 high, AAC 48 kHz stereo, faststart, CRF 21 (first rung, under 45 MB), narration loudness-normalised to -16 LUFS by two-pass loudnorm (measured -20.37 LUFS in). Voice en-US-AndrewNeural at +4% through `narrate.py`; the house edge-tts install (7.2.8) was refused by the service (403), so the clips were made with edge-tts 7.3.1 in a scratch virtual environment, same voice and rate.

Beats, all live on the private test site at build 7689d8061f5e on 2026-11-18 between about 14:55 and 15:05 ET (market open) except the diagram and the closing card: (1) the commission over the workflow diagram; (2) the journey walked, fifteen steps, motion on; (3) Home, Read, Indices, the not-found page, Brokerage off; (4) Index Read on the S&P 500 row, the research sheet; (5) Cash flow by quarter pressed, Ask Milo, the answer streaming; (6) a chart's source line, Insider trades at 10 years; (7) Watchlist rows with today's lines, 1D; (8) Financials by year, Earnings price-target range; (9) the Optic Desk's right column; (10) Customize, one panel's group changed, a layout saved, Saved layouts, Open as panels; (11) the owner's Settings ("Plans are not on sale yet") and Metrics, figures blurred; (12) the closing card. Narration 3:38.

## Presentation edits, named

- Beat 11: every digit on Metrics and every network address on the owner's Settings blurred in the page by the recorder, and the Metrics tab that names the model's maker hidden (style only; no data changed). The first take of beat 11 showed them unblurred and was discarded (overwritten) before assembly.
- Beat 4's narration says deep research, passkeys and the alerts page work as well; those three are not shown on camera in this video (they were walked in the gauntlet and the human half).
- Deck: Metrics figures blurred; the Milo panel cropped above its allowance line.

## Messages spent and edits to data

- Evaluator account: three Milo messages (two for the deck's Milo still and one on camera, beat 5), against an allowance of 4,000 a day on this copy; Index Read asked once on camera; sessions from each fresh browser left to expire; `usage_event` visit rows from each browser.
- Owner account: no message; sessions left to expire.

## Demo edits left standing on the test site

None. The layout "Morning check" saved on camera (beat 10) was deleted afterwards (`/api/layouts` read back: 0 layouts); the link-group change made on camera lived only in that layout and the recording browser, and a fresh signed-in browser shows Quote and chart in the Blue group as before. The 1D press is a page view, not stored.

## Documents read, with their updated stamps

Linear-mirrored, from the main checkout at c6e885b (stamps equal to origin/main 831c3a3): Delivery artifacts standard 2026-10-22T01:48:23.266Z; Video production standard 2026-10-22T01:48:24.154Z; Delivery checklist 2026-11-06T19:59:38.473Z; Factory process overview 2026-11-06T19:59:37.836Z; Customer notification templates 2026-11-06T19:59:37.229Z; Factory operations guide 2026-10-27T22:01:58.045Z (CUSTOMER VOCABULARY). Not mirrored, no stamp, last commit stands in: product/llm-pattern.md (8a395c6, 2026-10-03), product/outcomes-and-metrics.md (c32c8ed, 2026-09-28). Also: Conjure/CLAUDE.md, skills/CUSTOMER-TONE.md, skills/GIT-POLICY.md, skills/DECISION-CARDS.md, optic-build/CLAUDE.md, the delivery kit skill with its references and diagrams/CONTRACT.md. Inputs: CON-54's description and comments (Linear API, 2026-11-18), `customers/optic/pass-summary-2026-11-17.md` (Round 2), `handoffs/optic-pass-2/` (gauntlet rounds one and two, the human half with its round-three re-walk, deploy-verify rounds one and two, D-54-1), the round-three gauntlet record in the fork's `.factory/gauntlet-2.md` (commit 92dbcca). `Conjure/handoffs/optic-pass-2/deploy-verify-CON-54-round3.md` ("DEPLOY VERIFIED at 34a30b71c56866c8c41f62e1c922f0555c5f1f7c on f33bedf0-b97c-480a-b293-e577e671b930 ... build id 7689d8061f5e") and `gauntlet-CON-54-round3.md` (Readiness: machine half on 34a30b7, D4 and D5 fixed and re-verified, suite from clean green apart from the one standing skip) appeared after the kit was built and were read before the final commit; they agree with the fork's record used above.

## Lints run

- Deck: never-list grep over the extracted text split at the divider, the count grep, the dash grep, a name grep: clean (CON-54-checks.md item 3).
- Narration and captions: mechanism and never-list grep over `text`, `say` and the .srt: clean apart from "test" in "private test site" and "test keys". No figure spoken.
- Message: clean apart from the host's own address for the private link and the mail inbox (as Pass 1).
- Names: no "Alexander", "Yazji" or "Alex" in the deck source and text, the narration, the captions, either diagram, the message or this kit's other files.
- Credentials: the three secret values of the key file matched by value in a script that prints counts only, across 57 kit files (delivery folder, deck source, build manifests, rec-log, recorder scripts and logs): 0 matches. The delivery message carries them, by design, and is untracked.

## Limits carried to the customer

L1 brokerage link (SnapTrade test keys), L2 alert email recipient, L3 the save notice's contrast and the Earnings table on a phone, L4 the five items deferred to round 3, L5 repeated table names on Financials: deck page 18 and reviewer page D, and the message. O1 (memory and open files growing at rest, 1.8 GB and over 500 descriptors after the round-three suite) is for the operator; the deck's reviewer page D names it in one plain sentence without figures. Operator's call whether that stays.

## Key file

`~/.conjure/optic-eval.key` read by the recorder into process memory only, never printed or written; still in place, as the brief says. Delete it once the artifacts are accepted.

## Record of this kit

Send time: [to be filled at the send]

Commits and pull requests: fork sidprobstein/optic, branch `factory/delivery-optic-pass-2` (cut from `factory/pass-2-works-data-workspace` at 92dbcca), kit commit e9baf74, pull request https://github.com/sidprobstein/optic/pull/1 (base: the pass branch, not the customer's repository); Conjure sidprobstein/conjure-work, branch `factory/delivery-optic-pass-2` (cut from origin/main 831c3a3), record commit 8c82cdf, pull request https://github.com/sidprobstein/conjure-work/pull/398. Not merged. This line added by a follow-up commit on each branch.
