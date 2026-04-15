# Roadmap

## 当前状态

- [x] 基于现有 `openclaw_tools/` 完成 4 段式 wrapper：parser / collector / analyzer / reporter
- [x] 提供可合并的 `openclaw_runtime/openclaw.json` 多 agent 模板
- [x] 为 5 个 workspace 补齐 `AGENTS.md`
- [x] 入口 agent 与专责 agent 的职责边界拆清
- [x] 运行产物统一落到 `openclaw_runtime/runs/<run_id>/`
- [x] 规则引擎归因跑通 mock 数据
- [x] Reporter 能生成 Markdown / JSON / Mercury payload
- [x] LLM 依赖缺失时可自动退化到规则模式

## 下一步

- [ ] 把 `at-entry` 的编排从说明文档进一步收敛为稳定的 OpenClaw 任务模板
- [ ] 为 `at-analyzer` 接回对抗诊断、模型升级链、根因聚类
- [ ] 把 RAG Wiki 独立成 MCP 服务，而不是停留在本地库调用
- [ ] 加上 `requirements.txt` 或 `pyproject.toml`
- [ ] 补 CI，用 mock 数据跑 parser → collector → analyzer → reporter 回归
- [ ] 把 Excel 依赖与 webhook 推送变成可选 profile

## 不再保留的旧结构

下面这类内容已经从仓库主路径移除，不再作为主交付形式：

- 旧的 `openclaw_agents/*.yaml` 伪配置
- 只做迁移设想的架构文档
- 本地验证输出目录中的一次性结果文件

## 目标状态

目标是把这个仓库稳定成一套“可本地验证、可被 OpenClaw 入口 agent 调度、可逐步替换为 MCP / skill / workflow”的中间态工程，而不是继续维护一套文档化的伪多 agent 架构。
