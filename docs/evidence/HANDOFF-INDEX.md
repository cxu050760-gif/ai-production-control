# HANDOFF-INDEX — 会话进度总表（v1.1-blackbox 开发线）

> 维护者：主会话（齐活林/交付总监）。各会话检查点文件统一命名 `HANDOFF-CP-<日期>-<序号>-<会话名>.md`，本 INDEX 汇总每会话完成/进行中/下一步。新会话开工先读本 INDEX 决定接哪块。

## 总览（2026-08-30 23:5x 快照）

| 会话 | 文件域 | 阶段 | 状态 | 下一步 |
|---|---|---|---|---|
| 主会话（本） | 治理文件 + 编排 | R1-R6/D1-D6 编排 | 进行中 | 汇总各刀产出、审核门禁、统一提交推送 |
| software-engineer | scripts/guard/ | R1 守护层 | 进行中 | guard_all.cmd + schtasks + 自愈实测 |
| software-engineer-r2 | config/capability-registry.json + docs/ops/registry-* | R2 注册表 | 进行中 | registry JSON + 消费脚本 + 校验 |
| software-engineer-r3 | runtime/ 新命令 + docs/ops/blackbox-card* | R3 黑箱 | 进行中 | 四动词补齐 + 一页卡 + 冒烟 |

## 分支与推送纪律
- 开发线：v1.1-blackbox（master 冻结为 V1.0 收束基准）
- 推送：fetch → pull --rebase → push 串行（主会话协调），禁 force，全程代理 http://127.0.0.1:7897
- 治理文件（PROJECT_STATE.*/DECISION_LEDGER/本 INDEX/主报告修订记录）只由主会话写

## 审核登记（§17）
| 阶段 | 需要会签数 | 审核者 | 结论落点 |
|---|---|---|---|
| R1 | ≥2 | 待派 | docs/evidence/reviews/ |
| R3 | ≥2 | 待派 | docs/evidence/reviews/ |
| D1 | ≥2 | 待派 | docs/evidence/reviews/ |
| D6 | ≥2 | 待派 | docs/evidence/reviews/ |
| 其余 | ≥1 | 待派 | docs/evidence/reviews/ |
