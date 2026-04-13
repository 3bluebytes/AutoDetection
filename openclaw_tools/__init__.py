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
from .tools.excel_reporter import render_daily_excel, render_stats_excel, compute_case_stats
from .tools.version_identifier import (
    extract_uvp_version,
    match_known_issue,
    get_responsibility,
    COMPONENT_TEAM_MAP,
    COMPONENT_REPO_MAP
)
from .tools.adversarial_diagnosis import adversarial_diagnose, DiagnosisStatus
from .tools.model_chain import classify_with_model_chain
from .tools.root_cause_cluster import cluster_failures
from .tools.regression_detector import detect_regressions, detect_multi_version_regressions
from .tools.rag_wiki import search_wiki, get_component_architecture

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
    # Excel 报告
    "render_daily_excel",
    "render_stats_excel",
    "compute_case_stats",
    # 版本识别
    "extract_uvp_version",
    "match_known_issue",
    "get_responsibility",
    "COMPONENT_TEAM_MAP",
    "COMPONENT_REPO_MAP",
    # 对抗诊断
    "adversarial_diagnose",
    "DiagnosisStatus",
    # 模型升级链
    "classify_with_model_chain",
    # 根因聚类
    "cluster_failures",
    # 版本回归
    "detect_regressions",
    "detect_multi_version_regressions",
    # RAG Wiki
    "search_wiki",
    "get_component_architecture",
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
        "description": "加权规则引擎匹配失败类型",
        "enabled": True
    },
    "llm_inference": {
        "module": "tools.llm_inference",
        "description": "调用 LLM API 分析日志",
        "enabled": True
    },
    "reporter": {
        "module": "tools.reporter",
        "description": "生成 Markdown/JSON 报告并推送",
        "enabled": True
    },
    "excel_reporter": {
        "module": "tools.excel_reporter",
        "description": "生成 Excel 日报和累计统计",
        "enabled": True
    },
    "version_identifier": {
        "module": "tools.version_identifier",
        "description": "版本识别、已知问题匹配、责任人映射",
        "enabled": True
    },
    "adversarial_diagnosis": {
        "module": "tools.adversarial_diagnosis",
        "description": "去中心化对抗诊断 + 仲裁",
        "enabled": True
    },
    "model_chain": {
        "module": "tools.model_chain",
        "description": "置信度驱动模型升级链",
        "enabled": True
    },
    "root_cause_cluster": {
        "module": "tools.root_cause_cluster",
        "description": "跨用例根因聚类",
        "enabled": True
    },
    "regression_detector": {
        "module": "tools.regression_detector",
        "description": "版本回归检测",
        "enabled": True
    },
    "rag_wiki": {
        "module": "tools.rag_wiki",
        "description": "UVP 组件架构 RAG 知识库",
        "enabled": True
    },
}
