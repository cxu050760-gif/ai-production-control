# T0 Evidence — 规范锚定与治理/测量件入库

施工线: `v0.9-b1/authority-effect-core`
BASE_SHA: `50cf8bd1d1d36b4ebe8518b35a62a68204c4e39f`
SPEC_SHA: `3deccf581bdcdf11ba6a2edba4d3f28cee410c69f3182b7f41065031e1db41fa`
V14_SPEC_SHA: `6fe3bb7996a1f78a7d6584d08311c3ebc1aa2d9ffc56c27fc61e8d599e154df6`
裁决链: R1/R2 `dd9b89e5…b083` · R18 `7e1a714d…467a` · R3/R4 `34c18b74…765a1`
（`git diff --name-only` 见"改动清单"；本文件绑定 BASE，T0 提交 SHA 记于下一批证据）

## 1. 逐字节一致性证明（blob 级，非工作树级）

本机 `core.autocrlf=true` 且无 `.gitattributes`，工作树 sha256 会受 CRLF 转换影响，
故字节一致性一律以 **git blob ID** 为准（这是比文本哈希更强的证明：同一 blob 即同一字节序列）。

移植源 = `b2@f74d48e`（R3 裁决改定；原 a0ce691 指示已撤销，见 DECISION_LEDGER D005）。

| 文件 | blob ID | 与 f74d48e |
|---|---|---|
| `PROJECT_STATE.json` | `19d4a59a3e034d4cb981e7b22fc84abb161d7e00` | IDENTICAL（此后仅 §3.1 授权的 spec_registry 填充） |
| `PROJECT_STATE.md` | `fc1589dabd79d3711135fcd9fe709bf62b99b716` | IDENTICAL（同上，孪生同步） |
| `state/branch_registry.json` | `edd26e9fe262a19b4930e6a2358144806ad7094f` | IDENTICAL |
| `scripts/state_doctor.py` | `da6a67e770c992cc4b557d7c84aefdce60f33383` | IDENTICAL |
| `scripts/test_state_doctor_classification.py` | `89f8dbea239abf05890560fc9c7864f086a9a6de` | IDENTICAL |
| `docs/PHASE0_PACK_README.md` | `8d2ba134bd1118af00f1dfc9d45ae60ccc4af465` | IDENTICAL |
| `runtime/test_v09_attack_matrix_offline.py` | `cb0cc3067b1c5436b104b09a48a48775f4ed5cb8` | IDENTICAL（冻结原件，零改动） |
| `runtime/fixtures/v09_authority_effect_attack_cases.json` | 源 `ee7ac3c8b6101a2de3693a6ea852d2e5ac0774ab` | 源两点同值；仅 +1 行 `spec_anchor`（见 §2） |

冻结原件 sha256（内容层，交叉验证）：
`076aef918bc4a2125f82c0fc844b3a00685ec8c48572bd0c63206e3563c9c2fb`（夹具源）、
`d54ca1be901142f659998c50aa9e10a22043f0f597ae0b54f6e8e002586ffed0`（运行器）。
`a0ce691` 与 `f74d48e` 两点的这 2 个测量件 blob 相同（R3/R4 §1.4 判定"无需重做"，实测吻合）。

## 2. 夹具唯一授权改动

```
$ diff <a0ce691/f74d48e 原件> runtime/fixtures/v09_authority_effect_attack_cases.json
7a8
>   "spec_anchor": "sha256:6fe3bb7996a1f78a7d6584d08311c3ebc1aa2d9ffc56c27fc61e8d599e154df6",
```

- 仅新增 1 行（8854 → 8946 字节），其余字节不动；JSON 可解析；`cases` 仍为 36；
- 改动依据 = 规格 T0（"spec_registry 已指定的唯一夹具改动，仅元数据"）+
  R18 裁决书 §3 复申（"冻结夹具原件…仍然逐字节不动"，spec_anchor 除外）。

## 3. V14 规范入库

`docs/specs/V14-FROZEN-EXECUTION-SPEC.txt` sha256 =
`6fe3bb7996a1f78a7d6584d08311c3ebc1aa2d9ffc56c27fc61e8d599e154df6`，66,931 字节，
与 `.codex/attachments/c33ac6a6-…/pasted-text.txt` 及 `spec-anchor-pack/` 副本三者同值。

## 4. spec_registry 登记

`PROJECT_STATE.json.spec_registry`：`[]` → 1 条（内容 = `spec-anchor-pack/spec_registry.json`
的 `specs[0]` 全量字段），唯一语义改动 = `"status": "STAGED_NOT_COMMITTED"` → `"COMMITTED"`，
另加 `committed_by` / `committed_at` 两个溯源字段。
未触碰 `baselines` / `verdict` / `release_status` / `current_stage` / `current_blockers`
（R1/R2 裁决书 §3 禁止项）。孪生 `PROJECT_STATE.md` 增补"规范锚（spec_registry，T0 入库）"表。

## 5. doctor 出口判据

```
$ python scripts/state_doctor.py
WARN: journal staleness | updated_at=2026-08-17 but latest commit=2026-08-28 (>7 days)
DRIFT_FREE
exit=0
```

- 出口判据"doctor 对 spec_registry 不再报 SPEC_NOT_ANCHORED"：已满足（该 WARN 在本批前一轮出现，现消失）。
- 唯一残留 WARN = journal staleness，R1/R2 裁决书 §2 明列为预期合法 WARN。
- `scripts/test_state_doctor_classification.py`（随移植入库）= 6/6 OK。

## 6. 适配运行器首测（T0 完成点，产品代码零改动）

`runtime/test_v09_attack_matrix_on_b1_core.py`：AD-1（外部权威签发）、AD-2（intent 显式
effect_type/data_classification）、AD-3（resource-a 绑定）、AD-4（同 state root 新
Controller 实例模拟重启）、AD-5（R18 裁决期望覆盖 + 身份断言）。

- 36 例：`matched=25 / red=11`；无 `HARNESS_ERROR`。
- **R18 以 AD-5 判据 MATCH**：`observed=ALLOW_DISTINCT_EFFECT`，身份证明
  `slots=['same-slot-diff'] logical_effect_ids=2 intent_hashes=2 action_rows=2 independent_reservations=True`
  —— 满足 R18 裁决书 §3"防止碰巧 ALLOW 收口"的要求（同槽、两独立预留、两不同身份）。
- **R21 经 AD-4 复现规格 T6 记录的基线行为** `DEDUPLICATED_WITHOUT_RECONCILE`
  （改前为 `HARNESS_ERROR`：重启实例被 auth 身份绑定预检挡住，测不到去重分支）。
- R34 双路径：矩阵原走法 `MATCH`（但理由是 "authorization effect type mismatch"，属表面匹配）；
  忠实探针 `V09-R34-FAITHFUL` = `observed=ALLOW` **MISMATCH** → 证明未知 effect_type
  在签发侧与执行侧均未 fail-closed。按任务简报 §14，以忠实探针为真实缺口，**不得收绿**。
- 11 例 RED 与规格 A/B 类清单一致：R06、R08、R09、R20、R21、R26、R32、R36（A 类 8 例）
  + R22、R23、R24（B 类 `UNSUPPORTED`）。D 类 R01/R04/R13 全 MATCH。

## 7. T0 范围合规

`src/`、`config/`、`runtime/runtime.py`、`runtime/effect_safety_lite.py` **零改动**
（规格 T0 FORBIDDEN：任何 `src/`、`runtime/` 其他文件、任何业务逻辑）。
本批全部改动为新增文件或唯一授权的夹具单行元数据。
