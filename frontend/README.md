# AgentOS frontend

Next.js/React workspace with REST/SSE integration, workflow inspection, connectors,
organizations, deliverables, and a dynamically loaded React Three Fiber scene.
Use package.json for version constraints and package-lock.json for resolution.

## Development

From frontend/, run npm ci and npm run dev. The UI defaults to
http://localhost:3000; start the backend separately from the repository root.
Set NEXT_PUBLIC_API_URL to the intended API base including /api/v1.
Public build variables must never contain provider secrets or private keys.

Read [AGENTS.md](AGENTS.md) and installed Next documentation before framework
changes. Online documentation may describe a newer release.

## Code map

| Path | Responsibility |
|---|---|
| src/lib/api.ts | Backend client and response handling |
| src/lib/auth-session.ts | Session storage and refresh coordination |
| src/lib/auth-context.tsx | React authentication state |
| src/app/dashboard/workspace/[run_id]/page.tsx | Run workspace |
| src/app/dashboard/integrations/ | Build, credentials, coverage and integration state |
| src/app/dashboard/orgs/page.tsx | Invitations and roles |
| src/components/ExecutionTimeline.tsx | Execution events |
| src/components/WorkflowGraph.tsx | DAG presentation |
| src/components/CyanotypeScene.tsx | Existing 3D scene and fallback |
| src/app/drafting.css and src/app/globals.css | Visual system |

## Checks

```bash
npm run lint -- --max-warnings=0
npm test
npm run typecheck
npm run build
npm run test:e2e:production
```

These are commands to execute, not newly recorded pass results. Production E2E
needs the built app and supported Playwright browsers. API-mocked tests establish
UI behavior, not live backend/provider integration. Add real-backend journeys
and concurrent-tab session checks for launch acceptance.

## Planned frontend work

[Roadmap phases 18–19](../docs/full-stack-roadmap.md) cover shared run states,
reconnection, preserved drafts, session races, consistent forms, accessibility,
performance and optional 3D workflow exploration. Earlier phases specify recovery,
uncertain-outcome, browser, connector-evidence, evaluation and experiment surfaces.

Keep scenes lazy-loaded, suspend hidden/offscreen work, provide reduced motion
and WebGL fallback, and keep essential actions outside canvas. Preserve mobile
scrolling; no new mobile scene-zoom gestures are planned. Illustrative animation
must not imply live telemetry or successful recovery.

Suggested routes/components are proposals. Publish capabilities only after
backend and frontend acceptance checks pass.
