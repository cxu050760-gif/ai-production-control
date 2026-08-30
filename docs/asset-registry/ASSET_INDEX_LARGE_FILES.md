# ASSET_INDEX_LARGE_FILES — 不入 git 的大资产索引（流 B · B-1）

> 生成：2026-08-29（会话日）· 产出人：许清楚（PM，流 B）
> 目的：登记**不入 git** 的大资产（目录/文件），供备份与后续流检索。仅路径+规模+处置建议，**未读内容**。
> 取数：FREEZE_SNAPSHOT.md（2026-08-29 22:03 +08:00）；大小/文件数为实测或引用审计（标注【审】）。
> 索引人：许清楚（PM，流 B）。

---

## 1. 大资产索引表（按大小降序）

| 路径 | 大小 | 文件数 | 是否需备份 | 分类 | 备注 |
|------|------|--------|-----------|------|------|
| `E:\WB\state\ai-production-control`（全根） | 418 MB | 10881 | **是** | 相关（②状态基座） | 含 runtime/relay/browser 全部事实源 |
| `E:\执衡`（全根） | 323 MB | 7625 | **是** | 相关（③主目录） | 含 04_测试证据 |
| `E:\执衡\04_测试证据` | 200 MB | 1022 | **是（唯一副本证据）** | 相关（③主目录） | 证据库，不可重建 |
| └ `04_测试证据\webmodel_delivery` | 170 MB | 606 | **是** | 相关 | 最大单子目录 |
| └ `04_测试证据\webmodel_lab` | 28 MB | 243 | 是（证据） | 相关 | — |
| `E:\WB\state\...\runtime-v1` | 32 MB | 3841 | **是（唯一副本）** | 相关（②状态基座） | 109/110 RUN 事实源 |
| `E:\WB\state\...\construction-relay` | 23 MB | 1691 | **是（唯一副本）** | 相关（②状态基座） | O/C 轮转记录 |
| `C:\Users\17838\.workbuddy\traces` | 1584 MB【审】 | 5265【审】 | 否（域外） | 无关（B-08） | 一条未读 |
| `E:\AI_Projects\AI_Video_Automation` | 1.9 GB | 数千 | 否（域外） | 无关（B-03） | — |
| `E:\WB\tools\bsk-file-bridge` | ~3.4 GB【审】 | 数千 | **建议** | 相关（A-31，工具） | 最大工具，唯一副本 |
| `E:\AI_Projects\Novel_Download_Hub` | 458 MB | 数千 | 否（域外） | 无关（B-04） | — |
| `E:\DeepSeekHarness\2026.8.16.15.28` | 541 MB | 数千 | 建议（各有 .git） | 相关（A-30） | 3 应用+hy3 |
| `E:\AI_Projects\open-kimi-ppt-skill` | 263 MB | 数百 | 否（可重建） | 相关（A-29） | — |
| `E:\AI_Projects\OpenWrite_Local` | 136 MB | 7508【审】 | 否（有备份目录） | 相关（A-26） | — |
| `E:\WB\tools\windows-mcp-runtime` | 136 MB【审】 | 数十 | 否（可重建） | 相关（A-33） | — |
| `E:\AI_Projects\ChatGPT_Codex_Bridge` | 106 MB | 数十 | 否（可重建） | 相关（A-28） | — |
| `C:\Users\17838\.codex\sessions` | 169.7 MB【审】 | 114【审】 | 否（域外） | 无关（B-09） | — |
| `E:\AI_Projects\OpenWrite_Analysis` | 51 MB | 数十 | 否 | 相关（A-36） | — |
| `E:\AI_Projects\个人内容账号_时代观察` | 28 MB | 小 | 否 | 无关（B-05） | — |
| `E:\WB\state\...\construction-relay\role-runs` | 6.0 MB | — | 是（唯一副本） | 相关（A-07） | 65 ROLE |
| `E:\WB\state\...\runtime-v1\runs` | 2.4 MB | 645 | **是（唯一副本）** | 相关（A-05） | 110 RUN |
| `E:\WB\state\...\control.db` | 966 KB | 1 | **是（唯一副本，用途存疑 D-01）** | 存疑（D-01） | 未读内容 |
| `E:\WB\state\...\browser-auth-profile-v1` | 小（17~18 项） | 17~18 | **是（登录态唯一）** | 相关（A-10，敏感） | 未读内容 |
| `E:\WB\state\...\browser-auth-profile-v2` | 小（17 项） | 17 | **是（登录态唯一）** | 相关（A-10，敏感） | 未读内容 |
| `E:\WB\state\...\browser-cli-doctor` / `lab` | 小（14~16 项） | 14~16 | 建议 | 相关（A-12，敏感 Cookies） | 未读内容 |
| `E:\WB\tools\catpaw-longcat-proxy` | 1.2 MB | 121 | 有备份（backups 5 点） | 相关（A-24） | 生产反代 |
| `E:\WB\outputs\ai-production-control` | 7.4 MB | 98 | 否（可重建） | 相关（④输出根） | 含本批产出 |

## 2. 备份优先级建议

| 优先级 | 资产 | 理由 |
|--------|------|------|
| P0（最先备份） | 04_测试证据、runtime-v1\runs、construction-relay、snapshots、browser-auth-profile-v1/v2、会话注册.json、proxy-key.dpapi、control.db | 唯一副本/登录态/密钥/用途存疑，丢失即事实或凭据丢失 |
| P1（建议备份） | bsk-file-bridge、DeepSeekHarness 3 应用、catpaw（已有 backups 可加固） | 大工具/多应用，重建成本高 |
| P2（可重建，不必备份） | 其余 AI_Projects、outputs、traces、codex-sessions | git 或可再生成 |

## 3. 索引人

- 索引人：许清楚（PM，流 B），2026-08-29
- 复核建议：由流 A / 业主在备份计划阶段复核 P0 清单。

*大文件索引 · 流 B B-1 · 2026-08-29*
