"""
OpenCLAW Tool: model_chain
置信度驱动的模型升级链

设计原则：
1. 规则引擎覆盖 80% 高频问题（成本≈0）
2. 不确定的升级到快速模型（MiniMax，成本低速度快）
3. 仍不确定的升级到推理模型（DeepSeek Reasoner，最强但最贵）
4. 每级只在需要时触发，避免浪费

面试话术：
"我设计了一个置信度驱动的模型升级链。不是所有日志都丢给大模型——
规则引擎覆盖 80% 高频问题零成本，只有不确定的才逐步升级模型。
每天 150 个用例只有十几个需要调模型，大部分用快速模型就够了，
推理模型只处理最难的。这样成本从'全用最强模型'的 N 元降到 0.1N。"
"""

import json
from typing import Dict, List, Optional


# ─── 模型层级定义 ──────────────────────────────────────────────

MODEL_TIERS = {
    0: {
        "name": "rule_engine",
        "description": "规则引擎（零成本）",
        "cost": 0,
        "speed": "instant",
        "suitable_for": "高频常见问题"
    },
    1: {
        "name": "fast_model",
        "description": "快速模型（低成本，高速）",
        "config": {
            "provider": "minimax",
            "model": "MiniMax-M2.7-highspeed",
            "api_base": "https://api.minimaxi.com/v1",
            "temperature": 0.2,
            "max_tokens": 2000,
        },
        "cost": 0.01,
        "speed": "fast",
        "suitable_for": "中等置信度补充判断"
    },
    2: {
        "name": "reasoning_model",
        "description": "推理模型（高成本，最强）",
        "config": {
            "provider": "deepseek",
            "model": "deepseek-reasoner",
            "api_base": "https://api.deepseek.com/v1",
            "temperature": 0.1,
            "max_tokens": 4000,
        },
        "cost": 0.05,
        "speed": "slow",
        "suitable_for": "复杂问题深度推理"
    }
}

# 置信度到模型层级的映射
CONFIDENCE_TIER_MAP = {
    "high": 0,     # 高置信度 → 规则引擎够用
    "medium": 1,   # 中等置信度 → 升级到快速模型
    "low": 2,      # 低置信度 → 升级到推理模型
}


def get_required_tier(confidence: str) -> int:
    """根据置信度确定需要升级到哪个层级"""
    return CONFIDENCE_TIER_MAP.get(confidence, 2)


def classify_with_model_chain(
    log_content: str,
    test_name: str = "",
    fail_reason: str = "",
    rule_result: Optional[Dict] = None,
    max_tier: int = 2,
) -> Dict:
    """
    置信度驱动的模型升级链

    流程：
    1. 规则引擎分析 → high → 结束
    2. 规则引擎 → medium → 快速模型补充 → 结束
    3. 规则引擎 → low → 推理模型深度分析 → 结束

    Args:
        log_content: 日志内容
        test_name: 测试名称
        fail_reason: 失败原因
        rule_result: 已有的规则引擎结果（避免重复计算）
        max_tier: 最高升级到哪一级（0=仅规则, 1=快速模型, 2=推理模型）

    Returns:
        最终分析结果 + 使用的模型层级 + 成本估算
    """
    from .rule_match import classify_failure
    from .llm_inference import call_llm

    chain_log = []
    total_cost = 0.0

    # Tier 0: 规则引擎
    if rule_result is None:
        rule_result = classify_failure(log_content, test_name, fail_reason)

    chain_log.append({
        "tier": 0,
        "model": "rule_engine",
        "failure_type": rule_result["failure_type"],
        "confidence": rule_result["confidence"],
        "cost": 0,
    })

    # 高置信度 → 直接返回
    if rule_result["confidence"] == "high" or max_tier == 0:
        return _build_result(
            final_type=rule_result["failure_type"],
            final_confidence=rule_result["confidence"],
            method="rule_engine",
            chain_log=chain_log,
            total_cost=total_cost,
            rule_result=rule_result,
        )

    # Tier 1: 快速模型
    if max_tier >= 1:
        tier1_config = MODEL_TIERS[1]["config"]
        tier1_result = _call_tier1(log_content, test_name, fail_reason, rule_result, tier1_config)

        chain_log.append({
            "tier": 1,
            "model": tier1_config["model"],
            "failure_type": tier1_result.get("failure_type", "unknown"),
            "confidence": tier1_result.get("confidence", "low"),
            "cost": MODEL_TIERS[1]["cost"],
        })
        total_cost += MODEL_TIERS[1]["cost"]

        # 快速模型 + 规则引擎一致 → 提升置信度
        if tier1_result.get("failure_type") == rule_result["failure_type"]:
            return _build_result(
                final_type=rule_result["failure_type"],
                final_confidence="high",
                method="rule_engine_confirmed_by_fast_model",
                chain_log=chain_log,
                total_cost=total_cost,
                rule_result=rule_result,
                tier1_result=tier1_result,
            )

        # 中等置信度且快速模型有结论 → 取快速模型结论
        if tier1_result.get("confidence") in ("high", "medium") and rule_result["confidence"] == "medium":
            return _build_result(
                final_type=tier1_result["failure_type"],
                final_confidence=tier1_result["confidence"],
                method="fast_model_override",
                chain_log=chain_log,
                total_cost=total_cost,
                rule_result=rule_result,
                tier1_result=tier1_result,
            )

    # 仍然不确定且允许升级到 Tier 2
    if max_tier >= 2:
        tier2_config = MODEL_TIERS[2]["config"]
        tier2_result = _call_tier2(log_content, test_name, fail_reason, rule_result, tier2_config)

        chain_log.append({
            "tier": 2,
            "model": tier2_config["model"],
            "failure_type": tier2_result.get("failure_type", "unknown"),
            "confidence": tier2_result.get("confidence", "low"),
            "cost": MODEL_TIERS[2]["cost"],
        })
        total_cost += MODEL_TIERS[2]["cost"]

        return _build_result(
            final_type=tier2_result.get("failure_type", rule_result["failure_type"]),
            final_confidence=tier2_result.get("confidence", "low"),
            method="reasoning_model",
            chain_log=chain_log,
            total_cost=total_cost,
            rule_result=rule_result,
            tier1_result=tier1_result if max_tier >= 1 else None,
            tier2_result=tier2_result,
        )

    # 兜底：规则引擎结果
    return _build_result(
        final_type=rule_result["failure_type"],
        final_confidence=rule_result["confidence"],
        method="rule_engine",
        chain_log=chain_log,
        total_cost=total_cost,
        rule_result=rule_result,
    )


