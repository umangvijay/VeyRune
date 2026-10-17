"""
AgentOS — Memory Router

POST /api/v1/memory             — Add a memory entry
GET  /api/v1/memory             — List memory entries
POST /api/v1/memory/search      — Semantic search
DELETE /api/v1/memory/{id}      — Delete a memory entry
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, Request, Depends, status
from pydantic import BaseModel, Field
from typing import Optional, List

from backend.api.dependencies.auth import get_current_user, AuthenticatedUser, require_not_viewer
from backend.security.input_sanitizer import sanitize_text, InputValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])

ALLOWED_MEMORY_TYPES = {"profile", "workflow", "semantic"}


def _get_factory(request: Request):
    factory = getattr(request.app.state, "factory", None)
    if not factory:
        raise HTTPException(status_code=500, detail="Server not initialized")
    return factory


class AddMemoryRequest(BaseModel):
    content: str
    memory_type: str = "semantic"   # "profile" | "workflow" | "semantic"
    tags: Optional[List[str]] = None
    metadata: Optional[dict] = None

class SearchMemoryRequest(BaseModel):
    query: str
    memory_type: Optional[str] = None
    limit: int = Field(default=10, ge=1, le=100)


def _validate_memory_type(memory_type: Optional[str]) -> Optional[str]:
    if memory_type is None:
        return None
    if memory_type not in ALLOWED_MEMORY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"memory_type must be one of {sorted(ALLOWED_MEMORY_TYPES)}",
        )
    return memory_type


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_memory(
    body: AddMemoryRequest, request: Request,
    user: AuthenticatedUser = Depends(require_not_viewer),
):
    """Add a memory entry with optional embedding."""
    factory = _get_factory(request)
    memory_type = _validate_memory_type(body.memory_type)

    try:
        content = sanitize_text(body.content, "content", max_length=10_000)
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)

    if not content.strip():
        raise HTTPException(status_code=422, detail="content cannot be empty")

    embedding = None
    try:
        from backend.services.embedding_service import GoogleCloudEmbeddingService
        embedding = await asyncio.to_thread(GoogleCloudEmbeddingService().embed_text, content)
    except Exception as e:
        logger.exception("Embedding generation failed")
        # Preserve content and report degraded retrieval honestly.
        embedding = None

    metadata = dict(body.metadata or {})
    if body.tags:
        metadata["tags"] = body.tags
    try:
        memory_id = await factory.memory_repo.store_memory(
            user_id=user.user_id,
            content=content,
            memory_type=memory_type,
            metadata=metadata,
            embedding=embedding or [],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("store_memory failed")
        raise HTTPException(
            status_code=500,
            detail=f"Could not store the memory entry on this storage backend: {type(e).__name__}",
        ) from e

    return {"memory_id": memory_id, "embedded": embedding is not None}


@router.get("")
async def list_memories(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    memory_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List memory entries for the current user."""
    factory = _get_factory(request)
    _validate_memory_type(memory_type)
    lister = getattr(factory.memory_repo, "list_memories", None)
    if not callable(lister):
        raise HTTPException(
            status_code=500,
            detail="Memory listing is not available on this storage backend.",
        )
    try:
        memories = await lister(
            user_id=user.user_id,
            memory_type=memory_type,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.exception("list_memories failed")
        raise HTTPException(status_code=500, detail="Could not list memories") from e
    return {"memories": memories, "count": len(memories)}


@router.post("/search")
async def search_memory(
    body: SearchMemoryRequest, request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Semantic search over memory using embeddings."""
    factory = _get_factory(request)
    _validate_memory_type(body.memory_type)

    try:
        query = sanitize_text(body.query, "query", max_length=2000)
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)

    from backend.services.memory_search import keyword_search
    try:
        from backend.services.embedding_service import GoogleCloudEmbeddingService
        query_embedding = await asyncio.to_thread(GoogleCloudEmbeddingService().embed_text, query)
        results = await factory.memory_repo.search_memory(
            user_id=user.user_id, query_embedding=query_embedding,
            memory_type=body.memory_type, limit=body.limit,
        )
        mode = "semantic"
    except Exception:
        logger.warning("Semantic memory unavailable; using keyword retrieval", exc_info=True)
        results = await keyword_search(factory.memory_repo, user.user_id, query, body.memory_type, body.limit)
        mode = "keyword"
    return {"results": results, "count": len(results), "retrieval_mode": mode}


@router.get("/search")
async def search_memory_get(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    q: str = Query(..., min_length=1, max_length=2000),
    memory_type: Optional[str] = None,
    limit: int = Query(10, ge=1, le=100),
):
    """GET-form of memory search — consistent with the rest of the GET surface.

    The POST form stays the canonical rich-search endpoint (embedding mode);
    this alias runs the same pipeline with query parameters."""
    body = SearchMemoryRequest(query=q, memory_type=memory_type, limit=limit)
    return await search_memory(body, request, user)


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str, request: Request,
    user: AuthenticatedUser = Depends(require_not_viewer),
):
    """Delete a memory entry."""
    factory = _get_factory(request)
    deleted = await factory.memory_repo.delete_memory(user.user_id, memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return {"memory_id": memory_id, "deleted": True}
