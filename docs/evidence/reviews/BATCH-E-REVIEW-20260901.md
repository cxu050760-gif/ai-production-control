# 批次 E 盲审记录 — §74 十二条件门禁 final_gate(20260901)

## 范围

- `runtime/final_gate.py`(新增,Canonical §74 十二条件门禁)
- `runtime/test_final_gate_offline.py`(新增,25 例)
- `docs/evidence/V1.0-ACHIEVEMENT-MATRIX-20260901.md`(§74 行更新,仍"部分")

## 第一轮盲审(R-E,独立子代理,仅给文件清单+canonical 原文)

结论:**REWORK**。

- [P1] C8 绑定弱检查:commit 仅非空即过,不与 Artifact 交叉绑定;
- [P1] 六项自证布尔(C1/C3/C5/C10/C11/C12)整体取信 manifest 作者,
  伪造 manifest 即可 12 条全绿;
- [P2] C4 状态自报 R_REVIEW_PASS 不与 reviewer.verdict 交叉验证;
- [P2] C8_REVIEW_EVIDENCE_NOT_FOUND 无独立测试路径;
- [P2] reviewer.evidence 只查存在不读内容,空文件也过。

(R-E 同时确认:存在性条件真查磁盘、§45 集成真实、fail-closed 到位、
权力边界钉死、矩阵行诚实。)

## 处置(全部采纳,代码升级为交叉核验制)

1. P1 C8:commit 须为 7-40 位 hex SHA(`C8_REVIEW_COMMIT_MALFORMED`);
   evidence 文件须存在且非空(`..._EMPTY`)、含 PASS(`..._NO_PASS`)、
   并逐个点名 artifact(`C8_REVIEW_NOT_BOUND:<name>`);
2. P1 自证布尔:六项声明全部强制引用盘上 evidence 源
   (C1_GOAL_EVIDENCE_NOT_FOUND / C3_RUNNER_NOT_FOUND /
   C5_CHECK_NO_COMMAND+C5_CHECK_EVIDENCE_NOT_FOUND /
   C10_EFFECT_EVIDENCE_NOT_FOUND / C11_EFFECT_EVIDENCE_NOT_FOUND /
   C12_AUTHORITY_EVIDENCE_NOT_FOUND)——伪造必须伪造整条磁盘证据链;
3. P2 状态-裁定脱钩:artifact 自报 review 级以上状态而 reviewer.verdict
   ≠ PASS → `C4_STATE_REVIEW_MISMATCH`(低于 review 层级不参与);
4. P2 补 C8_REVIEW_EVIDENCE_NOT_FOUND 独立用例;
5. P2 内容校验并入第 1 条。

## 复审(R-E resume,逐文件读回+实跑+对抗实测)

方式:三文件逐行读回+实跑 25 例(全过)+伪造 manifest 对抗性 CLI 实测。

- P1 C8 → 已修复(假 SHA→MALFORMED、未点名 artifact→NOT_BOUND 实测均拒);
- P1 六自证布尔 → 已修复(伪造全假路径 manifest 实测 11 个问题码全量拒绝);
- P2 状态-裁定脱钩 → 已修复(F3 正反两用例在);
- P2 C8 独立测试路径 → 已修复;
- P2 证据只查存在 → 已修复(空/无 PASS/未点名三支实读)。

终裁:**PASS**。遗留一项测试覆盖不对称:P2 `C11_EFFECT_EVIDENCE_NOT_FOUND`
分支无独立单测。→ 已补 `test_f2_c11_evidence_missing_independent`,
final_gate 测试 26 例全绿,遗留清零。

## 回归直录

| 轮 | RUNTIME | TESTS | STATE | 说明 |
|----|---------|-------|-------|------|
| batchE_r5 | 737 OK (79s) | 219 OK | CLEAN | R-E 处置后;启动早于 C11 补例落盘 |
| batchE_r6 | 738 OK (77s) | 219 OK | CLEAN | 含 C11 补例的最终口径,与提交内容一致 |

738 = 712(批次 D 基线)+ 26(final_gate,含 R-E 遗留补例);tests 219 不变。

## 权力边界(§74 固有)

门禁 verdict 只出 `FINAL_DONE_ELIGIBLE`,永不出 FINAL DONE;
FINAL DONE 是 Human Gate 裁定。§74 行保持"部分":
机制已门禁化,业主 FINAL DONE 未发生(外部依赖)。
