"""Immutable connector definitions. Restores create disabled, credential-free copies."""
import hashlib
import json
import uuid
from datetime import datetime, timezone

MANIFEST_FIELDS = ('name', 'description', 'version', 'transport', 'source_type',
                   'spec_json', 'spec_hash', 'spec_version', 'source_uri')
TOOL_FIELDS = ('tool_name', 'name', 'description', 'input_schema', 'inputSchema',
               'operation', 'risk_level')


async def checkpoint(repo, mcp_id):
    manifest = await repo.get_mcp(mcp_id)
    if not manifest:
        raise ValueError('Connector not found')
    if manifest.get('transport') != 'internal':
        raise ValueError('Revision restore currently supports internal connectors only')
    tools = await repo.get_cached_tools(mcp_id=mcp_id)
    definition = {
        'manifest': {k: manifest[k] for k in MANIFEST_FIELDS if k in manifest},
        'tools': [{k: t[k] for k in TOOL_FIELDS if k in t} for t in tools],
    }
    encoded = json.dumps(definition, sort_keys=True, default=str)
    if len(encoded.encode()) > 800_000:
        raise ValueError('Connector definition exceeds revision storage limit')
    revision = {**definition, 'revision_id': hashlib.sha256(encoded.encode()).hexdigest(),
                'created_at': datetime.now(timezone.utc).isoformat()}
    await repo.save_revision(mcp_id, revision)
    return revision


async def restore_copy(repo, mcp_id, revision_id, owner):
    revision = await repo.get_revision(mcp_id, revision_id)
    if not revision:
        raise ValueError('Revision not found')
    new_id = str(uuid.uuid4())
    manifest = {
        **revision['manifest'], 'mcp_id': new_id, 'owner': owner,
        'name': revision['manifest']['name'] + ' (restored)',
        'endpoint': f'internal://openapi/{new_id}',
        'is_enabled': False, 'state': 'DRAFT', 'health': 'UNKNOWN',
        'trust_tier': 'pending_review', 'auth': {'type': 'NONE'},
    }
    tools = [{**tool, 'mcp_id': new_id, 'mcp_version': revision_id} for tool in revision['tools']]
    await repo.register_mcp(manifest)
    try:
        await repo.cache_tools(new_id, tools)
        await checkpoint(repo, new_id)
    except Exception:
        await repo.delete_mcp(new_id)
        raise
    return new_id
