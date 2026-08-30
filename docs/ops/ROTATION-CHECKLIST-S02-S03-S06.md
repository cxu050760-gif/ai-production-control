# 凭据轮换操作清单 — S-02 / S-03 / S-06（执行主体 = 业主本人）

- 依据：主脑裁决书 `MAINBRAIN_RULING_E1-E4_BATCH.md` B11（S-02/S-03/S-06 凭据轮换：批准方向，**执行主体 = 业主本人**；施工团只产出操作清单，**不得触碰凭据本体**）
- 状态：**操作清单**（文档）。本文件不含任何凭据值、不读取凭据内容；施工团零触碰。
- 执行：recovery-controller（仅起草清单）· 2026-08-30 17:20（北京）

## 0. 总则

- 以下全部操作由**业主本人**执行（B11）；施工团/后续 AI 不得代为执行。
- 轮换前先确认 P0 备份已完成（2026-08-30 已备份，见 `docs/asset-registry/BACKUP_P0_20260830.md`）。
- 每项轮换后必须执行对应验证，验证失败即回滚（回滚方式见各项）。

---

## S-02 / S-03｜浏览器登录态轮换（browser-auth-profile-v1 / v2）

**对象**：`E:\WB\state\ai-production-control\browser-auth-profile-v1\`（S-02）、`...\browser-auth-profile-v2\`（S-03）
**性质**：Chromium Profile（Cookies / Trust Tokens / 登录态），ChatGPT 网页会话凭据载体

### 轮换步骤
1. **停桥**：关闭 bsk daemon（52900 端口）与连接中的 Chrome 扩展会话（保留扩展本身，只断连接）。
2. **清理登录态**：在 Chrome 的该 profile 中退出 ChatGPT 登录（或删除 profile 内 `Default\Network\Cookies` 与 `Default\Trust Tokens` 下的登录态数据）。**注意：不要删除整个 profile 目录**（扩展、配置仍在）。
3. **重新登录**：以该 profile 启动 Chrome → 打开 chatgpt.com → 重新登录（登录方式与原一致）。
4. **重连桥**：启动 bsk daemon（`bsk-home` 配置）→ 扩展自动重连 → 确认 `browsers connected = 1`。

### 验证方法
- `chatgpt_bridge status` → 返回 READY 且 browsers connected ≥1
- 用一次**只读**真实 GOAL（如 `runtime.py work` + `report`）验证 R 会话可收发；PASS 即轮换成功
- 验证失败回滚：检查登录态是否完整（重新登录）或恢复 P0 备份中的 profile

### 注意事项
- S-02 与 S-03 是两个 profile，**分别轮换**，避免两个同时不可用。
- 轮换后旧登录态失效属预期（正是轮换目的）。

---

## S-06｜代理密钥轮换（proxy-key.dpapi）

**对象**：`E:\WB\tools\catpaw-longcat-proxy\runtime\proxy-key.dpapi`（588B，DPAPI 加密）
**性质**：catpaw 反代的生产代理密钥；**DPAPI 机器绑定**（仅本机可解，复制到其他机器无效）

### 轮换步骤
1. **定位签发入口**：catpaw-longcat-proxy 的管理界面/CLI 中找到「重新生成代理密钥/API Key」功能（**不要直接读写 .dpapi 文件**——它是 DPAPI 密文，任何复制/读取都无意义且属凭据触碰）。
2. **重新签发**：在 catpaw 中生成新密钥 → 由 catpaw 自身重新加密覆盖 `proxy-key.dpapi`（密钥材料不经人工中转）。
3. **重启反代**：重启 catpaw 进程使新密钥生效。

### 验证方法
- catpaw 端口（32177）重新 LISTENING，`GET` 一次健康检查端点返回正常
- 用一次真实 API 调用（经 catpaw 转发）确认新密钥可鉴权
- 验证失败回滚：恢复 catpaw 配置中的旧密钥（catpaw 管理界面可查看/切换）

### 注意事项
- **绝对不要复制 .dpapi 文件**（B10 明示：DPAPI 机器绑定，复制无效）；备份清单中该项已按裁决保持原状。
- 轮换后更新 `会话注册.json` 或相关配置中指向该密钥的引用（如有）。

---

## 1. 轮换记录要求

每项轮换完成后，业主在 `docs/asset-registry/SENSITIVE_FILES.md` 对应行追加轮换时间与结果（如 `S-02 轮换 2026-08-30 OK`），保持敏感资产台账可审计。

## 2. 本批施工团边界声明

- ✅ 已产出：本操作清单（步骤 + 验证方法）
- ❌ 未触碰：任何凭据本体（未读取 Cookies / .dpapi / 会话注册内容 / profile 内容）
- ❌ 未执行：任何轮换动作（执行主体为业主本人）
