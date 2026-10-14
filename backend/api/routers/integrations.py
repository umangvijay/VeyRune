"""
AgentOS — Integrations Router

GET  /api/v1/integrations                — List all integrations
POST /api/v1/integrations/build          — Build from OpenAPI spec
POST /api/v1/integrations/build-from-url — Build from URL
POST /api/v1/integrations/build-from-prompt — Build from description
GET  /api/v1/integrations/{id}           — Get integration detail
POST /api/v1/integrations/{id}/test      — Test an integration
GET  /api/v1/integrations/{id}/health    — Get health status
POST /api/v1/integrations/{id}/enable    — Enable
POST /api/v1/integrations/{id}/disable   — Disable
DELETE /api/v1/integrations/{id}         — Delete
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Depends, status
from pydantic import BaseModel

from backend.api.dependencies.auth import get_current_user, AuthenticatedUser, require_not_viewer
from backend.security.rate_limiter import check_rate_limit
from backend.security.input_sanitizer import sanitize_text, InputValidationError
from backend.mcp.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _get_factory(request: Request):
    factory = getattr(request.app.state, "factory", None)
    if not factory:
        raise HTTPException(status_code=500, detail="Server not initialized")
    return factory


# ── Request Models ────────────────────────────────────────────────

class BuildFromSpecRequest(BaseModel):
    spec: str           # OpenAPI/Swagger JSON/YAML
    name: Optional[str] = None

class BuildFromURLRequest(BaseModel):
    url: str            # URL to API docs or a website
    name: Optional[str] = None
    method: Optional[str] = None  # url | website

class BuildFromPromptRequest(BaseModel):
    prompt: str         # Natural language description
    name: Optional[str] = None

class BuildFromWebsiteRequest(BaseModel):
    url: str
    name: Optional[str] = None
    notes: Optional[str] = None


# ══════════════════════════════════════════════════════════════════
#  LIST / GET
# ══════════════════════════════════════════════════════════════════

@router.get("")
async def list_integrations(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """List all integrations visible to the user."""
    factory = _get_factory(request)
    # Admins administer the whole platform: see every integration.
    mcps = await factory.mcp_repo.list_mcps(user_id=None if user.is_admin() else user.user_id)

    # Enrich with circuit breaker status
    results = []
    for mcp in mcps:
        mcp_id = mcp.get("mcp_id", "")
        breaker_status = circuit_breaker.get_status(mcp_id)
        mcp["circuit_breaker"] = breaker_status
        # Get cached tool count
        tools = await factory.mcp_repo.get_cached_tools(mcp_id=mcp_id)
        mcp["tool_count"] = len(tools)
        results.append(mcp)

    return {"integrations": results, "count": len(results)}


@router.get("/{mcp_id}")
async def get_integration(
    mcp_id: str, request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Get integration detail with tools and health."""
    factory = _get_factory(request)
    mcp = await factory.mcp_repo.get_mcp(mcp_id)
    if not mcp or (mcp.get("owner") not in (user.user_id, "system") and not user.is_admin()):
        raise HTTPException(status_code=404, detail="Integration not found")

    tools = await factory.mcp_repo.get_cached_tools(mcp_id=mcp_id)
    breaker_status = circuit_breaker.get_status(mcp_id)

    return {
        **mcp,
        "tools": tools,
        "tool_count": len(tools),
        "circuit_breaker": breaker_status,
    }


# ══════════════════════════════════════════════════════════════════
#  BUILD (MCP Factory) — async jobs with persisted stages
# ══════════════════════════════════════════════════════════════════

async def _start_build(factory, user_id: str, method: str, source: str, name: Optional[str], workflow_engine=None) -> dict:
    """Persist MCP build as a normal workflow task so worker restarts cannot lose it."""
    import uuid
    from backend.models.schemas import Task, TaskStatus, WorkflowRun, TaskTriggerEvent

    build_id = str(uuid.uuid4())
    await factory.mcp_repo.create_build({
        "build_id": build_id,
        "user_id": user_id,
        "name": name or "",
        "method": method,
        "source": source[:2000],
        "status": "queued",
        "stage": "queued",
    })

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
        "message": "MCP Factory build started. Poll /integrations/builds/{build_id} for progress.",
    }


