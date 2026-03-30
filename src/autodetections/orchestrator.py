from __future__ import annotations

from autodetections.analyzers.rules import RuleAnalyzer
from autodetections.connectors.archive import ArchiveCollector
from autodetections.connectors.avocado import AvocadoResultLoader
from autodetections.connectors.llm import OpenAICompatibleClient
from autodetections.connectors.mercury import MercuryPublisher
from autodetections.connectors.webhook import WebhookPublisher
from autodetections.models import AgentConfig, CaseAnalysis, JobReport
from autodetections.reporters import ReportWriter
from autodetections.utils import unique_strings


class AutoDetectionAgent:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._loader = AvocadoResultLoader()
        self._collector = ArchiveCollector(config.archive, config.analysis.max_log_chars_per_artifact)
        self._rules = RuleAnalyzer(config.analysis)
        self._llm = OpenAICompatibleClient(config.llm, config.analysis.llm_snippet_chars)
        self._report_writer = ReportWriter(config.output.output_dir)
        self._mercury = MercuryPublisher(config.output.mercury)
        self._webhook = WebhookPublisher(config.output.webhook)

    def run(self) -> dict[str, object]:
        job = self._loader.load(
            self._config.job_root,
            build_id=self._config.build_id,
            date=self._config.date,
            host=self._config.host,
        )

        analyses: list[CaseAnalysis] = []
        for case in job.failed_cases:
            artifacts = self._collector.collect(job, case)
            findings = self._rules.analyze(case, artifacts)
            summary = findings[0].summary if findings else "No summary generated."
            category = findings[0].category if findings else "unknown_failure"
            confidence = findings[0].confidence if findings else 0.0
            llm_summary = ""
            recommendation = ""
            if artifacts:
                llm_summary, recommendation = self._llm.summarize_case(case, findings, artifacts)
            analyses.append(
                CaseAnalysis(
                    case_id=case.case_id,
                    case_name=case.name,
                    status=case.status,
                    category=category,
                    confidence=confidence,
                    summary=summary,
                    rule_findings=findings,
                    llm_summary=llm_summary,
                    recommendation=recommendation,
                    artifacts_used=unique_strings(artifact.name for artifact in artifacts),
                )
            )

        report = JobReport(
            job_id=job.job_id,
            build_id=job.build_id,
            date=job.date,
            total_cases=len(job.cases),
            failed_cases=len(job.failed_cases),
            analyses=analyses,
        )

        json_path, md_path = self._report_writer.write(report)
        report.publish_results.append(self._mercury.publish(report))
        report.publish_results.append(self._webhook.publish(report))
        self._report_writer.write(report)
        return {
            "job_id": report.job_id,
            "json_report": str(json_path),
            "markdown_report": str(md_path),
            "failed_cases": report.failed_cases,
            "total_cases": report.total_cases,
        }
