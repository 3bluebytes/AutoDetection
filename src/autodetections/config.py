from __future__ import annotations

import json
from pathlib import Path

from autodetections.models import (
    AgentConfig,
    AnalysisConfig,
    ArchiveConfig,
    ArtifactPattern,
    LLMConfig,
    MercuryConfig,
    OutputConfig,
    WebhookConfig,
)


def load_config(path: str) -> AgentConfig:
    config_path = Path(path).resolve()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    base_dir = config_path.parent
    job_root = _resolve_path(raw["job_root"], base_dir)
    return AgentConfig(
        job_root=job_root,
        build_id=raw.get("build_id", ""),
        date=raw.get("date", ""),
        host=raw.get("host", ""),
        analysis=_parse_analysis(raw.get("analysis", {})),
        archive=_parse_archive(raw.get("archive", {})),
        llm=_parse_llm(raw.get("llm", {})),
        output=_parse_output(raw.get("output", {}), base_dir),
    )


def _resolve_path(value: str, base_dir: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve())


def _parse_analysis(raw: dict) -> AnalysisConfig:
    return AnalysisConfig(
        max_log_chars_per_artifact=int(raw.get("max_log_chars_per_artifact", 12000)),
        rule_context_lines=int(raw.get("rule_context_lines", 3)),
        llm_snippet_chars=int(raw.get("llm_snippet_chars", 16000)),
    )


def _parse_archive(raw: dict) -> ArchiveConfig:
    patterns = [
        ArtifactPattern(
            name=item["name"],
            component=item["component"],
            path_template=item["path_template"],
            required=bool(item.get("required", False)),
        )
        for item in raw.get("artifact_patterns", [])
    ]
    return ArchiveConfig(
        base_url=raw.get("base_url", ""),
        auth_token_env=raw.get("auth_token_env", ""),
        request_timeout_seconds=int(raw.get("request_timeout_seconds", 20)),
        verify_tls=bool(raw.get("verify_tls", True)),
        artifact_patterns=patterns,
    )


def _parse_llm(raw: dict) -> LLMConfig:
    return LLMConfig(
        enabled=bool(raw.get("enabled", False)),
        base_url=raw.get("base_url", ""),
        api_key_env=raw.get("api_key_env", ""),
        model=raw.get("model", ""),
        temperature=float(raw.get("temperature", 0.1)),
        request_timeout_seconds=int(raw.get("request_timeout_seconds", 45)),
    )


def _parse_output(raw: dict, base_dir: Path) -> OutputConfig:
    mercury_raw = raw.get("mercury", {})
    webhook_raw = raw.get("webhook", {})
    return OutputConfig(
        output_dir=_resolve_path(raw.get("output_dir", "outputs"), base_dir),
        mercury=MercuryConfig(
            enabled=bool(mercury_raw.get("enabled", False)),
            endpoint=mercury_raw.get("endpoint", ""),
            auth_token_env=mercury_raw.get("auth_token_env", ""),
            dashboard_key=mercury_raw.get("dashboard_key", ""),
        ),
        webhook=WebhookConfig(
            enabled=bool(webhook_raw.get("enabled", False)),
            url=webhook_raw.get("url", ""),
            token_env=webhook_raw.get("token_env", ""),
        ),
    )

