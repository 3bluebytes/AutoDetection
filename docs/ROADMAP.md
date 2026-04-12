# AutoDectections Agent - 改进路线图

## 当前状态

- [x] Mock 数据（7 个失败用例 + 日志）
- [x] 规则引擎归因（加权版，7/7 正确归因）
- [x] Pipeline 脚本（Parser → Collector → Analyzer → Reporter）
- [x] OpenCLAW Skill 配置（avocado-analyzer）
- [x] 微信推送（通过 OpenCLAW weixin 插件）
- [x] LLM 分析接口（DeepSeek API，低置信度时调用）

## 创新点规划（面试亮点）

### 创新点 1：多 Agent 对抗验证 + 仲裁

同一个日志分别交给两个 Agent 独立分析：
- Agent A：规则引擎归因
- Agent B：LLM 独立归因

结论一致 → 高置信度，直接输出
结论冲突 → 触发 Agent C（仲裁 Agent，用更强模型做最终判断）

面试话术：*"我设计了对抗验证机制——两个 Agent 独立分析同一份日志，结论一致才高置信度输出，冲突时触发仲裁。类似 adversarial validation 的思想。"*

### 创新点 2：置信度驱动的模型升级链

不是所有日志都丢给大模型，而是按置信度逐步升级：

```
规则引擎命中 (成本≈0)  → 置信度 high  → 结束
规则引擎模糊           → 置信度 medium → 升级到 MiniMax(快速模型) → 结束
规则+快速模型都模糊     → 置信度 low   → 升级到 DeepSeek Reasoner(推理模型) → 结束
```

面试话术：*"我设计了一个模型升级链，规则引擎覆盖 80% 高频问题零成本，只有不确定的才逐步升级模型。150 个用例只有十几个需要调模型，大部分用快速模型就够了，推理模型只处理最难的。成本和质量做了最优 trade-off。"*

### 创新点 3：根因聚类 - 跨用例关联分析

不只是逐条归因，而是做跨用例关联分析：

7 个失败用例逐条分析后，聚类 Agent 发现：
- #3(timeout) + #7(migration断开) + #iscsi(Connection refused) → 共同特征：09:05-09:20 网络异常时段 → 归为同一根因：09:05 网络抖动

最终输出 3 个根因（而非 7 个独立问题），对运维排障价值完全不同。

面试话术：*"逐条分析会报 7 个问题，但聚类后只有 3 个根因。一次网络抖动会导致迁移超时、连接断开、存储拒绝等多个用例同时失败，聚类 Agent 能发现这种时序相关性。"*

## 实现顺序

2 → 1 → 3（从简单到复杂）

- 创新点 2（置信度升级链）：改动最小，在现有 pipeline 基础上加模型路由逻辑
- 创新点 1（对抗验证+仲裁）：需要新增仲裁 Agent，修改 Analyzer 流程
- 创新点 3（根因聚类）：需要新增聚类 Agent，实现时序相关性分析

## 架构演进

### 当前架构（单线 Pipeline）

```
Parser → Collector → Analyzer → Reporter
```

### 目标架构（多 Agent 协作 + 对抗验证 + 聚类）

```
Parser → Collector → ┌─ Agent A (规则引擎) ─┐
                     └─ Agent B (LLM)      ─┤ → 仲裁Agent → 聚类Agent → Reporter
```
