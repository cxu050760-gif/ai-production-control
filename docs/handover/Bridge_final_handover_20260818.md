# Bridge 最终接班证据包（2026-08-18）

R 终判：CHATGPT_ONLY_BRIDGE_STABLE_PASS。本包供更换本地 AI 后直接接手。

## 1. CURRENT_PRODUCTION_PATH

唯一生产链路（自上而下）：

| 环节 | 位置 |
|---|---|
| 官方入口 wrapper | `C:\Users\17838\.local\bin\chatgpt_bridge`（+bridge_send.py/.cmd） |
| 核心函数库 | `E:\WB\workspace\2026-08-16-21-49-32\work\yz_lib.sh`（bash source 后用 yz_* 函数；最全口径，实测以此为准） |
| 二进制 | `E:\WB\tools\bsk-file-bridge\repo\target\release\bsk.exe`（dev 版，含 upload） |
| daemon | BSK_HOME=`E:\WB\tools\bsk-file-bridge\bsk-home`，ws 端口 **52900**（现为默认值，自动拉起即落对） |
| 浏览器 | 生产 Chrome 默认 profile，dev 扩展实例 **7da8483f**（唯一，勿新建实例） |
| R 总审查会话 | `https://chatgpt.com/c/6a83b967-d184-83ee-9525-ccd7133e83b5` |
| E 实验会话 | `https://chatgpt.com/c/6a83b98e-cd8c-83ee-b840-2f82458b775d` |
| 生产发送器 | `C:\Users\17838\.qwenworkcn\workspace\msxabcrk9r3d8zr3\s8_send.sh`（URL 硬编码旧审查会话 6a81b611，换目标需临时改第 9 行后恢复）；`C:\Users\17838\.qwenworkcn\workspace\msxee0lj8st52vui\nsb\send_pkg.sh`（URL 读同目录 conv_url.txt） |

## 2. CHANGES_TODAY

每项：故障 → 修改 → 真实验证结果。

1. **`repo\crates\bsk-cli\src\cli\daemon.rs:10` + `tests\cli_parse.rs:23`（2 行）+ 重编译 bsk.exe**
   故障：daemon 死后生产入口自动拉起落默认端口 52800，扩展只连 52900，冷启动永不自愈（实测 FAIL）。
   修改：DEFAULT_WS_PORT 52800→52900，重编译（PATH 前置 `E:\WB\tools\bsk-file-bridge\mingw64\bin`）。
   验证：停净 daemon 后仅调 wrapper → 自动拉起 52900 LISTENING、wrapper READY、E 页面 READY 且往返回声正确（证据：r_reply_9.txt、e_cold_reply.txt）。
2. **`yz_lib.sh` yz_wait_reply_done**
   故障：回复完整但缺 DONE 标记时必然白等到 hard 超时（180~300s），并产生无效恢复 session。
   修改：新增 DONE_NO_MARKER 容错（恢复读取已尝试 + 新回复存在 + 恢复后 IDLE≥30s + 长度稳定≥20s → 完成）。marker 优先级不变。
   验证：nomarker2 实测 SEND_RESULT=DONE_NO_MARKER、exit 0、耗时 102s（<300s）、capture 完整（nomarker2_trace.txt、e_nomarker2_capture.txt）。
3. **`yz_lib.sh` yz_send_text / yz_send_file / yz_wait_reply_done 基线传参**
   故障：assistant 基线在发送后才读取，快回复被吞进基线 → count>base 恒假，恢复与容错全失效（xtrace 实锤 base=4=回复后值）。
   修改：点击发送前采集基线，作为第 5 参数传入 wait。
   验证：nomarker2 轮 trace 显示 base_pre=3=base_acount=3<4，容错生效（nomarker2_trace.txt 行 17/39/50）。
4. **`yz_lib.sh` yz_acquire_conv 复用分支**
   故障：卡死会话 hoil（存活+URL 对，但页面卡 GEN）被复用 → SEND_FAILED（真实发生）。
   修改：复用须再过 yz_gen_state==IDLE 一关；GEN/读取失败则新建 session，不 stop 旧会话。
   验证：健康复用回归两次 acquire 同 SID、零新增 session/window/tab（tabs_idle_before/after.json、r_reply_26 前证据）。
