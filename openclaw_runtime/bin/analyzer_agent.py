#!/usr/bin/env python3
"""
Analyzer stage with advanced capabilities:
- Weighted rule engine
- Adversarial diagnosis (Agent A: rule engine + Agent B: LLM)
- Model upgrade chain (rule -> fast model -> reasoning model)
- Root cause clustering
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common import ensure_dir, read_json, write_json
from openclaw_tools.tools.rule_match import classify_failure
from openclaw_tools.tools.version_identifier import match_known_issue, get_responsibility
from openclaw_tools.tools.adversarial_diagnosis import adversarial_diagnose, DiagnosisStatus
from openclaw_tools.tools.model_chain import classify_with_model_chain
from openclaw_tools.tools.root_cause_cluster import cluster_failures


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


def _extract_root_cause(rule_result: Dict[str, Any], advanced_result: Optional[Dict[str, Any]]) -> str:
    # Handle different result formats from adversarial/model_chain
    if advanced_result:
        # Try different possible root_cause locations
        if advanced_result.get("failure_type"):
            # This is likely from model_chain with final result
            if advanced_result.get("root_cause"):
                return str(advanced_result["root_cause"])
        # For adversarial, check agent_b reasoning
        agent_b = advanced_result.get("agent_b") or {}
        if agent_b and agent_b.get("reasoning"):
            return agent_b["reasoning"][:120]
        # For model_chain, check tier results
        tier2 = advanced_result.get("tier2_result") or {}
        if tier2 and tier2.get("root_cause"):
            return tier2["root_cause"][:120]

    # Fall back to rule_result
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
    advanced_result: Optional[Dict[str, Any]],
    known_issue: Optional[Dict[str, Any]],
) -> str:
    if known_issue:
        return known_issue.get("summary", "")

    if advanced_result:
        # Check various possible suggestion locations
        if advanced_result.get("suggestion"):
            return str(advanced_result["suggestion"])
        tier2 = advanced_result.get("tier2_result") or {}
        if tier2 and tier2.get("suggestion"):
            return tier2["suggestion"]
        agent_b = advanced_result.get("agent_b") or {}
        if agent_b and agent_b.get("reasoning"):
            # Use reasoning as suggestion for adversarial
            return agent_b["reasoning"][:200]

    return DEFAULT_SUGGESTIONS.get(rule_result.get("failure_type", "unknown_failure"), DEFAULT_SUGGESTIONS["unknown_failure"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyzer stage wrapper")
    parser.add_argument("--collected-logs", required=True, help="Path to collected_logs.json")
    parser.add_argument("--job-info", required=True, help="Path to job_info.json")
    parser.add_argument("--run-dir", required=True, help="Shared run artifact directory")
    # Analysis mode flags
    parser.add_argument("--use-llm", action="store_true", help="Enable basic LLM supplement")
    parser.add_argument("--use-adversarial", action="store_true", help="Enable adversarial diagnosis (Agent A + Agent B)")
    parser.add_argument("--use-model-chain", action="store_true", help="Enable model upgrade chain (tier 0->1->2)")
    parser.add_argument("--use-clustering", action="store_true", help="Enable root cause clustering")
    parser.add_argument("--max-tier", type=int, default=2, choices=[0,1,2], help="Max model tier for model-chain (0=rule only, 1=fast, 2=reasoning)")
    args = parser.parse_args()

    run_dir = ensure_dir(args.run_dir)
    collected_logs = read_json(args.collected_logs)
    job_info = read_json(args.job_info)

    # Check available analysis capabilities
    llm_available = False
    llm_import_error = ""
    try:
        from openclaw_tools.tools.llm_inference import call_llm, analyze_log_with_llm
        llm_available = True
    except Exception as exc:
        llm_import_error = str(exc)

    # Warn about unavailable features
    warnings = []
    if args.use_llm and not llm_available:
        warnings.append(f"LLM unavailable: {llm_import_error}")
    if args.use_adversarial and not llm_available:
        warnings.append("Adversarial diagnosis requires LLM, falling back to rule-only")
        args.use_adversarial = False
    if args.use_model_chain and not llm_available:
        warnings.append("Model chain requires LLM, falling back to rule-only")
        args.use_model_chain = False

    analyzed = []
    for test in collected_logs:
        log_content = test.get("log_content", "")
        test_name = test.get("test_name", "")
        fail_reason = test.get("fail_reason", "")

        # Step 1: Rule engine always runs
        rule_result = classify_failure(log_content, test_name, fail_reason)

        # Step 2: Advanced analysis based on flags
        diagnosis_result = None
        if args.use_adversarial and llm_available:
            # Adversarial diagnosis: Agent A (rule) + Agent B (LLM) + arbitration
            diagnosis_result = adversarial_diagnose(
                log_content, test_name, fail_reason,
                enable_llm=True
            )
        elif args.use_model_chain and llm_available:
            # Model upgrade chain: rule -> fast model -> reasoning model
            diagnosis_result = classify_with_model_chain(
                log_content, test_name, fail_reason,
                rule_result=rule_result,
                max_tier=args.max_tier
            )

        # Use advanced result if available, otherwise fall back to rule result
        if diagnosis_result:
            failure_type = diagnosis_result.get("failure_type", rule_result["failure_type"])
            confidence = diagnosis_result.get("confidence", rule_result["confidence"])
            method = "adversarial" if args.use_adversarial else "model_chain"
            evidence = diagnosis_result.get("agent_a", {}).get("evidence", rule_result.get("evidence", {}))
            scores = diagnosis_result.get("agent_a", {}).get("scores", rule_result.get("scores", {}))
        else:
            failure_type = rule_result["failure_type"]
            confidence = rule_result["confidence"]
            method = rule_result.get("method", "rule_engine")
            evidence = rule_result.get("evidence", {})
            scores = rule_result.get("scores", {})

        # Known issue matching
        known_issue = match_known_issue(log_content, job_info.get("uvp_version", ""))
        responsibility = get_responsibility(failure_type)

        # Extract root cause and suggestion
        root_cause = _extract_root_cause(rule_result, diagnosis_result)
        suggestion = _extract_suggestion(rule_result, diagnosis_result, known_issue)

        analyzed.append(
            {
                "test_name": test_name,
                "test_id": test.get("test_id", ""),
                "failure_type": failure_type,
                "confidence": confidence,
                "scores": scores,
                "evidence": evidence,
                "method": method,
                "root_cause": root_cause,
                "suggestion": suggestion,
                "known_issue": f"{known_issue['id']}: {known_issue['summary']}" if known_issue else "",
                "owner": responsibility["owner"],
                "team": responsibility["team"],
                "duration": test.get("duration", 0),
                "log_path": test.get("log_path", ""),
                "analysis_mode": method,
            }
        )

    # Step 3: Root cause clustering (optional post-processing)
    if args.use_clustering and len(analyzed) > 1:
        cluster_result = cluster_failures(analyzed)
        # Handle both dict and list return formats
        clusters = cluster_result.get("clusters", []) if isinstance(cluster_result, dict) else cluster_result

        # Add cluster info to each result
        for item in analyzed:
            for cluster in clusters:
                test_ids = cluster.get("test_ids", []) if isinstance(cluster, dict) else []
                if item["test_id"] in test_ids:
                    item["cluster_id"] = cluster.get("cluster_id") if isinstance(cluster, dict) else None
                    item["root_cause_summary"] = cluster.get("summary") if isinstance(cluster, dict) else None
                    break

    type_counts = dict(Counter(item["failure_type"] for item in analyzed))
    analyzed_path = write_json(run_dir / "analysis.json", analyzed)

    # Write clustering results if enabled
    if args.use_clustering and len(analyzed) > 1:
        cluster_result = cluster_failures(analyzed)
        write_json(run_dir / "clusters.json", cluster_result)

    summary = {
        "success": True,
        "analysis_path": str(analyzed_path),
        "failure_count": len(analyzed),
        "type_counts": type_counts,
        "warnings": sorted(set(warnings)),
        "used_adversarial": args.use_adversarial,
        "used_model_chain": args.use_model_chain,
        "used_clustering": args.use_clustering,
    }
    write_json(run_dir / "analysis_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
