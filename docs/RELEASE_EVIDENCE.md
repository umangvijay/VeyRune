# Release Evidence Packet — Sandtable (AgentOS)

Audit baseline: *AgentOS / Sandtable — Full-stack audit & advancement plan v4.0* (30 Oct 2026).
This packet tracks the audit's required evidence, item by item, with the honest
status of each: **verified (local)** means implemented with regression tests that
run in this repository; **pending** means it requires resources this repository
cannot produce (a real deployment, provider accounts, or independent review).

A finding is *closed* only when its evidence meets the acceptance criteria.
A code change or passing narrow test alone does not close a broader guarantee.

## Review amendment — 31 October 2026

The blanket remediation claim below has been withdrawn. The prior rows record
reported historical evidence, not a new full-suite run during this documentation
update. Review baseline: committed v5.5.0 (`3ef8063`), with concurrent working-tree
fixes not certified here. See [current status](implementation-status.md) and the
[22-phase file-by-file roadmap](full-stack-roadmap.md).

| Finding/gate | Revised scope | Acceptance still needed |
|---|---|---|
| F01 invitations | Flow exists; legacy direct-add conversion is in progress | All paths plus transactional accept/revoke/duplicate races |
| F08 usage | Ledger exists; SQLite commit fix is in progress | Separate connections/restart, atomic reservations and complete paid-call accounting |
| F09 limits | Local counters are bounded | Shared multi-replica enforcement |
| F07 effects | Quarantine/resolution primitives exist | Actual provider receipts and controlled resolution coverage |
| G02 coverage | Execution predicate and displayed coverage diverged in a focused check | Changed definitions/credentials invalidate both |
| G03/G04 runtime | Packaging status checks exist; host execution is disabled | Content-tampering rejection and trusted isolated protocol runner |
| G07 build recovery | Both paths record metadata; orchestrator still ran inline in baseline | Unified durable dispatch and crash/resume tests |
| Browser actions | Local observe/act and challenge handling exist | Cleanup, session ownership and action-level approval coverage |
| Learning | Router records execution outcomes | Verified task rewards and real evaluation metrics |

Focused in-memory checks in the preceding review showed SQLite writes removable
by rollback, modified standalone contents still marked deployable, and invalidated
operations still counted in coverage. They are not cloud exploit or full-suite
claims. Changes arriving concurrently must be rechecked before these rows close.

Historical test totals in this packet differ by release (for example 263 and
279). Retain exact run logs and revisions rather than treating either number as
a fresh result. Configuration of a CI step is not proof that its current run passed.

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
| Accepted-invitation lifecycle (invite → accept) | **Partial; reopened** — basic invitation tests exist; legacy path and transaction/concurrency acceptance remain | `backend/tests/test_org_invitations.py`, `dashboard/orgs/page.tsx` |
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
| Completed local work suppresses duplicate execution | **Verified (local)** — stack-level test | `backend/tests/test_chaos_recovery.py` |
| Old execution cannot overwrite a reclaimed task (fencing) | **Verified (local)** | `backend/tests/test_chaos_recovery.py` |
| Uncertain-outcome handling | **Verified (local)** — uncertain state quarantines ambiguous outcomes and crash-orphaned locks (worker sweep); replay blocked with explicit reconciliation message; operator/provider receipt resolves via reconcile_uncertain | `backend/tests/test_uncertain_reconciliation.py` |
| Provider-specific reconciliation receipts | **Pending** — requires real provider accounts | — |
| Connector lifecycle: untested revisions cannot execute | **Verified (local)** — per-operation evidence + trust-tier gate | `backend/tests/test_connector_coverage.py`, `test_audit_security.py` (G01/G02) |
| Standalone packaging protocol-status checks | **Partial** — tests cover status flags; content-bound evidence and isolated runtime remain | `backend/tests/test_standalone_packaging.py` (G03) |
| Provenance labels (official/extracted/inferred) | **Verified (local)** | `backend/tests/test_connector_coverage.py` (G06) |
| Both build entry points record build metadata | **Partial** — equivalent queued execution/restart semantics not established | `backend/tests/test_connector_build_service.py` (G07) |
| **Self-extension loop (page-48 happy path)**: waiting run → durable build (origin + parent link) → adapter from real spec → live probe → verified registration → original run resumes and completes → auditable record | **Verified (local)** — full lifecycle integration test | `backend/tests/test_self_extension_loop.py` |
| Deliverable artifact validates and preserves user facts | **Verified (local)** — rendered HTML opens, contains actual facts, no placeholders; invented employers flagged; ATS score labeled heuristic | `backend/tests/test_resume_deliverable.py` (G08) |
| Release gate configuration | **Configured** — API image pytest, worker import smoke, frontend lint/unit/typecheck; current run evidence and real-backend browser gates remain | `cloudbuild.yaml`, `cloudbuild.frontend.yaml` (F16) |
| Resume deliverable grounding (no invented employers/degrees unnoticed) | **Verified (local)** — deterministic check + heuristic score label | `backend/services/resume_builder.py` (G08) |

