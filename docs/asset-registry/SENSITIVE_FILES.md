# SENSITIVE_FILES — 敏感文件清单（流 B · B-1）

> 生成：2026-08-29（会话日）· 产出人：许清楚（PM，流 B）
> **纪律：以下文件全部未读取内容，零复制入本文件/任何产出。**
> 处置建议三档：**只登记**（记录存在，不动）/ **需备份**（唯一副本/登录态，建议纳入备份）/ **需轮换**（凭据可能过期或泄露，建议业主评估轮换）。
> 索引人：许清楚（PM，流 B）。

---

## 1. 敏感文件/目录清单

| # | 类别 | 路径 | 处置建议 | 备注 |
|---|------|------|---------|------|
| S-01 | 会话注册 | `E:\执衡\05_资源\会话注册.json`（10.8 KB） | **只登记 + 需备份** | R-PROD 会话权威；唯一副本 |
| S-02 | 浏览器登录态 | `E:\WB\state\ai-production-control\browser-auth-profile-v1\` | **需备份 + 需轮换评估** | Chromium Profile（Cookies/Trust Tokens）；登录态可能过期 |
| S-03 | 浏览器登录态 | `E:\WB\state\ai-production-control\browser-auth-profile-v2\` | **需备份 + 需轮换评估** | 同 S-02 |
| S-04 | 浏览器 CLI Cookies | `E:\WB\state\ai-production-control\browser-cli-doctor\Default\Network\Cookies` 等 | 只登记（实验基线） | 与 browser-cli-doctor/lab 目录同体 |
| S-05 | 浏览器 CLI Cookies | `E:\WB\state\ai-production-control\browser-cli-lab\Default\Network\Cookies` 等 | 只登记（实验基线） | 同 S-04 |
| S-06 | 代理密钥 | `E:\WB\tools\catpaw-longcat-proxy\runtime\proxy-key.dpapi`（588 B） | **需备份 + 需轮换评估** | DPAPI 加密，仅本机可解；生产反代凭据 |
| S-07 | 仓库配置 | `C:\Users\17838\Documents\QoderCN\2026-08-28\chat-1\ai-production-control\config\production.json`（2.1 KB） | **只登记** | 未读内容；git 内配置，建议确认是否含密钥并评估轮换 |
| S-08 | 疑似凭据样文件（仅路径登记） | `...\ai-production-control\.github\workflows\v09-authority-effect-verify.yml`、`...\runtime\fixtures\v09_authority_effect_attack_cases.json`、`...\runtime\v09_authority_effect_evidence.py`、`E:\WB\state\...\construction-relay\bindings\authority-arbiter.json`、`E:\执衡\00_先看这里\能力操作手册_20260820\05_DOCUMENT_AUTHORITY_MAP.md` | **只登记** | 文件名含 authority/auth/evidence 关键词，未读内容，按需由授权方核 |
| S-09 | 公开上传标记 | `E:\WB\state\ai-production-control\browser-cli-public-upload.txt`（33 B） | **只登记** | 内容未读；疑似公开链接（存疑 D-04） |

## 2. 处置总原则

1. **零读取零复制**：本清单仅路径 + 元信息（大小），不含任何内容。
2. **需要备份的**（S-01/S-02/S-03/S-06）：纳入 P0 备份（见 ASSET_INDEX_LARGE_FILES.md §2）。
3. **需要轮换评估的**（S-02/S-03/S-06/S-07）：登录态与密钥可能过期/轮换周期未定，建议由业主决定轮换策略；本流不发起任何轮换。
4. **只登记的**：保持不动，仅记录存在。
5. 任何后续流如需读取/使用上述文件，**必须经业主授权**，并在产出中继续遵守"不复制内容"纪律。

*敏感文件清单 · 流 B B-1 · 2026-08-29 · 全部未读内容*
