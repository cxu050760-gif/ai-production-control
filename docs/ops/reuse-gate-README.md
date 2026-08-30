# Reuse Gate README — §48-51 Reuse 门禁工具化（D3）

> 对应宪法：§48 Reuse Gate / §49 Adapt / §50 Compose / §51 Supply Chain。
> 本工具把「先搜 GitHub 现成方案 → 判定 Reuse>Adapt>Compose>Build → Decision 留痕」
> 流程机械化，并强制「**无 Decision 不得 BUILD**」。

## 一句话

```
python scripts/reuse_gate.py check --task "<任务描述>" --require-decision
```

- 输出 `BUILD_BLOCKED`（退出码 **1**）= 该任务没有 Decision 留痕，**禁止进入 BUILD**。
- 输出 `GATE_OK`（退出码 0）= 已有覆盖该任务的 Decision，可继续。

## 三个命令

| 命令 | 作用 |
|---|---|
| `check` | 四步流程：①本地已有方案搜索（capability-registry + FAILED_APPROACH_LEDGER）②GitHub 搜索（gh CLI 或搜索指引）③判定 Reuse>Adapt>Compose>Build + 理由 ④门禁判定 |
| `record` | 生成结构化 Decision 留痕，追加到 `docs/evidence/reuse-decisions.ndjson`（供主理人汇总入 DECISION_LEDGER） |
| `list` | 查看已有留痕（可 `--task` 过滤覆盖项，只读） |

## 用法示例

```bash
# ① 先跑 check（不强制留痕，看判定与本地/已失败路线命中）
python scripts/reuse_gate.py check --task "守护层看门狗" --search watchdog keepalive

# ② 按判定结果 record 留痕（evidence 必须是 URL 或本地路径）
python scripts/reuse_gate.py record --task "守护层看门狗" --decision compose \
    --evidence "docs/DECISION_LEDGER.md#D022" \
    --note "复用 schtasks+端口探活；GitHub 无现成可直接接入组件"

# ③ 门禁模式：无 Decision -> BUILD_BLOCKED（exit 1）
python scripts/reuse_gate.py check --task "守护层看门狗" --require-decision

# ④ 查已有留痕
python scripts/reuse_gate.py list
python scripts/reuse_gate.py list --task "守护层看门狗"
```

## 判定规则（机械，可解释）

按优先级取最优先的可行级别（§48 Reuse>Adapt>Compose>Build）：

1. **Reuse**：本地 capability-registry 命中同能力官方工具，或 GitHub 命中可直接接入组件；
2. **Adapt**：GitHub 命中现成方案但需改造接入；
3. **Compose**：无整体现成方案，但有可组合既有组件（复用系统自带/既有命令组装）；
4. **Build**：本地无命中、GitHub 无直接可接入组件，才自研。

`check` 输出中 `decision_template` + `record_command` 字段直接给出下一步 record 命令。

## 已失败路线衔接（FAILED_APPROACH_LEDGER）

`check` 会读 `docs/FAILED_APPROACH_LEDGER.md` 的 F 系列条目，当任务关键词命中已失败路线时输出
`failed_approach_ledger.warning`——**重新实现前必须满足其 do_not_retry_unless 条件**，
否则属于重复发明失败方案。`record` 时也会在记录中带上 `failed_approach_warning`。

## Decision 留痕文件

- 路径：`docs/evidence/reuse-decisions.ndjson`（每行一个 JSON 对象，追加式）
- 结构：`decision_id / recorded_at / task / decision / evidence / note / gate_check_summary`
- 纪律：本工具只留痕，**不代主理人写 DECISION_LEDGER**；正式汇总由主理人统一写。
- 机器可读消费点：门禁判定读同一 ndjson 文件（`--decisions` 可覆盖路径）。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | GATE_OK（含无 --require-decision 的普通 check） |
| 1 | BUILD_BLOCKED（缺 Decision 记录）或写文件失败 |
| 2 | 用法错误（缺参数 / 非法 decision 值） |

## 红线

1. 只读衔接 `config/capability-registry.json` / `docs/FAILED_APPROACH_LEDGER.md`，不改它们；
2. 不改 `src/aicontrol/`、`config/production.json`、`runtime/runtime.py`；
3. 凭据不入仓；本工具无任何凭据输入。

## 实测记录（2026-08-30，D3 冒烟）

| 场景 | 结果 |
|---|---|
| `check --task "Playwright 通用网页下载工具"` | GATE_OK；本地命中 cap-browser-download/browser-playwright-cdp；F003 已失败路线警告；verdict=reuse |
| `record`（Playwright 下载） | 追加 docs/evidence/reuse-decisions.ndjson 成功 |
| `check --require-decision`（有记录任务） | GATE_OK，covering_count=1，exit 0 |
| `check --require-decision`（无记录任务） | **BUILD_BLOCKED**，covering_count=0，**exit 1** |
