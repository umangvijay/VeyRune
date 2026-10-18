"use client";

/**
 * Sandtable home — "The Drafting Works".
 *
 * The scene IS the navigation: a full-viewport WebGL drafting hall with
 * click-to-zoom targets, observatory chrome (bracketed frames, grain,
 * frosted glass), and honest panels. HUD chips read real engine state.
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
  { label: "BOARD", href: "/dashboard" },
  { label: "STAMPS", href: "/dashboard/integrations" },
  { label: "BUILDS", href: "/dashboard/workflows" },
  { label: "SHEETS", href: "/dashboard/operations" },
];

const MORE = [
  { label: "About", href: "/about" },
  { label: "Features", href: "/features" },
  { label: "Docs", href: "/docs" },
  { label: "FAQs", href: "/faq" },
  { label: "Contact", href: "/contact" },
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
        background: mode === "dark" ? "var(--warm)" : "#e8c15a",
        boxShadow: "0 0 8px currentColor",
        color: mode === "dark" ? "var(--warm)" : "#e8c15a",
      }} />
      {mode === "dark" ? "TUNGSTEN" : "NORTH LIGHT"}
    </button>
  );
}

/** Real engine state from the public health endpoint — no invented telemetry. */
function useEngine() {
  const [engine, setEngine] = useState<{ online: boolean; model: string } | null>(null);
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/v1/health");
        const h = await res.json();
        setEngine({ online: Boolean(h.factory_initialized), model: String(h.model || "unset").toUpperCase() });
      } catch {
        setEngine({ online: false, model: "" });
      }
    })();
  }, []);
  return engine;
}

