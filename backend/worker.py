import logging
import asyncio
from backend.engine.repo_adapter import persist_task
from backend.models.schemas import TaskTriggerEvent
from backend.models.schedule import SchedulerTriggerEvent
from backend.repositories.message_bus import MessageBus, MessageContext
from backend.repositories.schedule_repository import ScheduleRepository
from backend.engine.engine import WorkflowEngine
from backend.engine.repo_adapter import maybe_await

logger = logging.getLogger(__name__)

async def start_worker(message_bus: MessageBus, workflow_engine: WorkflowEngine, schedule_repo: ScheduleRepository = None, token_denylist_repo=None, audit_repo=None, idempotency_repo=None):
    logger.info("Worker started, listening for events...")
    
    async def handle_event(event, ctx: MessageContext):
        try:
            if isinstance(event, dict):
                run_id = event.get("run_id")
                task_id = event.get("task_id")
            else:
                run_id = getattr(event, "run_id", None)
                task_id = getattr(event, "task_id", None)
            if not run_id or not task_id:
                logger.error("Worker received trigger without run_id/task_id: %s", event)
                await ctx.ack()
                return
            logger.info(f"Worker processing task {task_id} for run {run_id}")
            await workflow_engine.execute_task(run_id, task_id)
            await _resume_build_waiter(run_id, task_id)
            await _evaluate_terminal_run(run_id)
            await ctx.ack()
        except Exception as e:
            logger.error(f"Worker encountered unhandled exception: {e}")
            await ctx.nack()

    async def _evaluate_terminal_run(run_id: str):
        """v5.6 §4: evaluation records come from REAL execution events —
        generated once per terminal run, with the per-run token spend the
        model client recorded. Evaluation must not be a placeholder."""
        try:
            repo = workflow_engine.repo
            run = await maybe_await(repo.get_run(run_id))
            if not run or run.get("status") not in ("COMPLETED", "FAILED"):
                return
            # Re-load the full model object so task fields are typed.
            from backend.models.schemas import WorkflowRun
            run_model = WorkflowRun.model_validate(run)
            from backend.services.evaluation_service import EvaluationService
            EvaluationService(getattr(workflow_engine, "db_client", None)).evaluate_run(run_model)
        except Exception:
            logger.debug("Run evaluation failed for %s", run_id, exc_info=True)

    async def _resume_build_waiter(run_id: str, task_id: str):
        """v5.6 A10: when a queued capability build completes, auto-resume the
        orchestrator task that parked on it. The build record carries the
        parent linkage; the parked task is a durable approval bound to the
        build — resolved here and re-dispatched with the approval bound to
        the task (mirrors the approvals endpoint's resume logic)."""
        try:
            repo = workflow_engine.repo
            run = await maybe_await(repo.get_run(run_id))
            if not run:
                return
            completed = next((t for t in (run.get("tasks") or []) if t.get("task_id") == task_id), None)
            if not completed or completed.get("agent") != "core.mcp_build":
                return
            build_id = ((completed.get("input_data") or {}) .get("build_id"))
            if not build_id or not hasattr(workflow_engine, "mcp_repo") or workflow_engine.mcp_repo is None:
                return
            build = await workflow_engine.mcp_repo.get_build(build_id)
            parent_run_id = build.get("parent_run_id")
            parent_task_id = build.get("parent_task_id")
            if not parent_run_id or not parent_task_id or build.get("status") != "success":
                return
            parent_run = await maybe_await(repo.get_run(parent_run_id))
            if not parent_run:
                return
            parent_task = next((t for t in (parent_run.get("tasks") or [])
                                if t.get("task_id") == parent_task_id), None)
            if not parent_task or parent_task.get("status") != "WAITING_APPROVAL":
                return
            pending = await maybe_await(repo.list_pending_approvals(parent_run.get("user_id") or ""))
            match = next((a for a in pending
                          if a.get("run_id") == parent_run_id and a.get("task_id") == parent_task_id
                          and ((a.get("arguments") or {}).get("build_id") == build_id)), None)
            if not match:
                return
            resolved = await maybe_await(repo.resolve_approval(
                match["approval_id"], "APPROVED", decision_by="SYSTEM:capability-build"))
            if not resolved:
                return
            await maybe_await(repo.reset_failed_task(parent_run.get("workflow_id"), parent_task_id))
            fresh = await maybe_await(repo.get_run(parent_run_id))
            fresh_task = next((t for t in (fresh.get("tasks") or []) if t.get("task_id") == parent_task_id), None)
            if fresh_task is not None:
                fresh_task["status"] = "PENDING"
                fresh_task["error"] = None
                fresh_task.setdefault("input_data", {})["_approved_request_id"] = match["approval_id"]
                await persist_task(repo, parent_run_id, fresh_task)
            await maybe_await(repo.update_run_status(parent_run_id, "RUNNING"))
            await message_bus.publish("agentos-workflow-events", TaskTriggerEvent(
                workflow_id=fresh.get("workflow_id"), run_id=parent_run_id, task_id=parent_task_id,
            ).model_dump(mode="json"))
            logger.warning("Capability build %s landed; resumed parked task %s/%s",
                           build_id[:8], parent_run_id[:8], parent_task_id)
        except Exception:
            logger.exception("Build-waiter resume failed for %s/%s", run_id, task_id)

    # We will gather all consumers at the end
    
    async def handle_schedule(event, ctx: MessageContext):
        try:
            if not schedule_repo:
                await ctx.ack()
                return

            logger.info(f"Worker received schedule trigger: {event}")
            if isinstance(event, SchedulerTriggerEvent):
                trigger = event
            else:
                trigger = SchedulerTriggerEvent(**event)
            schedule = await maybe_await(schedule_repo.get_schedule(trigger.schedule_id))

            if not schedule or str(schedule.get("status", "")).upper() != "ACTIVE":
                logger.warning(f"Schedule {trigger.schedule_id} not found or not ACTIVE")
                await ctx.ack()
                return

            # Max-concurrency guard (audit P2.12): skip this window if the
            # schedule's previous run is still in flight, and tell the user.
            try:
                history = await maybe_await(schedule_repo.get_execution_history(trigger.schedule_id, limit=3)) or []
                for entry in history:
                    prev_run_id = entry.get("run_id")
                    if not prev_run_id:
                        continue
                    prev = await maybe_await(workflow_engine.repo.get_run(prev_run_id))
                    if prev and prev.get("status") in ("PENDING", "RUNNING", "WAITING", "RECOVERING", "RETRYING"):
                        logger.info("Skipping schedule %s trigger: previous run %s still %s",
                                    trigger.schedule_id, prev_run_id[:12], prev.get("status"))
                        await maybe_await(schedule_repo.record_execution(trigger.schedule_id, prev_run_id, "SKIPPED_BUSY"))
                        from backend.services.notification_service import NotificationService
                        await NotificationService(getattr(workflow_engine, "notification_repo", None)).create(
                            user_id=schedule["user_id"],
                            notification_type="SCHEDULE_SKIPPED",
                            title="Schedule skipped",
                            body=f"'{schedule.get('name')}' did not fire: its previous run is still in progress.",
                            metadata={"schedule_id": trigger.schedule_id, "run_id": prev_run_id},
                        )
                        await ctx.ack()
                        return
            except Exception:
                logger.warning("Concurrency guard check failed; proceeding with trigger", exc_info=True)

            # Deterministic id: schedule_id + logical scheduled time. The API's
            # run-now creates the same run; create_if_absent keeps it exactly-once.
            from backend.scheduler.run_factory import build_scheduled_run, scheduled_run_id
            run_id = scheduled_run_id(trigger.schedule_id, trigger.scheduled_time)
            run = build_scheduled_run(schedule, run_id)

            created = await maybe_await(workflow_engine.repo.create_if_absent(run.model_dump(mode="json")))
            if created:
                logger.info(f"Successfully enqueued new run {run_id} for schedule {trigger.schedule_id}")
                try:
                    await maybe_await(schedule_repo.record_execution(trigger.schedule_id, run_id, "STARTED"))
                except Exception:
                    logger.warning("Failed to record schedule execution", exc_info=True)
                
                await workflow_engine.evaluate_dag(run_id)
            else:
                logger.info(f"Run {run_id} already exists; rechecking pending tasks.")
                await workflow_engine.evaluate_dag(run_id)
                
            await ctx.ack()
        except Exception as e:
            logger.error(f"Worker encountered error processing schedule trigger: {e}")
            await ctx.nack()

    async def cron_ticker():
        """Local scheduler: fire due cron schedules (Cloud Scheduler replaces this in prod).

        Catch-up policy: skip missed windows — each due schedule fires at most
        once per pass and next_run_at advances from *now*, so a backlog of
        missed windows during downtime collapses into a single run. A large
        miss is surfaced to the user instead of firing silently."""
        from datetime import datetime, timezone
        from backend.services.notification_service import NotificationService
        notification_repo = getattr(workflow_engine, "notification_repo", None)
        while True:
            try:
                if schedule_repo and hasattr(schedule_repo, "list_due_schedules"):
                    now = datetime.now(timezone.utc)
                    due = await maybe_await(schedule_repo.list_due_schedules(now.isoformat()))
                    for schedule in due:
                        trigger = SchedulerTriggerEvent(
                            schedule_id=schedule["schedule_id"], scheduled_time=datetime.fromisoformat(schedule["next_run_at"].replace("Z", "+00:00"))
                        )
                        # Missed-run alert: the window is far in the past, i.e.
                        # the worker was unavailable when it was due.
                        try:
                            missed_by = (now - trigger.scheduled_time).total_seconds()
                            if missed_by > 300:
                                await NotificationService(notification_repo).create(
                                    user_id=schedule["user_id"],
                                    notification_type="SYSTEM",
                                    title="Schedule caught up",
                                    body=f"'{schedule.get('name')}' missed its {trigger.scheduled_time:%H:%M} UTC window "
                                         f"({int(missed_by // 60)} min late). Running it once now; later missed windows are skipped.",
                                    metadata={"schedule_id": schedule["schedule_id"], "missed_by_seconds": int(missed_by)},
                                )
                        except Exception:
                            logger.debug("Missed-run notification failed", exc_info=True)
                        await message_bus.publish(
                            "agentos-scheduler-triggers", trigger.model_dump(mode="json")
                        )
                        # Advance next_run_at so the schedule doesn't refire
                        try:
                            from croniter import croniter
                            cron = croniter(schedule.get("cron_expression") or "", now)
                            next_run = cron.get_next(datetime).isoformat()
                        except Exception:
                            next_run = None
                        await maybe_await(schedule_repo.update_schedule(
                            schedule["schedule_id"], {"next_run_at": next_run}
                        ))
            except Exception as e:
                logger.error(f"Cron ticker error: {e}")
            # Housekeeping: expired denylist entries are dead weight; purge
            # opportunistically instead of needing a separate cron job.
            try:
                if token_denylist_repo is not None:
                    await maybe_await(token_denylist_repo.purge_expired())
            except Exception:
                logger.debug("Denylist purge failed", exc_info=True)
            # Paused browser sessions (human challenges) hold a whole
            # Chromium; expire leases so worker memory stays bounded (v5.6 A7).
            try:
                from backend.services.browser_sessions import sweep_expired_sessions
                await sweep_expired_sessions()
            except Exception:
                logger.debug("Browser session sweep failed", exc_info=True)
            # Crash-orphaned idempotency locks (audit F07): a worker that died
            # between claim and commit leaves 'running' forever. Quarantine it
            # as 'uncertain' — the external outcome is unknown, so blind
            # replay is never offered; an operator or provider receipt
            # reconciles it explicitly.
            try:
                if idempotency_repo is not None and hasattr(idempotency_repo, "sweep_stale_running"):
                    swept = await maybe_await(idempotency_repo.sweep_stale_running(older_than_seconds=1800))
                    if swept:
                        logger.warning("Idempotency sweep: %d stale running execution(s) quarantined as uncertain", swept)
            except Exception:
                logger.debug("Idempotency stale-running sweep failed", exc_info=True)
            # Retention control (enterprise P2): purge old events/audit rows
            # once per day. Workflow runs are never auto-deleted.
            try:
                from backend.config.settings import settings as app_settings
                retention_days = int(getattr(app_settings, "RETENTION_DAYS", 0) or 0)
                if retention_days > 0 and getattr(start_worker, "_last_retention_purge", None) != datetime.now(timezone.utc).date():
                    start_worker._last_retention_purge = datetime.now(timezone.utc).date()
                    repo = workflow_engine.repo
                    if hasattr(repo, "purge_old_events"):
                        removed = await maybe_await(repo.purge_old_events(retention_days))
                        logger.info("Retention purge: %d events older than %dd removed", removed, retention_days)
                    if audit_repo is not None and hasattr(audit_repo, "purge_older_than"):
                        removed = await maybe_await(audit_repo.purge_older_than(retention_days))
                        logger.info("Retention purge: %d audit rows older than %dd removed", removed, retention_days)
            except Exception:
                logger.debug("Retention purge failed", exc_info=True)
            await asyncio.sleep(30)

    from backend.workers.recovery_worker import RecoveryWorker
    recovery_worker = RecoveryWorker(message_bus, workflow_engine.repo, workflow_engine)

    await asyncio.gather(
        message_bus.consume("agentos-workflow-events", handle_event),
        message_bus.consume("agentos-scheduler-triggers", handle_schedule),
        message_bus.consume("agentos-recovery-events", recovery_worker.handle_recovery_event),
        cron_ticker(),
    )


