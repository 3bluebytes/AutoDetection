#!/usr/bin/env python3
"""
OpenCLAW Agent Pipeline - 运行完整的日志归因流程

Agent 工作流：
1. Parser Agent    - 解析 Avocado results.json，识别版本
2. Collector Agent  - 收集日志
3. Analyzer Agent   - 规则引擎 + LLM 分析 + 已知问题匹配
4. Reporter Agent   - 生成 Excel/Markdown/JSON 报告 + 累计统计

实际使用时，这些 Agent 会通过 OpenCLAW Gateway 通信运行
"""

import json
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from openclaw_tools import (
    read_results_json,
    read_local_log,
    read_job_log,
    match_failure_type,
    classify_failure,
    analyze_log_with_llm,
    render_markdown_report,
    render_json_report,
    render_mercury_payload
)
from openclaw_tools.tools.excel_reporter import (
    render_daily_excel,
    render_stats_excel,
    compute_case_stats
)
from openclaw_tools.tools.version_identifier import (
    extract_uvp_version,
    match_known_issue,
    get_responsibility
)


# 默认配置
DEFAULT_JOB_ROOT = "mock_data/job-results/job-20260412-001"
DEFAULT_OUTPUT_DIR = "output"


def run_parser_agent(job_root: str) -> dict:
    """
    Agent 1: Parser - 解析 Avocado 结果 + 版本识别
    """
    print("\n" + "=" * 60)
    print("🔍 Agent 1: Parser - 解析 Avocado 结果")
    print("=" * 60)

    result = read_results_json(job_root)

    if not result["success"]:
        print(f"❌ 解析失败: {result.get('error')}")
        return None

    data = result["data"]
    failed_tests = [t for t in data.get("tests", []) if t.get("status") == "FAIL"]

    # 版本识别
    uvp_version = extract_uvp_version(data)
    print(f"✓ 读取到 {result['total_tests']} 个测试用例")
    print(f"✓ 失败用例: {result['failed_count']} 个")
    print(f"✓ UVP 版本: {uvp_version or '未识别'}")

    return {
        "job_info": {
            "job_id": data.get("job_id"),
            "build_id": data.get("build_id"),
            "date": data.get("date"),
            "host": data.get("host"),
            "uvp_version": uvp_version,
            "operator": data.get("operator", ""),
            "total": data.get("total"),
            "passed": data.get("passed"),
            "failed": data.get("failed"),
            "skipped": data.get("skipped")
        },
        "failed_tests": failed_tests
    }


def run_collector_agent(job_root: str, failed_tests: list) -> list:
    """
    Agent 2: Collector - 收集日志
    """
    print("\n" + "=" * 60)
    print("📂 Agent 2: Collector - 收集日志")
    print("=" * 60)

    collected = []

    for test in failed_tests:
        test_id = test.get("id")
        test_name = test.get("name")

        print(f"\n📄 收集日志: {test_name} (ID: {test_id})")

        # 读取用例的 debug.log
        log_result = read_local_log(job_root, test_id, "debug.log")

        if log_result["success"]:
            print(f"  ✓ 读取到 {log_result.get('size', 0)} 字节")
            collected.append({
                "test_id": test_id,
                "test_name": test_name,
                "fail_reason": test.get("fail_reason", ""),
                "error_type": test.get("error_type", ""),
                "duration": test.get("time", 0),
                "log_content": log_result["content"]
            })
        else:
            print(f"  ⚠ {log_result.get('error', '未知错误')}")
            collected.append({
                "test_id": test_id,
                "test_name": test_name,
                "fail_reason": test.get("fail_reason", ""),
                "error_type": test.get("error_type", ""),
                "duration": test.get("time", 0),
                "log_content": ""
            })

    print(f"\n✓ 共收集 {len(collected)} 个失败用例的日志")
    return collected


