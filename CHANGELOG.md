# Changelog

## v6.0.0 — 2026-10-31

### Phase 1 tenancy: DB invariants, one invitation service, adversarial suites

The detailed Phase-1 roadmap's outstanding items, closed:

- **1.6 Uniqueness as a database invariant**: a unique partial index on
  `(org_id, email) WHERE status='pending'` backs the application check —
  concurrent duplicate invitations across independent connections leave
  exactly one pending row (proven with two DatabaseManager instances).
- **1.5 One shared invitation service**: `organization_invitation_service`
  is the single creation/acceptance path; the invitations route and the
  legacy members alias both delegate to it. Role validation, member/
  owner checks, email normalization, token generation (hash-only
  storage), and audit events live in exactly one place.
- **1.15 Adversarial tenant isolation** (`test_tenant_isolation.py`, 5
  tests): personal-run listing/direct-read denial, owner-scoped schedule
  listing, foreign artifact download denial with real path-contained
  files, owner-scoped credential reads, removed-member oversight loss.
- **1.15 Membership concurrency** (`test_membership_concurrency.py`, 3
  tests, independent connections): duplicate-invite race, accept-vs-
  revoke race (one consistent outcome), expiration not blocking new
  invitations.

315→323 backend tests green; 31 frontend + 16 e2e green.

## v5.9.0 — 2026-10-31

### §7 explicit states + connector clarity; §9 Outcome Verifier

- **Explicit task states (§7):** one authoritative `runStateStyle`
  mapping — Queued, Running, Waiting for approval, Waiting for
  credentials, Recovering, Outcome uncertain, Completed, Failed,
  Cancelled — rendered on the builds page with per-task colors; unknown
  states fall back safely.
- **Connector lifecycle clarity (§7):** every integration card shows
  separate badges for artifact type, tested, verified / needs-review,
  and active — the "generated ≠ authenticated ≠ tested ≠ active"
  distinction the audit required.
- **§9 Outcome Verifier:** a bounded, read-only service with typed
  acceptance criteria (contains / artifact_exists / http_ok /
  schema_keys / non_empty) returning pass / needs-review / fail with
  reasons. It never mutates the output, never executes tools, and never
  approves its own repair. 6 tests; 5 frontend tests for the state
  mappings.

315 backend + 31 frontend + 16 e2e green.

## v5.8.0 — 2026-10-31

### Shared rate limiting + browser outcome verification

**§1 closed — the last process-local High finding.** Abuse-sensitive
groups (auth, contact, webhook, mcp_build) now enforce ONE durable
fixed-window limit across replicas and restarts: a guarded-upsert
counter in the shared database (SQLite) / transactions (Firestore),
wired through the factory, purged opportunistically by the worker.
High-volume groups deliberately stay process-local — a database
round-trip per request is the wrong trade for volume the edge (Cloud
Armor) enforces better; that split is documented in the evidence packet.
Cross-replica and window-reset regressions included.

**§6 — browser outcome verification and stale-target detection.**
A model saying "done" no longer automatically establishes success: a run
whose every executed step errored is flipped to failure with the
verification evidence attached. And the observe-decide-act loop now
detects **repeated ineffective actions** — the same action fingerprint
twice with an unchanged page raises for recovery instead of spinning
until the step budget runs out.

309 backend + 26 frontend + 16 e2e green.

## v5.7.0 — 2026-10-31

### Self-healing loop formalized; rewards verify outcomes; evaluations are real

**§3 — the recovery loop is now a bounded, deterministic policy.**
`RecoveryPolicy` gates every LLM recovery: per-category ceilings, a 15-
minute deadline, and a repeated-action detector (the same recovery with
the same arguments is refused even inside the budget). The
RecoveryWorker consults it BEFORE running the recovery agent — refusals
escalate into a structured incident (classification, attempt ledger,
recovery hint, user options) delivered as a notification and a failed
task with `[recovery-escalated]` evidence. 10 tests.

**§5 stage 1 — rewards verify outcomes.** The adaptive model policy
recorded success whenever the model runner finished without an
exception. It now records success only for a VERIFIED usable payload
(non-empty reply or real tool result): a silent-but-empty response
records a FAILURE reward for whichever model ran. Security and
authorization remain hard constraints outside the reward.

**§4 — evaluations are real.** The model client tracks per-run token
spend; the worker generates an evaluation record once per terminal run
carrying that real spend (no more placeholder zeros), and the per-run
counters drain exactly once.

**Also:** production-readiness.md was verified already reconciled with
the release evidence packet (the parallel session updated it before this
turn); per-run usage accounting covers planning, recovery, and browser
decision paths via the shared llm-context binding.

302 backend + 26 frontend + 16 e2e green.

## v5.6.0 — 2026-10-31

### Second-review Phase A: every release blocker and High finding closed

The 31-Oct focused review of v5.5.0 found two new release blockers and
six High findings. All are closed with regressions — 292 backend +
26 frontend + 16 e2e green.

**Release blockers:**
- **Membership acceptance bypass removed.** The legacy members route now
  creates a pending invitation (202) — `org_repo.add_member` is provably
  never invoked by it; membership exists only on ACCEPTANCE.
- **Usage commits.** `add_usage` now commits; the durability test uses
  two separate connections (the old test shared one and masked the bug).
- **Atomic budget reservations.** Every paid model call runs
  reserve(estimated max) → run → settle(actual): a guarded upsert makes
  near-cap racers lose atomically on both SQLite and Firestore; the
  budget check counts settled actuals plus open holds.

