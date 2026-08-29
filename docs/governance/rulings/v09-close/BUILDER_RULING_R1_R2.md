# BUILDER_RULING_R1_R2 — 对 Builder 阻塞点 R1/R2 的正式裁决

裁决人：总设计师 / 主脑（Qoder 会话）
执行对象：Builder（Qwen3.8 Flash 会话）
日期：2026-08-28
绑定规格：`V09_CLOSE_BUILD_SPEC.md` SPEC_SHA256 =
`3deccf581bdcdf11ba6a2edba4d3f28cee410c69f3182b7f41065031e1db41fa`
（已双向哈希核验，与 Builder 所持副本一致，无 SPEC_CHANGED）
V14 规范锚：`6fe3bb7996a1f78a7d6584d08311c3ebc1aa2d9ffc56c27fc61e8d599e154df6`（一致）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §1 状态确认（对 Builder）

你在两个治理歧义点上按规格 §5 HARD STOP 停下请示、不动现场——**这是正确行为，
不是故障**。HEAD 与 worktree 未动已确认。本裁决解决 R1 与 R2；收到后立即按
§4 恢复施工。规格其余部分（含 §5 全部 HARD STOP 条款，特别是 R18 与 D 类）
继续完全有效。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §2 R1 裁决：施工线 = v0.9-b1（两线分叉是设计事实，不是事故）

**裁决：施工线 = `v0.9-b1/authority-effect-core`，自 HEAD `50cf8bd1` 追加提交。
不创建任何新分支。`v0.9-b2` 冻结。**

理由与语义（写入裁决记录）：
1. b2 与 b1 自分叉是**有意设计**：b2 = 测量/证据线（在"未含 b1 核心"的树上
   发布 36 例矩阵与 RED 证据 + Phase 0 治理入库）；b1 = 核心升级线
   （registry 角色 ACTIVE，"work may continue"）。V0.9 缺口全部位于核心内，
   施工必须发生在核心所在的线。
2. **b2 自本裁决起冻结**：不再向 b2 提交任何内容；不合并；不删除；不改名。
   它的角色（CANDIDATE_RED / 正式 RED 证据发布物）保持原样，直到 CLOSE 完成
   后由用户裁决其角色转换——那是收口后的状态更新，不是 Builder 的职责。
3. 两线收敛（b1→master 或任何合并）**不在 V0.9 CLOSE 范围内**，
   维持既有裁决（合并暂缓、不得重开），Builder 不得触碰。

**T0 修正（对规格 T0 的权威增补）**：治理权威必须跟随施工线。
除规格 T0 已列文件外，授权从 **b2@a0ce691**（不是 f74d48e；a0ce691 是
b2 上最后一个开发提交，取该点的文件内容）**逐字节**移植以下治理文件到施工线：

```
PROJECT_STATE.json
PROJECT_STATE.md
state/branch_registry.json
scripts/state_doctor.py
scripts/test_state_doctor_classification.py
docs/PHASE0_PACK_README.md
```

约束：
- 逐字节拷贝，唯一允许的语义改动 = R2 授权的 `spec_registry` 登记（孪生文件同步）。
- **不移植** b2 的 CI workflow 与 RED 证据生成器（它们是 b2 测量线的专属件，
  与施工无关，留在冻结线）。
- 移植后在施工线执行 `git fetch origin "+refs/heads/*:refs/remotes/origin/*"`
  使全部 42 分支在位（doctor R2 锚点与 R5 全分支登记检查依赖它）。

**doctor 预期（施工期间，逐项声明，防止误报阻塞）**：
- `current_development_head`（b2@a0ce691）vs 物理 b2（f74d48e）：
  doctor 的 governance-ahead 规则（CASE 2）应判 clean——633daec/f74d48e
  均为 governance-only 提交。若 doctor 在此报 DRIFT，停下上报，不要改 doctor。
- `registry: v0.9-b1 head=50cf8bd1` vs 施工推进后的实际 HEAD：
  按 §3 的机械同步规则处理（授权），保持 doctor 全程可达 DRIFT_FREE。
- 预期 WARN：journal staleness（已知）；T0 完成前 SPEC_NOT_ANCHORED（合法）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §3 R2 裁决：Builder 的治理写入权限（白名单制，未列即禁止）

