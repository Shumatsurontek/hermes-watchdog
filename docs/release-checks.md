# Local acceptance and submission

## Native acceptance sequence

Use a disposable Desktop profile with the same Hermes revision as the test binary. Enable the agent plugin, its Desktop contribution, notification permission, and the required parent toolsets. Keep the judge off for the first run.

1. Start a supervised research task. Confirm the parent replies before the task finishes and another chat message works while it runs.
2. Inspect its task row. Confirm child observations and final result appear, and the completion returns to the exact originating conversation.
3. Repeat while that conversation is busy. Confirm the notification queues there, without going to another active tab.
4. Start a slow task with a short deadline. Confirm one cancellation request, then either an authoritative terminal result or an unresolved state that retains its slot.
5. Close and reopen the tab. Confirm this alone never marks its task deleted. Explicitly delete another parent and verify cancellation is requested and further notices are suppressed.
6. Disable notification permission. Confirm false acceptance is attempted at most three times, then shown as failed, with the result still available.
7. Switch profiles and gateway routes while the activity page is loading. Confirm old data clears and stale actions cannot mutate the newly selected profile.
8. Restart with an active task. Confirm history survives, control is unavailable, and no replacement worker launches.

Do not use the preview harness or manually edited state as evidence that native recovery works.

## Demo storyboard — under 90 seconds

The intended flagship is the [native shared-failure scenario](native-integration.md). It is a proposed integration and must be implemented and tested before recording it. The [customer-briefing scenario](use-case.md) remains a smoke test for the current build, with a launch prompt and detailed 85-second storyboard. Neither document is evidence of a recorded live-provider run.

- 0–12s: Ask Hermes to start supervised research and show its immediate reply.
- 12–25s: Ask a separate question while the task runs; open Watchdog to show the live worker.
- 25–50s: Show an actual slow/failing worker, the observed evidence, and cancellation being requested. A visibly labelled short demo deadline is fine.
- 50–70s: Show the real terminal or unresolved outcome and the originating chat notification. Explain that uncertain work cannot be retried.
- 70–85s: Open the retained result/action history and show how to install the plugin.

Keep real wall-clock waits or disclose any time compression. Do not claim a cancellation request killed a tool, a returned answer was verified, or notification acceptance guarantees delivery.

## Catalog preparation

The runtime payload consists of `plugin.yaml`, `__init__.py`, `watchdog/`, `dashboard/`, `desktop/`, `assets/`, the README, license, and public docs. `scripts/stage.py` creates an explicit allowlist copy and file hashes; tests, private plans, caches, and development probes stay outside it.

`assets/catalog-banner.png` is the 2:1 promotional image. The catalog entry's `image` field must use its public GitHub raw URL pinned to the same commit as the code. Do not put this generated artwork in `screenshots`; that gallery is for genuine product captures. The current `docs/preview.jpg` is visibly labelled as a fixture-based browser harness and does not demonstrate native acceptance. [Artwork prompt](artwork-prompt.md) records the generation method and source inspiration.

Before publication, decide the repository/license, establish a released Hermes version floor, and run `hermes plugins validate <staged-directory> --install-deps`. Inspect warnings. Commit only after local acceptance and explicit approval. The catalog entry must pin the exact public repository commit with a full 40-character SHA and quote the plugin version.

The hackathon announcement supplied for this project requires the catalog PR, a working demo posted on X tagging `@NousResearch`, and both links in the submission form. None of those external actions has been performed.
