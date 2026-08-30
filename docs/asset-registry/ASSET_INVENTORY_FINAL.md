# ASSET_INVENTORY_FINAL — 执衡系统资产正式盘点表（流 B · B-1 转正）

> 生成：2026-08-29（会话日）· 产出人：许清楚（PM，流 B）
> 状态：**正式版**（由 ASSET_INVENTORY_DRAFT.md 转正；取数冻结基线见 FREEZE_SNAPSHOT.md，取数时间 2026-08-29 22:03 +08:00）
> 上游依据：`E:\WB\docs\ZHIHENG_ANTI_MISLEADING_HANDOFF_20260828.md`（审计，起点地图非权威清单）；章程 §3 六大组成；草案 D1–D9 存疑登记。
> 纪律：**只读**；大目录仅列；凭据内容零读取零复制；不写 worktree；证据不足标 UNVERIFIED 不猜。

---

## 1. 覆盖面声明（三级，如实）

| 级别 | 范围 | 涉及资产 |
|------|------|---------|
| **全量读** | 审计报告全文；catpaw 端口/进程只读探测；本盘点全部目录级 `ls/find/du/stat` 输出 | 必读起点、catpaw、各资产目录结构 |
| **抽样读** | 审计已实测部分（109/110 RUN 统计、66/65 轮 O/C、catpaw HANDOFF_REPORT 全文、00_先看这里 手册）——经审计背书 | runtime-v1 runs、construction-relay、catpaw 交接、00_先看这里 |
| **仅列目录** | 未读内容的大目录/项目集/凭据目录 | AI_Projects、DeepSeekHarness、bsk-file-bridge、04_测试证据、browser-auth-profile-*、会话注册.json 等 |

**深读覆盖率仍 ≤1/3**（继承审计 + 草案结论）。本表为目录级权威清单，非内容级权威清单。

---

## 2. 三档分类总表（A-相关 / B-无关 / D-存疑，逐项编号）

### 2.1 相关（A-xx，收束纳入系统范围）

