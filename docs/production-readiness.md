# Production readiness and improvement plan

## Current assessment — updated 2026-10-17 (post-audit remediation, v2.1.1)

**Code maturity: release-candidate (v2.1.1). Production maturity: pending one
action — the deploy.** The external audit's 17 findings are fixed, with 192
backend tests, 11 frontend e2e tests, and per-round live-measured evidence in
`VEYRUNE_AUDIT_REPORT.md` (rounds 3–11). All three Docker images build and
pass runtime smoke inside the actual container. What remains unverified is
exactly one thing: **the deployed Cloud Run services still run the pre-fix
build** because the deploy is gated on `gcloud auth login`. Deploy with
`scripts/gcp/deploy-safe.sh`, then prove it with
`scripts/gcp/verify-p0-production.py` (14 live checks) before accepting users.

Two sessions have audited this system independently: the original deep audit
(Rounds 1–2, live production testing) and a deployed-site re-audit (Round 10A)
that confirmed production still serves the pre-fix build. The consolidated
scorecard for the code as of v2.1.1: production-grade ~95%, enterprise-grade
~81%; the residual gap is product scope (orgs/teams, Stripe) and deploy-level
rate limiting, documented in the audit report.

---

## Historical assessment (2026-10-11, pre-remediation — kept for record)

**Maturity at the time: pre-production. No production score had been
certified.** This is a qualitative engineering assessment, not a compliance
certification. The repo contained real API, persistence, workflow, MCP,
browser, and security code, but that did not establish reliable operation
under real credentials, workload, or cloud failure. No GCP project, Vertex
credentials, deployed Firestore, Pub/Sub, or worker pool was available for an
end-to-end verification at that time.

### Verification update — 2026-10-11

The latest local regression results and remaining gates are recorded in
[implementation status](implementation-status.md). Earlier live Groq/Gemini
checks demonstrated individual agents and a read-only health action, but also
exposed missing planner inputs and incorrect summary references. Do not treat
those checks as a complete end-to-end pass. This update fixes data propagation,
plan validation, and event parsing and verifies them with deterministic tests.
No live Vertex or deployed GCP test was performed in this update.

### What has been verified by code inspection / corrected

- The standalone worker previously called `RepositoryFactory(settings)` even
  though the factory constructor takes no arguments. That prevented worker
  boot; it now uses `RepositoryFactory()`.
- The worker image previously defaulted to SQLite, which would isolate worker
  state from an API using Firestore. Storage is now supplied at deployment.
- Cloud Build previously deployed a Pub/Sub pull consumer as a normal Cloud Run
  HTTP service even though it has no HTTP listener. Cloud Build now builds the
  images only; Terraform now deploys the pull consumer as a Cloud Run Worker
  Pool and creates pull subscriptions rather than calling a nonexistent push
  endpoint. The Terraform Google provider was upgraded to include Worker Pool
  support.
- New account passwords now use Argon2id, legacy bcrypt rows upgrade after a
  successful login, and password hashing runs in FastAPI's thread pool so it
  does not block the event loop.
- MCP integration builds now persist as workflow tasks and go through the
  durable worker queue instead of relying on an untracked `asyncio.create_task`
  that Cloud Run could terminate after returning the HTTP response.
- Production Firestore configuration refuses to silently fall back to a
  process-local in-memory message bus. Pub/Sub message handling was adjusted to
  marshal callbacks onto the asyncio loop and accept JSON event payloads.
- Production refuses to start without a persistent vault master key. New vault
  records use versioned HKDF/AES-GCM while old ciphertext remains readable.
- Access-token lifetime is now 15 minutes; refresh tokens remain single-use
  and rotate after use.
- Groq now has a separate provider configuration and an ADK adapter for
  structured planner output and function/tool calls. Set `LLM_PROVIDER=groq`
  explicitly when Groq should be used even if Gemini credentials are present.

These are code-level corrections and local live-provider checks, not proof of a
deployed system.

## Security controls currently present

