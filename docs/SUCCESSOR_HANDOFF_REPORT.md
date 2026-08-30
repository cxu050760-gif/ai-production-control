# DEPRECATED / HISTORICAL — Successor Handoff Report

> This report is retained as historical evidence only. It predates V0.1 Official Runtime Entry canonicalization and MUST NOT be used as current startup or Worker instructions.
> Current entry selection: read `runtime/WEAK_WORKER_START_HERE.md` and use `E:\WB\tools\ai-production-control\runtime\run.cmd` as the only OFFICIAL Runtime Entry. `ai-control.cmd` / `scripts/ai_control.py` are COMPATIBILITY / LEGACY only.

---

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

## 4. 接手者完整剩余关键路径（2026-08-17 20:50 修正版）

> 修正说明：早先版本把剩余工作说成"接 bsk 通道→重跑验收"——**说窄了**。
> 核实事实：A18"全链路"虽 PASS 但走的是 fallback 脑；ChatGPT 主脑路径从
> Codex 时代第一天起（5 次运行）从未真实通过。规格的核心体验
> （goal → ChatGPT 主脑 → 全自动流水线）至今一次都没真实跑通过。

### 4.0 必须先建立的认知

62/65 PASS 的真实含义：
- 证明了：控制面公理（WAL/Authority/防伪造/防复活/TCB）在故障注入下成立；
  浏览器能力矩阵在 fixture 上全过（A02）；5 类真实网站通过（A03-A07）；
  Worker/Local Runtime、结果真实性、发布完整性门禁全部在位。
- 没证明：真实 ChatGPT 当主脑（A08/A09 全程 BLOCKED）；A18 走真实主脑
  （用 fallback 顶替通过）；真实 ChatGPT UI 漂移下的稳定性（A23/A26/A28
  是 fixture 级 PASS）；§122 独立 Brain 终审（依赖 A09 reviewer 会话，同样被堵）。
- 本系统立意（V14 §56-64/§72-77）：通用浏览器运行时面向所有网页、
  程序化 CLI 入口任何 AI 可调用——这部分骨架已在，但"通用性"的最终
  证据必须包含真实主脑链路，不能只有 fixture + fallback。

### 4.0.5 独立能力矩阵审计（2026-08-17 21:10，本任补做——此前从未有人做过）

> 背景：用户核心目标是**通用浏览器全自动化（所有网页）**，不是"修好 ChatGPT"。
> A02 PASS 只证明 Codex 写的实验室通过了 Codex 写的检查。本节是对照
> V14 §57/§63 逐项独立审计的结果。

**实验室（lab）实际覆盖**：约 20/21 类 fixture 有真实交互验证——navigate/
back/forward/reload/click/dblclick/hover/mouse/keyboard/input/select/checkbox/
radio/scroll/drag-drop/clipboard/contenteditable/iframe/popup/multi-tab/upload/
download/SPA/DOM替换/慢网络(弱)/video 全状态/canvas 视觉回退/accessibility/
screenshot/prompt-injection/UI-changed —— 基本盘扎实。

**已识别缺口（按严重度）**：
1. **ProseMirror 类富编辑器：未真正测试**（§63 明列，仅用普通 div contenteditable
   顶替）。讽刺的是这恰是 ChatGPT composer 的能力类别——通用运行时最弱的
   一环正好卡在旗舰用例上。A08/A09 被堵不是巧合，是能力矩阵缺口的必然暴露。
2. **auth-expired 仅属性模拟**（data-auth="expired"），无真实过期登录流验证。
3. **infinite scroll 判定浅**（滚动后 count>0，无渐进加载断言）。
4. **真实网站集偏易**：bing/github/w3schools/heroku upload/github zip——
   无登录墙、无 Cloudflare 反爬、无 shadow DOM、无 canvas 应用、无重型 SPA。
   "代表 5 站通过" ≠ "所有网页可用"。

