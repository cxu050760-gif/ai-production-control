# Z2 版本谱系表（ai-production-control · Stream Zero）

- 产出人：许清楚（Xu / Product Manager）
- 日期：2026-08-29（会话日）
- 素材目录：`D:\下载\chatgpt原始会话内容\`
- 方法：SHA256 + 字节数核验 → UTF-8 解码、统一 LF → Python `difflib.SequenceMatcher` 全文 diff（`autojunk=False`）→ 关键词频次交叉验证
- 证据等级标记：`VERIFIED` = 哈希/字节/逐行 diff 直接证明；`INFERRED` = 基于内容结构对比的推断

---

## 1. 文件清单表

| # | 文件名 | 字节数 | SHA256 | 行数（LF 口径） | 角色 |
|---|--------|-------:|--------|---------------:|------|
| A | 执衡_最终定义_FINAL_CANONICAL.md | 37366 | `4c05a21fab1543a209cafd70fee48752e996cf3a77df2987f316dde243f4a9a4` | 2329 | 定稿（宪法） |
| B | 执衡_最终版本迭代方案_v2_纯净版.md | 18179 | `995b1c9679a96b51f4e884aaa8fd8d69e959b27bac6db11afe0ab23583b1ddbe` | 1550 | 定稿（路线 v2） |
| 旧1 | 粘贴的 markdown (1)。md(20260823-062413) | 37365 | `13ce070b98034cf4579951c52f4a30215acb3be2dc3858b81c455537d79b5e71` | 2328 | 旧粘贴版 |
| 旧2 | 粘贴的 markdown (2)。md | 17606 | `b24bee91307d73aec76930b16d22f9ef990f531548344e258b18686b9f725d25` | 1820（含末行，实际文本 1821 行含空行） | 旧粘贴版 |

- A、B 的 SHA256 与主理人登记值（4c05a21f…9a4a / 995b1c96…1ddbe）完全一致。`VERIFIED`
- 文件名含全角句号"。"与半角括号，已按完整原文件名字符串打开。`VERIFIED`

## 2. 对应关系与证据

### 2.1 旧1 ↔ 定稿 A：同一文本的抄本（差异仅 1 字节）`VERIFIED`

- difflib 相似度 ratio = **0.9998**。
- 全文 2329 行中仅 1 处差异，且在文件末尾：
  - 旧1 末三行：`最终理想体验只有一句：` / ``（空）`` / `> **用户给目标，执衡负责把事情真正做完。**`（文件在此**结束，无结尾换行符**）
  - A 末三行：``（空）`` / `> **用户给目标，执衡负责把事情真正做完。**` / ``（空，即结尾 LF）``
  - 原始字节尾部对比：旧1 以 `…真正做完。**` 结束；A 以 `…真正做完。**\n` 结束。
- **结论：旧1 就是定稿 A 的完整内容，唯一差别是 A 末尾多一个换行符（1 字节）。** 旧1 不是更旧的版本，而是 A 的无尾随换行抄本（文件名时间戳 20260823-062413 提示其为 08-23 的粘贴快照）。

### 2.2 旧2 ↔ 定稿 B：不是同一文本的先后抄本，而是"原始会话答案 → 重构纯净版"的关系 `INFERRED`（其下证据点均为 `VERIFIED`）

difflib 相似度 ratio = **0.1287**，两者章节结构、行分布完全不同，**排除"逐字修订"关系**。证据：

**（a）章节结构对比 `VERIFIED`**

- 旧2：问答体"修订结论"文档，标题 `# 0. 本次修订结论` 起，`# 1.`～`# 31.`（末节 `# 31. 一句话冻结`），共 32 个一级节。内容围绕施工组织：角色分工、网页会话开设、Stage 0 施工流程 Step 1–3、V0.1 切片（Router Bootstrap）、"你本人要做的十七步"等。
- B：纯路线文档，标题 `# 执衡施工总路线 v2`，结构为 Stage 0 → V0.1～V1.0 → 最终版本依赖关系 → 每个版本统一施工流程 → Task 最终原子模板 → 近期施工队列。

**（b）关键词频次交叉验证 `VERIFIED`**