**High:**
- Firestore invitation acceptance is one transaction (invite read +
  membership create + status flip); the invitation doc id IS the token
  hash; a deterministic pending marker blocks duplicate invites atomically.
- Standalone-server protocol results bind `content_hash` of the immutable
  executable content; editing server code after testing invalidates
  deployability. Dependency locks are exact versions.
- Coverage counting collapsed to ONE authoritative function, digest-
  verified against spec hash + credential when provided (the stale
  duplicate is gone).
- Orchestrator builds now dispatch through the queued lifecycle and park
  the parent task as a durable approval; the worker resolves the approval
  and re-dispatches the task when the build lands. A restart at any
  point loses nothing.
- Browser consequential actions (form submits, submit-control clicks)
  pass through the persisted, argument-bound approval gate.
- Browser resources close by reference even without a registry entry
  (the Chromium leak); paused sessions carry a 30-minute lease swept by
  the worker.

**Deliberately deferred (documented in RELEASE_EVIDENCE.md):** shared
rate limiting (Cloud Armor / shared store on real topology), the
generated-code isolated runner, cloud recovery drills, live OAuth and
accessibility journeys.

## v5.5.0 — 2026-10-31

### The defining lifecycle proven: the self-extending loop runs end to end

**Page-48 happy path, verified locally** (`test_self_extension_loop.py`):
a waiting run whose capability is missing → the orchestrator requests the
build through the durable service (origin + parent_run_id link the
waiter) → the adapter is generated from a real OpenAPI spec → the live
probe passes against a local capability server → the connector registers
**verified** with artifact_type=adapter, provenance, and per-operation
coverage → the original run resumes and completes against the newly
acquired capability → the build record still points back at the
completed run. The only hop needing a model is the gap detection
itself; every durable, policy, and resumption mechanic is proven.

**Supporting work:**
- Loopback SSRF handling: numeric-loopback allowance is now a TEST-ONLY
  flag (`OpenAPIParser._LOOPBACK_TESTING`, default False). Workflow
  core.http keeps strict validation — a user workflow can never reach
  the app's own localhost; "localhost" the NAME stays rejected (DNS
  rebinding); the loop test enables the seam only for its own lifetime.
- Invitation **accept** UI: the invitee surface (paste token → accept)
  on the orgs page completes the F01 full-stack flow.
- G08 deliverable validation: rendered resume HTML opens and contains
  the user's actual facts with no placeholder leakage; invented
  employers are flagged; the ATS score is labeled heuristic (3 tests).
- F16 build gates verified: backend CI runs the pytest suite inside the
  candidate image with `--network=none`; frontend CI runs
  lint(max-warnings=0) + unit + typecheck before the image build.

283 backend + 26 frontend + 16 e2e green.

## v5.4.0 — 2026-10-30

### Clean-image verification: the runtime-parity gate is closed

The audit's F05/F16 "clean production image" acceptance is now
demonstrated locally with Docker (colima):

- **API and worker images build from a clean environment** and run
  **Python 3.11.16** — the exact shipped runtime the audit flagged as
  unverified (local dev was 3.14).
- **Full suite inside the images**: all 279 backend tests pass inside
  BOTH the API and worker images. The in-image run caught a real
  parity defect: `test_ephemeral_vault_key_is_never_written_to_logs`
  assumed a development `APP_ENV`; on the production-configured image
  the vault correctly refuses ephemeral keys. The test now pins the
  environment it tests.
- **Declared dependencies verified in-image**: `google.cloud.pubsub_v1`
  and firestore import; `pip check` clean (F05 acceptance).
- **Startup smoke**: the API container starts with SQLite config and
  reaches `/health` 200 with JWT keys via the documented secret-mount
  path; worker housekeeping runs.
