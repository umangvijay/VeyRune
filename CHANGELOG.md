# Changelog

## v2.4.0 — 2026-10-18

### Organizations UI
- `/dashboard/orgs`: create orgs, add members by email, the role ladder
  inline (owner-immutable), remove members, and **run oversight** — a
  read-only view of member runs with scoped fields. Sidebar entry +
  2 e2e specs (14 e2e total). Visually verified in a real browser:
  the renamed brand, forge core, and both themes render correctly.


### Product renamed: Veyrune → **Yantrika**
- Sanskrit *yantra* — "machine/instrument" — the workspace that builds its
  own instruments. The historian tie: the 11th-century treatise
  *Samarāṅgaṇa-sūtradhāra* catalogs yantra automata. All user-facing
  surfaces renamed (117 replacements); repo/package identity stays AgentOS.

### 3D forge design system
- New design tokens: ember/steel identity, forge gradients, bevel + depth
  shadows; glass cards gain material thickness and a lit top bevel.
- `.panel-3d` perspective-tilt cards with specular sheen; metallic
  primary buttons with pressed depth.
- The **forge core**: a CSS-3D animated yantra (three counter-rotating
  rings around a molten core) in the home hero and via the new BrandMark
  (isometric yantra logo) in the sidebar, home footer, and auth.

### Theme: light / dark / system
- New resolver (`src/lib/theme.ts`): `system` follows the OS via
  prefers-color-scheme with live updates; first-paint script resolves
  before hydration; Settings gains the three-way selector.

### BYOK + token information
- New "Model & tokens" card on Settings: active provider + whose
  credential is in use (BYOK status), 5h rolling-window usage vs your
  daily budget with a progress bar and reset countdown.
- 3 new unit tests (theme resolver) — **11 unit tests** total.

## v2.2.0 — 2026-10-18

### Organizations (enterprise RBAC foundation)
- **Orgs + membership with a role ladder**: owner > admin > member > viewer.
  Create orgs, add members by email (anti-enumeration preserved — a missing
  email 404s without revealing account existence), change roles (owner only),
  remove members (owner-protected; admins manage members/viewers only).
- **Run oversight**: org admins/owners get a read-only view of member runs
  with scoped task fields (id, title, agent, status, error) — never full
  input/output payloads.
- Every membership change is audited (`ORG_*` events). Shared vaults and
  org-scoped workspaces remain the documented next steps.
- 9 new RBAC tests (201 backend total); full lifecycle verified live.

### v2.1.1
- Session-expiry regression tests (the deployed build's mid-action logout
  bug), guest-creation retry, model A/B ops guidance.

## v2.1.0 — 2026-10-17

Eight remediation-and-hardening rounds against the external audit
(`VEYRUNE_AUDIT_REPORT.md` rounds 3–10). 192 backend tests, 10 frontend
e2e tests, all three Docker images build and pass runtime smoke.

### P0 (audit-blocking)
- **Fixed invalid-JSON responses at the root**: lone UTF-16 surrogates in
  untrusted text (scraped HTML, PDF text, LLM output) crashed storage and
  corrupted responses. One canonical JSON layer (`SafeJSONResponse` on
  every response, safe SSE frames) plus surrogate repair at the input
  choke point. Property-tested with hostile payloads.
- **Server-side logout**: `token_denylist` store (SQLite + Firestore);
  a logged-out token 401s immediately instead of surviving its TTL.
- **Workflow rate limit** tightened to 10/min per user (quota-burn loophole).
- **OpenAPI relative server URLs** parse, resolve against the spec URL,
  and are SSRF-revalidated — petstore-style specs build again.
- **`GET /api/v1/health`** with version, baked commit SHA, uptime, and
  LLM credential status.

### Security & enterprise
- Per-user **API keys** (`vry_…`): hash-stored, shown once, individually
  revocable — stable auth for MCP clients and CI.
- **Daily token budget with a hard stop** on workflow creation, fed by
  usage recording at the LLM choke points (was dead code).
- **Outbound run webhooks**: HMAC-signed POSTs on run completion,
  SSRF-validated URL, Vault-configurable signing secret.
- **Data retention**: `RETENTION_DAYS` purge of events/audit rows (runs
  never auto-deleted).
- Rate limits on every state-changing surface; pagination guards
  everywhere; production CSP without `unsafe-inline` scripts.
- **Audit log**: API + admin Control Center UI.

### Product
- **Shared integration catalog**: publish verified integrations, browse,
  one-click per-user install (credentials never copied).
- **Self-evolving model routing**: UCB1 bandit re-ranks the model
  fallback chain from real task outcomes; leaderboard at
  `GET /api/v1/usage/models` and the Operations page.
- Task `title` + `started_at` populate end-to-end (timeline, DAG,
  details panel); details panel reports results as readable summaries.
- Schedules: run-now materializes the run synchronously (immediately
  observable), max-concurrency guard, skip-missed catch-up, missed-run
  notifications, `is_enabled` contract fixed.
- Chat replies report full health facts (status, latency, TLS expiry,
  grade, missing headers) instead of a bare status code.
- resume/scan: filename-safety, transient retry, honest error codes.

### Performance & ops
- `list_runs` N+1 eliminated: 6.0ms → 2.0ms p50 at 100 runs (3×).
- Memory writes under load: 5,835ms → 20.3ms p50 (embedding fail-fast
  with cooldown).
- Dockerfiles fixed for the unprivileged runtime user (file modes, JWT
  keys dir) — all three images build and pass runtime smoke.
- `scripts/gcp/deploy-safe.sh` (image-only deploys that preserve service
  config), `scripts/gcp/verify-p0-production.py` (14-check live P0
  verification), `docs/ops-runbook.md`, `.env.example`.

### Known scope boundaries
- Orgs/teams, Stripe billing, cross-instance rate limiting: product/
  deploy scope, documented in the audit report.
- Frontend CSP keeps `unsafe-inline` for scripts: marketing pages are
  statically prerendered, so per-request nonces are impossible (attempted
  and reverted with evidence in Round 8).
