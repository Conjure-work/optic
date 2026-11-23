# The suite on GitHub

`.github/workflows/tests.yml` runs the whole suite on every pull request and every push to `main` (and to the
`factory/**` branches a fork pull request is built from). Since 2026-11-23 it runs as parallel shards, because the one
job took about 33 minutes on a fast Mac and timed out at 40 on GitHub's shared macOS runner.

## How it is split

`tests/support/shards.py` assigns every test file to exactly one shard: the browser journeys (`tests/e2e`) are their
own shards, and the Python files are split into ranges by name, sized from measured durations. A new test file lands
in a shard by its name with no change to the workflow, and `tests/test_ci_shards.py` fails if any file is in no shard
or in two.

Each shard writes its own JUnit file and checks its own floor (the count it passed when the floors were last set).
The `count` job then adds the shards' JUnit files together and fails unless the total passed is at least the suite's
floor, `SUITE_FLOOR`, and nothing failed. The run's summary shows every shard's line and the total.

To change a floor: run the suite, read each shard's count from the run summary, and set `SHARD_FLOORS` in
`tests/support/shards.py`; `SUITE_FLOOR` in the workflow must equal their sum (a test checks it). Lowering a floor
needs a reason in the pull request.

## Two settings that are the repository owner's

Neither is needed for the suite to pass; both decide whether checks run on a pull request opened from a fork.

1. **Approving workflow runs from a fork.** GitHub holds the first workflow run of a pull request from an outside
   contributor until a maintainer approves it. On the pull request, press **Approve and run** under the held checks.
   To change the rule for every pull request: the repository's **Settings**, then **Actions**, then **General**, then
   under **Fork pull request workflows from outside collaborators** choose **Require approval for first-time
   contributors** (the default) or another option, and **Save**.
2. **Vercel and fork pull requests.** The Vercel check on a fork pull request reads "Authorization required to
   deploy", because Vercel will not build a fork's code into the team's project without a team member's say. On
   Vercel: the project's **Settings**, then the **Git Fork Protection** setting (under **Security** in the current
   dashboard; earlier dashboards listed it under **Git**) decides it; leaving it on
   keeps fork pull requests from deploying, and a team member can still authorize one deployment from the link in
   the check. The suite does not depend on Vercel.