## 4. Durability and shared controls

| Evidence required | Status | Where |
|---|---|---|
| Usage ledger persists and enforces a cross-process cap | **Reopened** — commit fix in progress; existing test shares a connection; reservation coverage required | `backend/tests/test_usage_ledger.py` (F08) |
| Ledger read failures are explicit (503) | **Narrow local evidence** — recording failures and missing accounting need separate coverage | `backend/tests/test_usage_ledger.py` |
| Rate limiting holds across replicas | **Partially closed** — trusted-proxy parsing, bounded state, group quotas done; *distributed* counters need Cloud Armor or a shared store (deployment-stage) | `backend/security/rate_limiter.py` |
| Blog/contact submissions durable + validated + rate-limited | **Verified (local)** — backend content repo; restart/scaling test requires deployment | `backend/api/routers/blogs.py`, `contact.py` |
| Dead-letter quarantine configured | **Verified in Terraform** — DLQ topics, quarantine subscriptions, bounded retries; alerting + replay drill are deployment-stage | `terraform/modules/pubsub/main.tf` |
| Budget reservations reconcile against provider usage | **Pending acceptance** — implement/verify reservation wiring locally; invoice comparison additionally needs provider access | — |

## 5. Frontend acceptance

| Evidence required | Status | Where |
|---|---|---|
| Session refresh coordination and 204 handling | **Partial** — local tests exist; real two-tab and unsupported-Web-Locks acceptance remain | `frontend/src/lib/auth-session.ts`, `e2e/session-expiry.spec.ts` |
| OAuth configuration consistent (CSP script/frame/connect + build var + clean disabled state) | **Verified (config)** — live Google sign-in requires real client credentials | `frontend/next.config.ts`, `cloudbuild.frontend.yaml` |
| ESLint quality gate | **Verified** — 0 errors, 0 warnings | CI-able |
| Build observation stops on unmount; reload resumes from build ID | **Verified (local)** | `dashboard/integrations/create/page.tsx` (G05) |
| Production-browser journeys (every page, devices, a11y, error states) | **Pending** — requires the production candidate deployment | — |
| WCAG 2.2 AA evaluation | **Pending** — requires defined scope + assistive-technology testing | — |

## 6. Operations

| Evidence required | Status |
|---|---|
| Clean production image build + startup (API + worker) | **Verified (clean-image, local)** — API and worker images build from a clean environment; Python 3.11.16 runtime parity confirmed by running the full 279-test suite INSIDE both images; declared deps import (pubsub, firestore); `pip check` clean; startup smoke reaches `/health` 200 with keys via secret-mount; production mode without keys fails with an actionable operator message. Cloud-project startup (Pub/Sub wiring) still needs the deployment |
| Backup restoration drill | **Pending** |
| Rollback drill | **Pending** |
| Load/soak evidence | **Pending** |
| Correlated traces + alerts + runbooks | **Pending** (tracing infrastructure exists; alert routing needs deployment) |
| Independent security assessment | **Pending** — explicitly not claimed by this project |

---

## Change ledger additions (v5.5.0)
| Item | Implementation | Evidence |
|---|---|---|
| Invitation accept UI | invitee surface on the orgs page (paste token → accept) | `dashboard/orgs/page.tsx` |
| Loopback SSRF seam | numeric-loopback allowance is a TEST-ONLY flag, default strict; workflow core.http can never reach app-localhost | `openapi_parser.py` (`_LOOPBACK_TESTING`) |

## v5.6 review closure (second focused review, 31 Oct)

| Finding | Status | Evidence |
|---|---|---|
| Membership acceptance bypass (members route) | **Closed** — the route now creates a pending invitation (202); `org_repo.add_member` is never invoked by it; tests assert the smoking gun | `test_v56_review_regressions.py` |
| SQLite usage persistence (missing commit) | **Closed** — add_usage commits; cross-connection durability test (separate DatabaseManager instances) | `test_v56_review_regressions.py` |
| Budget not an atomic reservation | **Closed** — guarded-upsert reserve before every paid call, settle after; concurrent near-cap racers cannot both win; budget counts settled+holds | `test_v56_review_regressions.py`, `test_usage_ledger.py` |
| Firestore invitation races | **Closed** — accept is one transaction (invite read + membership create + status flip); token-hash doc id; deterministic pending marker for duplicate creation | `backend/repositories/firestore/sidecar.py` |
| Artifact evidence not bound to content | **Closed** — protocol results record `content_hash`; mark_deployable refuses when content changed after testing; exact dependency pins | `test_standalone_packaging.py` |
| Coverage helper stale/duplicated | **Closed** — one authoritative function, digest-verified when spec_hash/credential supplied; factory passes both | `test_connector_coverage.py` |
| Orchestrator builds not restart-safe | **Closed** — agent builds dispatch through the queued lifecycle; parent task parks as a durable approval; the worker resolves it and re-dispatches when the build lands | `test_connector_build_service.py` |
| Browser consequential actions ungated | **Closed** — form submissions and submit-control clicks pass through the persisted, argument-bound approval gate | `web_agent.py` (`_is_consequential`) |
| Browser session leaks / unbounded pauses | **Closed** — owned resources close by reference even without a registry entry; session leases (30 min) swept by the worker | `browser_sessions.py`, `worker.py` |
| Rate limiting across replicas | **Open (deployment-stage)** — needs Cloud Armor or a shared store on the actual topology | — |
| Generated-code isolated runner | **Open (product work)** — host execution disabled; supported runner is a scoped build | — |
| Cloud recovery, load, live OAuth, a11y journeys | **Open (deployment-bound)** | — |

