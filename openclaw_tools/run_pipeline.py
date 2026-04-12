#!/usr/bin/env python3
"""
OpenCLAW Agent Pipeline - 运行完整的日志归因流程

这个脚本模拟 OpenCLAW Agent 的工作流程：
1. Parser Agent - 解析 Avocado results.json
2. Collector Agent - 收集日志
3. Analyzer Agent - 规则引擎 + LLM 分析
4. Reporter Agent - 生成报告

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


# 默认配置
DEFAULT_JOB_ROOT = "mock_data/job-results/job-20260412-001"
DEFAULT_OUTPUT_DIR = "output"


def run_parser_agent(job_root: str) -> dict:
    """
    Agent 1: Parser - 解析 Avocado 结果
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

    print(f"✓ 读取到 {result['total_tests']} 个测试用例")
    print(f"✓ 失败用例: {result['failed_count']} 个")

    return {
        "job_info": {
            "job_id": data.get("job_id"),
            "build_id": data.get("build_id"),
            "date": data.get("date"),
            "host": data.get("host"),
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
                "log_content": log_result["content"]
            })
        else:
            print(f"  ⚠ {log_result.get('error', '未知错误')}")
            collected.append({
                "test_id": test_id,
                "test_name": test_name,
                "fail_reason": test.get("fail_reason", ""),
                "error_type": test.get("error_type", ""),
                "log_content": ""
            })

    print(f"\n✓ 共收集 {len(collected)} 个失败用例的日志")
    return collected


def run_analyzer_agent(failed_tests: list, use_llm: bool = False) -> list:
    """
    Agent 3: Analyzer - 规则引擎 + LLM 分析
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

        # LLM 补充分析：低/中置信度必须调；高置信度可选调（做交叉验证）
        llm_result = None
        if use_llm and rule_result["confidence"] != "high":
            print(f"  🤖 调用 LLM 补充分析...")
            llm_result = analyze_log_with_llm(log_content, test_name, rule_result)

            if llm_result["success"]:
                try:
                    # 尝试解析 LLM 返回的 JSON
                    llm_analysis = json.loads(llm_result["content"])
                    print(f"  🤖 LLM: {llm_analysis.get('failure_type', 'unknown')}")
                except:
                    print(f"  ⚠ LLM 返回格式异常")

        analyzed.append({
            "test_name": test_name,
            "failure_type": rule_result["failure_type"],
            "confidence": rule_result["confidence"],
            "evidence": rule_result.get("evidence", {}),
            "root_cause": _extract_root_cause(rule_result, llm_result),
            "suggestion": _extract_suggestion(rule_result, llm_result)
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
        # 取 primary_type 对应的证据
        primary = rule_result.get("failure_type", "")
        if primary in evidence and evidence[primary]:
            return evidence[primary][0][:120]
        # 兜底取第一个有证据的
        first_type = list(evidence.keys())[0]
        if evidence[first_type]:
            return evidence[first_type][0][:120]
    return "Unknown"


def _extract_suggestion(rule_result: dict, llm_result: dict) -> str:
    """提取建议"""
    if llm_result and llm_result.get("success"):
        try:
            analysis = json.loads(llm_result["content"])
            return analysis.get("suggestion", "")
        except:
            pass

    # 基于失败类型给建议
    suggestions = {
        "libvirt_error": "检查 libvirtd 服务状态，查看 libvirt 版本兼容性",
        "qemu_crash": "检查 QEMU 进程崩溃原因，查看 dmesg 和 QEMU 日志",
        "kernel_panic": "分析内核崩溃转储，检查虚拟机配置",
        "memory_issue": "检查宿主机内存使用情况，增加可用内存",
        "timeout": "增加测试超时时间，排查网络或存储性能问题",
        "environment_issue": "检查网络连通性和存储挂载状态",
        "case_script_issue": "检查测试用例脚本，修复断言或配置问题",
        "infrastructure_issue": "检查存储服务和网络配置"
    }

    return suggestions.get(rule_result["failure_type"], "需要人工进一步排查")


def run_reporter_agent(job_info: dict, analyzed: list, output_dir: str = "output") -> None:
    """
    Agent 4: Reporter - 生成报告
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

    # Mercury payload（用于调试）
    mercury = render_mercury_payload(job_info, analyzed)
    print(f"\n📤 Mercury Payload:")
    print(json.dumps(mercury["payload"], indent=2, ensure_ascii=False)[:500] + "...")


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

    # Step 1: Parser
    parser_result = run_parser_agent(args.job_root)
    if not parser_result:
        print("❌ Parser 失败，退出")
        return 1

    # Step 2: Collector
    collected = run_collector_agent(args.job_root, parser_result["failed_tests"])

    # Step 3: Analyzer
    analyzed = run_analyzer_agent(collected, use_llm=args.use_llm)

    # Step 4: Reporter
    run_reporter_agent(parser_result["job_info"], analyzed, args.output)

    print("\n" + "=" * 60)
    print("✅ Pipeline 完成!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
