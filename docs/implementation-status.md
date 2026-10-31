# Implementation status

Snapshot: 31 October 2026. Committed baseline: `3ef8063` (v5.5.0).
This is source status, not a fresh test report. Earlier numerical results belong
to their original revision/environment; see [release evidence](RELEASE_EVIDENCE.md).
Application files are changing concurrently. Recheck diffs before implementation;
this documentation task does not certify those changes.

## Implementation and remaining acceptance

| Area | Present in the reviewed baseline | Remaining acceptance |
|---|---|---|
| Identity | Active-account checks, revocation, invitation UI | All membership paths, role regressions and atomic accept/revoke |
| Tenancy | Run org_id and personal-run filtering | Complete resource matrix and explicit sharing lifecycle |
| Accounting | Usage ledger and budget checks | Durable commits, atomic reservations, complete paid-call coverage |
| Abuse controls | Bounded local counters | Shared limits, concurrency quotas and overload behavior |
| Workflows | DAGs, leases/fencing, retries and build records | Shared queued build lifecycle and cloud failure drills |
| Side effects | Uncertain quarantine and reconciliation primitives | Provider receipts, controlled resolution and direct-tool coverage |
| Connectors | Trust gate, read evidence, revision/provenance metadata | Accurate coverage, credential-version binding and write/auth tests |
| Standalone MCP | Packaging and protocol-status helpers | Immutable content verification, exact dependencies and isolated runner |
| Browser | Observe/decide/act and challenge pauses | Cleanup, session ownership, action approvals and robust DOM support |
| Learning | UCB-style ranking and epsilon exploration | Verified rewards, persistent evaluations and controlled experiments |
| Frontend | Workspace, session coordination and 3D scene | Real-backend/multi-tab checks, accessibility and state consistency |
| Operations | Build/Terraform configuration and verification scripts | Candidate-bound cloud, scan, restore, rollback and load evidence |

## Working-tree fixes observed at the start of this documentation task

- Legacy direct membership creation changed to a pending-invitation response.
- SQLite usage recording gained a commit call.

These were not newly regression-tested here. Additional implementation may arrive
while documentation is being written. In particular, review transaction ownership
on shared SQLite connections and verify all callers of any reservation API.

## Earlier focused reproductions

- SQLite usage remained in an open transaction and disappeared on rollback.
  The newer fix requires separate-connection/restart verification.
- Modified standalone server contents still passed mark_deployable after passing
  test statuses were recorded. Content-bound trusted evidence is required.
- Modified operations failed execution validation but still counted as tested
  coverage. Displayed coverage must share the execution predicate.

These focused checks do not replace complete regression suites. The current
[roadmap](full-stack-roadmap.md) provides file maps, acceptance criteria and order.
Prior implementation narratives remain in Git history; this snapshot supersedes
the older blanket “audit items closed” banner.
