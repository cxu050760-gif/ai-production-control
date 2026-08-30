# docs/canon — 执衡宪法级文档库

本目录存放执衡（Zhiheng）项目的宪法级定稿文档，由流 Zero Z4 逐字节哈希校验入仓（charter v4.4 §4）。

## ① 文件清单

| 路径 | 中文标题 | SHA256（实测） | 字节大小 | 来源路径 | 性质 |
|---|---|---|---|---|---|
| `ZHIHENG_FINAL_DEFINITION_FINAL_CANONICAL.md` | 执衡·最终定义（FINAL CANONICAL） | `4c05a21fab1543a209cafd70fee48752e996cf3a77df2987f316dde243f4a9a4` | 37366 | `D:\下载\chatgpt原始会话内容\执衡_最终定义_FINAL_CANONICAL.md` | 宪法锁死层 |
| `ZHIHENG_CONSTRUCTION_ROUTE_V2.md` | 执衡·最终版本迭代方案 v2（纯净版） | `995b1c9679a96b51f4e884aaa8fd8d69e959b27bac6db11afe0ab23583b1ddbe` | 18179 | `D:\下载\chatgpt原始会话内容\执衡_最终版本迭代方案_v2_纯净版.md` | 基准层（历史基准） |
| `stream-zero/Z1_hash_verification.md` | Z1 哈希校验记录 | `94badea6d8cf05c52e023a63b1d09b6edd15eb3224ba6ca016468412d8cda51f` | 1426 | `E:\WB\outputs\ai-production-control\stream-zero\Z1_hash_verification.md` | 流 Zero 产出 |
| `stream-zero/Z2_lineage_table.md` | Z2 溯源表 | `72dfc586261d44a9241206ec12d71ef871a799c1b96c07ba25fb412072a3acc1` | 11325 | `E:\WB\outputs\ai-production-control\stream-zero\Z2_lineage_table.md` | 流 Zero 产出 |
| `stream-zero/Z3_revision_registry.md` | Z3 修订登记册 | `c4dc89c03c8e1b386d17283c96c6a9c51fb40bd4c643bd082c77a3a03d2a7be9` | 18728 | `E:\WB\outputs\ai-production-control\stream-zero\Z3_revision_registry.md` | 流 Zero 产出 |
| `stream-zero/Z4_version_comparison_and_change_requests.md` | Z4 版本对照与变更请求 | `949ba7be70039cc5c28e7525877f3bf6b3ab7462fe004740a935a6c2034dc43d` | 13404 | `E:\WB\outputs\ai-production-control\stream-zero\Z4_version_comparison_and_change_requests.md` | 流 Zero 产出 |

所有文件均为逐字节复制（binary copy），入仓后 SHA256 与来源文件实测一致；两份定稿的哈希已对照任务下发的期望值核验通过。

## ② 文档层级说明

- **《执衡·最终定义（FINAL CANONICAL）》为宪法零修改锁死层**：本文件内容不得作任何改动；任何施工、测试、规范若与之冲突，以本文件为准。
- **《执衡·最终版本迭代方案 v2（纯净版）》为历史基准**：它是路线演进的历史快照（各版本号语义对照见 `stream-zero/Z4_version_comparison_and_change_requests.md`），不代表现行执行版本。
- **现行版本基准**：以仓库根的 `PROJECT_STATE` / `ROADMAP` 为准（权威层级见章程 §2）。canon 目录中的历史文档与现行基准不一致时，按层级裁决，而非直接改写。

## ③ 规范锚登记指引

canon 目录下的两份定稿（`ZHIHENG_FINAL_DEFINITION_FINAL_CANONICAL.md`、`ZHIHENG_CONSTRUCTION_ROUTE_V2.md`）可作为规范锚登记进 `PROJECT_STATE.json` 的 `spec_registry` 数组，条目结构参照现有 `V14-FROZEN` 条目的同构精简版（`spec_id` / `title` / `path` / `sha256` / `size_bytes` / `source_provenance` / `status` / `committed_by` / `committed_at`），并同步更新 `PROJECT_STATE.md` 的「规范锚（spec_registry，T0 入库）」表格。

登记动作须经 `scripts/state_doctor.py` 校验（登记前保存基线输出，登记后重跑对比；doctor 失败或出现新增漂移则回退登记、以本 README 为登记依据的存档点）。

## ④ 备考

定稿 B（`ZHIHENG_CONSTRUCTION_ROUTE_V2.md`，纯净版）含 **68 处空代码围栏对**（`` ``` `` 与 `` ``` `` 相邻成对）。此为纯净化转换过程留下的伪影，非内容缺失。本次入仓坚持逐字节复制、不改原文；读者阅读时请参照上下文理解空围栏处的原意。
