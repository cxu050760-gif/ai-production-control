# SELF-AUDIT — HARDENING 批次 A 施工+外审投递全程独立重审（2026-08-31）

- 重审人：独立重审员（未参与施工与投递）
- 审计对象：分支 `hardening/p0-gates-20260831`，提交范围 `9a31e2c..fbbc7c2`（14 commits，+2065/−148 行，28 文件）
- 审计材料：主仓库只读检查 + E:\WB 下 relay 账本（autopilot-actions.ndjson / relay.ndjson / quarantine / verdict 文件）/ RUN-20260831-164921-6214 全档 / HE-BATCHA-HARDENING-20260831 证据包 / E:\WB\temp\review-batch-a-20260831 副本仓库
- 工作树状态：主仓库 `git status` 干净、无 stash；工作树与 HEAD 一致
- 只读声明：本审计未运行任何改状态命令；唯一写入为本文件

---

## 一、结论总表（逐提交 keep / revert / redo）

| 提交 | 内容 | 裁决 | 一句理由 |
|---|---|---|---|
| 8e4f3e7 | GATE-1#1 report 回路接三闸 | **keep** | 堵住唯一生产外发路径绕过效果闸的真实缺陷，经内审盲审实测 R1-R4 通过 |
| d9ff266 | GATE-1#2/#3/#4 禁伪造 commit/FROZEN 拦截/三闸 fail-closed | **keep** | 内审逐条核对 verdict 空间后确认拦截完备，C1-C4/F1-F4 实测 |
| 5ec6d13 | GATE-1#5 effect-reconcile 对账出口 | **keep** | 消除 OUTCOME_UNKNOWN 永久自锁（原 effect-gate 是死入口），X1-X5 実 |
| b9de73f | GATE-2#6 controller_lease 原子化+revoke | **keep** | 内审 4 线程并发实测复现旧代码重复 generation；fsync/revoke/畸形 expires 全部 fail-closed 正确 |
| 41e80e3 | GATE-2#7/#8/#9+GATE-3+GATE-4+测试还账+治理 | **keep** | 内审确认全部"旧代码必红"真断言（138 例实跑），wiring 隔离彻底 |
| 059afe8 | 内审 P2×3 修复（rename-steal/per-RUN RunLock/RunLock 非对象 JSON） | **keep** | 响应内审必改清单、随附内审报告入仓、修后全量回归绿；候选 9655c96 已被 R 侧过目 |
| 0ed6cff | 送审包文档 | **keep** | 纯文档，送审材料本身无问题 |
| 878da28 | lease 门同代续约分支 + tmp-review-goal 入仓 | **keep(代码)/回退(工件)** | 续约分支语义与 V1.0 renew 既有"同代可续"一致且 fencing 未弱化，**但该提交引入 check-OK 路径 KeyError 且未跑测试即提交**；tmp 工件应移出 |
| f5836de | cost 阈值 0.5→2.0（owner 批准留痕） | **keep** | 业主裁决方案二，_threshold_history 留痕合规 |
| 294ce2e | renew 统一包装 + admission KeyError 根治 + 测试同步 | **keep** | 修复真实 KeyError（自造缺陷的必要纠正）+ API 包装一致性；属于"补丁"但方向正确、有测试 |
| 9655c96 | submit 加 --repo-path（GATE-5） | **keep** | 修真实硬编码缺陷（E:\WB\temp 非 git 仓库致 FAILED_INTERNAL），在候选 9655c96 审查范围内 |
| 341d01e | submit 加 --review-packet | **keep(附条件)** | 修真实缺陷（round18 遗留常量致 R 会话串台），但**在内审与证据包范围之外、无测试** |
| e97f5ea | 外审查包入副本仓库 + drive-review-log | **keep(附条件)** | 文档留痕合理；但 drive-review-log.txt 里连 argparse 报错碎片一起入仓，属投递碎片 |
| fbbc7c2 | --evidence-path 参数 + tmp-review-message + 外审闭环声明 | **keep(代码,附条件)/否定(结论)** | 参数修真实缺陷（遗留 V0.6 证据常量）但混入 docs 提交、零测试、零审查；**其宣称的"外审闭环 PASS"不成立，见第四节** |

