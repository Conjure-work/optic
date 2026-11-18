# Pre-send checklist, CON-54 Pass 2: Optic

Numbered to match the Delivery checklist (mirror `updated: 2026-11-06T19:59:38.473Z`) and the kit's `references/pre-send-checklist.md`. Filled 2026-11-18 by the delivery kit session up to, not including, the send. [M] is a machine check (evidence in `CON-54-checks.md`); [CARD] is the operator's. Nothing at or below the send is done.

## Readiness precondition

- [x] Deployed in place on the one evaluation environment: `conjure-optic-eval` / `production`, deployment f33bedf0, build 7689d8061f5e, code 34a30b7, DEPLOY VERIFIED (round three).
- [x] Gauntlet passed on that deployment: machine half rounds one to three, human half 31 of 32 asks walked (ask 27 SKIP, L1), D4 and D5 re-walked PASS; the operator's Artifacts verdict under D-54-1.
- [x] Deck, video and sign-in details in hand together (this kit; the message file carries the sign-in lines).

## The checks

1. [M] [x] Real-browser smoke from outside on the deployed build: GREEN.
2. [M] [x] Secret scan green (gitleaks v8.24.3, the fork's own job). Free round: no transfer set to stage.
3. [M] [x] Deck machine checks GREEN. [CARD] [ ] the deck (card D-54-2 below).
3. note: card D-54-2 answered by the operator: deck approved as is.
4. [M] [x] Video machine checks GREEN on the re-voiced encode. [CARD] [ ] the video (card D-54-3 below): re-voiced after operator review, awaiting the operator.
5. [M] [ ] RED: CI's suite job is cancelled at its 40-minute limit, so no CI count agrees with the clean clone's 9,174 passed, 1 skipped at 34a30b7.
6. [x] Invoice: none. CON-54 carries Free (students offer, free pass 2 of 3).
7. [M] [x] Message lints GREEN with the one disclosed exception (the private link is the host's own address, as in Pass 1). Attach on THE message: the deck PDF, the video, both diagram HTML pages.
8. [CARD] [ ] A person reads the assembled message end to end (in the send card D-54-4).

Also open before the send (Step 0 row A10): the Pass 2 draft pull request on the customer's repository does not exist yet, and the message says this round reaches the repository as a second pull request on top of 19.

## The cards (Before delivery sitting; not asked by this session, which has no way to put a question to the operator)

```
CARD       D-54-2   Deck   holds: the send card
Context    The round-two deck, 24 pages, 4 reviewer pages after one divider.
Question   Does the deck go as it is?
Options    A (recommended) Looks right - it is attached to the delivery message as is
           B Change - say what; the PDF is re-exported from its source and re-linted
           C Hold - nothing is sent
Evidence   PDF 3,558,878 bytes, 24 pages, request quoted verbatim on page 2, table on page 3
           Machine checks green (CON-54-checks.md item 3); no count from testing, no names
           Deferred items on page 18: donut and treemap, Milo on Investing/Earnings, Read Desk, grid tab, save line
           Judgement to confirm: those deferrals are the operator's call, not yet agreed with the customer (Step 0)
           Reviewer D names the memory growth at rest (O1) and the CI timeout in plain sentences
Record     .factory/delivery/CON-54-optic-pass2-delivery-deck.pdf; source Conjure/customers/optic/pass-2/deck-source/deck.html
If nothing is answered:  the work waits at the gate
```

```
CARD       D-54-3   Video   holds: the send card
Status     Re-voiced after operator review, awaiting the operator (take one rejected on the voice track: S&P read as letters, the brand, one sentence shape)
Context    The round-two walkthrough, recorded live on the private test site at build 7689d8061f5e; the picture as shot, the voice track re-made from the operator's revised lines.
Question   Does the re-voiced video go as it is?
Options    A (recommended) Looks right - attached as is
           B Change - say which beat; that beat is re-recorded and the video re-assembled
           C Hold - nothing is sent
Evidence   ffprobe: 15,615,166 bytes, 218.4 s, h264 443,922 b/s, aac 119,478 b/s, 1280 x 720
           12 beats: diagram, journey, workflows, six features, Milo, sources and insiders, today's lines, Financials, Desk, workspace, owner, close
           Metrics figures and session addresses blurred in the page; the model-named tab hidden
           Spoken text grep: Alexander, Yazji, S&P, conjure.work, both dashes all zero; picture unchanged (beat 3 held 1.1 s)
           Beat 4 says deep research, passkeys and alerts work without showing them on camera
           One demo layout saved on camera and deleted afterwards; nothing left standing
Record     .factory/delivery/CON-54-optic-pass2-delivery-narration.md and .srt
If nothing is answered:  the work waits at the gate
```

```
CARD       D-54-4   Send   holds: the delivery message, move to Delivered, the manifest comment
Context    The round-two delivery message with four attachments; Free, so no invoice.
Question   Send the delivery message?
Options    A (recommended once item 5 and A10 are settled) Send - posted with --notify yes; the customer is emailed and the review window starts
           B Hold - nothing is sent
Evidence   [M] checks: 6 of 7 green; item 5 RED (CI suite timeout), item 7 carries the host-address exception
           Deployed build 7689d8061f5e = code 34a30b7 = the commit the gauntlet tested
           Invoice: none, Free
           Placeholder search empty
           Message Conjure/handoffs/CON-54-delivery-message.txt; attachments 3.6 MB, 15.6 MB (re-voiced), 96 KB, 76 KB
Record     CON-54-checks.md, CON-54-package-manifest.md
If nothing is answered:  the work waits at the gate
```

## Send (not done; the operator's explicit yes in that session first)

- [ ] `scripts/ops-write.sh post-thread-message 69988272-31ff-416d-9687-f21e101ab3fa --file /Users/sid/Code/claude_work/Conjure/handoffs/CON-54-delivery-message.txt --attach /Users/sid/Code/claude_work/optic-wt-delivery-pass-2/.factory/delivery/CON-54-optic-pass2-delivery-deck.pdf --attach /Users/sid/Code/claude_work/optic-wt-delivery-pass-2/.factory/delivery/CON-54-optic-pass2-delivery-video.mp4 --attach /Users/sid/Code/claude_work/optic-wt-delivery-pass-2/.factory/delivery/CON-54-optic-architecture.html --attach /Users/sid/Code/claude_work/optic-wt-delivery-pass-2/.factory/delivery/CON-54-optic-workflow.html --notify yes --decision D-54-4`, then read the thread back.
- [ ] `scripts/ops-write.sh move-pass CON-54 Delivered --decision D-54-4`.
- [ ] `scripts/ops-write.sh comment CON-54 --file /Users/sid/Code/claude_work/optic-wt-delivery-pass-2/.factory/delivery/CON-54-package-manifest.md --decision DD-16`.
- [ ] The send time noted in the manifest (starts the five-business-day review window).
- [ ] `scripts/ops-write.sh sync --notify yes --decision DD-15`.
- [ ] `~/.conjure/optic-eval.key` deleted once the artifacts are accepted.
