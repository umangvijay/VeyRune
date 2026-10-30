# Release Evidence Packet — Sandtable (AgentOS)

Audit baseline: *AgentOS / Sandtable — Full-stack audit & advancement plan v4.0* (30 Oct 2026).
This packet tracks the audit's required evidence, item by item, with the honest
status of each: **verified (local)** means implemented with regression tests that
run in this repository; **pending** means it requires resources this repository
cannot produce (a real deployment, provider accounts, or independent review).

A finding is *closed* only when its evidence line says so. A code change alone
does not close a finding.

---

## 1. Identity and authorization

| Evidence required | Status | Where |
|---|---|---|
| Disabled users receive no tokens via password login | **Verified (local)** — HTTP regression | `backend/tests/test_audit_security.py` |
| Disabled users receive no tokens via Google login | **Verified (local)** — route regression with mocked id_token verification | `backend/tests/test_audit_security.py` |
| Disabled/refresh paths enforce account status | **Verified (local)** | `backend/tests/test_auth_http.py` |
| Role changes take effect immediately (no stale claims) | **Verified (local)** | `backend/tests/test_auth_http.py`, `test_audit_security.py` |
| Revocation enforced; denylist outage fails closed (503) | **Verified (local)** | `backend/tests/test_audit_security.py` |
| Membership creation never mutates roles (router + repository, atomic) | **Verified (local)** | `backend/tests/test_audit_security.py` |
| Owner-only role-change holds on every path | **Verified (local)** + router guards | `backend/api/routers/orgs.py`, `test_orgs_rbac.py` |
| Accepted-invitation lifecycle (invite → accept) | **Pending** — first-batch scope excluded personal runs instead; invitation UX remains enterprise-stage work | — |
| SSO / MFA / provisioning | **Pending** (enterprise option) | — |

## 2. Tenant isolation

| Evidence required | Status | Where |
|---|---|---|
| Oversight excludes personal and other-org runs | **Verified (local)** — runs scoped to explicit `org_id` ownership; payload sanitization asserted | `backend/tests/test_audit_security.py` |
| Explicit organization ownership on shared resources | **Partially verified** — `WorkflowRun.org_id` ownership slice shipped; org-owned resources beyond runs (credentials, schedules, artifacts) remain user-scoped | `backend/models/schemas.py`, migration in `sqlite/database.py` |
| Cross-tenant isolation for memory/search/artifacts | **Pending** — needs the adversarial matrix run across every retrieval path | — |

## 3. Execution safety

| Evidence required | Status | Where |
|---|---|---|
| Expired RUNNING tasks reclaimable (Firestore parity) | **Verified by source + contract tests** — live kill-test requires cloud | `backend/repositories/firestore/workflow_repository.py`, `test_chaos_recovery.py` (SQLite path) |
| Duplicate delivery executes exactly once | **Verified (local)** — stack-level test | `backend/tests/test_chaos_recovery.py` |
| Old execution cannot overwrite a reclaimed task (fencing) | **Verified (local)** | `backend/tests/test_chaos_recovery.py` |
| Uncertain-outcome handling / provider idempotency receipts | **Pending** — ledger distinguishes states; provider-specific reconciliation requires real providers | `backend/engine/idempotency_guard.py` |
| Connector lifecycle: untested revisions cannot execute | **Verified (local)** — per-operation evidence + trust-tier gate | `backend/tests/test_connector_coverage.py`, `test_audit_security.py` (G01/G02) |
| Standalone server packaging never deployable without protocol tests | **Verified (local)** | `backend/tests/test_standalone_packaging.py` (G03) |
| Provenance labels (official/extracted/inferred) | **Verified (local)** | `backend/tests/test_connector_coverage.py` (G06) |
| Both build entry points share one durable record | **Verified (local)** | `backend/tests/test_connector_build_service.py` (G07) |
| Resume deliverable grounding (no invented employers/degrees unnoticed) | **Verified (local)** — deterministic check + heuristic score label | `backend/services/resume_builder.py` (G08) |

## 4. Durability and shared controls

| Evidence required | Status | Where |
|---|---|---|
| Daily token cap survives restart and spans processes | **Verified (local)** — durable ledger, atomic increments both backends | `backend/tests/test_usage_ledger.py` (F08) |
| Ledger failures are explicit (503), never silent pass | **Verified (local)** | `backend/tests/test_usage_ledger.py` |
| Rate limiting holds across replicas | **Partially closed** — trusted-proxy parsing, bounded state, group quotas done; *distributed* counters need Cloud Armor or a shared store (deployment-stage) | `backend/security/rate_limiter.py` |
| Blog/contact submissions durable + validated + rate-limited | **Verified (local)** — backend content repo; restart/scaling test requires deployment | `backend/api/routers/blogs.py`, `contact.py` |
| Dead-letter quarantine configured | **Verified in Terraform** — DLQ topics, quarantine subscriptions, bounded retries; alerting + replay drill are deployment-stage | `terraform/modules/pubsub/main.tf` |
| Budget reservations reconcile against provider usage | **Pending** — requires provider billing access | — |

