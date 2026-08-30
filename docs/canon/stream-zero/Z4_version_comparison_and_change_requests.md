# Z4 版本对照与变更请求（ai-production-control · Stream Zero）

- 产出人：许清楚（Xu / Product Manager）
- 日期：2026-08-29（会话日）
- 性质：文档考古收尾产出（流 Zero Z4）。**全程未触碰施工 worktree**；仓库现行基准信息仅引自主理人提供的 PROJECT_STATE.md（2026-08-28）与 PROJECT_STATE.json 摘要。
- 上游依据：业主《全权委托章程 v4.4》（SHA256 769c7c62…440fe，§2 权威层级、§4 流 C 指定项）；定稿 A/B；Z2/Z3 产出。

---

## 一、现状

### 1.1 两套并存的有效版本语义

| 基准 | 载体 | 内容 | 法律地位（章程 §2） |
|------|------|------|---------------------|
| 历史基准 | 定稿 B《执衡施工总路线 v2》（SHA256 `995b1c9679a96b51f4e884aaa8fd8d69e959b27bac6db11afe0ab23583b1ddbe`，1550 行 LF） | Stage 0 → V0.1～V1.0 十三级路线（V0.10 = Multi-Worker；V0.11 = Production Capability Expansion；V1.0 = Self-hosted Iteration） | 历史基准：记录 08-23/24 规划冻结时点的版本号语义 |
| 现行基准 | 仓库 PROJECT_STATE.md / PROJECT_STATE.json（GitHub 远端，2026-08-28） | **Phase 0 → V0.9 收口 → V0.10 单类真实 GOAL → V0.11 REWORK/RECOVERY → V1.0 硬化**（用户已批准） | **当前版本基准**：可演化，任何变更须经业主裁决 |

补充事实（来自 Z2/Z3，证据路径见落款）：

- 现行 V0.1–V1.0 序列的历史起点是 2026-08-23 03:43"评估路线问题"会话的"小幅重排"评审，其十三级序列与定稿 B 章节逐级一致（Z3·R2，VERIFIED）。
- 施工期（08-23/24）路线未被推翻：唯一推翻级风险 LOCAL_SUPERVISOR_BOOTSTRAP 当日撤回，撤回令明示"恢复冻结 Roadmap"（Z3·R15，VERIFIED）。
- PROJECT_STATE.json 顶层键含 `roadmap` / `open_questions` / `do_not_reopen`；`spec_registry` 已有 V14-FROZEN 登记先例（登记机制可用）。

### 1.2 证据链现状

- 定稿 A/B 哈希已由主理人校验并与本组复核一致（Z2 §1，VERIFIED）。
- 旧1（粘贴版 1）≡ 定稿 A（仅差末尾 1 字节 LF），无缺口。
- 旧2（粘贴版 2，"修订结论"0–31 节）的直接源会话**不在已给的三个导出内**（独特语句探针三导出全部 0 命中；Z3·R16，INFERRED），疑似 2026-08-24 白天更晚的会话——证据链存在一处已知缺口。

## 二、问题

### P1（冲突，章程 §4 流 C 指定项）：V0.10 语义冲突

- 定稿 B：**V0.10 = Multi-Worker**。
- 仓库现行基准：**V0.10 = 单类真实 GOAL（本地文件/代码任务类）**。
- 业主章程已指示：Multi-Worker 语义记入版本对照，视为后续能力扩展候选，不得与现行 V0.10 混用。
- 风险：若不显式登记，任何引用"V0.10"的文档/会话/Spec 都存在二义性；且 Multi-Worker 在 v2 中排在 Adapter 产品化（V0.8）、Authority 硬化（V0.9）之后，属后期扩展，提前混入现行 V0.10 会破坏"每次只加一个可靠性维度"的路线哲学（Z3·R2）。

### P2（权威层级）：历史基准与现行基准的裁决关系需登记生效

