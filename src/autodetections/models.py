from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ArtifactPattern:
    name: str
    component: str
    path_template: str
    required: bool = False


@dataclass(slots=True)
class ArchiveConfig:
    base_url: str = ""
    auth_token_env: str = ""
    request_timeout_seconds: int = 20
    verify_tls: bool = True
    artifact_patterns: list[ArtifactPattern] = field(default_factory=list)


@dataclass(slots=True)
class LLMConfig:
    enabled: bool = False
    base_url: str = ""
    api_key_env: str = ""
    model: str = ""
    temperature: float = 0.1
    request_timeout_seconds: int = 45


@dataclass(slots=True)
class MercuryConfig:
    enabled: bool = False
    endpoint: str = ""
    auth_token_env: str = ""
    dashboard_key: str = ""


@dataclass(slots=True)
class WebhookConfig:
    enabled: bool = False
    url: str = ""
    token_env: str = ""


@dataclass(slots=True)
class OutputConfig:
    output_dir: str = "outputs"
    mercury: MercuryConfig = field(default_factory=MercuryConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)


@dataclass(slots=True)
class AnalysisConfig:
    max_log_chars_per_artifact: int = 12000
    rule_context_lines: int = 3
    llm_snippet_chars: int = 16000


@dataclass(slots=True)
class AgentConfig:
    job_root: str
    build_id: str = ""
    date: str = ""
    host: str = ""
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    archive: ArchiveConfig = field(default_factory=ArchiveConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


@dataclass(slots=True)
class CaseResult:
    case_id: str
    name: str
    status: str
    duration_seconds: float | None = None
    log_dir: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_failed(self) -> bool:
        return self.status.strip().lower() not in {"pass", "passed", "success", "skip", "skipped", "cancel"}


@dataclass(slots=True)
class JobRun:
    job_id: str
    root_path: str
    build_id: str = ""
    date: str = ""
    host: str = ""
    cases: list[CaseResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def failed_cases(self) -> list[CaseResult]:
        return [case for case in self.cases if case.is_failed]


@dataclass(slots=True)
class LogArtifact:
    name: str
    component: str
    source: str
    content: str
    optional: bool = True


@dataclass(slots=True)
class Evidence:
    artifact: str
    line_number: int
    snippet: str


@dataclass(slots=True)
class RuleFinding:
    category: str
    component: str
    summary: str
    confidence: float
    evidences: list[Evidence] = field(default_factory=list)


@dataclass(slots=True)
class CaseAnalysis:
    case_id: str
    case_name: str
    status: str
    category: str
    confidence: float
    summary: str
    rule_findings: list[RuleFinding] = field(default_factory=list)
    llm_summary: str = ""
    recommendation: str = ""
    artifacts_used: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PublishResult:
    target: str
    success: bool
    detail: str


@dataclass(slots=True)
class JobReport:
    job_id: str
    build_id: str
    date: str
    total_cases: int
    failed_cases: int
    analyses: list[CaseAnalysis]
    publish_results: list[PublishResult] = field(default_factory=list)

