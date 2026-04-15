#!/usr/bin/env python3
"""
Thin CLI wrapper for the current reporter stage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common import ensure_dir, read_json, write_json, PROJECT_ROOT
from openclaw_tools.tools.reporter import (
    render_markdown_report,
    render_json_report,
    render_mercury_payload,
)
from openclaw_tools.tools.excel_reporter import (
    render_daily_excel,
    render_stats_excel,
    compute_case_stats,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reporter stage wrapper")
    parser.add_argument("--job-info", required=True, help="Path to job_info.json")
    parser.add_argument("--analysis", required=True, help="Path to analysis.json")
    parser.add_argument("--run-dir", required=True, help="Shared run artifact directory")
    parser.add_argument("--output-dir", help="Report output directory, defaults to <run-dir>/reports")
    args = parser.parse_args()

    run_dir = ensure_dir(args.run_dir)
    output_dir = ensure_dir(args.output_dir or (Path(args.run_dir) / "reports"))
    job_info = read_json(args.job_info)
    analysis = read_json(args.analysis)

    markdown_result = render_markdown_report(job_info, analysis, str(output_dir / "report.md"))
    json_result = render_json_report(job_info, analysis, str(output_dir / "report.json"))
    mercury_payload = render_mercury_payload(job_info, analysis)
    mercury_payload_path = write_json(output_dir / "mercury_payload.json", mercury_payload.get("payload", {}))

    manifest = {
        "success": True,
        "markdown": markdown_result.get("output_path", ""),
        "json": json_result.get("output_path", ""),
        "mercury_payload": str(mercury_payload_path),
        "excel_daily": "",
        "excel_stats": "",
        "warnings": [],
    }

    try:
        daily_result = render_daily_excel(job_info, analysis, str(output_dir / "daily_report.xlsx"))
        manifest["excel_daily"] = daily_result.get("output_path", "")

        history_path = PROJECT_ROOT / "mock_data" / "history.json"
        if history_path.exists():
            case_stats = compute_case_stats(read_json(history_path))
            stats_result = render_stats_excel(case_stats, str(output_dir / "case_stats.xlsx"))
            manifest["excel_stats"] = stats_result.get("output_path", "")
        else:
            manifest["warnings"].append("mock_data/history.json not found, skipped cumulative stats workbook")
    except Exception as exc:
        manifest["warnings"].append(f"Excel generation skipped: {exc}")

    manifest_path = write_json(run_dir / "report_manifest.json", manifest)
    print(json.dumps({**manifest, "manifest_path": str(manifest_path)}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
