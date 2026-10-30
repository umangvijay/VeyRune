"""Revision-bound evidence for declarative operations, never whole-app verification."""
import hashlib
import json
from datetime import datetime, timezone


def definition_digest(tool: dict, spec_hash: str | None) -> str:
    operation = {k: v for k, v in (tool.get("operation") or {}).items() if k != "_validation"}
    definition = {"operation": operation, "schema": tool.get("input_schema") or {},
                  "name": tool.get("tool_name"), "version": tool.get("mcp_version"),
                  "risk": tool.get("risk_level"), "spec_hash": spec_hash}
    return hashlib.sha256(json.dumps(definition, sort_keys=True, default=str).encode()).hexdigest()


def record_read_probe(tool: dict, spec_hash: str | None, credential_ref=None) -> dict:
    evidence = {"kind": "read_probe", "status": "passed", "digest": definition_digest(tool, spec_hash),
                "credential_ref": credential_ref, "tested_at": datetime.now(timezone.utc).isoformat()}
    return {**tool, "operation": {**(tool.get("operation") or {}), "_validation": evidence}}


def has_valid_read_probe(tool: dict, spec_hash: str | None, credential_ref=None) -> bool:
    op = tool.get("operation") or {}
    evidence = op.get("_validation") or {}
    return (op.get("http_method") in ("GET", "HEAD")
            and evidence.get("status") == "passed" and evidence.get("kind") == "read_probe"
            and evidence.get("credential_ref") == credential_ref
            and evidence.get("digest") == definition_digest(tool, spec_hash))