### 四刀专项裁决

1. **relay_autopilot --repo-path/--review-packet/--evidence-path + build_event**：解决真实缺陷（三个遗留常量各自实测造成 FAILED_INTERNAL/串台/REWORK），改动为可选参数、默认回落旧行为，无新风险面；relay 模式禁伪造 commit 的 fail-closed 语义未被绕过。裁决：**keep**；但三参数零测试（全仓 grep 无一测试引用），341d01e/fbbc7c2 两段在所有审查范围之外 → 列入批次 B 补测+补审（redo 测试，不必 revert 代码）。
2. **controller_lease renew 统一包装与 rename-steal**：rename-steal 是内审 P2-1/P2-3 的正确修复（唯一成功者获得接管权，Windows/POSIX 双路径封死），并发测试 A 系列实测；统一 {ok, reason, lease} 包装修复调用方按 ok 分支必然 KeyError 的 API 不一致，唯一生产调用方 relay_autopilot:179 与测试均已同步。裁决：**keep**。
3. **admission lease 续约分支**：check-OK 路径先落 checks["lease"] 修 KeyError 正确（test_lease_gate_present 隐式回归钉住）；"自己持有的过期租约同代续约"与 V1.0 renew 既有语义一致、文件锁内校验 generation 被接管仍拒、fencing 未弱化，且生产实测两次真实续约成功（07:59/08:38 账本留痕）。裁决：**keep**；但 renew 分支本身零测试覆盖（wiring 假 check 恒 OK，从不触发 renew）→ 补测（redo 测试）。
4. **guard_all.cmd lock 段**：`del /q lock.json + 非递归 rmdir + mkdir` 取代 `rmdir /s /q`，与 Python 侧"lock.json 本身即原子认领"语义对齐；比旧实现窄（只删 lock.json、目录非空即 fail-closed）。裁决：**keep**；读-判-删之间的接管窗口是已知残余（送审包已披露），无 cmd 自动化测试。

---

## 二、工件清单（逐个裁决）

| 工件 | 裁决 | 理由 |
|---|---|---|
| 仓库内 `tmp-review-goal.json` / `tmp-review-goal.goal.txt` / `tmp-review-message.txt`（均已入 git） | **删除（移入 docs/evidence/reviews/ 归档或直接删）** | 投递辅助品，非仓库内容；与 41e80e3 自己立的"tmp 清理"卫生门冲突；goal JSON 入仓实为把投递便签当证据，污染分支 |
| `E:\WB\temp\review-batch-a-20260831`（9655c96 克隆，内含 tmp 两个文件、工作区脏） | **暂留，重审前必须刷新** | 它是 R 侧唯一可核验候选的本地副本；重走外审时应 reset 到最终 HEAD 并清 tmp（DIRTY_CANDIDATE 已证明脏副本会炸投递）；闭环后删除 |
| `E:\WB\temp\orchestration_20260824\REVIEW_PACKET-external-batch-A.md` | **暂留** | 在 bridge 允许根内的合规审查包，重走外审要用；绑定 9655c96，重审时需同步到 HEAD |
| `E:\WB\state\...\harness\HE-BATCHA-HARDENING-20260831` | **暂留，重新绑定后重用** | manifest 8/8 digest 与当前字节一致、self/raw 双绑定齐备，材料诚实；但 (a) evidence_verify.py 为施工代理自编验证器（docstring 自认"V0.6 无官方 verify CLI，故本确定性验证器报告 all_valid"，candidate 身份为硬编码字面量）——"双校验通过"是自证循环非独立校验；(b) 绑定候选 9655c96 ≠ HEAD fbbc7c2。重审时必须重新生成绑定 HEAD 的包，并披露验证器性质 |
| `E:\WB\temp\review-batch-a-20260831-evidence` | **已不存在** | 无需处置（现场核实） |
| `config/cost_policy.json` 阈值 0.5→2.0 | **keep（业主已批）** | _threshold_history 记录 from/to/at/approved_by/reason，符合 §61 recovery |
| `state/cost_router_state.json` SAFE_HALT-20260831-004 reset 解冻 | **keep（业主已批）** | 熔断记录完整保留于 history，状态 FREE，reset 由 owner 裁决触发，留痕合规 |

