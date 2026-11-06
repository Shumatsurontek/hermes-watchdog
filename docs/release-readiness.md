# A release decision that survives a blocked worker

The concrete task is to decide whether this checkout of Watchdog is ready to release. The output is a reviewable decision with test evidence, recovery risks, packaging checks and explicit unknowns. This is useful even when every worker succeeds.

Use [the ready-to-paste prompt](release-readiness-prompt.txt) in a new Hermes Desktop conversation opened on this repository. It uses ordinary native delegates: tests/build, recovery audit, and package/rollback. It requests bounded tool use and read-only review; Hermes still owns actual iteration, time and provider budgets. Watchdog does not enforce the prompt's tool-call limit.

Open Watchdog while the workers run. The first lines of their goals become short local task titles. The shared `Release readiness · …` prefix gives this conversation its display heading. No special tool is needed to opt into observation. Arbitrary titles work too; conversations without a shared prefix use a neutral heading.

If a worker encounters a real missing dependency, access problem or human-input request, keep the other results. Watchdog shows human waits and reported failures. Matching tool failures are grouped only after at least three identical tool/error fingerprints across two workers in the same conversation within two minutes. A single ordinary tool error does not automatically become a shared incident. A returned worker with errors in the retained observation window is shown as **Returned with errors**.

For an incident, **Ask Hermes to recover** queues one brief to the original conversation. Hermes inspects the transcripts and current state, preserves usable work, and determines the follow-up. If access or input is needed, resolve it through Hermes. The review must not rerun already-useful work without a reason. Watchdog cannot prove this behavior merely from message acceptance: inspect the resulting conversation and report.

If the run is healthy, do not manufacture a failure. The useful artifact is still the release decision. For a recovery demonstration, use an actual blocked task or label a deliberately controlled fault as such. The old missing-file exercise tests transport; it is not the main product story.

## A demo under 90 seconds

- Show the real release question and the three native workers. Cut waiting time transparently.
- Open Watchdog: task names, useful returned work, and the actual blocker if one occurred.
- Open an existing result, then request a scoped recovery review for the incident. Show the difference between a queued review and a received answer.
- End on the release decision, including the unresolved checks. Point out which completed analysis was retained.

Do not claim time, token savings, verified recovery, or an avoided duplicate operation unless the real run demonstrates it. A fixture screenshot is for UI testing, not evidence for the competition.