# ── Standalone worker entrypoint ──────────────────────────────────────
# Run with: python -m backend.worker
# Docker: CMD ["python", "-m", "backend.worker"]
# Env: WORKER_ONLY=1 (set in Dockerfile.worker / cloudbuild.yaml)

if __name__ == "__main__":
    import os
    import sys

    # Confirm this is a standalone worker, not the API
    worker_only = os.environ.get("WORKER_ONLY", "1")
    logger.info("Starting standalone worker process (WORKER_ONLY=%s)", worker_only)

    async def _boot_and_run():
        from backend.config.settings import settings
        from backend.repositories.factory import RepositoryFactory

        # RepositoryFactory reads the shared settings module itself; it does
        # not accept a settings argument. The old call crashed before any
        # consumer could start, leaving queued automation tasks untouched.
        factory = RepositoryFactory()
        await factory.initialize()

        # Tool router (same as API init)
        from backend.mcp.tool_router import ToolRouter
        from backend.mcp.tool_policy import ToolPolicy
        from backend.services.approvals_engine import ApprovalsEngine

        approvals_engine = ApprovalsEngine()
        tool_policy = ToolPolicy()
        tool_router = ToolRouter(
            factory.mcp_repo, tool_policy, approvals_engine,
            factory.idempotency_repo, secrets_repo=factory.secrets_repo,
        )

        # Agent factory
        from backend.agents.agent_factory import AgentFactory
        from backend.services.runtime_snapshot import RuntimeSnapshotRegistry
        snapshot_registry = RuntimeSnapshotRegistry()
        agent_factory = AgentFactory(snapshot_registry, tool_router)

        # Workflow engine
        from backend.engine.engine import WorkflowEngine
        workflow_engine = WorkflowEngine(
            factory.workflow_repo, factory.message_bus,
            agent_factory, factory.memory_repo, factory.settings_repo,
            factory.notification_repo, factory.adaptive_policy_repo,
        )

        logger.info("Worker initialized. Listening for events...")
        await start_worker(factory.message_bus, workflow_engine, factory.schedule_repo, factory.token_denylist_repo, factory.audit_repo)

    try:
        asyncio.run(_boot_and_run())
    except KeyboardInterrupt:
        logger.info("Worker stopped by keyboard interrupt.")
        sys.exit(0)