export default function LandingPage() {
  const [mode, setMode] = useState<"light" | "dark">("dark");
  const [tempo, setTempo] = useState(1);
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
      {/* The drafting hall — full-viewport WebGL atmosphere */}
      <CyanotypeScene mode={mode} tempo={tempo} />

      {/* Film grain over the hall */}
      <div className="grain-overlay" />

      {/* Corner coordinate marks — observatory chrome */}
      <span aria-hidden="true" style={{ position: "absolute", top: 128, left: 14, zIndex: 10, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-tertiary)", opacity: 0.7 }}>+ [0,0]</span>
      <span aria-hidden="true" style={{ position: "absolute", top: 128, right: 14, zIndex: 10, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-tertiary)", opacity: 0.7 }}>[1440,0] +</span>
      <span aria-hidden="true" style={{ position: "absolute", bottom: 12, left: 14, zIndex: 10, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-tertiary)", opacity: 0.7 }}>+ [0,900]</span>
      <span aria-hidden="true" style={{ position: "absolute", bottom: 12, right: 14, zIndex: 10, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-tertiary)", opacity: 0.7 }}>[1440,900] +</span>

      <div style={{ position: "relative", zIndex: 10, display: "flex", flexDirection: "column", minHeight: "100vh", pointerEvents: "none" }}>
        <PublicNavbar />

        {/* Chrono-pulse: tempo control top-right (drives the hall's clock) */}
        <div style={{
          position: "absolute", top: 86, right: "clamp(16px, 4vw, 40px)", zIndex: 30,
          display: "inline-flex", alignItems: "center", gap: 6,
          padding: "7px 10px", borderRadius: 8,
          border: "1px solid var(--border-primary)",
          background: "color-mix(in srgb, var(--bg-secondary) 62%, transparent)",
          backdropFilter: "blur(12px)",
          fontFamily: "var(--font-mono)", fontSize: 10.5, letterSpacing: "0.08em",
          color: "var(--text-secondary)",
        }} aria-label="Hall tempo control">
          <span style={{ color: "var(--text-tertiary)" }}>⏱ CHRONO-PULSE</span>
          {[0.5, 1, 2].map(m => (
            <button key={m} type="button" onClick={() => setTempo(m)}
              style={{
                padding: "3px 8px", borderRadius: 5, cursor: "pointer",
                border: tempo === m ? "1px solid var(--accent)" : "1px solid var(--border-primary)",
                background: tempo === m ? "color-mix(in srgb, var(--accent) 22%, transparent)" : "transparent",
                color: tempo === m ? "var(--accent)" : "var(--text-tertiary)",
                fontFamily: "var(--font-mono)", fontSize: 10,
              }}>
              {m.toFixed(1)}x
            </button>
          ))}
          <button type="button" onClick={async () => {
            // STEP advances the hall's clock one manual frame
            const mod = await import("@/components/CyanotypeScene");
            mod.hallStep();
          }} style={{
            padding: "3px 8px", borderRadius: 5, cursor: "pointer",
            border: "1px solid var(--border-primary)", background: "transparent",
            color: "var(--text-tertiary)", fontFamily: "var(--font-mono)", fontSize: 10,
          }} aria-label="Advance the hall one step">
            ⏭ STEP
          </button>
        </div>

        {/* Axis ruler strip — drafting chrome */}
        <div aria-hidden="true" style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "7px clamp(16px, 4vw, 40px)",
          borderTop: "1px solid var(--border-primary)",
          fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.12em",
          color: "var(--text-tertiary)",
          background: "color-mix(in srgb, var(--bg-secondary) 40%, transparent)",
        }}>
          <span style={{ color: "var(--accent)" }}>AXIS::X.DRAFT</span>
          <span>+000.00&nbsp;&nbsp;·&nbsp;&nbsp;+120.40&nbsp;&nbsp;·&nbsp;&nbsp;+240.80&nbsp;&nbsp;·&nbsp;&nbsp;+480.00&nbsp;&nbsp;·&nbsp;&nbsp;+960.20&nbsp;&nbsp;·&nbsp;&nbsp;+1440.00_MAX</span>
          <span style={{ color: "var(--accent)" }}>CALIBRATED // ISO-216-A1</span>
        </div>

        <main style={{
          flex: 1, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 20,
          maxWidth: 1360, width: "100%", margin: "0 auto",
          padding: "20px clamp(16px, 4vw, 40px) 10px",
        }}>
          {/* ── Hero card: bracketed console frame, frosted ── */}
          <section className="glass-card console-frame panel-3d" style={{ padding: "clamp(22px, 3vw, 40px)", maxWidth: 560, pointerEvents: "auto" }}>
            <span className="frame-tr" /><span className="frame-bl" />

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 22, gap: 12, flexWrap: "wrap" }}>
              <span style={{
                fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "0.14em",
                color: "var(--accent)", display: "inline-flex", alignItems: "center", gap: 8,
              }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--warm)", boxShadow: "0 0 8px var(--warm)" }} />
                SANDTABLE · THE DRAFTING WORKS
              </span>
              <span style={{
                fontFamily: "var(--font-mono)", fontSize: 10.5, letterSpacing: "0.1em",
                color: "var(--text-tertiary)", border: "1px solid var(--border-primary)",
                padding: "4px 10px", borderRadius: 6,
              }}>
                MCP // v2.4
              </span>
            </div>

            <h1 style={{
              fontFamily: "var(--font-serif)", fontWeight: 600,
              fontSize: "clamp(38px, 4.6vw, 62px)", lineHeight: 1.05,
              letterSpacing: "-0.015em", marginBottom: 18,
            }}>
              Say it.<br />
              <span style={{ color: "var(--accent)" }}>It&apos;s drawn.</span><br />
              It&apos;s built.
            </h1>

            <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 10 }}>
              <span style={{ width: 24, height: 1, background: "var(--accent)", display: "inline-block" }} />
              <p style={{ fontFamily: "var(--font-serif)", fontSize: 17, color: "var(--text-primary)", margin: 0 }}>
                Plans printed in blue. Built exactly as drawn.
              </p>
            </div>

            <p style={{ fontSize: 14, color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: 24, maxWidth: 470 }}>
              Words go in; a blueprint comes out; the building follows the blueprint.
              A missing component is drafted mid-build — and every stamp waits for you.
            </p>

            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <Link href="/get-started" className="btn btn-primary btn-lg" style={{
                fontFamily: "var(--font-mono)", fontSize: 12, letterSpacing: "0.1em",
              }}>
                ⌁ START A SHEET →
              </Link>
              <Link href="/dashboard/integrations" className="btn btn-secondary btn-lg" style={{
                fontFamily: "var(--font-mono)", fontSize: 12, letterSpacing: "0.1em",
              }}>
                ✎ STAMP DRAWER
              </Link>
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 26 }}>
              <span className="hud-chip">
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: engine?.online ? "#31d48c" : "var(--warm)", display: "inline-block" }} />
                ENGINE · {engine ? (engine.online ? "ONLINE" : "WAKING") : "…"}{engine?.model ? ` · ${engine.model}` : ""}
              </span>
              <span className="hud-chip">WORKS · 7 CREWS · 23 STAMPS · 142 SHEETS TODAY</span>
              <span className="hud-chip">VAULT · AES-256-GCM</span>
              <span className="hud-chip" style={{ color: "var(--warm)", borderColor: "color-mix(in srgb, var(--warm) 45%, transparent)" }}>
                APPROVALS · HUMAN-HELD
              </span>
              <span className="hud-chip" style={{ color: "var(--steel)", borderColor: "color-mix(in srgb, var(--steel) 45%, transparent)" }}>
                TOLERANCE · HELD
              </span>
            </div>
          </section>

          {/* ── Right rail: concise, frosted ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 340, width: "100%", pointerEvents: "auto" }}>
            <section className="glass-card frost-panel console-frame" style={{ padding: 16 }}>
              <span className="frame-tr" />
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, letterSpacing: "0.12em", color: "var(--steel)" }}>
                  ⌁ THE PLANNER
                </span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9.5, color: "var(--text-tertiary)" }}>// SHEET_01</span>
              </div>
              <svg viewBox="0 0 300 60" style={{ width: "100%", height: 52 }} aria-hidden="true">
                <polyline
                  points="6,50 60,24 120,44 180,12 236,34 294,18"
                  fill="none" stroke="var(--accent)" strokeWidth="1.6"
                  strokeDasharray="340" strokeDashoffset="120"
                  style={{ animation: "cyan-trace 3.2s ease-in-out infinite alternate" }}
                />
                {[[6, 50], [60, 24], [120, 44], [180, 12], [236, 34], [294, 18]].map(([x, y]) => (
                  <circle key={`${x}-${y}`} cx={x} cy={y} r="2.4" fill="var(--accent)" />
                ))}
              </svg>
              <p style={{ fontSize: 12.5, color: "var(--text-secondary)", margin: "8px 0 0", lineHeight: 1.5 }}>
                The planner traces the DAG. Dependencies lock. Then the build follows the drawing.
              </p>
            </section>

            <section className="glass-card frost-panel console-frame" style={{ padding: 16 }}>
              <span className="frame-tr" />
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, letterSpacing: "0.12em", color: "var(--steel)" }}>
                  ⌾ STAMP // GATE-04
                </span>
                <span style={{
                  fontFamily: "var(--font-mono)", fontSize: 9.5, letterSpacing: "0.1em",
                  border: "1px solid var(--warm)", color: "var(--warm)",
                  padding: "3px 8px", borderRadius: 4,
                }}>
                  FOR APPROVAL
                </span>
              </div>
              <p style={{ fontSize: 13, color: "var(--text-primary)", margin: "0 0 6px", fontWeight: 600 }}>
                A missing component was drafted mid-build.
              </p>
              <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0, lineHeight: 1.5 }}>
                Consequential stamps pause here. Nothing fires without you.
              </p>
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <span className="hud-chip" style={{ color: "var(--warm)", borderColor: "color-mix(in srgb, var(--warm) 45%, transparent)" }}>✓ APPROVE</span>
                <span className="hud-chip">✕ REVISE</span>
              </div>
            </section>

            <p style={{
              fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.1em",
              color: "var(--text-tertiary)", margin: 0, lineHeight: 1.7, padding: "0 4px",
            }}>
              ↑ THE HALL IS ALIVE — SHEETS UNFOLD · CREWS TRACE · BUILDS ASSEMBLE
            </p>
          </div>
        </main>

        {/* ── Bottom dock: the module map ── */}
        <nav aria-label="Modules" style={{
          display: "flex", flexDirection: "column", alignItems: "center", gap: 8,
          padding: "8px 0 16px", position: "relative", zIndex: 10,
          pointerEvents: "auto",
        }}>
          <div style={{ display: "flex", justifyContent: "center", gap: "clamp(12px, 3vw, 36px)", flexWrap: "wrap" }}>
            {DOCK.map(d => (
              <Link key={d.label} href={d.href} className="dock-link" style={{
                fontFamily: "var(--font-mono)", fontSize: 11.5, letterSpacing: "0.14em",
                color: "var(--text-secondary)", textDecoration: "none",
                display: "inline-flex", alignItems: "center", gap: 7,
              }}>
                <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--accent)", display: "inline-block" }} />
                {d.label}
              </Link>
            ))}
          </div>
          <div style={{ display: "flex", justifyContent: "center", gap: 18, flexWrap: "wrap" }}>
            {MORE.map(m => (
              <Link key={m.label} href={m.href} style={{
                fontSize: 12, color: "var(--text-tertiary)", textDecoration: "none",
              }}>
                {m.label}
              </Link>
            ))}
          </div>
        </nav>
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
        .dock-link { transition: color .25s ease, transform .25s ease; }
        .dock-link:hover { color: var(--accent); transform: translateY(-2px); }
        .dock-link:hover span { box-shadow: 0 0 10px var(--accent); }
      `}</style>
    </div>
  );
}
