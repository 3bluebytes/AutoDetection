from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from autodetections.models import CaseResult, LLMConfig, LogArtifact, RuleFinding


class OpenAICompatibleClient:
    def __init__(self, config: LLMConfig, snippet_chars: int) -> None:
        self._config = config
        self._snippet_chars = snippet_chars

    @property
    def enabled(self) -> bool:
        return self._config.enabled and bool(self._config.base_url and self._config.model and self._config.api_key_env)

    def summarize_case(self, case: CaseResult, findings: list[RuleFinding], artifacts: list[LogArtifact]) -> tuple[str, str]:
        if not self.enabled:
            return "", ""

        api_key = os.getenv(self._config.api_key_env, "")
        if not api_key:
            return "", ""

        body = {
            "model": self._config.model,
            "temperature": self._config.temperature,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a virtualization AT triage assistant. "
                        "Given Avocado failure metadata, rule findings, and log snippets, "
                        "produce a concise root cause summary and one follow-up recommendation."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(case, findings, artifacts),
                },
            ],
        }
        request = urllib.request.Request(
            urllib.parse.urljoin(self._config.base_url.rstrip("/") + "/", "chat/completions"),
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._config.request_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception:
            return "", ""

        content = self._extract_message(payload)
        if not content:
            return "", ""

        summary, recommendation = self._split_response(content)
        return summary, recommendation

    def _build_prompt(self, case: CaseResult, findings: list[RuleFinding], artifacts: list[LogArtifact]) -> str:
        rule_lines = []
        for finding in findings[:3]:
            evidence = finding.evidences[0].snippet if finding.evidences else "no evidence"
            rule_lines.append(
                f"- category={finding.category}, confidence={finding.confidence:.2f}, "
                f"summary={finding.summary}, evidence={evidence[:600]}"
            )

        artifact_lines = []
        consumed = 0
        for artifact in artifacts:
            remaining = self._snippet_chars - consumed
            if remaining <= 0:
                break
            snippet = artifact.content[: min(remaining, 2000)]
            artifact_lines.append(f"## {artifact.name} ({artifact.component})\n{snippet}")
            consumed += len(snippet)

        return (
            f"Case: {case.name}\n"
            f"Case ID: {case.case_id}\n"
            f"Status: {case.status}\n\n"
            "Rule findings:\n"
            f"{chr(10).join(rule_lines) if rule_lines else '- none'}\n\n"
            "Relevant logs:\n"
            f"{chr(10).join(artifact_lines) if artifact_lines else 'No logs available.'}\n\n"
            "Respond in exactly two lines:\n"
            "Summary: <root cause summary>\n"
            "Recommendation: <next action>\n"
        )

    def _extract_message(self, payload: dict) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        message = choices[0].get("message", {})
        return str(message.get("content", "")).strip()

    def _split_response(self, content: str) -> tuple[str, str]:
        summary = ""
        recommendation = ""
        for line in content.splitlines():
            if line.lower().startswith("summary:"):
                summary = line.split(":", 1)[1].strip()
            elif line.lower().startswith("recommendation:"):
                recommendation = line.split(":", 1)[1].strip()
        return summary, recommendation

