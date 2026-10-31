/**
 * Explicit task/run states (audit §7 UX): one authoritative mapping from
 * engine states to human labels, badge classes, and colors — used by every
 * surface so "uncertain" and "waiting" are never rendered as generic.
 */
export type StateStyle = { label: string; badge: string; color: string; needsAttention: boolean };

const RUN_STATES: Record<string, StateStyle> = {
  QUEUED: { label: "Queued", badge: "badge-neutral", color: "var(--text-tertiary)", needsAttention: false },
  PENDING: { label: "Queued", badge: "badge-neutral", color: "var(--text-tertiary)", needsAttention: false },
  RUNNING: { label: "Running", badge: "badge-info", color: "var(--info)", needsAttention: false },
  WAITING_APPROVAL: { label: "Waiting for approval", badge: "badge-warn", color: "var(--warning)", needsAttention: true },
  WAITING_CREDENTIALS: { label: "Waiting for credentials", badge: "badge-warn", color: "var(--warning)", needsAttention: true },
  RECOVERING: { label: "Recovering", badge: "badge-info", color: "var(--info)", needsAttention: false },
  OUTCOME_UNCERTAIN: { label: "Outcome uncertain", badge: "badge-warn", color: "var(--warning)", needsAttention: true },
  COMPLETED: { label: "Completed", badge: "badge-success", color: "var(--success)", needsAttention: false },
  FAILED: { label: "Failed", badge: "badge-error", color: "var(--error)", needsAttention: true },
  CANCELLED: { label: "Cancelled", badge: "badge-neutral", color: "var(--text-tertiary)", needsAttention: false },
};

export function runStateStyle(status: string | undefined | null): StateStyle {
  return RUN_STATES[(status || "").toUpperCase()] || {
    label: status || "Unknown", badge: "badge-neutral", color: "var(--text-tertiary)", needsAttention: false,
  };
}

/** Connector lifecycle clarity (§7): separate generated / authenticated /
    tested / active instead of one broad badge. */
export function connectorStateBadges(integration: {
  trust_tier?: string; artifact_type?: string; is_enabled?: boolean;
  spec_provenance?: string; test_coverage?: { read_probe_passed?: number; total?: number };
}): Array<{ label: string; badge: string }> {
  const badges: Array<{ label: string; badge: string }> = [];
  badges.push({
    label: integration.artifact_type === "standalone_server" ? "standalone server" : "adapter",
    badge: "badge-neutral",
  });
  if ((integration.test_coverage?.read_probe_passed ?? 0) > 0) badges.push({ label: "tested", badge: "badge-info" });
  if (integration.trust_tier === "verified") badges.push({ label: "verified", badge: "badge-success" });
  else badges.push({ label: "needs review", badge: "badge-warn" });
  if (integration.is_enabled) badges.push({ label: "active", badge: "badge-success" });
  return badges;
}
