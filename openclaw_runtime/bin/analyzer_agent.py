#!/usr/bin/env python3
"""
Thin CLI wrapper for the current analyzer stage.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any, Dict, Optional

from common import ensure_dir, load_module, read_json, write_json


DEFAULT_SUGGESTIONS = {
    "libvirt_error": "检查 libvirtd 服务状态，确认 API 兼容性，查看对应版本 libvirt 变更日志",
    "qemu_crash": "收集 QEMU coredump，检查 QEMU 版本和补丁情况，查看对应版本 QEMU 变更",
    "kernel_panic": "分析内核崩溃转储 (vmcore)，检查内核版本和驱动兼容性",
    "memory_issue": "检查宿主机内存配置和 limits，确认 cgroup 设置，增加可用内存",
    "timeout": "排查网络/存储性能瓶颈，检查用例超时配置是否合理",
    "environment_issue": "检查网络连通性、存储挂载状态，确认环境依赖是否就绪",
    "case_script_issue": "检查测试用例脚本逻辑，修复断言或配置问题",
    "infrastructure_issue": "检查存储服务和网络配置，确认基础设施组件状态",
    "unknown_failure": "需要人工进一步排查，建议收集更多日志信息",
}


def _parse_llm_content(result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not result or not result.get("success"):
        return None

    content = result.get("content", "").strip()
    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0]
    elif content.startswith("```"):
        content = content.split("```", 1)[1].split("```", 1)[0]

    try:
        return json.loads(content.strip())
    except Exception:
        return None


def _extract_root_cause(rule_result: Dict[str, Any], llm_payload: Optional[Dict[str, Any]]) -> str:
    if llm_payload and llm_payload.get("root_cause"):
        return str(llm_payload["root_cause"])

    evidence = rule_result.get("evidence", {})
    primary = rule_result.get("failure_type", "")
    if primary in evidence and evidence[primary]:
        return evidence[primary][0][:120]
    if evidence:
        first_key = next(iter(evidence))
        if evidence[first_key]:
            return evidence[first_key][0][:120]
    return "Unknown"


def _extract_suggestion(
    rule_result: Dict[str, Any],
    llm_payload: Optional[Dict[str, Any]],
    known_issue: Optional[Dict[str, Any]],
) -> str:
    if known_issue:
        return known_issue.get("summary", "")
    if llm_payload and llm_payload.get("suggestion"):
        return str(llm_payload["suggestion"])
    return DEFAULT_SUGGESTIONS.get(rule_result.get("failure_type", "unknown_failure"), DEFAULT_SUGGESTIONS["unknown_failure"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyzer stage wrapper")
    parser.add_argument("--collected-logs", required=True, help="Path to collected_logs.json")
    parser.add_argument("--job-info", required=True, help="Path to job_info.json")
    parser.add_argument("--run-dir", required=True, help="Shared run artifact directory")
    parser.add_argument("--use-llm", action="store_true", help="Enable optional LLM analysis")
    args = parser.parse_args()

    run_dir = ensure_dir(args.run_dir)
    collected_logs = read_json(args.collected_logs)
    job_info = read_json(args.job_info)

    rule_match = load_module("rule_match_tool", "openclaw_tools/tools/rule_match.py")
    version_identifier = load_module("version_identifier_tool", "openclaw_tools/tools/version_identifier.py")

    llm_tool = None
    llm_import_error = ""
    if args.use_llm:
        try:
            llm_tool = load_module("llm_inference_tool", "openclaw_tools/tools/llm_inference.py")
        except Exception as exc:
            llm_import_error = str(exc)

    warnings = []
    if args.use_llm and llm_import_error:
        warnings.append(f"LLM wrapper unavailable, fallback to rule-only mode: {llm_import_error}")

    analyzed = []
    for test in collected_logs:
        rule_result = rule_match.classify_failure(
            test.get("log_content", ""),
            test.get("test_name", ""),
            test.get("fail_reason", ""),
        )

        llm_result = None
        llm_payload = None
        if args.use_llm and llm_tool and rule_result.get("confidence") != "high":
            llm_result = llm_tool.analyze_log_with_llm(
                test.get("log_content", ""),
                test.get("test_name", ""),
                rule_result,
            )
            llm_payload = _parse_llm_content(llm_result)
            if llm_result and not llm_result.get("success"):
                warnings.append(
                    f"LLM analyze failed for {test.get('test_name', '')}: {llm_result.get('error', 'unknown error')}"
                )

        known_issue = version_identifier.match_known_issue(
            test.get("log_content", ""),
            job_info.get("uvp_version", ""),
        )
        responsibility = version_identifier.get_responsibility(rule_result["failure_type"])

        analyzed.append(
            {
                "test_name": test.get("test_name", ""),
                "test_id": test.get("test_id", ""),
                "failure_type": rule_result["failure_type"],
                "confidence": rule_result["confidence"],
                "scores": rule_result.get("scores", {}),
                "evidence": rule_result.get("evidence", {}),
                "method": rule_result.get("method", "rule_engine"),
                "root_cause": _extract_root_cause(rule_result, llm_payload),
                "suggestion": _extract_suggestion(rule_result, llm_payload, known_issue),
                "known_issue": f"{known_issue['id']}: {known_issue['summary']}" if known_issue else "",
                "owner": responsibility["owner"],
                "team": responsibility["team"],
                "duration": test.get("duration", 0),
                "log_path": test.get("log_path", ""),
                "llm_used": bool(llm_payload),
            }
        )

    type_counts = dict(Counter(item["failure_type"] for item in analyzed))
    analyzed_path = write_json(run_dir / "analysis.json", analyzed)
    summary = {
        "success": True,
        "analysis_path": str(analyzed_path),
        "failure_count": len(analyzed),
        "type_counts": type_counts,
        "warnings": sorted(set(warnings)),
        "used_llm": any(item.get("llm_used") for item in analyzed),
    }
    write_json(run_dir / "analysis_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
