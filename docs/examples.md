# Usage examples

These prompts are intended workflows, not claims of completed live-provider demos. Native observation needs a local Desktop conversation and the enabled plugin; no `watchdog_start` call is required.

## Release preparation

> Prepare the next release. Delegate separate read-only workers to inspect CI failures, identify release blockers, and draft a rollout checklist from local documentation. Preserve useful partial work and surface decisions that need me.

If independent workers hit matching errors, open **Related failures**. Inspect the group, then choose **Send recovery brief** to ask the original parent to review the evidence and current state. The plugin will not retry writes or diagnose a credential failure from a generic error.

## Waiting for approval

> Delegate the investigation, but ask me before making changes.

When a worker reaches a real Hermes human-input request, **Needs you** identifies it. Open the conversation to answer. An unrelated successful tool call does not clear that wait. Sending a recovery brief is not approval.

## Keep the returned work

> Split this investigation into independent tasks. Return partial findings as each worker finishes, even if another is blocked.

**Returned results** points to native worker transcripts. Open the worker to inspect its output, or open the root conversation to continue. Reported completion does not verify the content.

## Conversation-local status

Use `/watchdog status`, or ask:

> Show the Watchdog incidents and supervised tasks for this conversation. Distinguish returned work, unresolved execution, and recovery-message acceptance.

The status response is scoped to that conversation. It does not combine results from other profiles or chats.

## Optional legacy search launcher

Run the setup helper with `--legacy-launcher` to enable its search toolset, then ask:

> Use watchdog_start to research the official Hermes catalog submission requirements. Request cancellation after 120 seconds and return the task ID immediately.

Inspect it in **Legacy launcher history**, or use `/watchdog inspect <id>` and `/watchdog cancel <id>`. A deadline requests cooperative cancellation; it is not a hard kill or spend cap. Retry remains unavailable because the host does not attest repeat-safe execution. Existing v0.1 task history stays in this view after migration.
