"""
OpenCLAW Tool: rule_match
规则引擎 - 根据日志内容匹配失败类型

改进点：
1. 按日志来源加权（libvirt 日志里的 libvirt error 权重更高）
2. 规则带权重，区分强信号和弱信号
3. 证据提取完整行，不再截断
4. 多类型命中时按得分排序，不再硬编码优先级
"""

import re
from typing import Dict, List, Optional, Tuple


# 日志来源权重：来自对应组件日志的关键词权重更高
LOG_SOURCE_WEIGHTS = {
    "libvirt": 2.0,
    "qemu": 2.0,
    "kernel": 2.0,
    "dmesg": 1.5,
    "messages": 1.2,
    "avocado": 1.0,
    "iscsi": 2.0,
}


# 规则定义：每条规则带权重
# weight: 强信号(2.0) / 一般信号(1.0) / 弱信号(0.5)
# source: 该规则最相关的日志来源（用于加权）
FAILURE_RULES = {
    "libvirt_error": {
        "patterns": [
            {"re": r"libvirt.*error", "weight": 2.0, "source": "libvirt"},
            {"re": r"virDomain.*failed", "weight": 2.0, "source": "libvirt"},
            {"re": r"virsh.*error", "weight": 1.5, "source": "libvirt"},
            {"re": r"libvirtd.*error", "weight": 2.0, "source": "libvirt"},
            {"re": r"Failed to attach.*device", "weight": 1.5, "source": "libvirt"},
            {"re": r"Operation not supported.*hypervisor", "weight": 2.0, "source": "libvirt"},
            {"re": r"qemuProcessKill", "weight": 0.5, "source": "libvirt"},  # libvirt 报 qemu 挂了，弱信号
        ]
    },
    "qemu_crash": {
        "patterns": [
            {"re": r"qemu.*crash", "weight": 2.0, "source": "qemu"},
            {"re": r"qemu.*fatal", "weight": 2.0, "source": "qemu"},
            {"re": r"qemu-img.*error", "weight": 1.5, "source": "qemu"},
            {"re": r"bdrv_snapshot.*failed", "weight": 2.0, "source": "qemu"},
            {"re": r"qcow2.*error", "weight": 1.5, "source": "qemu"},
            {"re": r"qemu-kvm.*error", "weight": 1.5, "source": "qemu"},
        ]
    },
    "kernel_panic": {
        "patterns": [
            {"re": r"kernel panic", "weight": 2.0, "source": "kernel"},
            {"re": r"VFS: Unable to mount", "weight": 2.0, "source": "kernel"},
            {"re": r"panic\+", "weight": 1.0, "source": "kernel"},
            {"re": r"unknown-block", "weight": 1.5, "source": "kernel"},
        ]
    },
    "memory_issue": {
        "patterns": [
            {"re": r"oom-killer", "weight": 2.0, "source": "kernel"},
            {"re": r"Out of memory.*[Kk]ill", "weight": 2.0, "source": "kernel"},
            {"re": r"oom_score_adj", "weight": 1.0, "source": "kernel"},
            {"re": r"Memory cgroup out of memory", "weight": 2.0, "source": "kernel"},
            {"re": r"not enough memory", "weight": 1.5, "source": "kernel"},
            {"re": r"Out of memory during allocation", "weight": 1.5, "source": "qemu"},
        ]
    },
    "timeout": {
        "patterns": [
            {"re": r"timeout after \d+ seconds", "weight": 2.0, "source": "avocado"},
            {"re": r"timeout.*exceeded", "weight": 1.5, "source": "avocado"},
            {"re": r"operation timed out", "weight": 1.0, "source": "avocado"},
            {"re": r"did not complete within timeout", "weight": 1.5, "source": "avocado"},
        ]
    },
    "environment_issue": {
        "patterns": [
            {"re": r"link down", "weight": 2.0, "source": "kernel"},
            {"re": r"connectivity lost", "weight": 2.0, "source": "libvirt"},
            {"re": r"network.*down", "weight": 1.5, "source": "kernel"},
            {"re": r"host machine.*lost", "weight": 1.5, "source": "avocado"},
            # 注意：Connection removed from environment_issue，它太泛了
        ]
    },
    "case_script_issue": {
        "patterns": [
            {"re": r"assertion failed", "weight": 2.0, "source": "avocado"},
            {"re": r"test internal error", "weight": 2.0, "source": "avocado"},
            {"re": r"Traceback.*most recent call last", "weight": 2.0, "source": "avocado"},
            {"re": r"AssertionError", "weight": 2.0, "source": "avocado"},
            {"re": r"test.*error.*utils\.py", "weight": 1.5, "source": "avocado"},
        ]
    },
    "infrastructure_issue": {
        "patterns": [
            {"re": r"iscsi.*(?:failed|refused|error)", "weight": 2.0, "source": "iscsi"},
            {"re": r"iscsiadm.*[Cc]onnection refused", "weight": 2.0, "source": "iscsi"},
            {"re": r"pool.*capacity.*0", "weight": 1.5, "source": "libvirt"},
            {"re": r"nfs.*error", "weight": 1.5, "source": "kernel"},
            {"re": r"mount.*failed", "weight": 1.0, "source": "kernel"},
            {"re": r"iSCSI target not ready", "weight": 2.0, "source": "libvirt"},
        ]
    }
}


