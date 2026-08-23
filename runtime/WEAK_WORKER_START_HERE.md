# WEAK WORKER START HERE — Production Runtime V1 唯一生产契约

你是本地执行者 W（弱模型即可）。本 RUN 的一切推进只通过 `runtime` 命令完成。
**入口**：`E:\WB\tools\ai-production-control\runtime\run.cmd`（下文记作 `run`）。
PowerShell 示例：`& "E:\WB\tools\ai-production-control\runtime\run.cmd" status --run-id RUN-...`

**宿主调用约束（必读）**：只允许用 Windows-native 分发路径调用入口（PowerShell 或 cmd）。
禁止用裸 bash 类 host 工具包装 run 命令（可能被解析到 WSL shim 而在入口前就死亡）；
看到 WSL/shim/PATH 类错误时不要自行折腾 WSL/PATH/Bridge，直接报告用户。
入口被真正到达的证据在 `cli_log.jsonl` 的 `RUNTIME_ENTRY_REACHED`；没有该记录 = 宿主分发问题，不是 Runtime 问题。

## 铁律（违反即任务失败）

1. 只用 `run` 的 9 个命令：start / status / step / directive / send / recv / done / metrics / health。
2. **永远不要**直接调用或研究 bsk、daemon、端口、yz_lib、session、marker、click、浏览器实例。桥传输失败时只允许"按预算重试同一条 run 命令"；出现 HARD_BLOCKED 就停止并报告用户。
3. 每个新 RUN 必须由用户显式提供 R_URL。没有 R_URL → `start` 会返回 MISSING_R_URL：立即停止，向用户索要。不继承旧 RUN、不从历史/记忆/文件猜、不自行创建或寻找 ChatGPT 会话。
4. 除 `start`/`health` 外所有命令必须带明确的 `--run-id`。不要假设"当前 RUN"。
5. 用户指令 PAUSE/STOP/RESUME/R_URL_CHANGE/CHANGE_SCOPE/USER_OVERRIDE 必须立即执行：
   `run directive --run-id <ID> <ACTION> [--new-r-url ...] [--note ...]`。先落盘再行动是 runtime 内置的，你只需调用并读取返回。
6. 上下文被压缩、换了会话/模型后：第一件事 `run status --run-id <ID>`，以 state 的 `status`/`next_action` 为唯一权威。你自己对"新旧会话"的判断不作数。

## 标准循环

1. `run status --run-id <ID>` → 读 `status` 与 `next_action`。
2. 状态非 RUNNING：按 `allowed_actions` 行动（PAUSED 就等待；HARD_BLOCKED/STOPPED 就报告用户）。
3. RUNNING：做 `next_action` 要求的工作；每完成一步：
   `run step --run-id <ID> --current "刚完成的" --next "接下来要做的" [--checkpoint "关键成果位置"]`
4. 需要 R 审查时（关键决策/真实异常/高风险/最终验收/REWORK 完成后）：
   `run send --run-id <ID> --message "<简洁正文>" [--file 证据文件 ...]`
   - **多行正文必须**先写成文件再用 `--message-file <路径>`；`--message` 只传单行（入口层换行会截断，多行会被拒绝）。
   - **默认 text-only**：简短日志、状态摘要、metrics、verdict 请求一律直接写进正文，不要为它们创建并上传 txt。只有审查方确实需要文件内容时才加 `--file`。
   - `--file` = **attachment-required**：上传超预算会 HARD_BLOCKED，runtime 不会偷偷丢附件改文本；不带 `--file` = text-only，绝不触发上传。返回的 `attachment_mode` 字段会显式告诉你本次是哪种。
   - 只传增量：已经传过且未变的文件 runtime 会自动跳过，放心列全。
   - 返回的 `last_r_verdict` 已由 runtime 解析好：
     - `PASS` → 收尾后 `run done --run-id <ID>`
     - `REWORK` → 直接按 `next_action` 返工，完成后再次 send（不要问用户常规技术决策）
     - `BLOCKED` 或 run 变 HARD_BLOCKED → 停止并报告用户
     - `NO_VERDICT` → runtime 已自动追问过；继续推进工作，下个 delta 里再次明确请求终判
5. 相同内容在相同步骤重复发送会被 runtime 拒绝（DUPLICATE_ACTION）：换内容或先 `step` 推进，禁止机械重试。

## 输出语义（机器可解析，直接照做，不要自行解读 R 的自然语言）

- exit 0 + `"status":"OK"` → 成功。
- `"status":"MISSING_R_URL"` → 停止，找用户要 R_URL。
- `"status":"RUN_PAUSED"` / `"DENIED"` → 不要绕过；等用户 directive。
- `"status":"HARD_BLOCKED"` → 停止；把 state 文件路径报告给用户。
- `"status":"DUPLICATE_ACTION"` → 禁止重复同一动作。

## 快速开始（用户提供 GOAL + R_URL 时）

```
run start --goal "<GOAL>" --r-url "<R_URL>" --worker-id "<你的名字>"
```
记下返回的 run_id；此后一切命令带 `--run-id <run_id>`。

## 中途接班（压缩/重启/换 Worker/换模型后）

不要相信自己的记忆。只读两个文件恢复：
1. `E:\WB\tools\ai-production-control\runtime\bootstrap.json`（固定资源路径）；
2. `run status --run-id <RUN_ID>` 的输出（唯一权威：status / current_step / next_action / r_url）。

详细步骤见同目录 `WEAK_WORKER_BOOTSTRAP.md`。
