# Hermes Watchdog

![Watchdog for Hermes: an engraved guardian dog watching three task signals](assets/catalog-banner.png)

Keep background work accountable while the conversation stays available.

Watchdog launches supervised Hermes workers, records their progress and outcomes, requests cancellation at a deadline, and reports back to the originating conversation. Its Desktop page separates **execution**, **supervision**, and **notification acceptance** so a stuck worker never becomes a fictitious success.

**v0.1.0 preview.** Tested against Hermes source revision `b200f5bc60e31588ba2cb60e288029c4a54ba5fa`. Native Desktop acceptance, a live-provider smoke test, and the minimum released Hermes version remain unverified. See [compatibility](docs/compatibility.md) and [release downloads](https://github.com/Shumatsurontek/hermes-watchdog/releases).

## What it does

- `watchdog_start` launches a leaf worker and returns immediately after host construction.
- `watchdog_status` reads this conversation's tasks, observations, and unverified results.
- `watchdog_control` queues cancellation. The monitor calls Hermes from the owning parent context.
- `/watchdog status`, `inspect <id>`, and `cancel <id>` provide conversation-local controls.
- A Desktop activity page shows outcomes, evidence, pending controls, and notification failures.
- An optional judge can recommend attention or one change of approach. It is off by default.

Watchdog supervises only workers launched through its own tool. Native `delegate_task` keeps its existing behavior.

**Retries are disabled in this version**, including human-requested retries. The current host does not attest the effective child tool surface, and some terminal failures can hide a pending tool thread. A `search` toolset label alone cannot prove repeat safety because Hermes may inherit MCP tools.

## Try it

> Use Watchdog to research the official Hermes plugin-submission requirements in the background. Set a 120-second cancellation-request deadline, ask for source URLs, and return the task ID immediately.

Continue chatting, then open **Watchdog** in the sidebar or use `/watchdog status`. Read [four usage examples](docs/examples.md): plugin research, release preparation, cancellation, and a short-deadline test.

## Current smoke test: background research

You're preparing a Shopify support-team briefing. Ask Watchdog to research three public topics in the background: Intercom Fin pricing, Zendesk AI-agent pricing, and Gorgias AI Agent's documented Shopify actions. While those workers run, ask Hermes to draft your discovery questions.

If two workers return and the third misses its deadline, you can use the returned research and identify the missing piece. Watchdog requests cancellation of the overdue worker, preserves its evidence, and attempts to notify the same conversation. If execution remains uncertain, the task stays unresolved and keeps its capacity reservation. There is no automatic replacement worker.

This exercises the current explicit-launch runtime, ledger, and Desktop controls. Hermes itself already supports background delegation; this example is a functional smoke test, not the intended hackathon flagship.

This is a proposed workflow, not a recorded live-provider run. See the [ready-to-paste prompt](docs/customer-briefing-prompt.txt) and [worked scenario with an 85-second demo script](docs/use-case.md).

## Install the preview

Use a disposable test profile first. No model credentials belong in this plugin: workers and the optional judge use Hermes's existing provider route and authentication.

The supported host is a **local macOS/Linux Desktop gateway with in-process plugins**. An isolated plugin process, remote gateway, CLI conversation, or messaging platform is not currently supported. Python 3.11+ is required. The setup helper refuses an incompatible isolation setting without changing it.

Quit Hermes Desktop before installation and setup so its gateway does not compete for the profile's Watchdog ownership lock. For the source repository:

```sh
hermes plugins install https://github.com/Shumatsurontek/hermes-watchdog
python3 "${HERMES_HOME:-$HOME/.hermes}/plugins/hermes-watchdog/scripts/configure.py"
```

For a reproducible install, add `--ref` followed by the exact 40-character commit from the release notes to the install command. A bare `hermes-watchdog` install is unavailable until the plugin is accepted into the catalog. If a manually installed copy already exists, back it up before following the host's reinstall flow.

The source repository includes development probes that intentionally import Hermes internals; validating the entire source tree reports those imports. They are not loaded by the plugin. The release archive contains only the runtime payload and public documentation and passes validation without those warnings. To use the archive, verify its checksum, extract it, copy its `hermes-watchdog` folder into your test profile's `plugins` directory, and run the included `scripts/configure.py` with that profile selected.

The helper enables the Python plugin, permits notifications to the originating conversation, and adds `watchdog` and `search` to the parent tool selection while preserving existing toolsets. It uses `HERMES_HOME`, or `~/.hermes` by default; `--profile-home /path/to/profile` selects another profile. It does not change the provider, credentials, or plugin isolation mode.

Reopen Hermes Desktop, enable its Desktop contribution in **Capabilities → Plugins**, and start a new conversation. The Python plugin and Desktop contribution have separate toggles. Hermes may expose the tools through `tool_search` / `tool_call` rather than listing each tool eagerly.

### Manual configuration

If configuring manually, merge this entry into the profile's existing configuration and include both `search` and `watchdog` in its parent CLI/Desktop toolsets:

```yaml
plugins:
  enabled:
    - hermes-watchdog
  entries:
    hermes-watchdog:
      allow_gateway_injection: true
      settings:
        enabled: true
        preset: search
        deadline_seconds: 900
        retry_mode: manual
        judge_enabled: false
```

Do not replace an existing `plugins.enabled` list; add this entry. Notification permission uses the host's existing `allow_gateway_injection` control. Without it, outcomes remain in the ledger and the activity page reports notification failure.

In a Desktop conversation:

> Use Watchdog to research the Hermes plugin submission requirements in the background. Set a 120-second cancellation-request deadline and return immediately.

Continue chatting. Open **Watchdog** in the sidebar to inspect the worker. Its result also remains available through `watchdog_status` if the chat notification cannot be accepted.

## Guarantees and limits

| Contract | Bound / behavior |
| --- | --- |
| Active attempts | 3 per profile, including unresolved execution |
| Conversation admission | 10 tasks while its history is retained |
| Retry | Disabled; no automatic replacement workers |
| Deadline | 900 seconds by default; configurable from 10 to 1,800 seconds |
| Polling | Every 5 seconds, at most 370 ticks per attempt |
| Cancellation | One request; after 30 seconds without confirmation, record unresolved execution |
| Quiet / repeated errors | 120 seconds without observed progress, or 3 distinct failing calls with the same fingerprint, produces suspicion |
| Optional judge | 2 calls per task; 1 in flight per profile; 3-second request timeout; 256 output tokens; 4,096-byte evidence input; 1 steer |
| Notifications | At most 3 acceptance attempts per task; nearby results can share one notice |
| Ledger | 1,000 tasks, 256 retained conversations, 128 action events per task |
| Observations | Latest 64 plus total count and retained-from sequence |
| Result | 128,000 UTF-8 bytes; an excerpt is explicitly labelled |
| UI pages | At most 50 tasks; refreshes do not wake the model |

Healthy supervision makes no judge calls. Worker cost, iteration limits, model temperature, and hard execution timeouts remain Hermes-owned: the inspected lifecycle API does not accept per-child overrides for those budgets. `model=None` / `provider=None` deliberately select the host's routing rules.

A deadline is a **request to cancel**, not a hard kill. Even a `cancelled` or `interrupted` agent loop retains its reservation: the public result does not attest that every underlying tool thread has stopped. A successful host result means the worker returned successfully, not that its deliverable was independently verified. Notification `accepted` means Hermes accepted the injection, not that a user received a final answer.

After restart or lost ownership, history survives but live control cannot be reconstructed from a saved handle. Watchdog retains uncertain reservations and does not start replacement work. Three unresolved attempts will therefore block further admission. Use the host's controls to inspect and stop workers; do not clear the ledger merely to bypass that bound.

## Data and permissions

State lives in the active profile's `plugin-data/hermes-watchdog/data.db`, outside the install directory. The directory is private and the database has owner-only permissions. It contains task briefs, results, event history, and private lifecycle capabilities. API and model snapshots omit those capabilities; tool arguments are fingerprinted rather than stored. Result text is rendered as text and remains untrusted data.

No analytics, external telemetry, self-updater, core patches, model credential reads, or direct provider SDK calls are included. Network activity consists of normal host-owned worker calls, optional host-owned judge calls, and host message injection.

`/watchdog prune` removes settled records older than seven days, retaining unresolved work and counters for conversations that still have retained tasks. Do not remove the state directory while workers or plugin monitors may still be running.

## Development and verification

```sh
python3 scripts/test.py --report /tmp/watchdog-tests.json
node --input-type=module --check < desktop/plugin.js
python3 scripts/stage.py --output /tmp/hermes-watchdog-package
hermes plugins validate /tmp/hermes-watchdog-package --install-deps
```

The dependency-free runner skips HTTP tests if FastAPI/httpx are unavailable. Run those and the upstream host-injection contracts using Hermes's managed Python and dependencies:

```sh
HERMES_HOME=/tmp/watchdog-test-profile python scripts/host_tests.py \
  --hermes-source /path/to/hermes-agent \
  --test-deps /path/to/test-only-pytest-install \
  --report /tmp/watchdog-host-tests.xml
```

`scripts/probe_runtime.py` exercises real lifecycle launch/context retention, steering, cancellation, and result access against a scripted loopback model. `scripts/probe_plugin.py` loads the actual plugin and has a real Hermes parent invoke its tool through normal dispatch. Both accept `--hermes-source` and `--output`. Use a disposable `/tmp` `HERMES_HOME`; these probes do not use account credentials and are not live-model benchmarks.

The browser harness under `tests/ui/` renders the actual Desktop module with an SDK fixture. It verifies rendering and controls, not native Desktop installation. [Release checks and demo storyboard](docs/release-checks.md) describe the remaining acceptance work.

## Planned native integration

Hermes already provides asynchronous delegation, stalled-worker detection, and tool-loop guardrails. A proposed next direction is to observe normal native delegates and correlate shared connection failures across workers, without requiring a Watchdog-specific launch step. **Native observation, incident grouping, and connection blocking are not implemented.** See the [design proposal](docs/native-integration.md).
