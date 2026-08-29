# VERIFY-SUMMARY（REWORK 修订版）— 候选代码树只读全量验证报告

- 生成：2026-08-29 22:37 +08:00 · 真实 GOAL `RUN-20260829-223254-b173`（R 评审 REWORK 后按六点要求修订重交）
- 被测对象：ai-production-control 候选代码树 `C:\Users\17838\Documents\Qoder\2026-08-28\031cb4e3\b1`（分支 v0.9-b1/authority-effect-core）
- **被测 HEAD（长 SHA）：`249e1370dbad54f51ab233cc32514a6bb6e70b1d`**（短 SHA `249e137` 即其前 7 位，与 Goal Contract 指定一致，无差异）
- 性质：只读验证。**被测代码树未修改的客观证据**：验证执行后 `git status --short` 输出为空（工作树干净，0 变更 0 untracked）；验证过程仅运行只读命令与生成任务工作区文件（E:\WB\outputs\ai-production-control\stream-c\real-goal-001\，位于被测树之外）。
- Python 3.12.10 canonical（C:/Users/17838/AppData/Local/Programs/Python/Python312/python.exe），无 pytest。

## 1. 判据达成总表（逐项核对用）

| 套件/项 | 总数 | 通过 | 失败 | failures=0 | 原始错误摘要 |
|---|---|---|---|---|---|
| runtime 离线套件（冻结原件 test_v09_attack_matrix_offline.py 除外） | 26 | 26 | 0 | ✅ | N/A (no failures) |
| tests/ 套件（含 CLOSE） | 19 | 19 | 0 | ✅ | N/A (no failures) |
| 攻击矩阵（适配运行器 test_v09_attack_matrix_on_b1_core.py） | 36 cases | matched=36 | red=0 | ✅ | N/A (no failures) |
| R34 / R34-FAITHFUL 忠实探针 | — | FAIL_CLOSED MATCH ×2 | 0 | ✅ | N/A (no failures) |
| state_doctor 体检 | — | DRIFT_COUNT=1（已裁决豁免项） | 0 新增漂移 | ✅（豁免项非失败） | N/A |

## 2. 原始输出证据（可逐项核对）

- **verify_raw.log（62 行，同目录）**：逐文件记录 26 个 runtime 文件与 19 个 tests 文件的 `exit_code | 文件名 | 结果行`（26 行 `0 | runtime/...`、19 行 `0 | test_...`，无任何非零退出）；矩阵输出（case_count=36, matched=36, red=0；V09-R34 与 V09-R34-FAITHFUL exp/obs 均 FAIL_CLOSED MATCH）；doctor 输出（DRIFT 行 + WARN 行 + DRIFT_COUNT=1）。
- harness 特例说明：`test_harness_verify_offline.py` 以进程内剔除宿主超长环境变量 `ACC_PRODUCT_CONFIG_V3`（515167 字符 > Windows 32767 上限，属环境噪声非代码问题）口径运行，结果 11/11 OK（Ran 11 tests OK）。
- 冻结原件 `runtime/test_v09_attack_matrix_offline.py`：按 §4.2 单独口径**未运行入判据**、未改动（blob 保持）。

## 3. doctor 真实结论（不写成字面 zero drift）

`python scripts/state_doctor.py` 实测输出：
- `DRIFT: registered head mismatch | expected=v0.9-b1/authority-effect-core@c6d1a55b | actual=v0.9-b1/authority-effect-core@249e1370` → **DRIFT_COUNT=1**
- `WARN: journal staleness | updated_at=2026-08-17 but latest commit=2026-08-29 (>7 days)`
- 该 DRIFT 为**章程 §7.8 唯一已裁决豁免项**（registry b1-head 滞后，引导期结构性滞后，已裁决且明令不得修复）；WARN 为已知合法预告。
- 结论表述：**DRIFT_FREE_WITH_ACCEPTED_EXCEPTIONS**（除已登记且已裁决的豁免项外零漂移），非字面意义的"zero drift"。

## 4. 关键命令记录

- 套件逐文件：`python runtime/test_*.py`；`cd tests && python test_*.py`（harness 特例见 §2）
- 矩阵：`python runtime/test_v09_attack_matrix_on_b1_core.py`
- 体检：`python scripts/state_doctor.py`
- 未修改证据：`git status --short`（空输出）
- 全部原始输出见同目录 verify_raw.log

## 5. 验收标准对照（Goal Contract 要求）

| GOAL 验收项 | 达成 |
|---|---|
| VERIFY-SUMMARY.md 存在 | ✅ 本文件 |
| 六项数据齐全且与实测一致 | ✅（总数/通过/失败/矩阵/doctor/时间戳与命令） |
| 未修改任何被测文件 | ✅ git status 空（§2 证据） |
