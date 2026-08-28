# Phase 0 成品包 — 入库清单与操作指南

状态：待提交入 `ai-production-control` 仓库（提交动作由用户或 Builder 执行；
规划者不直接动仓库）。

## 包内容 → 仓库落点

| 包内文件 | 仓库落点 | 说明 |
|---|---|---|
| PROJECT_STATE.json | `/PROJECT_STATE.json` | 机器可验权威状态 |
| PROJECT_STATE.md | `/PROJECT_STATE.md` | 人类可读权威状态（与 JSON 一致） |
| branch_registry.json | `/state/branch_registry.json` | 42 分支角色登记（含策略条款） |
| state_doctor.py | `/scripts/state_doctor.py` | 只读漂移检测器（退出码 0=DRIFT_FREE） |

## 建议提交顺序（每一步独立提交，符合 durable checkpoint 纪律）

1. `chore(phase0): land PROJECT_STATE canonical source (md+json)`
2. `chore(phase0): land branch_registry with 42-branch classification`
3. `feat(phase0): state_doctor read-only drift detector`
4. 在 `v0.9-b2` 还是 `master` 上落？**建议落在 v0.9-b2（当前开发头）**——
   权威状态应跟随真实状态；master 合并本就暂缓。若用户另有裁决，以裁决为准。

## 首跑验收

```
cd <repo> && python scripts/state_doctor.py
```
预期：无 DRIFT；若干 WARN（均为预期）：
- `SPEC_NOT_ANCHORED`（规范未入库，Phase 0 期间合法）
- 41 条 `registered branch not present in this clone`（浅克隆/未拉全分支时出现；
  执行 `git fetch origin "+refs/heads/*:refs/remotes/origin/*"` 后消失）
- `journal staleness`（BUILD_MISSION_JOURNAL 冻结于 08-17，已知事实）
doctor 首跑通过 = Phase 0 底座 DRIFT_FREE 基线（专项提示除外）。

## 规范入库操作（只有用户能启动）

1. 将完整 V0.9 规范（当前在 `C:\Users\17838\.codex\attachments\...\pasted-text.txt`
   及相关件）复制为 `docs/specs/v0.9-authority-effect.md`（可拆分多文件）。
2. 计算并记录每个文件的 SHA256。
3. 在 `PROJECT_STATE.json` 的 `spec_registry` 追加：
   `{"spec_id": "v0.9-authority-effect", "path": "docs/specs/...", "sha256": "...", "governs": ["runtime/fixtures/v09_authority_effect_attack_cases.json"]}`
4. 在攻击矩阵 fixture 顶层增加 `"spec_anchor": "<该 sha256>"`。
5. 提交：`chore(phase0): anchor V0.9 spec into repo (BLK-1 unblocked)`。

## 完成判据（Phase 0 EXIT）

- doctor 无 DRIFT（预期 WARN 除外）
- spec_registry 非空且锚点可复算
- 对照实验：把仓库交给零历史新 AI + NEW_WORKER_START_HERE 恢复协议 v2，
  其状态报告与 PROJECT_STATE 一致、无需用户纠偏（本次接管即对照组）