## 5. Frontend acceptance

| Evidence required | Status | Where |
|---|---|---|
| Session refresh: concurrent requests, cross-tab, 204 | **Verified (local)** — single-flight + Web Locks + stale guards; e2e regression | `frontend/src/lib/auth-session.ts`, `e2e/session-expiry.spec.ts` |
| OAuth configuration consistent (CSP script/frame/connect + build var + clean disabled state) | **Verified (config)** — live Google sign-in requires real client credentials | `frontend/next.config.ts`, `cloudbuild.frontend.yaml` |
| ESLint quality gate | **Verified** — 0 errors, 0 warnings | CI-able |
| Build observation stops on unmount; reload resumes from build ID | **Verified (local)** | `dashboard/integrations/create/page.tsx` (G05) |
| Production-browser journeys (every page, devices, a11y, error states) | **Pending** — requires the production candidate deployment | — |
| WCAG 2.2 AA evaluation | **Pending** — requires defined scope + assistive-technology testing | — |

## 6. Operations

| Evidence required | Status |
|---|---|
| Clean production image startup (API + worker) with declared dependencies | **Pending** — `google-cloud-pubsub` is declared; image build/start smoke needs the cloud project |
| Backup restoration drill | **Pending** |
| Rollback drill | **Pending** |
| Load/soak evidence | **Pending** |
| Correlated traces + alerts + runbooks | **Pending** (tracing infrastructure exists; alert routing needs deployment) |
| Independent security assessment | **Pending** — explicitly not claimed by this project |

---

## Release claim this packet supports today

> The 30-Oct audit's F01–F16 baseline and G01–G08 observations are remediated
> and regression-tested at the repository level: 263 backend tests (including
> 8 adversarial authorization tests), 26 frontend unit tests, 16 browser E2E
> tests, ESLint clean. The release verdict beyond local evidence is unchanged:
> **not ready for unrestricted public or enterprise launch** until the
> deployment-stage items above are demonstrated on the actual production
> candidate.

## Change ledger (implementation vs audit findings)

| Finding | Implementation | Regression evidence |
|---|---|---|
| F01 org oversight | org-scoped runs only (`org_id` ownership) | `test_audit_security.py` |
| F02 role bypass | 409 on re-add; atomic create-only repos | `test_audit_security.py` |
| F03 disabled login | password + Google + refresh enforcement | `test_audit_security.py`, `test_auth_http.py` |
| F04 revocation | fail-closed 503; current-state authorization | `test_audit_security.py`, `test_auth_http.py` |
| F05 Pub/Sub dep | declared in requirements | `requirements.txt` |
| F06 Firestore leases | expired-RUNNING reclaim + fencing | `test_chaos_recovery.py`, source parity check |
| F07 exactly-once | ledger states; provider reconciliation pending | partial |
| F08 budgets | durable ledger + explicit failures | `test_usage_ledger.py` |
| F09 rate limits | proxy parsing + bounded state; distributed pending | partial |
| F10 Firestore parity | activation, tx-uniqueness, tx-counters, db id | `test_cloud_contracts.py` |
| F11 refresh race | single-flight + Web Locks + 204 | `e2e/session-expiry.spec.ts` |
| F12 OAuth/CSP | GIS origins + build var + disabled state | config verification |
| F13 local JSON | durable content repo + validation + limits | routers + e2e |
| F14 sandbox | redaction, python3, clear unsupported failure, host-execution prevention | `test_cloud_contracts.py` |
| F15 dead letters | DLQ + quarantine + bounded retries | Terraform |
| F16 release gates | hermetic tests, lint clean, adversarial suites | full suite |
| G01 execution gate | trust_tier + per-operation evidence | `test_connector_coverage.py` |
| G02 coverage | explicit evidence + coverage reporting | `test_connector_coverage.py` |
| G03 artifacts | adapter default; standalone gated by protocol tests | `test_standalone_packaging.py` |
| G05 build polling | abort on unmount | source + e2e |
| G06 provenance | stamped, preserved, trust ceiling | `test_connector_coverage.py` |
| G07 durable builds | shared service, origin + parent run | `test_connector_build_service.py` |
| G08 resume | grounding check + heuristic label | `resume_builder.py` |
