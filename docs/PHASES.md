# Implementation phases

Updated 31 October 2026. The former “all 14 phases complete” statement is
superseded. A component's existence does not establish production behavior.
The authoritative plan is [the full-stack roadmap](full-stack-roadmap.md).

## Mapping from the earlier A–G plan

| Earlier phase | Detailed phases | Outcome |
|---|---|---|
| A — Correctness | 00–03 and evidence fixes in 06–07 | Scope, identity, spending and shared limits |
| B — Durability | 04–09 | Commands, reconciliation, connectors and browser execution |
| C — Release evidence | 00 and 20 | Candidate-bound tests and operational drills |
| D — Advanced execution | 09–11 and 15 | DOM, verified ReAct, recovery and delegation |
| E — Learning | 12–14 | Evaluations, controlled improvement and contextual routing |
| F — Product expansion | 16–19 and 21 | Memory, deliverables, React, 3D and templates |
| G — Enterprise options | 21 with phase 20 verification | Provisioning and governance for selected customers |

## Execution order

1. Establish phase 00 evidence and supported launch scope.
2. Complete identity, spending, rate-limit, command and effect safety (01–05).
   Verify current working-tree fixes before duplicating implementation.
3. Complete connector/browser/runtime gates required by launch scope (06–09).
4. Add verified ReAct and recovery (10–11); wire evaluations (12) early enough
   to measure them. Memory and deliverables require their own isolation checks.
5. Develop React reliability and design (18–19) alongside agreed API contracts.
6. Close phase 20 evidence before public launch of the selected scope.
7. Expand learning, delegation and optional products after prerequisites pass.

Instrumentation starts early; phase 20 is the final release gate. Optional
learning and enterprise phases are not universal launch prerequisites.
Each detailed phase names files, steps, acceptance tests and rollout conditions.

## Status convention

- **Present:** code exists; correctness still needs evidence.
- **In progress:** an implementation change is visible but not accepted.
- **Verified locally:** named tests passed for a named revision/environment.
- **Verified in staging:** deployed journeys and failure checks passed.
- **Planned:** design only; no functionality implied.
- **Excluded:** deliberately outside the supported release.

See [implementation status](implementation-status.md),
[release evidence](RELEASE_EVIDENCE.md), and
[production readiness](production-readiness.md).