def _detect_log_source(line: str) -> str:
    """检测一行日志的来源组件"""
    line_lower = line.lower()
    if "/var/log/libvirt" in line_lower or "libvirtd" in line_lower or "virdomain" in line_lower or "virsh" in line_lower:
        return "libvirt"
    if "/var/log/qemu" in line_lower or "qemu-img" in line_lower or "[qemu]" in line_lower:
        return "qemu"
    if "kernel:" in line_lower or "kernel panic" in line_lower:
        return "kernel"
    if "dmesg" in line_lower:
        return "dmesg"
    if "/var/log/messages" in line_lower:
        return "messages"
    if "/var/log/avocado" in line_lower or "avocado" in line_lower:
        return "avocado"
    if "iscsi" in line_lower:
        return "iscsi"
    return "unknown"


def _extract_evidence_lines(log_content: str, pattern: str, max_lines: int = 3) -> List[str]:
    """提取匹配规则的完整日志行"""
    lines = log_content.split("\n")
    evidence = []
    regex = re.compile(pattern, re.IGNORECASE)
    for line in lines:
        if regex.search(line):
            evidence.append(line.strip())
            if len(evidence) >= max_lines:
                break
    return evidence


def match_failure_type(log_content: str) -> Dict:
    """
    根据日志内容匹配失败类型（加权版）

    Args:
        log_content: 日志文本内容

    Returns:
        Dict with scored types and evidence
    """
    type_scores: Dict[str, float] = {}
    type_evidence: Dict[str, List[str]] = {}

    for failure_type, rule_def in FAILURE_RULES.items():
        total_score = 0.0
        all_evidence = []

        for rule in rule_def["patterns"]:
            pattern = rule["re"]
            weight = rule["weight"]
            expected_source = rule["source"]

            regex = re.compile(pattern, re.IGNORECASE)
            found_lines = _extract_evidence_lines(log_content, pattern, max_lines=2)

            if found_lines:
                # 检测日志来源，匹配来源加权
                source_bonus = 1.0
                for line in found_lines:
                    detected_source = _detect_log_source(line)
                    if detected_source == expected_source:
                        source_bonus = LOG_SOURCE_WEIGHTS.get(detected_source, 1.0)
                        break

                total_score += weight * source_bonus
                all_evidence.extend(found_lines)

        if total_score > 0:
            type_scores[failure_type] = total_score
            type_evidence[failure_type] = all_evidence[:3]

    # 按得分排序
    sorted_types = sorted(type_scores.items(), key=lambda x: -x[1])

    if not sorted_types:
        return {
            "success": True,
            "matched_types": [],
            "primary_type": "unknown_failure",
            "scores": {},
            "evidence": {},
            "confidence": "low"
        }

    # 判断置信度
    primary_type = sorted_types[0][0]
    primary_score = sorted_types[0][1]
    has_gap = len(sorted_types) == 1 or (sorted_types[0][1] - sorted_types[1][1]) >= 1.0

    confidence = "high" if has_gap and primary_score >= 2.0 else "medium"

    return {
        "success": True,
        "matched_types": [t[0] for t in sorted_types],
        "primary_type": primary_type,
        "scores": {t[0]: round(t[1], 2) for t in sorted_types},
        "evidence": type_evidence,
        "confidence": confidence
    }


