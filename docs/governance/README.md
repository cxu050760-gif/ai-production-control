# docs/governance — 治理文档入仓（流 E）

- 入仓时间：2026-08-29 · 依据：业主《全权委托章程 v4.4》§4 流 E
- 入仓人：齐活林（主理人，机械复制）+ 许清楚（PM，映射方案/Q5 考古）+ 寇豆码/严过关（审查链）
- 原则：**逐字节复制，哈希复核**；来源 = close-pack（C:\Users\17838\Documents\QoderCN\2026-08-28\chat-1\v09-close-pack\）

## 1. 文件清单（SHA256 = 整文件原始字节）

| 路径 | 内容 | SHA256（整文件） | 来源 |
|---|---|---|---|
| `ZHIHENG_FULL_DELEGATION_CHARTER.md` | 委托章程 v4.4（§0 哈希锁定版） | `1dec34570979915b46214d1b1825d09bfaa4440586ae7d989abd9b2224d6ad0c` | close-pack |
| `rulings/v09-close/BUILDER_RULING_{AD8TCB,EGRESS,FINALBATCH,GATE23,R18,R1_R2,R3_R4,T11B,TIER2}.md` | 裁决书集（9 份） | 各见裁决链哈希：a32e14a4 / de4ad566 / 1987b91e / 6b476ca9 / 7e1a714d / dd9b89e5 / 34c18b74 / 866b2004 / 17f46a12（前 8 位） | close-pack |
| `analysis/R18_SEMANTIC_ANALYSIS.md` | R18 语义分析 | 与来源逐字节一致 | close-pack |
| `../specs/V09_CLOSE_BUILD_SPEC.md` | V0.9 CLOSE 施工规格 | 与来源逐字节一致 | close-pack（G-3：入 specs 与 V14-FROZEN 同级） |
| `VERSION_LADDER_V01_V04.md` | Q5 版本阶梯回填（V0.1–V0.4） | 见文件头 | 流 E 考古产出（草案 → 正式版） |

## 2. 章程双哈希口径（重要，防误报）

- **整文件 SHA256** = `1dec3457…d0c`（上表）
- **§0 校验口径**（剔除"章程身份行："行 + LF 规范化 + 尾部 LF）= `769c7c62a2b0e09b206e0915fc8a49c5f9d77dd868fca8421b261fab6c7440fe`
- 两值**同时有效、口径不同**：身份行里的 769c7c62… 是 §0 口径；校验请用章程 §0 所载 verify 脚本，勿用整文件哈希直接比对（否则误报"篡改"）。

## 3. "八份 vs 九份"裁决书计数口径（待业主裁决，不改原文）

章程流 E 写"八份裁决书"，实际入仓 9 份（AD8TCB/EGRESS/FINALBATCH/GATE23/R18/R1_R2/R3_R4/T11B/TIER2）。可能解释（供裁决）：
1. R18 裁决书与 R18 分析曾合并计数；
2. R1_R2 与 R3_R4 曾合并计数；
3. FINALBATCH（最终批）为后增。
本目录按实际 9 份全量入仓，计数差异登记于此，不修改任何原文。

## 4. 重测报告（仅登记引用，不重复入仓）

`v09-close-adjudication-c6d1a55b.md` 与 `v09-close-remeasure-c6d1a55b.jsonl` 已随候选 c6d1a55b 入仓于 `docs/evidence/v09-close/`（blob 7f0bd345…/02a79bec…，commit 6dd2295）。governance 不重复入仓，此处仅登记引用。

## 5. 待业主确认项（G 系列，均不阻塞）

- **G-2**：章程流 E "路线图详版"候选 = chat-1 根目录 `ROADMAP-V0.9到V1.0收口路线.md`（24196B，SHA 597100f0…c08，在 close-pack 之外）。是否即清单所指、是否入仓，待业主确认；**确认前不入仓**。
- **G-3**：V09_CLOSE_BUILD_SPEC 已按建议入 `docs/specs/`（与 V14-FROZEN 同级），不入 governance（已执行）。
- **G-4**：`_collision_snapshot_2249/`（4 个代码冲突快照）**不入仓**（施工中间产物）。

## 6. 凭据与安全

close-pack 全部 16 文件凭据模式扫描 **0 命中**（PM 流 E 起草期实测）；本目录全部文件逐字节复制自 close-pack，无新增内容；不包含任何凭据样内容。
