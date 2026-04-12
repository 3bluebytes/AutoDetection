# AutoDectections - 虚拟化 AT 日志归因 Agent

基于 OpenCLAW 的多 Agent 日志归因系统，面向虚拟化 AT 工程的失败用例自动分析。

## 架构

```
                        OpenCLAW Gateway
                     (ws://127.0.0.1:18789)
                              │
              ┌───────────────┼───────────────┐
              │               │               │
        ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
        │  Parser   │  │ Collector │  │ Analyzer  │
        │  Agent    │──│  Agent    │──│  Agent    │
        └───────────┘  └───────────┘  └─────┬─────┘
                                             │
                                    ┌────────▼────────┐
                                    │   Reporter Agent │
                                    └────────┬────────┘
                                             │
                              ┌──────────┬────┴────┐
                              │          │         │
                          Mercury    Slack    WeChat
```

### Agent 职责

| Agent | 职责 | 关键技术 |
|-------|------|----------|
| **Parser** | 解析 Avocado results.json，提取失败用例 | JSON 解析、正则 |
| **Collector** | 收集本地 + 远程归档日志 | 文件 I/O、HTTP 下载 |
| **Analyzer** | 规则引擎归因 + LLM 补充推理 | 加权规则匹配、LLM API |
| **Reporter** | 生成报告，推送 Mercury / IM | Markdown/JSON、Webhook |

### 核心设计

**加权规则引擎**：规则带权重和日志来源标签，匹配时根据日志来源加权计算得分，避免误分类。

**置信度驱动**：规则引擎高置信度直接输出，中等置信度用快速模型补充，低置信度用推理模型深度分析。

## 目录结构

```
.
├── mock_data/                   # 模拟 Avocado 结果数据
│   └── job-results/
│       └── job-20260412-001/
│           ├── results.json     # Avocado 测试结果
│           ├── job.log          # 主日志
│           └── test-results/    # 各用例 debug.log
├── openclaw_agents/             # Agent 配置
│   ├── 01_parser_agent.yaml
│   ├── 02_collector_agent.yaml
│   ├── 03_analyzer_agent.yaml
│   └── 04_reporter_agent.yaml
├── openclaw_tools/              # Tool 实现
│   ├── run_pipeline.py          # Pipeline 入口
│   ├── __init__.py
│   └── tools/
│       ├── read_local_log.py    # 日志读取工具
│       ├── rule_match.py        # 加权规则引擎
│       ├── llm_inference.py     # LLM 推理工具
│       └── reporter.py          # 报告生成工具
└── docs/
    └── ROADMAP.md               # 改进路线图
```

## 快速开始

### 前置条件

- OpenCLAW Gateway 运行中
- Python 3.12+ (Anaconda)
- DeepSeek API Key（可选，用于 LLM 分析）

### 运行 Pipeline

```bash
# 仅规则引擎分析
D:\Anaconda3\python.exe openclaw_tools/run_pipeline.py \
  --job-root mock_data/job-results/job-20260412-001

# 启用 LLM 深度分析
D:\Anaconda3\python.exe openclaw_tools/run_pipeline.py \
  --job-root mock_data/job-results/job-20260412-001 --use-llm
```

### 通过 OpenCLAW 触发

在微信 / WebChat 中对 Agent 说：

> 分析一下 AT 工程日志

Agent 会自动调用 avocado-analyzer Skill 执行分析并返回结果。

## 归因类型

| 类型 | 说明 | 典型证据 |
|------|------|----------|
| `libvirt_error` | libvirt 组件错误 | virDomain.*failed, Operation not supported |
| `qemu_crash` | QEMU 进程崩溃 | qemu.*fatal, bdrv_snapshot.*failed |
| `kernel_panic` | 内核崩溃 | kernel panic, VFS: Unable to mount |
| `memory_issue` | 内存问题 | oom-killer, Out of memory |
| `timeout` | 测试超时 | timeout after N seconds |
| `environment_issue` | 环境异常 | link down, connectivity lost |
| `case_script_issue` | 用例脚本问题 | assertion failed, Traceback |
| `infrastructure_issue` | 基础设施问题 | iscsi.*refused, pool.*capacity.*0 |

## 改进路线

详见 [docs/ROADMAP.md](docs/ROADMAP.md)

- **创新点 1**：多 Agent 对抗验证 + 仲裁
- **创新点 2**：置信度驱动的模型升级链
- **创新点 3**：根因聚类 - 跨用例关联分析