5. **`s8_send.sh:31` 与 `send_pkg.sh:31`（各 1 行）**
   故障：门槛只认 DONE，DONE_NO_MARKER 被误判失败（exit 4），容错进不了生产。
   修改：接受 DONE|DONE_NO_MARKER。
   验证：s8_send.sh 真实全流程 SEND_WAIT=DONE_NO_MARKER→capture 完整→S8_END、exit 0（gate2_reply.txt）。

## 3. VERIFIED_PASS（均有真实运行证据）

| 项 | 证据（workspace msy08g6icwp0nlno） |
|---|---|
| 冷启动 52900 自愈 + E 往返 | e_cold_reply.txt、r_reply_9.txt |
| DONE_NO_MARKER 容错（102s 完成） | nomarker2_trace.txt、e_nomarker2_capture.txt |
| 基线竞态修复 | nomarker2_trace.txt（行 17/39/50）、race_trace.txt（修复前反证） |
| 正常 marker 路径 DONE | regress_trace.txt（行 883 echo DONE；经卡尾帧恢复命中属既有设计） |
| 发送器 DONE_NO_MARKER 门槛 | gate2_reply.txt（19 字节完整回声、exit 0） |
| acquire 幂等 + IDLE 门不误伤 | tabs_idle_before/after.json |
| 会话回收连带关窗口/tab、无泄漏 | tabs_precycle.json、sess_before/after_nomarker.txt、r_reply_11.txt |
| 构建路径溯源+受控重编译/部署 | r_reply_6/7/8.txt、备份哈希见 BASELINE |

## 4. NOT_PROVEN / KNOWN_RISK（未证实或 R 暂缓，非故障）

- **CAPTURE 新鲜度**：R=DONE 后旧 SID 可能抓到 ≥50 字节的截断/陈旧回复且无 task_id 绑定校验——仅理论推演，无真实反例，R 明确暂缓。
- **marker 偶发不输出**：模型侧行为（E、R 各出现过），已被容错覆盖，无法根除。
- **长思考超窗**：附件+复杂否定指令曾致 E 思考 >420s（gate 尝试 1，真实发生但属模型行为）；短指令可避免。
- **yz_send_file 仍用坐标 click**（第 315 行，未改）：理论上可被 overlay 截走，今日无新反例。
- **daemon 约 5-6 分钟 idle 自退**：已知设计；自退后任意生产命令会自动拉起（现已落对 52900）。

## 5. DO_NOT_TOUCH

- 旧生产 bsk（52800）已退役；冷存档 `E:\AI_COLD_ARCHIVE\bridge-baseline-2026-08-17` 严禁当现役读取/执行。
- `chatgpt_bridge.ps1` = BUG3 未修旧实现，勿用。
- 禁止重新安装工具链：重编译只需已存在的 `E:\WB\tools\bsk-file-bridge\mingw64\bin`（rust 自带 mingw 缺 nanosleep64 必失败；本机无 MSVC）。
- 禁止重新设计 marker 协议 / 等待状态机 / 守护保活机制（R 已判结构正确）。
- 禁止重测已 PASS 项（冷启动、窗口回收、门槛、marker 状态机、IDLE 门）。
- 禁止新建 Chrome/浏览器实例；只复用 7da8483f 与 R/E 两会话；禁止批量 kill Chrome。
- 基线继续冻结：任何新修改须用户另行明确授权。

## 6. STARTUP_FOR_NEW_AI（最少启动步骤）

