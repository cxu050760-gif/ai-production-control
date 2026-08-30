# 执衡黑箱操作卡 v1.1-blackbox（一页卡）

> 给第一次接触执衡的弱 AI（混元3 / 豆包级）看。你不需要理解执衡内部。
> 只记住：**一个入口、四个动词、五步操作**。其余全部自动。
> 对应宪法：§64 工具手册 / §65 唯一入口 / §71 简洁用户界面。

---

## 四个动词（§65）

| 动词 | 做什么 | 命令 |
|---|---|---|
| `work` | 提交任务（SUBMIT TASK） | `run.cmd work --goal-file <目标文件> --r-url <R会话URL>` |
| `report` | 交回结果、请审查（STATUS） | `run.cmd report --run-id <RUN号> --message-file <结果文件>` |
| `result` | 查最终结果（RESULT） | `python runtime\blackbox_bridge.py result --run-id <RUN号>` |
| `human-gate` | 查需要人类介入的任务 | `python runtime\blackbox_bridge.py human-gate` |

---

## 五步操作

### ① 进入工作目录
```
cd C:\Users\17838\Documents\Qoder\2026-08-28\031cb4e3\b1
```

### ② 把目标写进 UTF-8 文本文件
写清楚两件事：**要什么成果** + **怎么算做完了**。例如 `goal.txt`：
```
产出一份《X 项目验收报告》，包含：结论、证据清单、遗留风险。完成后给我文件路径。
```

### ③ 提交任务（work）
```
& "E:\WB\tools\ai-production-control\runtime\run.cmd" work --goal-file goal.txt --r-url <R会话URL>
```
- R 会话 URL 从 `E:\执衡\05_资源\会话注册.json` 的 **`roles` → `R-PROD` → `url`** 读取（三层嵌套，不是顶层）。
- 只读 URL 字段；**不要**复制、外传或修改该文件里的任何内容。
- 成功后输出会给你一个 `run_id`（形如 `RUN-20260818-173304-7350`），记下来。

### ④ 干完活交回结果（report）
把结果写进一个 UTF-8 文本文件（如 `result.txt`），然后：
```
& "E:\WB\tools\ai-production-control\runtime\run.cmd" report --run-id <RUN号> --message-file result.txt
```
- 审查方只会回两种结论：`PASS`（通过）或 `REWORK`（哪里不行）。
- 若 `REWORK`：按它说的改 → 再 `report`，**直到 PASS**。只有审查方 PASS 算数，你自己不能宣布"完成"。

### ⑤ 查结果 / 查人类介入（result / human-gate）
```
python runtime\blackbox_bridge.py result --run-id <RUN号>
python runtime\blackbox_bridge.py human-gate
```
- `result` 输出：`verdict`（PASS/REWORK）+ `conclusion`（结论原文）+ `final`（是否终态）。
- `human-gate` 输出：当前**需要人类介入**的任务清单（`waiting` 数组），每项含：哪个 RUN、卡在哪一步、需要什么。
  没有等待任务时输出 `waiting_count: 0`，照实报告即可。
- 看到 human-gate 清单：**原样转发给用户**，等用户决策（例如 `run.cmd directive --run-id <ID> RESUME` 恢复）。

---

## 出错怎么办（一句话规则）

> **任何命令报错，把报错原文一字不改地贴给用户；不要自己猜路径、不要自己改生产文件、不要重试循环。**

常见情况：
- `RUN_NOT_FOUND` / `STATE_NOT_FOUND`：RUN 号不对，问用户。
- `MISSING_R_URL` / `INVALID_R_URL`：R 会话 URL 没给对，问用户。
- `RUNTIME_ENV_BLOCKED` / `BRIDGE_UNHEALTHY`：环境没起来，把输出贴给用户。

## 红线（违者重罚）

- **禁止**修改 `E:\WB\tools\ai-production-control\runtime\` 下任何文件。
- **禁止**碰任何凭据文件（含会话注册.json 的非 URL 字段）。
- **禁止**自己宣布"任务完成"——只有审查方 `PASS` 算数。
- **禁止**猜路径；路径一律用本卡给出的。

---

*本卡为 v1.1-blackbox 施工线文档。`work`/`report` 走生产 run.cmd（现役冻结）；`result`/`human-gate` 走本仓 `runtime\blackbox_bridge.py`（只读查询，不改生产结构）。四动词统一入口在桥升级后收口。*
