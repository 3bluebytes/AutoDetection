#!/usr/bin/env python3
"""
Thin CLI wrapper for the current collector stage.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import ensure_dir, load_module, read_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Collector stage wrapper")
    parser.add_argument("--job-root", required=True, help="Avocado job-results directory")
    parser.add_argument("--failed-tests", required=True, help="Path to failed_tests.json")
    parser.add_argument("--run-dir", required=True, help="Shared run artifact directory")
    args = parser.parse_args()

    run_dir = ensure_dir(args.run_dir)
    failed_tests = read_json(args.failed_tests)
    read_local_log = load_module("read_local_log_tool", "openclaw_tools/tools/read_local_log.py")

    collected = []
    missing_logs = []
    for test in failed_tests:
        test_id = str(test.get("id", ""))
        log_result = read_local_log.read_local_log(args.job_root, test_id, "debug.log")
        entry = {
            "test_id": test_id,
            "test_name": test.get("name", ""),
            "fail_reason": test.get("fail_reason", ""),
            "error_type": test.get("error_type", ""),
            "duration": test.get("time", 0),
            "log_content": log_result.get("content", "") if log_result.get("success") else "",
            "log_path": log_result.get("file_path", ""),
            "log_size": log_result.get("size", 0),
        }
        collected.append(entry)
        if not log_result.get("success"):
            missing_logs.append(
                {
                    "test_id": test_id,
                    "test_name": entry["test_name"],
                    "error": log_result.get("error", "unknown error"),
                }
            )

    collected_path = write_json(run_dir / "collected_logs.json", collected)
    output = {
        "success": True,
        "collected_logs_path": str(collected_path),
        "collected_count": len(collected),
        "missing_log_count": len(missing_logs),
        "missing_logs": missing_logs,
    }
    write_json(run_dir / "collector_output.json", output)
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
