# Compatibility and evidence

Public prerelease: v0.2.0, 2026-11-06. It is not an accepted catalog entry.

## Supported boundary

Target local macOS/Linux Hermes Desktop with in-process plugins and Python 3.11+. Storage ownership uses POSIX `flock`; Windows, remote gateways, isolated plugin processes, and native CLI/messaging observation are not supported.

Exercised Hermes source: `b200f5bc60e31588ba2cb60e288029c4a54ba5fa`. A minimum **released** Hermes version has not been established. The plugin uses public observer hooks, plugin storage, session context, message injection, and `host.openSession`. The legacy launcher still uses the public lifecycle service.

## Checked

- Actual ordinary and nested `delegate_task` execution with a scripted loopback model: three native workers, four failed tool calls, and four paired human-input requests.
- The installed development plugin records one related-failure group, four resolved waits, and three returned worker rows. Native observation creates no legacy execution reservations.
- Fault tests cover identity de-duplication, missing/oversized evidence, root isolation, concurrent sends, bounds, migration rollback, v1 backup/restore, stale actions, lost execution ownership, interrupted sends, and stop/reset/delete behavior.
- Real FastAPI routes validate parent/revision/nonce and reject extra profile fields. HTTP queues intent without invoking a worker or injector.
- Hermes's upstream injection contracts cover busy/idle routing and its distinct CLI/TUI/gateway slots. Watchdog also refuses to dispatch persisted Desktop briefs through classic CLI, whose host branch ignores session keys.
- The browser SDK fixture renders the actual Desktop module with the real local API. Its header labels seeded data. This checks page behavior, not native Desktop integration.
- A 600-call local WAL SQLite timing run with two workers measured p95 below 0.2 ms for both healthy and matching-error events. This is not a saturated-host latency guarantee or a model benchmark.

Development reports remain local artifacts. Do not reinterpret scripted requests as measured live-provider usefulness, token savings, user attention saved, or delivered conversation replies.

## Migration and rollback

Schema v2 adds native roots, runs, compact event identities, bounded evidence, incidents, members, action identities, and recovery outbox tables. The v1 `sessions`, `tasks`, `attempts`, and `events` tables retain their meaning and data. Native rows never release legacy reservations.

Migration runs in one explicit SQLite transaction. Tests exercise an invalid migration and prove the version and preceding DDL roll back. A disposable v1 database is backed up, migrated without changing its task snapshot, and restored as v1.

Before upgrading a real profile, stop its Hermes host and back up the entire `plugin-data/hermes-watchdog` directory, including any SQLite sidecar files. Restore that backup together with the v0.1 plugin to roll back. **Do not run v0.1 against a v2 database**, and do not clear unresolved rows to regain admission capacity.

## Remaining release gates

The native UI driver was retried and again returned `runtime_open_timeout` (timed out waiting for an Orca desktop window). No native-window success is claimed.

- Arthur tests the candidate in an actual clean-profile Desktop window: normal delegation, input waits, returned work, recovery delivery while the parent is busy/idle, and profile switching.
- Establish a released Hermes version floor, then declare it in the final manifest.
- Run the paired comparison against real Hermes alone with the same host/model settings. Predeclare call, iteration, timeout, and operator spend ceilings before any live-provider trial. The planned 36 matched trials are still outstanding; unit tests are not a substitute.
- Record a genuine under-90-second demo. Label controlled faults and time cuts, and show the actual recovery outcome.
- Submit the catalog PR pinned to the reviewed public revision. X posting and form submission are separate actions; publishing a prerelease does not complete the competition entry.
