# Typed conversation view — local candidate

The frontend source lives in `desktop/src/`. `desktop/plugin.js` is a generated ESM bundle with React and the public Hermes SDK external; Hermes users need no Node build step. Styles use Hermes' public `--foreground`, `--card`, `--border`, `--primary` and related tokens, with standalone fallbacks.

`watchdog/views.py` defines bounded Pydantic response models for the new work/history views and their actions. FastAPI validates responses. `scripts/export_contracts.py` exports their JSON schemas. `npm run contracts` generates TypeScript declarations and standalone AJV validators from those same schemas. Every frontend network response starts as `unknown` and must validate before the UI can act. TypeScript enables strict mode, unchecked-index checks and exact optional properties. `desktop/src/hermes-sdk.d.ts` is the narrow public SDK subset consumed by this plugin, checked against the tested Hermes source revision; it is not a vendored copy of Hermes internals. The preserved v0.2 native/tool APIs remain compatible; this work does not claim to statically type all pre-existing runtime code.

Build from the checkout:

```sh
npm ci --ignore-scripts
python3 scripts/export_contracts.py   # requires Pydantic 2 in this Python environment
npm run contracts
npm run build
```

Hermes-managed Python can run the export with `--hermes-source /path/to/hermes-agent`. Use a disposable `HERMES_HOME` for developer probes. `npm run build` runs the strict type check before bundling. Commit generated artifacts with their source when a release is approved. `scripts/stage.py` ships only the built desktop entry, not source schemas, tooling or node_modules.

The work endpoint reads at most ten conversations per page, fifty worker summaries and fifty incident summaries per conversation. Exact totals and pagination/omission messages disclose the rest. Evidence is fetched only when expanded (latest 64 events). Polling waits five seconds after completion; requests have a twelve-second SDK timeout and only one read plus one action can be in flight across page modes. A read uses a deferred SQLite snapshot, not an immediate write lock. Profile, connection, gateway epoch and unmount guards discard stale responses and invalidate actions. HTTP actions still use the existing parent/revision/idempotency checks and durable outbox.

Schema v3 additively stores a task-label excerpt and an excerpt flag on native runs. The title takes only the first line, at most 160 characters, from a bounded goal input; it never copies full worker results or summaries. Common credential shapes, URLs, addresses and invisible controls are removed. This filtering cannot guarantee that arbitrary task prose contains no sensitive information: titles are local task content in the existing protected profile database. They are displayed as text and never included in recovery instructions. Old runs keep blank titles, with a tool-based fallback in the UI. No transcript backfill occurs. Existing pruning rules apply.

Before replacing an installed v0.2 runtime, back up both plugin files and SQLite using the backup API. To roll back from schema v3 to v0.2, restore the matching pre-upgrade database as well as the plugin. v0.2 intentionally rejects newer schemas. Never overwrite the live DB or reload an active owner mid-task.

Browser checks use the compiled bundle and real FastAPI routes with a labelled SDK fixture. They verify navigation identities, scoped recovery, profile isolation, malformed responses, backend failure and narrow layout. They do not prove native Desktop navigation or provider recovery. Those still require a real Hermes session.
