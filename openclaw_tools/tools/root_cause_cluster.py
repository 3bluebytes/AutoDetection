"""
OpenCLAW Tool: root_cause_cluster
根因聚类 - 跨用例关联分析

核心思想：
7个失败用例逐条分析会报7个问题，但实际上可能只有3个根因。
一次网络抖动会导致迁移超时、连接断开、存储拒绝等多个用例同时失败。
聚类 Agent 能发现这种时序和关联性，输出 N 个根因而非 N 个独立问题。

聚类维度：
1. 时间窗口：同一时段（±5分钟）的失败归为同一根因
2. 主机维度：同一 host 上的失败可能是同一个环境问题
3. 类型关联：某些失败类型天然相关（network + storage + migration）

面试话术：
"我不只是逐条归因，还有一个聚类 Agent 做跨用例关联分析。
真实场景中一次网络抖动会导致迁移超时、连接断开、存储拒绝等多个
用例同时失败，逐条分析会报 7 个问题，但聚类后只有 3 个根因。
这对运维排障的价值完全不同——修一个问题比修七个问题快得多。"
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


# ─── 关联规则定义 ──────────────────────────────────────────────

# 天然关联的失败类型组
CORRELATED_TYPES = [
    {"timeout", "environment_issue"},         # 网络问题导致超时
    {"environment_issue", "infrastructure_issue"},  # 网络问题影响存储
    {"memory_issue", "qemu_crash"},           # OOM 导致 QEMU 崩溃
    {"kernel_panic", "memory_issue"},         # 内存问题导致内核崩溃
    {"libvirt_error", "qemu_crash"},          # QEMU 崩溃导致 libvirt 报错
]

# 时间窗口（秒）
TIME_WINDOW = 300  # 5 分钟


def _parse_time(time_str: str) -> Optional[datetime]:
    """解析时间字符串"""
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(time_str, fmt)
        except:
            continue
    return None


def _are_types_correlated(type_a: str, type_b: str) -> bool:
    """判断两个失败类型是否天然关联"""
    if type_a == type_b:
        return True
    for group in CORRELATED_TYPES:
        if type_a in group and type_b in group:
            return True
    return False


def _are_time_close(time_a: Optional[datetime], time_b: Optional[datetime],
                    window: int = TIME_WINDOW) -> bool:
    """判断两个时间是否在同一个窗口内"""
    if not time_a or not time_b:
        return False
    return abs((time_a - time_b).total_seconds()) <= window


def cluster_failures(failures: List[Dict]) -> Dict:
    """
    跨用例根因聚类

    Args:
        failures: 失败用例列表，每条包含:
            test_name, failure_type, start_time, host, root_cause, evidence

    Returns:
        聚类结果
    """
    if not failures:
        return {"success": True, "clusters": [], "total_clusters": 0}

    # 构建邻接关系
    n = len(failures)
    adj = defaultdict(set)  # 用例索引 → 相关联的用例索引集合

    for i in range(n):
        for j in range(i + 1, n):
            fi, fj = failures[i], failures[j]

            # 维度 1：同一主机
            same_host = 1 if (fi.get("host") and fi.get("host") == fj.get("host")) else 0

            # 维度 2：时间窗口
            time_i = _parse_time(fi.get("start_time", ""))
            time_j = _parse_time(fj.get("start_time", ""))
            time_close = 1 if _are_time_close(time_i, time_j) else 0

            # 维度 3：类型关联
            types_related = 1 if _are_types_correlated(
                fi.get("failure_type", ""),
                fj.get("failure_type", "")
            ) else 0

            # 至少满足两个维度才关联
            correlation_score = same_host + time_close + types_related
            if correlation_score >= 2:
                adj[i].add(j)
                adj[j].add(i)

    # 连通分量（Union-Find）
    visited = set()
    clusters = []

    for i in range(n):
        if i in visited:
            continue

        # BFS 找连通分量
        cluster_indices = set()
        queue = [i]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            cluster_indices.add(node)
            for neighbor in adj.get(node, set()):
                if neighbor not in visited:
                    queue.append(neighbor)

        # 单独的用例也形成一个聚类
        cluster_indices = list(cluster_indices)
        cluster_cases = [failures[idx] for idx in cluster_indices]

        # 提取聚类特征
        cluster = _build_cluster(cluster_cases, cluster_indices)
        clusters.append(cluster)

    # 排序：影响用例多的排前面
    clusters.sort(key=lambda c: -c["affected_count"])

    return {
        "success": True,
        "clusters": clusters,
        "total_clusters": len(clusters),
        "total_cases": n,
        "reduction_ratio": round(n / len(clusters), 1) if clusters else 0,
    }


def _build_cluster(cases: List[Dict], indices: List[int]) -> Dict:
    """构建一个聚类的摘要"""
    # 统计失败类型
    type_counts = defaultdict(int)
    hosts = set()
    times = []

    for c in cases:
        type_counts[c.get("failure_type", "unknown")] += 1
        if c.get("host"):
            hosts.add(c["host"])
        if c.get("start_time"):
            t = _parse_time(c["start_time"])
            if t:
                times.append(t)

    # 确定主要类型
    primary_type = max(type_counts.items(), key=lambda x: x[1])[0] if type_counts else "unknown"

    # 确定时间范围
    time_range = ""
    if times:
        earliest = min(times)
        latest = max(times)
        time_range = f"{earliest.strftime('%H:%M:%S')} ~ {latest.strftime('%H:%M:%S')}"

    # 生成根因描述
    root_cause = _generate_cluster_root_cause(primary_type, cases, hosts, time_range)

    return {
        "cluster_id": f"cluster-{indices[0]}",
        "affected_count": len(cases),
        "cases": [c.get("test_name", "") for c in cases],
        "primary_type": primary_type,
        "type_distribution": dict(type_counts),
        "hosts": list(hosts),
        "time_range": time_range,
        "root_cause": root_cause,
        "severity": "high" if len(cases) >= 3 else ("medium" if len(cases) >= 2 else "low"),
    }


def _generate_cluster_root_cause(primary_type: str, cases: List[Dict],
                                  hosts: set, time_range: str) -> str:
    """生成聚类级别的根因描述"""
    case_names = [c.get("test_name", "") for c in cases]

    # 根据类型组合判断
    type_set = set(c.get("failure_type", "") for c in cases)

    if "environment_issue" in type_set and ("timeout" in type_set or "infrastructure_issue" in type_set):
        desc = f"网络/环境异常（{time_range}），导致 {len(cases)} 个用例失败"
        if hosts:
            desc += f"，涉及主机: {', '.join(hosts)}"
        return desc

    if "memory_issue" in type_set and "qemu_crash" in type_set:
        return f"内存不足导致 QEMU 崩溃，影响 {len(cases)} 个用例"

    if "kernel_panic" in type_set:
        return f"内核崩溃（{time_range}），影响 {len(cases)} 个用例"

    # 通用描述
    return f"{primary_type} 类问题（{time_range}），影响 {len(cases)} 个用例"


# OpenCLAW Tool 注册信息
TOOL_METADATA = {
    "name": "root_cause_cluster",
    "description": "Cross-case root cause clustering by time, host, and failure type correlation",
    "parameters": {
        "failures": "list - failure analyses with test_name, failure_type, start_time, host",
    },
    "returns": "JSON with clustered root causes",
    "enabled": True
}


if __name__ == "__main__":
    # 测试聚类
    failures = [
        {
            "test_name": "nested_kvm",
            "failure_type": "timeout",
            "start_time": "2026-04-12T08:55:00Z",
            "host": "test-runner-01",
            "root_cause": "Migration timeout"
        },
        {
            "test_name": "live_migration",
            "failure_type": "environment_issue",
            "start_time": "2026-04-12T09:15:30Z",
            "host": "test-runner-01",
            "root_cause": "Network link down"
        },
        {
            "test_name": "iscsi_pool",
            "failure_type": "infrastructure_issue",
            "start_time": "2026-04-12T09:20:00Z",
            "host": "test-runner-01",
            "root_cause": "iSCSI connection refused"
        },
        {
            "test_name": "bridge_mtu",
            "failure_type": "memory_issue",
            "start_time": "2026-04-12T09:05:12Z",
            "host": "test-runner-02",
            "root_cause": "OOM killer"
        },
        {
            "test_name": "qcow2_snapshot",
            "failure_type": "qemu_crash",
            "start_time": "2026-04-12T09:00:45Z",
            "host": "test-runner-02",
            "root_cause": "QEMU snapshot error"
        },
        {
            "test_name": "virsh_console",
            "failure_type": "kernel_panic",
            "start_time": "2026-04-12T09:10:30Z",
            "host": "test-runner-03",
            "root_cause": "VFS mount failure"
        },
        {
            "test_name": "memory_hotplug",
            "failure_type": "libvirt_error",
            "start_time": "2026-04-12T08:43:00Z",
            "host": "test-runner-01",
            "root_cause": "Memory hotplug not supported"
        },
    ]

    result = cluster_failures(failures)
    print(json.dumps(result, indent=2, ensure_ascii=False))