- 章程 §2 已定：仓库当前路线（PROJECT_STATE/ROADMAP，GitHub 远端）= 当前版本基准（可演化，变更须业主裁决）；路线 v2 的版本号语义 = 历史基准。
- 需要把该权威层级与 P1 的裁决一并写入登记（建议走 PROJECT_STATE.json 既有登记机制，参照 V14-FROZEN 先例），否则 V0.9–V1.0 各级的"收窄/演化"缺乏可引用的效力凭证。

### P3（对照缺口，已由主理人补核关闭）：V0.1–V0.8 不在现行 roadmap 登记范围

- 主理人于 2026-08-29 直接读取施工 worktree 的 `PROJECT_STATE.json` → `roadmap` 字段核实：现行 roadmap 仅含五级序列 `["PHASE_0","V0.9_CLOSE","V0.10_REAL_GOAL","V0.11_REWORK_RECOVERY","V1.0_HARDENING"]`（approved: 2026-08-28 by user）+ discipline 一行，**无任何 V0.1–V0.8 条目**。
- 结论：V0.1–V0.8 属**已完成施工历史**（其版本语义冻结于各阶段出口时的 PROJECT_STATE/证据文件，不是现行基准的组成部分）。对照表相应行由"待核"改为"历史已完成"，其 v2 语义作为历史基准保留，不构成冲突。

### P4（证据缺口）：旧2 直接源会话未导出

- 影响：旧2 谱系中"O/千问/WorkBuddy/R 组织修订结论"一脉（Z2 谱系二、Z3·M4）只能给到 INFERRED 级；若业主需要该脉完整证据链，需补导出。

### P5（备考，非问题）：定稿 B 含 68 处空代码围栏对