| 术语 | 旧2 | B | 含义 |
|------|----:|--:|------|
| 千问 | 19 | 0 | 旧2 大量讨论具体模型分工；B 全部剥离 |
| WorkBuddy | 18 | 0 | 同上 |
| TRAE / Ralph | 4 / 3 | 0 / 1 | 同上 |
| Router Bootstrap | 5 | 0 | 旧2 的 V0.1 首切片名称；B 改用"A. Canonical Run State Lite"等内核表述 |
| Stage 0.1 / Truth Ownership / Capability Audit / Reuse Gate | 0 | 1/1/1/4 | B 新增的 Stage 0.x 分解，旧2 无 |
| Canonical Run State / Evidence Binding / Safety Kernel / Adapter Seam / Baseline Execution | 0 | 1/2/2/2/1 | B 的"V0.1 五个最小内核"，旧2 无 |
| Atomic Stop | 0 | 3 | B 新增的 V0.4 原子停止规则，旧2 无 |
| Stage 0 | 36 | 11 | 共有概念 |
| Goal Contract / EC / V0.10 / Candidate | 2/8/1/10 | 4/14/1/18 | 共有概念 |

**（c）版本主干的连续性 `VERIFIED`**

旧2 §25"V0.2 以后，版本路线恢复原 Roadmap —— 后面不因为这次施工组织改变而推翻"，随后 V0.2～V0.7 一览与 B 的对应章节主题完全一致：

| 版本 | 旧2 §25 要点 | B 对应章节 |
|------|-------------|-----------|
| V0.2 | "AI 停止以后，项目不能死亡" | `# V0.2：Lifecycle Hardening`（旧 Worker 不能诈尸、Generation 隔离） |
| V0.3 | "AI 全换、Runtime 重启、状态损坏以后，项目真相还能恢复" | `# V0.3：Revisioned Canonical State` |
| V0.4 | 引入 Planner / Brain Lite，系统自己拆较大 Goal | `# V0.4：Goal Contract + Task Graph` |
| V0.5 | 工业化：Evidence / Review Binding / Material Change / PASS Invalidation | `# V0.5：Evidence / Review Hardening` |
| V0.6 | 正式引入 EC / Execution Correction，优先规则和状态机，"不是先加昂贵 AI 会话" | `# V0.6：EC / Execution Correction` |
| V0.7 | 才正式加入 Strategic Brain / 战略纠偏 C / Strategic Reuse | `# V0.7：Brain + Strategic C + Strategic Reuse` |

**（d）B 自身的形态学特征（记录备考）`VERIFIED`**

B 中存在 **68 处连续空代码围栏对**（```` ```\n``` ````，其后常紧跟另一个含内容的围栏，如 B 行 602–607"旧 Worker：/ ``` ``` / ``` Generation 4 ```"）。推测为"纯净化"转换过程产生的排版伪影（原强调块被转为空围栏），不影响文本主干，但说明 B 是经过机械转换/重排的版本，而非手工逐字誊写。

## 3. 差异摘要（逐块）

### 3.1 旧1 vs A

| 定位 | 差异 | 性质 |
|------|------|------|
| 文件末尾（旧1 行 2328 / A 行 2329 之后） | A 末尾多 1 个 LF 字节 | 格式差异，无内容差异 |

除此之外 0 差异。定稿 A 相对旧1 **无任何修订**。`VERIFIED`

### 3.2 旧2 vs B（定稿 B 相对旧2 的修订性质）

