from backend.models.mcp_schemas import MCPManifest, CachedToolDefinition, ToolPolicyResult
from backend.services.tool_validation import has_valid_read_probe

class ToolPolicy:
    def is_allowed(self, tool: CachedToolDefinition, mcp: MCPManifest, context: dict = None) -> ToolPolicyResult:
        if not mcp.is_enabled:
            return ToolPolicyResult(allowed=False, reason="MCP is disabled")
        if mcp.trust_tier != "verified":
            return ToolPolicyResult(allowed=False, reason="Connector revision requires validation")

        # Health is informational — intermittent upstream 5xx should not block catalog or execution.
        if tool.mcp_id != mcp.mcp_id:
            return ToolPolicyResult(allowed=False, reason="Tool does not belong to this MCP")

        if mcp.transport == "internal" and not has_valid_read_probe(
            tool.model_dump(mode="json"), mcp.spec_hash, mcp.auth.credential_ref
        ):
            return ToolPolicyResult(allowed=False, reason="Operation needs validation for this revision and credential")

        return ToolPolicyResult(allowed=True)
