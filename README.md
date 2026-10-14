> **Deploy Veyrune:** Follow the [Google Cloud + Vertex AI deployment guide](docs/deploy-gcp.md). It covers a non-upgraded $300 trial, API, pull worker, frontend, secrets, and live verification. [Current readiness and remaining gates](docs/production-readiness.md).

# AgentOS

**Tell it what you want. It builds the tools and does the work.**

AgentOS is an autonomous AI workspace. You describe an outcome in plain language. A planner turns that into a DAG of tasks. If the tools needed to finish the work do not exist yet, the MCP factory **builds them**, probes them live, registers them, and the orchestrator continues in the same run.

It is not a chatbot with canned replies. Runs hit live HTTP APIs, a real browser, site health checks, an encrypted vault, resume generation, and an action timeline of what the agents actually did.

**Stack:** Next.js (port 3000) · FastAPI (port 8000) · SQLite locally · Firestore on Cloud Run · Gemini (AI Studio key locally, or Vertex on GCP).

## Local and cloud

The same codebase runs in both places. One setting switches storage; Gemini follows the key.

| | Laptop | Google Cloud |
| --- | --- | --- |
| How | `python main.py` + `npm run dev` | Cloud Run (`docs/deploy-gcp.md`) |
| Storage | `STORAGE_BACKEND=sqlite` | `STORAGE_BACKEND=firestore` |
| Gemini | `GEMINI_API_KEY` (AI Studio) | Leave the key empty; Vertex uses `GOOGLE_CLOUD_PROJECT` + the Cloud Run service account |
| Optional provider | `LLM_PROVIDER=groq`, `GROQ_API_KEY`, `GROQ_MODEL` (Groq); `LLM_PROVIDER=huggingface`, `HF_TOKEN`, `HF_MODEL` (HF Inference Providers); or `XAI_API_KEY` + `GROK_MODEL` for shared-call fallback | Store the selected provider key in Secret Manager if enabled |
| Secrets | `.env` (gitignored) | Secret Manager |
| Data | `data/agentos.db` | Firestore (survives scale-to-zero) |

