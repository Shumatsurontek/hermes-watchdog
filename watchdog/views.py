"""Typed, bounded UI read models. Execution and recovery stay in the existing ledger."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .incidents import EVIDENCE_MAX, PAGE_MAX, ROOTS_MAX
from .policy import EVENTS_MAX, OBSERVATIONS_MAX
from .store import Store

Id = Annotated[str, Field(max_length=256)]
Text = Annotated[str, Field(max_length=4096)]
RunState = Literal["active", "returned", "failed", "interrupted", "unknown"]
IncidentKind = Literal["human_input", "related_failures", "worker_failed", "worker_interrupted"]
IncidentState = Literal["open", "acknowledged", "follow_up_requested", "resolved", "withdrawn", "grouped"]
DeliveryState = Literal["pending", "sending", "accepted", "failed", "unknown", "withdrawn"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Evidence(Contract):
    seq: int
    at: float
    kind: str
    tool: str = ""
    status: str = ""
    outcome: str = ""


class Worker(Contract):
    session_id: Id
    parent_id: Id
    root_id: Id
    label: Annotated[str, Field(max_length=160)]
    label_excerpt: bool
    state: RunState
    waiting: bool
    updated: float
    gap: Text
    observed_errors: int
    last_tool: str
    event_count: int
    retained_from: int


class WorkerDetail(Contract):
    worker: Worker
    evidence: Annotated[list[Evidence], Field(max_length=EVIDENCE_MAX)]


class Delivery(Contract):
    kind: Literal["recovery", "opening"]
    state: DeliveryState
    attempts: int


class Incident(Contract):
    id: Id
    root_id: Id
    kind: IncidentKind
    status: IncidentState
    revision: int
    updated: float
    recovery_available: bool
    member_ids: Annotated[list[Id], Field(max_length=1000)]
    tools: Annotated[list[str], Field(max_length=PAGE_MAX)]
    delivery: Annotated[list[Delivery], Field(max_length=3)]


class Counts(Contract):
    workers: int
    active: int
    waiting: int
    returned: int
    attention: int


class Mission(Contract):
    root_id: Id
    created: float
    updated: float
    deleted: bool
    route_available: bool
    counts: Counts
    workers: Annotated[list[Worker], Field(max_length=PAGE_MAX)]
    incidents: Annotated[list[Incident], Field(max_length=PAGE_MAX)]
    incident_count: int


class WorkPage(Contract):
    version: Literal[1] = 1
    missions: Annotated[list[Mission], Field(max_length=10)]
    next_cursor: int | None
    total_missions: int
    health: dict[str, str]


class ActionResult(Contract):
    incident_id: Id
    action: Literal["acknowledge", "request_recovery_review"]
    outbox_id: Id | None = None


class HistoryEvent(Contract):
    id: int
    kind: str
    status: str
    created: float


class HistoryTask(Contract):
    id: Id
    session_key: Id
    parent_id: Id
    revision: int
    goal: str
    execution: str
    supervision: str
    notification: str
    created: float
    can_cancel: bool
    cancel_pending: bool
    result: str | None
    result_excerpt: bool
    retry_reason: str
    observations: Annotated[list[Evidence], Field(max_length=OBSERVATIONS_MAX)]
    events: Annotated[list[HistoryEvent], Field(max_length=EVENTS_MAX)]


class HistoryPage(Contract):
    tasks: Annotated[list[HistoryTask], Field(max_length=PAGE_MAX)]
    next_cursor: str | None


class CancelResult(Contract):
    task_id: Id
    action: Literal["cancel_queued"]


def worker_detail(store: Store, session_id: str) -> WorkerDetail:
    run = store.native.run(session_id, evidence=True)
    evidence = [Evidence(**{k: e[k] for k in Evidence.model_fields if k in e}) for e in run["evidence"]]
    return WorkerDetail(
        worker=Worker(
            session_id=run["session_id"],
            parent_id=run["parent_id"],
            root_id=run["root_id"],
            label=run["label"],
            label_excerpt=bool(run["label_excerpt"]),
            state=run["state"],
            waiting=run["waiting"],
            updated=run["updated"],
            gap=run["gap"],
            observed_errors=sum(e.status == "error" for e in evidence),
            last_tool=next((e.tool for e in reversed(evidence) if e.tool), ""),
            event_count=run["seq"],
            retained_from=run["retained_from"],
        ),
        evidence=evidence,
    )


def work_page(store: Store, cursor: int = 0) -> WorkPage:
    # One read snapshot prevents mixing a worker completion and an older incident.
    # At most 10 roots, 50 displayed workers/root, 64 evidence rows/worker.
    with store.lock, store.db:
        store.db.execute("BEGIN")
        roots = store.db.execute(
            "SELECT r.*, max(n.updated) AS updated FROM native_roots r JOIN native_runs n USING(root_id) "
            "GROUP BY r.root_id ORDER BY r.created DESC, r.root_id LIMIT 11 OFFSET ?",
            (cursor,),
        ).fetchall()
        missions: list[Mission] = []
        for root in roots[:10]:
            rid = root["root_id"]
            totals = store.db.execute(
                "SELECT count(*), sum(state='active'), sum(state='returned') FROM native_runs WHERE root_id=?",
                (rid,),
            ).fetchone()
            waiting = store.db.execute(
                "SELECT count(*) FROM native_runs n WHERE n.root_id=? AND n.state='active' AND EXISTS "
                "(SELECT 1 FROM incidents i JOIN incident_members m ON i.id=m.incident_id "
                "WHERE m.session_id=n.session_id AND i.kind='human_input' "
                "AND i.status IN ('open','acknowledged','follow_up_requested'))",
                (rid,),
            ).fetchone()[0]
            runs = store.db.execute(
                "SELECT session_id FROM native_runs WHERE root_id=? ORDER BY created,session_id LIMIT ?",
                (rid, PAGE_MAX),
            ).fetchall()
            workers = [worker_detail(store, r[0]).worker for r in runs]
            ids = store.db.execute(
                "SELECT id FROM incidents WHERE root_id=? AND status NOT IN ('grouped','resolved','withdrawn') "
                "ORDER BY (status='open') DESC,(kind='human_input') DESC,updated DESC LIMIT ?",
                (rid, PAGE_MAX),
            ).fetchall()
            incidents: list[Incident] = []
            for row in ids:
                item = store.native.detail(row[0])
                members = [m["session_id"] for m in item["members"]]
                # Match the incident fingerprint, not whichever tool ran most recently.
                matched = store.db.execute(
                    "SELECT e.data FROM native_evidence e JOIN native_runs n USING(session_id) "
                    "JOIN incidents i ON i.root_id=n.root_id AND i.signature=e.fingerprint "
                    "WHERE i.id=? LIMIT 1",
                    (item["id"],),
                ).fetchone()
                tool = json.loads(matched[0]).get("tool", "") if matched else ""
                incidents.append(
                    Incident(
                        id=item["id"],
                        root_id=rid,
                        kind=item["kind"],
                        status=item["status"],
                        revision=item["revision"],
                        updated=item["updated"],
                        recovery_available=item["recovery_available"],
                        member_ids=members,
                        tools=[tool] if tool else [],
                        delivery=[
                            Delivery(kind=d["kind"], state=d["state"], attempts=d["attempts"]) for d in item["delivery"]
                        ],
                    )
                )
            incident_count = store.db.execute(
                "SELECT count(*) FROM incidents WHERE root_id=? AND status IN ('open','acknowledged','follow_up_requested')",
                (rid,),
            ).fetchone()[0]
            missions.append(
                Mission(
                    root_id=rid,
                    created=root["created"],
                    updated=root["updated"],
                    deleted=bool(root["deleted"]),
                    route_available=bool(root["route"] and root["route_active"] and not root["deleted"]),
                    counts=Counts(
                        workers=totals[0],
                        active=totals[1] - waiting,
                        waiting=waiting,
                        returned=totals[2],
                        attention=incident_count,
                    ),
                    workers=workers,
                    incidents=incidents,
                    incident_count=incident_count,
                )
            )
        total = store.db.execute("SELECT count(DISTINCT root_id) FROM native_runs").fetchone()[0]
        assert total <= ROOTS_MAX
        return WorkPage(
            missions=missions,
            next_cursor=cursor + 10 if len(roots) > 10 else None,
            total_missions=total,
            health=dict(store.db.execute("SELECT key,value FROM native_meta LIMIT 4").fetchall()),
        )


def history_page(store: Store, cursor: str = "") -> HistoryPage:
    page = store.page(cursor=cursor)
    tasks: list[HistoryTask] = []
    for row in page["tasks"]:
        t = store.public(row["id"], detail=True)
        tasks.append(
            HistoryTask(
                **{k: t[k] for k in HistoryTask.model_fields if k in t and k not in {"observations", "events"}},
                observations=[
                    Evidence(**{k: e[k] for k in Evidence.model_fields if k in e}) for e in t["observations"]
                ],
                events=[HistoryEvent(**{k: e[k] for k in HistoryEvent.model_fields}) for e in t["events"]],
                can_cancel=bool(
                    t["reserved"]
                    and not t["cancel_at"]
                    and not t["cancel_pending"]
                    and not t["deleted"]
                    and t["execution"] not in {"succeeded", "failed", "cancelled", "interrupted"}
                    and t["supervision"] != "control_unavailable"
                ),
            )
        )
    return HistoryPage(tasks=tasks, next_cursor=page["next_cursor"])