1. `netstat -ano | grep ":52900"` — 无 LISTENING 也不用慌：任意 bsk 命令会自动拉起（默认已是 52900）；或显式 `BSK_HOME=E:/WB/tools/bsk-file-bridge/bsk-home E:/WB/tools/bsk-file-bridge/repo/target/release/bsk.exe daemon start --port 52900`。
2. `chatgpt_bridge status` → 应输出 Bridge: READY / Instance: 7da8483f。
3. `source /e/WB/workspace/2026-08-16-21-49-32/work/yz_lib.sh`
4. `SID=$(yz_acquire_conv "<R或E的URL>")` — 自动复用健康会话或新建；映射失效会自动恢复。
5. 发送：`res=$(yz_send_text "$SID" "正文" 300)` — 自动附带任务标记与 DONE 指令；返回 DONE / DONE_NO_MARKER / TIMEOUT / SEND_FAILED。
6. 抓取：`yz_recv_last "$SID" out.txt` — 用默认 minlen(≥50)，勿手动传小值；勿手工补 marker。
7. SEND_FAILED → 查该 session `yz_gen_state`，卡 GEN 就 `bsk session stop <sid>` 后重新 acquire。
8. 注意：`$(yz_send_text)` 在子 shell 内更新的全局 YZ_SID 不外传；后续抓取在父 shell 用 yz_recv_last（其自带新 attach 回退）。

## 7. R / E / W PROTOCOL

- **R 总审查**（最终判断权）：`https://chatgpt.com/c/6a83b967-d184-83ee-9525-ccd7133e83b5`
- **E 实验**（唯一试错场）：`https://chatgpt.com/c/6a83b98e-cd8c-83ee-b840-2f82458b775d`
- **W 本地执行者**：只执行 R 的 NEXT_ACTION；改代码前必须经用户精确授权；已 PASS 项无新反例不重开；新故障只处理第一个真实断点；全程桥传输，不让用户手工复制粘贴。
- W→R 首轮可发完整现状；此后每轮只发：`CURRENT_STEP:` / `EVIDENCE_DELTA:` / `RESULT:` / `HYPOTHESIS:`（可选）。
- R 回复格式：`===REVIEW_VERDICT=== PASS|REVISE|BLOCKED` + `===NEXT_ACTION===` + WHY + DO_NOT，末行 `===CHATGPT_DONE:<task_id>===`（yz_send_text 自动附加该指令；R 偶发漏标记时按容错/重抓处理）。
- 任务终态令牌：`CHATGPT_ONLY_BRIDGE_STABLE_PASS`（已于 2026-08-18 达成）。

## 8. BASELINE

现役 SHA-256：

| 文件 | SHA-256 |
|---|---|
| bsk.exe | 72f385427a26161217658b8e46b049f672564285a79218db457982fc53c0ffb7 |
| yz_lib.sh | f2ad7bd05cac7c0956dac8475f2e97340894c183e1e74a520d4713bfb8b2eb4c |
| s8_send.sh | 2e3df1d98d2a2b038399e739fd94d1bab94dad4887ad50dbbe83bec2adb031f8 |
| send_pkg.sh | ee88dcbf7e1325f9a0b48b22e7425d2d054dfc1240481f446d7165b312ffed09 |

- 冻结状态：基线自 2026-08-18 起继续冻结（新改动须用户授权）。
- 回退备份（workspace msy08g6icwp0nlno）：bsk.exe.bak-20260816（旧 0f87b179…）、yz_lib.sh.bak-20260818（原 7f54eb7c…）/ .bak-p2 / .bak-p3、s8_send.sh.bak-20260818、send_pkg.sh.bak-20260818、conv_url.txt.bak-20260818。
- 未提交修改：git 仓库 `E:\WB\tools\bsk-file-bridge\repo` 中 daemon.rs/cli_parse.rs 两行改动未 commit；该仓库另有 8/16 前既有的未提交变更（extension dispatcher 等，与本次无关）。yz_lib.sh 所在目录非 git 仓库。
- 冷存档：`E:\AI_COLD_ARCHIVE\bridge-baseline-2026-08-17`（59 项清单 OK，含退役 52800 旧 bsk）。

## 9. EVIDENCE_INDEX

