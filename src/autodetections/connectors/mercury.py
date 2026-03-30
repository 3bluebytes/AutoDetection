from __future__ import annotations

import json
import os
import urllib.request

from autodetections.models import JobReport, MercuryConfig, PublishResult


class MercuryPublisher:
    def __init__(self, config: MercuryConfig) -> None:
        self._config = config

    def publish(self, report: JobReport) -> PublishResult:
        if not self._config.enabled:
            return PublishResult(target="mercury", success=False, detail="disabled")
        if not self._config.endpoint:
            return PublishResult(target="mercury", success=False, detail="missing endpoint")

        token = os.getenv(self._config.auth_token_env, "") if self._config.auth_token_env else ""
        category_summary: dict[str, int] = {}
        for analysis in report.analyses:
            category_summary[analysis.category] = category_summary.get(analysis.category, 0) + 1
        payload = {
            "dashboard_key": self._config.dashboard_key,
            "job_id": report.job_id,
            "build_id": report.build_id,
            "date": report.date,
            "total_cases": report.total_cases,
            "failed_cases": report.failed_cases,
            "category_summary": category_summary,
            "cases": [
                {
                    "case_id": analysis.case_id,
                    "case_name": analysis.case_name,
                    "status": analysis.status,
                    "category": analysis.category,
                    "confidence": round(analysis.confidence, 2),
                    "summary": analysis.llm_summary or analysis.summary,
                    "evidence": [
                        evidence.snippet
                        for finding in analysis.rule_findings[:2]
                        for evidence in finding.evidences[:1]
                    ],
                }
                for analysis in report.analyses
            ],
        }
        request = urllib.request.Request(
            self._config.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {token}"} if token else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20):
                return PublishResult(target="mercury", success=True, detail="published")
        except Exception as exc:
            return PublishResult(target="mercury", success=False, detail=str(exc))