@router.post("/build-from-spec", status_code=status.HTTP_202_ACCEPTED)
@router.post("/build", status_code=status.HTTP_202_ACCEPTED)
async def build_from_spec(
    body: BuildFromSpecRequest, request: Request,
    user: AuthenticatedUser = Depends(require_not_viewer),
):
    """Build an MCP integration from a raw OpenAPI/Swagger spec (JSON or YAML)."""
    factory = _get_factory(request)
    check_rate_limit(f"user:{user.user_id}", "mcp_build")

    try:
        spec_text = sanitize_text(body.spec, "spec", max_length=500_000)
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)

    return await _start_build(factory, user.user_id, "spec", spec_text, body.name, getattr(request.app.state, "workflow_engine", None))


@router.post("/build-from-url", status_code=status.HTTP_202_ACCEPTED)
async def build_from_url(
    body: BuildFromURLRequest, request: Request,
    user: AuthenticatedUser = Depends(require_not_viewer),
):
    """Build from a URL pointing to an OpenAPI spec or API documentation."""
    factory = _get_factory(request)
    check_rate_limit(f"user:{user.user_id}", "mcp_build")

    try:
        url = sanitize_text(body.url, "url", max_length=2000)
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)

    return await _start_build(factory, user.user_id, body.method or "url", url, body.name, getattr(request.app.state, "workflow_engine", None))


@router.post("/build-from-website", status_code=status.HTTP_202_ACCEPTED)
async def build_from_website(
    body: BuildFromWebsiteRequest, request: Request,
    user: AuthenticatedUser = Depends(require_not_viewer),
):
    """Build a Playwright website MCP for an app with no public API."""
    factory = _get_factory(request)
    check_rate_limit(f"user:{user.user_id}", "mcp_build")
    try:
        url = sanitize_text(body.url, "url", max_length=2000)
        notes = sanitize_text(body.notes or "", "notes", max_length=4000) if body.notes else ""
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    source = f"{url}\n{notes}".strip()
    return await _start_build(factory, user.user_id, "website", source, body.name, getattr(request.app.state, "workflow_engine", None))


@router.post("/build-from-prompt", status_code=status.HTTP_202_ACCEPTED)
async def build_from_prompt(
    body: BuildFromPromptRequest, request: Request,
    user: AuthenticatedUser = Depends(require_not_viewer),
):
    """Build from a natural language description (lands in pending-review trust tier)."""
    factory = _get_factory(request)
    check_rate_limit(f"user:{user.user_id}", "mcp_build")

    try:
        prompt = sanitize_text(body.prompt, "prompt", max_length=5000)
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)

    return await _start_build(factory, user.user_id, "prompt", prompt, body.name, getattr(request.app.state, "workflow_engine", None))


