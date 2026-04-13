"""
OpenCLAW Tool: regression_detector
版本回归检测 - 对比前后版本同一用例结果

检测逻辑：
1. 同一个用例上个版本 PASS → 本版本 FAIL = 回归失败
2. 同一个用例连续 2+ 版本 FAIL = 持续失败
3. 回归失败优先级 > 持续失败 > 新增失败
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict


def detect_regressions(
    current_results: List[Dict],
    previous_results: List[Dict],
    current_version: str = "",
    previous_version: str = ""
) -> Dict:
    """
    检测版本回归

    Args:
        current_results: 当前版本的用例结果列表
            [{"test_name": "...", "status": "PASS/FAIL", "failure_type": "..."}]
        previous_results: 上个版本的用例结果列表
        current_version: 当前版本号
        previous_version: 上个版本号

    Returns:
        回归检测结果
    """
    # 按用例名建立索引
    prev_map = {r["test_name"]: r for r in previous_results}
    curr_map = {r["test_name"]: r for r in current_results}

    regressions = []      # 回归失败：上个版本PASS → 本版本FAIL
    persistent = []       # 持续失败：两个版本都FAIL
    fixed = []            # 已修复：上个版本FAIL → 本版本PASS
    new_failures = []     # 新增用例失败：上个版本没有这个用例

    for name, curr in curr_map.items():
        prev = prev_map.get(name)

        if curr["status"] == "FAIL":
            if prev is None:
                new_failures.append({
                    "test_name": name,
                    "failure_type": curr.get("failure_type", ""),
                    "regression_type": "new_test",
                    "priority": "normal",
                    "detail": f"新增用例，首次执行即失败"
                })
            elif prev["status"] == "PASS":
                regressions.append({
                    "test_name": name,
                    "failure_type": curr.get("failure_type", ""),
                    "regression_type": "regression",
                    "priority": "high",
                    "detail": f"回归失败：{previous_version} PASS → {current_version} FAIL",
                    "prev_version": previous_version,
                    "curr_version": current_version,
                })
            else:
                persistent.append({
                    "test_name": name,
                    "failure_type": curr.get("failure_type", ""),
                    "regression_type": "persistent",
                    "priority": "medium",
                    "detail": f"持续失败：{previous_version} FAIL → {current_version} FAIL",
                    "failure_type_changed": curr.get("failure_type") != prev.get("failure_type"),
                })
        # PASS 的情况不需要额外处理

    # 已修复
    for name, prev in prev_map.items():
        curr = curr_map.get(name)
        if prev["status"] == "FAIL" and curr and curr["status"] == "PASS":
            fixed.append({
                "test_name": name,
                "regression_type": "fixed",
                "detail": f"已修复：{previous_version} FAIL → {current_version} PASS",
            })

    return {
        "success": True,
        "current_version": current_version,
        "previous_version": previous_version,
        "summary": {
            "regressions": len(regressions),
            "persistent": len(persistent),
            "fixed": len(fixed),
            "new_failures": len(new_failures),
        },
        "regressions": regressions,
        "persistent": persistent,
        "fixed": fixed,
        "new_failures": new_failures,
    }


def detect_multi_version_regressions(
    version_history: List[Dict],
) -> Dict:
    """
    多版本回归检测

    Args:
        version_history: 多个版本的结果列表，按版本顺序排列
            [{"version": "4.5.0", "results": [...]}, {"version": "4.6.0", "results": [...]}]

    Returns:
        跨版本回归分析
    """
    if len(version_history) < 2:
        return {"success": False, "error": "Need at least 2 versions"}

    # 按用例聚合所有版本结果
    case_versions = defaultdict(list)
    for vh in version_history:
        version = vh["version"]
        for r in vh.get("results", []):
            case_versions[r["test_name"]].append({
                "version": version,
                "status": r["status"],
                "failure_type": r.get("failure_type", ""),
            })

    # 分析每个用例的版本趋势
    case_analysis = []
    for name, versions in case_versions.items():
        # 找到首次失败的版本
        first_fail_version = None
        last_pass_version = None
        fail_count = 0
        total_count = len(versions)

        for v in versions:
            if v["status"] == "FAIL":
                fail_count += 1
                if not first_fail_version:
                    first_fail_version = v["version"]
            else:
                last_pass_version = v["version"]

        # 判断回归类型
        is_regression = False
        is_flaky = False

        if total_count >= 2:
            # 检查是否有 PASS→FAIL 的跳转
            for i in range(1, len(versions)):
                if versions[i-1]["status"] == "PASS" and versions[i]["status"] == "FAIL":
                    is_regression = True
                    break

            # Flaky：PASS 和 FAIL 交替出现
            pass_count = total_count - fail_count
            if pass_count > 0 and fail_count > 0:
                alternations = 0
                for i in range(1, len(versions)):
                    if versions[i]["status"] != versions[i-1]["status"]:
                        alternations += 1
                if alternations >= 2:
                    is_flaky = True

        case_analysis.append({
            "test_name": name,
            "total_versions": total_count,
            "fail_count": fail_count,
            "first_fail_version": first_fail_version,
            "last_pass_version": last_pass_version,
            "is_regression": is_regression,
            "is_flaky": is_flaky,
            "priority": "high" if is_regression and not is_flaky else ("medium" if is_flaky else "normal"),
        })

    # 排序：回归 > flaky > 其他
    case_analysis.sort(key=lambda x: (
        0 if x["is_regression"] and not x["is_flaky"] else
        1 if x["is_flaky"] else 2
    ))

    return {
        "success": True,
        "version_count": len(version_history),
        "versions": [vh["version"] for vh in version_history],
        "summary": {
            "regressions": sum(1 for c in case_analysis if c["is_regression"] and not c["is_flaky"]),
            "flaky": sum(1 for c in case_analysis if c["is_flaky"]),
            "stable_fail": sum(1 for c in case_analysis if c["fail_count"] > 0 and not c["is_regression"]),
        },
        "cases": case_analysis,
    }


# OpenCLAW Tool 注册信息
TOOL_METADATA = {
    "name": "regression_detector",
    "description": "Detect version regressions by comparing test results across versions",
    "parameters": {
        "current_results": "list - current version test results",
        "previous_results": "list - previous version test results",
        "current_version": "string",
        "previous_version": "string",
    },
    "returns": "JSON with regression analysis",
    "enabled": True
}


if __name__ == "__main__":
    # 测试
    prev = [
        {"test_name": "memory_hotplug", "status": "PASS"},
        {"test_name": "qcow2_snapshot", "status": "FAIL", "failure_type": "qemu_crash"},
        {"test_name": "live_migration", "status": "PASS"},
        {"test_name": "virsh_console", "status": "PASS"},
    ]

    curr = [
        {"test_name": "memory_hotplug", "status": "FAIL", "failure_type": "libvirt_error"},
        {"test_name": "qcow2_snapshot", "status": "FAIL", "failure_type": "qemu_crash"},
        {"test_name": "live_migration", "status": "PASS"},
        {"test_name": "virsh_console", "status": "FAIL", "failure_type": "kernel_panic"},
        {"test_name": "new_test", "status": "FAIL", "failure_type": "unknown"},
    ]

    result = detect_regressions(curr, prev, "4.8.0", "4.7.0")
    print(json.dumps(result, indent=2, ensure_ascii=False))