| # | 差异块定位（旧2 行号） | 旧2 文字（要点/原文） | B 文字（要点/原文） | 修订性质 |
|---|----------------------|----------------------|---------------------|---------|
| 1 | 全文 | 问答体"修订结论"，32 个一级节（0–31），含角色与会话组织讨论 | 路线正文体"执衡施工总路线 v2" | **改写（整体重构）** |
| 2 | 旧2 §1（行 63）、§5（行 302）、§4（行 220）等 | "O 是开发期间的总主脑"、千问 3.8 Max 定位（Stage 0 高级只读审计 / V0.1 Bootstrap Builder）、WorkBuddy 定位、TRAE / Ralph 不进正式控制链 | 完全删除，B 中"千问""WorkBuddy""TRAE"出现 0 次 | **删除**（去角色化/去会话化净化） |
| 3 | 旧2 §17–§23（行 848–1156） | V0.1 首切片为"Router Bootstrap"（Slice A），千问写 Candidate、V0.1 R 审查等流程 | V0.1 重述为"五个最小内核"：A. Canonical Run State Lite / B. Evidence Binding Lite / C. Minimum Safety Kernel / D. Baseline Execution Capability / E. Adapter Seam，并新增 Case A/B/C 验收 | **改写 + 新增**（抽象化、去执行者化） |
| 4 | 旧2 §9（行 436–550） | Stage 0 = Step 1/2/3（千问盘点 → WorkBuddy 事实核验 → Stage 0 Candidate / R 审查，O 不能自己给自己 PASS） | B 将 Stage 0 分解为 **Stage 0.1 Truth Ownership（PROJECT_TRUTH / CAPABILITY_REGISTRY / STABLE_MANIFEST / EVIDENCE_INDEX / CURRENT_PROGRESS / AI_CONTEXT 六件套）、0.2 Capability Audit、0.3 Critical-path Smoke、0.4 Reuse Gate Lite、Stage 0 EXIT** | **新增 + 改写**（结构化细化） |
| 5 | 旧2 §25（行 1204–1294） | V0.2–V0.7 各一句话概括 | B 对 V0.2–V0.7 各自扩写为完整章节（含验收标准），主题一一对应（见 §2.2(c) 表） | **保留主干 + 扩写** |
| 6 | 旧2 无 | — | B 新增 V0.8（Provider/Agent Adapter Productization）、V0.9（Authority/External Effect Safety Hardening）、V0.10（Multi-Worker）、V0.11（Production Capability Expansion）、V1.0（Self-hosted Iteration）专章及"最终版本依赖关系""Task 的最终原子模板" | **新增** |
| 7 | 旧2 §26–§30（行 1296–1752） | 网页会话生命周期、O 不接 Runtime、"你本人要做的十七步"、启动组织（非"三会话两连接"）、当前明确不要做的事情 | 全部删除（操作层内容不入路线文档） | **删除** |
| 8 | 旧2 末节 §31（行 1817–1821） | "一句话冻结：> **现在先建立 O 和 Stage 0 Reviewer，用千问负责"看懂旧工程"，WorkBuddy 负责"证明旧工程"，R 负责"审它能不能成为基线"，O 负责"正式接受基线"；Stage 0 PASS 后再创建 …** 这就是当前正式施工顺序。" | B 结尾："现在这版我认为已经可以作为**执衡正式施工路线的 Canonical Roadmap v1**……> **不再继续设计 V0.2～V1.0。先把 Stage 0 压缩完成，然后正式开 `V0.1 Candidate`。** 这一次确实应该开始往"东西越来越能用"走了，而不是"定义越来越完整"。" | **改写**（冻结句从"组织谁先建"改为"路线已冻结、开干"） |
| 9 | B 全文（形态） | 无空围栏现象 | 68 处空代码围栏对 | 转换伪影（备考） |

## 4. 推断版本谱系

```
【谱系一】(VERIFIED)
  粘贴的 markdown (1)。md(20260823-062413)  [08-23 粘贴快照, 37365B]
        ≡ 同一文本（仅差末尾 1 个 LF）
  执衡_最终定义_FINAL_CANONICAL.md (A)       [定稿, 37366B]
  → 旧1 是 A 的无尾随换行抄本；A 无实质修订。

【谱系二】(INFERRED，关键证据点 VERIFIED)
  会话原始答案"修订结论/执行顺序规划"(问答体, 31+1 节)  ←— 粘贴的 markdown (2)。md 为其存档
        │  修订性质：重构 + 净化 + 扩充
        ▼
  执衡施工总路线 v2 纯净版 (B)
  → B 相对旧2：删除全部角色/会话操作内容（千问/WorkBuddy/TRAE/Ralph/Router Bootstrap），
    新增 Stage 0.1–0.4 分解、V0.1 五个最小内核、V0.8–V1.0 专章与依赖关系/原子模板；
    V0.2–V0.7 版本主干语义一一保留。
  → 时间序推断：旧2 记录的是"执行顺序规划"会话（对应 zip：分支 · 执行顺序规划_2026-08-24），
    其 §25 自称"版本路线恢复原 Roadmap"，说明路线主干在旧2 之前已经成形；
    B 是其后对路线做净化定稿（v2）的产物。时间先后与中间版本待 Z3 会话导出交叉验证。
```

证据等级总表：

| 结论 | 等级 |
|------|------|
| A/B SHA256 与登记值一致 | VERIFIED |
| 旧1 ≡ A（仅差末尾 LF） | VERIFIED |
| 旧2 与 B 非逐字先后抄本（ratio 0.1287） | VERIFIED |
| 旧2 = 问答体修订结论存档；B = 重构纯净版 | INFERRED |
| B 相对旧2 的"删角色/会话、增 Stage 0.x 与 V0.8–V1.0、保 V0.2–V0.7 主干"修订性质 | INFERRED（各证据点 VERIFIED） |
| 旧2 早于 B | INFERRED（待 Z3 交叉验证） |

## 5. 方法与覆盖面声明

- 全部 4 个文件均做了 SHA256、字节数、LF 行数统计（Python，完整读入）。
- 两对文件均做了 difflib 全文 diff（统一 LF，`autojunk=False`），非抽样。
- 关键词频次表基于全文计数，非抽样。
- 未修改任何素材文件；本表为唯一产出。
