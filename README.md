# Hermes Watchdog

![Watchdog for Hermes: an engraved guardian dog watching three task signals](assets/catalog-banner.png)

**Keep the useful work. Resolve the blocker.**

Watchdog gives normal Hermes delegates a recovery inbox. It groups matching failures across workers, tracks requests waiting for a person, and keeps returned work visible. Send one recovery brief to the originating conversation so Hermes can inspect what happened before continuing.

**v0.2.0 prerelease.** Tested against Hermes source `b200f5bc60e31588ba2cb60e288029c4a54ba5fa`; native Desktop acceptance and a live-provider comparison remain pending. [Evidence and compatibility](docs/compatibility.md).

## Local development candidate

The working tree now includes a quieter conversation view: task names, returned work, a focused recovery action, and collapsed technical evidence. The frontend is TypeScript strict; Python response schemas generate its types and runtime validators. This is not yet in the published v0.2.0 archive. See [typed UI and migration notes](docs/typed-ui.md).

## A concrete use case

Use Hermes to audit this repository before release: tests/build, recovery correctness, and package/rollback, in parallel. The output is a release decision supported by evidence, even if one worker is blocked. [Copy the concrete prompt](docs/release-readiness-prompt.txt) and follow the [real-use-case demo](docs/release-readiness.md).

If two workers encounter matching tool errors while another returns useful work, Watchdog groups those failures and keeps the result visible alongside any separate human-input request. In the development UI, choose **Ask Hermes to recover**. The brief identifies affected and returned workers, asks Hermes to inspect current state and partial effects, and preserves its normal approvals.

Watchdog does not diagnose expired credentials from a generic error or replay failed writes. Hermes already owns connector retries, circuit breakers, delegation, and completion delivery. [Detailed scenario and demo script](docs/native-integration.md).

## What ships in v0.2.0

- Automatic observation of ordinary Desktop `delegate_task` workers, including nested ancestry. No special launch prompt required.
- **Needs you**, **Related failures**, **Returned results**, and **All workers** views.
- Three matching failed calls across at least two workers within 120 seconds form a related-failure group, scoped to one root conversation. Matching is evidence, not proof of a shared cause.
- Paired human-input request IDs: an unrelated tool event cannot clear an approval wait.
- **Open conversation** uses the public Desktop SDK and the selected profile.
- **Send recovery brief** persists a scoped, revision-checked, idempotent request. It does not create or restart workers.
- A single profile-owned outbox submits requests through Hermes. Accepted, failed, withdrawn, and unknown acceptance remain distinct.
- Default native observation makes **zero model calls**. Automatic native notices are opt-in; normal worker completion messages stay with Hermes.
- Existing `watchdog_start`, `watchdog_status`, `watchdog_control`, `/watchdog`, and legacy task history remain available. Legacy search-launcher retries remain disabled.

Acknowledge means you have seen the incident. Follow-up requested means a recovery request was queued. Neither means the dependency recovered or the task succeeded. There is no automatic “recovered” inference in this version.

## Install the prerelease

Use a disposable profile first. The supported target is local macOS/Linux Desktop, with in-process Python plugins and Python 3.11+. A minimum released Hermes version has not yet been established; do not infer support for every installed Hermes release.

Install the public source at the release tag:

```sh
hermes plugins install https://github.com/Shumatsurontek/hermes-watchdog --ref v0.2.0
python3 "${HERMES_HOME:-$HOME/.hermes}/plugins/hermes-watchdog/scripts/configure.py"
```

Use the exact commit from the release notes instead of the tag to pin the source immutably. For an existing installation, back up the plugin and its data before upgrading; stop its host before migrating the database. The runtime-only release archive avoids development-probe warnings in a whole-tree scan.

To build a **new test profile** from this checkout:

```sh
python3 scripts/stage.py --output /tmp/watchdog-v02/hermes-watchdog
mkdir -p /tmp/watchdog-test-profile/plugins
cp -R /tmp/watchdog-v02/hermes-watchdog /tmp/watchdog-test-profile/plugins/
HERMES_HOME=/tmp/watchdog-test-profile python3 /tmp/watchdog-test-profile/plugins/hermes-watchdog/scripts/configure.py
```

Start Hermes Desktop with that test profile, enable **Watchdog** in **Capabilities → Plugins**, and begin a new conversation. The agent plugin and Desktop contribution have separate toggles. Quit the old host before replacing its plugin: there is one runtime owner per profile.

The setup helper enables the plugin, its status tools, and permission to inject recovery briefs. It preserves existing toolsets and provider settings. Native observation does **not** add `search`; use `--legacy-launcher` if you also want the optional explicit search worker.