## v5.7 learning + recovery loop closure (31 Oct)

| Item | Status | Evidence |
|---|---|---|
| §3 self-healing loop (detect→classify→select→execute→verify→record→escalate) | **Verified (local)** — deterministic RecoveryPolicy with per-category ceilings, deadline, repeated-action detector; RecoveryWorker refuses disallowed recoveries and escalates into structured incidents with user options | `backend/tests/test_self_healing_and_learning.py` |
| §4 EvaluationService placeholders | **Closed** — records now carry the REAL per-run token spend the model client recorded; generated once per terminal run by the worker | `test_self_healing_and_learning.py` |
| §5 stage 1 outcome verification | **Closed** — the adaptive-policy reward is positive only for verified usable payloads; a silent-but-empty response records a FAILURE reward | `test_self_healing_and_learning.py`, engine post-loop gate |
| §7 explicit task states | **Partially** — engine states exist (PENDING/RUNNING/WAITING/WAITING_APPROVAL/RECOVERING/FAILED/COMPLETED); frontend badge mapping complete; "uncertain" surfaced via reconciliation states | engine + dashboard |
| §9 first subagents (Outcome Verifier / Recovery Analyst) | **Partially** — RecoveryPolicy IS the deterministic Recovery Analyst gate; Outcome Verifier exists for resumes + recovery outcomes; generalized verifier remains future work | `recovery_policy.py` |

## Release claim this packet supports today

The repository has substantial implementation and previously reported local
regression/image evidence. Findings listed in the amendment remain open or in
progress. Neither “all F01–F16/G01–G08 closed” nor “only deployment remains” is
supported. Required source fixes and candidate-specific operational evidence must
pass before the selected launch scope is accepted. No production certification
is claimed.

## Historical implementation ledger (qualified by the amendment above)

| Finding | Implementation | Regression evidence |
|---|---|---|
| F01 org oversight | org-scoped runs only (`org_id` ownership) + accepted-invitation lifecycle | `test_audit_security.py`, `test_org_invitations.py` |
| F02 role bypass | 409 on re-add; atomic create-only repos | `test_audit_security.py` |
| F03 disabled login | password + Google + refresh enforcement | `test_audit_security.py`, `test_auth_http.py` |
| F04 revocation | fail-closed 503; current-state authorization | `test_audit_security.py`, `test_auth_http.py` |
| F05 Pub/Sub dep | declared in requirements; imports verified in the clean image | `requirements.txt` + clean-image run |
| F06 Firestore leases | expired-RUNNING reclaim + fencing | `test_chaos_recovery.py`, source parity check |
| F07 exactly-once | uncertain quarantine + crash sweep + explicit reconciliation | `test_uncertain_reconciliation.py` |
| F08 budgets | durable ledger + explicit failures | `test_usage_ledger.py` |
| F09 rate limits | proxy parsing + bounded state; distributed pending | partial |
| F10 Firestore parity | activation, tx-uniqueness, tx-counters, db id | `test_cloud_contracts.py` |
| F11 refresh race | single-flight + Web Locks + 204 | `e2e/session-expiry.spec.ts` |
| F12 OAuth/CSP | GIS origins + build var + disabled state | config verification |
| F13 local JSON | durable content repo + validation + limits | routers + e2e |
| F14 sandbox | redaction, python3, clear unsupported failure, host-execution prevention | `test_cloud_contracts.py` |
| F15 dead letters | DLQ + quarantine + bounded retries | Terraform |
| F16 release gates | hermetic tests, lint clean, adversarial suites, clean-image parity (279/279 in-image on 3.11) | full suite + container run |
| G01 execution gate | trust_tier + per-operation evidence | `test_connector_coverage.py` |
| G02 coverage | explicit evidence + coverage reporting | `test_connector_coverage.py` |
| G03 artifacts | adapter default; standalone gated by protocol tests | `test_standalone_packaging.py` |
| G05 build polling | abort on unmount | source + e2e |
| G06 provenance | stamped, preserved, trust ceiling | `test_connector_coverage.py` |
| G07 durable builds | shared service, origin + parent run | `test_connector_build_service.py` |
| G08 resume | grounding check + heuristic label + deliverable validation | `resume_builder.py`, `test_resume_deliverable.py` |
