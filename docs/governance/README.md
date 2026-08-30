# docs/governance — 治理文档入仓（流 E）

- 入仓时间：2026-08-29 · 依据：业主《全权委托章程 v4.4》§4 流 E
- 入仓人：齐活林（主理人，机械复制）+ 许清楚（PM，映射方案/Q5 考古）+ 寇豆码/严过关（审查链）
- 原则：**逐字节复制，哈希复核**；来源 = close-pack（C:\Users\17838\Documents\QoderCN\2026-08-28\chat-1\v09-close-pack\）

## 1. 文件清单（SHA256 = 整文件原始字节）

| 路径 | 内容 | SHA256（整文件） | 来源 |
|---|---|---|---|
| `ZHIHENG_FULL_DELEGATION_CHARTER.md` | 委托章程 v4.4（§0 哈希锁定版） | `1dec34570979915b46214d1b1825d09bfaa4440586ae7d989abd9b2224d6ad0c` | close-pack |
| `rulings/v09-close/BUILDER_RULING_{AD8TCB,EGRESS,FINALBATCH,GATE23,R18,R1_R2,R3_R4,T11B,TIER2}.md` | 裁决书集（9 份） | 各见裁决链哈希：a32e14a4 / de4ad566 / 1987b91e / 6b476ca9 / 7e1a714d / dd9b89e5 / 34c18b74 / 866b2004 / 17f46a12（前 8 位） | close-pack |
| `rulings/v09-close/MAINBRAIN_RULING_E1-E4_BATCH.md` | 主脑裁决书（E1-E4 及累积清单批量裁决，2026-08-30） | `4a98499b4690dc79e0262afe1fd4b71190ba79430b0a8a2846d15758afcc33fc` | close-pack（主脑会话） |
| `rulings/v09-close/MAINBRAIN_RULING_COUNT_CALIBRATION_AND_SIGN_ROADMAP.md` | 主脑裁决书（计数口径统一 + §74 签字路线图，2026-08-30） | `10045466cf08b92245d16599aa002c8ff7c73d00cf9a81f0616728e919c49679` | close-pack（主脑会话） |
| `analysis/R18_SEMANTIC_ANALYSIS.md` | R18 语义分析 | 与来源逐字节一致 | close-pack |
| `../specs/V09_CLOSE_BUILD_SPEC.md` | V0.9 CLOSE 施工规格 | 与来源逐字节一致 | close-pack（G-3：入 specs 与 V14-FROZEN 同级） |
| `VERSION_LADDER_V01_V04.md` | Q5 版本阶梯回填（V0.1–V0.4） | 见文件头 | 流 E 考古产出（草案 → 正式版） |

## 2. 章程双哈希口径（重要，防误报）

- **整文件 SHA256** = `1dec3457…d0c`（上表）
- **§0 校验口径**（剔除"章程身份行："行 + LF 规范化 + 尾部 LF）= `769c7c62a2b0e09b206e0915fc8a49c5f9d77dd868fca8421b261fab6c7440fe`
- 两值**同时有效、口径不同**：身份行里的 769c7c62… 是 §0 口径；校验请用章程 §0 所载 verify 脚本，勿用整文件哈希直接比对（否则误报"篡改"）。

## 3. "八份 vs 九份"裁决书计数口径（已裁决，B7）

章程流 E 写"八份裁决书"，实际入仓 9 份（AD8TCB/EGRESS/FINALBATCH/GATE23/R18/R1_R2/R3_R4/T11B/TIER2）。
**主脑裁决（MAINBRAIN_RULING B7，2026-08-30）：采用诚实口径 = close-pack 原始 8 份 + GATE23（业主确认的全权授权主脑会话所出）= 9 份。**
本目录按实际 9 份全量入仓 + 主脑裁决书 1 份（合计 10 份），计数差异已裁决，不修改任何原文。

## 4. 重测报告（仅登记引用，不重复入仓）

`v09-close-adjudication-c6d1a55b.md` 与 `v09-close-remeasure-c6d1a55b.jsonl` 已随候选 c6d1a55b 入仓于 `docs/evidence/v09-close/`（blob 7f0bd345…/02a79bec…，commit 6dd2295）。governance 不重复入仓，此处仅登记引用。

## 5. G 系列处置状态

- **G-2**：章程流 E "路线图详版" = chat-1 根目录 `ROADMAP-V0.9到V1.0收口路线.md`。**主脑裁决批准入仓（B6），本批已执行**：入 `docs/governance/ROADMAP-V0.9到V1.0收口路线.md`（哈希见文件头登记），PROJECT_STATE 已登记。
- **G-3**：V09_CLOSE_BUILD_SPEC 已按建议入 `docs/specs/`（与 V14-FROZEN 同级），不入 governance（已执行）。
- **G-4**：`_collision_snapshot_2249/`（4 个代码冲突快照）**不入仓**（施工中间产物）。

## 6. 凭据与安全

close-pack 全部 16 文件凭据模式扫描 **0 命中**（PM 流 E 起草期实测）；本目录全部文件逐字节复制自 close-pack，无新增内容；不包含任何凭据样内容。
