from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.api.routers.integrations import _start_build


@pytest.mark.asyncio
async def test_mcp_build_is_persisted_as_worker_task():
    workflow_repo = SimpleNamespace(save_run=AsyncMock())
    mcp_repo = SimpleNamespace(create_build=AsyncMock(), update_build=AsyncMock())
    message_bus = SimpleNamespace(publish=AsyncMock())
    factory = SimpleNamespace(
        mcp_repo=mcp_repo,
        workflow_repo=workflow_repo,
        message_bus=message_bus,
    )
    engine = SimpleNamespace(evaluate_dag=AsyncMock())

    result = await _start_build(factory, "user-1", "prompt", "Build a public weather API connector", "Weather", engine)

    assert result["status"] == "queued"
    assert result["run_id"].startswith("mcp-")
    run = workflow_repo.save_run.await_args.args[0]
    task = run["tasks"][0]
    assert task["agent"] == "core.mcp_build"
    assert task["input_data"]["build_id"] == result["build_id"]
    assert task["input_data"]["intent"] == "Build a public weather API connector"
    engine.evaluate_dag.assert_awaited_once_with(result["run_id"])
    message_bus.publish.assert_not_awaited()