Repository: [umangvijay/AgentOS-an-Automation-tool](https://github.com/umangvijay/AgentOS-an-Automation-tool)

## Features

- **Dynamic MCP factory** — three ways to get tools: an OpenAPI URL, a description of any HTTP API with no spec, or a website with no API (origin-locked Playwright tools). Not a reverse-engineered private API.
- **Chat-first automation** — workspace chat plans, builds missing integrations mid-run, then calls the new tools. Follow-up messages reuse the catalog.
- **Orchestrator + DAG engine** — planner *is* the decomposer. Core nodes (HTTP, health, chat) run without a model.
- **Self-healing** — timeouts, network errors, and 429/quota retry. CAPTCHA, OTP, and MFA pause for you instead of being treated as failures.
- **Human-in-the-loop** — AgentOS never fills CAPTCHA, SMS OTP, or MFA. Complete the check, then Resume.
- **Vault** — AES-256-GCM credentials. After save, the API returns names only.
- **ATS resume** — scan against a job description, tailor from notes, HTML preview and download.
- **Studio** — site health, debug (code is not executed), generate a downloadable site or app.
- **Action timeline** — SSE events from the live run, not a fake progress bar.
- **Guest workspace** — try the product without creating an account first.

### MCP from chat

| You have | You type | What gets built |
| --- | --- | --- |
| OpenAPI URL | `Create MCP tools from https://…/openapi.json then list …` | HTTP tools from the spec, live-probed, then called |
| HTTP API, no spec | `Build MCP tools for [app] so I can [list / get / create …]` | HTTP tools on the public host (GitHub, Open-Meteo, PokeAPI, …) |
| Website, no API | Vault login, then `Create MCP tools for https://…`, then `Log in with vault credential NAME and use runOnSite …` | Browser tools (`runOnSite`, `login`, …) locked to that origin |

Same three paths exist on **Integrations → Create**.

## Architecture

Next.js is the workspace UI. FastAPI owns auth, the vault, the MCP registry, and the workflow engine. The engine plans a DAG, the MCP factory fills gaps, and Playwright runs only on a locked origin.

```mermaid
flowchart TD
  user[You] --> ui[Next.js workspace]
  ui -->|REST SSE cookies| api[FastAPI]
  api --> auth[JWT RS256]
  api --> vault[AES-GCM vault]
  api --> engine[Workflow engine]
  engine --> sqlite[(SQLite)]
  engine --> planner[Planner]
  planner --> dag[Task DAG]
  dag --> core[Core nodes: HTTP health chat]
  dag --> orch[Orchestrator]
  orch --> catalog[MCP catalog]
  catalog -->|missing| factory[MCP factory]
  factory --> httpMcp[HTTP tools]
  factory --> webMcp[Website Playwright tools]
  orch --> webAgent[WebAgent]
  webAgent -->|CAPTCHA OTP MFA| hitl[Pause for you]
  engine --> sse[SSE timeline]
  sse --> ui
```

### Cloud runtime and durable event flow

The cloud topology is different from the local in-process worker. Cloud Run
serves HTTP requests; a separate long-running Cloud Run Worker Pool pulls from
Pub/Sub. Both processes must use Firestore and the same project configuration.
The API and worker use separate service identities and least-privilege IAM.

```mermaid
flowchart LR
  User --> Web[Next.js]
  Web -->|REST / SSE| API[Cloud Run API]
  API --> DB[(Firestore)]
  API -->|publish| PS[Pub/Sub topics]
  PS -->|pull subscriptions| Worker[Cloud Run Worker Pool]
  Worker --> DB
  Worker -->|Vertex AI ADC| Gemini[Gemini on Vertex AI]
  Worker --> Tools[MCP / HTTP / origin-locked browser tools]
  Worker -->|state + events| DB
  Web <-->|SSE updates| API
  Tools --> HITL[Approval / challenge checkpoint]
  HITL -->|resume command| API
```

The event path is at-least-once: handlers must be idempotent, and persistent
failures need bounded retries and dead-letter handling. This diagram describes
the intended GCP deployment; it is **not evidence that a live GCP project has
been deployed or verified**. See [production readiness](docs/production-readiness.md)
and [GCP deployment](docs/deploy-gcp.md).

## Flowchart

What happens after you send a goal.

```mermaid
flowchart TD
  goal[Goal in chat] --> intent{Direct plan?}
  intent -->|health or GET| coreNow[core.health / core.http]
  intent -->|needs tools or reasoning| plan[Planner builds DAG]
  plan --> exists{Catalog already has a tool?}
  exists -->|yes| run[Orchestrator calls it]
  exists -->|no| kind{What did you provide?}
  kind -->|OpenAPI URL| spec[Fetch and normalize spec]
  kind -->|HTTP API no spec| sketch[Sketch or generate OpenAPI]
  kind -->|Website no API| browser[Plan origin-locked browser tools]
  spec --> probe[Live GET probe]
  sketch --> probe
  browser --> register[Register MCP]
  probe --> register
  register --> run
  coreNow --> out[Result + timeline]
  run --> challenge{Auth wall?}
  challenge -->|CAPTCHA OTP MFA| pause[WAITING_APPROVAL]
  pause --> you[You complete check]
  you --> resume[Resume]
  resume --> run
  challenge -->|no| out
```

## Data flow

```mermaid
sequenceDiagram
  participant You
  participant UI as Next.js
  participant API as FastAPI
  participant DB as SQLite
  participant P as Planner
  participant F as MCP factory
  participant X as Executor
  participant W as WebAgent

  You->>UI: High-level goal
  UI->>API: POST /api/v1/workflows
  API->>DB: Persist run and tasks
  API->>P: Build DAG
  alt Integration missing
    P->>F: url / prompt / website
    F->>F: Probe or lock origin
    F->>DB: Register tools
  end
  P->>X: Execute nodes
  alt HTTP API
    X-->>API: Live JSON
  else Website
    X->>W: Playwright on locked origin
    W-->>API: Page result or HITL pause
  end
  API-->>UI: SSE events
  UI-->>You: Timeline and deliverable
```

Local stores: `data/agentos.db` (users, runs, tasks, MCP registry), vault ciphertext in SQLite, JWT keys under `backend/security/keys/` (gitignored). Optional cloud persistence is Firestore — see [docs/architecture.md](docs/architecture.md).

## Quick start

```bash
cd AgentOS
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # set GEMINI_API_KEY
.venv/bin/python main.py
cd frontend && npm install && npm run dev
```

- App: http://localhost:3000
- API: http://127.0.0.1:8000
- In-app docs: http://localhost:3000/docs

Set `LLM_PROVIDER=groq` and `GROQ_API_KEY` or `LLM_PROVIDER=huggingface` and `HF_TOKEN` to use those OpenAI-compatible providers for shared model calls and ADK planner/orchestrator tasks. Hugging Face routes through `https://router.huggingface.co/v1`; use a hosted model ID such as `openai/gpt-oss-120b` in `HF_MODEL` (no model upload to this code repository is needed). For Gemini use `LLM_PROVIDER=gemini` with `GEMINI_API_KEY`; for GCP Vertex use `LLM_PROVIDER=vertex` and the configured project/service account. In `auto` mode Gemini takes precedence, then Vertex, Groq, and Hugging Face. Do not commit local environment files. Cloud Run + Vertex + the $100 kill switch: [docs/deploy-gcp.md](docs/deploy-gcp.md).

## Docs

- [Architecture](docs/architecture.md)
- [MCP builder](docs/mcp-builder.md)
- [Automation](docs/automation.md)
- [User guide](docs/user-guide.md)
- [Security](docs/SECURITY.md)
- [Production readiness and improvement plan](docs/production-readiness.md)
- [Environment setup](docs/environment-setup.md)
- [Google Cloud deploy](docs/deploy-gcp.md) — redeem credits, Vertex Gemini (no API key), Cloud Run, **$100 kill switch**
- [Diagrams](docs/diagrams/)

## Honest limits

- Website MCP is **UI automation**, not a hidden official API.
- CAPTCHA, SMS OTP, and bank MFA require you. AgentOS will not complete them for you.
- Paid APIs (for example live Stripe charges) need your own keys in the vault.
- Vertex AI, Firestore, Pub/Sub, and the cloud worker path require project
  credentials and IAM. Without them, those cloud features cannot be called
  live; local passing tests do not prove provider or cloud integration health.
- The current system is not yet enterprise production-ready. Review the
  verified controls, known gaps, and release gates in
  [docs/production-readiness.md](docs/production-readiness.md).
