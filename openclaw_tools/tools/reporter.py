"""
OpenCLAW Tool: reporter
生成报告并推送到 Mercury/IM 渠道
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


def render_markdown_report(
    job_info: Dict,
    failures: List[Dict],
    output_path: str = "output/report.md"
) -> Dict:
    """
    生成 Markdown 报告
    """
    # 构建失败用例表格
    failures_table = []
    for f in failures:
        failures_table.append(
            f"| {f.get('test_name', 'N/A')} | {f.get('failure_type', 'unknown')} | "
            f"{f.get('root_cause', 'N/A')[:50]} | {f.get('confidence', 'low')} |"
        )

    failures_table_str = "\n".join(failures_table) if failures_table else "| - | - | - | - |"

    # 构建建议
    suggestions = []
    type_counts = {}
    for f in failures:
        t = f.get('failure_type', 'unknown')
        type_counts[t] = type_counts.get(t, 0) + 1

    if type_counts:
        suggestions.append("### 按类型统计")
        for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            suggestions.append(f"- **{t}**: {count} 个")

    # 模板渲染
    template = f"""# AT 工程日志归因报告

## 任务概览
- **Job ID**: {job_info.get('job_id', 'N/A')}
- **Build**: {job_info.get('build_id', 'N/A')}
- **执行时间**: {job_info.get('date', 'N/A')}
- **主机**: {job_info.get('host', 'N/A')}
- **总计**: {job_info.get('total', 0)} | **通过**: {job_info.get('passed', 0)} | **失败**: {job_info.get('failed', 0)}

## 失败用例分析

| 用例 | 类型 | 根因 | 置信度 |
|------|------|------|--------|
{failures_table_str}

## 建议

{chr(10).join(suggestions) if suggestions else '无'}

---
*由 AutoDectections Agent 自动生成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""

    # 写入文件
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(template, encoding="utf-8")

    return {
        "success": True,
        "output_path": str(output_file),
        "size": len(template)
    }


def render_json_report(
    job_info: Dict,
    failures: List[Dict],
    output_path: str = "output/report.json"
) -> Dict:
    """
    生成 JSON 报告
    """
    report = {
        "metadata": {
            "job_id": job_info.get("job_id"),
            "build_id": job_info.get("build_id"),
            "date": job_info.get("date"),
            "host": job_info.get("host"),
            "generated_at": datetime.now().isoformat()
        },
        "summary": {
            "total": job_info.get("total", 0),
            "passed": job_info.get("passed", 0),
            "failed": job_info.get("failed", 0),
            "skipped": job_info.get("skipped", 0)
        },
        "failures": failures
    }

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return {
        "success": True,
        "output_path": str(output_file)
    }


def render_mercury_payload(
    job_info: Dict,
    failures: List[Dict]
) -> Dict:
    """
    生成 Mercury 平台格式的 payload
    """
    # 按类型聚合
    type_counts = {}
    for f in failures:
        t = f.get("failure_type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    payload = {
        "title": f"AT 工程失败归因 - {job_info.get('job_id', 'N/A')}",
        "job_id": job_info.get("job_id"),
        "build_id": job_info.get("build_id"),
        "date": job_info.get("date"),
        "summary": {
            "total": job_info.get("total", 0),
            "passed": job_info.get("passed", 0),
            "failed": job_info.get("failed", 0)
        },
        "failure_breakdown": type_counts,
        "failures": [
            {
                "test_name": f.get("test_name"),
                "failure_type": f.get("failure_type"),
                "root_cause": f.get("root_cause"),
                "evidence": f.get("evidence", ""),
                "suggestion": f.get("suggestion", "")
            }
            for f in failures
        ],
        "generated_at": datetime.now().isoformat()
    }

    return {
        "success": True,
        "payload": payload
    }


def post_to_mercury(
    payload: Dict,
    endpoint: Optional[str] = None,
    token: Optional[str] = None
) -> Dict:
    """
    推送到 Mercury 平台
    """
    import requests

    endpoint = endpoint or os.environ.get("MERCURY_ENDPOINT")
    token = token or os.environ.get("MERCURY_TOKEN")

    if not endpoint:
        return {
            "success": False,
            "error": "Mercury endpoint not configured"
        }

    headers = {
        "Content-Type": "application/json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return {
            "success": True,
            "status_code": response.status_code,
            "response": response.text
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def post_to_webhook(
    payload: Dict,
    webhook_url: str,
    webhook_type: str = "slack"
) -> Dict:
    """
    推送到 Slack/飞书 Webhook
    """
    import requests

    # Slack 格式
    if webhook_type == "slack":
        slack_payload = {
            "text": f"AT 工程失败归因 - Job {payload.get('job_id', 'N/A')}",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "AT 工程日志归因报告"}
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Job ID:*\n{payload.get('job_id', 'N/A')}"},
                        {"type": "mrkdwn", "text": f"*Build:*\n{payload.get('build_id', 'N/A')}"},
                        {"type": "mrkdwn", "text": f"*失败数:*\n{payload.get('summary', {}).get('failed', 0)}"},
                        {"type": "mrkdwn", "text": f"*通过率:*\n{payload.get('summary', {}).get('passed', 0)}/{payload.get('summary', {}).get('total', 0)}"}
                    ]
                }
            ]
        }
        data = slack_payload
    else:
        # 飞书格式（简化）
        data = payload

    try:
        response = requests.post(webhook_url, json=data, timeout=30)
        response.raise_for_status()
        return {
            "success": True,
            "status_code": response.status_code
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# OpenCLAW Tool 注册信息
TOOL_METADATA = {
    "name": "reporter",
    "description": "Generate reports (Markdown/JSON) and post to Mercury/IM",
    "parameters": {
        "job_info": "dict - job metadata",
        "failures": "list - list of failure analyses",
        "output_path": "string - output file path"
    },
    "returns": "JSON with report path or API response",
    "enabled": True
}


if __name__ == "__main__":
    # 测试
    job_info = {
        "job_id": "job-20260412-001",
        "build_id": "build-5823",
        "date": "2026-04-12",
        "host": "test-runner-01",
        "total": 156,
        "passed": 142,
        "failed": 8
    }

    failures = [
        {
            "test_name": "virt_testsuite.guest_test.memory_hotplug",
            "failure_type": "libvirt_error",
            "root_cause": "Memory hotplug not supported",
            "confidence": "high"
        }
    ]

    result = render_markdown_report(job_info, failures, "output/test_report.md")
    print(json.dumps(result, indent=2))