| ID | 资产 | 路径 | 归属（§3） | 恢复路径 | 覆盖 | 敏感 |
|----|------|------|-----------|---------|------|------|
| A-01 | GitHub 远端（权威） | `cxu050760-gif/ai-production-control`（私有） | ①仓库 | 唯一远端；本地可 clone | 仅列目录 | 否 |
| A-02 | 活跃副本（当前施工） | `C:\Users\17838\Documents\QoderCN\2026-08-28\chat-1\ai-production-control` | ①仓库 | 可重建（git fetch/clone） | 仅列目录 | 含 config/production.json（见 SENSITIVE） |
| A-03 | 旧副本（8-23） | `E:\WB\tools\ai-production-control` | ①仓库 | 可重建（git） | 仅列目录 | 否 |
| A-04 | runtime-v1 全量 | `E:\WB\state\...\runtime-v1`（3841 文件/32MB） | ②状态基座 | **唯一副本** | 抽样读 | 否 |
| A-05 | runtime-v1\runs | `...\runtime-v1\runs`（110 RUN/645 文件/2.4MB） | ②状态基座 | **唯一副本**（最硬事实源） | 抽样读 | 否 |
| A-06 | construction-relay | `...\construction-relay`（1691 文件/23MB） | ②状态基座 | **唯一副本** | 抽样读 | 否 |
| A-07 | construction-relay\role-runs | `...\role-runs`（65 ROLE/6.0MB） | ②状态基座 | **唯一副本** | 仅列目录 | 否 |
| A-08 | acceptance-fixtures | `...\acceptance-fixtures`（9 task-*） | ②状态基座 | 可重建（测试生成） | 仅列目录 | 否 |
| A-09 | snapshots | `...\snapshots`（30 revision-*.json） | ②状态基座 | **唯一副本**（证据） | 仅列目录 | 否 |
| A-10 | browser-auth-profile-v1/v2 | `...\browser-auth-profile-v1`、`v2` | ②状态基座 | **唯一副本**（登录态） | 仅列目录 | **是（未读）** |
| A-11 | browser-cli-benchmark | `...\browser-cli-benchmark` | ②状态基座 | 可重建 | 仅列目录 | 否 |
| A-12 | browser-cli-doctor/lab | `...\browser-cli-doctor`、`lab` | ②状态基座 | 可重建（含 Cookies 敏感） | 仅列目录 | **是（未读）** |
| A-13 | 00_先看这里 | `E:\执衡\00_先看这里`（10+7 文件） | ③执衡主目录 | 可重建（部分唯一） | 抽样读 | 否 |
| A-14 | 01_当前产品/webmodel | `E:\执衡\01_当前产品\webmodel` | ③执衡主目录 | 可重建（脚本+state） | 仅列目录 | 否 |
| A-15 | 02_正在开发 | `E:\执衡\02_正在开发`（wb_agg/wb_index/browser_resource/guardrail_g1 等） | ③执衡主目录 | 可重建；HUMAN_CORRECTION_LEDGER 唯一 | 仅列目录 | 否 |
| A-16 | 03_参考项目 | `E:\执衡\03_参考项目`（upstream + 复用判断.md） | ③执衡主目录 | 可重建/上游 fetch | 仅列目录 | 否 |
| A-17 | 04_测试证据 | `E:\执衡\04_测试证据`（1022 文件/200MB） | ③执衡主目录 | **唯一副本**（证据） | 仅列目录 | 否 |
| A-18 | 05_资源 | `E:\执衡\05_资源`（会话注册.json + 现有资源总表.md） | ③执衡主目录 | 会话注册.json **唯一副本** | 仅列目录 | **是（未读）** |
| A-19 | 根级脚本/交接文档 | `E:\执衡\` 根（交接.md、fix_*.py、create_evidence*.py 等 19 项） | ③执衡主目录 | 可重建；唯一副本 | 仅列目录 | 否 |
| A-20 | outputs\evidence | `E:\WB\outputs\...\evidence`（11 task-*） | ④输出根 | 可重建（运行时产物） | 仅列目录 | 否 |
| A-21 | outputs\tasks | `E:\WB\outputs\...\tasks`（21 条目） | ④输出根 | 可重建 | 仅列目录 | 否 |
| A-22 | outputs\stream-e / stream-zero | `E:\WB\outputs\...\stream-e`、`stream-zero` | ④输出根 | 可重建 | 仅列目录 | 否 |
| A-23 | outputs 顶层证据 | `acceptance-run-latest.json`、`v2-login-check.png` | ④输出根 | 可重建 | 仅列目录 | 否 |
| A-24 | catpaw 全量 | `E:\WB\tools\catpaw-longcat-proxy`（121 文件/1.2MB，端口 32177 LIVE_PASS） | ⑤接入设施 | **有备份**（backups/before-* 5 点） | 全量读+端口实测 | 否 |
| A-25 | catpaw 密钥 | `...\runtime\proxy-key.dpapi` | ⑤接入设施 | **唯一副本** | 仅列目录 | **是（未读）** |
| A-26 | OpenWrite_Local | `E:\AI_Projects\OpenWrite_Local`（7508 文件/136MB） | ⑥本地项目（融合候选） | 有备份目录 | 仅列目录 | 否 |
| A-27 | deepseek-harness | `E:\AI_Projects\DeepSeek\deepseek-harness`（7412 文件/181MB 含 DeepSeek 目录） | ⑥本地项目（接入候选） | 可重建（clone） | 仅列目录 | 否 |
| A-28 | ChatGPT_Codex_Bridge | `E:\AI_Projects\ChatGPT_Codex_Bridge`（106MB） | ⑥本地项目（接入候选） | 可重建 | 仅列目录 | 否 |
| A-29 | open-kimi-ppt-skill | `E:\AI_Projects\open-kimi-ppt-skill`（263MB） | ⑥本地项目（融合候选） | 可重建 | 仅列目录 | 否 |
| A-30 | DeepSeekHarness 3 应用 | `E:\DeepSeekHarness\2026.8.16.15.28\{apartment404,devour-evolution,zhutian-lvren}`（541MB 含 hy3） | ⑥本地项目（融合候选） | 各自有 .git | 仅列目录 | 否 |
| A-31 | bsk-file-bridge | `E:\WB\tools\bsk-file-bridge`（~3.4GB 最大工具） | ⑥本地项目（工具候选） | **唯一副本**（无备份） | 仅列目录 | 否 |
| A-32 | Trae-Ralph | `E:\WB\tools\Trae-Ralph` | ⑥本地项目（工具候选） | 可重建 | 仅列目录 | 否 |
| A-33 | windows-mcp-runtime | `E:\WB\tools\windows-mcp-runtime`（136MB） | ⑥本地项目（工具候选） | 可重建 | 仅列目录 | 否 |
| A-34 | BrowserSkill 离线备份 | `E:\WB\tools\BrowserSkill_0.1.10_OFFLINE_BACKUP` | ⑥本地项目（工具候选） | 备份 | 仅列目录 | 否 |
| A-35 | E:\ChatGPT\00_HOME 文档体系 | `E:\ChatGPT\00_HOME`（CODEX_PARALLEL_GUIDE 等） | ⑥本地项目（文档候选） | 可重建 | 仅列目录 | 否 |
| A-36 | OpenWrite_Analysis | `E:\AI_Projects\OpenWrite_Analysis`（51MB） | ⑥本地项目（融合候选） | 可重建 | 仅列目录 | 否 |
| A-37 | YongZhao_Writer_Core | `E:\AI_Projects\YongZhao_Writer_Core`（72KB） | ⑥本地项目（融合候选） | 可重建 | 仅列目录 | 否 |
| A-38 | OpenWrite_Local 备份目录 | `E:\AI_Projects\OpenWrite_Local_backup_before_content_workspace` | ⑥本地项目（备份） | 备份=恢复路径 | 仅列目录 | 否 |

### 2.2 无关（B-xx，零触碰零深读）

| ID | 资产 | 路径 | 归属（§3） | 恢复路径 | 覆盖 |
|----|------|------|-----------|---------|------|
| B-01 | 99_历史资料（空） | `E:\执衡\99_历史资料`（0 文件） | ③执衡主目录 | — | 仅列目录 |
| B-02 | outputs\release（空） | `E:\WB\outputs\...\release`（0 文件） | ④输出根 | — | 仅列目录 |
| B-03 | AI_Video_Automation | `E:\AI_Projects\AI_Video_Automation`（1.9GB） | ⑥本地项目 | 可重建 | 仅列目录 |
| B-04 | Novel_Download_Hub | `E:\AI_Projects\Novel_Download_Hub`（458MB） | ⑥本地项目 | 可重建 | 仅列目录 |
| B-05 | 个人内容账号_时代观察 | `E:\AI_Projects\个人内容账号_时代观察`（28MB） | ⑥本地项目 | 可重建 | 仅列目录 |
| B-06 | 个人精品内容账号 | `E:\AI_Projects\个人精品内容账号`（5.3MB） | ⑥本地项目 | 可重建 | 仅列目录 |
| B-07 | clash-convert | `E:\WB\tools\clash-convert`（129KB） | ⑥本地项目 | 可重建 | 仅列目录 |
| B-08 | .workbuddy\traces | `C:\Users\17838\.workbuddy\traces`（5265/1584MB） | ⑥本地项目 | 可重建 | 仅列目录 |
| B-09 | .codex\sessions | `C:\Users\17838\.codex\sessions`（114 会话/169.7MB） | ⑥本地项目 | 可重建 | 仅列目录 |
| B-10 | n8n-video | `E:\n8n-video`（6 项） | ⑥本地项目 | 可重建 | 仅列目录 |
| B-11 | VIDEO_DIRECTOR | `E:\VIDEO_DIRECTOR`（4 项） | ⑥本地项目 | 可重建 | 仅列目录 |
| B-12 | Y2A-Auto | `E:\Y2A-Auto`（1 项） | ⑥本地项目 | 可重建 | 仅列目录 |
| B-13 | traework | `E:\traework`（2 项） | ⑥本地项目 | 可重建 | 仅列目录 |
| B-14 | AI_Test_Project | `E:\AI_Projects\AI_Test_Project` | ⑥本地项目 | 可重建 | 仅列目录 |
| B-15 | Bridge_Public_Demo | `E:\AI_Projects\Bridge_Public_Demo` | ⑥本地项目 | 可重建 | 仅列目录 |
| B-16 | Computer_Audit_20260801 | `E:\AI_Projects\Computer_Audit_20260801` | ⑥本地项目 | 可重建 | 仅列目录 |
| B-17 | Paperclip_POC | `E:\AI_Projects\Paperclip_POC` | ⑥本地项目 | 可重建 | 仅列目录 |
| B-18 | AI个人工作系统成长账号 | `E:\AI_Projects\AI个人工作系统成长账号` | ⑥本地项目 | 可重建 | 仅列目录 |

### 2.3 存疑（D-xx，记表附建议，不猜测、不阻塞）

| ID | 存疑项 | 路径 | 归属 | 状态 | 建议 |
|----|--------|------|------|------|------|
| D-01 | control.db（966KB SQLite，用途未核） | `E:\WB\state\...\control.db` | ②状态基座 | **OPEN** | 勿删勿改；由流 A/业主确认用途 |
| D-02 | 执衡自带 .git | `E:\执衡\.git` | ③执衡主目录 | **OPEN** | 与 GitHub 仓库关系未核；建议核查独立版本库 |
| D-03 | RUN/ROLE 计数差异（审计 109/66 vs 实测 110/65） | `runtime-v1\runs`、`role-runs` | ②状态基座 | **CLOSED（复核关闭）** | 冻结快照两次实测一致（110/65）；审计差异归因未核，登记为统计口径差异，不再作为阻塞项 |
| D-04 | browser-cli-public-upload.txt（33B） | `E:\WB\state\...\browser-cli-public-upload.txt` | ②状态基座 | **OPEN** | 疑似公开链接；未读；业主确认后再处置 |
| D-05 | 空目录组（99_历史资料、outputs\release） | 见 B-01/B-02 | ③/④ | **OPEN** | 确认归档或继续预留 |
| D-06 | PROJECT_FORGE | `E:\ChatGPT\02_WORKSPACES\PROJECT_FORGE` | ⑥本地项目 | **OPEN** | 审计未打开；如需涉及时专项探查 |
| D-07 | _quarantine（8 个时间戳目录） | `E:\执衡\_quarantine\` | ③执衡主目录 | **OPEN** | 被隔离临时脚本；确认清理或保留备查 |
| D-08 | workspace 对照环境 | `E:\WB\workspace\2026-*`（含 zhiheng-review/zhiheng-old） | ⑥本地项目 | **OPEN** | 审计建的测试对照环境；由流 A 决定保留/清理 |
| D-09 | construction-relay 锁/陈旧项 | `...\construction-relay\relay.lock`、`stale-locks\` | ②状态基座 | **OPEN** | 心跳最后 08-27 00:04；建议核对是否遗留未清理 |

---

## 3. 台账字段草案（正式）

```
asset_id        # A-xx / B-xx / D-xx（本表编号）
资产名          # 人类可读名称
路径            # 绝对路径
归属            # 章程 §3 六大组成（①~⑥）
文件数/大小     # 实测（冻结快照取数 2026-08-29 22:03）
性质一句话      # 用途
覆盖面          # 全量读 / 抽样读 / 仅列目录
三档分类        # 相关 / 无关 / 存疑（+状态 OPEN/CLOSED）
恢复路径        # 唯一副本 / 可重建 / 有备份（+具体备份点）
敏感标记        # 无 / 凭据 / 会话 / 密钥（涉敏一律不读不复制）
时间戳          # 根目录 mtime / 最新文件 mtime（见 FREEZE_SNAPSHOT）
备注            # 存疑建议 / 差异说明 / 复核提示
```

---

## 4. 三档计数汇总

| 档位 | 计数 | 说明 |
|------|------|------|
| 相关（A-xx） | **38** | A-01..A-38（含敏感 4 项：A-10/A-12/A-18/A-25） |
| 无关（B-xx） | **18** | B-01..B-18（零触碰零深读） |
| 存疑（D-xx） | **9** | D-01..D-09（1 项 CLOSED：D-03；8 项 OPEN） |
| **合计** | **65** | — |

---

## 5. 与冻结快照的一致性

- 本表计数、大小、mtime 均以 `FREEZE_SNAPSHOT.md`（2026-08-29 22:03 +08:00）为准。
- 若后续发现资产变化，先对比冻结快照再更新本表（避免"盘点永远过时"陷阱 9）。
- 正式版取代草案 ASSET_INVENTORY_DRAFT.md（草案保留为过程产物，不删除）。

*正式盘点表 · 流 B B-1 · 2026-08-29 · 由 ASSET_INVENTORY_DRAFT.md 转正*
