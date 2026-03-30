from __future__ import annotations

import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from autodetections.models import ArchiveConfig, CaseResult, JobRun, LogArtifact
from autodetections.utils import safe_read_text


class ArchiveCollector:
    """Collects local and remote log artifacts for a failed case."""

    LOCAL_KEYWORDS: tuple[tuple[str, str], ...] = (
        ("job.log", "orchestrator"),
        ("debug.log", "case_debug"),
        ("libvirt", "libvirt"),
        ("qemu", "qemu"),
        ("dmesg", "kernel"),
        ("messages", "kernel"),
        ("oom", "memory"),
        ("memory", "memory"),
        ("sysinfo", "sysinfo"),
    )

    def __init__(self, config: ArchiveConfig, max_chars_per_artifact: int) -> None:
        self._config = config
        self._limit = max_chars_per_artifact

    def collect(self, job: JobRun, case: CaseResult) -> list[LogArtifact]:
        local = self._collect_local(job, case)
        remote = self._collect_remote(job, case)
        return self._deduplicate(local + remote)

    def _collect_local(self, job: JobRun, case: CaseResult) -> list[LogArtifact]:
        root = Path(job.root_path)
        candidates: list[Path] = []

        case_dir = Path(case.log_dir) if case.log_dir else None
        if case_dir and case_dir.exists():
            candidates.extend(path for path in case_dir.rglob("*") if path.is_file())

        for fallback in ("job.log", "debug.log"):
            path = root / fallback
            if path.exists():
                candidates.append(path)

        sysinfo_dir = root / "sysinfo"
        if sysinfo_dir.exists():
            candidates.extend(path for path in sysinfo_dir.rglob("*") if path.is_file())

        artifacts: list[LogArtifact] = []
        for path in candidates:
            lowered = path.name.lower()
            component = self._match_component(lowered, str(path).lower())
            if not component:
                continue
            artifacts.append(
                LogArtifact(
                    name=path.name,
                    component=component,
                    source=str(path),
                    content=safe_read_text(path, limit=self._limit),
                    optional=True,
                )
            )
        return artifacts

    def _collect_remote(self, job: JobRun, case: CaseResult) -> list[LogArtifact]:
        if not self._config.base_url or not self._config.artifact_patterns:
            return []

        ssl_context = ssl.create_default_context()
        if not self._config.verify_tls:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        artifacts: list[LogArtifact] = []
        headers = {}
        token = os.getenv(self._config.auth_token_env, "") if self._config.auth_token_env else ""
        if token:
            headers["Authorization"] = f"Bearer {token}"

        variables = {
            "job_id": job.job_id,
            "case_id": case.case_id,
            "case_name": case.name,
            "status": case.status,
            "date": job.date,
            "build_id": job.build_id,
            "host": job.host,
        }

        for pattern in self._config.artifact_patterns:
            relative_path = pattern.path_template.format(**variables)
            target_url = urllib.parse.urljoin(self._config.base_url, relative_path)
            request = urllib.request.Request(target_url, headers=headers)
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self._config.request_timeout_seconds,
                    context=ssl_context,
                ) as response:
                    content = response.read().decode("utf-8", errors="replace")[: self._limit]
                    artifacts.append(
                        LogArtifact(
                            name=pattern.name,
                            component=pattern.component,
                            source=target_url,
                            content=content,
                            optional=not pattern.required,
                        )
                    )
            except urllib.error.HTTPError as exc:
                if pattern.required:
                    artifacts.append(
                        LogArtifact(
                            name=pattern.name,
                            component=pattern.component,
                            source=target_url,
                            content=f"REMOTE_FETCH_FAILED: HTTP {exc.code}",
                            optional=False,
                        )
                    )
            except urllib.error.URLError:
                if pattern.required:
                    artifacts.append(
                        LogArtifact(
                            name=pattern.name,
                            component=pattern.component,
                            source=target_url,
                            content="REMOTE_FETCH_FAILED: connection error",
                            optional=False,
                        )
                    )
        return artifacts

    def _match_component(self, filename: str, full_path: str) -> str:
        for keyword, component in self.LOCAL_KEYWORDS:
            if keyword in filename or keyword in full_path:
                return component
        return ""

    def _deduplicate(self, artifacts: list[LogArtifact]) -> list[LogArtifact]:
        seen: set[tuple[str, str]] = set()
        ordered: list[LogArtifact] = []
        for artifact in artifacts:
            key = (artifact.name, artifact.source)
            if key not in seen:
                seen.add(key)
                ordered.append(artifact)
        return ordered

