# Implementation status — 2026-10-11

This is a partial implementation of the production improvement program. It is
not a release certification. No deployment or Git push was performed.

## Implemented and regression tested

- Workflow API accepts ADK content events without an `output` attribute.
- Missing output references fail explicitly instead of becoming empty strings.
- Whole-value references preserve dictionaries, lists, booleans, numbers and null.
- References require completed source tasks and valid dependency ancestry.
- Plans reject duplicate IDs, missing dependencies, unsupported core nodes,
  empty workflows, and missing mandatory inputs.
- Model-generated invalid plans receive at most one repair attempt, followed by
  the same validation. Invalid repaired plans never enter the execution queue.
- Summary nodes receive actual dependency results automatically. Results are
  identified as untrusted data in the prompt.
- Explicit health-and-summary requests create probes for all provided URLs and
  a dependent model-written summary, without inventing output field names.
- Queue triggers cannot execute tasks before their dependencies complete.
- Configurable task count, retry and timeout limits reject excessive plans.
  These are execution limits, not dollar budgets or measured token accounting.
- Direct HTTP write nodes pass through the existing exact-action approval gate.
  Header values are bound by a digest instead of copied into approval records.
  Approval behavior follows the configured autonomy policy.
- Explicit Vertex selection takes precedence over stored Gemini keys for shared
  generation and embeddings, matching the ADK provider path.
- Integration cards distinguish disabled, unverified, failed checks, open
  circuits, and last-check success; users can refresh server status.

## Evidence and its limits

The regression suite includes workflow API event parsing, plan repair failure,
required inputs, data-reference types, dependency scheduling, HTTP approval,
and Vertex client selection. A real temporary SQLite workflow executes two
nodes, propagates results, suppresses duplicate completed execution and retains
its final result after reopening the database. Model responses in these new
regression tests are substituted to avoid costs and nondeterministic tests.
That is not live inference evidence, Pub/Sub crash recovery, or a cloud test.

Frontend TypeScript and the changed page's lint check pass. Visual browser QA
of this change and live deployment testing are outstanding.

## Still required before a production claim

- [ ] Repeat complete autonomous MCP creation and tool use with live providers,
      unfamiliar APIs, authenticated connectors, and generated deliverables.
- [ ] Validate plans semantically across a representative evaluation set;
      structural validation cannot ensure the plan fulfills every requested goal.
- [ ] Add and verify passkeys/MFA enrollment, recovery and revocation UI.
      Existing browser OTP/MFA pauses are not account MFA.
- [ ] Add connector version history, pinned execution versions and rollback.
- [ ] Add durable per-run token/cost accounting and enforced spending budgets.
- [ ] Verify all external writes have approval and idempotency coverage;
      direct HTTP approval alone does not provide exactly-once external effects.
- [ ] Verify artifact existence, content and download authorization end to end.
- [ ] Implement and test isolated tool/browser execution and enforced egress.
- [ ] Expand prompt-injection and cross-user access regression cases.
- [ ] Verify user/session revocation, password recovery and ownership checks
      through the authenticated deployed API.
- [ ] Add tenant-aware operational dashboards and actionable alerts for stuck
      runs, queue age, completion rate, recovery, latency and cost.
- [ ] Exercise backup restore, key rotation and deployment rollback.
- [ ] Test Cloud Run API + Firestore + Pub/Sub worker with Vertex identity,
      duplicate delivery, process termination, approval resume and cancellation.
- [ ] Load testing, dependency/secret scanning, external security review and
      incident response rehearsal.

## Cloud validation handoff

The owner will push and deploy manually. Obtain the deployed API URL and an
approved test identity through the normal login flow; never put credentials in
this document or fixtures. Verify API and worker use the same revision and
storage. Run a read-only workflow, then an MCP build-and-use workflow. Confirm
saved results, events and downloads in the UI. Only then test recovery, writes
with explicit approval, concurrency and spending controls in staging.

Set `LLM_PROVIDER=vertex` to select ADC explicitly. Vertex project permissions,
model access and worker identity must be verified in the actual environment.

## Follow-up implementation — 2026-10-11

- Added immutable definition checkpoints to SQLite and Firestore adapters.
  New internal connector builds save a checkpoint. History endpoints enforce
  access checks and return metadata, not definition or credential bodies.
- Added save-version and restore controls to connector details. Restore creates
  a new disabled connector owned by the caller with no attached credentials.
  It does not mutate active runs or constitute in-place version rollback.
- Added an Operations page backed by the authenticated user's latest 200 runs:
  completion rate, median completion time, failures by agent and attention flags.
  Costs are explicitly unavailable; long-running flags are not queue metrics.
- Added root Git/Docker ignore rules for credentials, data and dependency output;
  narrowed worker image copies and configured API/worker images for non-root use.
  Ignore rules do not remove secrets already tracked in another checkout.
- Fixed missing ownership on agent-created deliverables and the dictionary/string
  mismatch in cloud file uploads. Cloud metadata and files now commit together.
- Added artifact checksums, manifest membership checks, reserved-path protection
  and attachment downloads with no-sniff/no-store headers. Legacy artifacts have
  no retroactive integrity guarantee; missing-owner artifacts need regeneration.
- Added `scripts/verify_deployed_workflows.py` for authenticated staging tests of
  persisted health + model summary, optionally followed by MCP build-and-use.
  It reads a process environment token, prints only sanitized status and run IDs,
  and never automatically approves actions. It creates test runs/connectors and
  incurs model usage when run. Supply the deployed API base including `/api/v1`.

Verification: 135 backend tests pass, including SQLite checkpoint/restore,
owner isolation, partial-restore cleanup, artifact ownership/integrity/cloud batch
shape and operational metrics. Firestore behavior has not been tested against
live GCP. The local Docker daemon is stopped, so image build/run verification is
outstanding. MFA/passkeys, enforceable spending budgets, real sandbox/egress
isolation, deployment recovery/load tests and external review remain outstanding.
