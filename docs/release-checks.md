# Prerelease acceptance and submission

## Local Desktop acceptance

Use a disposable profile and verify its Desktop binary matches the tested Hermes revision. Enable the Python plugin and Desktop contribution. Default native notices and the judge remain off.

1. Ask normal Hermes to delegate independent read-only release-preparation tasks. Do not use `watchdog_start`. Confirm the workers appear in Watchdog and the parent remains usable.
2. Cause a labelled controlled matching failure in two workers while a third returns useful local work. Confirm one related group and a separate returned worker. Verify that Hermes owns any retries and breaker behavior.
3. Trigger a real human-input request. Confirm an unrelated tool call cannot clear it; answer in the original conversation and confirm the matching wait resolves.
4. Open the incident's conversation. Send one recovery brief, click again rapidly, and verify only one request reaches the correct parent. Repeat once with a busy parent and once with an idle parent. Record acceptance and observed delivery separately.
5. Switch profiles/gateways during reads and actions. Confirm stale data clears and an old action cannot target the new profile.
6. Stop, reset, or delete an origin before a queued send. Confirm it is withdrawn. Close a tab without deleting it and confirm that alone does not withdraw it. A send already entered is not recallable.
7. Restart with unfinished work and an ambiguous send. Confirm execution/delivery uncertainty persists and no native worker or ambiguous request is replayed.
8. Open legacy history, launch one optional search worker, inspect its result, and request cancellation of another. Confirm v1 reservations and retry refusal remain intact.

The scripted host probe and seeded browser harness cannot satisfy the native/live-provider checks above.

## Evidence and comparison

The proposed paired comparison is six scenarios with three repetitions in each condition: Hermes alone and the same Hermes plus Watchdog. Healthy slow work, transient failure followed by success, cross-worker matching failures, human-input wait, returned result during a busy parent turn, and restart with ambiguous delivery comprise the scenario set.

Record actual provider/model/temperature, iteration/call/timeout ceilings, and the operator's spend ceiling before live execution. Measure completed work, missed outcomes, repeated dependency calls, false grouping/interventions, human decisions, acceptance versus delivered messages, and host usage. Do not invent a baseline without Hermes's existing safeguards. Do not claim saved connector calls from a breaker that belongs to Hermes.

The candidate's feature claim is native evidence grouping and durable scoped recovery intent. A measured reduction in repeated investigations remains a release/demo qualification gate.

## Runtime payload

`scripts/stage.py` stages an explicit runtime allowlist and hashes. Tests, development probes, private plans, caches, and internal host imports are excluded. Validate the exact stage with `hermes plugins validate <stage> --install-deps` and inspect warnings. Validator-generated caches are not release files; package only paths in the stage manifest.

`assets/catalog-banner.png` remains the 2:1 promotional image. Pin its public raw URL to the same eventual 40-character source commit used in the catalog. Generated banner art is not a product screenshot. Browser fixture captures are clearly labelled and do not attest native acceptance.

The v0.2.0 prerelease is published at https://github.com/Shumatsurontek/hermes-watchdog/releases/tag/v0.2.0. Prepare the catalog PR against its exact reviewed source commit after completing the native acceptance gates. Do not use a placeholder SHA in a submitted entry.

## Competition assets

Use the [85-second storyboard](native-integration.md). The supplied announcement requires a catalog PR, a working X demo tagging `@NousResearch`, and both links in the entry form. No catalog submission, X post, or form submission has been performed.
