from __future__ import annotations

from pathlib import Path

from autodetections.models import JobReport
from autodetections.utils import dump_json


class ReportWriter:
    def __init__(self, output_dir: str) -> None:
        self._output_dir = Path(output_dir).resolve()
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, report: JobReport) -> tuple[Path, Path]:
        json_path = self._output_dir / f"{report.job_id}.json"
        md_path = self._output_dir / f"{report.job_id}.md"
        dump_json(json_path, self._as_json_payload(report))
        md_path.write_text(self._render_markdown(report), encoding="utf-8")
        return json_path, md_path

    def _as_json_payload(self, report: JobReport) -> dict:
        category_summary: dict[str, int] = {}
        for analysis in report.analyses:
            category_summary[analysis.category] = category_summary.get(analysis.category, 0) + 1
        return {
            "job_id": report.job_id,
            "build_id": report.build_id,
            "date": report.date,
            "total_cases": report.total_cases,
            "failed_cases": report.failed_cases,
            "category_summary": category_summary,
            "analyses": [
                {
                    "case_id": analysis.case_id,
                    "case_name": analysis.case_name,
                    "status": analysis.status,
                    "category": analysis.category,
                    "confidence": analysis.confidence,
                    "summary": analysis.summary,
                    "llm_summary": analysis.llm_summary,
                    "recommendation": analysis.recommendation,
                    "artifacts_used": analysis.artifacts_used,
                    "rule_findings": [
                        {
                            "category": finding.category,
                            "component": finding.component,
                            "summary": finding.summary,
                            "confidence": finding.confidence,
                            "evidences": [
                                {
                                    "artifact": evidence.artifact,
                                    "line_number": evidence.line_number,
                                    "snippet": evidence.snippet,
                                }
                                for evidence in finding.evidences
                            ],
                        }
                        for finding in analysis.rule_findings
                    ],
                }
                for analysis in report.analyses
            ],
            "publish_results": [
                {
                    "target": item.target,
                    "success": item.success,
                    "detail": item.detail,
                }
                for item in report.publish_results
            ],
        }

    def _render_markdown(self, report: JobReport) -> str:
        category_summary: dict[str, int] = {}
        for analysis in report.analyses:
            category_summary[analysis.category] = category_summary.get(analysis.category, 0) + 1

        lines = [
            f"# Virtualization AT Report: {report.job_id}",
            "",
            f"- Build ID: {report.build_id or 'unknown'}",
            f"- Date: {report.date or 'unknown'}",
            f"- Total Cases: {report.total_cases}",
            f"- Failed Cases: {report.failed_cases}",
            "",
        ]
        if category_summary:
            lines.append("## Category Summary")
            lines.append("")
            for category, count in sorted(category_summary.items(), key=lambda item: (-item[1], item[0])):
                lines.append(f"- {category}: {count}")
            lines.append("")
        for analysis in report.analyses:
            lines.extend(
                [
                    f"## {analysis.case_name}",
                    "",
                    f"- Case ID: {analysis.case_id}",
                    f"- Status: {analysis.status}",
                    f"- Category: {analysis.category}",
                    f"- Confidence: {analysis.confidence:.2f}",
                    f"- Summary: {analysis.llm_summary or analysis.summary}",
                    f"- Recommendation: {analysis.recommendation or 'Review related logs and component owner.'}",
                    f"- Artifacts Used: {', '.join(analysis.artifacts_used) if analysis.artifacts_used else 'none'}",
                    "",
                ]
            )
            if analysis.rule_findings:
                lines.append("### Rule Findings")
                lines.append("")
                for finding in analysis.rule_findings:
                    lines.append(
                        f"- {finding.category} ({finding.component}, confidence={finding.confidence:.2f}): {finding.summary}"
                    )
                    if finding.evidences:
                        evidence = finding.evidences[0]
                        lines.append(f"  - {evidence.artifact}:{evidence.line_number}")
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"