def run_analyzer_agent(failed_tests: list, uvp_version: str = "", use_llm: bool = False) -> list:
    """
    Agent 3: Analyzer - 规则引擎 + LLM + 已知问题匹配 + 责任人映射
    """
    print("\n" + "=" * 60)
    print("🧠 Agent 3: Analyzer - 分析失败原因")
    print("=" * 60)

    analyzed = []

    for test in failed_tests:
        test_name = test["test_name"]
        log_content = test["log_content"]
        fail_reason = test.get("fail_reason", "")

        print(f"\n🔎 分析: {test_name}")

        # 规则引擎分类
        rule_result = classify_failure(log_content, test_name, fail_reason)
        scores_str = f" (得分: {rule_result.get('scores', {})})" if rule_result.get('scores') else ""
        print(f"  📊 规则引擎: {rule_result['failure_type']} (置信度: {rule_result['confidence']}){scores_str}")

        # LLM 补充分析：低/中置信度调用
        llm_result = None
        if use_llm and rule_result["confidence"] != "high":
            print(f"  🤖 调用 LLM 补充分析...")
            llm_result = analyze_log_with_llm(log_content, test_name, rule_result)

            if llm_result["success"]:
                try:
                    llm_analysis = json.loads(llm_result["content"])
                    print(f"  🤖 LLM: {llm_analysis.get('failure_type', 'unknown')}")
                except:
                    print(f"  ⚠ LLM 返回格式异常")

        # 已知问题匹配
        known_issue = match_known_issue(log_content, uvp_version)
        if known_issue:
            print(f"  🔗 已知问题: {known_issue['id']} - {known_issue['summary']}")
        else:
            print(f"  🔗 已知问题: 无匹配")

        # 责任人映射
        resp = get_responsibility(rule_result["failure_type"])
        print(f"  👤 责任人: {resp['owner']} ({resp['team']})")

        analyzed.append({
            "test_name": test_name,
            "test_id": test.get("test_id", ""),
            "failure_type": rule_result["failure_type"],
            "confidence": rule_result["confidence"],
            "evidence": rule_result.get("evidence", {}),
            "method": rule_result.get("method", "rule_engine"),
            "root_cause": _extract_root_cause(rule_result, llm_result),
            "suggestion": _extract_suggestion(rule_result, llm_result, known_issue),
            "known_issue": f"{known_issue['id']}: {known_issue['summary']}" if known_issue else "",
            "owner": resp["owner"],
            "team": resp["team"],
            "duration": test.get("duration", 0),
        })

    # 统计
    type_counts = {}
    for a in analyzed:
        t = a["failure_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"\n📈 失败类型统计:")
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  - {t}: {count}")

    return analyzed


def _extract_root_cause(rule_result: dict, llm_result: dict) -> str:
    """提取根因描述"""
    if llm_result and llm_result.get("success"):
        try:
            analysis = json.loads(llm_result["content"])
            return analysis.get("root_cause", "")
        except:
            pass

    evidence = rule_result.get("evidence", {})
    if evidence:
        primary = rule_result.get("failure_type", "")
        if primary in evidence and evidence[primary]:
            return evidence[primary][0][:120]
        first_type = list(evidence.keys())[0]
        if evidence[first_type]:
            return evidence[first_type][0][:120]
    return "Unknown"


def _extract_suggestion(rule_result: dict, llm_result: dict, known_issue: dict = None) -> str:
    """提取建议"""
    # 已知问题有修复建议优先
    if known_issue:
        return known_issue.get("summary", "")

    if llm_result and llm_result.get("success"):
        try:
            analysis = json.loads(llm_result["content"])
            return analysis.get("suggestion", "")
        except:
            pass

    suggestions = {
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

    return suggestions.get(rule_result["failure_type"], "需要人工进一步排查")


def run_reporter_agent(job_info: dict, analyzed: list, output_dir: str = "output") -> None:
    """
    Agent 4: Reporter - 生成报告（Markdown + JSON + Excel + 累计统计）
    """
    print("\n" + "=" * 60)
    print("📝 Agent 4: Reporter - 生成报告")
    print("=" * 60)

    # Markdown 报告
    md_path = os.path.join(output_dir, "report.md")
    render_markdown_report(job_info, analyzed, md_path)
    print(f"✓ Markdown 报告: {md_path}")

    # JSON 报告
    json_path = os.path.join(output_dir, "report.json")
    render_json_report(job_info, analyzed, json_path)
    print(f"✓ JSON 报告: {json_path}")

    # Excel 日报
    excel_path = os.path.join(output_dir, "daily_report.xlsx")
    excel_result = render_daily_excel(job_info, analyzed, excel_path)
    if excel_result["success"]:
        print(f"✓ Excel 日报: {excel_path}")

    # 累计统计（使用 mock 历史数据）
    stats_path = os.path.join(output_dir, "case_stats.xlsx")
    history = _load_mock_history()
    if history:
        case_stats = compute_case_stats(history)
        stats_result = render_stats_excel(case_stats, stats_path)
        if stats_result["success"]:
            print(f"✓ 累计统计: {stats_path}")

    # Mercury payload
    mercury = render_mercury_payload(job_info, analyzed)
    print(f"\n📤 Mercury Payload (前 300 字符):")
    print(json.dumps(mercury["payload"], indent=2, ensure_ascii=False)[:300] + "...")


def _load_mock_history() -> list:
    """加载 mock 历史运行记录（模拟累计统计的数据源）"""
    history_path = project_root / "mock_data" / "history.json"
    if history_path.exists():
        return json.loads(history_path.read_text(encoding="utf-8"))

    # 生成 mock 历史数据
    history = []
    import random
    test_names = [
        "virt_testsuite.guest_test.memory_hotplug",
        "virt_testsuite.guest_test.nested_kvm",
        "virt_testsuite.storage_test.qcow2_snapshot",
        "virt_testsuite.network_test.bridge_mtu",
        "virt_testsuite.guest_test.virsh_console",
        "virt_testsuite.guest_test.live_migration",
        "virt_testsuite.storage_test.iscsi_pool",
    ]
    failure_types = {
        "virt_testsuite.guest_test.memory_hotplug": "libvirt_error",
        "virt_testsuite.guest_test.nested_kvm": "timeout",
        "virt_testsuite.storage_test.qcow2_snapshot": "qemu_crash",
        "virt_testsuite.network_test.bridge_mtu": "memory_issue",
        "virt_testsuite.guest_test.virsh_console": "kernel_panic",
        "virt_testsuite.guest_test.live_migration": "environment_issue",
        "virt_testsuite.storage_test.iscsi_pool": "infrastructure_issue",
    }

    versions = ["4.5.0", "4.6.0", "4.7.0", "4.8.0"]

    for day_offset in range(30):
        date = f"2026-03-{14+day_offset:02d}"
        for name in test_names:
            # 大部分通过，少部分失败
            is_fail = random.random() < 0.3
            # Flaky: bridge_mtu 有时通过有时失败
            if "bridge_mtu" in name:
                is_fail = random.random() < 0.5

            history.append({
                "test_name": name,
                "status": "FAIL" if is_fail else "PASS",
                "duration": round(random.uniform(10, 300), 1),
                "date": date,
                "uvp_version": random.choice(versions),
                "failure_type": failure_types.get(name, "unknown") if is_fail else "",
            })

    # 保存供后续使用
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  📊 生成 mock 历史数据: {len(history)} 条记录")

    return history


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="AutoDectections Agent Pipeline")
    parser.add_argument("--job-root", default=DEFAULT_JOB_ROOT, help="Avocado job-results 目录")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_DIR, help="输出目录")
    parser.add_argument("--use-llm", action="store_true", help="启用 LLM 分析")

    args = parser.parse_args()

    print("\n🚀 AutoDectections Agent Pipeline")
    print(f"📁 Job Root: {args.job_root}")
    print(f"🤖 LLM: {'启用' if args.use_llm else '禁用'}")

    # Step 1: Parser + 版本识别
    parser_result = run_parser_agent(args.job_root)
    if not parser_result:
        print("❌ Parser 失败，退出")
        return 1

    # Step 2: Collector
    collected = run_collector_agent(args.job_root, parser_result["failed_tests"])

    # Step 3: Analyzer + 已知问题 + 责任人
    analyzed = run_analyzer_agent(
        collected,
        uvp_version=parser_result["job_info"].get("uvp_version", ""),
        use_llm=args.use_llm
    )

    # Step 4: Reporter (Markdown + JSON + Excel + 累计统计)
    run_reporter_agent(parser_result["job_info"], analyzed, args.output)

    print("\n" + "=" * 60)
    print("✅ Pipeline 完成!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
