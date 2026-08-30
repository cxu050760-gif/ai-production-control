# T0 BLOCKED — 治理文件移植源与 doctor 期望自相矛盾

绑定：SPEC_SHA `3deccf581bdcdf11ba6a2edba4d3f28cee410c69f3182b7f41065031e1db41fa`
R1/R2 裁决书 SHA `dd9b89e52ad8dead7ec00d24f5831fb2ea0fe2e98a65cf52874cca297209b083`
R18 裁决书 SHA `7e1a714df48099d49887a27e45dd1daefae3d292ca74f1272806f28be9b8467a`
V14 规范锚 SHA `6fe3bb7996a1f78a7d6584d08311c3ebc1aa2d9ffc56c27fc61e8d599e154df6`
施工线 BASE `50cf8bd1d1d36b4ebe8518b35a62a68204c4e39f`（remote 同值，开工前已核验）

## 矛盾内容

裁决书 §2 同时要求两件不可同时成立的事：

1. 治理文件**逐字节**取自 `b2@a0ce691`（"不是 f74d48e"）；
2. 移植后 `python scripts/state_doctor.py` 退出码 0，并预期
   "doctor 的 governance-ahead 规则（**CASE 2**）应判 clean——633daec/f74d48e 均为
   governance-only 提交"；且"若 doctor 在此报 DRIFT，停下上报，**不要改 doctor**"。

〔FACT〕`CASE 2 / GOVERNANCE_PATHS / _classify_dev_head` **只存在于 f74d48e 版 doctor**：

```
git cat-file blob a0ce691:scripts/state_doctor.py | grep -i "governance|CASE 2|ancestor"  → 0 命中
git cat-file blob f74d48e:scripts/state_doctor.py | 命中 GOVERNANCE_PATHS(L44)、
    _commit_is_governance_only(L167)、_classify_dev_head(L175)、"clean (CASE 2)"(L181)
git log -1 f74d48e  → "chore(phase0): state_doctor permits governance-only commits ahead of dev head"
```

即：a0ce691 版 doctor 不含裁决书所依赖的那条规则；而该规则正是 f74d48e 这个
governance-only 提交加进去的。用 a0ce691 的 doctor 去判定"a0ce691 之后的
governance-only 提交应判 clean"，在逻辑上不可能成立。

## 实测（在 b1 施工线，未改 doctor、未改 b2 行）

```
$ python scripts/state_doctor.py
WARN: SPEC_NOT_ANCHORED | spec_registry is empty; ...        （合法：T0 未完成，§2 已预告）
WARN: journal staleness | updated_at=2026-08-17 ...          （合法：§2 已预告）
DRIFT: registered head mismatch | expected=v0.9-b2/authority-effect-evidence@da6d1e5e
                              | actual=v0.9-b2/authority-effect-evidence@f74d48e
DRIFT_COUNT=1                                                 exit=1
```

触发点 = R6 `check_registry`，用字符串前缀规则比较 registry 行与在位 ref
（`not got.startswith(want) and not want.startswith(got)`），**不含任何祖先/governance 判定**。

〔对照实测〕同一时刻在 `b2` 检出（f74d48e 版 doctor + f74d48e 版 registry）运行 doctor：
`DRIFT_FREE`，exit=0。证明 f74d48e 的 doctor+registry 是**自洽的一对**，红只来自被指定的旧源。

## 受影响的移植范围（a0ce691 → f74d48e blob 对比）

| 文件 | 状态 |
|---|---|
| `PROJECT_STATE.json` | **DIFFERS** `59cebcab` → `19d4a59a` |
| `PROJECT_STATE.md` | **DIFFERS** `94819429` → `fc1589da` |
| `state/branch_registry.json` | **DIFFERS** `a632440c` → `edd26e9f`（b2 行 `da6d1e5e` → `a0ce691f`） |
| `scripts/state_doctor.py` | **DIFFERS** `845df0e7` → `da6a67e7`（+93 行，含 CASE 2） |
| `scripts/test_state_doctor_classification.py` | **DIFFERS** `b0f30013` → `89f8dbea` |
| `docs/PHASE0_PACK_README.md` | same |
| `runtime/fixtures/v09_authority_effect_attack_cases.json` | same（不受该裁决影响） |
| `runtime/test_v09_attack_matrix_offline.py` | same（不受该裁决影响） |

5/6 治理文件取值取决于本裁决，且 `spec_registry` 的写入目标正是 `PROJECT_STATE.json`
——先定源，否则任何 spec_registry 编辑都可能被随后的重新移植覆盖。

## 为何 Builder 不自行处置

- 改 `state/branch_registry.json` 的 **b2 行**：违反裁决书 §3.3
  （仅授权 `v0.9-b1/authority-effect-core` 条目的 `head` 字段）+ §2"b2 冻结"。
- 改 `scripts/state_doctor.py`：裁决书 §2 明文"不要改 doctor"。
- 换移植源为 f74d48e：与 §2 括注"不是 f74d48e"直接冲突，属裁决条款变更，非施工细节。
- 忽略 doctor DRIFT 继续施工：与 §4.1 自验判据（退出码 0）冲突，且会让后续每批
  "保持 doctor 全程可达 DRIFT_FREE"（§2）从一开始就不可达。

## 现场保留（未提交任何内容）

工作树状态：8 个新增文件（6 治理 + 2 测量件，均 blob 级 IDENTICAL / 夹具仅 +1 行 spec_anchor）、
`docs/specs/V14-FROZEN-EXECUTION-SPEC.txt`（sha256 == 6fe3bb79… 已核）、
`docs/SPEC_ANCHOR_REPORT.md`、`docs/RED_ADJUDICATION_MATRIX.md`、本证据目录。
`git log` HEAD 仍为 50cf8bd1；未 commit、未 push；b2 检出与 b2 ref 均未触碰。
夹具改动可复核：`diff` 仅 `7a8` 一行新增，`cases` 仍 36，JSON 可解析。

## 需要的裁决（R3）

请在以下中择一（建议 1）：

1. **改定移植源 = `b2@f74d48e`**（governance-sealed 自洽对，实测 DRIFT_FREE），
   6 个治理文件全部取自该点；2 个测量件在两点同值，不受影响。
   → 需同时撤销 §2"不是 f74d48e"的表述，理由：CASE 2 规则只存在于 f74d48e。
2. 维持 a0ce691 源，**豁免 §4.1 的 doctor exit-0 判据**（改为"除本条已知 DRIFT 外无新增 DRIFT"），
   并把该已知 DRIFT 记入裁决。
3. 其他（例如先向 b1 追加一个 governance-only 提交以对齐），但 §2 已 b2 冻结、
   且新增治理提交属主脑职权，非 Builder 可自决。
