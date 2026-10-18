"use client";

/**
 * Sandtable home — "The Drafting Works".
 *
 * One clean viewport: the CyanotypeScene WebGL drafting hall behind a glass
 * hero card (left) and two honest product panels (right). HUD chips show
 * real server state; the bottom dock is the module map. No fake telemetry.
 */

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import PublicNavbar from "@/components/PublicNavbar";
import { applyTheme, readThemePref, resolveTheme, watchSystemTheme, type ThemePref } from "@/lib/theme";

const CyanotypeScene = dynamic(() => import("@/components/CyanotypeScene"), {
  ssr: false,
  loading: () => <div style={{ position: "absolute", inset: 0, background: "#04060b" }} />,
});

const DOCK = [
  { label: "BOARD", href: "/dashboard", hint: "The drawing board — where goals become sheets" },
  { label: "STAMPS", href: "/dashboard/integrations", hint: "The stamp drawer — MCP registry" },
  { label: "BUILDS", href: "/dashboard/workflows", hint: "The builds — every run, kept" },
  { label: "SHEETS", href: "/dashboard/operations", hint: "The sheets — model board & metrics" },
];

function LampToggle() {
  const [mode, setMode] = useState<"light" | "dark">("dark");
  useEffect(() => {
    setMode(resolveTheme(readThemePref()));
    return watchSystemTheme();
  }, []);
  const toggle = useCallback(() => {
    const next: ThemePref = mode === "dark" ? "light" : "dark";
    applyTheme(next);
    setMode(next);
  }, [mode]);
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${mode === "dark" ? "North Light (day)" : "Tungsten (night)"}`}
      style={{
        display: "inline-flex", alignItems: "center", gap: 8,
        padding: "8px 14px", borderRadius: "var(--radius-md)",
        border: "1px solid var(--border-primary)",
        background: "var(--bg-glass)", color: "var(--text-secondary)",
        fontFamily: "var(--font-mono)", fontSize: 11.5, letterSpacing: "0.08em",
        cursor: "pointer",
      }}
    >
      <span style={{
        width: 7, height: 7, borderRadius: "50%",
        background: mode === "dark" ? "var(--accent)" : "#e8c15a",
        boxShadow: "0 0 8px currentColor",
        color: mode === "dark" ? "var(--accent)" : "#e8c15a",
      }} />
      {mode === "dark" ? "TUNGSTEN" : "NORTH LIGHT"}
    </button>
  );
}

/** Real engine state from the public health endpoint — no invented telemetry. */
function useEngine() {
  const [engine, setEngine] = useState<{ online: boolean; model: string; storage: string } | null>(null);
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/v1/health");
        const h = await res.json();
        setEngine({
          online: Boolean(h.factory_initialized),
          model: String(h.model || "unset").toUpperCase(),
          storage: String(h.storage || "").toUpperCase(),
        });
      } catch {
        setEngine({ online: false, model: "", storage: "" });
      }
    })();
  }, []);
  return engine;
}

export default function LandingPage() {
  const [mode, setMode] = useState<"light" | "dark">("dark");
  const engine = useEngine();

  useEffect(() => {
    setMode(resolveTheme(readThemePref()));
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (readThemePref() === "system") setMode(mq.matches ? "dark" : "light");
    };
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);

  return (
    <div style={{ position: "relative", minHeight: "100vh", overflow: "hidden" }}>
      {/* The drafting hall — full-viewport WebGL */}
      <CyanotypeScene mode={mode} />

      <div style={{ position: "relative", zIndex: 10, display: "flex", flexDirection: "column", minHeight: "100vh" }}>
        <PublicNavbar />

        <main style={{
          flex: 1, display: "grid", alignItems: "center", gap: 20,
          gridTemplateColumns: "minmax(0, 1fr)", maxWidth: 1360, width: "100%",
          margin: "0 auto", padding: "24px clamp(16px, 4vw, 40px) 12px",
          gridTemplateRows: "1fr auto",
        }}>
          <div style={{ display: "grid", gap: 20, alignItems: "center", gridTemplateColumns: "minmax(0,1fr)" }} className="hero-grid">
            {/* ── Hero card ── */}
            <section
              className="glass-card panel-3d"
              style={{ padding: "clamp(24px, 3.4vw, 44px)", maxWidth: 640 }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 26, gap: 12, flexWrap: "wrap" }}>
                <span style={{
                  fontFamily: "var(--font-mono)", fontSize: 11.5, letterSpacing: "0.14em",
                  color: "var(--accent)", display: "inline-flex", alignItems: "center", gap: 8,
                }}>
                  <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--accent)", boxShadow: "0 0 8px var(--accent)" }} />
                  SANDTABLE · THE DRAFTING WORKS
                </span>
                <span style={{
                  fontFamily: "var(--font-mono)", fontSize: 10.5, letterSpacing: "0.1em",
                  color: "var(--text-tertiary)", border: "1px solid var(--border-primary)",
                  padding: "4px 10px", borderRadius: 6,
                }}>
                  MCP TOOL ENGINE // v2.4
                </span>
              </div>

              <h1 style={{
                fontFamily: "var(--font-serif)", fontWeight: 600,
                fontSize: "clamp(40px, 5.2vw, 68px)", lineHeight: 1.04,
                letterSpacing: "-0.015em", marginBottom: 22,
              }}>
                Say it.<br />
                <span style={{ color: "var(--accent)" }}>It&apos;s drawn.</span><br />
                It&apos;s built.
              </h1>

              <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 14 }}>
                <span style={{ width: 28, height: 1, background: "var(--accent)", display: "inline-block" }} />
                <p style={{ fontFamily: "var(--font-serif)", fontSize: "clamp(17px, 1.6vw, 20px)", color: "var(--text-primary)", margin: 0 }}>
                  Plans printed in blue. Built exactly as drawn.
                </p>
              </div>

              <p style={{ fontSize: 15.5, color: "var(--text-secondary)", lineHeight: 1.65, marginBottom: 30, maxWidth: 520 }}>
                Describe the outcome. The planner prints the blueprint, light crews build exactly
                what&apos;s drawn, and a missing component is drafted and fabricated mid-build —
                every stamp waits for you.
              </p>

              <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" }}>
                <Link href="/get-started" className="btn btn-primary btn-lg" style={{
                  fontFamily: "var(--font-mono)", fontSize: 13, letterSpacing: "0.1em",
                  display: "inline-flex", alignItems: "center", gap: 10,
                }}>
                  ⌁ START A SHEET →
                </Link>
                <Link href="/dashboard/integrations" className="btn btn-secondary btn-lg" style={{
                  fontFamily: "var(--font-mono)", fontSize: 13, letterSpacing: "0.1em",
                  display: "inline-flex", alignItems: "center", gap: 10,
                }}>
                  ✎ OPEN THE STAMP DRAWER
                </Link>
              </div>

              {/* HUD chips — real engine state */}
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 34 }}>
                <span className="hud-chip">
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: engine?.online ? "#31d48c" : "#e8c15a", display: "inline-block" }} />
                  ENGINE · {engine ? (engine.online ? "ONLINE" : "WAKING") : "…"}{engine?.model ? ` · ${engine.model}` : ""}
                </span>
                <span className="hud-chip">VAULT · AES-256-GCM</span>
                <span className="hud-chip">APPROVALS · HUMAN-HELD</span>
              </div>
            </section>

            {/* ── Right rail: honest product panels ── */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <section className="glass-card" style={{ padding: 20 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "0.12em", color: "var(--steel)" }}>
                    ⌁ THE PLANNER // LIGHT CREWS
                  </span>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-tertiary)" }}>// SHEET_01</span>
                </div>
                <svg viewBox="0 0 300 80" style={{ width: "100%", height: 72 }} aria-hidden="true">
                  <polyline
                    points="6,66 60,30 120,52 180,14 236,40 294,20"
                    fill="none" stroke="var(--accent)" strokeWidth="1.6"
                    strokeDasharray="340" strokeDashoffset="120"
                    style={{ animation: "cyan-trace 3.2s ease-in-out infinite alternate" }}
                  />
                  {[[6, 66], [60, 30], [120, 52], [180, 14], [236, 40], [294, 20]].map(([x, y]) => (
                    <circle key={`${x}-${y}`} cx={x} cy={y} r="2.6" fill="var(--accent)" />
                  ))}
                  <polyline
                    points="6,70 90,58 160,64 240,50 294,58"
                    fill="none" stroke="var(--text-tertiary)" strokeWidth="1"
                    strokeDasharray="3 5" opacity="0.6"
                  />
                </svg>
                <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "10px 0 0", lineHeight: 1.55 }}>
                  A goal becomes a sheet: the planner traces the DAG, dependencies lock,
                  and every step is drafted before it is built.
                </p>
              </section>

              <section className="glass-card" style={{ padding: 20 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "0.12em", color: "var(--steel)" }}>
                    ⌾ STAMP STATUS // GATE-04
                  </span>
                  <span style={{
                    fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.1em",
                    border: "1px solid var(--accent)", color: "var(--accent)",
                    padding: "3px 8px", borderRadius: 4,
                  }}>
                    FOR APPROVAL
                  </span>
                </div>
                <p style={{ fontSize: 13.5, color: "var(--text-primary)", margin: "0 0 8px", fontWeight: 600 }}>
                  WritePermission_PostgresSchema
                </p>
                <p style={{ fontSize: 12.5, color: "var(--text-secondary)", margin: 0, lineHeight: 1.55 }}>
                  A missing component was drafted mid-build. Consequential stamps pause
                  here — approve, revise, or reject. Nothing fires without you.
                </p>
                <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
                  <span className="hud-chip" style={{ color: "var(--accent)", borderColor: "var(--accent)" }}>✓ STAMP (APPROVE)</span>
                  <span className="hud-chip">✕ REVISE</span>
                </div>
              </section>
            </div>
          </div>

          {/* ── Bottom dock: the module map ── */}
          <nav aria-label="Modules" style={{
            display: "flex", justifyContent: "center", gap: "clamp(12px, 3vw, 36px)",
            flexWrap: "wrap", padding: "10px 0 18px",
          }}>
            {DOCK.map(d => (
              <Link key={d.label} href={d.href} title={d.hint} style={{
                fontFamily: "var(--font-mono)", fontSize: 11.5, letterSpacing: "0.14em",
                color: "var(--text-secondary)", textDecoration: "none",
                display: "inline-flex", alignItems: "center", gap: 7,
              }}>
                <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--accent)", display: "inline-block" }} />
                {d.label}
              </Link>
            ))}
          </nav>
        </main>
      </div>

      <style jsx global>{`
        .hud-chip {
          display: inline-flex; align-items: center; gap: 8px;
          font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 0.1em;
          color: var(--text-secondary);
          border: 1px solid var(--border-primary);
          background: var(--bg-glass);
          padding: 6px 12px; border-radius: 6px;
        }
        @keyframes cyan-trace {
          from { stroke-dashoffset: 340; }
          to   { stroke-dashoffset: 0; }
        }
      `}</style>
    </div>
  );
}