**结构性问题（比缺口更重要）**：验收用例与实现同源（Codex 自写自评），
A18 用 fallback 脑 PASS 是自评放水的实证。接手者必须把"审计用例严谨性"
当作与"跑通用例"同级的任务，禁止把 A01-A65 当作用户目标的完备代理。

**对接手者的含义**：修复优先级应为 ①富编辑器能力（含真实 ProseMirror
fixture）→ ②bsk/ChatGPT 通道（作为高难度站点实例）→ ③反爬/shadow DOM
等硬类别扩展 → ④其余浅判定加深。ChatGPT 是难度样本，不是目标本身。

### 4.1 完整行动清单（按序执行，不许跳步）

```
1.  读 V14-FROZEN + docs/BUILD_MISSION_JOURNAL.md + 本报告 §3 资产清单
2.  前置确认：git log 见 af4e692 之后；doctor 全 PASS；生产 Chrome 运行中
    且已登录 ChatGPT（dev 扩展 flgjhpgekodbmbngjbagficgnacdbaae 已装）
3.  后台启动 daemon（前台跑会阻塞挂死会话！）：
    Start-Process bsk.exe -ArgumentList 'daemon','start','--port','52900'
    验证：bsk.exe browsers（BSK_HOME=E:/WB/tools/bsk-file-bridge/bsk-home）
    显示 INSTANCE + EXT 0.1.5
4.  在 src/aicontrol/runtimes.py 实现 bsk chatgpt 通道（参考 yz_lib.sh 已验证
    函数），acceptance.py chatgpt_call 路由到该通道。必须实现 §49-54 全协议：
    会话 acquire/复用去重（0 开/1 用/>1 查）、发送≠完成两段提交、
    崩溃窗口 outgoing nonce 存在即不重发、===CP_REQUEST/===CHATGPT_DONE===
    marker（复用 Codex 已有 marker 逻辑）、reconnect、截获清理
5.  A08/A09 真实 PASS（证据=真会话 URL+marker 绑定，非 fixture）
6.  A18 必须以真实 ChatGPT 主脑重跑通过；禁止 fallback 顶替后宣称核心体验成立
7.  真实路径稳定性攻击（对应用户对旧桥"时稳时不稳"的核心顾虑）：
    连续 ≥5 轮真实调用全通过（对标旧桥 round5_v4 5/5 强度），
    含一次中途断连恢复、一次慢响应等待
8.  §122 独立 Brain 终审：用 A09 reviewer 独立会话审
    architecture/Effect Gate/WAL/Authority/TCB/acceptance/release；
    blocking finding → 修复 → 复审干净
9.  最终回归：ai-control.cmd acceptance 全量重跑（预期 65/65 或
    64/65+A11 条件跳过），final_status=READY_FOR_USER_ACCEPTANCE
10. Release Candidate：ai-control.cmd release → digest 链校验
    （tested=reviewed=release=delivered 四 digest 一致）
11. V14 §134 完整最终报告（含真实 limitation：ChatGPT UI 漂移风险与
    marker/轮询缓解、同用户 OS 无法绝对阻断 PRIVILEGED_UNBROKERED、
    依赖生产 Chrome 保持登录+dev 扩展已加载）
12. 每完成一步：更新 BUILD_MISSION_JOURNAL.md + git commit（durable checkpoint）
```

### 4.2 风险预告（接手前想清楚）

- ChatGPT 前端会变：选择器以 §3 的 DOM 事实表为基准，失效先 bsk snapshot
  重新定位，不要臆测（旧桥三铁律仍然有效）
- 测试判定三条铁律（旧桥 v2/v3 用误判换来的）：JS 侧判定单 token 返回；
  回复=轮询"assistant 数增加+含关键字"；图片附件查 img 元素数
- bsk 发送按钮偶发失效一次：轮询"存在且非 disabled"再点击，失败隔 2 秒重试
- daemon 有 idle 退出：每轮验证前确认 52900 在听
- 你的 AI 会话若直接前台跑 daemon start 会挂死——必须 Start-Process

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