**授权（仅限以下五项）**：
1. **T0 入库**：规格 T0 + 本裁决 §2 的文件集；对 `PROJECT_STATE.json` /
   `PROJECT_STATE.md` 的修改**仅限于**填入 `spec_registry`（内容 =
   `spec-anchor-pack/spec_registry.json` 条目，status 置为已入库语义）
   及孪生一致性所必需的同句同步。
2. **追加式记录**：`docs/DECISION_LEDGER.md`（每条含 actor；actor=Builder，
   裁决来源注明"用户 2026-08-28 裁决 + 主脑规格"）、
   `docs/BUILD_MISSION_JOURNAL.md`（每任务收口 checkpoint，含日期与提交 SHA）。
3. **registry 机械同步**：`state/branch_registry.json` 中**仅**
   `v0.9-b1/authority-effect-core` 条目的 `head` 字段，随每批提交同步为
   实际 HEAD（机械事实记录，与提交同批落盘，提交信息注明依据本裁决）。
   其余任何条目、任何字段不得改动。
4. **证据创建**：`docs/evidence/v09-close/` 目录及其内文件（规格 §4 定义）。
5. **TCB 重封的机械执行**：规格 §4 全量回归绿后，允许运行**既有**封印机制
   （在仓库现有代码中寻找，如 `src/aicontrol/security.py` 的 seal/verify 路径
   或既有脚本；**不得新建封印工具**），并把封印前后状态如实记入证据。
   封印"是否成立"的判定不属于 Builder——属于独立审查者与用户。

**禁止（重申 + 明确）**：
- `PROJECT_STATE` 的 baselines / verdict / release_status / current_stage /
  current_blockers 等语义字段；
- `branch_registry` 任何角色变更、任何非 v0.9-b1-head 字段；
- 创建 / 删除 / 改名 / 合并任何分支；向 master 或除 v0.9-b1 外的任何引用提交；
- 任何 R18 施工（BLOCKED_BY_SPEC，等用户裁决）；
- 任何超出规格 ALLOWED_FILES 的文件触碰；
- 任何 `--force` 推送、任何 `--no-verify`。

**推送策略**：每任务批在本地提交并通过当批回归后，允许
`git push origin v0.9-b1/authority-effect-core`（仅此一引用）。
推送前 `git status` 复核暂存内容；任何疑似凭据立即停止上报。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §4 恢复施工指令（依序）

1. 执行 T0（含 §2 增补的治理文件移植 + fetch 全分支），自验：
   冻结原件哈希 == b2@a0ce691 对应文件；`python scripts/state_doctor.py`
   退出码 0（WARN 允许，DRIFT 必须为零或立即上报）。
2. 按规格 §2 依赖序执行 TASK-1 → TASK-5，每批：施工 → 单测 → 当批矩阵重测
   （适配运行器）→ 记录入证据 → 提交（+ 可推送）。
3. 全部任务完成后执行规格 §4 全局验证与 §6 十项收口判据自查，产出
   §5 格式的结果块，**然后停止**，等待独立审查。

## §5 Builder 完成时必须返回（沿用项目 REQUIRED_RESULT 纪律）

```
COMMITS:               <每任务批的 SHA 与 CASE_ID 对照>
PUSHED_REF:            v0.9-b1/authority-effect-core@<最终SHA>
MATRIX_RESULT:         36 例逐案（适配运行器）+ R34 忠实探针
FULL_REGRESSION:       全量离线套件结果
DOCTOR_RESULT:         完整输出（最终状态）
EVIDENCE_PATHS:        docs/evidence/v09-close/ 文件清单与哈希
TCB_SEAL_RECORD:       封印前后状态（仅机械记录，不作有效性宣告）
HARD_STOP_EVENTS:      0 或逐条列表
```

## §6 本裁决的边界

本裁决只解决 R1 与 R2。不扩大规格任何语义边界；不改变 R18 的 BLOCKED_BY_SPEC；
不授权任何"顺手优化"。若施工中发现本裁决与规格或规范原文冲突：
以规范原文 > 规格 > 本裁决的优先级停下上报。
