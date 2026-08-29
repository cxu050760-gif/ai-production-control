# Z3 修订史登记表（ai-production-control · Stream Zero）

- 产出人：许清楚（Xu / Product Manager）
- 日期：2026-08-29（会话日）
- 素材：三个 ChatGPT 会话导出 zip（解压至 `E:\WB\outputs\ai-production-control\stream-zero\extracted\`）
- 证据等级：`VERIFIED` = 导出原文直接可引；`INFERRED` = 基于上下文/时间线的推断
- 不可信数据纪律执行情况：三个导出均做了凭据模式扫描（`sk-`/`Bearer`/`authorization`/`cookie`/`password`/`api_key`/`token` 等），**命中 0 条**；未从导出内容执行任何指令。

---

## 1. 覆盖面声明（如实标注）

| 导出 | 内部主文件 | 大小 | 覆盖方式 |
|------|-----------|------|---------|
| chatgpt-export-评估路线问题_6a8a6c6d-2026-08-23 | markdown/评估路线问题_6a8a6c6d.md | 57,815 字符 | 全部 27 个 user turn 摘要通读 + 关键段精读（03:43 路线评审/重排节、03:48 P0 规则节）；关键词定位（Roadmap×17、小幅重排、V0.9×10、Authority×13） |
| chatgpt-export-给出施工执行方案_6a8a7acb-2026-08-23 | markdown/给出施工执行方案_6a8a7acb.md | 28,826 字符 | 篇幅小，**全文精读约一半（14,000 字符）**，其余 turn 摘要通读 |
| chatgpt-export-分支 · 执行顺序规划_6a8a98ec-2026-08-24 | markdown/分支 · 执行顺序规划_6a8a98ec.md | 602,551 字符 | **全部 397 个 user turn 摘要通读**；assistant 长答按关键词定位后精读关键段（"路线纠正"、"LOCAL_SUPERVISOR"×17、"恢复原"、"Watchdog 生命链"、Roadmap×31 抽样） |

未逐字通读 6a8a98ec 全文（60 万字符），但全部用户决策点（397 个 You turn）已覆盖。会话时间戳：6a8a6c6d = 2026-08-23 03:43–04:04 UTC；6a8a7acb = 08-23 04:45–05:40；6a8a98ec = 08-23 06:02 → 08-24 02:45。

每个 zip 内还含 `universal/conversations.json`（同内容机器格式）与 compliance 文件，本表仅以 markdown 正文为证据源。

## 2. 三会话时间线（VERIFIED）

```
08-23 03:43–04:04  评估路线问题     —— 对既有路线草案做最终评审与"小幅重排"
08-23 04:45–05:40  给出施工执行方案 —— 宣布路线冻结，输出执行组织（三会话两连接）与 8 步操作
08-23 06:02–08-24 02:45  分支 · 执行顺序规划 —— Stage 0 → V0.1 实际施工全程（397 turn），
                                        中途发生一次重大"路线纠正"（GAP_RECONCILIATION）
