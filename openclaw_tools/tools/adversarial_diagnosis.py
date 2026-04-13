"""
OpenCLAW Tool: adversarial_diagnosis
去中心化对抗诊断 - 两个 Agent 独立分析同一份日志

设计原则：
1. Agent A（规则引擎）和 Agent B（LLM）拿到的是同一份原始日志
2. 双方互不知晓对方结论，避免确认偏误
3. 结论一致 → 高置信度输出
4. 结论冲突 → 仲裁 Agent 裁决
5. 仲裁仍不确定 → 标记人工介入

面试话术：
"我设计了一个去中心化的对抗诊断机制。单一 Agent 容易陷入确认偏误——
它一旦倾向某个分类，就会在日志里找支持自己判断的证据，忽略矛盾信息。
所以我把同一份原始日志分别交给两个独立 Agent，它们互不知晓对方结论。
只有双方独立得出相同结论时，我才高置信度输出。
冲突时触发仲裁，仲裁仍然不确定的标记为人工介入。"
"""

import json
import os
from typing import Dict, List, Optional
from enum import Enum

from .rule_match import classify_failure
from .llm_inference import analyze_log_with_llm, call_llm


class DiagnosisStatus(str, Enum):
    CONSENSUS = "consensus"         # 双方一致
    CONFLICT = "conflict"           # 双方冲突，需仲裁
    ARBITRATED = "arbitrated"       # 仲裁完成
    ESCALATE = "escalate"           # 仲裁仍不确定，需人工


def diagnose_agent_a(log_content: str, test_name: str = "", fail_reason: str = "") -> Dict:
    """
    Agent A：规则引擎独立诊断
    拿到的是原始日志，不含任何其他 Agent 的结论
    """
    result = classify_failure(log_content, test_name, fail_reason)

    return {
        "agent": "rule_engine",
        "failure_type": result["failure_type"],
        "confidence": result["confidence"],
        "evidence": result.get("evidence", {}),
        "scores": result.get("scores", {}),
        "method": result.get("method", "rule_engine"),
    }


def diagnose_agent_b(log_content: str, test_name: str = "", fail_reason: str = "",
                     llm_config: Optional[Dict] = None) -> Dict:
    """
    Agent B：LLM 独立诊断
    拿到的也是原始日志，完全不知道规则引擎的结论
    """
    system_prompt = """你是一个虚拟化测试日志分析专家。你需要独立分析这份日志，判断失败类型。

注意：你必须独立做出判断，不要考虑其他分析工具可能给出的结论。

失败类型选项：
- libvirt_error: libvirt 组件错误
- qemu_crash: QEMU 进程崩溃
- kernel_panic: 内核崩溃
- memory_issue: 内存问题（OOM 等）
- timeout: 测试超时
- environment_issue: 环境问题（网络断开等）
- case_script_issue: 用例脚本问题
- infrastructure_issue: 基础设施问题
- unknown_failure: 无法判断

请用 JSON 格式输出：
{
  "failure_type": "...",
  "confidence": "high/medium/low",
  "reasoning": "你的推理过程",
  "key_evidence": "支持你判断的关键日志行"
}"""

    user_prompt = f"""测试用例: {test_name}
Avocado 记录的失败原因: {fail_reason}

日志内容:
```
{log_content[:3000]}
```

请独立分析失败原因并输出 JSON。"""

    result = call_llm(user_prompt, system_prompt, llm_config)

    if not result.get("success"):
        return {
            "agent": "llm",
            "failure_type": "unknown_failure",
            "confidence": "low",
            "reasoning": f"LLM 调用失败: {result.get('error', 'unknown')}",
            "key_evidence": "",
        }

    try:
        # 尝试从返回中提取 JSON
        content = result["content"]
        # 处理 markdown 代码块
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        analysis = json.loads(content.strip())
        return {
            "agent": "llm",
            "failure_type": analysis.get("failure_type", "unknown_failure"),
            "confidence": analysis.get("confidence", "low"),
            "reasoning": analysis.get("reasoning", ""),
            "key_evidence": analysis.get("key_evidence", ""),
        }
    except:
        return {
            "agent": "llm",
            "failure_type": "unknown_failure",
            "confidence": "low",
            "reasoning": result.get("content", "")[:200],
            "key_evidence": "",
        }


