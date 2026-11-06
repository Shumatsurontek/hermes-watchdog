# Native recovery inbox

Implemented in the v0.2.0 prerelease. This replaces the earlier proposal for a plugin-owned connection breaker. Hermes already implements MCP circuit breaking; Watchdog does not block or retry connector calls.

## Release-preparation scenario

Ask normal Hermes:

> Prepare the next release of this repository. Delegate independent workers to inspect failed CI, review open release blockers, and draft a rollout checklist from local documentation. Keep the work read-only. Return useful partial results and identify anything requiring my decision.

Use a clearly labelled local tool fixture to produce the same controlled failure for the CI and blocker workers. Do not revoke real credentials or represent an injected fault as an external outage. Have the local-doc worker return normally.

Three distinct matching failed calls across two workers in the same root conversation create one **Related failures** item. Native tool access and the host's own retries remain unchanged. A separate **Returned results** row points to the useful worker transcript. Human-input requests appear in **Needs you** until their matching resolution or reported worker end.

Open the incident and select **Send recovery brief**. The original parent receives a bounded description of the incident and observed workers. It is told to inspect current external state, preserve returned work, check partial effects, and continue only within existing authorization. The user can also open the original conversation through the public SDK.

The visible benefit to evaluate is a single cross-worker investigation with useful partial work retained. No reduction in dependency calls or human decisions has yet been measured against a live Hermes baseline.

## Implementation

`NativeObserver` normalizes public hooks. `NativeLedger` stores independent execution rows, incident membership, bounded evidence, and action identities. `RecoveryOutbox` handles committed intent outside database transactions. The Desktop backend validates the parent and revision against stored ownership; client-supplied profile or route arguments cannot choose a delivery destination.

Error fingerprints match an exact observed tool name and bounded error text. They do not parse MCP names into connector identities. Classification remains **unclassified**. There is no adapter-specific auth diagnosis, health probe, automatic recovery claim, or worker restart.

An ambiguous send is not retried. A false acceptance may retry at most three times. Opening the profile in classic CLI cannot drain Desktop recovery messages into the REPL, because that host transport ignores explicit session keys.

DeepSeek's public superagent prototype informed the separation of execution, attention, and reply intent. It owns more of its executor than a Hermes observer plugin does; its restart behavior was not copied.

## Demo storyboard, 85 seconds

- 0–12: Show the ordinary release-preparation request and native delegates.
- 12–25: Show the labelled injected failure in two workers and a real result from the documentation worker.
- 25–43: Open Watchdog: one related group, its affected workers, and the returned result. Explain that the common cause is not proven.
- 43–60: Open the incident and send one recovery brief. Show its acceptance state and the actual originating conversation receiving the request.
- 60–78: Show Hermes inspecting current state and proposing the next action while preserving the useful result. Do not claim an unobserved recovery.
- 78–85: Show the repository and installation route after publication.

Record real native runtime state. Disclose time cuts and controlled faults. A seeded screenshot, an accepted injection, or a scripted model fixture is not proof of user-visible delivery or a completed real task.
