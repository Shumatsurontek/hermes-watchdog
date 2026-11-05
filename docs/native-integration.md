# Watchdog inside normal Hermes work

Status: proposed next direction. The current runtime still supervises only `watchdog_start` search workers. This document does not claim native task observation, shared incidents, or connection-level blocking have shipped.

## The product decision

Make Watchdog a shared-failure supervisor for the work Hermes already runs. The user should make an ordinary request and use ordinary Hermes delegation, tools, model routing, and approvals. They should not need a special launch command or another worker system.

Background research is a weak flagship. Hermes already provides asynchronous delegation and result delivery, stalled-worker detection, live list/steer/stop controls, persistent transcripts, and per-turn tool-loop guardrails. Repackaging those capabilities is insufficient differentiation. The useful part of the original Cortex design to pursue is correlating a shared dependency failure across several tasks and giving the user one actionable incident.

This is a focused product recommendation, not a claim that no other plugin offers supervision. Nerve and Operations already cover substantial adjacent territory.

## Concrete use case: prepare a release when GitHub authentication breaks

The user asks Hermes:

> Prepare the release brief for this repository: summarize merged PRs since the last release, investigate failing GitHub Actions checks, and identify open release blockers. Work on those independently. Draft a rollout checklist from the local release docs while they run. Do not publish, merge, or change anything remotely.

Hermes uses its normal delegation to create three workers. Each needs the same configured GitHub connection, but for a different operation: PR history, check results, and issue search. The parent can still work from local documentation.

During that run, the connection starts returning structured HTTP 401 authentication failures. A single worker can diagnose its own failed request; the cross-task problem is that several workers keep discovering the same broken dependency independently, potentially using different tools and arguments.

The target Watchdog behavior is:

1. Observe the normal `subagent_start`, `pre_tool_call`, and `post_tool_call` events. Join workers to their parent conversation using explicit Hermes identity fields.
2. Match supported, structured failures to one connection identity. After three matching authentication failures across at least two distinct workers within two minutes, record one shared incident.
3. Tell the originating conversation once: “The configured GitHub connection rejected authentication in three requests across two workers. PR research and CI investigation are affected. Local work can continue. Check or reconnect that connection.” Counts and affected tasks must come from evidence. HTTP 401 alone does not prove that a token expired.
4. While the incident is open, refuse further matching calls through the documented `pre_tool_call` block directive. Return a short incident ID and recovery instruction to each affected worker. Calls to files, terminal, or other connections continue normally. Do not claim that workers themselves are paused or that already-running requests stopped.
5. Show one incident in the native Watchdog page: connection, observed failure class, affected tasks, first/last occurrence, evidence counts, and suppressed-call count. Provide a route back to the originating conversation.
6. After the user fixes the connection, explicitly allow one known read-only probe. A successful authentication check reopens the connection for future calls. The parent decides what unfinished work to continue through native Hermes controls; Watchdog never replays writes or silently creates replacement workers.

The value is one repair decision for a shared blocker, plus continued progress on unaffected work. Do not advertise an exact token saving without measuring matched runs.

## What fully integrated means

| Surface | Contract |
| --- | --- |
| Task creation | Normal `delegate_task`; no requirement to call `watchdog_start` |
| Execution and model routing | Owned by Hermes, including its configured delegation backend |
| Observation | Public hooks with parent/child/session/turn/tool-call IDs; no transcript scraping |
| Dependency identification | A small supported adapter set mapping actual structured tool results to a configured connection; no guessing from arbitrary prose |
| Intervention | `pre_tool_call` refuses only future calls mapped to the same incident scope |
| Agent feedback | A bounded tool refusal explaining the incident and available recovery path |
| User feedback | One scoped incident update in the originating conversation and a native Desktop incident view |
| Recovery | Existing connection setup and native delegation controls; no new credential store |
| Persistence | Incident evidence survives restart; ambiguous delivery is not replayed blindly |
| Core compatibility | Do not replace core delegation, loop guards, provider retries, approvals, or terminal process ownership |

Observer visibility does not confer authority over native worker handles. The public lifecycle API controls children created through that API; do not fabricate capabilities for arbitrary `delegate_task` workers. Connection-call blocking uses a different public mechanism and does not require taking ownership of those workers.

