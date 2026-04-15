"""
OpenCLAW Tool: llm_inference
调用 LLM API 进行日志分析和总结
"""

import os
import json
from typing import Dict, Optional


DEFAULT_LLM_CONFIG = {
    "provider": "deepseek",  # deepseek, openai, anthropic
    "model": "deepseek-chat",
    "api_base": "https://api.deepseek.com/v1",
    "temperature": 0.3,
    "max_tokens": 1000
}


def call_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    config: Optional[Dict] = None
) -> Dict:
    """
    调用 LLM API

    Args:
        prompt: 用户提示词
        system_prompt: 系统提示词
        config: LLM 配置

    Returns:
        LLM 响应结果
    """
    config = config or DEFAULT_LLM_CONFIG

    provider = config.get("provider", "deepseek")
    model = config.get("model", "deepseek-chat")
    api_key = os.environ.get(f"{provider.upper()}_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")

    if not api_key:
        return {
            "success": False,
            "error": f"API key not found for provider: {provider}"
        }

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        if provider == "deepseek":
            return _call_deepseek(messages, api_key, config)
        elif provider == "openai":
            return _call_openai(messages, api_key, config)
        else:
            return {
                "success": False,
                "error": f"Unsupported provider: {provider}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def _call_deepseek(messages: list, api_key: str, config: Dict) -> Dict:
    """调用 DeepSeek API"""
    import requests

    url = config.get("api_base", "https://api.deepseek.com/v1") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": config.get("model", "deepseek-chat"),
        "messages": messages,
        "temperature": config.get("temperature", 0.3),
        "max_tokens": config.get("max_tokens", 1000)
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    result = response.json()
    return {
        "success": True,
        "content": result["choices"][0]["message"]["content"],
        "usage": result.get("usage", {}),
        "model": result.get("model", "")
    }


def _call_openai(messages: list, api_key: str, config: Dict) -> Dict:
    """调用 OpenAI API"""
    import requests

    url = config.get("api_base", "https://api.openai.com/v1") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": config.get("model", "gpt-4"),
        "messages": messages,
        "temperature": config.get("temperature", 0.3),
        "max_tokens": config.get("max_tokens", 1000)
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    result = response.json()
    return {
        "success": True,
        "content": result["choices"][0]["message"]["content"],
        "usage": result.get("usage", {}),
        "model": result.get("model", "")
    }


def analyze_log_with_llm(
    log_content: str,
    test_name: str,
    rule_result: Optional[Dict] = None,
    config: Optional[Dict] = None
) -> Dict:
    """
    使用 LLM 分析日志

    Args:
        log_content: 日志内容
        test_name: 测试名称
        rule_result: 规则引擎结果（可选）
        config: LLM 配置

    Returns:
        LLM 分析结果
    """
    system_prompt = """你是一个虚拟化测试日志分析专家。你的任务是分析 Avocado 测试失败的原因。

失败类型包括：
- libvirt_error: libvirt 组件错误
- qemu_crash: QEMU 进程崩溃
- kernel_panic: 内核崩溃
- memory_issue: 内存问题（OOM 等）
- timeout: 测试超时
- environment_issue: 环境问题（网络断开等）
- case_script_issue: 用例脚本问题
- infrastructure_issue: 基础设施问题

请根据日志内容，分析并输出：
1. failure_type: 失败类型
2. root_cause: 根本原因（简洁描述）
3. evidence: 支持你判断的关键日志行
4. suggestion: 后续排查建议

请用 JSON 格式输出。"""

    rule_context = ""
    if rule_result and rule_result.get("matched_types"):
        rule_context = f"\n规则引擎已识别的类型: {', '.join(rule_result['matched_types'])}"

    user_prompt = f"""测试用例: {test_name}
{rule_context}

日志内容:
```
{log_content[:3000]}  # 限制长度
```

请分析失败原因并输出 JSON 格式的分析结果。"""

    return call_llm(user_prompt, system_prompt, config)


# OpenCLAW Tool 注册信息
TOOL_METADATA = {
    "name": "llm_inference",
    "description": "Call LLM API for log analysis and summarization",
    "parameters": {
        "log_content": "string - log text to analyze",
        "test_name": "string - test case name",
        "rule_result": "dict - optional rule engine result"
    },
    "returns": "JSON with LLM analysis",
    "enabled": True
}


if __name__ == "__main__":
    # 测试
    test_log = """
    2026-04-12 08:41:23.456+08:00 error: virDomainMemoryPlug:1712 - Operation not supported: device 'memory' not supported by this hypervisor
    2026-04-12 08:41:23.678+08:00 error: Domain memory_hotplug: Failed to attach memory device
    """

    result = analyze_log_with_llm(test_log, "virt_testsuite.guest_test.memory_hotplug")
    print(json.dumps(result, indent=2, ensure_ascii=False))