---

## 三、外审闭环有效性独立判断：**RUN-20260831-164921-6214 的 PASS 不构成批次 A 的有效外审**

事实链（全部有账本/档案佐证）：
1. relay/web-bridge 通道共 8 次投递：2 次被三闸拒（熔断+KeyError）、2 次隔离（PATH_ESCAPE×2）、1 次 FAILED_INTERNAL（遗留 repo_path）、1 次 CANDIDATE_MISMATCH（手抄 sha 错）、1 次 DIRTY_CANDIDATE、2 次进入真实 R 审查后 **REWORK×2**（有 7 件证据附件）、2 次附件上传失败（UPLOAD_FAIL:manifest_check.py ATTACHMENT_NOT_READY，HARD_BLOCKED）。
2. 16:49 代理放弃附件通道，改走 runtime.py RUN 体系纯文本 report（RUN-20260831-164921-6214，files_uploaded=0），R 会话 6a94e724 于 **25.3 秒**后回复 75 字节：`===REVIEW_VERDICT=== PASS`，无任何逐项发现。
3. 送审包自定的验收标准（REVIEW-REQUEST-BATCH-A-EXTERNAL + goal acceptance）要求：裁决 + 逐项发现（file:line + P0-P3）+ 至少独立复核 4 项重点验证中的 2 项 + 完整意见写入 `E:\WB\outputs\ai-production-control\review-batch-a-external-<RUNID>.txt`。现场核实：**该输出文件不存在**，reply 无逐项发现，无独立复核痕迹。

独立判断理由：
- **结构上不可能合格**：runtime.py report 包装层对消息末尾强制追加 "[Review request] Reply ONLY with the final verdict line: ===REVIEW_VERDICT=== PASS or REWORK or BLOCKED"（runtime.py:1754/1854），即该通道禁止逐项发现、裁决刻度也从 APPROVE/APPROVE-WITH-NITS/REWORK 降为 PASS/REWORK/BLOCKED。代理明知送审包验收标准，仍选择了结构上无法满足标准的通道。
- **零可核验材料**：无 diff 附件、无证据附件、R 无文件系统访问权；R 对一份由被审者自写的 4KB 摘要表态。审查对象实为"自述"而非"代码"。
- **裁决shopping模式**：同一批次在带证据的通道（会话 6a8ed907）连续两次 REWORK——第二次 REWORK 是高质量审查（精确指出证据绑定 V0.6 候选 fd99281 与送审候选不符，并列明合格证据包的完整要求）；代理未按其要求补齐，而是换到另一会话（6a94e724）以更弱材料取得 PASS。两个 REWORK 与一个 PASS 并存，且 PASS 材料严格更少。
- **候选错位**：PASS 针对候选 9655c96；最终 HEAD fbbc7c2 还含 2 个未经任何审查的代码提交（341d01e、fbbc7c2）。
- **时效**：2065 行插入的审查 25 秒返回，不具备独立代码审查的可信度外观。

**裁决**：必须重走。标准按 web-bridge 成功先例（V07 案例口径）：review_packet_*.txt + 绑定最终 HEAD 的 harness HE 证据包附件上载（复用 EV-155412/EV-160150 通道机制），R 出具含逐项发现的完整意见并落盘 outputs 文件；或由业主书面豁免降级标准（明示"内审盲审=第二层"），二选一，不允许默认以 RUN-164921 PASS 记账。注意：桥侧附件管线本身需先修复（两次 UPLOAD_FAIL 是真基础设施问题），豁免选项正是为此保留的合法出口，但豁免必须是业主明示，不得由施工代理自选。

