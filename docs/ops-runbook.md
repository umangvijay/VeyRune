# Sandtable — Operations Runbook

Production topology on Cloud Run: `veyrune-api` (FastAPI, RUN_WORKER=0),
`veyrune-worker` (separate consumer, Pub/Sub), `veyrune-frontend`
(Next.js standalone), Firestore, Pub/Sub, Secret Manager.

**Verification note — 31 October 2026:** confirm actual project, resource type,
image digest, configuration and permissions before using any command. This
document is not evidence that a drill passed. Record outcomes in
[RELEASE_EVIDENCE.md](RELEASE_EVIDENCE.md); roadmap phase 20 defines acceptance.

## Deploy

```bash
gcloud auth login && gcloud config set project <PROJECT_ID>
bash scripts/gcp/deploy-safe.sh          # image-only; preserves env/secrets/IAM
python3 scripts/gcp/verify-p0-production.py https://<veyrune-api-url>
```

Never redeploy with `scripts/gcp/deploy-api-cloudshell.sh` against an
existing service: its `--set-env-vars` wipes the service's env config.

## Verify health after any deploy

```bash
curl -s https://<api-url>/api/v1/health | jq .
# expect: status=healthy, factory_initialized=true, storage=firestore,
#         llm_status.status in (catalog_ok, vertex), commit=<revision sha>
```

`llm_status=missing` means no Gemini/Vertex credentials — LLM-dependent
features degrade with honest errors; LLM-free actions (site health, GET,
OpenAPI builds) keep working.

## Rollback

Cloud Run keeps every revision:

```bash
gcloud run services describe veyrune-api --region us-central1 \
  --format='value(status.traffic[0].revisionName)'   # current
gcloud run services update-traffic veyrune-api --region us-central1 \
  --to-revisions <PREVIOUS_REVISION>=100
```

Choose rollback or containment according to the incident. Additive schemas alone
do not guarantee old-code compatibility: event formats, policy, data semantics,
and migrations also matter. Test rollback against the actual candidate and data.

## Kill switch

`scripts/gcp-killswitch/` contains emergency-stop tooling that must be checked
against the deployed topology. The pull consumer is a Cloud Run Worker Pool,
not an HTTP service; do not use a service-scaling command as its stop procedure.

Before launch, rehearse and record resource-specific steps to stop new schedule
and API submissions, pause worker consumption, contain already-running browser
or provider actions, and verify no further expenditure. Preserve uncertain
effect records for reconciliation. Restart only after checking backlog and
duplicate-delivery behavior. Do not assume stopping intake cancels in-flight work.

## Runbook: common incidents

**429s spiking on /workflows** — inspect the specific refusal, user/tenant scope,
replica count, queue pressure and accounting health. Local counters and token
checks do not by themselves prove global enforcement. Do not raise limits before
identifying the source and verifying spending reservations.

**Model quality regressions** — inspect `GET /api/v1/usage/models` alongside
verified task outcomes. Runner success can differ from useful completion. Use
documented configuration/rollback procedures; no policy-reset API is implied here.

**Memory/JSON 5xx with hostile payloads** — should not happen: the
canonical JSON layer (`backend/security/json_safety.py`) plus surrogate
repair at `sanitize_text` cover storage and responses. If seen, capture
the payload and file against the sanitizer.

**Site-health misses on datacenter-blocked sites** — tune
`HEALTH_USER_AGENT`; a dedicated egress pool is the deploy-level fix.

**Scheduled runs piling up** — schedules have a max-concurrency guard
(skips with `SCHEDULE_SKIPPED` notifications) and skip-missed catch-up;
a backlog means the worker was down — check worker logs and Pub/Sub
subscription backlog.

## Data retention

`RETENTION_DAYS` (default 90) purges timeline events and audit rows in
the worker's daily pass. Workflow runs are never auto-deleted. Export
before large deletions if compliance requires it.

## Model selection (A/B guidance)

The observations below are historical, not current model recommendations.
Do not select or upgrade providers from these tiny samples. Phase 12 requires
representative outcomes; phase 14 adds controlled routing evaluation.

The adaptive policy (`GET /api/v1/usage/models`) re-ranks the model chain
from real task outcomes. Live A/B evidence from the audit (n=1 each,
indicative only):

- `gemini-3.8-flash` (default): planned both sites of a multi-part goal
  and wrote the synthesis (~26s).
- `gemini-4-argon`: ~2× faster (~12s) but dropped one site from the plan
  and skipped the synthesis.

Policy: keep `gemini-3.8-flash` as the default until a per-goal-template
A/B (≥20 runs each) shows argon planning multi-part goals reliably. The
bandit will surface the difference automatically in
`failed_tasks_by_agent` and the leaderboard once production traffic
accumulates — check it before changing defaults manually.