```

## 3. 修订史登记表

| # | 来源（zip + 内部文件 + 位置） | 日期（UTC） | 修订主题 | 要点（旧 → 新） | 对现行定稿的影响 | 证据等级 |
|---|------------------------------|------------|---------|----------------|----------------|---------|
| R1 | 评估路线问题_6a8a6c6d，"还有一个我认为很关键的问题：所谓'无限细化'必须有停止条件"起至"小幅重排"节 | 08-23 03:43 | 路线评审：细化停止条件 + Stage 0 防失控 + 真源/视图分离 | 路线草案（被评审文件，`filecite turn0file0`，原文未随导出保存）→ 评审意见：CONTEXT 只能是 View 不能成为 Truth；Stage 0 要防"整理地狱" | 采纳（理念进入定稿 A/B 的 Truth Ownership 与 Stage 0 范围硬限制） | VERIFIED（意见原文）；影响判定 INFERRED |
| R2 | 评估路线问题_6a8a6c6d，"# 我建议最终路线只做一个小幅重排" | 08-23 03:43 | **路线版本序列重排（现行 V0.1–V1.0 序列的诞生点）** | 旧草案的 V0.x 排布 → 新序列：Stage 0（事实收口+Truth ownership+Reuse Gate Lite+critical-path smoke）→ V0.1 单任务闭环（+Canonical Run State Lite/Evidence Binding Lite/Minimum Safety Kernel/基础执行能力）→ V0.2 生命周期（generation/fencing/watchdog）→ V0.3 Revisioned Canonical State → V0.4 Goal Contract+Task Graph+双视图 → V0.5 Evidence/Review Hardening → V0.6 EC → V0.7 Brain+C+Strategic Reuse → V0.8 Provider/Agent Adapter 产品化 → V0.9 完整 Authority/Effect/Credential/Egress → V0.10 Multi-Worker → V0.11 Production Capability Expansion → V1.0 Stable 自举 Candidate。评审者给旧草案 8/10，核心哲学"先冻结现有闭环→封 Stable→Stable 参与开发下一 Candidate→每次只加一个可靠性维度"不动 | **被采纳**：该序列与定稿 B 的章节序列逐一对应（B：Stage 0→V0.1 五内核→V0.2 Lifecycle Hardening→V0.3 Revisioned Canonical State→V0.4 Goal Contract+Task Graph→V0.5 Evidence/Review Hardening→V0.6 EC→V0.7 Brain+Strategic C+Strategic Reuse→V0.8 Adapter Productization→V0.9 Authority Hardening→V0.10 Multi-Worker→V0.11→V1.0 Self-hosted Iteration） | VERIFIED（重排原文完整可引）；与 B 的对应为 VERIFIED（逐章比对） |
| R3 | 评估路线问题_6a8a6c6d，"V0.1 的'三个简单任务'验收也应该稍微改一下" | 08-23 03:43 | V0.1 验收改造 | 旧："连续三个简单任务"（如"创建一个 txt 文件"×3）→ 新：三个不同性质路径 Case A 创建 Artifact / Case B 修改+machine check / Case C 故意制造错误→REWORK→自动修复→PASS，"证明的是闭环，不是写文件三次没坏" | **被采纳**：定稿 B"V0.1 验收"即 Case A—Create / Case B—Modify / Case C—Rework | VERIFIED；对应关系 VERIFIED |
| R4 | 评估路线问题_6a8a6c6d，03:48 答复（"钉死 3 个施工规则"实列 4 条） | 08-23 03:48 | 开工前 4 条 P0 施工规则 | ①累计回归门禁："V0.N PASS = V0.N 新增验收全部 PASS + V0.1～V0.N-1 的 Stable Regression Suite 全部 PASS"；②Stable/Candidate 从第一天物理隔离（main=Stable 禁直接改，candidate/* 分支）+ Run State 从 V0.1 就加 `schema_version`；③Review 从 V0.1 起 fail-closed（timeout/error/无法解析/缺 Evidence/hash 不符/Final/UNKNOWN ≠ PASS）；④Data Egress Lite 前移进 V0.1（只发 Review 必需内容，禁止 dump workspace） | 部分采纳进后续施工纪律（6a8a98ec 中 AC-11 fail-closed 复验、Candidate hash 绑定等实践与之吻合）；是否全部落入定稿文本未逐条核对 | VERIFIED（规则原文）；影响判定 INFERRED |
| R5 | 评估路线问题_6a8a6c6d，03:48 答复开头 | 08-23 03:48 | 被否决方案：整体重排 | "推翻路线、重新排序整个版本树" → 明确否定："没有发现需要推翻路线、重新排序整个版本树的大问题了……不建议继续改 Roadmap 了，直接开 Stage 0" | 被否决（重排仅限 R2 的小幅重排） | VERIFIED |
| R6 | 评估路线问题_6a8a6c6d，03:52–03:59 | 08-23 03:52 | 会话组织演进 | 2 会话 → 3 会话（+1 个专门传代码到 GitHub 的会话），理由"从现有能力找，而不是专门验证/补能力" | 部分采纳后被替代：最终组织由 R8 定为"三会话、两连接、一个本地 AI"（总控/Builder/Reviewer+本地 AI），代码上传职责并入 Builder+Git 前置 | VERIFIED（演进过程）；终局 INFERRED |
| R7 | 评估路线问题_6a8a6c6d，04:01 | 08-23 04:01 | 被质疑方案：ChatGPT 会话直接开发 | 用户质疑"为什么非要千问本地开发？ChatGPT 更聪明，让它先改本地验证不行吗（本末倒置？）" → 04:04 讨论了配合与"ChatGPT 会话不停"问题；最终架构仍为千问（本地 Worker）主开发、ChatGPT 会话任 Builder/Reviewer，ChatGPT 直连 GitHub 开发仅作为后手 | 被否决（否决理由：会话会停、非可程序调用的可靠入口；见 R9 的"可调用入口"论证） | VERIFIED（质疑与答复原文）；否决结论 INFERRED（综合 04:04 与 6a8a7acb 04:48 段） |
| R8 | 给出施工执行方案_6a8a7acb，04:45 首答"你现在到底怎么干" | 08-23 04:45 | **路线冻结宣告 + 执行组织定稿** | "没有发现还需要停工修改的 P0 级问题……到这里停止'总方案审计'"；组织=三会话（ZH-CONSTRUCTION-CONTROL 总控 / ZH-BUILDER-V0.1 / ZH-REVIEWER-V0.1）+ 两连接（B_URL/R_URL）+ 一个本地 AI；8 步操作序列（①文件入 Repo ②开总控 ③开 Builder ④开 Reviewer ⑤一次性交给本地 AI ⑥只跑 Stage 0 ⑦STAGE_0_ACCEPTED ⑧Runtime 接双链开 V0.1）；V0.1 验收=Case A/B/C+10 项检查 | 采纳；成为 6a8a98ec 施工的组织基线；对应旧2（修订结论）§5–§8 的"先开 O、Stage 0 两个网页会话"谱系前身 | VERIFIED |
| R9 | 给出施工执行方案_6a8a7acb，04:48 长答 | 08-23 04:48 | **关键架构修订：Runtime/Supervisor 非 AI 化** | 旧（用户设想）："本地 AI 控制三个网页会话、保证本地 AI 不停" → 新："AI 停了项目不能停"的不是 AI 而是**非 AI 的 Runtime/Supervisor 程序**；旧 Invocation 标 DEAD→新 Invocation 读 Canonical State 继续；三层生命链雏形（OS Supervisor→Runtime→AI）；"负责救人的 AI 自己死了谁救它"循环依赖论证 | **被采纳**：成为后续 runtime/run.cmd 实际架构与定稿 A"AI 是可替换资源、生命周期由确定性控制承担"的执行面表达 | VERIFIED |
| R10 | 给出施工执行方案_6a8a7acb，04:48 末段 | 08-23 04:48 | Stage 0 范围微扩 | 原 Stage 0 清单 → 追加 WORKER LIFECYCLE CHECK 4 项（调用入口？Runtime 能否启动/重启？新 Invocation 能否仅靠 Canonical State+Repo+Task 继续？）→ WORKER_REINVOCATION = VERIFIED/PARTIAL/BLOCKED；"不推翻 Roadmap，只补一个现场检查项" | 部分采纳（现场补检查，不改路线文本） | VERIFIED |
| R11 | 给出施工执行方案_6a8a7acb，05:34 答复 | 08-23 05:34 | V0.1 唯一 Local Worker 选型 | 泛化的"唤醒任何本地 AI" → 收敛为"把 WorkBuddy CLI 定死成 V0.1 唯一 Worker Host"；同时盘点已有（Bridge/52900 daemon/Runtime V1/run.cmd/R_URL 往返/REWORK 循环/WorkBuddy CLI+Parallel 全 ✅）与未证明（Runtime 永久 Supervisor⚠️/崩掉自启⚠️/任意 AI 可拉起❌/HY3、千问、DeepSeek 独立 CLI❌） | 采纳（后续施工即以 WorkBuddy CLI 为本地执行路径） | VERIFIED |
| R12 | 分支 · 执行顺序规划_6a8a98ec，06:02 首答（"一、现在最终组织结构，别再改了""二、你现在不要开四个 ChatGPT"） | 08-23 06:02 | 最终组织结构冻结 + 反对开四个会话 | 此前多会话设想 → 定案：先建 O（开发期总主脑，不接 Runtime）+ Stage 0 相关会话；"组织结构别再改了" | 采纳；与旧2 §1"O 是开发期间的总主脑"、§6"第一阶段只开 O"、§8"Stage 0 实际有两个网页会话"同源（旧2 为该谱系后续修订版，其直接源会话不在这三个导出内，见 R16） | VERIFIED（组织结论）；与旧2 同源关系 INFERRED |
| R13 | 分支 · 执行顺序规划_6a8a98ec，07:24–08:02 段 | 08-23 07:24–08:02 | Stage 0 首轮 REWORK 与冻结 | R 审查 Verdict=REWORK（BLOCKING 1：正式生产 Runtime 未绑定 Git 基线）→ 用户接受 REWORK_PLAN，"不进入 V0.1、不开始 Multi-Role Router、不扩大 Stage 0 范围，唯一施工顺序锁定"；随后 Stage 0 Canonical State 冻结，PASS 绑定完整 Review Lineage（REWORK→Blocking 1→TASK_1 Evidence→…），"不作为孤立字符串处理" | 采纳（过程决策，非路线文本修订；但确立了 PASS 必须绑定审查链的纪律） | VERIFIED |
| R14 | 分支 · 执行顺序规划_6a8a98ec，09:03–09:49 段 | 08-23 09:03–09:49 | V0.1 切片细化 + 插入前置 | Slice A（Router Bootstrap）PASS 后 → 插入"Slice B FIRST_TASK 前必须补齐的 Bootstrap"（Builder Git Production Access Bootstrap，GitHub 权限打通+1f3b4300 运输链验证 Candidate）；09:49 "V0.1 Slice B 最小施工任务正式冻结"（GAP_AUDIT 结果，不重开盘点、不进 Slice C+） | 采纳（V0.1 内部切片序演进：Slice A→B→C…；定稿 B 只保留到"五个最小内核+Case A/B/C"粒度，切片序属于执行层） | VERIFIED |
| R15 | 分支 · 执行顺序规划_6a8a98ec，13:13–13:39 段（含 "# 所以，我会修改我们刚才的施工顺序"） | 08-23 13:13–13:39 | **重大路线纠正：LOCAL_SUPERVISOR_BOOTSTRAP 提出→撤回（GAP_RECONCILIATION）** | 被否决方案：为达成 MINIMUM_UNATTENDED_LOOP_E2E，插入 `LOCAL_SUPERVISOR_BOOTSTRAP`（本地常驻监督器，O 任务发现→启动 Runtime→监督→回传 O）作为 V0.1 前置，并警告 Supervisor"不能成为第二个 Runtime"。→ 13:39 用户接受纠正：**"撤回 LOCAL_SUPERVISOR_BOOTSTRAP 作为 V0.1 前置；保留所有已 PASS 成果；恢复冻结 Roadmap；先做 V0.1 C～I 缺口对账 → 补最小 Gap → Slice J → Stable V0.1；Stable V0.1 一成立，立即进入受控自我迭代 Bootstrap，让 V0.1 参与开发 V0.2"**。Canonical State 更新：CURRENT_STAGE=V0.1，CURRENT_MODE=GAP_RECONCILIATION，"不修改产品定义、不修改总 Roadmap、不回滚任何已 PASS 成果" | **被否决（LOCAL_SUPERVISOR 前置）+ 恢复冻结 Roadmap（采纳）**；"受控自我迭代（V0.x Stable 可开发 Candidate 但不能自我宣布取代 Stable）"原则后被 B 的 V0.1–V1.0 依赖关系与安全边界吸收 | VERIFIED（撤回令原文完整可引） |
| R16 | （旁证）旧2"粘贴的 markdown (2)。md" 的源会话 | ≈08-24（文件创建 08-24 17:48） | "修订结论"文档（0–31 节） | 见 Z2 谱系表；其独特语句（"一句话冻结""本次修订结论""三会话两连接"等）在三个导出中**均未出现**（探针计数全 0；仅"Router Bootstrap"×12 在 6a8a98ec 中出现，属同谱系术语） | 说明旧2 的直接源会话晚于 08-24 02:45（6a8a98ec 导出结束点），**不在这三个 zip 覆盖范围内** | INFERRED（探针证据 VERIFIED，结论为推断） |
| R17 | 分支 · 执行顺序规划_6a8a98ec，08-24 02:15 前后（"恢复原"上下文） | 08-24 02:15 | Runtime 自愈设计原则（沉淀不改期） | 用户"程序出问题 AI 会去修" → 助手确立：Runtime 连续机械恢复失败→冻结现场 Evidence→启动 Repair AI→Candidate→R 审查→PASS→替换 Stable；安全边界"AI 不能直接改正在运行的正式 Runtime"；设计原则："**Runtime 负责救 AI；极小的 OS 托管 Watchdog 负责救 Runtime；复杂故障再唤醒 AI 来修 Runtime**"；明确"现在先别造它"，完整 Watchdog/自愈归 V0.2 Lifecycle Hardening | 原则采纳、施工后置（与 B 的 V0.2 定位一致） | VERIFIED |

## 4. 路线文本中间修订版清单（与定稿 B = 995b1c96… 的关系）

| 变体 | 出现位置 | 内容形态 | 与定稿 B 的关系 |
|------|---------|---------|----------------|
| M0 路线草案（被评审稿） | 评估路线问题 03:43，`filecite turn0file0` 引用（L5–L20、L27–L82、L828–L886、L3042–L3081 等引注；**原文未随导出保存**） | 含 PRODUCT_DEFINITION 分离、Stage 0、V0.1"三个简单任务"、三会话两连接、V0.x 排布（旧序） | B 的前身；其"三会话两连接"组织与 V0.x 旧序被 R2/R8 修订 |
| M1 小幅重排版 | 评估路线问题 03:43"我建议最终路线只做一个小幅重排"（完整 13 级序列原文在案） | Stage 0 + V0.1（四件套内核）+ V0.2…V1.0 | **与 B 的版本序列逐级一致**（B 在 V0.1 增为五个内核、补 Case A/B/C 验收与各版本验收节）——B 的直接文本祖先级中间版 |
| M2 执行化版 | 给出施工执行方案 04:45（8 步 + 三会话两连接 + Stage 0 任务书全文） | 路线 + 操作手册混合体 | B 的执行序言；其 Stage 0 任务书 13 项检查与 B 的 Stage 0.1–0.4 分解同源而粒度不同 |
| M3 纠正后状态 | 执行顺序规划 13:39 Canonical State（撤回 LOCAL_SUPERVISOR、恢复冻结 Roadmap、V0.1 C–I 对账→Slice J→Stable V0.1→受控自我迭代） | 执行态快照，非路线全文 | 与 B"V0.1→V0.2 依赖关系"一致；确认 B 冻结的 Roadmap 未被施工期推翻 |
| M4 修订结论文档（旧2 谱系） | ≈08-24 17:48 前的后续会话（不在三导出内）；存档=粘贴的 markdown (2)。md | 0–31 节问答体，O/千问/WorkBuddy/R 组织与施工流程 | 与 B 同谱系不同侧：B=去角色化路线正文（v2 纯净版）；旧2=带角色的执行组织修订结论。B 相对旧2 删除角色层、保留版本主干（详见 Z2 谱系表 §3.2） |
| M5 定稿 B | 执衡_最终版本迭代方案_v2_纯净版.md（08-29 定稿，SHA256 995b1c96…1ddbe） | Canonical Roadmap v1（文末自称） | 终点：M1 序列 + M0/M2 中仍有效的硬规则（fail-closed、Stable/Candidate 隔离等体现为验收与依赖章节）+ 去角色化 |

## 5. 关键发现（供主理人参考）

1. **现行 V0.1–V1.0 版本序列诞生于 08-23 03:43 的"小幅重排"评审**（R2），此前旧草案排序不同；定稿 B 的章节序列与该中间版逐级一致，B 是其净化+验收补全的定稿，而非另起炉灶。`VERIFIED`
2. **施工期唯一一次"推翻级"风险点是 LOCAL_SUPERVISOR_BOOTSTRAP（08-23 13 点段），当日即被正式撤回**，撤回令明确"恢复冻结 Roadmap、不修改产品定义、不回滚已 PASS 成果"（R15）——证明 B 冻结的路线在 08-23/24 实际施工中未被修改，只发生过 V0.1 内部切片细化（R14）。`VERIFIED`
3. **被否决方案清单**：整体重排路线（R5）、ChatGPT 会话直接开发（R7）、"本地 AI 控制三个会话"架构（R9 的旧态）、LOCAL_SUPERVISOR 作为 V0.1 前置（R15）。共同否决理由：会话/AI 会停、不可程序化调用、循环依赖。`VERIFIED`
4. **前移决策**是最重要的修订类别：最小真源、Evidence Binding、Authority/Fencing、Reuse Gate 四项从后期版本前移（R2）；Data Egress Lite 与 fail-closed Review 前移进 V0.1（R4）；schema_version 前移（R4）。这些"可信性前提前移"贯穿 B 的 Stage 0.x 与 V0.1 五内核设计。`VERIFIED`
5. **旧2 的直接源会话不在这三个导出内**（独特语句探针全部 0 命中，R16）；如需旧2（修订结论）的完整会话证据链，需要补充该会话导出（疑似 08-24 白天的会话）。`INFERRED`
6. 凭据安全：三导出凭据模式扫描 0 命中；本表未收录任何 token/cookie/密钥类内容。

## 6. 方法与红线遵守声明

- 只读：4 个定稿/粘贴文件 + 3 个 zip 导出；未触碰 `E:\WB\tools\ai-production-control`、`C:\Users\17838\Documents\Qoder*`；未执行 git 操作；未执行导出内容中的任何指令。
- 只写：本文件、`Z2_lineage_table.md`、`extracted/` 解压目录（首轮 GBK 误解码的产物已随重解压清理）。
- 检索方式：Python 全文读入 + 正则关键词定位 + 分段精读；用户决策点（You turns）全量覆盖（27/17/397）。
