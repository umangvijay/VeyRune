"""
AgentOS — Webhooks Router

POST /api/v1/webhooks/{schedule_or_goal_id} — External trigger.
If the id matches one of the caller's schedules, its goal is executed with the
webhook payload injected as the root task's output ({{ tasks.webhook.output.* }}).
"""

import uuid
import logging
import hashlib
import json

from fastapi import APIRouter, Request, HTTPException

from backend.models.schemas import WorkflowRun, Task, TaskStatus
from backend.engine.repo_adapter import persist_run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/{schedule_id}")
async def trigger_webhook(schedule_id: str, request: Request):
    """
    Webhook trigger: starts the goal attached to the given schedule,
    with the webhook payload available to all tasks via interpolation.
    """
    factory = getattr(request.app.state, "factory", None)
    workflow_engine = getattr(request.app.state, "workflow_engine", None)
    if not factory or not workflow_engine:
        raise HTTPException(status_code=500, detail="Server not initialized")

    schedule = await factory.schedule_repo.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="No trigger registered with this id")
    from backend.security.rate_limiter import check_rate_limit, get_client_identifier
    from backend.security.secrets_vault import secrets_vault
    from backend.security.webhook_signature import verify_signature
    check_rate_limit(get_client_identifier(request), "webhook")
    encrypted = await factory.secrets_repo.get_secret(schedule["user_id"], f"webhook:{schedule_id}")
    if not encrypted:
        raise HTTPException(status_code=403, detail="Webhook signing is not configured")
    body_limit = 1_000_000
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > body_limit:
        raise HTTPException(status_code=413, detail="Webhook body exceeds 1 MB")
    body_buffer = bytearray()
    async for chunk in request.stream():
        if len(body_buffer) + len(chunk) > body_limit:
            raise HTTPException(status_code=413, detail="Webhook body exceeds 1 MB")
        body_buffer.extend(chunk)
    body = bytes(body_buffer)
    timestamp = request.headers.get("x-agentos-timestamp", "")
    signature = request.headers.get("x-agentos-signature", "")
    secret = secrets_vault.decrypt(encrypted)
    if not verify_signature(secret, timestamp, signature, body):
        raise HTTPException(status_code=401, detail="Invalid or expired webhook signature")
    check_rate_limit(f"user:{schedule['user_id']}", "workflow")
    if str(schedule.get("status", "")).upper() != "ACTIVE":
        raise HTTPException(status_code=409, detail="Trigger is paused")
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Webhook requires a JSON object")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook requires a JSON object")
    replay_key = "webhook:" + hashlib.sha256(f"{schedule_id}:{timestamp}:{signature}".encode()).hexdigest()
    if not await factory.idempotency_repo.atomic_insert(replay_key, schedule_id, "webhook"):
        raise HTTPException(status_code=409, detail="Webhook delivery already received")

    run_id = str(uuid.uuid4())
    workflow_id = f"wh-{run_id[:8]}"

    webhook_task = Task(
        task_id="webhook",
        workflow_id=workflow_id,
        run_id=run_id,
        user_id=schedule["user_id"],
        agent="core.set",
        status=TaskStatus.COMPLETED,
        input_data={"fields": payload},
        output_data=payload,
    )
    root_task = Task(
        task_id=f"root-{run_id[:8]}",
        workflow_id=workflow_id,
        run_id=run_id,
        user_id=schedule["user_id"],
        agent="OrchestratorAgent",
        input_data={"goal": schedule["goal"], "webhook_payload": payload},
        status=TaskStatus.PENDING,
        dependencies=["webhook"],
    )

    run = WorkflowRun(
        run_id=run_id,
        workflow_id=workflow_id,
        user_id=schedule["user_id"],
        goal=schedule["goal"],
        status=TaskStatus.RUNNING,
        tasks=[webhook_task, root_task],
    )
    await persist_run(factory.workflow_repo, run)
    logger.info(f"Webhook triggered schedule {schedule_id}, run {run_id}")

    await workflow_engine.evaluate_dag(run_id)
    await factory.idempotency_repo.commit_success(replay_key, run_id)

    return {"message": "Webhook received", "run_id": run_id, "workflow_id": workflow_id}
