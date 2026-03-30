from __future__ import annotations

import json
import os
import urllib.request

from autodetections.models import JobReport, PublishResult, WebhookConfig


class WebhookPublisher:
    def __init__(self, config: WebhookConfig) -> None:
        self._config = config

    def publish(self, report: JobReport) -> PublishResult:
        if not self._config.enabled:
            return PublishResult(target="webhook", success=False, detail="disabled")
        if not self._config.url:
            return PublishResult(target="webhook", success=False, detail="missing url")

        token = os.getenv(self._config.token_env, "") if self._config.token_env else ""
        lines = [
            f"Virtualization AT report: {report.job_id}",
            f"Build: {report.build_id or 'unknown'}",
            f"Failed cases: {report.failed_cases}/{report.total_cases}",
        ]
        for analysis in report.analyses[:5]:
            lines.append(f"- {analysis.case_name}: {analysis.category} ({analysis.confidence:.2f})")

        payload = {"text": "\n".join(lines)}
        request = urllib.request.Request(
            self._config.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {token}"} if token else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15):
                return PublishResult(target="webhook", success=True, detail="published")
        except Exception as exc:
            return PublishResult(target="webhook", success=False, detail=str(exc))
