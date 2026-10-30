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
    existing = (tool.get("operation") or {}).get("_validation") or {}
    evidence = {"kind": "read_probe", "status": "passed", "digest": definition_digest(tool, spec_hash),
                "credential_ref": credential_ref, "tested_at": datetime.now(timezone.utc).isoformat(),
                # Provenance survives the probe: an operation's origin never
                # upgrades itself by being tested (audit G06).
                "provenance": existing.get("provenance", "official_spec")}
    return {**tool, "operation": {**(tool.get("operation") or {}), "_validation": evidence}}


def validation_provenance(tool: dict) -> str:
    """Where this operation's definition came from (audit G06): the official
    spec, documentation extraction, or a model-inferred sketch."""
    return ((tool.get("operation") or {}).get("_validation") or {}).get("provenance", "official_spec")


def coverage_from_tools(tools: list) -> dict:
    """Per-operation test coverage summary (audit G02). A passing probe is
    evidence for exactly one operation — never for the integration as a
    whole."""
    dumped = [t.model_dump(mode="json") if hasattr(t, "model_dump") else t for t in tools]
    def evidence_of(d: dict) -> dict:
        return (d.get("operation") or {}).get("_validation") or {}
    probed = sum(1 for d in dumped
                 if evidence_of(d).get("kind") == "read_probe" and evidence_of(d).get("status") == "passed")
    mutating_untested = sum(1 for d in dumped
                            if (d.get("operation") or {}).get("http_method") not in ("GET", "HEAD")
                            and evidence_of(d).get("status") != "passed")
    return {
        "total": len(dumped),
        "read_probe_passed": probed,
        "untested": len(dumped) - probed,
        "mutating_untested": mutating_untested,
    }


def coverage_from_tools(tools: list) -> dict:
    """Per-operation test coverage summary (audit G02). A passing probe is
    evidence for exactly one operation — never for the integration as a
    whole."""
    total = len(tools)
    probed = sum(1 for t in tools if has_valid_read_probe(t.model_dump(mode="json") if hasattr(t, "model_dump") else t, None)
                 or (((t.model_dump(mode="json") if hasattr(t, "model_dump") else t).get("operation") or {}).get("_validation") or {}).get("kind") == "read_probe"
                 and (((t.model_dump(mode="json") if hasattr(t, "model_dump") else t).get("operation") or {}).get("_validation") or {}).get("status") == "passed")
    mutating_untested = 0
    for t in tools:
        d = t.model_dump(mode="json") if hasattr(t, "model_dump") else t
        op = d.get("operation") or {}
        evidence = op.get("_validation") or {}
        if op.get("http_method") not in ("GET", "HEAD") and evidence.get("status") != "passed":
            mutating_untested += 1
    return {
        "total": total,
        "read_probe_passed": probed,
        "untested": total - probed,
        "mutating_untested": mutating_untested,
    }


def has_valid_read_probe(tool: dict, spec_hash: str | None, credential_ref=None) -> bool:
    op = tool.get("operation") or {}
    evidence = op.get("_validation") or {}
    return (op.get("http_method") in ("GET", "HEAD")
            and evidence.get("status") == "passed" and evidence.get("kind") == "read_probe"
            and evidence.get("credential_ref") == credential_ref
            and evidence.get("digest") == definition_digest(tool, spec_hash))
