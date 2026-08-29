# 执衡系统用户操作指南（User Operation Guide）

- 生成：2026-08-30 01:05 · RUN: RUN-20260830-010247-37d9 · Brain 拆解：proposal 已生成
- 面向：第一次接触执衡的普通用户
- 原则：所有命令可直接复制执行；真实动作（work/report）只在有真实任务时使用

## 1. 提交一个目标（run.cmd work）

1. 把目标写进一个 UTF-8 文本文件（如 `goal.txt`）
2. 执行：
   ```cmd
   & "E:\WB\tools\ai-production-control\runtime\run.cmd" work --goal-file <goal文件路径> --r-url <R会话URL>
   ```
3. R 会话 URL 从 `E:\执衡\05_资源\会话注册.json` 的 R-PROD.url 读取，**不要自己猜**
4. 成功输出：`{"status":"OK","run_id":"RUN-...","bridge":"READY"}`

## 2. 查看状态（status）

```cmd
& "E:\WB\tools\ai-production-control\runtime\run.cmd" status --run-id <RUN_ID>
```
输出当前 step、next_action、verdict。

## 3. 回交审查（report）

执行完目标后，把结果写进一个 UTF-8 文件，然后：
```cmd
& "E:\WB\tools\ai-production-control\runtime\run.cmd" report --run-id <RUN_ID> --message-file <结果文件>
```
R 会返回 PASS / REWORK / BLOCKED。REWORK 就按 next_action 返工后重交；直到 DONE。

## 4. 用 Brain 拆解目标（brain_bridge）

```cmd
cd C:\Users\17838\Documents\Qoder\2026-08-28\031cb4e3\b1\runtime
python brain_bridge.py --goal-file <goal.txt> [--out taskgraph.json]
```
输出：proposal_id、约束提取、Task Graph、human_view（进度投影）。

## 5. 用 Capsule 续跑（capsule_bridge）

会话中断后，新会话接手第一步：
```cmd
python capsule_bridge.py --run-id <RUN_ID> [--verify]
```
输出：机械投影的 Context Capsule（facts + resume_instruction），无需用户重讲历史。

## 6. 只读安全命令（可随时用）

- `run.cmd health`：链路健康
- `run.cmd status --run-id <ID>`：RUN 状态
- `chatgpt_bridge status`：桥健康（需 BSK_HOME）

## 纪律提醒

- `<尖括号>` 是占位符，替换后才能执行
- work/report 是真实动作（消耗真实算力/会话），没有真实任务禁止试跑
- R_URL 只从会话注册.json 读，缺失即停