def arbitrate(diagnosis_a: Dict, diagnosis_b: Dict, log_content: str,
              test_name: str = "", llm_config: Optional[Dict] = None) -> Dict:
    """
    仲裁 Agent：看到双方的诊断和论据，做最终裁决
    使用更强的模型（如 DeepSeek Reasoner）
    """
    system_prompt = """你是一个虚拟化日志分析的仲裁者。两个独立的 Agent 对同一份日志给出了不同的诊断结果。

你需要：
1. 评估双方论据的合理性
2. 查看原始日志做独立判断
3. 给出最终裁决

输出 JSON：
{
  "failure_type": "最终判断的失败类型",
  "confidence": "high/medium/low",
  "winner": "agent_a 或 agent_b",
  "reasoning": "为什么选择这个结论",
  "escalate": false
}

如果你也无法确定，设置 escalate: true，confidence: "low"。"""

    user_prompt = f"""测试用例: {test_name}

Agent A（规则引擎）诊断:
- 类型: {diagnosis_a['failure_type']}
- 置信度: {diagnosis_a['confidence']}
- 证据: {json.dumps(diagnosis_a.get('evidence', {}), ensure_ascii=False)[:500]}

Agent B（LLM）诊断:
- 类型: {diagnosis_b['failure_type']}
- 置信度: {diagnosis_b['confidence']}
- 推理: {diagnosis_b.get('reasoning', '')[:500]}

原始日志:
```
{log_content[:2000]}
```

请做出最终裁决。"""

    # 使用更强模型做仲裁
    arbiter_config = llm_config or {}
    if not arbiter_config.get("model"):
        arbiter_config = {
            "provider": "deepseek",
            "model": "deepseek-reasoner",
            "api_base": "https://api.deepseek.com/v1",
            "temperature": 0.1,
            "max_tokens": 2000,
        }

    result = call_llm(user_prompt, system_prompt, arbiter_config)

    if not result.get("success"):
        return {
            "status": DiagnosisStatus.ESCALATE,
            "failure_type": "unknown_failure",
            "confidence": "low",
            "reasoning": f"仲裁失败: {result.get('error', 'unknown')}",
            "escalate": True,
        }

    try:
        content = result["content"]
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        analysis = json.loads(content.strip())
        escalate = analysis.get("escalate", False)

        return {
            "status": DiagnosisStatus.ESCALATE if escalate else DiagnosisStatus.ARBITRATED,
            "failure_type": analysis.get("failure_type", "unknown_failure"),
            "confidence": analysis.get("confidence", "low"),
            "winner": analysis.get("winner", ""),
            "reasoning": analysis.get("reasoning", ""),
            "escalate": escalate,
        }
    except:
        return {
            "status": DiagnosisStatus.ESCALATE,
            "failure_type": "unknown_failure",
            "confidence": "low",
            "reasoning": "仲裁结果解析失败",
            "escalate": True,
        }


