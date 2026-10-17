# Veyrune — Operations Runbook

Production topology on Cloud Run: `veyrune-api` (FastAPI, RUN_WORKER=0),
`veyrune-worker` (separate consumer, Pub/Sub), `veyrune-frontend`
(Next.js standalone), Firestore, Pub/Sub, Secret Manager.

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

Rollback is the first response to a bad deploy — database migrations in
this codebase are additive (new tables/columns only), so older revisions
keep working against newer schemas.

## Kill switch

`scripts/gcp-killswitch/` contains the emergency-stop tooling. Use when
active abuse (quota burn, runaway schedules) must stop faster than a
rollback: pause the worker service first (stops all execution), then the
API if needed:

```bash
gcloud run services update veyrune-worker --region us-central1 --min-instances=0 --max-instances=0
```

## Runbook: common incidents

**429s spiking on /workflows** — the per-user rate limit (10/min) or
daily token budget doing its job. Confirm in audit log
(`GET /api/v1/admin/audit?event_type=...`); raise per-user limits via
admin if legitimate.

**Model quality regressions** — check the learned routing:
`GET /api/v1/usage/models`. The UCB1 policy shifts traffic away from
failing models automatically; `POST`-reset is admin-only via the repo if
ever needed.

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
