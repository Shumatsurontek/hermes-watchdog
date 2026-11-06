# Changelog

## Unreleased — typed conversation view

- Group native workers by conversation, with task-title excerpts and directly accessible results.
- Put the next action first; collapse secondary incidents, IDs and evidence. Use real Hermes theme tokens.
- Keep returned work with observed errors visibly distinct from verified success.
- Generate strict TypeScript types and runtime validators from bounded Python response models.
- Add atomic schema-v3 migration; retain existing observations, ownership and outbox semantics.
- Add a real release-readiness review prompt, migration and frontend build instructions.

## 0.2.0 — preview

Normal Desktop delegates now appear automatically in a recovery inbox. Related failures are grouped within their root conversation; paired human-input waits and returned workers remain visible. A user can open the originating conversation and send one durable recovery brief without starting a replacement worker.

- Add metadata-only native evidence, restart uncertainty, and additive schema v2 migration.
- Add parent/revision/idempotency validation, bounded delivery attempts, and explicit ambiguous acceptance.
- Withdraw pending requests on observed stop, deletion, or reset; preserve them on tab closure.
- Keep v0.1 launcher behavior and execution reservations separate; make search setup optional.
- Keep the existing banner. No connector breaker, automatic replay, or always-on judge added.

Native Desktop/live-provider acceptance and the competition demo remain pending. This is a prerelease, not a claim of completed native acceptance.

## 0.1.0 — preview

- Explicitly launched search workers with a durable task ledger and bounded monitoring.
- Deadline and user-requested cancellation through the owning Hermes parent context.
- Conversation-scoped status, notification acceptance tracking, and slash controls.
- Native Desktop task page with evidence, outcomes, and unavailable retries shown explicitly.
- Optional bounded progress judge, disabled by default.
- Marketplace banner, usage examples, and an opt-in profile setup helper.

Verified with deterministic plugin/API tests and real Hermes orchestration against a scripted loopback model. Native Desktop end-to-end acceptance, live-provider behavior, and the minimum released Hermes version remain unverified. This is a prerelease, not a stable release or marketplace acceptance.
