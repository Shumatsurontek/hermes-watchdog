"""Authenticated host-mounted API. HTTP only queues actions; it never controls handles."""

import hashlib
import importlib.util
import sqlite3
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

# Hermes loads dashboard backends as standalone modules, independently of the
# agent plugin package. Load ONLY our own package under a path-specific namespace
# so installations in different profiles cannot import each other's code/state.
_package = Path(__file__).resolve().parents[1] / "watchdog"
# A path alone aliases old Python modules after a supported hot reload. Bind the
# namespace to the installed code too, while in-flight old requests keep theirs.
_digest = hashlib.sha256(str(_package).encode())
_sources = sorted(_package.glob("*.py"))
if len(_sources) > 32:
    raise ImportError("Watchdog backend exceeds its 32-module load bound")
for _source in _sources:
    with _source.open("rb") as _file:
        _contents = _file.read(262_145)
    if len(_contents) > 262_144:
        raise ImportError("Watchdog backend module exceeds its 256 KiB load bound")
    _digest.update(_source.name.encode())
    _digest.update(_contents)
_name = "watchdog_api_" + _digest.hexdigest()[:16]
if _name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        _name, _package / "__init__.py", submodule_search_locations=[str(_package)]
    )
    if _spec is None or _spec.loader is None:
        raise ImportError("Cannot load Watchdog backend package")
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _module
    _spec.loader.exec_module(_module)
from importlib import import_module

_storage = import_module(_name + ".storage")
_views = import_module(_name + ".views")
Rejected = import_module(_name + ".policy").Rejected

router = APIRouter()


def ledger():
    store = None
    try:
        store = _storage.open_store()
        yield store
    except Rejected as exc:
        raise HTTPException(409, str(exc)) from None
    except sqlite3.OperationalError:
        raise HTTPException(503, "Watchdog storage is busy or unavailable") from None
    finally:
        if store is not None:
            store.close()


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: str = Field(pattern="^cancel$")
    session_key: str = Field(min_length=1, max_length=256)
    revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=80)


@router.get("/tasks")
def tasks(cursor: str = Query("", max_length=64), limit: int = Query(50, ge=1, le=50), store=Depends(ledger)):
    return store.page(cursor=cursor, limit=limit)


@router.get("/tasks/{task_id}")
def task(task_id: str, store=Depends(ledger)):
    return store.public(task_id, detail=True)


@router.post("/tasks/{task_id}/actions", status_code=202, response_model=_views.CancelResult)
def action(task_id: str, body: Action, store=Depends(ledger)):
    store.request_cancel(task_id, body.session_key, body.revision, body.idempotency_key)
    return {"task_id": task_id, "action": "cancel_queued"}


class IncidentAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: str = Field(pattern="^(acknowledge|request_recovery_review)$")
    parent_session_id: str = Field(min_length=1, max_length=256)
    revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=80)


@router.get("/incidents")
def incidents(
    cursor: str = Query("", max_length=256),
    limit: int = Query(50, ge=1, le=50),
    view: str = Query("all", pattern="^(all|related|needs)$"),
    store=Depends(ledger),
):
    return store.native.page(cursor=cursor, limit=limit, view=view)


@router.get("/incidents/{incident_id}")
def incident(incident_id: str, store=Depends(ledger)):
    return store.native.detail(incident_id)


@router.post("/incidents/{incident_id}/actions", status_code=202, response_model=_views.ActionResult)
def incident_action(incident_id: str, body: IncidentAction, store=Depends(ledger)):
    return store.native.action(incident_id, body.action, body.parent_session_id, body.revision, body.idempotency_key)


@router.get("/native-runs")
def native_runs(
    cursor: str = Query("", max_length=256),
    limit: int = Query(50, ge=1, le=50),
    view: str = Query("all", pattern="^(all|returned)$"),
    store=Depends(ledger),
):
    return store.native.page(cursor=cursor, limit=limit, runs=True, view=view)


@router.get("/native-runs/{session_id}")
def native_run(session_id: str, store=Depends(ledger)):
    return store.native.run(session_id, evidence=True)


@router.get("/work", response_model=_views.WorkPage)
def work(cursor: int = Query(0, ge=0, le=256), store=Depends(ledger)) -> _views.WorkPage:
    return _views.work_page(store, cursor)


@router.get("/work/runs/{session_id}", response_model=_views.WorkerDetail)
def work_run(session_id: str, store=Depends(ledger)) -> _views.WorkerDetail:
    return _views.worker_detail(store, session_id)


@router.get("/history", response_model=_views.HistoryPage)
def history(cursor: str = Query("", max_length=64), store=Depends(ledger)) -> _views.HistoryPage:
    return _views.history_page(store, cursor)
