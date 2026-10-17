"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getOperationsSummary, OperationsSummary, getModelLeaderboard, ModelLeaderboardRow } from "@/lib/api";

export default function OperationsPage() {
  const [data, setData] = useState<OperationsSummary | null>(null);
  const [leaderboard, setLeaderboard] = useState<ModelLeaderboardRow[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const load = useCallback(() => Promise.all([getOperationsSummary(), getModelLeaderboard()]).then(([result, board]) => {
    setData(result); setLeaderboard(board.models || []); setError("");
  }).catch((err: unknown) => {
    setError(err instanceof Error ? err.message : "Could not load run metrics");
  }).finally(() => setBusy(false)), []);
  useEffect(() => { void load(); }, [load]);
  return <main style={{ maxWidth: 1000, margin: "0 auto" }}>
    <header style={{ display: "flex", justifyContent: "space-between", gap: 20, marginBottom: 24 }}>
      <div><h1>Operations</h1><p>Observed results from your recent workflows.</p></div>
      <button className="btn btn-secondary" disabled={busy} onClick={() => { setBusy(true); void load(); }}>{busy ? "Loading…" : "Refresh"}</button>
    </header>
    {error && <p role="alert">{error}</p>}
    {data && <>
      <p style={{ color: "var(--text-secondary)", marginBottom: 20 }}>Latest {data.sample_size} runs, up to {data.sample_limit}. Updated {new Date(data.generated_at).toLocaleString()}. Refresh to update.</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16 }}>
        {[["Completion rate", data.completion_rate === null ? "No finished runs" : `${data.completion_rate}%`],
          ["Median completion", data.median_completion_seconds === null ? "No timing data" : `${data.median_completion_seconds}s`],
          ["Est. spend (sample)", `$${(data.cost_tracking?.estimated_cost_usd ?? 0).toFixed(4)} · ${data.cost_tracking?.estimated_tokens?.toLocaleString() ?? 0} tok`],
          ["Needs attention", String(data.attention.length)]].map(([label, value]) =>
          <div className="glass-card" style={{ padding: 24 }} key={label}><p>{label}</p><strong style={{ fontSize: 24 }}>{value}</strong></div>)}
      </div>
      <p style={{ margin: "16px 0", color: "var(--text-secondary)" }}>Completion rate includes completed and failed runs. Long-running means more than 15 minutes since creation; it does not necessarily mean stuck. Spending is not measured here.</p>
      <section className="glass-card" style={{ padding: 24, marginBottom: 20 }}>
        <h2>Needs attention</h2>
        {!data.attention.length && <p>No flagged runs in this sample.</p>}
        {data.attention.map(run => <div key={run.run_id} style={{ display: "flex", justifyContent: "space-between", padding: "12px 0", gap: 16 }}>
          <span>{run.reason === "approval_required" ? "Awaiting your approval" : run.reason === "failed" ? "Run failed" : "Long-running workflow"}</span>
          <Link href={`/dashboard/workflows/${encodeURIComponent(run.run_id)}`} className="btn btn-secondary">Inspect run</Link>
        </div>)}
      </section>
      <section className="glass-card" style={{ padding: 24 }}><h2>Failed tasks by agent</h2>
        {!Object.keys(data.failed_tasks_by_agent).length && <p>No failed tasks in this sample.</p>}
        {Object.entries(data.failed_tasks_by_agent).map(([agent, count]) => <p key={agent}>{agent}: {count}</p>)}
      </section>
    </>}
  {leaderboard && leaderboard.length > 0 && (
      <section style={{ marginTop: 28 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>Model leaderboard</h2>
        <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
          Learned by the adaptive routing policy from real task outcomes (UCB1 + 10% exploration).
        </p>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text-tertiary)", fontSize: 12 }}>
                <th style={{ padding: "8px 12px 8px 0" }}>Model</th>
                <th style={{ padding: "8px 12px" }}>Attempts</th>
                <th style={{ padding: "8px 12px" }}>Success rate</th>
                <th style={{ padding: "8px 12px" }}>Avg latency</th>
                <th style={{ padding: "8px 12px" }}>Policy score</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map(row => (
                <tr key={row.model} style={{ borderTop: "1px solid var(--border-primary)" }}>
                  <td style={{ padding: "9px 12px 9px 0", fontFamily: "var(--font-mono)", fontSize: 12.5 }}>{row.model}</td>
                  <td style={{ padding: 12 }}>{row.attempts}</td>
                  <td style={{ padding: 12 }}>{row.success_rate === null ? "—" : `${Math.round(row.success_rate * 100)}%`}</td>
                  <td style={{ padding: 12 }}>{Math.round(row.ewma_latency_ms)} ms</td>
                  <td style={{ padding: 12 }}>{row.score.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    )}
  </main>
}
