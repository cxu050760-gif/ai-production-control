# 本地链调用索引（Local Chain Calls）

> 用途：执衡系统"本地链"（纯本地施工循环 + 中继控制层）的调用方式总索引。
> 维护：2026-08-29 恢复控制会话收束入仓。数据真源 = 磁盘实际文件，凭据样内容仅登记路径不读内容。
> 纪律：优先复用本索引指向的现成资产，禁止重新开发同类能力。

## 1. 施工循环拓扑（当前）

```
用户给目标
   ↓
[O 规划会话]（网页强 AI，web-roles.json → o）
   ↓ 提案 NEXT_TASK + validateTaskProposal
[Controller 中继]（construction-relay，确定性状态机）
   ↓ TASK_ACTIVATED + WAKE_GRANT
[Builder]（TRAE / 本地执行端，bindings/builder.json）
   ↓ 施工 → Candidate 提交 → BUILDER_READY 事件
[Controller] 认领事件 → 送审
   ↓
[R 审查会话]（网页强 AI，web-roles.json → r）
   ↓ PASS / REWORK
[Controller] 推进 → O 再规划 → 循环
```

角色注册（权威）：`E:\执衡\05_资源\会话注册.json`（R-PROD / B-V0.1 / R-V0.1 / O-V0.1）。
中继配置：`E:\WB\state\ai-production-control\construction-relay\relay.config.json`。
角色绑定：`...\construction-relay\bindings\`（builder.json / web-roles.json / reviewer.json）。

## 2. 调用链资产（只登记调用方式，二进制不入仓）

| 资产 | 位置 | 调用方式 | 状态 |
|---|---|---|---|
| chatgpt_bridge | `C:\Users\17838\.local\bin\chatgpt_bridge(.cmd)` | `status\|open\|upload\|send\|receive\|close` | 生产现役，统一传输层 |
| bridge_send.py | 同目录 | 桥发送实现 | 现役 |
| bsk daemon | `E:\WB\tools\bsk-file-bridge\repo\target\release\bsk.exe` | 需 `export BSK_HOME=...\bsk-home`；WS 52900 | 现役（R 通道） |
| yz_lib.sh | `E:\WB\workspace\2026-08-16-21-49-32\work\` | 桥接消费端库（G-14 待迁移） | 未迁移 |
| Runtime V1 入口 | worktree `run.cmd` | `run.cmd work/report "<goal>"` | 生产现役黑盒 |
| catpaw 反代 | `E:\WB\tools\catpaw-longcat-proxy\` | 端口 32177，9 模型 API | LIVE_PASS 零改动 |

## 3. 能力手册（已入仓 docs/canon/zh_cn/）

- `capability_registry.md` ← `E:\执衡\00_先看这里\能力操作手册_20260820\03_CAPABILITY_REGISTRY.md`（11 张 CLI 调用卡）
- `operator_manual.md` ← `04_AI_OPERATOR_MANUAL.md`
- `bootstrap.md` ← `06_NEW_AI_BOOTSTRAP.md`

## 4. 00_HOME 工具链文档（仅登记，未入仓）

`E:\ChatGPT\00_HOME\`：TOOLCHAIN / CAPABILITY_MAP / WORKBUDDY_CLI_GUIDE / CODEX_PARALLEL_GUIDE / RULES / AGENT_PROTOCOL / PROJECT_REGISTRY。
状态：流 B 盘点登记；本次收束仅索引，是否复制入仓待业主裁决（G-2 同类项）。
凭据纪律：AGENT_PROTOCOL 明示 OAuth 凭证仅 DPAPI 加密存于 00_HOME，不得明文入仓——故本索引不复制其内容。

## 5. 中继控制层（construction-relay）

- 状态根：`E:\WB\state\ai-production-control\construction-relay\`（1691 文件/23MB）
- 恢复运行：2026-08-29 23:46（PID 17360 watcher + 5864 guard，心跳持续刷新）
- 结构：bindings / events / tasks / grants / watchdog / arbitrations / budgets / promotions / quarantine / relay.ndjson（账本）
- 角色轮转：`role-runs\`（65 个 ROLE 目录，O/C 交替历史）
- 纪律：运行时状态不入 git；只收编 bindings/config 结构与轮转索引（见 docs/asset-registry/）

## 6. 启动命令速查

```bash
# 起 guard（先）
cd E:/WB/tools/Trae-Ralph && node src/relay/outer-guard.js watch \
  --config E:\WB\state\ai-production-control\construction-relay\relay.config.json \
  --interval-ms 15000 --stale-ms 3600000
# 起 watcher（后）
node E:\WB\tools\Trae-Ralph\src\review-relay.js watch \
  --config E:\WB\state\ai-production-control\construction-relay\relay.config.json
# 查状态
node E:\WB\tools\Trae-Ralph\src\review-relay.js status --config <config>
```
