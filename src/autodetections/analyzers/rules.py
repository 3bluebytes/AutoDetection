from __future__ import annotations

import re
from dataclasses import dataclass

from autodetections.models import AnalysisConfig, CaseResult, Evidence, LogArtifact, RuleFinding


@dataclass(slots=True)
class Rule:
    category: str
    component: str
    summary: str
    confidence: float
    patterns: tuple[str, ...]


class RuleAnalyzer:
    RULES: tuple[Rule, ...] = (
        Rule(
            category="kernel_panic",
            component="kernel",
            summary="Kernel panic or oops signature was detected.",
            confidence=0.97,
            patterns=(r"kernel panic", r"\boops\b", r"call trace:", r"BUG:\s+unable to handle"),
        ),
        Rule(
            category="memory_issue",
            component="memory",
            summary="Memory pressure or OOM signature was detected.",
            confidence=0.93,
            patterns=(r"out of memory", r"\boom-killer\b", r"memory leak", r"cannot allocate memory"),
        ),
        Rule(
            category="qemu_crash",
            component="qemu",
            summary="QEMU crash or fatal assertion was detected.",
            confidence=0.92,
            patterns=(r"qemu:.*segmentation fault", r"fatal:", r"assertion.*failed", r"qemu unexpectedly closed"),
        ),
        Rule(
            category="libvirt_error",
            component="libvirt",
            summary="libvirt error signature was detected.",
            confidence=0.9,
            patterns=(r"libvirtError", r"error\s*:\s*vir", r"failed to connect to the hypervisor", r"state change lock"),
        ),
        Rule(
            category="timeout",
            component="framework",
            summary="Case timeout signature was detected.",
            confidence=0.88,
            patterns=(r"\btimeout\b", r"test timed out", r"duration exceeded", r"deadline exceeded"),
        ),
        Rule(
            category="environment_issue",
            component="environment",
            summary="Environment instability or infrastructure readiness issue was detected.",
            confidence=0.84,
            patterns=(r"connection refused", r"no route to host", r"host is down", r"failed to acquire resource"),
        ),
        Rule(
            category="infrastructure_issue",
            component="scheduler",
            summary="Scheduler or executor issue was detected.",
            confidence=0.8,
            patterns=(r"executor unavailable", r"jenkins", r"workspace cleanup failed", r"agent disconnected"),
        ),
        Rule(
            category="case_script_issue",
            component="test_case",
            summary="Test case script error or assertion failure was detected.",
            confidence=0.78,
            patterns=(r"assertionerror", r"traceback \(most recent call last\)", r"testerror", r"avocado.core.exceptions"),
        ),
    )

    def __init__(self, config: AnalysisConfig) -> None:
        self._context_lines = config.rule_context_lines

    def analyze(self, case: CaseResult, artifacts: list[LogArtifact]) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        for rule in self.RULES:
            evidences: list[Evidence] = []
            for artifact in artifacts:
                matches = self._scan_artifact(rule, artifact)
                evidences.extend(matches)
            if evidences:
                findings.append(
                    RuleFinding(
                        category=rule.category,
                        component=rule.component,
                        summary=rule.summary,
                        confidence=rule.confidence,
                        evidences=evidences[:5],
                    )
                )

        if findings:
            findings.sort(key=lambda item: item.confidence, reverse=True)
            return findings

        if case.status.strip().upper() in {"ERROR", "FAIL", "FAILED"}:
            return [
                RuleFinding(
                    category="unknown_failure",
                    component="unknown",
                    summary="The case failed but no known high-confidence signature was matched.",
                    confidence=0.4,
                    evidences=[],
                )
            ]
        return []

    def _scan_artifact(self, rule: Rule, artifact: LogArtifact) -> list[Evidence]:
        lines = artifact.content.splitlines()
        evidences: list[Evidence] = []
        for index, line in enumerate(lines):
            for pattern in rule.patterns:
                if re.search(pattern, line, flags=re.IGNORECASE):
                    start = max(0, index - self._context_lines)
                    end = min(len(lines), index + self._context_lines + 1)
                    snippet = "\n".join(lines[start:end])
                    evidences.append(
                        Evidence(
                            artifact=artifact.name,
                            line_number=index + 1,
                            snippet=snippet,
                        )
                    )
                    break
        return evidences

