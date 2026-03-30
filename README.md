# AutoDectections Agent

`AutoDectections` 是一个面向虚拟化 AT 工程的日志归因 Agent 骨架，按标准 Avocado 结果目录组织输入，关联 libvirt、qemu、kernel、memory 等日志，再通过规则引擎和 OpenAI-compatible 大模型生成失败用例摘要，最终输出 JSON / Markdown，并预留 Mercury 与企业通讯软件的对接接口。

这个仓库的定位不是生产版平台，而是一个可讲得通、结构完整、可继续扩展的 PoC。

## 适用场景

- 每日版本工程由 Avocado 执行测试
- 失败用例的日志散落在执行机本地与归档服务器
- 工程跑完后需要自动输出失败归因摘要
- 结果需要投递到 Mercury 看板或企业通讯软件

## 目录结构

```text
.
|-- config/
|   `-- example_config.json
|-- docs/
|   `-- mercury_payload_example.json
|-- src/
|   `-- autodetections/
|       |-- analyzers/
|       |   `-- rules.py
|       |-- connectors/
|       |   |-- archive.py
|       |   |-- avocado.py
|       |   |-- llm.py
|       |   |-- mercury.py
|       |   `-- webhook.py
|       |-- cli.py
|       |-- config.py
|       |-- models.py
|       |-- orchestrator.py
|       |-- reporters.py
|       `-- utils.py
`-- pyproject.toml
```

## Agent 工作流

```text
Avocado job-results
    -> 解析失败用例
    -> 关联本地 debug/job/sysinfo 日志
    -> 按配置拼接归档服务器 URL 拉取远程日志
    -> 规则引擎做首次归因
    -> LLM 对规则结果和关键证据做补充总结
    -> 输出 Markdown / JSON
    -> 可选投递到 Mercury / Webhook
