#!/usr/bin/env python3
"""
Thin CLI wrapper for the current parser stage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import ensure_dir, load_module, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Parser stage wrapper")
    parser.add_argument("--job-root", required=True, help="Avocado job-results directory")
    parser.add_argument("--run-dir", required=True, help="Shared run artifact directory")
    args = parser.parse_args()

    run_dir = ensure_dir(args.run_dir)
    read_local_log = load_module("read_local_log_tool", "openclaw_tools/tools/read_local_log.py")
    version_identifier = load_module("version_identifier_tool", "openclaw_tools/tools/version_identifier.py")

    result = read_local_log.read_results_json(args.job_root)
    if not result.get("success"):
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 1

    data = result["data"]
    failed_tests = [test for test in data.get("tests", []) if test.get("status") == "FAIL"]
    job_info = {
        "job_id": data.get("job_id"),
        "build_id": data.get("build_id"),
        "date": data.get("date"),
        "host": data.get("host"),
        "operator": data.get("operator", ""),
        "uvp_version": version_identifier.extract_uvp_version(data),
        "total": data.get("total", len(data.get("tests", []))),
        "passed": data.get("passed"),
        "failed": data.get("failed", len(failed_tests)),
        "skipped": data.get("skipped"),
        "job_root": str(Path(args.job_root).resolve()),
        "results_file": result.get("file_path", ""),
    }

    job_info_path = write_json(run_dir / "job_info.json", job_info)
    failed_tests_path = write_json(run_dir / "failed_tests.json", failed_tests)
    output = {
        "success": True,
        "job_info_path": str(job_info_path),
        "failed_tests_path": str(failed_tests_path),
        "failed_count": len(failed_tests),
        "total_tests": result.get("total_tests", len(data.get("tests", []))),
        "uvp_version": job_info["uvp_version"],
    }
    write_json(run_dir / "parser_output.json", output)
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
