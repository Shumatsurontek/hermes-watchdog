# Compatibility and evidence

Implementation date: 2026-11-05. Version 0.1.0 is a preview, not an accepted marketplace entry.

## Supported boundary

The runtime targets local macOS/Linux Hermes Desktop, with Python plugins running in-process. It requires the public `PluginContext.subagent_lifecycle`, session context getter, plugin storage helpers, observer hooks, `inject_message`, and the native Desktop SDK. The per-profile owner lock currently uses POSIX `flock`; Windows is unsupported.

The inspected and exercised Hermes source is `b200f5bc60e31588ba2cb60e288029c4a54ba5fa`. A released `requires_hermes` version floor has **not** been established. It is deliberately absent from the development manifest rather than invented; establish it before submitting a catalog entry.

## Checked locally

- The actual plugin loaded from a disposable profile and registered its tools/hooks.
- A real `AIAgent` parent invoked `watchdog_start` through Hermes's normal deferred-tool bridge, then replied while its real child was still running.
- The plugin correlated the child's identity and recorded real observer events and success.
- A copied parent context retained lifecycle authority after the original scope ended; an unbound call returned `UNKNOWN`.
- A real lifecycle cancellation request was accepted and confirmed `CANCELLED` in the loopback fixture.
- The deterministic tests cover concurrent admission, restart ambiguity, cancellation races, lost context, notification ambiguity/exhaustion, profile/session isolation, waiting for human input, bounds, and judge budgets.
- The real FastAPI routes were tested with isolated databases, including stale revisions, foreign-session actions, capability redaction, idempotency, and rejected retry/extra fields.
- Hermes's own six injection tests passed, covering correct busy-session queues, idle-session dispatch, unknown sessions, and the separate CLI/TUI/gateway injection slots. These are host contract tests with fixtures, not a native Desktop end-to-end run.
- The actual Desktop ESM module was rendered in a browser with an SDK fixture and a real local ledger/API. Seeded-task rendering, detail selection, cancellation queueing, unavailable retry, empty/error states, and route-reset behavior were checked.
- The runtime-only staged payload passes the catalog validator. Development probes intentionally import host internals as test fixtures and are excluded from that payload.

Exact measurements and test reports are local development artifacts. The model endpoint in both runtime probes is scripted HTTP on loopback. It provides deterministic orchestration evidence, not claims about real model speed, task usefulness, or completion quality.

## Remaining stable-release gates

The packaged Desktop artifact was located, but the native UI driver returned `runtime_open_timeout` ("Timed out waiting for an Orca desktop window"). No native end-to-end success is claimed.

1. Install the staged payload in an actual clean-profile Desktop window at a known source/binary revision. Exercise busy and idle conversations, profile switching, tab closure, parent deletion, and notification refusal.
2. Run a live-provider success and failure scenario using host-owned credentials. Check host usage attribution and observed tool errors.
3. Verify the optional judge against a real host provider, including its timeout. It remains off by default.
4. Establish the minimum released Hermes version and declare it truthfully. Check the final public repository name and license before publication.
5. Record the real demo and submit a catalog PR pinned to the exact public source commit, with the catalog image pinned to that same commit. A GitHub prerelease alone does not constitute catalog acceptance or hackathon submission.

## Changes from the initial design

- No retry authorization or second-attempt path ships. The planned safe-surface gate could not be established from the public host contract; all retry requests return the reason.
- Three bounded per-attempt monitor threads retain independent execution contexts. A per-profile lock prevents competing owners. There is no global cron and no fabricated parent context.
- `ctx.get_config` takes a key such as `deadline_seconds`, already relative to the plugin's `settings` object; `settings.deadline_seconds` is rejected by this host. The loaded-plugin probe caught and corrected that assumption.
- `on_session_finalize` is observed but does not mark the conversation deleted: Desktop also emits it for disconnect/eviction.
- Notification retries are limited to explicit nonacceptance. Exceptions or restart during sending become `unknown`, with no automatic replay.
- The activity page and slash command accept cancellation; HTTP never receives or operates on lifecycle handles.

## Upstream capabilities that would unlock more

A public immutable attestation of the child's actual effective tools, explicit physical-execution settlement, portable reconnect/ownership, and per-child execution budgets would allow stronger recovery guarantees. Until then, Watchdog preserves uncertainty instead of guessing.
