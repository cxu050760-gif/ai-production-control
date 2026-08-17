# 交接报告 — AI Production Control Plane（V14-FROZEN）

> 生成：2026-08-17 20:30（第 3 任 build owner：TRAE/GLM 接手 OpenAI Codex 后）
> 读者：下一任接手 AI 或开发者。本文自包含，配合 `docs/BUILD_MISSION_JOURNAL.md` 食用。
> 唯一正式规格：V14-FROZEN，位于 `C:\Users\17838\.codex\attachments\c33ac6a6-82c9-4ebb-8783-abc6ace36301\pasted-text.txt`

---

## 0. 一句话现状

**系统本体 62/65 验收 PASS、全部基础设施绿；唯一卡点是 A08/A09（ChatGPT 真实调用）需要登录态通道，而这条通道的现成解（bsk + 生产 Chrome 扩展）早在 2026-08-16 就被旧桥项目验证为 PASS，但 Codex 和本任前期都没有读取旧桥交付文档，各自绕了弯路。**

---

## 1. 责任复盘（诚实版，为什么慢）

| 任 | 做对了什么 | 犯的错 |
|----|-----------|--------|
| Codex（前任） | 建成完整控制面：Canonical State / Effect WAL / Authority Journal / Effect Gate / TCB / 65 个验收 case 实现 | ① chatgpt_call 只写了 playwright+独立 profile 路径，没接 bsk；② 没读旧桥 HANDOVER.md（D004"不修改 Bridge"被执行成了"不读 Bridge 的成功数据"）；③ 中断在 TCB 改动未重封处 |
| 本任（TRAE/GLM） | 完成接管：外部备份、Git baseline `374073f`、TCB 重封 gen6、跑通第一轮全量验收 62/65、诊断 A08/A09 根因 | **继承了 Codex 的弯路**：用户已给出 ENTRY_README 指路后，仍先尝试"复制生产 cookie 到自动化 profile"两次实验（即旧桥 README 明令禁止的弯路），浪费了约 1 小时；此错误已记录 F004 |
| 环境因素 | — | `bsk.exe daemon start` 是前台阻塞命令，直接调用会挂住会话（本任踩过一次，已停掉） |

**教训（对所有后续 AI）**：`E:\WB` 层已有资产的成功数据是第一优先级输入。项目 docs 里"不要把历史 BrowserSkill/Bridge 报告当作当前运行时验收"的意思是"要重新实测"，不是"不读它们的方法论和已验证路径"。

---

## 2. 真实进度（以磁盘证据为准，2026-08-17 20:30）

| 项 | 状态 | 证据 |
|----|------|------|
| Git baseline | ✅ `374073f` CODEX_INTERRUPTED_STATE_BASELINE + 4 docs commits | `git log` |
| 外部备份 | ✅ 93 文件含 SHA256 manifest | `E:\WB\backups\ai-production-control-PRE_TAKEOVER_BACKUP-20260817-1750` |
| 单元测试 | ✅ 4/4 PASS | `python -m unittest discover -s tests` |
| doctor / selftest | ✅ 全 PASS（TCB gen6 VERIFIED, 15 files） | `ai-control.cmd doctor / selftest` |
| Canonical State | ✅ rev 18 hash-valid；Effect WAL 39 条 verified；Authority Journal 60 events verified | doctor 输出 |
| 验收 A01–A65 | ✅ **62/65 PASS**；A11 合法条件跳过；A08/A09 EXTERNAL_BLOCKED | `E:\WB\outputs\ai-production-control\acceptance-run-latest.json`（manifest sha256 f9990a3f…） |
| Release Candidate / 最终报告 | ⏳ 排在 A08/A09 之后 | — |

A08/A09 从 Codex 时代起 5 次运行从未 PASS，根因始终同一个：自动化 profile 无 ChatGPT 登录态。

---

## 3. A08/A09 的现成解（已被旧桥验证 PASS，照做即可）

**旧桥判定：`BROWSER_FILE_BRIDGE_V1 = PASS`（2026-08-16 20:40，ChatGPT 连续 5 轮实测 5/5）**

