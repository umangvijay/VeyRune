"use client";

import { useEffect, useState } from "react";
import { getContextUsage } from "@/lib/api";

/**
 * Live "Model & tokens" status for the Settings page:
 * - Which LLM provider is active and whose credential it is using (BYOK)
 * - Context-window and rolling 5h-window token budget with a progress bar
 *   and reset countdown — the audit's token-information ask.
 */
export default function TokenStatusCard() {
  const [provider, setProvider] = useState<{ llm: string; status: string; detail: string } | null>(null);
  const [usage, setUsage] = useState<Awaited<ReturnType<typeof getContextUsage>> | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/v1/health");
        const h = await res.json();
        setProvider({
          llm: h.llm || "unset",
          status: h.llm_status?.status || "unknown",
          detail: h.llm_status?.detail || "",
        });
      } catch { /* health unreachable — leave status quiet */ }
      try {
        setUsage(await getContextUsage());
      } catch { /* usage endpoint unavailable */ }
    })();
  }, []);

  const used = Number(usage?.daily_used ?? 0);
  const limit = Number(usage?.daily_limit ?? 0);
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const resetsAt = usage?.window_resets_at ? new Date(usage.window_resets_at) : null;
  const minutesToReset = resetsAt ? Math.max(0, Math.round((resetsAt.getTime() - Date.now()) / 60000)) : null;

  const providerLabel: Record<string, string> = {
    gemini: "Gemini (AI Studio key)", vertex: "Google Vertex AI",
    groq: "Groq", huggingface: "Hugging Face", unset: "Not configured",
  };

  return (
    <div className="glass-card panel-3d" style={{ padding: 24, marginBottom: 24 }}>
      <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 14, borderBottom: "1px solid var(--border-primary)", paddingBottom: 12 }}>
        Model & tokens
      </h2>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16, marginBottom: 16 }}>
        <div style={{ padding: 14, borderRadius: "var(--radius-md)", background: "var(--bg-tertiary)", border: "1px solid var(--border-primary)" }}>
          <div style={{ fontSize: 12, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Active provider</div>
          <div style={{ fontSize: 15, fontWeight: 600 }}>{providerLabel[provider?.llm || ""] || (provider?.llm || "…")}</div>
          <div style={{ fontSize: 12.5, color: provider?.status === "catalog_ok" || provider?.status === "vertex" ? "var(--success, #22c55e)" : "var(--text-tertiary)", marginTop: 4 }}>
            {provider?.status === "catalog_ok" ? "Credential working"
              : provider?.status === "vertex" ? "Vertex credentials working"
              : provider?.status === "missing" ? "No credential on the server — add your own key below"
              : provider?.detail?.slice(0, 80) || "…"}
          </div>
        </div>
        <div style={{ padding: 14, borderRadius: "var(--radius-md)", background: "var(--bg-tertiary)", border: "1px solid var(--border-primary)" }}>
          <div style={{ fontSize: 12, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>5h rolling window</div>
          <div style={{ fontSize: 15, fontWeight: 600 }}>
            {Number(used || 0).toLocaleString()} <span style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>/ {Number(limit || 0).toLocaleString()} tokens</span>
          </div>
          <div style={{ fontSize: 12.5, color: "var(--text-tertiary)", marginTop: 4 }}>
            {minutesToReset !== null ? `resets in ~${minutesToReset} min` : "—"}
          </div>
        </div>
      </div>

      <div style={{ height: 8, borderRadius: 6, background: "var(--bg-tertiary)", overflow: "hidden", border: "1px solid var(--border-primary)" }}>
        <div style={{
          width: `${pct}%`, height: "100%",
          background: pct > 85 ? "var(--error, #ef4444)" : "var(--forge-grad)",
          borderRadius: 6, transition: "width .6s ease",
        }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-tertiary)", marginTop: 6 }}>
        <span>{pct}% of your daily token budget</span>
        <span>{usage && usage.remaining_tokens != null ? `${Number(usage.remaining_tokens).toLocaleString()} remaining` : ""}</span>
      </div>
    </div>
  );
}
