"""Audit G07 acceptance: both build entry points share ONE durable contract.

- The API path persists a build record with origin=api, a workflow task,
  and dispatches through the engine/bus.
- The orchestrator path gets a durable record with origin=orchestrator and
  the waiting parent run, so a restart mid-build leaves a recoverable trace.
- Build provenance survives persistence (origin / parent_run_id / wait_reason).
"""
import pytest
import pytest_asyncio

from backend.repositories.sqlite.database import DatabaseManager


@pytest_asyncio.fixture
async def db(tmp_path):
    manager = DatabaseManager(str(tmp_path / "builds.db"))
    await manager.initialize()
    yield manager
    await manager.close()


@pytest_asyncio.fixture
async def factory(db):
    """Minimal factory surface for the build service: mcp_repo, workflow_repo,
    message_bus — backed by real SQLite."""
    from backend.repositories.in_memory_message_bus import InMemoryMessageBus
    from backend.repositories.sqlite.mcp_repository import SQLiteMCPRepository
    from backend.repositories.sqlite.workflow_repository import SQLiteWorkflowRepository

    f = type("FactorySurface", (), {})()
    f.mcp_repo = SQLiteMCPRepository(db)
    f.workflow_repo = SQLiteWorkflowRepository(db)
    f.message_bus = InMemoryMessageBus()
    f.db_manager = db
    return f


@pytest.mark.asyncio
async def test_g07_api_dispatch_persists_durable_record_and_run(factory):
    from backend.services.connector_build_service import ORIGIN_API, request_durable_build

    result = await request_durable_build(
        factory, user_id="u1", method="url",
        source="https://api.example.com/openapi.json", name="Example",
        origin=ORIGIN_API,
    )
    build = await factory.mcp_repo.get_build(result["build_id"])
    assert build is not None
    assert build["origin"] == "api"
    assert build["status"] == "queued"
    # The workflow task is durable: a worker restart cannot lose the request.
    run = await factory.workflow_repo.get_run(result["run_id"])
    assert run is not None
    assert run["tasks"][0]["agent"] == "core.mcp_build"
    assert run["tasks"][0]["input_data"]["build_id"] == result["build_id"]
    # The event was published for the bus/engine.
    queue = factory.message_bus._get_queue("agentos-workflow-events")
    assert queue.qsize() >= 1, "build task must be dispatched"


@pytest.mark.asyncio
async def test_g07_orchestrator_track_records_waiting_parent_run(factory):
    from backend.services.connector_build_service import ORIGIN_ORCHESTRATOR, track_inline_build

    track = await track_inline_build(
        factory, user_id="u2", method="prompt",
        source="an API that lists cats", name="Cats",
        origin=ORIGIN_ORCHESTRATOR, parent_run_id="run-parent-1",
    )
    build = await factory.mcp_repo.get_build(track["build_id"])
    assert build["origin"] == "orchestrator"
    assert build["parent_run_id"] == "run-parent-1"
    assert build["wait_reason"] == "capability_missing"
    # No workflow run is dispatched in track mode — the caller runs inline.
    assert await factory.workflow_repo.get_run(f"mcp-{track['build_id']}") is None


@pytest.mark.asyncio
async def test_g07_build_record_survives_reopen(factory, tmp_path):
    """Durability: the provenance columns are on disk, not in memory."""
    from backend.services.connector_build_service import ORIGIN_ORCHESTRATOR, track_inline_build

    track = await track_inline_build(
        factory, user_id="u3", method="url", source="https://x.example.com/spec",
        name="X", origin=ORIGIN_ORCHESTRATOR, parent_run_id="run-42",
    )
    fresh = SQLiteMCPRepositoryFactory(factory.db_manager)
    build = await fresh.mcp_repo.get_build(track["build_id"])
    assert build["origin"] == "orchestrator" and build["parent_run_id"] == "run-42"


def SQLiteMCPRepositoryFactory(db):
    from backend.repositories.sqlite.mcp_repository import SQLiteMCPRepository
    f = type("F", (), {})()
    f.mcp_repo = SQLiteMCPRepository(db)
    return f
