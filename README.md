# AutoDetection

面向虚拟化 AT 失败日志的多 Agent 归因工程。

当前仓库已经收敛为一套可落地的 OpenClaw 运行模板：

- 1 个入口 agent：`at-entry`
- 4 个专责 agent：`at-parser`、`at-collector`、`at-analyzer`、`at-reporter`
- 现有分析能力继续复用 `openclaw_tools/` 里的规则引擎、LLM、报告生成逻辑
- agent 之间通过共享 `run_dir` 工件目录解耦，而不是靠一个本地大脚本串起来

## 当前结构

```text
.
├── mock_data/                       # Mock job-results 与历史数据
├── openclaw_runtime/
│   ├── bin/                         # 4 个薄 wrapper，承接现有 pipeline 逻辑
│   ├── openclaw.json                # 可合并到 ~/.openclaw/openclaw.json 的模板
│   ├── runs/                        # 运行时工件目录（默认不入库）
│   └── workspaces/
│       ├── at-entry/
│       ├── at-parser/
│       ├── at-collector/
│       ├── at-analyzer/
│       └── at-reporter/
├── openclaw_tools/                  # 复用的业务能力实现
│   ├── run_pipeline.py              # 历史 pipeline 入口，保留作参考
│   └── tools/
└── docs/
    └── ROADMAP.md
```

## Agent 职责

| Agent | 职责 | 主要输入 | 主要输出 |
|------|------|---------|---------|
| `at-entry` | 接 IM / gateway，请求编排与结果回传 | `job_root` | 最终摘要、报告路径 |
| `at-parser` | 解析 `results.json`，提取失败用例与版本 | `job_root` | `job_info.json`、`failed_tests.json` |
| `at-collector` | 收集失败用例 `debug.log` | `job_root`、`failed_tests.json` | `collected_logs.json` |
| `at-analyzer` | 规则归因、已知问题匹配、可选 LLM 补充 | `collected_logs.json`、`job_info.json` | `analysis.json` |
| `at-reporter` | 生成 Markdown / JSON / Mercury payload / Excel | `analysis.json`、`job_info.json` | `report_manifest.json`、报告文件 |

## 本地验证

### 1. Parser

```bash
python3 openclaw_runtime/bin/parser_agent.py \
  --job-root mock_data/job-results/job-20260412-001 \
  --run-dir openclaw_runtime/runs/demo
```

### 2. Collector

```bash
python3 openclaw_runtime/bin/collector_agent.py \
  --job-root mock_data/job-results/job-20260412-001 \
  --failed-tests openclaw_runtime/runs/demo/failed_tests.json \
  --run-dir openclaw_runtime/runs/demo
```

### 3. Analyzer

```bash
python3 openclaw_runtime/bin/analyzer_agent.py \
  --collected-logs openclaw_runtime/runs/demo/collected_logs.json \
  --job-info openclaw_runtime/runs/demo/job_info.json \
  --run-dir openclaw_runtime/runs/demo
```

启用 LLM：

```bash
python3 openclaw_runtime/bin/analyzer_agent.py \
  --collected-logs openclaw_runtime/runs/demo/collected_logs.json \
  --job-info openclaw_runtime/runs/demo/job_info.json \
  --run-dir openclaw_runtime/runs/demo \
  --use-llm
```

### 4. Reporter

```bash
python3 openclaw_runtime/bin/reporter_agent.py \
  --job-info openclaw_runtime/runs/demo/job_info.json \
  --analysis openclaw_runtime/runs/demo/analysis.json \
  --run-dir openclaw_runtime/runs/demo
```

## 接入 OpenClaw

1. 把 `openclaw_runtime/openclaw.json` 里的 `agents` / `bindings` 合并到本机 `~/.openclaw/openclaw.json`。
2. 确保 5 个 workspace 路径与本机仓库路径一致。
3. 在各 workspace 下保留 `AGENTS.md`，入口 agent 使用 `at-entry/AGENTS.md` 做编排。
4. 在 gateway 已登录 IM 账号的前提下，从微信或其它已绑定渠道向入口 agent 发起请求。

## 产物约定

每次运行都会在 `openclaw_runtime/runs/<run_id>/` 下产生工件：

- `job_info.json`
- `failed_tests.json`
- `collected_logs.json`
- `analysis.json`
- `analysis_summary.json`
- `report_manifest.json`
- `reports/report.md`
- `reports/report.json`
- `reports/mercury_payload.json`
- `reports/daily_report.xlsx`（环境中存在 `openpyxl` 时）
- `reports/case_stats.xlsx`（存在历史数据且 `openpyxl` 可用时）

## 依赖说明

- 基础运行：Python 3.12+
- 可选 LLM：`DEEPSEEK_API_KEY`、`MINIMAX_API_KEY`
- Excel 输出：`openpyxl`

当前实现已对 `requests` 做懒加载；即便未安装相关依赖，规则引擎路径仍可运行。

## 后续

路线图见 [docs/ROADMAP.md](docs/ROADMAP.md)。