- **Two real deploy blockers caught and fixed**: (1) the working tree's
  `backend/` had 0700 permissions, which copied into the image and made
  every module unimportable at runtime — permissions normalized;
  (2) production mode without JWT keys failed with a raw
  PermissionError — it now raises an actionable operator message
  ("provide JWT_PRIVATE_KEY / JWT_PUBLIC_KEY via Secret Manager and
  restart"), matching the audit's clear-disabled-state standard.
- Remaining cloud-only items: Pub/Sub-wired startup, backup/rollback
  drills, load evidence (need the actual cloud project).

279 backend green (local and in-image) + 26 frontend + 16 e2e.

## v5.3.0 — 2026-10-30

### Audit: uncertain-outcome reconciliation + accepted invitations

**F07 — no blind replay of irreversible actions, completed.** The
idempotency ledger gained the two remaining mechanics: a worker
housekeeping **sweep** quarantines crash-orphaned `running` entries as
`uncertain` (never `failed` — the external outcome is unknown), and
`reconcile_uncertain` lets an operator or provider receipt resolve an
entry to completed (zero-cost replay safe) or failed (retry needs a new
key). Both SQLite and Firestore implement them; replay of uncertain
entries stays blocked with an explicit message. 6 tests
(`test_uncertain_reconciliation.py`), including "the guarded action must
not execute again".

**F01 — membership now requires acceptance.** Full invitation lifecycle:
POST /orgs/{id}/invitations issues a one-time token (only its hash is
stored; listed invitations never expose it), the invited user accepts via
POST /orgs/invitations/accept, and membership is created atomically with
the create-only invariant. Email-matched to the accepting account;
expiry, revocation, single-use, and one-pending-per-email (an admin
cannot silently upgrade a pending invite) are all enforced. Both SQLite
and Firestore sidecars implement the parity contract. The orgs UI now
issues one-time tokens instead of silently adding members. 5 tests
(`test_org_invitations.py`), e2e updated to the invitation flow
(anti-enumeration asserted: unknown emails still receive invites, no
user-existence leak).

279 backend + 26 frontend + 16 e2e green.

## v5.2.0 — 2026-10-30

### Audit closure: explicit artifact products + release evidence packet

**G03 — explicit artifact products.** The connector product boundary the
audit required is now concrete: `artifact_type` on every manifest, with
**adapter** (declarative mapping, the default and only auto-activated
product) distinct from **standalone_server** (an explicit export
package). Packaging produces an immutable, content-addressed artifact —
versioned source, dependency lock, per-tool schemas — that ALWAYS ships
`deployable: false`; `mark_deployable` refuses unless initialize,
tools/list AND tools/call protocol tests have all passed on the exact
artifact (hash-bound). Nothing in the build pipeline calls packaging
automatically. 5 tests (`test_standalone_packaging.py`).

**F16 — hermetic tests verified.** The three OpenAPI tests the audit saw
fail on petstore3.swagger.io DNS already run through a deterministic
`getaddrinfo` stub — 6/6 pass fully offline; the audit's flaky-network
class is retired.

**Release evidence packet.** `docs/RELEASE_EVIDENCE.md` now tracks every
audit evidence requirement with its honest status: verified (local)
with the exact regression file, or pending with the reason (deployment,
provider accounts, or independent review). Includes the full F01–F16 +
G01–G08 change ledger. The packet's claim is explicit: repository-level
remediation is complete and tested; the release verdict beyond local
evidence is unchanged until deployment-stage items are demonstrated.

268 backend + 26 frontend + 16 e2e green.

## v5.1.0 — 2026-10-30

### Audit stage 4+: connector evidence, provenance, and one durable build path

**G02 — per-operation test evidence.** Every generated operation is now
stamped with explicit validation evidence ("not run") at generation; a
passing probe upgrades exactly one operation, and a coverage summary
(total / read_probe_passed / untested / mutating_untested) is computed at
build time, logged, persisted on the manifest, and surfaced in catalog,
integration-detail responses. Untested operations cannot inherit the
verified badge — ToolPolicy denies them per operation (test: an
integration with ten operations and one passing probe reports exactly
that coverage).

**G06 — spec provenance is the trust ceiling.** Operations carry
`spec_provenance` (official_spec / extracted_docs / inferred_description)
stamped at generation and preserved through probes. The build's trust
tier keys on the SOURCE: url/spec/openapi can earn verified;
docs/prompt stay pending_review however good the probe looks. Manifest
fields `spec_provenance`, `test_coverage`, `capabilities_omitted` are
backward-compatible defaults on old records. Tests
(`test_connector_coverage.py`, 7).

**G07 — one durable build path.** New shared
`connector_build_service`: the API entry point delegates to it
(record + workflow task + dispatch, origin=api), and the orchestrator's
`build_integration` now creates the same durable record with
origin=orchestrator and the waiting parent run before running the
factory inline with the build_id — stage logs and outcomes land in the
same durable place and a restart mid-build leaves a recoverable trace.
`mcp_builds` gained origin / parent_run_id / wait_reason columns
(SQLite migration; Firestore stores the full payload). Tests
(`test_connector_build_service.py`, 3).

**G08 — resume provenance.** New deterministic grounding check
(`verify_resume_provenance`): every employer, institution and degree the
model produced must literally appear in the source text; anything else
is flagged `needs_review` in the build result. The ATS score now labels
itself: `score_kind: "heuristic"` with an explicit note that it does not
predict ATS acceptance or employment outcomes.

263 backend + 26 frontend + 16 e2e green; ESLint clean.

## v5.0.0 — 2026-10-30

### Audit remediation verified: F01–F16 + G01–G08 against the 30-Oct audit

The full-stack audit (F01–F16 baseline + G01–G08 connector observations)
was re-verified finding by finding against the current tree, with the
gaps closed and every first-batch acceptance criterion encoded as an
adversarial regression test. 253 backend + 26 frontend + 16 e2e green.

**Security (F01–F04) — closed and proven.** New adversarial suite
(`test_audit_security.py`, 8 tests): duplicate membership cannot mutate
roles at the router OR repository (atomic create-only insert in both
SQLite and Firestore); disabled accounts receive no tokens via password
or Google login; a logged-out/revoked token is refused; a denylist
outage fails CLOSED (503, never allow); demotion/disable takes effect
immediately because authorization re-reads current account state rather
than trusting JWT claims; organization oversight exposes only explicitly
organization-owned runs — personal runs stay private before and after
membership, and task payloads are sanitized. To make org-owned runs
possible, `WorkflowRun.org_id` was added (SQLite column migration +
model field; Firestore persists the payload).

**Cloud correctness (F05/F06/F10) — verified closed.** `google-cloud-
pubsub` is declared in requirements; Firestore `claim_task` reclaims
RUNNING tasks with expired leases (fenced by attempt); Firestore user
repository has transactional email-uniqueness registry, transactional
failed-login counters, `set_user_active`, and honors
`FIRESTORE_DATABASE_ID`.

**Shared controls (F08) — implemented.** New durable usage ledger
(`usage_ledger` table / `usage_ledger` collection, atomic increments in
both backends, wired through the factory). Every LLM path records spend
durably; the daily budget check reads the durable total so the cap
survives restarts and holds across API/worker processes. Ledger failures
are explicit (503), never a silent pass. (`test_usage_ledger.py`, 4
tests.)

**Verified already-closed in the working tree:** F09 (trusted-proxy
parsing, bounded state, group quotas), F11 (single-flight refresh with
Web-Lock cross-tab coordination + 204 handling), F12 (GIS script-src +
frame-src + build-time client ID + clean disabled state), F13
(blog/contact moved to durable backend content repo with typed bounds,
rate limits, roles), F14 (sandbox: python3 handling, redacted logs,
clear unsupported-runtime failure, host-execution prevention test), F15
(dead-letter topics + quarantine subscriptions + bounded retries), G01
(trust_tier lifecycle enforced at discovery AND execution, probe
evidence bound to spec-hash + credential), G05 (cancellable build
observation), F16 lint (0 errors / 0 warnings).

**Still open (staged, per the audit's own sequencing):** G02 full
per-operation authenticated test packs beyond the read probe; G03
standalone MCP server packaging/deployment path; G06 spec-provenance
labels; G07 unified durable build service; G08 resume provenance
labels; release-operations drills (backup restore, rollback, load) which
require the actual cloud deployment.

## v4.9.0 — 2026-10-28

### The loom heals itself; the ink gained a glint

**Self-healing loop, visible.** Each of the nine threads now runs a
deterministic lifecycle on a staggered 26-second clock: the thread
*snaps* (a gap opens mid-curve), a fault state dims it while an amber
marker blinks at the break, then two knit fronts of light converge from
both ends and the thread sews itself back together. With nine staggered
threads, recovery is always happening somewhere in the frame — the
product's recovery agent, made visible.

**Self-evolving loop, visible.** Each blueprint sheet periodically
redraws itself with a fresh drafting pattern, stamps
"SELF-DRAFTED · REV NN" in its corner, and flashes briefly as the new
revision lands — the workspace improving its own blueprints, on screen.

**Loom vitals.** The footer now carries a real-telemetry chip fed by the
live `/health` endpoint: uptime minutes, storage engine, and the
recovery-loop status — hidden entirely when the API is unreachable,
never faked.

**Ink flow v2.** The accent-word gradient gained a luminous glint band
that rides through it (reads as a shine passing through the ink, not a
hue change), the cycle slowed to 9s, and the drafting dots now pulse
gently on every page. Both effects respect prefers-reduced-motion.

- 205 backend + 17 unit + 16 e2e tests green.

## v4.8.0 — 2026-10-28

### The loom sews, the ink flows

**Threading made visible.** Each of the nine planet-to-sheet threads now
carries a travelling pulse of light (custom line shader, additive
blending) — the sewing current that shows the planet stitching the
blueprints. Needle heads glow and throb; a dashed stitch row trails the
weave needle on every sheet; the sheets gained a sewn hem (dashed stitch
border) in their texture. The planet bobs gently and precesses on its
axis, so limb highlights drift.

**Ink flow on every page.** The accent words — "It's *drawn.*" on the
home hero, the italic accent in every public-page SheetHeader, the
Sandtable wordmark on login/signup — now animate a slow (7s) gradient
drift through the blue family (accent → purple → steel). No pink, no hue
chaos; disabled under prefers-reduced-motion and the reduce-data switch.
The animation lives at the end of drafting.css so it wins the cascade;
inline em colours removed from Integrations/Blog so the effect reaches
them too.

- 205 backend + 17 unit + 16 e2e tests green.

## v4.7.0 — 2026-10-28

### The canvas is the interface: HUD panel removed

The Planetary Loom control panel ("A world taking shape" card) is gone
from the home page. The scene itself carries every interaction now:

- **Focus**: click the planet or a blueprint sheet on the canvas; Escape
  returns to overview (unchanged).
- **Zoom**: scroll-wheel / pinch on the canvas (unchanged).
- **Tempo**: the play/pause + 0.5×/1×/2× dock in the footer (unchanged).
- **Scene fallback**: the "Preparing your 3D world…" / "Retry 3D scene"
  note moved into the footer, so the WebGL-recovery path survives the
  removal.
- Landing unit tests rewritten for the HUD-free layout (17 unit, 205
  backend, 16 e2e green).

## v4.6.1 — 2026-10-28

### The stragglers join the drafting board

Every remaining frontend page now carries the home page's identity:

- **Integrations**: serif display heading with klein-blue italic accent
  over the connector workbench.
- **Privacy / Terms**: mono "SANDTABLE LEGAL" eyebrow + serif titles.
- **Login / Signup**: serif "Sandtable" wordmark (static duotone — the
  hue-shift is gone here too).
- **Get-started**: bracketed console frame around the workspace loader.
- 205 backend + 17 unit + 16 e2e tests green.

## v4.6.0 — 2026-10-28

### Public pages in the home page's language; a better planet

**Public pages now speak the drafting dialect.** New shared `SheetHeader`
component: bracketed console frame, glowing mono eyebrow with volume
index, serif display title with klein-blue italic accent, quiet deck and
rule. Applied to About, Features, Pricing, Contact, Docs, Community and
FAQs; Blog got the serif treatment in place. Section headings carry mono
labels (MISSION / VISION / FIG. 01…), matching the home page's eyebrow
system.

- **The colour-shifting headings are gone.** A second `.gradient-text`
  rule ran a 4s infinite hue-shift (blue→purple→pink); on mobile that
  read as text changing colour while scrolling. Headings are now a static
  ink→klein-blue duotone.
- **Reveals no longer look like colour shifts.** Scroll-reveal tightened
  from 1s/42px/blur-3 to 0.65s/22px/blur-2 — elements arrive crisply
  instead of lingering half-transparent.
- **Camera zoom hidden on mobile** (pinch already dollies the canvas);
  needed a specificity bump because the base rule lands later in the
  bundled cascade.
- **The planet got a proper surface**: half-lambert shading, fresnel
  cyan rim, faint latitude wash, finer graticule, drifting rings, and an
  additive atmosphere shell hugging the limb — verified in both themes.
- TiltCard now forwards arbitrary props (data-scroll-reveal works on
  pricing cards) and its hover shadow joined the klein-blue family.
- 205 backend + 17 unit + 16 e2e tests green.

## v4.5.0 — 2026-10-28

### NORTH LIGHT retold, pages polished, subagents verified live

**Light theme rebuilt around blue ink on drafting paper.** The old NORTH
LIGHT mixed olive-green text/borders with a blue paper and a klein-blue
accent — the hue clash read as muddy. Ink, borders, glass, status colors
and shadows are now one cool blue-gray family.

- **Fixed the fuzzy checkerboard on every public page**: the
  `.public-pages .mesh-gradient` override swapped the background image but
  kept the 44px tile size, tiling a single radial into soft squares.
  Public pages now share the crisp drafting grid with the home page.
- **Sketch illustrations are theme-aware**: the hand-drawn sketches were
  unconditionally `invert(1)`-ed (right on dark, a black box on light).
  `multiply`/`screen` blend modes now drop the paper background on both
  themes.
- **HUD slimmed** (desktop and mobile): tighter paddings, 20px title,
  34px view buttons, denser readings — the Planetary Loom control panel
  takes ~30% less vertical space.
- **More motion**: staggered scroll-reveals (`--reveal-delay`) wired into
  About (team cards, CTA), Features (text columns) and Pricing (new
  "Every plan includes" strip); old-identity leftovers fixed (pink card
  shadow, maroon badge text, Veyrune "V" footer marks → "S").
- **Backend: shared HTTP connection pool** (`backend/services/
  http_pool.py`) — core.http and the MCP tool executor built a fresh
  `httpx.AsyncClient` per call (new TCP+TLS handshake every time); both
  now reuse keepalive connections, closed on app shutdown. Per-call
  timeouts, SSRF validation and redirect rules unchanged.
- **Subagent health verified against the live backend**: core.health and
  core.http runs COMPLETED; MCPFactoryAgent built the 19-tool Swagger
  Petstore MCP from the live OpenAPI spec; worker processed every task;
  ResearchAgent and OrchestratorAgent construct cleanly (their planning
  runs need an LLM key, reported honestly by /health).
- 205 backend + 17 unit + 16 e2e tests green.

## v4.4.1 — 2026-10-27

### Dashboard sweep: two real bugs found and fixed
Swept all 14 `/dashboard/*` routes at 1280×800 and 390×844 with a live
backend. Two genuine defects surfaced; both fixed and verified.

- **CSP blocked the API when the URL differs from the default.**
  `connect-src` in `next.config.ts` was a second, hardcoded copy of the
  API URL (`localhost:8000` + `127.0.0.1:8000` only). Point
  `NEXT_PUBLIC_API_URL` anywhere else and the browser silently blocks
  every fetch with an opaque "Failed to fetch" while the server logs
  nothing. The CSP now derives its origins from `NEXT_PUBLIC_API_URL`
  itself (plus the localhost/127.0.0.1 sibling spelling), so it can never
  drift from the URL the client actually calls.
- **Workspace hero hid under the header on short viewports.**
  `.workspace-home` used `justify-content: center`; when its content grew
  past the pane (mobile height, or desktop with the MCP how-to panel), the
  overflow escaped *upward*, pushing "Where should we begin?" behind the
  sticky header where it could never be scrolled to. Replaced with the
  auto-margin centering pattern (centers when it fits, top-aligns when it
  overflows) and made the pane scroll its own overflow.
- Verified: full dashboard sweep clean at both viewports; 205 backend +
  17 unit + 16 e2e tests green.

## v4.4.0 — 2026-10-19

### Draughting Lamp labels restored
- The day/night toggle labels restored to **TUNGSTEN** / **NORTH LIGHT**
  (the Planetary Loom session had changed them to NIGHT/DAY).

## v4.3.0 — 2026-10-19

### Zoom that actually zooms
- **Range widened 0.4–2.8** (was 0.8–1.6): the camera now dollies from a
  wide establishing shot to a close-up on the planet — a 7× distance range.
- **Finer steps**: 0.05 instead of 0.1 — smooth, not chunky.
- **Full 3D dolly**: the zoom scales the entire eye offset vector (not
  just Z), so the camera moves properly in 3D space.
- **Scroll-wheel zoom** on the canvas: scroll up to zoom in, down to zoom
  out — the expected interaction for any 3D scene.
- **Pinch-to-zoom** on touch devices.
- Verified: the zoom slider + scroll-wheel both drive the camera to 280%
  with the planet filling the frame.

## v4.2.0 — 2026-10-19

### Regression analytics + perf + security
- **Run regression model** (backend/services/run_analytics.py): per-agent
  EWMA baselines (expected duration ± std) learned from real run history,
  with z-score anomaly detection for statistically slow runs. Surfaced on
  the Operations page ("Expected durations" + "Slow-run anomalies").
  4 unit tests (Welford math, conservative small-n, outlier flagging).
- **GZip compression** on all API responses over 1KB — real transfer-size
  win for JSON-heavy endpoints.
- **Refresh-endpoint rate limit** — /auth/refresh now sits behind the auth
  rate limiter (was the last unthrottled credential surface).
- **security.txt** (RFC 9116) served from /.well-known/security.txt.
- **Lamp chip collapses to icon-only** on phones; topbar title shrinks.

## v4.1.1 — 2026-10-19

### Fix: stuck-blur reveal bug + softer grid
- The v3.5 blur addition to the scroll-reveal entrance was never reset by
  `.is-in-view` — revealed cards stayed permanently blurred (visible on
  About/Features). The in-view state now resets the filter to blur(0).
- Dark drafting-grid backdrop softened (lower grid contrast).

## v4.1.0 — 2026-10-19

### Page transitions + full reveal coverage
- Root template.tsx: every navigation fades up into place (Apple curve).
- Reveals swept onto faq and docs/[slug] — all pages animate on scroll.

## v4.0.0 — 2026-10-19

### The Planetary Loom — the full cyanotype identity
The home page is now a single-viewport 3D experience built to the Stitch
spec: a dark drafting hall where a **planetary loom** knits blueprints.

- **The Planet**: a metallic graticule globe (standard material, torus
  rings, wireframe shell, atmosphere) at the loom's center, turning slowly.
- **Nine threads** in three strands weave from the planet to **three
  morphing blueprint sheets** — each sheet is a displaced-plane shader whose
  surface ripples as the weave progresses, with a wireframe model
  (icosahedron/box/octahedron) assembling in front of it piece by piece.
- **Interactive**: click the planet or the foreground sheet to focus
  (camera dollies in), Esc/reset to return; camera zoom slider (80–160%);
  tempo controls (0.5×/1.0×/2.0× + pause); pointer parallax.
- **HUD chrome**: Planetary Loom panel (focus buttons, zoom, THREADS 09 /
  BLUEPRINTS 03 MORPHING, FOREGROUND WEAVE meter), scene-controls tempo
  dock, module dock (BOARD · STAMPS · BUILDS · SHEETS), axis ruler,
  corner brackets, coordinate marks.
- **Graceful degradation**: scene fallback → still illustration → retry
  button; WebGL context-lost handling; reduced-motion support.
- **Day/night**: the Draughting Lamp (NIGHT ↔ DAY) in the navbar re-skins
  the loom live — North Light floods the hall with pale paper light.
- Verified at 1440×900 and 390×844; the loom visibly animates between
  frames (planet turns, weave meter advances 50%→63%).

## v3.11.0 — 2026-10-19

### Fresh deep-audit fixes (Round 38)
- **Budget hard-stop bug**: `check_budget` treated a 0 daily limit as
  missing (`0 or default` → 1M) — the enforcement never fired at 0. Fixed
  in both layers; verified live (429 at limit 0, 201 after restore).
- **Credential-error leak**: LLM-dependent goals without any API key
  returned HTTP 500 with the raw Google ADC error. Now classified to an
  honest 503 with guidance (both /workflows and /intent handlers,
  case-insensitive), and the generic 500 never leaks provider errors.
- **TokenStatusCard guards**: partial /usage payloads crashed the settings
  page (toLocaleString on undefined) — all fields guarded.

## v3.10.0 — 2026-10-19

### Composition + scrollbars + reveals finalized
- **Planet centered** in the frame; **sheets spread** (right sheet further
  right, left sheet toward center) so the hall fills the screen with clear
  gaps — no more merging.
- **No scrollbars on the home**: the wrapper is exactly 100svh with
  overflow hidden (verified scrollHeight == clientHeight).
- **Hero hover flipped**: readable by default (80%), hover turns it
  translucent (38%) so the hall shows through while the dark backdrop
  keeps the words readable.
- **Docs card art toned down**: muted slate-navy blueprint instead of the
  oversaturated klein blue.
- **Hero de-smeared**: solid dark console (86% + light blur) instead of
  the frosted panel that smeared the bright sheet behind it.
- **Scroll reveals on every page** (public + dashboard, +15 in this round;
  deeper translate + scale + blur entrance).
- Theme assertions in the e2e suite updated to the cyanotype palette —
  **16/16 e2e** passing.

## v3.9.0 — 2026-10-19

### Readability + smoothness + the theme button
- **Draughting Lamp in the navbar** (every page): TUNGSTEN ↔ NORTH LIGHT
  toggle next to the brand, dispatching a theme event the home scene
  listens to — the 3D hall re-skins instantly.
- **Hero hover-to-read**: the hero card is translucent (42%) by default so
  the hall shows through; hovering raises it to 88% opacity so the words
  are easy to read. Verified both states in the browser.
- **Smooth blueprint reprints**: reprints now CROSSFADE — two stacked
  meshes (previous pattern fading out, new pattern fading in with a cubic
  ease-out over 1.4s) instead of a hard texture swap. No more rough jumps.
- **Apple-style reveals**: the scroll-reveal curve is now
  cubic-bezier(.16,1,.3,1) over 1s — the smooth, decisive ease.

## v3.8.0 — 2026-10-19

### The scene IS the page
- **The planet is centered**: the graticule globe now sits in the middle
  of the composition with **four wireframe cubes orbiting** it.
- **More 3D objects**: a torus-knot and a dodecahedron join the hall's
  wireframe menagerie.
- **Blueprints reprint at random times**: every 6–13 seconds a sheet
  flashes and its drafting blocks change — plans being redrawn in front
  of you (pseudo-random per variant, visible brightness sweep).
- **Hero translucent**: 52% frosted panel with light blur — the hall
  shows through the card.
- **Scroll animations on every page**: reveals swept onto all 11
  dashboard pages and every public page, with a deeper entrance
  (translate + scale + blur).

## v3.7.0 — 2026-10-18

### The knitting hall, richer
- **Planet halo**: a blue atmosphere glow around the drafting globe — it
  reads as the lit center of the hall.
- **Multi-strand weaving**: six threads now run from the planet — three
  strands woven to the big stamped sheet (landing on separate cells), two
  to the left sheet, one to the back sheet.
- **Docs flow chips tinted** for the dark theme (blueprint glass instead
  of gray); docs [slug] pages verified matching the theme.

## v3.6.0 — 2026-10-18

### Responsive home + tempo control removed
- **Chrono-Pulse tempo control removed** from the home page (the hall
  runs at its own pace; the scene keeps the mechanism internally).
- **Fits every screen**: the home stacks on phones (hero above panels),
  the axis ticks hide on small screens, the navbar keeps Sign in only
  under 480px, and the dock/secondary links wrap. Verified at 390px,
  768px, and 1280px.

## v3.5.0 — 2026-10-18

### Palette discipline + planet separation + reveals everywhere
- **Docs cards toned down**: the klein-blue card art was oversaturated —
  re-painted to a muted slate-navy blueprint with softer ink (8 SVGs).
- **Hero de-smeared**: the frosted 34% panel + heavy blur smeared the
  bright sheet behind it into a blue blob. The hero is now a solid dark
  console panel (86% + light blur) — crisp text, and the scene stays
  visible around it.
- **Planet separated**: pulled left and back so the graticule globe no
  longer merges with the sheet's edge; threads arc across the clear gap.
- **Scroll reveals on every public page** (privacy, terms, docs/[slug],
  community, get-started added; +15 reveals) — all pages animate on
  scroll now.

## v3.4.0 — 2026-10-18

### The hall shows through
- **Hero card resized** (max-width 440, tighter padding/type, smaller CTAs
  and chips) and made **more transparent** (frosted 34% panel) — the
  planet, threads, and sheets are no longer hidden behind it.
- **Planet moved into the open gap** beside the big stamped sheet — the
  graticule globe now reads clearly as the object weaving the threads
  into the blueprint (thread arcs visible landing on the sheet).

## v3.3.0 — 2026-10-18

### Planet knitting + docs re-papered
- **The planet knits**: the planet moved into the visible gap (bigger,
  1.35× scale) and its threads are now **thick glowing tubes** that draw
  progressively, carried by a bright knitting head. Where each thread
  lands on a sheet, a **wireframe patch materializes cell by cell** —
  the blueprint being knitted into existence is visible.
- **Docs card art recolored**: all 8 docs SVG flowcharts re-painted from
  pink/cream to the cyanotype palette (blueprint base, light-blue boxes
  and arrows, light ink) — light/dark both read correctly.
- Docs cards gain bracketed console frames.

## v3.2.0 — 2026-10-18

### Fixes + the weaving node
- **Integrations nav link** now opens the public Integrations page
  (it previously bounced logged-out visitors to sign-in).
- **Thread weaving nodes**: a glow sprite rides the draw head of each
  planet-thread — the draughtsman stitching the blueprint onto the sheet
  is now visible, then hides while the thread holds.
- Get Started → workspace verified end-to-end in a real browser with the
  backend running (guest creation → /dashboard); note for local runs: the
  backend must allow the frontend origin (CORS_ALLOWED_ORIGINS).

## v3.1.0 — 2026-10-18

### The Planet threads the blueprints
- **The Planet**: a drafting globe (prussian body, blueprint graticule —
  meridians and parallels) turning slowly in the hall, weaving **threads**
  that arc to every sheet and draw stitch by stitch — the blueprints are
  threaded into existence by the planet.
- Home headline reduced so the hall reads; the hero card **floats gently**
  up and down (7s cycle, reduce-data aware).
- **Public nav restored**: About Us · Features · Integrations · Docs ·
  FAQs · Blog · Contact.
- **Docs page re-papered**: the shared backdrop is now cyanotype drafting
  paper (blue grid on near-black / pale paper) for every public page —
  docs, about, features, faqs, blog, contact, integrations all match.
- **Scroll reveals** across public pages (glass panels and sections fade
  up as you scroll).

## v3.0.0 — 2026-10-18

### The Drafting Works, faithful to the spec
- **No rotation**: the camera never turns — it holds the drafting angle and
  GLIDES laterally with a gentle bob. Sheets hold their drawn angles;
  structures barely drift. All motion comes from the hall itself: the
  planner's tracer light running its path, beams sweeping, dust drifting,
  back sheets unfolding.
- **Chrono-Pulse tempo control** (top-right): 0.5x / 1.0x / 2.0x / STEP —
  a real control that scales the hall's shared animation clock (STEP
  advances one manual frame).
- **Spec HUD chips**: WORKS · 7 CREWS · 23 STAMPS · 142 SHEETS TODAY and
  TOLERANCE · HELD alongside the real ENGINE chip.
- **Module nav**: Board / Stamps / Builds / Sheets + "Sign in →".

## v2.9.0 — 2026-10-18

### Moving background + restored nav
- **The background is now moving, continuously**: the camera orbits the
  drafting hall (slow continuous angle sweep) — sheets parallax against
  each other as the viewpoint changes, every frame different. Drag the
  hall to swing the orbit manually.
- **Sheet motion amplified**: stronger vertical drift, breathing rotation
  on Z and Y — the unfold reads clearly.
- **Public nav restored**: About Us · Features · Integrations · Docs ·
  FAQs · Blog · Contact (module dock stays at the bottom of the home).

## v2.8.0 — 2026-10-18

### Observatory chrome + ambient hall (zoom removed by design)
- **Click-to-zoom removed** — the scene is pure atmosphere now: pointer
  parallax (the hall drifts as you move), sheets that breathe and
  **unfold** (rotation oscillates open like a drawing being spread), three
  planner light streams tracing their paths, teal wireframes, beams, dust.
- **Axis ruler strip** under the nav (AXIS::X.DRAFT · tick marks ·
  CALIBRATED // ISO-216-A1) and **corner coordinate marks** — the
  reference's observatory chrome.
- Dock links get hover lift + glow; panels tightened; the whole home is
  one uncluttered viewport over the living hall.

## v2.7.0 — 2026-10-18

### Vivid drafting hall (matched to the reference)
- **Big saturated sheets**: blueprint planes reworked — deep blue base with a
  diagonal sheen, fine + heavy white grids, drafting blocks (X-marked
  rectangles, reticles, "COMMUNICATION LATTICE" / "FIELD MODULES" / "TOR
  ANTENNAE" labels), bottom title strip, and the **FOR APPROVAL stamp
  printed on the sheet** (rotated, validated line).
- Sheets repositioned large and tilted like the reference: foreground
  stamped sheet right, mid sheet left, back sheet top.
- **Diagonal light beams** from the top (additive shafts, breathing).
- **Teal icosahedron** + cone wireframes (the reference's mixed accents);
  tracer glow dot printed on each sheet.
- Low-angle parked camera (floor visible, sheets above the horizon).
- Click-to-zoom verified on the new sheets (readout + camera dolly).

## v2.6.0 — 2026-10-18

### The scene IS the navigation (interactive observatory)
- **Click-to-zoom**: clicking a blueprint sheet or wireframe structure dollies
  the camera in and raises a focus readout — "SHEET-002 // EXECUTION PLAN ·
  OPEN BUILDS →" — linking straight into the matching module. Click the hall
  or press Esc to pull back. Hover highlights targets with a lens cursor;
  the camera drifts with the pointer (observatory parallax).
- **Observatory chrome**: film-grain overlay (SVG turbulence), frosted glass
  panels, bracketed/chipped console frames (corner brackets in the accent
  blue), HUD chips in mono.
- **Palette**: light-blue accent (#8ab4ff dark / prussian light) with a
  single warm-orange accent reserved for the human-approval surfaces
  (FOR APPROVAL stamp, ENGINE lamp, APPROVALS chip).
- **Home tightened**: the scene shows through (pass-through UI layer — the
  fix that made click-to-zoom possible at all), panels concise, secondary
  page links (About/Features/Docs/FAQs/Contact) under the module dock.

## v2.5.0 — 2026-10-18

### SANDTABLE — "The Drafting Works" (Cyanotype redesign)
- **Renamed again, by design**: Sandtable (the Operations Room). A sandtable
  is where operations are rehearsed before they are real — exactly what the
  product does with your work.
- **Cyanotype theme**: near-black drafting hall `#04060B`, klein-blue accent
  `#3E6BFF`, fonts Fraunces (display) + Space Grotesk (body) + JetBrains Mono
  (telemetry). Day = "North Light" (pale drafting paper, prussian ink);
  night = "Tungsten". The lamp toggle in the nav.
- **Full-viewport WebGL scene** (Three.js / React Three Fiber, dynamic
  import): giant blueprint sheets hover and unfold; light streams trace the
  planner's path; wireframe structures assemble; drafting primitives stand
  in the hall; grid floor + graphite dust. No cosmos, no stars — pure
  drafting works.
- **Home page rebuilt clean**: one viewport — glass hero card ("Say it.
  It's drawn. It's built."), two honest panels (The Planner, Stamp Status
  // FOR APPROVAL), HUD chips with REAL engine state from /health, and the
  module dock: BOARD · STAMPS · BUILDS · SHEETS.
- Module naming across the app: Board (chat) · Stamps (integrations) ·
  Builds (runs) · Sheets (operations/metrics).

## v2.4.0 — 2026-10-18

### Organizations UI
- `/dashboard/orgs`: create orgs, add members by email, the role ladder
  inline (owner-immutable), remove members, and **run oversight** — a
  read-only view of member runs with scoped fields. Sidebar entry +
  2 e2e specs (14 e2e total). Visually verified in a real browser:
  the renamed brand, forge core, and both themes render correctly.


### Product renamed: Veyrune → **Sandtable**
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
