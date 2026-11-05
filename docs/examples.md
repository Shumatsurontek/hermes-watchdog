# Usage examples

These examples target the v0.1.0 preview: local macOS/Linux Hermes Desktop, in-process plugins, search workers launched explicitly through Watchdog. They are instructions to try, not transcripts or guaranteed research outcomes. Complete the README setup first.

## 1. Check a plugin before installing it

Paste into a Desktop conversation, replacing the name:

> Use watchdog_start to research the public documentation for the Hermes plugin NAME. Give it a 180-second deadline and the search preset. Ask for its supported platforms, required services, data disclosures, and links to official sources. Mark anything not established by the sources as unknown. Return the task ID immediately; do not install anything or wait for the worker.

While it runs:

> Help me write a short checklist for deciding whether this plugin fits my local setup. Use what we already know; don't wait for the research.

When notified:

> Use watchdog_status to read the returned result. Separate documented facts from unknowns, and keep the source links. A successful worker outcome does not itself establish that the plugin is safe or compatible.

Watchdog should retain the outcome even if the chat notification cannot be accepted. The search preset supplies web search, not a general web-content extraction or private-repository toolset.

## 2. Research release requirements while writing the README

> Launch two separate Watchdog search workers. One should research the official Hermes catalog-submission requirements; the other should research the official Desktop-plugin compatibility requirements. Give each a 120-second deadline. Ask for concise findings and official source URLs. Return both task IDs and any launch refusals immediately, without polling or starting replacement workers.

Then continue the same conversation:

> While those run, draft a README outline for a local Desktop plugin that supervises background search tasks. Don't claim that the plugin is already accepted into the marketplace.

This exercises independent results and the responsive parent conversation. There can be at most three execution reservations in the profile; unresolved older attempts still consume a reservation.

## 3. Inspect and cancel a task you no longer need

Ask in the originating Desktop conversation:

> Show my Watchdog tasks and their execution, supervision, and notification states. Request cancellation of TASK_ID because I no longer need its research. Do not launch a replacement.

Or use the slash commands, substituting an actual ID returned by Watchdog:

```text
/watchdog status
/watchdog inspect TASK_ID
/watchdog cancel TASK_ID
```

Open **Watchdog** in the sidebar to inspect evidence and the returned result. “Cancellation queued” or “cancel requested” is not confirmation that a tool stopped. A cancelled or interrupted agent can still have an underlying tool unwinding, so its capacity reservation remains.

## 4. Exercise a short deadline

> Use Watchdog to compare the public plugin-development documentation of Hermes and another agent framework. Request source URLs and unresolved questions. Set a 10-second cancellation-request deadline for this test and return the task ID immediately.

This is a deliberately short deadline, not a simulated provider outage. The worker might finish before the deadline; do not label that as a timeout. Otherwise, Watchdog requests cancellation on a monitor poll and records the observed outcome. Polls run every five seconds, and cancellation is cooperative.

Avoid repeatedly running this example in a working profile: unresolved execution retains its slot. There is no force-release or retry control in this version. Use a disposable profile for failure testing and never delete live task data to bypass the bound.

## What is outside these examples

Native `delegate_task` observation, shared GitHub incidents, connection blocking, automatic retries, and recovery of running workers after restart are not implemented. The [native integration design](native-integration.md) is a proposal, not a v0.1.0 feature list.
