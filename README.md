# AutoDectections - 虚拟化 AT 日志归因 Agent

基于 OpenCLAW 的多 Agent 日志归因系统，面向虚拟化 AT 工程的失败用例自动分析。

## 架构

```
                    OpenCLAW Gateway
                 (ws://127.0.0.1:18789)
                          │
            ┌─────────────┼─────────────┐
            │             │             │
      ┌─────▼─────┐ ┌────▼────┐ ┌──────▼──────┐
      │  Parser   │ │Collector│ │   Analyzer  │
      │ +版本识别  │ │ +RAG检索│ │  ┌─Agent A  │
      └─────┬─────┘ └────┬────┘ │  │(规则引擎) │
            │             │      │  ├─Agent B  │
            │             │      │  │(LLM独立) │
            │             │      │  └─仲裁Agent│
            │             │      └──────┬──────┘
            │             │             │
            │      ┌──────▼──────┐      │
            │      │模型升级链   │      │
            │      │0→1→2级     │      │
            │      └──────┬──────┘      │
            │             │             │
            │      ┌──────▼──────┐      │
            │      │根因聚类     │      │
            │      │跨用例关联   │      │
            │      └──────┬──────┘      │
            │             │             │
            └──────┬──────┘             │
                   ▼                    ▼
            ┌──────────────────────────────┐
            │       Reporter Agent         │
            │  Excel日报 + 累计统计 + 推送  │
            └──────┬──────────┬────────┬───┘
                   │          │        │
               Mercury    Slack    WeChat
```

## 核心设计

### 1. 去中心化对抗诊断

两个 Agent 拿到同一份原始日志，**互不知晓对方结论**，独立诊断：

- **Agent A**（规则引擎）：加权规则匹配
- **Agent B**（LLM）：独立推理分析
- 结论一致 → 高置信度输出
- 结论冲突 → 仲裁 Agent（更强模型裁决）
- 仲裁仍不确定 → 标记"需人工介入"

> 核心洞察：单一 Agent 容易陷入确认偏误——一旦倾向某个分类，就会在日志里找支持自己判断的证据，忽略矛盾信息。去中心化诊断避免结论污染。

### 2. 置信度驱动模型升级链

不是所有日志都丢给大模型，按置信度逐步升级：

```
Tier 0: 规则引擎 (成本≈0)        → high  → 结束
Tier 1: 快速模型 MiniMax (低成本) → medium → 补充判断 → 结束
Tier 2: 推理模型 DeepSeek Reasoner → low  → 深度推理 → 结束
```

> 规则引擎覆盖 80% 高频问题零成本，成本从"全用最强模型"的 N 降到 0.1N。

### 3. 根因聚类 - 跨用例关联分析

7 个失败用例逐条分析会报 7 个问题，但聚类后只有 4 个根因：

| 聚类 | 包含用例 | 根因 |
|------|---------|------|
| 1 | timeout + migration断开 + iscsi拒绝 | 网络异常（同一时段同一主机） |
| 2 | memory_issue + qemu_crash | 内存不足导致 QEMU 崩溃（同一主机） |
| 3 | kernel_panic | 内核崩溃（独立） |
| 4 | libvirt_error | 热插拔不支持（独立） |

聚类维度：时间窗口（±5min） + 主机 + 失败类型关联，满足 2/3 即归为同一根因。

### 4. RAG Wiki - 组件架构知识库

基于 TF-IDF 的轻量 RAG，包含 libvirt、qemu、dpdk、ovs 四个开源项目的代码架构：

- Agent 归因时可检索对应版本的代码架构定位问题
- 支持按组件和失败类型双维度过滤
- 例：memory_hotplug 失败 → 检索到 libvirt 的 domain 模块和 memory 管理调用链

### 5. 版本回归检测

对比前后版本同一用例结果：

| 情况 | 标记 | 优先级 |
|------|------|--------|
| 上版本 PASS → 本版本 FAIL | 回归失败 | 高 |
| 连续 2+ 版本 FAIL | 持续失败 | 中 |
| 新增用例首次失败 | 新增失败 | 普通 |

## Agent 职责

| Agent | 职责 | 关键技术 |
|-------|------|----------|
| **Parser** | 解析 results.json，提取失败用例，识别版本 | JSON 解析、版本提取 |
| **Collector** | 收集本地+远程日志，检索 RAG Wiki | 文件 I/O、TF-IDF 检索 |
| **Analyzer** | 对抗诊断 + 模型升级链 + 已知问题匹配 | 加权规则、LLM、仲裁 |
| **Reporter** | Excel 日报 + 累计统计 + 根因聚类 + 推送 | Excel/JSON/Webhook |