def _call_tier1(log_content: str, test_name: str, fail_reason: str,
                rule_result: Dict, config: Dict) -> Dict:
    """Tier 1: 快速模型补充判断"""
    system_prompt = """你是虚拟化测试日志分析专家。规则引擎给出了一个中等置信度的判断，请补充分析。

输出 JSON：
{
  "failure_type": "...",
  "confidence": "high/medium/low",
  "reasoning": "..."
}"""

    user_prompt = f"""测试: {test_name}
失败原因: {fail_reason}
规则引擎判断: {rule_result['failure_type']} (置信度: {rule_result['confidence']})

日志:
```
{log_content[:2000]}
```

请补充分析并输出 JSON。"""

    result = call_llm(user_prompt, system_prompt, config)

    if not result.get("success"):
        return {"failure_type": "unknown_failure", "confidence": "low", "reasoning": "fast model failed"}

    try:
        content = result["content"]
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content.strip())
    except:
        return {"failure_type": "unknown_failure", "confidence": "low", "reasoning": "parse failed"}


def _call_tier2(log_content: str, test_name: str, fail_reason: str,
                rule_result: Dict, config: Dict) -> Dict:
    """Tier 2: 推理模型深度分析"""
    system_prompt = """你是虚拟化测试日志的高级分析专家。低层级的分析无法确定根因，请深度分析。

仔细推理，输出 JSON：
{
  "failure_type": "...",
  "confidence": "high/medium/low",
  "reasoning": "详细推理过程",
  "key_evidence": "关键日志行"
}"""

    user_prompt = f"""测试: {test_name}
失败原因: {fail_reason}
规则引擎判断: {rule_result['failure_type']} (置信度: {rule_result['confidence']})

完整日志:
```
{log_content[:3000]}
```

请深度分析并输出 JSON。"""

    result = call_llm(user_prompt, system_prompt, config)

    if not result.get("success"):
        return {"failure_type": "unknown_failure", "confidence": "low", "reasoning": "reasoning model failed"}

    try:
        content = result["content"]
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content.strip())
    except:
        return {"failure_type": "unknown_failure", "confidence": "low", "reasoning": "parse failed"}


def _build_result(final_type: str, final_confidence: str, method: str,
                  chain_log: list, total_cost: float,
                  rule_result: Dict, tier1_result: Dict = None,
                  tier2_result: Dict = None) -> Dict:
    """构建最终结果"""
    return {
        "failure_type": final_type,
        "confidence": final_confidence,
        "method": method,
        "chain_log": chain_log,
        "total_cost": round(total_cost, 4),
        "tiers_used": len(chain_log),
        "rule_result": rule_result,
        "tier1_result": tier1_result,
        "tier2_result": tier2_result,
    }


# OpenCLAW Tool 注册信息
TOOL_METADATA = {
    "name": "model_chain",
    "description": "Confidence-driven model upgrade chain for cost-optimal analysis",
    "parameters": {
        "log_content": "string - log content",
        "test_name": "string - test case name",
        "fail_reason": "string - fail reason",
        "rule_result": "dict - existing rule engine result",
        "max_tier": "int - max upgrade tier (0/1/2)",
    },
    "returns": "JSON with final diagnosis, chain log, and cost",
    "enabled": True
}