def classify_failure(log_content: str, test_name: str = "", fail_reason: str = "") -> Dict:
    """
    综合分类失败类型（规则 + 上下文 + 加权）

    Args:
        log_content: 日志内容
        test_name: 测试名称
        fail_reason: Avocado 记录的失败原因

    Returns:
        分类结果
    """
    # 先用规则匹配
    rule_result = match_failure_type(log_content)

    # 如果规则匹配到且置信度高，直接返回
    if rule_result["matched_types"] and rule_result["confidence"] == "high":
        return {
            "success": True,
            "failure_type": rule_result["primary_type"],
            "confidence": rule_result["confidence"],
            "evidence": rule_result["evidence"],
            "scores": rule_result.get("scores", {}),
            "method": "rule_engine"
        }

    # 规则匹配到但置信度不高，结合 fail_reason 辅助判断
    if rule_result["matched_types"] and fail_reason:
        reason_result = match_failure_type(fail_reason)
        if reason_result["matched_types"]:
            # 如果 fail_reason 的首选项和日志匹配类型一致，提升置信度
            if reason_result["primary_type"] == rule_result["primary_type"]:
                return {
                    "success": True,
                    "failure_type": rule_result["primary_type"],
                    "confidence": "high",
                    "evidence": rule_result["evidence"],
                    "scores": rule_result.get("scores", {}),
                    "method": "rule_engine_confirmed"
                }
            # 不一致时取日志得分更高的
            return {
                "success": True,
                "failure_type": rule_result["primary_type"],
                "confidence": "medium",
                "evidence": rule_result["evidence"],
                "scores": rule_result.get("scores", {}),
                "method": "rule_engine_with_reason"
            }

    # 规则匹配到但置信度低
    if rule_result["matched_types"]:
        return {
            "success": True,
            "failure_type": rule_result["primary_type"],
            "confidence": rule_result["confidence"],
            "evidence": rule_result["evidence"],
            "scores": rule_result.get("scores", {}),
            "method": "rule_engine"
        }

    # 规则未匹配，尝试从 fail_reason 推断
    if fail_reason:
        reason_result = match_failure_type(fail_reason)
        if reason_result["matched_types"]:
            return {
                "success": True,
                "failure_type": reason_result["primary_type"],
                "confidence": "medium",
                "evidence": reason_result["evidence"],
                "scores": reason_result.get("scores", {}),
                "method": "fail_reason_inference"
            }

    # 无法分类，交给 LLM
    return {
        "success": True,
        "failure_type": "unknown_failure",
        "confidence": "low",
        "evidence": {},
        "scores": {},
        "method": "unmatched"
    }


# OpenCLAW Tool 注册信息
TOOL_METADATA = {
    "name": "rule_match",
    "description": "Match failure types from log content using rule engine",
    "parameters": {
        "log_content": "string - log text to analyze",
        "test_name": "string - test case name (optional)",
        "fail_reason": "string - fail reason from Avocado (optional)"
    },
    "returns": "JSON with matched failure type and evidence",
    "enabled": True
}


if __name__ == "__main__":
    # 测试
    test_log = """
    ==> /var/log/messages <==
    2026-04-12 09:05:10.123+08:00 kernel: Out of memory: Kill process 5421 (qemu-kvm) score 950
    2026-04-12 09:05:10.234+08:00 kernel: Killed process 5421 total-vm:16384000kB
    """

    result = match_failure_type(test_log)
    print(result)