Hermes hook callbacks are fail-open. This is an operational aid, not a security boundary or a guaranteed spending limit. CLI, Desktop, and messaging routing need separate acceptance evidence; a Python hook being callable on all surfaces does not prove notifications work on all of them.

## Narrow first implementation

Start with local Desktop, native delegates, and one configured GitHub MCP connection with a known structured authentication-error contract. Keep unsupported tool formats observable but ineligible for automatic blocking. Do not interpret a generic MCP `isError`, a shell command's prose output, or every HTTP 403 as a global authentication incident. A resource-specific permission failure must not block unrelated resources.

Use a per-profile connection scope with separate incident views and notices for each affected parent conversation. A shared failure must never expose another conversation's goal, results, or private task details. Never inspect or copy authentication tokens. If the adapter cannot establish a stable connection identity without credentials, do not group or block it automatically.

Proposed envelope before implementation:

- Zero model calls for matching, grouping, blocking, and rendering; deterministic structured evidence is enough for this first case.
- At most 64 tracked native workers, 32 open connection incidents, and 128 retained evidence entries per incident. Overflow produces a visible degraded state and disables new automatic decisions rather than silently dropping evidence.
- Three matching failures from at least two workers in a rolling 120-second window; exact repeated hook delivery never increments the counter twice.
- One initial parent incident notice, one recovery notice, and at most three explicit-nonacceptance attempts per notice. Ambiguous acceptance is recorded without replay.
- One read-only recovery probe in flight per incident, with a named adapter timeout of five seconds. No arbitrary tool replay or probe of a mutating operation.
- Persisted records retain at most seven days of settled evidence, with a 1,000-incident hard cap. Open incidents require explicit reconciliation after restart.
- Existing provider errors, retries, and call limits remain Hermes-owned. Do not layer another provider retry loop underneath them.

The probe requires an actual host-supported invocation path and permission contract. If that cannot be established, ship an explicit “allow next matching read-only call” gate driven by the parent instead; do not call private runtime internals.

## Demonstration and acceptance

Use a clearly labelled local MCP fixture that exposes the GitHub adapter's structured contract. Return successful data first, then deliberately return the same authentication failure to native workers. Do not revoke real credentials or pretend the fixture is an external outage.

The under-90-second story is: ordinary Hermes request; native workers start; controlled shared failure; one incident appears; a subsequent affected call is refused while local work continues; a successful permitted probe clears the incident. The native conversation and Desktop page must reflect real runtime events, not seeded ledger rows.

Before making an integration claim, verify:

- Normal `delegate_task` children appear without Watchdog-specific launch tools.
- Independent connections and profiles cannot contaminate each other's incidents.
- Different parent conversations get only their own affected-task details.
- Repeated event delivery, concurrent failures, and a late success cannot create contradictory incidents.
- Resource-specific access denials and unrecognized error formats do not open a shared circuit.
- The block directive prevents the matched tool handler from running, preserves normal approvals, and leaves unrelated calls available.
- Restart, a missing message route, and a full notification queue stay explicit.
- Recovery never replays a write and never assumes a returned worker can resume.

## Evidence checked in Hermes

- [Native delegation](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation): background execution, result delivery, live controls, heartbeat staleness, and transcript persistence.
- [Tool-loop guardrails](https://hermes-agent.nousresearch.com/docs/user-guide/configuration#tool-loop-guardrails): repeated failures and identical-result loops already have core handling.
- [Observer hooks](https://hermes-agent.nousresearch.com/docs/developer-guide/observer-hooks): identity fields, structured outcomes, the pre-tool block directive, and fail-open behavior.
- [Subagent lifecycle API](https://hermes-agent.nousresearch.com/docs/developer-guide/subagent-lifecycle-api): capability-bound ownership and restart limitations.

Local source inspected: `tools/delegate_tool.py`, `agent/tool_guardrails.py`, `agent/subagent_lifecycle.py`, and the matching developer documentation in the installed Hermes checkout. These findings justify changing the product story; they do not validate the proposed implementation.
