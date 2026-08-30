# 融合资源池接入索引（Fusion Access）

> 用途：执衡系统融合资源池中与生产链路直接相关的本地项目的**接入方式**登记。
> 维护：2026-08-29 恢复控制会话。纪律：生产在用设施零改动，只登记接入方式。
> 依据：docs/asset-registry/FUSION_ASSESSMENT_FINAL.md（13 候选融合评估）。

## 接入方式速查

| 项目 | 位置 | 接入执衡的方式 | 状态 |
|---|---|---|---|
| catpaw-longcat-proxy | `E:\WB\tools\catpaw-longcat-proxy\` | 反代服务，端口 32177；9 模型 API；执衡经其访问模型能力 | LIVE_PASS，PID 22944，零改动 |
| ChatGPT_Codex_Bridge | `E:\AI_Projects\ChatGPT_Codex_Bridge\` | `dist\server.js` 运行中；Codex 隧道/tunnel-profiles/codex-runner | 运行中，零改动 |
| windows-mcp-runtime | `E:\WB\tools\windows-mcp-runtime\` | 本地 MCP 运行时（136MB），供本地工具接入 | 登记，零改动 |
| bsk-file-bridge | `E:\WB\tools\bsk-file-bridge\` | bsk daemon（WS 52900）+ chatgpt_bridge 封装，R 审查通道 | 生产现役 |
| BrowserSkill 备份 | `E:\WB\tools\BrowserSkill_0.1.10_OFFLINE_BACKUP\` | 浏览器自动化能力备份 | 备份，零改动 |
| DeepSeek Harness | `E:\AI_Projects\DeepSeek\deepseek-harness\` | 融合评估 F-08：Adapt 档，待业主裁决后接入 | 待裁决 |

## 接入纪律（章程 §7）

1. 生产在用设施（catpaw、Runtime、桥）**只登记零改动**，不修改其运行配置。
2. 大文件/二进制不入 git；凭据样文件（proxy-key.dpapi、tunnel-profiles、runtime\secrets）仅登记路径。
3. 融合评估结论见 `docs/asset-registry/FUSION_ASSESSMENT_FINAL.md`（Reuse 5 / Adapt 4 / Compose 2 / Build 2）。
4. P0 融合候选：catpaw / Codex_Bridge / open-kimi-ppt / windows-mcp-runtime / BrowserSkill / DeepSeekHarness / 00_HOME / 资产台账。

## 待业主裁决（融合相关）

- F-08：deepseek-harness 是否纳入（Adapt 档）
- G-2：路线图详版（`ROADMAP-V0.9到V1.0收口路线.md`）是否入仓
- P0 备份排期：证据库/runs/snapshots/浏览器配置/control.db 等 7 项