必读资产（全在磁盘上）：
1. `E:\WB\tools\bsk-file-bridge\reports\HANDOVER.md` — 完整交接：架构、DOM 事实、测试方法论三铁律
2. `E:\WB\tools\bsk-file-bridge\reports\ENTRY_README.md` — 短入口："用已登录的浏览器，不要新起"
3. `E:\WB\workspace\2026-08-16-21-49-32\work\yz_lib.sh` — 已验证函数：`yz_acquire_conv / yz_send_text / yz_send_file / yz_grab_reply / yz_wait_reply_done`
4. `C:\Users\17838\.workbuddy\reviewer-registry.json` — ChatGPT 总审查会话 URL，last_verdict=PASS
5. `E:\WB\tools\bsk-file-bridge\test\round5_v4.sh` + `reports\round5_v4_results.txt` — 权威测试脚本与 5/5 结果

关键环境事实：
- 用户生产 Chrome（默认 profile）**已有 ChatGPT 有效登录态**，正常启动自动恢复
- dev 扩展已装入生产 Chrome（ID `flgjhpgekodbmbngjbagficgnacdbaae`，"加载已解压"，Chrome 重启自动重载）
- dev daemon 有 idle 退出机制；BSK_HOME=`E:/WB/tools/bsk-file-bridge/bsk-home`，端口 52900
- bsk.exe = `E:\WB\tools\bsk-file-bridge\repo\target\release\bsk.exe`（0.1.10，含 upload）

ChatGPT DOM 事实（2026-08-16 实测）：composer=`#prompt-textarea`（contenteditable DIV 非 textarea）；发送=`button[data-testid="send-button"]`；生成中=`[data-testid="stop-button"]` 存在；回复=`div[data-message-author-role="assistant"]`；file input=`#upload-files`。

---

## 4. 接手者精确行动清单

```
1. 读 V14-FROZEN 规格 + docs/BUILD_MISSION_JOURNAL.md + 本报告
2. 确认前置：git log 看到 15d3567；ai-control.cmd doctor 全 PASS；
   用户生产 Chrome 正在运行（16 进程左右）且已登录 ChatGPT
3. 后台启动 daemon（不要直接 RunCommand 前台跑，会阻塞挂死）：
   Start-Process bsk.exe -ArgumentList 'daemon','start','--port','52900'
   验证：bsk.exe browsers（设 BSK_HOME）应显示 INSTANCE + EXT 0.1.5
4. 参考 yz_lib.sh，在 src/aicontrol/runtimes.py 增加 bsk chatgpt 通道
   （acquire conversation → send text with markers → grab reply），
   在 acceptance.py chatgpt_call 里按 config browser.fallback=bsk 路由，
   保留 playwright 路径为 primary 之外的 fallback（D003 决策反转不需要，
   只需让 A08/A09 真正可达）
5. 注意 Codex 实现已支持 marker 协议（===CP_REQUEST / ===CHATGPT_DONE===），
   bsk 通道沿用同一 marker 协议即可复用现有 WAL/Effect Gate 逻辑
6. 重跑：ai-control.cmd acceptance（预期 64/65 或 65/65，A11 视条件）
7. RELEASE：ai-control.cmd release → digest verify → V14 §134 最终报告
8. 每步更新 BUILD_MISSION_JOURNAL.md 并 git commit
```

---

## 5. 已证伪路径（不要再走）

| 编号 | 死路 | 原因 |
|------|------|------|
| F004 | 复制生产 Chrome cookie 到自动化 profile（无论配 CFT chrome 还是真 chrome.exe） | Chrome v20 app-bound 加密绑定原安装上下文，两次实验均 AUTH_EXPIRED，cookie 被静默丢弃 |
| 旧桥 README 禁令 | 新起浏览器 / 新建 profile / 复制 profile / VSS/ABE 解密登录态 | 旧桥 2026-08-16 已全部踩过，全是弯路 |
| F001 | Windows Computer Use 当主浏览器后端 | 输入确认与恢复不可靠 |
| F003 | bsk 当唯一后端 | 旧 fork 无通用 download；bsk 只做登录态通道+上传 |

---

## 6. 环境快照（2026-08-17 20:30）

```
代码根   E:\WB\tools\ai-production-control（git master, HEAD 15d3567）
状态根   E:\WB\state\ai-production-control（control.db, rev18）
输出根   E:\WB\outputs\ai-production-control（acceptance-run-latest.json 等）
Chrome   生产实例运行中；默认 profile 已登录 ChatGPT；dev 扩展已装
bsk      bsk.exe 存活；daemon 端口 52900 未监听（idle 退出，需后台重启）
TCB      generation 6 VERIFIED（manifest 08f606b1…）
人为残留 browser-auth-profile-v2（F004 实验遗留，可删）
```
