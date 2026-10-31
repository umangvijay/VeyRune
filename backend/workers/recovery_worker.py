import logging
from backend.repositories.message_bus import MessageBus
from backend.repositories.workflow_repository import WorkflowRepository
from backend.repositories.audit_repository import audit_repo, AuditEvent
from backend.models.schemas import TaskRecoveryEvent, TaskStatus, TaskTriggerEvent, SemanticErrorReason
from backend.models.recovery import RecoveryContext, RecoveryAction, RecoveryActionEnum
from backend.agents.recovery.recovery_agent import get_recovery_agent
from backend.engine.repo_adapter import load_run, persist_task
from datetime import datetime, timezone

logger = logging.getLogger("recovery_worker")

class RecoveryWorker:
    def __init__(self, message_bus: MessageBus, workflow_repo: WorkflowRepository, workflow_engine=None):
        self.message_bus = message_bus
        self.repo = workflow_repo
        self.workflow_engine = workflow_engine

    async def handle_recovery_event(self, event, ctx=None):
        """Processes a TaskRecoveryEvent from the message bus."""
        try:
            if not isinstance(event, TaskRecoveryEvent):
                event = TaskRecoveryEvent(**event)
            await self._recover(event)
            if ctx:
                await ctx.ack()
        except Exception as e:
            logger.error(f"Recovery worker failed to process event: {e}")
            if ctx:
                await ctx.nack()

    async def _recover(self, event: TaskRecoveryEvent):
        run = await load_run(self.repo, event.run_id)
        if not run:
            return

        task = next((t for t in run.tasks if t.task_id == event.task_id), None)
        if not task:
            return

        # Idempotency check: only recover if status is RECOVERING and attempts match
        if task.status != TaskStatus.RECOVERING or task.recovery_attempts + 1 != event.recovery_attempt:
            logger.info(f"Ignoring duplicate/stale recovery event for {task.task_id}")
            return

        # Atomic claim: increment recovery_attempts to mark it claimed
        task.recovery_attempts += 1
        await persist_task(self.repo, run.run_id, task)

        # Formal recovery policy gate (v5.6 §3): deterministic caps, deadline,
        # and repeated-action detection decide whether the LLM recovery may
        # run at all. Refusals escalate into a structured incident.
        from backend.engine.failure_classifier import classify_failure
        from backend.services.recovery_policy import (
            RecoveryAttempt, RecoveryPolicy,
        )
        classifier = classify_failure(task.error or "")
        prior = [RecoveryAttempt(
            attempt=i + 1, category=classifier.category, action="retry",
            action_hash=RecoveryPolicy.action_hash(task.tool or task.agent,
                                                   classifier.category,
                                                   task.original_input or task.input_data),
            rationale=str(h)[:120], verified=False,
        ) for i, h in enumerate(getattr(task, "recovery_history", []) or [])]
        policy = RecoveryPolicy(attempts=prior)
        decision = policy.decide(classifier, task.tool or task.agent,
                                 task.original_input or task.input_data)
        if not decision.allowed:
            from backend.services.notification_service import NotificationService
            incident = RecoveryPolicy.incident(
                task.task_id, run.run_id, prior, classifier, decision.reason)
            task.status = TaskStatus.FAILED
            task.error = f"[recovery-escalated] {decision.reason}"
            await persist_task(self.repo, run.run_id, task)
            try:
                await NotificationService(getattr(workflow_engine, "notification_repo", None)).create(
                    user_id=run.user_id,
                    notification_type="SYSTEM",
                    title="Automatic recovery stopped — action needed",
                    body=decision.reason,
                    metadata={"incident": incident, "run_id": run.run_id, "task_id": task.task_id},
                )
            except Exception:
                logger.debug("Recovery escalation notification failed", exc_info=True)
            await self._trigger_dag(run.run_id)
            return

        try:
            if self.workflow_engine:
                from backend.services.llm_context import load_user_llm_keys, load_user_model
                factory = getattr(self.workflow_engine, "agent_factory", None)
                router = getattr(factory, "tool_router", None)
                await load_user_llm_keys(getattr(router, "secrets_repo", None), run.user_id, run_id=run.run_id)
                await load_user_model(getattr(self.workflow_engine, "settings_repo", None), run.user_id, task.input_data.get("_model"))
            context = RecoveryContext(
                workflow_id=run.workflow_id,
                run_id=run.run_id,
                task_id=task.task_id,
                task_type=task.tool or task.agent,
                original_input=task.original_input or task.input_data,
                current_input=task.input_data,
                validation_error=task.error or "Unknown semantic error",
                error_reason=getattr(SemanticErrorReason, task.error_type, SemanticErrorReason.TOOL_SEMANTIC_REJECTION),
                allowed_tool_schema={},
                previous_recovery_attempts=task.recovery_attempts - 1,
                safe_error_details="Semantic violation occurred during execution."
            )

            from backend.services import gemini_client

            prompt = f"Please analyze this recovery context and provide a RecoveryAction:\n{context.model_dump_json()}"
            events = await gemini_client.run_adk_debug(
                lambda model: get_recovery_agent(model=model),
                prompt,
                "AgentOS",
            )

            if not events:
                raise ValueError("RecoveryAgent returned empty response")

            raw_output = None
            for e in reversed(events):
                if getattr(e, 'output', None) is not None:
                    raw_output = e.output
                    break
                if hasattr(e, 'content') and e.content and hasattr(e.content, 'parts'):
                    for part in e.content.parts:
                        if hasattr(part, 'text') and part.text:
                            raw_output = part.text
                            break
                    if raw_output:
                        break

            if isinstance(raw_output, str):
                action = RecoveryAction.model_validate_json(raw_output)
            elif isinstance(raw_output, RecoveryAction):
                action = raw_output
            else:
                data = raw_output.model_dump() if hasattr(raw_output, 'model_dump') else raw_output
                action = RecoveryAction.model_validate(data)

            if action.action == RecoveryActionEnum.ABORT:
                logger.info(f"RecoveryAgent elected to ABORT task {task.task_id}")
                task.status = TaskStatus.FAILED
                task.error = f"Unrecoverable: {action.rationale}"
                task.completed_at = datetime.now(timezone.utc)
                await persist_task(self.repo, run.run_id, task)
                await self._trigger_dag(run.run_id)
                return

            if action.action == RecoveryActionEnum.REPAIR:
                logger.info(f"RecoveryAgent provided repair for task {task.task_id}")

                # Invalidate any approvals if the input changed!
                if task.input_data.get("_approved_request_id") and action.corrected_input != task.input_data:
                    logger.warning(f"Task {task.task_id} had an approval, but arguments changed. Invalidating approval.")
                    task.input_data.pop("_approved_request_id", None)

                internal_metadata = {k: v for k, v in task.input_data.items() if k in ("_model", "_agent_id")}
                task.input_data = {k: v for k, v in (action.corrected_input or {}).items() if not k.startswith("_")}
                task.input_data.update(internal_metadata)
                task.recovery_history.append({
                    "attempt": task.recovery_attempts,
                    "action": action.model_dump(),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                task.status = TaskStatus.PENDING
                await persist_task(self.repo, run.run_id, task)

                from backend.repositories.audit_repository import ActorType
                audit_repo.log_event(AuditEvent(
                    event_type="TASK_RECOVERED",
                    actor_id="SYSTEM",
                    actor_type=ActorType.SYSTEM,
                    resource_id=task.task_id,
                    workflow_id=run.workflow_id,
                    run_id=run.run_id,
                    task_id=task.task_id,
                    details={"attempt": task.recovery_attempts, "rationale": action.rationale}
                ))

                trigger_event = TaskTriggerEvent(
                    workflow_id=run.workflow_id,
                    run_id=run.run_id,
                    task_id=task.task_id
                )
                await self.message_bus.publish("agentos-workflow-events", trigger_event)

        except Exception as e:
            logger.error(f"Recovery Worker failed for task {task.task_id}: {e}")
            task.status = TaskStatus.FAILED
            task.error = f"Recovery failed: {str(e)}"
            task.completed_at = datetime.now(timezone.utc)
            await persist_task(self.repo, run.run_id, task)
            await self._trigger_dag(run.run_id)

    async def _trigger_dag(self, run_id: str):
        if self.workflow_engine:
            await self.workflow_engine.evaluate_dag(run_id)
