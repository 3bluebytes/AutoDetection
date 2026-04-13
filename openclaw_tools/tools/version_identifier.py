"""
OpenCLAW Tool: version_identifier
版本识别 + 已知问题匹配 + 责任人映射
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional


# ─── 已知问题知识库 ──────────────────────────────────────────

KNOWN_ISSUES_PATH = Path(__file__).parent / "known_issues.json"


def load_known_issues(path: str = "") -> List[Dict]:
    """加载已知问题知识库"""
    p = Path(path) if path else KNOWN_ISSUES_PATH
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def match_known_issue(log_content: str, uvp_version: str = "") -> Optional[Dict]:
    """
    从已知问题库中匹配

    Args:
        log_content: 日志内容
        uvp_version: UVP 版本号

    Returns:
        匹配到的已知问题，或 None
    """
    issues = load_known_issues()

    for issue in issues:
        pattern = issue.get("pattern", "")
        if not pattern:
            continue

        regex = re.compile(pattern, re.IGNORECASE)
        if regex.search(log_content):
            # 版本范围检查
            version_range = issue.get("version_range", [])
            if version_range and uvp_version:
                v_min, v_max = version_range[0], version_range[-1]
                if v_min <= uvp_version <= v_max:
                    return issue
                # 版本不在范围内，仍然返回但标记
                return {**issue, "version_match": False}
            # 没有版本限制或没有版本信息
            return {**issue, "version_match": True if not version_range else None}

    return None


# ─── 版本识别 ──────────────────────────────────────────────────

def extract_uvp_version(results_data: Dict) -> str:
    """
    从 Avocado results.json 中提取 UVP 版本号

    真实场景中版本信息可能在不同位置：
    - results.json 顶层字段
    - sysinfo/ 下的系统信息文件
    - job.log 中的版本行

    Args:
        results_data: results.json 解析后的数据

    Returns:
        UVP 版本字符串
    """
    # 尝试多种位置
    # 1. 顶层字段
    for key in ["uvp_version", "version", "build_version", "product_version"]:
        if key in results_data:
            return str(results_data[key])

    # 2. sysinfo 字段
    sysinfo = results_data.get("sysinfo", {})
    if isinstance(sysinfo, dict):
        for key in ["uvp_version", "version"]:
            if key in sysinfo:
                return str(sysinfo[key])

    # 3. 从 build_id 推断（mock 场景）
    build_id = results_data.get("build_id", "")
    if build_id:
        return f"4.8.0-{build_id}"

    return ""


def extract_version_from_log(log_content: str) -> str:
    """
    从日志内容中提取版本信息

    常见格式：
    - UVP Version: 4.8.0-xxx
    - libvirt-9.0.0-xxx
    - qemu-kvm-8.2.0-xxx
    """
    patterns = [
        r"UVP\s*[Vv]ersion[:\s]+([\d.\w-]+)",
        r"libvirt-([\d.]+-[\d.\w]+)",
        r"qemu-kvm-([\d.]+-[\d.\w]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, log_content)
        if match:
            return match.group(1)
    return ""


# ─── 责任人映射 ────────────────────────────────────────────────

COMPONENT_TEAM_MAP = {
    "libvirt_error": {"team": "计算组", "owner": "张三"},
    "qemu_crash": {"team": "计算组", "owner": "李四"},
    "kernel_panic": {"team": "内核组", "owner": "王五"},
    "memory_issue": {"team": "内核组", "owner": "赵六"},
    "timeout": {"team": "软硬协同组", "owner": "钱七"},
    "environment_issue": {"team": "软硬协同组", "owner": "孙八"},
    "case_script_issue": {"team": "计算组", "owner": "周九"},
    "infrastructure_issue": {"team": "存储组", "owner": "吴十"},
    "unknown_failure": {"team": "待定", "owner": "待定"},
}

# 组件到 git 仓库的映射（用于 RAG Wiki）
COMPONENT_REPO_MAP = {
    "libvirt": {"repo": "https://gitlab.com/libvirt/libvirt.git", "branch": "v9.0.0"},
    "qemu": {"repo": "https://gitlab.com/qemu-project/qemu.git", "branch": "v8.2.0"},
    "dpdk": {"repo": "https://dpdk.org/git/dpdk", "branch": "v23.11"},
    "ovs": {"repo": "https://github.com/openvswitch/ovs.git", "branch": "v3.3.0"},
    "kernel": {"repo": "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git", "branch": "v5.15"},
}


def get_responsibility(failure_type: str) -> Dict:
    """根据失败类型获取责任人和团队"""
    return COMPONENT_TEAM_MAP.get(failure_type, {"team": "待定", "owner": "待定"})


def get_component_repo(component: str) -> Dict:
    """根据组件名获取 git 仓库信息"""
    return COMPONENT_REPO_MAP.get(component, {})


# OpenCLAW Tool 注册信息
TOOL_METADATA = {
    "name": "version_identifier",
    "description": "Extract UVP version, match known issues, map responsibility",
    "parameters": {
        "results_data": "dict - parsed results.json",
        "log_content": "string - log text",
        "failure_type": "string - classified failure type",
    },
    "returns": "JSON with version, known issue, responsibility info",
    "enabled": True
}