The [v0.2.0 release](https://github.com/Shumatsurontek/hermes-watchdog/releases/tag/v0.2.0) includes the runtime archive, its file manifest, and checksums. A bare catalog install remains unavailable until catalog acceptance.

### Configuration

Merge these settings into the existing profile; preserve other enabled plugins:

```yaml
plugins:
  enabled:
    - hermes-watchdog
  isolation: in_process
  entries:
    hermes-watchdog:
      allow_gateway_injection: true
      settings:
        observe_native: true
        native_notifications: false
        judge_enabled: false
```

`observe_native` controls new native observation. `native_notifications` opts into incident opening and human-wait resolution notices. Recovery briefs are explicit user actions and require `allow_gateway_injection`. The legacy `enabled`, `deadline_seconds`, `preset`, and `retry_mode` settings retain their existing meanings.

[Usage examples](docs/examples.md) include normal delegation, approval waits, incident review, and the legacy launcher.

## Resource limits

| Resource | Bound |
| --- | --- |
| Tracked native execution | 64 active or ownership-unknown workers per profile; does not limit Hermes execution |
| Native history | 1,000 workers, 1,000 incidents, 256 root conversations |
| Open attention | 32 items; overflow explicitly degrades observation |
| Evidence | Latest 64 metadata events per worker; total and retained-from sequence shown |
| De-duplication | 4,096 compact event identities per worker; overflow is an explicit evidence gap |
| Error matching input | 65,536 UTF-8 bytes; normalized events at most 1,024 bytes |
| Recovery brief | 4,096 bytes; selected worker count is disclosed |
| Outbox | 32 pending/in-flight/ambiguous messages; three explicit nonacceptance attempts |
| Delivery | One host call in flight, one row per five-second tick, one pump per profile |
| Actions | 2,000 retained idempotency records |
| Desktop | 50 list rows per page; one read and one action in flight |
| Retention | Explicit pruning after seven days; unresolved work and ambiguous sends retained |

A blocked host delivery cannot create additional delivery threads. Unload waits up to two seconds; a still-running call retains the owner lease and store until process exit. A send already entered cannot be recalled by deleting a conversation. Queued sends are withdrawn on deletion, reset, or an observed interrupted parent turn; closing a tab alone does not withdraw them.

A restart marks unfinished native execution **unknown** and interrupted sends **unknown**, without replaying them. No lifecycle handles are fabricated. The legacy launcher's three execution reservations remain separate and unchanged.

## Data and trust

Profile-local state lives in `plugin-data/hermes-watchdog/data.db`, outside the installation directory. Schema v2 adds native tables without changing the v1 task tables. Back up the database with the host stopped before upgrading; v0.1 cannot open a v2 database. [Migration and rollback](docs/compatibility.md).

Native records store session relationships, tool names, status metadata and error hashes. The local schema-v3 candidate also stores a bounded first-line task-title excerpt, with common secret shapes filtered; arbitrary task prose can still be sensitive. It does not store full goals, commands, arguments, worker results or raw error text. See [title retention and migration](docs/typed-ui.md). Open the native conversation to inspect source evidence. Worker “returned” means a reported agent outcome, not verified correctness or proof every underlying tool thread stopped.

Legacy records retain task briefs, results, and private lifecycle capabilities as before; APIs omit those capabilities. No external telemetry, core patches, automatic executor, or connector probe is included. A requested recovery review invokes the normal Hermes model and incurs normal usage.

## Development and verification

```sh
python3 scripts/test.py --report /tmp/watchdog-tests.json
node --input-type=module --check < desktop/plugin.js
python3 scripts/measure_native.py --output /tmp/watchdog-timing.json
python3 scripts/stage.py --output /tmp/watchdog-package/hermes-watchdog
hermes plugins validate /tmp/watchdog-package/hermes-watchdog --install-deps
```

The dependency-free runner skips API tests when FastAPI/httpx are absent. `scripts/host_tests.py` runs those tests plus Hermes's upstream injection contracts using its managed dependencies. `scripts/probe_native.py --hermes-source /path/to/hermes-agent --output /tmp/native.json` runs actual ordinary and nested delegates, failed tools, and paired human waits against a scripted loopback model; set a disposable `/tmp` `HERMES_HOME` first.

The older `probe_plugin.py` and `probe_runtime.py` cover the preserved launcher. Development probes intentionally import host internals and are excluded from the runtime release. Validate the staged runtime; scanning the whole source tree will report those test imports.

The browser harness renders the actual Desktop module against an SDK fixture and a real API. It is labelled as a fixture, not a native Desktop run. [Acceptance checks](docs/release-checks.md) distinguish checked behavior from the remaining native/live-provider and competition gates.