- 纯净化转换伪影（Z2 §2.2(d)，VERIFIED）。**定稿入仓为逐字节复制，不改原文**；本文件仅作登记说明，任何下游读者遇 B 中 ```` ``` ```` 紧跟空围栏的段落，应参照上下文而非视作内容缺失。

## 三、对照表：路线 v2 各级语义 vs 仓库现行基准

标注口径：**一致** = 语义沿用；**演化** = 语义延续但有收窄/重排/重命名；**冲突** = 同一版本号承载不同能力；**待核** = 现行语义未取得，无法判定。

| v2 版本号（历史基准，995b1c96…） | v2 语义要点 | 仓库现行语义（2026-08-28 基准） | 标注 | 说明 |
|------|------------|--------------------------------|------|------|
| Stage 0 | 事实收口 / Construction Baseline；0.1 Truth Ownership 六件套 → 0.4 Reuse Gate Lite → EXIT | **Phase 0**（roadmap sequence[0]=PHASE_0） | 演化 | 现行序列首位即 PHASE_0；与 v2 Stage 0 的同阶段对应关系按 CR-4 确认 |
| V0.1 | Single-Task Reliable Loop；五个最小内核（Canonical Run State Lite / Evidence Binding Lite / Minimum Safety Kernel / Baseline Execution Capability / Adapter Seam）；验收 Case A/B/C | （现行 roadmap 无此级） | 历史已完成 | 施工期（08-23/24）曾按 Slice A/B/C… 推进并有 PASS 记录（Z3·R13/R14）；语义冻结于当期阶段出口证据 |
| V0.2 | Lifecycle Hardening（AI 停止项目不死亡；generation 隔离；旧 Worker 不能诈尸） | （现行 roadmap 无此级） | 历史已完成 | — |
| V0.3 | Revisioned Canonical State（版本化状态、恢复真相） | （现行 roadmap 无此级） | 历史已完成 | — |
| V0.4 | Goal Contract + Task Graph + Atomic Stop Rule | （现行 roadmap 无此级） | 历史已完成 | — |
| V0.5 | Evidence / Review Hardening（Review Bundle、PASS Invalidation） | （现行 roadmap 无此级） | 历史已完成 | — |
| V0.6 | EC / Execution Correction（执行现场纠偏，优先规则与状态机） | （现行 roadmap 无此级） | 历史已完成 | — |
| V0.7 | Brain + Strategic C + Strategic Reuse | （现行 roadmap 无此级） | 历史已完成 | — |
| V0.8 | Provider / Agent Adapter Productization | （现行 roadmap 无此级） | 历史已完成 | — |
| V0.9 | Authority / External Effect Safety Hardening（完整 Authority/Effect/Credential/Egress） | **V0.9 = 收口** | 演化（语义收窄/重定位） | 现行"收口"与 v2 的"安全硬化"是否同物异名，待确认（并入 CR-2 附带核对） |
| V0.10 | **Multi-Worker** | **V0.10 = 单类真实 GOAL（本地文件/代码任务类）** | **冲突** | 章程 §4 流 C 指定项。裁决方向已由业主指示：现行 V0.10 以"单类真实 GOAL"为准，Multi-Worker 降级为后续能力扩展候选，另立版本号或登记为扩展项（见 CR-1） |
| V0.11 | Production Capability Expansion | V0.11 = REWORK/RECOVERY | **冲突（重定位）** | v2 中 REWORK/RECOVERY 相关纪律散布于 Review Hardening（V0.5）与验收流程；现行将其升为独立版本级。属语义重定位而非能力否定，建议按"演化（重定位）"登记（并入 CR-2） |
| V1.0 | Self-hosted Iteration（自举工业化） | V1.0 = 硬化 | 演化（收窄） | 现行"硬化"是 v2 V1.0 的收窄表述；完整自举语义保留为远期目标（并入 CR-2 附带确认） |
| （v2 无） | — | Phase 0 → V0.9 → V0.10 → V0.11 → V1.0（用户已批准） | 现行主干 | 现行主干为五级，比 v2 的十三级大幅收拢；被收拢的 v2 中间级语义作为历史基准保留，可在后续扩展时按需取用 |
| （Multi-Worker，原 v2 V0.10） | 多 Worker 并行 | 无现行版本号，降为扩展候选 | 演化（降级） | 见 CR-1 |

## 四、选项

### O-A：仅登记，不改任何文件（推荐）

在 PROJECT_STATE.json（或同等登记位）以既有登记机制（参照 V14-FROZEN 先例）追加一条版本语义对照登记：现行基准胜出、v2 降为历史基准、Multi-Worker 移出 V0.10。不修改定稿 B、不修改 PROJECT_STATE.md 正文。
- 优点：零代码风险、可回溯、与"变更须业主裁决"流程一致。
- 缺点：两套文档并存，新人仍可能读 v2 产生误解（靠登记条目兜底）。

### O-B：修订定稿 B 附加勘误页

在 B 之后追加"勘误/历史标注"页说明 V0.10 等冲突。
- 优点：读者在源头即见标注。
- 缺点：定稿 B 已冻结哈希（995b1c96…），任何改动破坏哈希链与"逐字节复制"纪律；**不推荐**。

### O-C：维持双语义，仅在需要时人工消歧

- 优点：零成本。
- 缺点：二义性持续存在，违反章程 §4 流 C 的指定处理方式；**不推荐**。

## 五、影响面

1. **施工执行**：V0.10 开发范围的唯一依据变为"单类真实 GOAL"；Multi-Worker 相关设计（并行 Worker、Provider 轮换的多实例面）不得提前混入。Z3·R15 已确立"受控自我迭代、每版只加一个可靠性维度"，本裁决与其同向。
2. **文档/Spec 引用**：所有引用 V0.9–V1.0 的 Spec、任务书、会话提示词需按对照表口径解读；引用旧 v2 语义的文本（若有）在下次触及机会修正，不发起专项返工。
3. **证据链管理**：旧2 证据缺口（P4）不阻塞任何施工；仅影响文档考古结论的证据等级（该脉维持 INFERRED）。
4. **登记机制**：需在 spec_registry / PROJECT_STATE.json 落一条登记（O-A），不动 roadmap 主干结构；`do_not_reopen` 可考虑追加"不得以 v2 语义重开 V0.10 = Multi-Worker"条目（由业主裁决是否加入）。
5. **无代码影响**：本对照与裁决均为文档层，不触碰 runtime/仓库 worktree。

## 六、待业主裁决项清单

| 编号 | 裁决项 | 建议裁决 | 依据 |
|------|--------|---------|------|
| CR-1 | **V0.10 语义收窄确认**：确认现行基准"V0.10 = 单类真实 GOAL（本地文件/代码任务类）"为唯一有效语义；Multi-Worker 降级为后续能力扩展候选，另立版本号或登记为扩展项，不得与现行 V0.10 混用 | 按 O-A 登记生效 | 章程 §4 流 C 指定项；Z2 对照（B 中 V0.10=Multi-Worker）；现行基准（PROJECT_STATE 2026-08-28） |
| CR-2 | **权威层级与对照表生效确认**：确认"仓库 PROJECT_STATE/ROADMAP = 当前版本基准（可演化，变更须业主裁决）；路线 v2 = 历史基准"，并确认本文件第三节对照表为两套语义的官方对照；附带核对 V0.9"收口"vs v2 V0.9"安全硬化"、V0.11 重定位、V1.0"硬化"的标注是否认可 | 认可并登记 | 章程 §2；Z2/Z3 产出 |
| CR-3 | **旧2 证据链闭合**：是否补导出旧2（"粘贴的 markdown (2)。md"，0–31 节修订结论）的直接源会话（疑似 2026-08-24 白天更晚会话）以将 Z2 谱系二、Z3·M4 从 INFERRED 升级为 VERIFIED？不补亦不阻塞施工 | 可选补导出；默认不阻塞 | Z3·R16 探针 0 命中 |
| CR-4 | **Phase 0 ↔ v2 Stage 0 对应关系确认**：确认 Phase 0 与 v2 Stage 0 为同一阶段的演化（重命名/收编）。V0.1–V0.8 已核实不在现行 roadmap 登记范围（P3 已闭合），无需补核 | 确认对应关系并登记 | 本文件 P3（主理人 2026-08-29 直读 roadmap 核实） |

备考登记（无需裁决）：定稿 B 含 68 处空代码围栏对（纯净化转换伪影，Z2 §2.2(d) VERIFIED）；**定稿入仓为逐字节复制、不改原文**，本条仅作读者指引。

---

## 落款：证据路径

| 证据 | 路径 / 标识 |
|------|------------|
| 业主章程 v4.4 | SHA256 769c7c62…440fe（主理人校验） |
| 定稿 A（宪法） | D:\下载\chatgpt原始会话内容\执衡_最终定义_FINAL_CANONICAL.md，SHA256 4c05a21fab1543a209cafd70fee48752e996cf3a77df2987f316dde243f4a9a4 |
| 定稿 B（路线 v2） | D:\下载\chatgpt原始会话内容\执衡_最终版本迭代方案_v2_纯净版.md，SHA256 995b1c9679a96b51f4e884aaa8fd8d69e959b27bac6db11afe0ab23583b1ddbe |
| Z2 版本谱系表 | E:\WB\outputs\ai-production-control\stream-zero\Z2_lineage_table.md |
| Z3 修订史登记表 | E:\WB\outputs\ai-production-control\stream-zero\Z3_revision_registry.md（R2/R13/R14/R15/R16 为本文件主要引用条目） |
| 会话导出解压产物 | E:\WB\outputs\ai-production-control\stream-zero\extracted\（评估路线问题_6a8a6c6d / 给出施工执行方案_6a8a7acb / 分支 · 执行顺序规划_6a8a98ec） |
| 仓库现行基准 | PROJECT_STATE.md（2026-08-28）；PROJECT_STATE.json 顶层键 roadmap/open_questions/do_not_reopen、spec_registry V14-FROZEN 先例（引述来源：主理人指派信息）；roadmap 字段已于 2026-08-29 由主理人直读核实（P3） |

（本文件为流 Zero Z4 唯一产出；未修改定稿、未触碰施工 worktree。）