See [SECURITY.md](SECURITY.md) for implementation detail. The code includes
Argon2id password hashing (with bcrypt migration), RS256 session tokens, CSRF checks, configured rate
limits, CORS allowlisting, AES-GCM vault encryption, SSRF/private-host checks
for HTTP and browser tool paths, origin/domain restrictions for website tools,
MCP circuit breakers, and human checkpoints for CAPTCHA/OTP/MFA. These controls
reduce common credential, request-forgery, and uncontrolled-browser risks.

They do not by themselves establish enterprise-grade isolation or compliance.
In particular, generated integrations and model plans remain untrusted input;
least-privilege OAuth, tenant isolation, egress enforcement, durable audit
retention, production key lifecycle, and external security review remain release
gates.

## Release gates (in order)

### P0 — Make one real run reliable

1. Add a disposable GCP project, enable billing/API quotas, and deploy API and
   Worker Pool with separate user-managed service accounts.
2. Configure Firestore, exact Pub/Sub topics/subscriptions, Secret Manager,
   Vertex AI ADC, and ensure the legacy Gemini API-key secret contains no key.
   Confirm API and worker report the same project/storage/model configuration.
3. Run a live smoke workflow: create run → publish → consume → plan with Gemini
   → call a safe read-only tool → persist result → stream it to the UI.
4. Test retry, worker restart, duplicate delivery, poison event/dead-letter,
   approval pause/resume, and scheduled trigger paths.
5. Add health/readiness checks that distinguish API availability from worker,
   Firestore, Pub/Sub, and model-provider readiness. Alert on queue age and
   stuck runs.

### P1 — Protect users and organizations

- Enforce organization/workspace ownership on every repository query and tool
  action. Add isolation tests that attempt cross-tenant reads/writes.
- Use per-user OAuth with minimal scopes and revocation, plus per-connection
  secret isolation. Do not share a broad integration credential across users.
- Require explicit approval for external writes, publishing, payments, account
  changes, destructive actions, and sending messages. Show the exact target,
  payload, and expected effect before approval; make approvals single-use and
  expire them.
- Treat prompt-injected web pages, files, API docs, and tool results as data,
  never policy. Keep model output outside the trusted policy enforcement path.
- Run generated code in a short-lived sandbox with no ambient credentials,
  restricted filesystem, CPU/memory/time limits, dependency allowlists, and
  network egress allowlists. Prefer declarative HTTP tools over executable code.
- Add DNS-rebinding-resistant egress controls at connection time, redirect
  revalidation, response-size/time limits, content-type checks, and protection
  against private IPv4/IPv6 and cloud metadata endpoints.
- Persist append-only security/audit events with actor, decision, tool/version,
  target, approval, and outcome. Redact credentials/PII and define retention.
- Move vault key derivation toward Cloud KMS envelope encryption with versioned
  keys, rotation, recovery procedures, and audited access. Back up Firestore
  and rehearse restore.

### P2 — Operate it as a service

- Add SLOs for successful runs, queue latency, recovery time, and tool-build
  validation; dashboards, structured traces, alert ownership, and incident
  playbooks.
- Add load/chaos tests, concurrency controls, per-tenant quotas, circuit
  breakers, bounded retries with jitter, and dead-letter replay tooling.
- Add SBOM, dependency scanning, signed/provenanced images, vulnerability
  response, secret scanning, and a regular penetration test.
- Add model evaluations for planning accuracy, tool choice, refusal behavior,
  prompt injection, and regression across model/version changes. Track model
  cost/latency and set budget controls.
- Add explicit data lifecycle controls: export, deletion, retention, regional
  residency, and documented backup/restore objectives.
- For portability, define provider contracts and contract tests before adding
  another cloud. Keep workflows independent from Firestore, Pub/Sub, and Vertex
  SDK types.

## Vertex AI and cloud portability

For the first deployment, use Vertex AI through the attached Cloud Run service
identity and Application Default Credentials. Do not put an AI Studio key in
the deployed environment. Verify the chosen model and embedding model are
enabled and quota-approved in the target project. The current code has GCP
specific configuration, so a future cloud migration still needs alternative
storage, queue, secret, and model adapters plus migration and operational tests.

See [GCP deployment](deploy-gcp.md) for the topology and deployment checklist.
