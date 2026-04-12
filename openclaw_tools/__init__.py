"""
OpenCLAW Tools - AutoDectections 自定义工具集
"""

from .tools.read_local_log import read_local_log, read_job_log, read_results_json
from .tools.rule_match import match_failure_type, classify_failure
from .tools.llm_inference import call_llm, analyze_log_with_llm
from .tools.reporter import (
    render_markdown_report,
    render_json_report,
    render_mercury_payload,
    post_to_mercury,
    post_to_webhook
)

__all__ = [
    # 日志读取
    "read_local_log",
    "read_job_log",
    "read_results_json",
    # 规则匹配
    "match_failure_type",
    "classify_failure",
    # LLM 推理
    "call_llm",
    "analyze_log_with_llm",
    # 报告生成
    "render_markdown_report",
    "render_json_report",
    "render_mercury_payload",
    "post_to_mercury",
    "post_to_webhook",
]

# 工具元数据注册表
TOOLS_REGISTRY = {
    "read_local_log": {
        "module": "tools.read_local_log",
        "description": "读取 Avocado 测试日志文件",
        "enabled": True
    },
    "rule_match": {
        "module": "tools.rule_match",
        "description": "规则引擎匹配失败类型",
        "enabled": True
    },
    "llm_inference": {
        "module": "tools.llm_inference",
        "description": "调用 LLM API 分析日志",
        "enabled": True
    },
    "reporter": {
        "module": "tools.reporter",
        "description": "生成报告并推送",
        "enabled": True
    }
}