## 目录结构

```
.
├── mock_data/                       # 模拟数据
│   ├── job-results/                 # Avocado 结果
│   │   └── job-20260412-001/
│   │       ├── results.json
│   │       ├── job.log
│   │       └── test-results/*/      # 各用例 debug.log
│   └── history.json                 # 模拟历史运行记录
├── openclaw_agents/                 # Agent 配置
│   ├── 01_parser_agent.yaml
│   ├── 02_collector_agent.yaml
│   ├── 03_analyzer_agent.yaml
│   └── 04_reporter_agent.yaml
├── openclaw_tools/                  # Tool 实现
│   ├── run_pipeline.py              # Pipeline 入口
│   ├── __init__.py
│   └── tools/
│       ├── read_local_log.py        # 日志读取
│       ├── rule_match.py            # 加权规则引擎
│       ├── llm_inference.py         # LLM API 调用
│       ├── reporter.py              # Markdown/JSON 报告
│       ├── excel_reporter.py        # Excel 日报 + 累计统计
│       ├── version_identifier.py    # 版本识别 + 责任人映射
│       ├── known_issues.json        # 已知问题知识库
│       ├── adversarial_diagnosis.py # 对抗诊断 + 仲裁
│       ├── model_chain.py           # 模型升级链
│       ├── root_cause_cluster.py    # 根因聚类
│       ├── regression_detector.py   # 版本回归检测
│       └── rag_wiki/                # RAG 知识库
│           ├── rag_engine.py        # TF-IDF 检索引擎
│           └── wiki_data.json       # 组件架构数据
└── docs/
    └── ROADMAP.md                   # 路线图
```

## 快速开始

### 前置条件

- OpenCLAW Gateway 运行中
- Python 3.12+ (Anaconda)
- DeepSeek API Key（可选）

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

Agent 会调用 avocado-analyzer Skill 执行分析并返回结果。

## 输出

### Excel 日报

| 列名 | 说明 |
|------|------|
| 时间 | 执行时间 |
| 用例名称 | 失败用例名 |
| 任务链接 | 云龙工程链接 |
| 人物名 | 执行人 |
| host机 | 执行主机 |
| 任务UVP版本 | 版本号 |
| 版本失败原因 | 根因描述 |
| 版本分类 | 失败类型 |
| 置信度 | high/medium/low |
| 分析方法 | 规则引擎/LLM/仲裁 |
| 改进措施 | 排查建议 |
| 责任人 | 自动映射 |
| 所属团队 | 内核/计算/存储/软硬协同 |
| 日志链接 | 归档路径 |
| 是否重复失败 | 近期同类失败次数 |
| 关联已知问题 | 匹配到的 BUG 单号 |

### 累计统计

- 成功率趋势（7/30天）
- Flaky Test 识别
- 首次失败版本
- 平均运行时间
- 失败原因分布

## 归因类型

| 类型 | 说明 | 责任团队 |
|------|------|---------|
| `libvirt_error` | libvirt 组件错误 | 计算组 |
| `qemu_crash` | QEMU 进程崩溃 | 计算组 |
| `kernel_panic` | 内核崩溃 | 内核组 |
| `memory_issue` | 内存问题（OOM） | 内核组 |
| `timeout` | 测试超时 | 软硬协同组 |
| `environment_issue` | 环境异常 | 软硬协同组 |
| `case_script_issue` | 用例脚本问题 | 计算组 |
| `infrastructure_issue` | 基础设施问题 | 存储组 |

## 面试讲法

> 1. "我用加权规则引擎覆盖 80% 高频问题，成本为零"
> 2. "不确定的通过去中心化对抗诊断，两个独立 Agent 避免确认偏误"
> 3. "模型升级链让成本从 N 降到 0.1N，大部分用快速模型就够了"
> 4. "根因聚类把 7 个问题压缩到 4 个根因，修 4 个比修 7 个快"
> 5. "RAG Wiki 让 Agent 能查到对应版本的代码架构定位问题"
> 6. "版本回归检测自动标记'上个版本还通过'的高优先级回归"

## 路线图

详见 [docs/ROADMAP.md](docs/ROADMAP.md)
