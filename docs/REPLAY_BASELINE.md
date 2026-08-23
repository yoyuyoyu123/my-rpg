# 固定多回合回放基线

## 目的

固定多回合回放不是“让模型再玩一遍然后凭感觉看看”。它要回答三个问题：

1. 同一输入是否能得到可解释、可恢复的状态变化；
2. 修改架构后，事实、人物知识、承诺和玩家选择是否比之前稳定；
3. UX、调用次数和延迟是否在改进叙事时发生回退。

它只比较**可验证的契约和指标**，不要求模型每次写出完全相同的句子。

## 一、两种回放模式

### A. 确定性协议回放（必须通过）

目的：测试程序、数据库、Agent 编排和前端协议，而不是测试模型文笔。

- 使用本地 fake provider 或录制的模型 cassette；
- 固定随机种子、世界、预设、配置和初始状态；
- 模型输出固定，但仍经过真实解析、校验、存档和检索流程；
- 每次运行都应得到相同的状态、事件、承诺、调用顺序和错误码。

这一层可以作为 CI 的硬门。

### B. 真实模型质量回放（用于比较）

目的：观察真实模型在固定场景上的质量变化。

- 使用指定 provider/model 和固定设置；
- 每个场景运行 3-5 次，不要求正文逐字一致；
- 只记录硬错误、结构指标、延迟和人工盲评；
- 结果作为版本间比较，不把一次模型随机输出当成绝对失败。

这一层不能替代确定性协议回放，也不能因为平均文风变好就掩盖状态错误。

## 二、每个场景必须冻结的内容

每个 fixture 至少包含：

```json
{
  "schema_version": 1,
  "id": "commitment_recall_20_turns",
  "description": "20回合承诺召回",
  "world_id": "fantasy",
  "preset_id": "",
  "seed": 1729,
  "settings": {
    "pace": "medium",
    "stream": true,
    "story_agents": true,
    "state_sync": true,
    "option_repair": true
  },
  "setup": {
    "game_state": {},
    "facts": [],
    "events": [],
    "commitments": [],
    "npc_beliefs": [],
    "character_states": []
  },
  "turns": [
    {"input": "向王掌柜答应明天来取货", "expect": {"commitment_created": true}},
    {"input": "先去市场买些日用品", "expect": {}},
    {"input": "回到茶馆询问昨天的约定", "expect": {"commitment_recalled": true}}
  ],
  "assertions": {
    "hard": [],
    "metrics": []
  }
}
```

还要记录运行环境：`git_commit`、应用版本、数据库 schema 版本、provider、model、thinking 设置、prompt hash 和依赖版本。

## 三、第一批固定场景

现有 `research/regression/phase0_scenarios.json` 的 8 类场景是起点；其中穿越开局必须额外加入，因为它已经暴露过“规划 Agent 没有推进前提”的真实缺陷。

| 场景 | 建议长度 | 固定动作骨架 | 必须检查 |
|---|---:|---|---|
| 1. 承诺召回 | 20 回合 | 建立承诺 → 插入 10-15 回合无关行动 → 回到承诺 | NPC/玩家记得内容、期限和状态；不重复创建 |
| 2. NPC 知识边界 | 8-10 回合 | A 私聊秘密 → B 不在场 → 与 B 对话 → A 再确认 | B 不得把 A 的秘密当成已知事实；每条知识有来源 |
| 3. 拒绝持续 | 8 回合 | 提出任务 → 玩家明确拒绝 → 处理其他行动 → 回到原人物 | 原入口不得换名、换皮或原样重发；世界仍有其他行动 |
| 4. 玩家分叉 | 两条各 8 回合 | 同一存档复制为 A/B → 不同选择 | 后续状态、关系、事件或可用行动至少一项有因果差异 |
| 5. 低压日常 | 5-8 回合 | 问路、购物、吃饭、工作、闲聊 | 无玩家调查时不自动出现阴谋、追杀、灭世、神秘警告 |
| 6. 行动相关性 | 5 回合 | 购买、移动、检查、询问、休息 | 描写服务当前行动/空间/关系/信息；无关段落受控 |
| 7. 人物动态 | 10-12 回合 | 轻微冲突 → 道歉/修复 → 普通相处 | 稳定身份不漂移；短期情绪可变化并按规则衰减 |
| 8. 穿越/转生链 | 5-6 回合 | 原世界起点 → 触发 → 阈限 → 转移 → 首次落地 | 规划器收到并维护迁移状态；阶段不丢、不跳、不被生活支线吞掉 |
| 9. 状态与交易 | 8 回合 | 获得、使用、出售、缺货、余额不足 | 金钱、物品、位置、时间由程序结算；非法 patch 被拒绝 |
| 10. 故障恢复与 UX | 3 个子测试 | 首 token、断流、重试、读档、Enter、后端离线 | 正文不消失、失败可恢复、不静默损坏存档 |

