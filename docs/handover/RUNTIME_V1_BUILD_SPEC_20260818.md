# Weak-AI Runtime V1 — Build Spec (canonical, 2026-08-18)

本文件是 Runtime V1 建设任务的权威规格摘要（来自 2026-08-18 用户提示词），登记为 canonical 基线文档。
完整原始提示词以用户会话为准；此处只固化不会过期的结构性要求。

## 目标

把已验收稳定的 WorkBuddy↔ChatGPT Bridge（冻结，见同目录 Bridge_final_handover_20260818.md）
收口为弱 AI（会员三/HY3 级）可直接使用的 Production Runtime V1。

用户体验：每次只提供 GOAL + 本次 R_URL；弱 Worker 自动执行→审查→返工→恢复→交付；
用户不做人肉消息中转，不负责普通技术决策。

## 三件建设内容

- A. 唯一 Weak-AI Runtime Facade：弱 Worker 只见有限 CLI 状态（SUCCESS/REVIEW_PASS/REVIEW_REWORK/PAUSED/MISSING_R_URL/RETRYABLE_ERROR/HARD_BLOCKED 类），不知道 bsk/daemon/端口/session/marker/click/WAIT/CAPTURE 等内部。
- B. Durable Task State：状态不依赖聊天记忆；PAUSE/STOP/RESUME/CHANGE_SCOPE/R_URL_CHANGE/USER_OVERRIDE 先 durable commit 再执行；压缩/重启/换 Worker 后从 state 恢复。
- C. Fast Path：健康缓存、session 复用、evidence delta、重复动作拒绝、有限预算（retries/recoveries/requiries），杜绝每小动作一审。

## P0 规则

1. R_URL 永远无默认值：新 RUN 未显式传入 → MISSING_R_URL 停止；不继承、不猜、不自建会话。
   当前 RUN 可 durable 保存自己的 R_URL 供恢复，但绝不自动成为下一 RUN 的 R_URL。
2. 窗口/tab/session 不随轮次增长：同 RUN+同 R_URL 复用健康会话；能 reattach 就 reattach；
   只管理 Runtime 自建资源；禁止批量 kill Chrome。

## 最小验收（7 项）

T1 R_URL 无默认/不继承；T2 唯一入口（Worker 不碰 Bridge 原语）；T3 真实 R↔W 闭环
（执行→审→REWORK→自动返工→PASS，用户不搬消息）；T4 PAUSE durable 且重启后保持；
T5 新 Worker 只读 Bootstrap+State 可恢复；T6 多轮后窗口/tab/session 数不增长；
T7 有限异常恢复：注入一次故障→内部有限恢复→超预算 HARD_BLOCKED。

## 禁止扩展

Universal Browser / V13 / V14 / 多 Brain / 多 Worker 大系统 / Memory 重构 / Effect WAL /
Authority Journal 一律不做；Facade/API 保留清晰 adapter 扩展口即可。

## 本次 BUILD RUN 显式配置（仅本 RUN 有效，不是默认值）

- R（总审查）：https://chatgpt.com/c/6a840eee-f430-83ee-847d-8520cb3bc928
- E（实验）：https://chatgpt.com/c/6a841ab7-9c64-83e8-ab3f-30769bf98779

（记录于本 RUN 的 RUN state；下一个 RUN 必须重新显式提供，不得引用此处。）
