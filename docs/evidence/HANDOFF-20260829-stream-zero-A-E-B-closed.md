# HANDOFF — 移交检查点（2026-08-29）

- 生成：齐活林（主理人）· 2026-08-29 · 依据：章程 v4.4 §9 移交检查点协议（停机点 f：上下文将尽）
- 团队：software-zhiheng（software-zhiheng-b139 续）· 成员：许清楚（PM）/ 寇豆码（工程师，429 中断后主理人接管）/ 严过关（QA）
- 恢复锚：本文件 + PROJECT_STATE.md/.json + 各流结果块（docs/evidence/{stream-zero,stream-a,stream-e,stream-b}/RESULT_BLOCK*.md）+ 远端 v0.9-b1/authority-effect-core

## 1. 已完成（提交链 = 进度真源，全部已推送 origin/v0.9-b1/authority-effect-core，无 force）

| 提交 | 内容 | 审查 |
|---|---|---|
| `42b0596` | 流 Zero：宪法文档入仓 docs/canon/（定稿 A/B 逐字节 + Z1-Z4 谱系/修订史/版本对照 + spec_registry 登记 2 条） | QA PASS 7/7 |
| `665a73c` | 流 Zero 结果块 | — |
| `c464190` | 流 A：FINALBATCH 三门构造 8 处 + 新增接线 11 例 + AD-8 登记册 + D016；矩阵 36/36 red=0、全量绿 | QA R1 PASS（1 缺陷） |
| `d401a21` | 流 A 收口：AD-8 行号修正 + evidence_registry 登记 + 结果块 | QA R2 PASS 6/6 |
| `22e4b4f` | 流 E：治理入仓（9 裁决书 + R18 + 章程双哈希 + BUILD_SPEC + Q5 版本阶梯） | QA PASS 7/7 |
| `54b9980` | 流 E 结果块 | — |
| `56627ec` | 流 B-1：冻结快照 + 盘点（38/18/9）+ 大文件索引 26 条 + 敏感清单 9 项 | QA R1 PASS 7/7 |
| `f0d9c88` | 流 B-2：融合评估 13 候选（Reuse5/Adapt4/Compose2/Build2；P0×8） | QA R2 PASS |
| `9cfbc72` | 流 B 结果块 | — |
| （本提交） | 本移交检查点 | — |

状态事实：HEAD=9cfbc72；工作树干净；doctor DRIFT_COUNT=1（= §7.8 豁免项 registry b1-head 滞后，**不得修复**）；release_status=PRODUCT_NOT_READY；TCB=UNVERIFIED_AFTER_CONTROLLER_CHANGE（封印属发布负责人）；冻结件 test_v09_attack_matrix_offline.py blob cb0cc306… 未动。

## 2. 下一动作：流 C｜V0.10 单类真实 GOAL（收窄：本地文件/代码任务类）

入口：读 WORKER_CONTRACT.md、runtime/（runtime.py / send_guard_lite.py / goal_contract_lite.py / harness_verify.py）、docs/specs/V14-FROZEN（GOAL 相关条款）、docs/specs/V09_CLOSE_BUILD_SPEC.md。
工单要点：
1. 设计 1 个真实本地任务 GOAL（如：在任务 workspace 生成/修改本地文件并产出结果），走 Goal Contract（build_contract → persist_contract，注意 data_egress_policy 参数与投影）→ runtime 执行（start/send）→ 全链路证据（state.json、transport log、效果记录、验收）入库 docs/evidence/stream-c/。
2. 三门纪律照旧：真实执行时 egress/TCB/授权按真实世界语义（非场景构造——真实 GOAL 不得用场景声明蒙混，TCB 未封印状态按 fail-closed 处理，只做本地文件类零外部效果任务以避开外部效果限制）。
3. 红线：不 merge master、不删改名分支、禁 force、不碰 runtime.py 结构性重构、期望断言不削弱、PROJECT_STATE 语义字段仅阶段出口更新。
4. 出口：真实 GOAL 全链路证据入库 + 增量收束（分支策略待业主裁决，v0.9-b1 沿用或按裁决）。

## 3. 未决项（请业主批量裁决，均不阻塞流 C 开工）

- **CR-1~CR-4**（docs/canon/stream-zero/Z4）：V0.10 语义收窄确认（Multi-Worker 降扩展候选）/ 权威层级对照生效 / 旧2 源会话补导出 / Phase0↔Stage0 对应。
- **G-2**（docs/governance/README.md）：路线图详版候选 = chat-1 根 ROADMAP-V0.9到V1.0收口路线.md（SHA 597100f0…c08）是否即清单所指并入仓。
- **八 vs 九份裁决书**计数口径（3 种解释待选，不改原文）。
- 流 B 存疑 D-01（control.db 用途）/D-02（执衡 .git 与远端关系）/D-04..D-09 共 8 项（docs/asset-registry/ASSET_INVENTORY_FINAL.md）。
- 融合 F-08 deepseek-harness 是否纳入（接入范围 + 凭据策略）。
- P0 备份排期（04_测试证据 / runtime-v1\runs / snapshots / browser-profile / 会话注册.json / proxy-key.dpapi / control.db）。
- 敏感文件 S-02/S-03/S-06 轮换策略（browser-auth-profile-v1/v2、proxy-key.dpapi）。

## 4. 环境与纪律备忘

- 代理 127.0.0.1:7897（git push/fetch 必需）；Python 3.12.10 canonical（C:/Users/17838/AppData/Local/Programs/Python/Python312/python.exe）；无 pytest。
- 测试环境噪声：宿主变量 ACC_PRODUCT_CONFIG_V3（515KB）致 harness_verify 类 mock 环境恢复 ValueError → 进程内 `os.environ.pop('ACC_PRODUCT_CONFIG_V3',None)` 后跑（或 env -u）。
- tests 调用规范：cd tests && python test_v09_close_*.py；体检：python scripts/state_doctor.py。
- 冻结参照克隆（只读）：C:\Users\17838\Documents\QoderCN\2026-08-28\chat-1\ai-production-control。
- 宪法/章程哈希：定义 4c05a21f…、路线v2 995b1c96…、章程 §0 口径 769c7c62…（整文件 1dec3457…）；任何不符 = SAFE_HALT。
- 资源锁：同一时刻仅一会话持 worktree 写权限。