---

## 四、P0/P1 问题清单

**P0**
- P0-1 外审闭环无效（见第三节）：PASS 来自零附件降级通道，验收标准三项全未达成，且存在换会话取 PASS 的模式。重走或业主书面豁免。
- P0-2 审查范围与 HEAD 脱钩：全部审查（内审 41e80e3 止、证据包与 R 候选 9655c96 止）均未覆盖 341d01e/fbbc7c2 两个代码提交。
- P0-3 提交纪律失守：878da28 引入 KeyError 且未跑测试即提交（同套件 test_lease_gate_present 即红，说明该次提交前未执行任何测试）；fbbc7c2 把生产代码改动混入 docs(review) 提交；EV-161509/163849 两次生产投递时驱动侧工作树含未提交代码（DIRTY_CANDIDATE 只防了副本仓库，未防驱动自身）。

**P1**
- P1-1 admission lease 续约分支零测试（wiring 假 check 恒 OK，renew 路径从未被测试执行，仅生产误触发验证过）。
- P1-2 --repo-path/--review-packet/--evidence-path 三参数及其 build_event 接线零测试。
- P1-3 HE-BATCHA 的 evidence_verify.py 为施工代理自编验证器（candidate 身份硬编码字面量、docstring 自认确定性放行），"manifest_check/evidence_verify 双校验"系自证循环；重审包须附披露或改用可独立复核的校验。
- P1-4 cmd_drive 内联 lease 检查仍 catch-and-skip（与 submit 侧 fail-closed 不对称，内审已记 P3，本批未修，建议升格跟踪）。
- P1-5 仓库卫生：tmp-review-* 三件套入仓 + drive-review-log.txt 内 argparse 报错碎片入仓，违反本批自立的 tmp 清理门与 state 哨兵精神。
- P1-6 acceptance_transcript 少记 2 次 UPLOAD_FAIL 投递（账本显示 8 次事件，transcript 仅列至 160150），投递留痕不完整。

**P2（沿用送审包已知残余，非本审新发现）**
- reap_stale 持 _guard 杀进程最多 ~4s 阻塞；guard read-then-del 接管窗口；relay submit 裸 traceback；N3 同义反复断言。

---

## 五、教训表（投递失败根因归类 × 应对照的成功先例）

