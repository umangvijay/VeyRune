"""Shared durable connector-build entry point (audit G07).

Two surfaces can request an integration build — the integrations API and
the orchestrator's build_integration tool. Both now go through this
service so a build has ONE durable record with its origin and (when it
came from autonomous execution) the parent run that is waiting on it:

- dispatch mode (API): create the record, persist a workflow task, and
  hand it to the engine/bus — worker restarts cannot lose it.
- track mode (orchestrator): create the record and hand its id to the
  inline factory run, so stage logs and the final outcome land in the
  same durable place and the parent run is recoverable from the record.
"""
import logging
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ORIGIN_API = "api"
ORIGIN_ORCHESTRATOR = "orchestrator"


async def create_build_record(
    factory,
    *,
    user_id: str,
    method: str,
    source: str,
    name: Optional[str],
    origin: str,
    parent_run_id: Optional[str] = None,
    parent_workflow_id: Optional[str] = None,
    parent_task_id: Optional[str] = None,
    wait_reason: str = "capability_missing",
) -> Dict[str, Any]:
    build_id = str(uuid.uuid4())
    await factory.mcp_repo.create_build({
        "build_id": build_id,
        "user_id": user_id,
        "name": name or "",
        "method": method,
        "source": (source or "")[:2000],
        "status": "queued",
        "stage": "queued",
        # Provenance for recovery (audit G07 / v5.6 A10): who asked, and
        # exactly which run+task is waiting for this capability.
        "origin": origin,
        "parent_run_id": parent_run_id,
        "parent_workflow_id": parent_workflow_id,
        "parent_task_id": parent_task_id,
        "wait_reason": wait_reason,
    })
    return {"build_id": build_id}


async def request_durable_build(
    factory,
    *,
    user_id: str,
    method: str,
    source: str,
    name: Optional[str],
    origin: str = ORIGIN_API,
    parent_run_id: Optional[str] = None,
    parent_workflow_id: Optional[str] = None,
    parent_task_id: Optional[str] = None,
    workflow_engine=None,
) -> Dict[str, Any]:
    """Dispatch mode: persist the build AND a workflow task, then enqueue."""
    from fastapi import HTTPException

    from backend.models.schemas import Task, TaskStatus, TaskTriggerEvent, WorkflowRun

    record = await create_build_record(
        factory, user_id=user_id, method=method, source=source, name=name,
        origin=origin, parent_run_id=parent_run_id,
        parent_workflow_id=parent_workflow_id, parent_task_id=parent_task_id,
    )
    build_id = record["build_id"]

    run_id = f"mcp-{build_id}"
    workflow_id = f"wf-{build_id[:8]}"
    goal = f"Build MCP integration {name or source[:160]}"
    task = Task(
        task_id="mcp-build", workflow_id=workflow_id, run_id=run_id,
        user_id=user_id, agent="core.mcp_build", tool="mcp_build",
        input_data={"method": method, "source": source, "name": name or "", "build_id": build_id, "intent": source[:4000]},
        status=TaskStatus.PENDING, timeout_seconds=300, max_retries=2,
        recovery_enabled=True,
    )
    run = WorkflowRun(
        run_id=run_id, workflow_id=workflow_id, user_id=user_id,
        goal=goal, status=TaskStatus.RUNNING, tasks=[task], thread_id=run_id,
    )
    run_data = run.model_dump(mode="json")
    run_data["tasks"] = [task.model_dump(mode="json")]
    try:
        await factory.workflow_repo.save_run(run_data)
        if workflow_engine:
            await workflow_engine.evaluate_dag(run_id)
        else:
            # Durable Pub/Sub in cloud; the in-process bus in local development.
            await factory.message_bus.publish("agentos-workflow-events", TaskTriggerEvent(
                workflow_id=workflow_id, run_id=run_id, task_id=task.task_id,
            ))
    except Exception as exc:
        await factory.mcp_repo.update_build(build_id, {
            "status": "error", "stage": "enqueue_failed",
            "error": "Could not enqueue MCP build; retry the request.",
        })
        logger.exception("Could not enqueue MCP build %s", build_id)
        raise HTTPException(status_code=503, detail="Could not queue MCP build") from exc
    return {
        "build_id": build_id,
        "run_id": run_id,
        "status": "queued",
        "origin": origin,
        "parent_run_id": parent_run_id,
    }


async def track_inline_build(
    factory,
    *,
    user_id: str,
    method: str,
    source: str,
    name: Optional[str],
    origin: str = ORIGIN_ORCHESTRATOR,
    parent_run_id: Optional[str] = None,
    parent_workflow_id: Optional[str] = None,
    parent_task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Track mode: durable record only; the caller runs the factory inline
    and passes the returned build_id so every stage persists."""
    return await create_build_record(
        factory, user_id=user_id, method=method, source=source, name=name,
        origin=origin, parent_run_id=parent_run_id,
        parent_workflow_id=parent_workflow_id, parent_task_id=parent_task_id,
    )
