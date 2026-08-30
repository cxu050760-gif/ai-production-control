# W-1 最小接线方案 — 生产配置下满足自身闸门（只出方案，不施工）

- 依据：主脑裁决书 `MAINBRAIN_RULING_E1-E4_BATCH.md` C-2（GATE23 揭示）→ 立项 W-1
- 状态：**方案文档**（设计稿）。**施工前须经主脑审阅通过**；未接线前，一切"生产可用"表述禁止。
- 执行：recovery-controller · 2026-08-30 17:20（北京）

## 1. 问题定性（GATE23 取证）

真实发送路径存在三门闸（V0.9 CLOSE 构造的 egress 三门）：
- **门 ①**：egress policy（数据出口策略）——已有产品侧生产者（effect_safety_lite + 策略文件）
- **门 ②**：TCB 声明（tcb_verified）——**产品侧零生产者**（当前仅在测试场景构造中赋值）
- **门 ③**：授权签发（grant_authorization）——**产品侧零生产者**（函数已实现于 `runtime/effect_safety_lite.py:90`，但生产 runtime.py 无调用入口）

当前 36/36 矩阵全绿**依赖测试场景构造**（fixture 里手工造三门），**不代表生产配置下产品能自行满足三门**。这是"生产可用"表述被禁止的根因。

## 2. 设计目标

> 生产配置（`config/production.json` + 真实 Controller 会话）下，产品自身完整满足门①门②门③，
> 至少 1 次真实发送全程无测试场景构造。改动最小、不结构性重构冻结 runtime.py。

## 3. 方案骨架（Reuse Gate 先行——逐项复用已有资产，零重造）

### 3.1 门 ③ 授权签发：复用 `grant_authorization`，补产品侧签发入口

- **已有资产**：`runtime/effect_safety_lite.py:90 grant_authorization(state, issuer_role, holder_role, ...)`（V0.9 三门构造测试已验证其逻辑：issuer 必须是 Authority 角色、scope 完整性校验、generation/revocation 单调性）
- **缺口**：产品侧无「谁在何时签发」的入口——授权只能由测试代码调
- **最小接线**：新增独立 CLI 动词 `runtime.py grant-auth --run-id <ID> --issuer O --holder B --scope <...>`（非侵入：不改冻结核心逻辑，仅新增 argparse 分支；签发动作写入 RUN state 的 effect_authorizations，由 `_new_run` 后、执行前调用）
- **生产者职责**：Controller（O 角色会话）在生产配置下显式签发；Worker 无权自签（Authority 隔离维持）
- **Reuse Decision**：R=Reuse（复用已实现的 grant_authorization 函数 + 既有效力存储结构）

### 3.2 门 ② TCB 声明：定义「TCB 清单 + 启动期验证」最小路径

- **已有资产**：`config/production.json`（TCB 声明目标：src/aicontrol、ai-control.cmd、scripts、config/production.json、package-lock.json）；`security.seal_tcb` 先例（流 D §5 记录）；AGENTS.md TCB 范围
- **缺口**：运行时无「启动时验证 TCB 清单与运行代码一致」的产品侧动作（tcb_verified 仅测试赋值）
- **最小接线**：新增 `runtime.py tcb-verify`（或并入 health）：按 production.json 声明的 TCB 文件清单计算 SHA256 与清单对比，输出 `tcb_verified: true/false`；`cmd_work` 在创建 RUN 时记录该值到 state（`tcb_verified` 字段），三门检查读此字段
- **说明**：完整 TCB 封印（seal_tcb + manifest）仍属发布负责人职责（E1 后置），本方案只解决「生产侧能产出 tcb_verified 布尔值」——先让门②有生产者，不替代封印

### 3.3 门 ① 维持现状（已有生产者）

- egress policy 已由 effect_safety_lite + 策略文件满足，零改动。

### 3.4 接线时序（生产配置下的一次真实发送）

```
Controller 会话（O）
  ├─ 1. tcb-verify  → tcb_verified=true 写入 RUN state（门②生产者）
  ├─ 2. grant-auth  → 签发 effect_authorizations（门③生产者）
  └─ 3. work/report → 真实发送，三门检查读取 state 中的 tcb_verified + authorization（门①既有）
```

## 4. 验收标准（施工完成后）

1. 生产配置（非测试场景构造）下跑通 ≥1 次真实发送，三门全过；
2. 矩阵 36/36 保持全绿（无回归）；
3. 冻结件零改动（runtime.py 仅新增 argparse 分支，不结构性重构；effect_safety_lite 零改动）；
4. 无 TCB 声明时（未执行 tcb-verify）→ 门② FAIL（fail-closed 维持）。

## 5. 施工边界（本批不做）

- ❌ 不实现代码（本方案仅设计稿，经主脑审后再施工）
- ❌ 不执行 TCB 封印（E1 后置：第二团审计通过 + 业主 §74 签字后由发布负责人执行）
- ❌ 不触碰 production.json 内容（S-07 只登记）
- ✅ 施工量预估：2 个 CLI 动词（tcb-verify / grant-auth）+ 1 个 RUN state 字段接线 + 2 组测试，全部复用既有模块

## 6. 待主脑审阅点

1. grant-auth 动词的 CLI 形态是否符合 Controller 交互惯例（或应走 config 预签发而非运行时动词）？
2. tcb_verified 写入 RUN state 是否为最小侵入（vs 独立 manifest 文件）？
3. 是否需要在 tcb-verify 中纳入 config/production.json 自身哈希（防配置漂移）？
