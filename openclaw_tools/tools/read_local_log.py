"""
OpenCLAW Tool: read_local_log
读取本地日志文件
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional


def read_local_log(job_root: str, test_id: str, log_type: str = "debug.log") -> Dict:
    """
    读取本地日志文件

    Args:
        job_root: Avocado job-results 目录路径
        test_id: 测试用例 ID
        log_type: 日志类型 (debug.log, job.log, 等)

    Returns:
        Dict with file content or error
    """
    # 构建日志文件路径
    test_dir = Path(job_root) / "test-results" / test_id
    log_file = test_dir / log_type

    if not log_file.exists():
        # 尝试查找第一个子目录
        subdirs = list(test_dir.glob("*"))
        if subdirs and subdirs[0].is_dir():
            log_file = subdirs[0] / log_type

    if not log_file.exists():
        return {
            "success": False,
            "error": f"Log file not found: {log_file}",
            "test_id": test_id,
            "log_type": log_type
        }

    try:
        content = log_file.read_text(encoding="utf-8", errors="ignore")
        return {
            "success": True,
            "content": content,
            "file_path": str(log_file),
            "test_id": test_id,
            "log_type": log_type,
            "size": len(content)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "test_id": test_id,
            "log_type": log_type
        }


def read_job_log(job_root: str) -> Dict:
    """
    读取主 job.log 文件
    """
    job_log = Path(job_root) / "job.log"

    if not job_log.exists():
        return {
            "success": False,
            "error": "job.log not found"
        }

    content = job_log.read_text(encoding="utf-8", errors="ignore")
    return {
        "success": True,
        "content": content,
        "file_path": str(job_log),
        "size": len(content)
    }


def read_results_json(job_root: str) -> Dict:
    """
    读取 Avocado results.json
    """
    results_file = Path(job_root) / "results.json"

    if not results_file.exists():
        return {
            "success": False,
            "error": "results.json not found"
        }

    try:
        data = json.loads(results_file.read_text(encoding="utf-8"))
        return {
            "success": True,
            "data": data,
            "file_path": str(results_file),
            "total_tests": len(data.get("tests", [])),
            "failed_count": len([t for t in data.get("tests", []) if t.get("status") == "FAIL"])
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# OpenCLAW Tool 注册信息
TOOL_METADATA = {
    "name": "read_local_log",
    "description": "Read local log files from Avocado job results directory",
    "parameters": {
        "job_root": "string - path to job-results directory",
        "test_id": "string - test case ID",
        "log_type": "string - log file name (default: debug.log)"
    },
    "returns": "JSON with file content or error",
    "enabled": True
}


if __name__ == "__main__":
    # 简单测试
    import sys

    # 从命令行参数读取
    if len(sys.argv) > 1:
        job_root = sys.argv[1]
        test_id = sys.argv[2] if len(sys.argv) > 2 else "2"
        log_type = sys.argv[3] if len(sys.argv) > 3 else "debug.log"

        result = read_local_log(job_root, test_id, log_type)
        print(json.dumps(result, indent=2, ensure_ascii=False))
