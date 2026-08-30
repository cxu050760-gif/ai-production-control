# FUSION_ASSESSMENT_FINAL — 融合评估正式版（流 B · B-2）

> 生成：2026-08-29（会话日）· 产出人：许清楚（PM，流 B）
> 上游：草案 §6 融合候选（Reuse 5 / Adapt 4 / Compose 2 / Build 2 = **13 项**）；正式盘点表 `ASSET_INVENTORY_FINAL.md`（A-01..A-38）。
> 门禁语义（章程 Reuse 硬门禁）：**能复用不重写、能适配不改写、能组合不新建**；档位判定 = 满足更高档则取更高档。
> 纪律：只读；大目录不深读；凭据零读取；不写 worktree。本文件为流 B B-2 唯一产出。

---

## 1. 门禁判定依据要点

| 档位 | 判定依据 |
|------|---------|
| **Reuse**（直接复用） | 资产**可直接被执衡调用或服务**，零/近零改动即接入（如 catpaw 反代、Codex_Bridge） |
| **Adapt**（适配复用） | 功能近似但**需小幅改造**（配置/契约/工作区核对）后接入（如 OpenWrite_Local、deepseek-harness） |
| **Compose**（组合复用） | 不改代码，**组合复用其方法论/脚本/文档**形成新能力（如 00_HOME 文档体系） |
| **Build**（仅借鉴需自建） | 无现成可复用，**仅借鉴模式、须自建**（如资产台账、browser-cli 标准化） |

---

## 2. 13 候选融合评估表

| # | 候选 | 路径 | 性质一句话 | 门禁判定 | 判定理由 | 融合决策 | 对接面（§3） |
|---|------|------|-----------|---------|---------|---------|-------------|
| F-01 | catpaw-longcat-proxy | `E:\WB\tools\catpaw-longcat-proxy`（121/1.2MB，端口 32177 LIVE_PASS） | 生产反代（9 模型 LongCat-2.0） | **Reuse** | 已生产验证、零改动登记即可被执衡调用；复用成本最低，符合"能复用不重写"；敏感点仅 proxy-key.dpapi（只登记不读）。 | **纳入融合资源池** | ⑤接入设施（生产在用，保持零改动） |
| F-02 | ChatGPT_Codex_Bridge | `E:\AI_Projects\ChatGPT_Codex_Bridge`（106MB） | Codex Bridge 隧道 + codex-runner | **Reuse** | 已有 tunnel-profiles 与 codex-runner，8-28 仍活跃；可直接作接入通道服务执衡 B/R 链路，无需改造。 | **纳入融合资源池** | ⑤接入设施 / ⑥本地项目（接入候选） |
| F-03 | open-kimi-ppt-skill | `E:\AI_Projects\open-kimi-ppt-skill`（263MB） | 成熟 PPT 生成 skill（含本地编辑器） | **Reuse** | 可直接作为内容产出能力被调用；含编辑器与 bin 工具链，接口完整，无需重写。 | **纳入融合资源池** | ⑥本地项目（融合候选）→ 能力层供③执衡调用 |
| F-04 | windows-mcp-runtime | `E:\WB\tools\windows-mcp-runtime`（136MB） | Windows MCP 运行时 | **Reuse** | 现成运行时可直接挂接，执衡 Worker/工具链可经 MCP 调用；零改造。 | **纳入融合资源池** | ⑤接入设施（MCP 运行时） |
| F-05 | BrowserSkill_0.1.10_OFFLINE_BACKUP | `E:\WB\tools\BrowserSkill_0.1.10_OFFLINE_BACKUP` | 浏览器 skill 离线备份 | **Reuse** | 离线即用，可作为浏览器能力离线恢复点/基线；与 F-13 标准化的关系需在敏感处置后梳理，但本身直接可用。 | **纳入融合资源池** | ⑤接入设施 / ②状态基座 browser-* |
| F-06 | OpenWrite_Local | `E:\AI_Projects\OpenWrite_Local`（7508/136MB） | 写作执行器体系 | **Adapt** | 功能近似内容执行 Worker，但需小幅改造（先核对内容工作区、executors 配置透传）；符合"能适配不改写"。 | **纳入融合资源池（条件：先完成内容工作区核对）** | ⑥本地项目 → 能力 Worker（内容执行） |
| F-07 | YongZhao_Writer_Core | `E:\AI_Projects\YongZhao_Writer_Core`（72KB） | 永昭写作核心（novel-writer skill） | **Adapt** | 已 SKILL 化但需验证与执衡 Worker 契约（R 链路/证据绑定）兼容后适配；小幅改造。 | **纳入融合资源池（条件：Worker 契约兼容验证）** | ⑥本地项目 → 能力 Worker（写作） |
| F-08 | deepseek-harness | `E:\AI_Projects\DeepSeek\deepseek-harness`（7412/181MB） | DeepSeek Harness 执行框架 | **Adapt** | 7412 文件工程，执行框架可复用但需适配为执衡 DeepSeek 接入执行器；涉及外部模型接入策略与可能的凭据面，**建议业主裁决接入范围**。 | **待业主裁决（条件：确认接入范围与凭据策略）** | ⑤接入设施（DeepSeek 接入） |
| F-09 | Trae-Ralph | `E:\WB\tools\Trae-Ralph` | 自动续跑工具 | **Adapt** | 续跑机制可能重复 construction-relay/watchdog 现有能力；需先与 relay 现状对照避免重复建设，条件满足后再纳入。 | **暂不纳入（条件：与 construction-relay/watchdog 对照确认非重复后）** | ②状态基座 construction-relay（若纳入） |
| F-10 | DeepSeekHarness 3 应用 | `E:\DeepSeekHarness\2026.8.16.15.28\{apartment404,devour-evolution,zhutian-lvren}`（541MB 含 hy3） | 3 个独立交付应用 | **Compose** | 3 应用各自独立（均有 .git），不改代码，组合其运行脚本/文档即可形成多场景演示/验收矩阵；符合"能组合不新建"。 | **纳入融合资源池** | ⑥本地项目 → 验收/演示能力（供 04_测试证据 扩展） |
| F-11 | E:\ChatGPT\00_HOME 文档体系 | `E:\ChatGPT\00_HOME` | CLI/工具链文档体系 | **Compose** | CODEX_PARALLEL_GUIDE + CAPABILITY_MAP + TOOLCHAIN 等组合为操作手册底稿；纯文档组合，零代码风险。 | **纳入融合资源池** | ③执衡 00_先看这里（手册底稿） |
| F-12 | 资产台账（自建） | `E:\WB\outputs\...\stream-b\ASSET_INVENTORY_FINAL.md` | 权威资产台账 | **Build** | 现有盘点全过时（审计陷阱 9），无现成可复用，须以台账为底自建权威清单；**本流已执行（正式盘点表已转正）**。 | **纳入（已完成）** | ③执衡 / ④输出根（治理产物） |
| F-13 | browser-cli-* 系列标准化 | `...\browser-cli-benchmark`、`doctor`、`lab` | 统一浏览器 CLI 基座 | **Build** | 现有 benchmark/doctor/lab 分散且含敏感登录态（Cookies），需先确定敏感处置与轮换策略后再自建统一基座；避免与 F-05 重复。 | **暂不纳入（条件：browser-auth 敏感处置与业主轮换决策完成后）** | ②状态基座 browser-* |