def adversarial_diagnose(
    log_content: str,
    test_name: str = "",
    fail_reason: str = "",
    llm_config: Optional[Dict] = None,
    enable_llm: bool = True
) -> Dict:
    """
    去中心化对抗诊断 - 主入口

    流程：
    1. Agent A 和 Agent B 独立诊断
    2. 对比结论
    3. 一致 → 共识输出
    4. 冲突 → 仲裁
    5. 仲裁不确定 → 人工介入

    Args:
        log_content: 原始日志内容
        test_name: 测试名称
        fail_reason: Avocado 记录的失败原因
        llm_config: LLM 配置
        enable_llm: 是否启用 LLM（关闭则只走规则引擎）

    Returns:
        对抗诊断结果
    """
    # Agent A：规则引擎（始终运行）
    diag_a = diagnose_agent_a(log_content, test_name, fail_reason)

    # Agent B：LLM（可选）
    if not enable_llm:
        return {
            "status": DiagnosisStatus.CONSENSUS,
            "failure_type": diag_a["failure_type"],
            "confidence": diag_a["confidence"],
            "agent_a": diag_a,
            "agent_b": None,
            "arbitration": None,
            "escalate": False,
        }

    diag_b = diagnose_agent_b(log_content, test_name, fail_reason, llm_config)

    # 对比结论
    if diag_a["failure_type"] == diag_b["failure_type"]:
        # 双方一致 → 高置信度
        final_confidence = _merge_confidence(diag_a["confidence"], diag_b["confidence"])

        return {
            "status": DiagnosisStatus.CONSENSUS,
            "failure_type": diag_a["failure_type"],
            "confidence": final_confidence,
            "agent_a": diag_a,
            "agent_b": diag_b,
            "arbitration": None,
            "escalate": False,
        }

    # 双方冲突 → 仲裁
    arbitration = arbitrate(diag_a, diag_b, log_content, test_name, llm_config)

    if arbitration.get("escalate"):
        # 仲裁仍不确定 → 人工介入
        return {
            "status": DiagnosisStatus.ESCALATE,
            "failure_type": arbitration.get("failure_type", "unknown_failure"),
            "confidence": "low",
            "agent_a": diag_a,
            "agent_b": diag_b,
            "arbitration": arbitration,
            "escalate": True,
            "escalate_reason": _build_escalate_reason(diag_a, diag_b, arbitration),
        }

    # 仲裁完成
    return {
        "status": DiagnosisStatus.ARBITRATED,
        "failure_type": arbitration["failure_type"],
        "confidence": arbitration.get("confidence", "medium"),
        "agent_a": diag_a,
        "agent_b": diag_b,
        "arbitration": arbitration,
        "escalate": False,
    }


def _merge_confidence(conf_a: str, conf_b: str) -> str:
    """合并双方置信度"""
    confidence_order = {"high": 3, "medium": 2, "low": 1}
    # 双方一致时取较高的
    if confidence_order.get(conf_a, 0) >= confidence_order.get(conf_b, 0):
        # 如果双方都 high，保持 high；否则至少提升一级
        if conf_a == "high" and conf_b == "high":
            return "high"
        elif conf_a == "high" or conf_b == "high":
            return "high"  # 一方 high 就够
        else:
            return "medium"  # 双方都 medium → 共识下提升为 high 不合适，保持 medium
    return conf_b


def _build_escalate_reason(diag_a: Dict, diag_b: Dict, arbitration: Dict) -> str:
    """构建人工介入原因"""
    return (
        f"Agent A 判定: {diag_a['failure_type']} (置信度: {diag_a['confidence']}); "
        f"Agent B 判定: {diag_b['failure_type']} (置信度: {diag_b['confidence']}); "
        f"仲裁结果: {arbitration.get('failure_type', 'unknown')} "
        f"(置信度: {arbitration.get('confidence', 'low')}); "
        f"建议人工复核确认根因"
    )


# OpenCLAW Tool 注册信息
TOOL_METADATA = {
    "name": "adversarial_diagnosis",
    "description": "Decentralized adversarial diagnosis with two independent agents and arbitration",
    "parameters": {
        "log_content": "string - raw log content",
        "test_name": "string - test case name",
        "fail_reason": "string - fail reason from Avocado",
        "enable_llm": "bool - enable LLM agent (default: True)",
    },
    "returns": "JSON with diagnosis status, agent results, and arbitration if needed",
    "enabled": True
}


if __name__ == "__main__":
    # 测试对抗诊断
    test_log = """
    ==> /var/log/libvirt/libvirtd.log <==
    2026-04-12 08:41:23.456+08:00 error: virDomainMemoryPlug:1712 - Operation not supported: device 'memory' not supported
    2026-04-12 08:41:23.678+08:00 error: Domain memory_hotplug: Failed to attach memory device

    ==> /var/log/qemu/qemu-1.log <==
    2026-04-12 08:41:23.123+08:00 [qemu] error: kvm_set_device_memory_region: KVM_CAP_DEVICE_MEM_SUPPORT not available
    """

    print("=== 对抗诊断测试（仅规则引擎）===")
    result = adversarial_diagnose(
        test_log,
        test_name="virt_testsuite.guest_test.memory_hotplug",
        fail_reason="libvirt error: Failed to attach memory device",
        enable_llm=False
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    print("\n=== 对抗诊断测试（规则引擎 + LLM）===")
    result = adversarial_diagnose(
        test_log,
        test_name="virt_testsuite.guest_test.memory_hotplug",
        fail_reason="libvirt error: Failed to attach memory device",
        enable_llm=True
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