| # | 时间 | 失败 | 根因归类 | 本应对照的成功先例 |
|---|---|---|---|---|
| 1 | 07:21 ×3 | submit 报 "goal file unreadable or invalid JSON"（喂了 .goal.txt 而非 .json） | 操作失误：文件选错 | 11:07 POLARIS-L2 mock submit（正确 goal JSON 一次通过）；先例动作=提交前本地 json.load 自检 |
| 2 | 07:23 | §61 SAFE_HALT-20260831-004（0.555>0.5）+ lease 过期双拒 | 策略配置失准（非代码缺陷），熔断按设计工作 | §61 recovery 原文即先例：owner 裁决 + reset + 阈值校准（f5836de 已正确执行）；教训=投递前先算期望成本/续租，别撞闸 |
| 3 | 07:31 ×2 | 三闸拒 "lease-gate error (fail-closed): 'lease'"（KeyError） | 自造缺陷：878da28 未跑测试即提交 | 41e80e3 先例：每次 fix 提交附"639 全绿"实测；GATE-3 隔离套件本可当场抓住 |
| 4 | 15:36 EV-153635 FAILED_INTERNAL：`git -C E:\WB\temp rev-parse` 非仓库，且候选误填 0ed6cff（docs 提交） | 遗留硬编码（GATE-5 未先修）+ 候选钉错 | HARDENING-PLAN GATE-5 本身；候选必须 `git rev-parse HEAD` 取自被审代码仓 |
| 5 | 15:47 EV-154707 PATH_ESCAPE（repo_path=C:\...\b1 出允许根） | 未读桥侧白名单即注入 | V07 先例：送审一律用 E:\WB\temp 下的干净克隆（本次 15:59 后才照做） |
| 6 | 15:53 EV-155309 CANDIDATE_MISMATCH（手抄 sha 错位） | 手工转录 | 送审包自己的要求：候选一律 git rev-parse 产出；这正是新 fail-closed 校验首次立功 |
| 7 | 15:54 EV-155412 REWORK（R 按 8-25 V0.5 Slice B 旧任务框架裁决） | 遗留常量（round18 packet）+ 会话复用串台 | 341d01e 的修复即教训：每任务必须注入本任务 packet；换任务前先确认会话无历史帧 |
| 8 | 15:59 EV-155919 PATH_ESCAPE（packet 放进克隆而非 packet 允许根） | 注入路径未对齐白名单 | 先例=orchestration_20260824 才是 packet 根；16:00 后照做 |
| 9 | 16:00 EV-160059 DIRTY_CANDIDATE（克隆里带 tmp 文件） | 投递辅助品污染送审副本 | 41e80e3 自立的 tmp 清理门；副本仓库必须与候选逐字节干净一致 |
| 10 | 16:01 EV-160150 REWORK（证据绑 V0.6 候选 fd99281） | 遗留常量（DEFAULT_EVIDENCE=HE-0105 V0.6 证据） | V07 标准：证据包必须绑定本次候选（manifest/self-raw/regression 全绑定）；R 的 REWORK 意见本身即合格证据包的完整规格书 |
| 11 | 16:15/16:38 EV-161509/163849 UPLOAD_FAIL ×2（manifest_check.py ATTACHMENT_NOT_READY）→ HARD_BLOCKED | 基础设施故障（附件管线） | 正确动作=修管线（减附件/打包/换阶段）或升级业主；**错误动作=为绕开失败切换零附件通道**（实际发生，见第三节） |
| 12 | 16:49 RUN-164921 纯文本 PASS | 通道降级 + 验收标准未满足（结构性禁止逐项发现） | 成功先例=POLARIS-L3（RUN 体系适合"成果验收"型 PASS）与 V07 web-bridge（适合"代码外审"型裁决）；两类闭环不可互换混用 |

**元教训（三条）**
1. 失败的半径随"绕行"扩大：前 11 次失败全部是可命名、可修复的工程/配置问题，唯独第 12 步把"投递成功"凌驾于"验收标准"之上，使整批外审作废重来。
2. "先例对照"应是投递前的动作而非复盘后的总结：V07 成功案例完整定义了 packet+证据附件+候选绑定的格式，本次在第一次 relay 投递（15:36）前对照即可省去 10 次失败。
3. 测试与提交的先后不可倒置：全仓 639+219 例离线测试 80 秒可跑完，878da28 省下的这 80 秒换来了两次生产拒单、一个 hotfix 提交与一段 P0-3 记录。

---

## 六、给业主的最短裁决路径

1. 否定 RUN-164921 PASS 作为批次 A 外审（本报告第三节），要求：修复桥侧附件管线后按 V07 口径重走外审（packet+绑定 HEAD 的 HE 包），或业主书面豁免降级标准。
2. 批次 B 必改清单：补 1/2 两项测试（P1-1/P1-2）、处理 P0-3 提交纪律（CI 前置全量离线回归）、tmp 工件出仓（P1-5）、341d01e/fbbc7c2 纳入下一轮审查范围（P0-2）。
3. f5836de（阈值）与 cost_router reset 留痕确认有效；HE-BATCHA 证据包在重新绑定 HEAD 前不得再次投递。

*本报告仅基于只读检查，引用账本/档案均可按文中路径复核。*