---

## 3. 覆盖面对比（草案 13 候选 vs 正式盘点表 A-xx）

| 候选 | 正式盘点表覆盖 | 覆盖说明 |
|------|---------------|---------|
| F-01 catpaw | **A-24**（catpaw 全量）+ **A-25**（proxy-key.dpapi 敏感） | 已在盘点覆盖 |
| F-02 Codex_Bridge | **A-28** | 已在盘点覆盖 |
| F-03 open-kimi-ppt-skill | **A-29** | 已在盘点覆盖 |
| F-04 windows-mcp-runtime | **A-33** | 已在盘点覆盖 |
| F-05 BrowserSkill 备份 | **A-34** | 已在盘点覆盖 |
| F-06 OpenWrite_Local | **A-26**（+ A-38 备份目录） | 已在盘点覆盖 |
| F-07 YongZhao_Writer_Core | **A-37** | 已在盘点覆盖 |
| F-08 deepseek-harness | **A-27** | 已在盘点覆盖 |
| F-09 Trae-Ralph | **A-32** | 已在盘点覆盖 |
| F-10 DeepSeekHarness 3 应用 | **A-30** | 已在盘点覆盖 |
| F-11 00_HOME 文档体系 | **A-35** | 已在盘点覆盖 |
| F-12 资产台账 | **无直接 A-xx**（治理产出 = 盘点表本身） | **盘点上新增（治理层）** |
| F-13 browser-cli 标准化 | **A-10**（auth-profile）+ **A-11**（benchmark）+ **A-12**（doctor/lab） | 资产已覆盖；标准化动作为**盘点上新增（治理层）** |

