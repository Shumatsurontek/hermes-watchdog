# Changelog

## 0.1.0 — preview

- Explicitly launched search workers with a durable task ledger and bounded monitoring.
- Deadline and user-requested cancellation through the owning Hermes parent context.
- Conversation-scoped status, notification acceptance tracking, and slash controls.
- Native Desktop task page with evidence, outcomes, and unavailable retries shown explicitly.
- Optional bounded progress judge, disabled by default.
- Marketplace banner, usage examples, and an opt-in profile setup helper.

Verified with deterministic plugin/API tests and real Hermes orchestration against a scripted loopback model. Native Desktop end-to-end acceptance, live-provider behavior, and the minimum released Hermes version remain unverified. This is a prerelease, not a stable release or marketplace acceptance.
