# 最终签字包 — 封印 + §74 签字 + master 汇合（一次执行）

签发：主脑 · 2026-08-30
依据：第二团审计 AUDIT_PASS_WITH_REWORK（口径批已执行完毕，f5ea38c）·
MAINBRAIN_RULING_COUNT_CALIBRATION_AND_SIGN_ROADMAP §C
业主授权：业主已在本包下达封印令与签字（见 Part 2 签字栏），
施工团按本包机械执行，不得扩大任何范围。

---

## Part 1｜封印（业主已下令，施工团机械执行）

封印发出点 = 业主本包；执行 = 施工团；要求 = **不碰在产状态**。
新建收口专用 ControlStore，封印对象 = 施工 worktree（候选树），
与在产的 `E:\WB\state` 生产库完全隔离。

在 `C:\Users\17838\Documents\Qoder\2026-08-28\031cb4e3\b1` 下，
用 Python 3.12 canonical 解释器执行：

```python
import sys
sys.path.insert(0, r"C:\Users\17838\Documents\Qoder\2026-08-28\031cb4e3\b1\src")
from pathlib import Path
from aicontrol.store import ControlStore
from aicontrol.security import seal_tcb

close_root = Path(r"E:\WB\state\ai-production-control\v1-close")
close_root.mkdir(parents=True, exist_ok=True)
store = ControlStore(close_root / "control.db", state_root=close_root / "state")
code_root = Path(r"C:\Users\17838\Documents\Qoder\2026-08-28\031cb4e3\b1")
manifest = seal_tcb(store, code_root,
    reason="V1.0 engineering close seal - owner ordered, sign roadmap C-2")
store.close()
print("tcb_generation:", manifest["tcb_generation"])
print("manifest_hash:", manifest["manifest_hash"])
```

执行后：
1. `config/tcb-manifest.json` 会生成在 worktree 内——**入仓提交**；
2. 台账记录：收口库路径（`E:\WB\state\ai-production-control\v1-close\`）、
   tcb_generation、manifest_hash、reason、封印令出处（本包）；
3. 封印后跑 `python scripts/state_doctor.py` 与矩阵 36/36 抽查（封印不应
   影响任何测试；若有影响 = 停止升级）。

## Part 2｜§74 签字文书（业主已签，入仓）

以下内容以 `docs/governance/SIGNING-V1-ENGINEERING-CLOSE.md` 入仓：

```
# 执衡 V1.0 工程收口 — §74 完成条件核验与业主签字

日期：2026-08-30
对象：v0.9-b1/authority-effect-core @ f5ea38c（封印后 = 带封印之树）

## 定义 §74 十二条件核验（证据均在仓）

| # | 条件 | 核验 | 证据 |
|---|---|---|---|
| 1 | 用户 Goal 已实现 | V0.9 CLOSE + V0.10/V0.11 出口达成 | 各流结果块 |
| 2 | 正式 Deliverables 已产生 | 代码收口 + 宪法入仓 + 治理文档 | docs/canon, docs/governance |
| 3 | Acceptance Criteria 满足 | 第二团审计 15/16 PASS，口径批已补 | AUDIT_REPORT_2026-08-30.md |
| 4 | 真实 Artifact 存在 | 仓库树 + 封印 manifest | config/tcb-manifest.json |
| 5 | 机器可验证项通过 | 矩阵 36/36、CLOSE 40、egress 11、特性套件全绿 | 审计 §2-4~2-6（亲跑） |
| 6 | 必要 Evidence 存在 | 8 个真实 GOAL 全链路 + 演练 + 备份 | docs/evidence/* |
| 7 | 独立 Reviewer PASS | 第二团（混元 4，异源）审计通过 | AUDIT_REPORT |
| 8 | Review 绑定当前 Artifact | 审计对象 = 52cbc61→f5ea38c 链，提交号在案 | AUDIT_REPORT §一 |
| 9 | 无已知未解决核心 Blocker | 审计 0 BLOCKED；W-1 已立项有方案（非阻塞） | AUDIT §二 |
| 10 | Effect 状态一致 | 36/36 含 UNKNOWN/对账族全绿 | 矩阵 |
| 11 | 无未对账 OUTCOME_UNKNOWN | 生产运行态无未决项（118 RUN 终态明确） | 审计 §2-8 |
| 12 | 无已撤销仍使用的 Authority | 权限族 36/36 覆盖 + doctor 豁免外零漂移 | 矩阵 + doctor |

## 签字边界（必须随签字保留）

1. 本次签字确认的是**工程收口**（工程判据 + §74 十二条件）；
2. **北极星未达成**：自动调度闭环（无人手动驱动完成一个任务）尚未实现；
   "执衡可自动生产"的宣称**不成立**，列为 V1.0 后第一目标；
3. §3 完整体验（给目标即做完）= §68 自举之前的持续建设项；
4. release_status 晋升为 READY_FOR_USER_ACCEPTANCE（路线图 PHASE 4 口径），
   附上述边界注记；"自动生产"达成前不得再晋升。

## 签字

业主：________________（用户于 2026-08-30 在本包下达签字指令，
施工团代记：业主已签）
见证：主脑（Qoder 会话）· 第二团审计报告（混元 4）
```

（注：业主若日后补手签/书面确认，以补签件为准，本代记件保留为签字时点证据。）

## Part 3｜master 汇合（E3 执行，签字后同批）

施工团按序执行（一批内完成，原子性）：
1. 在 worktree 执行 `git merge master` 方向合并（**把 v0.9-b1 合入 master**：
   检出 master → merge v0.9-b1；master 自 8-23 未动，预期零冲突；
   **若出现任何冲突或意外提交 = 立即停止升级，不得自行解冲突**）；
2. 打标签 `v1.0-engineering-close`；
3. PROJECT_STATE 更新（同批提交）：
   - `current_stage` → `V1_ENGINEERING_CLOSED`；
   - `release_status` → `READY_FOR_USER_ACCEPTANCE` + Part 2 边界注记；
   - `trunk_policy.master.head` → 合并提交；状态改 `CURRENT`；
   - `baselines.current_development_head` → master@合并提交，
     verdict `ENGINEERING_CLOSED`；
4. registry 更新（同批）：`master` head 刷新；
   `v0.9-b1/authority-effect-core` → `ARCHIVE`（head=f5ea38c，
   注"已合入 master，V1.0 工程收口"）；
   **原"豁免项"（registry b1-head 滞后）废止**——本次更新后
   doctor 应完全 DRIFT_FREE（WARN 亦应已消）；
5. 推送：`git push origin master` + `git push origin v1.0-engineering-close`
   + `git push origin v0.9-b1`（registry 状态随分支提交）；
   全部禁 force；
6. 台账记 D021（封印+签字+汇合一批），结果块入 `docs/evidence/`；
7. 最后跑 `python scripts/state_doctor.py`：**目标 = 完全 DRIFT_FREE，
   零豁免**。达到后施工团停止，宣告 V1.0 工程收口执行完毕。

## 边界（对施工团）

本包范围 = 封印 + 签字文书入仓 + master 汇合 + 状态/注册表更新，
**零代码逻辑改动**（唯一新文件 = 封印 manifest 与签字文书）。
任何超出 = 停止升级。完成后施工团任务全部结束，项目进入
"业主验收 + 北极星（自动调度闭环）"新阶段。