**一致性说明**：
- **11/13 候选**在正式盘点表 A-01..A-38 中有直接资产条目覆盖，两表无冲突。
- **2/13 候选**（F-12 资产台账、F-13 browser-cli 标准化）为**治理层动作**而非独立资产：F-12 即本盘点产物本身；F-13 的底层资产（A-10/A-11/A-12）已在盘点覆盖，标准化是后续治理动作。
- 正式盘点表中另有非融合候选的相关资产（如 A-04 runtime-v1、A-06 construction-relay、A-17 04_测试证据 等系统本体）不属于融合资源池范畴，二者口径不重叠。

---

## 4. 决策记录（每项一行：判定 + 决策摘要 + 证据路径）

| # | 判定 | 决策摘要 | 证据路径 |
|---|------|---------|---------|
| F-01 | Reuse | 纳入：零改动接入生产反代 | 草案 §6 Reuse 1；盘点 A-24/A-25 |
| F-02 | Reuse | 纳入：直接作接入通道 | 草案 §6 Reuse 2；盘点 A-28 |
| F-03 | Reuse | 纳入：直接作内容产出能力 | 草案 §6 Reuse 3；盘点 A-29 |
| F-04 | Reuse | 纳入：直接挂接 MCP 运行时 | 草案 §6 Reuse 4；盘点 A-33 |
| F-05 | Reuse | 纳入：离线浏览器能力基线 | 草案 §6 Reuse 5；盘点 A-34 |
| F-06 | Adapt | 纳入（条件：内容工作区核对） | 草案 §6 Adapt 1；盘点 A-26/A-38 |
| F-07 | Adapt | 纳入（条件：Worker 契约兼容验证） | 草案 §6 Adapt 2；盘点 A-37 |
| F-08 | Adapt | 待业主裁决（接入范围/凭据策略） | 草案 §6 Adapt 3；盘点 A-27 |
| F-09 | Adapt | 暂不纳入（与 relay/watchdog 对照后） | 草案 §6 Adapt 4；盘点 A-32 |
| F-10 | Compose | 纳入：组合为验收/演示矩阵 | 草案 §6 Compose 1；盘点 A-30 |
| F-11 | Compose | 纳入：组合为操作手册底稿 | 草案 §6 Compose 2；盘点 A-35 |
| F-12 | Build | 纳入（已完成）：权威资产台账 | 草案 §6 Build 1；盘点=本表 |
| F-13 | Build | 暂不纳入（敏感处置前置） | 草案 §6 Build 2；盘点 A-10/A-11/A-12 |

---

## 5. 融合建议优先级

### P0（建议近期纳入，零/低成本直接可用）
1. **F-01 catpaw**（Reuse，生产反代零改动）
2. **F-02 ChatGPT_Codex_Bridge**（Reuse，接入通道现成）
3. **F-03 open-kimi-ppt-skill**（Reuse，内容产出能力现成）
4. **F-04 windows-mcp-runtime**（Reuse，MCP 运行时现成）
5. **F-05 BrowserSkill 离线备份**（Reuse，浏览器能力基线）
6. **F-10 DeepSeekHarness 3 应用**（Compose，组合为验收矩阵）
7. **F-11 00_HOME 文档体系**（Compose，组合为手册底稿）
8. **F-12 资产台账**（Build，已完成，转为维护态）

### P1（条件纳入，需先满足前置条件）
1. **F-06 OpenWrite_Local**（条件：内容工作区核对）
2. **F-07 YongZhao_Writer_Core**（条件：Worker 契约兼容验证）
3. **F-08 deepseek-harness**（条件：业主裁决接入范围与凭据策略）

### P2（观察，暂缓或待条件成熟）
1. **F-09 Trae-Ralph**（观察：与 construction-relay/watchdog 对照确认非重复）
2. **F-13 browser-cli 标准化**（观察：browser-auth 敏感处置与轮换决策完成后）

---

## 6. 红线与一致性

- 只读；大目录不深读；凭据零读取零复制；不写 worktree；唯一产出本文件。
- 判定分布：**Reuse 5 / Adapt 4 / Compose 2 / Build 2**（与草案一致，无档位漂移）。
- 决策分布：纳入 10 项（含 F-12 已完成）、暂不纳入 2 项（F-09/F-13）、待业主裁决 1 项（F-08）。

*融合评估正式版 · 流 B B-2 · 2026-08-29*
