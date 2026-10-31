"""Outcome Verifier (audit §9, first subagent): a bounded, read-only
checker that validates task outputs against declared acceptance criteria.

Permission boundary: READ-ONLY by default. It never executes tools, never
grants permissions, and never repairs — it only PASS/FAIL/NEEDS-REVIEW
with reasons, so a model cannot approve its own work by declaring "done".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AcceptanceCriterion:
    kind: str                     # non_empty | contains | regex | http_ok | artifact_exists | schema_keys
    value: Any = None
    description: str = ""

    def check(self, output: Dict[str, Any]) -> tuple[bool, str]:
        if self.kind == "non_empty":
            target = output.get(self.value) if isinstance(self.value, str) else output
            ok = bool(target) and str(target).strip() != ""
            return ok, "" if ok else f"expected non-empty '{self.value or 'output'}'"
        if self.kind == "contains":
            haystack = str(output.get("reply") or output.get("message") or "")
            ok = str(self.value).casefold() in haystack.casefold()
            return ok, "" if ok else f"output does not mention '{self.value}'"
        if self.kind == "http_ok":
            code = output.get("status_code")
            ok = isinstance(code, int) and 200 <= code < 300
            return ok, "" if ok else f"expected 2xx, got {code}"
        if self.kind == "artifact_exists":
            ok = bool(output.get("artifact_id") or output.get("file_path"))
            return ok, "" if ok else "no artifact was produced"
        if self.kind == "schema_keys":
            keys = output.keys()
            missing = [k for k in (self.value or []) if k not in keys]
            return not missing, "" if not missing else f"missing keys: {', '.join(missing)}"
        return False, f"unknown criterion kind: {self.kind}"


@dataclass
class VerificationResult:
    verdict: str                  # pass | fail | needs_review
    reasons: List[str] = field(default_factory=list)
    checked: int = 0

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"


class OutcomeVerifier:
    """Read-only verification of task outputs. The engine consults this
    before marking a deliverable-producing task complete (audit §5 stage 1
    outcome measurement)."""

    def verify(self, output: Optional[Dict[str, Any]],
               criteria: Optional[List[AcceptanceCriterion]] = None) -> VerificationResult:
        output = output or {}
        reasons: List[str] = []
        checked = 0

        # Baseline postcondition every task output must satisfy.
        has_content = any(
            isinstance(v, (str, dict, list)) and v
            for v in output.values()
        )
        if not has_content:
            return VerificationResult("fail", ["output is empty"], 0)

        for criterion in (criteria or []):
            checked += 1
            ok, reason = criterion.check(output)
            if not ok:
                reasons.append(reason or f"criterion '{criterion.kind}' failed")

        if not criteria:
            return VerificationResult("pass", [], 0)
        if reasons:
            # Needs-review (not hard fail) when SOME criteria passed: the
            # operator decides, per §5 — verification never silently passes.
            verdict = "needs_review" if checked > len(reasons) else "fail"
            return VerificationResult(verdict, reasons, checked)
        return VerificationResult("pass", [], checked)