@router.get("/builds/{build_id}")
async def get_build_status(
    build_id: str, request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Poll the status, stage, and logs of an MCP factory build."""
    factory = _get_factory(request)
    build = await factory.mcp_repo.get_build(build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")
    if build.get("user_id") != user.user_id and not user.is_admin():
        raise HTTPException(status_code=403, detail="Access denied")
    return build


# ══════════════════════════════════════════════════════════════════
#  TEST / HEALTH / ENABLE / DISABLE / DELETE
# ══════════════════════════════════════════════════════════════════

@router.post("/{mcp_id}/test")
async def test_integration(
    mcp_id: str, request: Request,
    user: AuthenticatedUser = Depends(require_not_viewer),
):
    """Test an integration: validate cached tools and run a safe live GET probe if possible."""
    factory = _get_factory(request)
    mcp = await factory.mcp_repo.get_mcp(mcp_id)
    if not mcp or (mcp.get("owner") not in (user.user_id, "system") and not user.is_admin()):
        raise HTTPException(status_code=404, detail="Integration not found")

    from datetime import datetime, timezone
    tools = await factory.mcp_repo.get_cached_tools(mcp_id=mcp_id)
    transport = str(mcp.get("transport") or "internal")

    try:
        if transport == "internal":
            if not tools:
                raise ValueError("No tools registered for this integration")
            # Live probe: first GET tool with no required arguments
            probe = {"status": "skipped", "reason": "no parameterless GET tool"}
            for tool in tools:
                op = tool.get("operation") or {}
                required = (tool.get("input_schema") or {}).get("required") or []
                if op.get("http_method") == "GET" and not required:
                    from backend.mcp.openapi_executor import execute_openapi_tool
                    result = await execute_openapi_tool(
                        mcp, tool, {}, user_id=user.user_id, secrets_repo=factory.secrets_repo,
                    )
                    probe = {"status": "probed", "ok": result.get("ok"), "http_status": result.get("status")}
                    break
            if probe.get("status") == "skipped":
                return {"status": "untested", "tools_discovered": len(tools), "probe": probe}
            healthy = probe.get("ok") is True
            await factory.mcp_repo.update_mcp_health(
                mcp_id, "HEALTHY" if healthy else "UNHEALTHY", datetime.now(timezone.utc)
            )
            (circuit_breaker.record_success if healthy else circuit_breaker.record_failure)(mcp_id)
            return {
                "status": "healthy" if healthy else "unhealthy",
                "tools_discovered": len(tools),
                "probe": probe,
            }

        # Remote MCP server (streamable HTTP / stdio)
        from backend.mcp.mcp_client import MCPClientManager
        discovered = await MCPClientManager.list_tools(mcp)
        await factory.mcp_repo.update_mcp_health(mcp_id, "HEALTHY", datetime.now(timezone.utc))
        circuit_breaker.record_success(mcp_id)
        return {"status": "healthy", "tools_discovered": len(discovered) if discovered else 0}
    except Exception as e:
        await factory.mcp_repo.update_mcp_health(
            mcp_id, "UNHEALTHY", datetime.now(timezone.utc)
        )
        circuit_breaker.record_failure(mcp_id)
        return {"status": "unhealthy", "error": str(e)}


# ══════════════════════════════════════════════════════════════════
#  CREDENTIALS
# ══════════════════════════════════════════════════════════════════

class CredentialsRequest(BaseModel):
    api_key: str
    auth_type: Optional[str] = "API_KEY"   # API_KEY | OAUTH2 | BASIC


@router.post("/{mcp_id}/credentials")
async def set_credentials(
    mcp_id: str, body: CredentialsRequest, request: Request,
    user: AuthenticatedUser = Depends(require_not_viewer),
):
    """Store an encrypted credential for this integration and link it via credential_ref."""
    factory = _get_factory(request)
    mcp = await factory.mcp_repo.get_mcp(mcp_id)
    if not mcp or (mcp.get("owner") not in (user.user_id, "system") and not user.is_admin()):
        raise HTTPException(status_code=404, detail="Integration not found")
    if mcp.get("owner") not in (user.user_id, "system") and not user.is_admin():
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        api_key = sanitize_text(body.api_key, "api_key", max_length=4000)
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)

    from backend.security.secrets_vault import secrets_vault
    credential_ref = f"mcp:{mcp_id}:api_key"
    encrypted = secrets_vault.encrypt(api_key)
    await factory.secrets_repo.store_secret(user.user_id, credential_ref, encrypted)

    auth = mcp.get("auth") or {}
    if isinstance(auth, str):
        import json as _json
        auth = _json.loads(auth)
    new_type = (body.auth_type or "API_KEY").upper()
    # Preserve the scheme placement recorded at build time (header/query + header name).
    placement = {k: auth[k] for k in ("in", "name") if k in auth}
    auth.clear()
    auth["type"] = new_type
    if new_type not in ("BEARER", "BASIC", "OAUTH2", "OAUTH", "NONE"):
        auth.update(placement)
    auth["credential_ref"] = credential_ref
    await factory.mcp_repo.update_mcp_auth(mcp_id, auth)

    await factory.audit_repo.log_event({
        "event_type": "MCP_CREDENTIALS_SET",
        "actor_id": user.user_id, "actor_type": "USER",
        "resource_id": mcp_id,
        "details": {"auth_type": auth["type"]},
    })

    return {"mcp_id": mcp_id, "credential_ref": credential_ref, "auth_type": auth["type"]}


@router.get("/{mcp_id}/health")
async def get_health(
    mcp_id: str, request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Get integration health and circuit breaker status."""
    factory = _get_factory(request)
    mcp = await factory.mcp_repo.get_mcp(mcp_id)
    if not mcp or (mcp.get("owner") not in (user.user_id, "system") and not user.is_admin()):
        raise HTTPException(status_code=404, detail="Integration not found")

    return {
        "mcp_id": mcp_id,
        "health": mcp.get("health", "UNKNOWN"),
        "health_updated_at": mcp.get("health_updated_at"),
        "circuit_breaker": circuit_breaker.get_status(mcp_id),
    }


@router.post("/{mcp_id}/enable")
async def enable_integration(
    mcp_id: str, request: Request,
    user: AuthenticatedUser = Depends(require_not_viewer),
):
    """Enable an integration."""
    factory = _get_factory(request)
    mcp = await factory.mcp_repo.get_mcp(mcp_id)
    if not mcp or (mcp.get("owner") not in (user.user_id, "system") and not user.is_admin()):
        raise HTTPException(status_code=404, detail="Integration not found")
    await factory.mcp_repo.set_mcp_enabled(mcp_id, True)
    return {"mcp_id": mcp_id, "is_enabled": True}


@router.post("/{mcp_id}/disable")
async def disable_integration(
    mcp_id: str, request: Request,
    user: AuthenticatedUser = Depends(require_not_viewer),
):
    """Disable an integration."""
    factory = _get_factory(request)
    mcp = await factory.mcp_repo.get_mcp(mcp_id)
    if not mcp or (mcp.get("owner") not in (user.user_id, "system") and not user.is_admin()):
        raise HTTPException(status_code=404, detail="Integration not found")
    await factory.mcp_repo.set_mcp_enabled(mcp_id, False)
    return {"mcp_id": mcp_id, "is_enabled": False}


@router.delete("/{mcp_id}", status_code=status.HTTP_200_OK)
async def delete_integration(
    mcp_id: str, request: Request,
    user: AuthenticatedUser = Depends(require_not_viewer),
):
    """Delete an integration and its cached tools."""
    factory = _get_factory(request)
    mcp = await factory.mcp_repo.get_mcp(mcp_id)
    if not mcp or (mcp.get("owner") not in (user.user_id, "system") and not user.is_admin()):
        raise HTTPException(status_code=404, detail="Integration not found")
    deleted = await factory.mcp_repo.delete_mcp(mcp_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Integration not found")

    await factory.audit_repo.log_event({
        "event_type": "MCP_DELETED",
        "actor_id": user.user_id, "actor_type": "USER",
        "resource_id": mcp_id,
        "details": {},
    })

    return {"mcp_id": mcp_id, "deleted": True}


@router.get('/builds/{build_id}/events')
async def stream_build_events(build_id: str, request: Request,
                              user: AuthenticatedUser = Depends(get_current_user)):
    """Stream persisted build state; reconnects recover the latest status."""
    import asyncio
    import json
    from fastapi.responses import StreamingResponse
    factory = _get_factory(request)
    build = await factory.mcp_repo.get_build(build_id)
    if not build or (build.get('user_id') != user.user_id and not user.is_admin()):
        raise HTTPException(status_code=404, detail='Build not found')

    async def events():
        previous = None
        while not await request.is_disconnected():
            current = await factory.mcp_repo.get_build(build_id)
            if not current:
                return
            payload = json.dumps(current, default=str)
            if payload != previous:
                yield f'event: build\ndata: {payload}\n\n'
                previous = payload
            else:
                yield ': heartbeat\n\n'
            if current.get('status') in ('success', 'error'):
                return
            await asyncio.sleep(1)
    return StreamingResponse(events(), media_type='text/event-stream',
                             headers={'Cache-Control':'no-cache', 'X-Accel-Buffering':'no'})


@router.get('/{mcp_id}/export')
async def export_integration(mcp_id: str, request: Request,
                             user: AuthenticatedUser = Depends(get_current_user)):
    from fastapi.responses import Response
    from backend.mcp.builder.portable_server import export_server
    factory = _get_factory(request)
    manifest = await factory.mcp_repo.get_mcp(mcp_id)
    if not manifest or (manifest.get('owner') not in (user.user_id, 'system') and not user.is_admin()):
        raise HTTPException(status_code=404, detail='Integration not found')
    tools = await factory.mcp_repo.get_cached_tools(mcp_id)
    try:
        archive = export_server(manifest, tools)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(archive, media_type='application/zip', headers={'Content-Disposition':'attachment; filename="generated-mcp.zip"'})

# Immutable definition history. Credentials are not included in revision responses.
@router.get('/{mcp_id}/revisions')
async def list_connector_revisions(mcp_id: str, request: Request,
                                   user: AuthenticatedUser = Depends(get_current_user)):
    factory = _get_factory(request)
    mcp = await factory.mcp_repo.get_mcp(mcp_id)
    if not mcp or (mcp.get('owner') not in (user.user_id, 'system') and not user.is_admin()):
        raise HTTPException(status_code=404, detail='Integration not found')
    revisions = await factory.mcp_repo.list_revisions(mcp_id)
    return {'revisions': [{'revision_id': r['revision_id'], 'created_at': r['created_at'],
                           'tool_count': len(r['tools']), 'version': r['manifest'].get('version')}
                          for r in revisions]}


@router.post('/{mcp_id}/revisions', status_code=201)
async def checkpoint_connector(mcp_id: str, request: Request,
                               user: AuthenticatedUser = Depends(require_not_viewer)):
    factory = _get_factory(request)
    mcp = await factory.mcp_repo.get_mcp(mcp_id)
    if not mcp or (mcp.get('owner') != user.user_id and not user.is_admin()):
        raise HTTPException(status_code=404, detail='Integration not found')
    from backend.services.connector_revisions import checkpoint
    try:
        revision = await checkpoint(factory.mcp_repo, mcp_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await factory.audit_repo.log_event({'event_type': 'CONNECTOR_CHECKPOINT', 'actor_id': user.user_id,
                                       'actor_type': 'USER', 'resource_id': mcp_id,
                                       'details': {'revision_id': revision['revision_id']}})
    return {'revision_id': revision['revision_id']}


@router.post('/{mcp_id}/revisions/{revision_id}/restore', status_code=201)
async def restore_connector_revision(mcp_id: str, revision_id: str, request: Request,
                                     user: AuthenticatedUser = Depends(require_not_viewer)):
    factory = _get_factory(request)
    mcp = await factory.mcp_repo.get_mcp(mcp_id)
    if not mcp or (mcp.get('owner') not in (user.user_id, 'system') and not user.is_admin()):
        raise HTTPException(status_code=404, detail='Integration not found')
    check_rate_limit(f'user:{user.user_id}', 'mcp_build')
    from backend.services.connector_revisions import restore_copy
    try:
        restored_id = await restore_copy(factory.mcp_repo, mcp_id, revision_id, user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await factory.audit_repo.log_event({'event_type': 'CONNECTOR_RESTORED', 'actor_id': user.user_id,
                                       'actor_type': 'USER', 'resource_id': restored_id,
                                       'details': {'source_mcp_id': mcp_id, 'revision_id': revision_id}})
    return {'mcp_id': restored_id, 'is_enabled': False,
            'message': 'Restored as a disabled copy. Reconnect credentials and test before enabling.'}
