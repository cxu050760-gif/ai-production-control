# WEAK_WORKER_BOOTSTRAP — 中途接班恢复（弱模型专用，<=40 行）

你被叫来接手一个已在跑的 RUN。不要相信任何聊天记忆；只有下面 4 步是真的。

## 你拿到的输入
只有两样：`RUN_ID`（形如 RUN-20260818-xxxxxx-xxxx），可能还有用户新指令。

## 恢复步骤（按顺序，不可跳）

1. 读固定路径登记：
   `E:\WB\tools\ai-production-control\runtime\bootstrap.json`
   （里面有 runtime 入口和 state 位置；没有任何会话 URL——URL 不该由你找。）

2. 用入口查状态（唯一权威）：
   `& "E:\WB\tools\ai-production-control\runtime\run.cmd" status --run-id <RUN_ID>`

3. 照 `status` 字段分支，不要自行解读：
   - `RUNNING` → 读 `current_step` 和 `next_action`，从那里继续干活；每完成一步用
     `run step --run-id <RUN_ID> --current "..." --next "..."` 落盘。
   - `PAUSED` → 停。什么都不做，等用户 RESUME。禁止绕过。
   - `STOPPED` / `DONE` → 终态，报告用户，不要继续。
   - `HARD_BLOCKED` → 停，把 state 文件路径报告用户，禁止另找路线。

4. 需要审查/返工/验收时只用：
   `run send --run-id <RUN_ID> --message "..." [--file ...]`
   返回的 `last_r_verdict`（PASS/REWORK/BLOCKED/NO_VERDICT）照契约执行，见
   `WEAK_WORKER_START_HERE.md`。

## 永远禁止
直接碰 bsk/daemon/端口/session/marker/click/浏览器；猜或继承 R_URL；
机械重复同一发送；自判"我是新会话所以重置任务"。

完整契约：`E:\WB\tools\ai-production-control\runtime\WEAK_WORKER_START_HERE.md`