```

## 已实现的能力

- 标准 Avocado `results.json` / `test-results/*` 结果读取
- 失败用例筛选和基础元数据建模
- 本地日志自动收集
  - `job.log`
  - `debug.log`
  - `sysinfo`
  - 目录名中包含 `libvirt` / `qemu` / `dmesg` / `messages` / `oom` / `memory` 的日志
- 归档服务器 HTTPS 拉取接口
- 规则引擎分类
  - `environment_issue`
  - `infrastructure_issue`
  - `timeout`
  - `libvirt_error`
  - `qemu_crash`
  - `kernel_panic`
  - `memory_issue`
  - `case_script_issue`
  - `unknown_failure`
- OpenAI-compatible 大模型接口
- Markdown / JSON 报告输出
- Mercury / 企业通讯 Webhook 发布接口

## 快速开始

1. 准备 Python 3.11+
2. 修改 [config/example_config.json](/E:/mysteryGarden/AutoDectections/config/example_config.json)
3. 运行：

```bash
python -m autodetections.cli --config config/example_config.json
```

也可以覆盖作业目录：

```bash
python -m autodetections.cli --config config/example_config.json --job-root E:/logs/avocado/job-results/job-20260330-001
```

## 配置说明

### `job_root`

Avocado 的 job-results 目录。标准情况下，这里会包含：

- `results.json`
- `job.log`
- `test-results/*/debug.log`
- `sysinfo/`

### `archive`

归档服务器配置。PoC 里默认按 URL 模板拼接：

```json
{
  "base_url": "https://archive.example.com",
  "auth_token_env": "ARCHIVE_TOKEN",
  "artifact_patterns": [
    {
      "name": "libvirt.log",
      "component": "libvirt",
      "path_template": "/archive/{date}/{job_id}/{case_id}/libvirt.log"
    }
  ]
}
```

可用占位符：

- `{job_id}`
- `{case_id}`
- `{case_name}`
- `{status}`
- `{date}`
- `{build_id}`
- `{host}`

### `llm`

支持 OpenAI-compatible 接口，例如 OpenAI / Azure OpenAI-compatible gateway / DeepSeek-compatible gateway / 内部模型网关。

只要兼容 `POST /chat/completions` 即可。

### `output.mercury`

PoC 假设 Mercury 接受结构化 JSON 输入。默认 payload 样例见 [docs/mercury_payload_example.json](/E:/mysteryGarden/AutoDectections/docs/mercury_payload_example.json)。

## 上游对接约定

当前骨架把“任务触发”和“日志分析”解耦了。也就是说，云龙工程 / Jenkins / 定时任务平台不需要理解日志分析细节，只需要在任务完成后把下面这些上下文传给 Agent：

- `job_root`
- `build_id`
- `date`
- `host`

最简单的接入方式有两种：

1. Jenkins 或任务平台在工程结束后执行一条命令：

```bash
python -m autodetections.cli --config config/example_config.json --job-root E:/logs/avocado/job-results/job-20260330-001
```

2. 上游系统先生成一份上下文配置，再调用 CLI。

样例见 [docs/upstream_job_event_example.json](/E:/mysteryGarden/AutoDectections/docs/upstream_job_event_example.json)。

## 关键接口设计

### 1. Avocado 解析接口

位置：[src/autodetections/connectors/avocado.py](/E:/mysteryGarden/AutoDectections/src/autodetections/connectors/avocado.py)

职责：

- 解析 `results.json`
- 回退扫描 `test-results/*`
- 输出统一 `JobRun` / `CaseResult` 模型

### 2. 归档日志接口

位置：[src/autodetections/connectors/archive.py](/E:/mysteryGarden/AutoDectections/src/autodetections/connectors/archive.py)

职责：

- 读取本地 job 目录中的关键日志
- 基于 URL 模板拼接远程日志地址
- 从 HTTPS 归档服务器下载日志正文

后续如果你们内部不是纯 HTTPS，而是先调用“云龙工程”或 Jenkins 的接口拿 URL，只需要替换这一层。

### 3. 规则分析接口

位置：[src/autodetections/analyzers/rules.py](/E:/mysteryGarden/AutoDectections/src/autodetections/analyzers/rules.py)

职责：

- 基于正则和上下文窗口抽取关键证据
- 对失败原因分类
- 为大模型提供结构化先验

### 4. 大模型接口

位置：[src/autodetections/connectors/llm.py](/E:/mysteryGarden/AutoDectections/src/autodetections/connectors/llm.py)

职责：

- 汇总失败上下文
- 基于规则分析结果生成易读摘要
- 输出责任域建议和后续排查建议

### 5. Mercury / Webhook 发布接口

位置：

- [src/autodetections/connectors/mercury.py](/E:/mysteryGarden/AutoDectections/src/autodetections/connectors/mercury.py)
- [src/autodetections/connectors/webhook.py](/E:/mysteryGarden/AutoDectections/src/autodetections/connectors/webhook.py)

职责：

- 推送结构化结果
- 支持日报看板或企业消息通知

## 推荐的落地演进

### Phase 1

用本地 Avocado 结果目录做离线分析，输出 Markdown / JSON。

### Phase 2

接入归档服务器和 Mercury。

### Phase 3

补充已知缺陷知识库、责任域映射、版本趋势统计。

## 面试怎么讲

这套 PoC 最容易讲清楚的点有 4 个：

1. 不是让大模型直接猜日志，而是先把失败用例和日志上下文收敛出来。
2. 规则引擎负责高频问题的稳定识别，LLM 只负责总结和补充判断。
3. 输出是结构化的，方便做 Mercury 看板和趋势分析。
4. 整个设计支持从 PoC 演进到生产版，不是单次脚本。

## 限制

- 当前仓库没有接入真实 Avocado 样本和真实内网接口
- 远程日志路径依赖 `artifact_patterns` 配置
- Mercury 接口按通用 REST 模式抽象，实际字段需要按内部平台调整
- 当前没有知识库去识别“已知缺陷单号”

## 你可以继续扩展的方向

- 接入 Jenkins / 云龙工程任务接口
- 引入已知问题知识库
- 做失败原因聚合统计
- 把规则配置外置成 JSON 或 YAML
- 细化组件维度，如 `storage` / `network` / `migration` / `snapshot`