## 四、每回合记录什么

每回合产生一条机器可读记录，至少包括：

```text
scenario_id / replay_id / turn_id
input_text / input_classification
state_version_before / state_version_after
retrieved_ids / excluded_ids / retrieval_reasons
scene_contract_id / planner_called / planner_reason
agent_runs[]：agent、model、开始/结束、状态、token、错误
prompt_hash / prompt_chars
first_token_ms / total_ms / output_chars / option_count
candidate_patch / validation_result / applied_patch
facts_written / events_written / commitments_changed
status：completed | degraded | failed
```

推理内容可以保存在本地诊断记录中，但不得进入正文、正史或提交到仓库。API Key、请求头和完整隐私存档必须脱敏。

## 五、硬性判定与软性指标

### 硬性失败（出现一次就记录为失败）

- 回合号重复、倒退或丢失；
- 同一个请求重试导致重复扣款/发物/推进时间；
- 已拒绝入口在没有新因果时重新出现；
- NPC 使用没有来源的知识；
- 背包、金钱、HP、位置违反程序规则；
- Planner/Writer 越权替玩家做决定；
- SSE 中途正文消失或完成后没有保存；
- Enter、选项、存档、读档或后端离线路径失效；
- API Key 出现在前端、存档或导出记录。

### 统计指标（用来比较版本）

- `commitment_errors`：承诺遗忘/误判次数；
- `unauthorized_knowledge_uses`：未授权知识使用次数；
- `reintroduced_gate_count`：拒绝入口重发次数；
- `branch_state_difference`：分支在指定回合后的状态差异；
- `unprepared_pressure_escalations`：无铺垫升压次数；
- `irrelevant_sentence_ratio`：人工盲评的无关句比例；
- `identity_errors_and_dynamic_score`：身份错误和动态变化评分；
- `hard_regression_count`：原版 UX 硬回归次数；
- `planner_calls_per_turn`、`first_token_ms`、`total_ms`、`input_tokens`、`output_tokens`。

## 六、执行顺序

### 第一步：先做协议回放器

输入 fixture，创建临时 SQLite 数据库，调用真实后端服务但替换 LLM provider，逐回合执行并输出 `replay.jsonl` 和 `summary.json`。

### 第二步：录制当前版本基线

在任何新架构迁移前运行全部场景，保存：

- 当前硬错误；
- 当前指标；
- 当前调用次数/延迟；
- 当前已知失败样例。

基线的意义是“知道起点”，不是证明当前实现合格。

### 第三步：每次只改一层

推荐顺序：

1. 回合/存档契约；
2. 事实与 NPC 知识；
3. 承诺生命周期；
4. SceneContract；
5. 规则结算；
6. 前端模块化；
7. 叙事质量调优。

每完成一层，先跑确定性回放，再跑真实模型质量回放。

### 第四步：生成版本差异报告

报告必须同时展示：

```text
新版本硬错误 - 旧版本硬错误
新版本质量指标 - 旧版本质量指标
新版本延迟/成本 - 旧版本延迟/成本
新增回归样例
未测量项
```

不能只展示“文风更好”或“测试数量增加”。

## 七、第一阶段完成标准

Phase 0 不要求剧情变完美，只要求建立可信测量系统：

1. 10 个场景 fixture 可执行；
2. 确定性回放重复三次结果一致；
3. 每回合有完整结构化日志；
4. 能自动发现状态、承诺、知识、选项和 UX 硬错误；
5. 真实模型回放能生成延迟、成本和人工评价表；
6. 任何后续代码改动都能说明“改善了哪一个场景、没有破坏哪些场景”。

在这些条件满足前，不继续增加新的 Agent、提示词禁令、世界观标签或复杂规则。