全部位于 `C:\Users\17838\.qwenworkcn\workspace\msy08g6icwp0nlno\`：

- W→R 26 轮 delta：`bridge_r_delta_2.txt` ~ `bridge_r_delta_26.txt`（首轮现状=`bridge_r_init_msg.txt`）。
- R 判定：`r_reply_1.txt` ~ `r_reply_26.txt`（部分带后缀如 r_reply_4b）。关键判定：r_reply_2（冷启动 FAIL→定位）、r_reply_6（溯源 PASS）、r_reply_9（冷启动验收设计）、r_reply_11（实例问题闭环）、r_reply_18（marker 断点闭环）、r_reply_22（门槛 PASS）、r_reply_26 后终判 **CHATGPT_ONLY_BRIDGE_STABLE_PASS**。
- E 实测：e_probe_reply.txt（首次探测）、e_cold_reply.txt（冷启动往返）、e_nomarker_capture.txt（容错首测 FAIL→竞态线索）、e_race_capture.txt（竞态探针）、e_nomarker2_capture.txt（容错复验 PASS）、e_regress_capture.txt（回归，含截断抓取案例）、gate2_reply.txt（门槛 PASS）。
- xtrace：race_trace.txt（竞态实锤）、nomarker2_trace.txt（容错 PASS 全证据）、regress_trace.txt（marker 路径）。
- 实例审计：tabs_precycle.json、tabs_idle_before/after.json、sess_before/after_nomarker.txt。

## 10. FINAL_STATUS

**SOLVED**：冷启动错误端口；marker 缺失白等；基线竞态；发送器门槛不兼容；卡死会话错误复用；浏览器实例增长（判无泄漏）。

**NOT_PROVEN**：CAPTURE ≥50 字节陈旧/截断回复的 task 绑定（无真实反例）；yz_send_file 坐标 click 的 overlay 隐患（今日无反例）。

**DEFERRED**（R 明确暂缓）：CAPTURE 新鲜度修复；daemon idle 自退机制调整；扩展仓库默认端口（wxt.config.ts 52800，仅未来重 build 扩展时相关）。

---

## NEW_AI_BOOTSTRAP_BRIEF（弱模型只读此段即可）

你是本地执行者 W。本机有一座已验收稳定的 WorkBuddy↔ChatGPT 桥，直接用它，不要重新设计、不要改它（改动需用户授权）。

链路：`source /e/WB/workspace/2026-08-16-21-49-32/work/yz_lib.sh` 后用里面的函数。二进制是 `E:/WB/tools/bsk-file-bridge/repo/target/release/bsk.exe`（BSK_HOME=`E:/WB/tools/bsk-file-bridge/bsk-home`），端口 52900。浏览器用生产 Chrome（扩展实例 7da8483f），不要新开浏览器。

会话只有两个：总审查 R=`https://chatgpt.com/c/6a83b967-d184-83ee-9525-ccd7133e83b5`，实验 E=`https://chatgpt.com/c/6a83b98e-cd8c-83ee-b840-2f82458b775d`。测试一律在 E，裁决找 R。

操作三步：① `SID=$(yz_acquire_conv "<URL>")` 拿会话（自动复用/自愈）；② `res=$(yz_send_text "$SID" "内容" 300)` 发送并等完成，返回 DONE 或 DONE_NO_MARKER 都算成功，TIMEOUT/SEND_FAILED 才算失败；③ `yz_recv_last "$SID" out.txt` 抓回复（不要加小 minlen 参数）。

常见情况：daemon 闲 5 分钟会自退——不用管，下一条 bsk 命令会自动拉起且端口正确；SEND_FAILED 多半是会话页面卡死，`bsk session stop <SID>` 后重新 acquire；抓到的内容像被截断就再 yz_recv_last 一次。

协议：R 有最终判断权。每轮只发 CURRENT_STEP/EVIDENCE_DELTA/RESULT/HYPOTHESIS 四项，等 R 的 NEXT_ACTION，只做那一步。改任何代码前必须先问用户拿到精确授权。已 PASS 的项目不要重测。完整证据和细则见本文件第 1-10 节（同目录 Bridge_final_handover_20260818.md）。
