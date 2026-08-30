# Capability Registry — 能力注册表说明（宪法 §63）

> 分支：`v1.1-blackbox` ｜ 实施：software-engineer-r2（R2：能力注册表 + 资产接入）
> 宪法锚点：**§63 Capability Registry**（原文：系统必须维护机器可读能力注册表…这样系统才能真正做到：资源可替换）
> 关联条款：§5 AI/Provider/Agent Independence · §20 浏览器是通用生产执行面 · §21 本地电脑是通用生产执行面 · §59 Cost Routing

## 1. 交付物

| 文件 | 作用 |
|---|---|
| `config/capability-registry.json` | 机器可读能力注册表（schema_version 1，顶层 15 节 + role_bindings） |
| `docs/ops/registry-validate.py` | schema 自检脚本（json.load + §63 完整性 + 引用一致性），只读 |
| `docs/ops/registry-launch.py` | 消费脚本：探测健康 → 对 Official 且停机的能力打印拉起命令建议；并验证 registry 被 production.json 消费 |

### 为什么消费脚本选 Python 而非 .cmd

1. **规范解释器就是 Python 3.12**：`config/production.json workers.local_python` 与 `runtime/run.cmd` 的 `APC_PY` 均指向
   `C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`，消费端与运行时同栈，无需引入新依赖。
2. **JSON 原生解析 + UTF-8 中文路径**：注册表含中文路径与嵌套 JSON，Python `json.load` 直接可用；
   `.cmd` 需要对 JSON 引号、CJK 路径做脆弱转义，易错且不可审计。
3. **探测安全可标记**：命令探测仅在 `health_check.read_only=true` 且显式 `--probe-commands` 时执行，
   拉起建议只打印不执行——符合"机器可完成部分做完、危险操作留人工"的纪律。

## 2. Registry 结构（覆盖 §63 全部 15 项）

顶层 `sections` 共 15 节，与宪法 §63 枚举一一对应：

| §63 条目 | 注册表节 | 内容示例 |
|---|---|---|
| Brain | `brains` | chatgpt-web（默认主脑）、workbuddy-deepseek-v4-flash、codex-local（回退） |
| Worker | `workers` | local_python、workbuddy_node、workbuddy_cli、codex_cli、trae-builder |
| C | `correctors` | ec-lite（执行纠偏）、strategic-correction（战略纠偏）、中继 corrector |
| R | `reviewers` | r-prod-chatgpt-web（强 AI 审查）、e-lab-codex-cli、trae-ralph-relay |
| Browser | `browsers` | playwright-cdp（主）、bsk（回退）、cft、chrome、各 profile |
| Tool | `tools` | chatgpt_bridge、bsk-daemon、runtime-run、catpaw-proxy、Trae-Ralph 中继/外闸 |
| Provider | `providers` | chatgpt-web、workbuddy、codex、catpaw、trae-solo-cn |
| Login State | `login_state` | 会话注册.json、.bridge_state.json、auth-profile-v1/v2、cft-profile、catpaw-gui |
| Cost | `costs` | 各能力 cost_per_call/cost_model（无数据一律 null + "待 D2 校准"） |
| Quota | `quotas` | codex strong-review 24 次/天（relay.config）、max_review_cycles 3 |
| Reliability | `reliabilities` | 各能力可靠性（当前全部"待实测"，附 last_probe 观测） |
| Capabilities | `capabilities` | §20/§21 能力目录 + v08 注册表 capability 令牌 |
| Official/Experimental/Deprecated | `lifecycle_status` | 三档定义 + 条目清单（Deprecated 例：legacy-bsk-no-upload） |
| Permissions | `permissions` | 全局策略默认 + 会话注册/browser-profile/外发三门/catpaw 专项 |
| Adapter | `adapters` | WebSessionProvider、APIModelProvider、chatgpt-bridge、bsk、catpaw-openai、trae-ralph、local-command |

每个能力条目统一携带：

```jsonc
{
  "id": "唯一 id（kebab-case）",
  "name": "人类可读名",
  "role": "brain|worker|c|r|browser|tool|provider|login_state",
  "type": "WEB_SESSION|API_MODEL|AI_CLI|LOCAL_RUNTIME|CDP|CHROMIUM|PROFILE|EXTENSION|CLI_WRAPPER|DAEMON|CLI_ENTRY|PROXY_SERVICE|RELAY|BRIDGE|RULES_MODULE|CREDENTIAL_REFERENCE|PROVIDER_ADAPTER|...",
  "status": "official|experimental|deprecated",
  "entry":     { "kind": "command|path|note", "command": [...], "path": "...", "cwd": "...", "note": "..." },
  "health_check": { "kind": "port|file|command|note", ... },
  "launch":    { "kind": "command", "command": [...], "note": "仅打印建议，不自动执行" },
  "cost":      { "cost_per_call": null, "cost_model": null, "note": "待 D2 校准" },
  "quota":     { "limit": null, "unit": null, "note": "..." },
  "reliability": { "level": "待实测", "last_probe": "...", "observed": "..." },
  "permissions": { "external_effect": "DENY", "credential_transport": "REFERENCE_ONLY", "note": "..." },
  "adapter":   "adapter-*（若适用）",
  "source":    "数据来源",
  "notes":     ["补充说明"]
}
```

顶层还有：

- `source_of_truth`：本注册表数据来源（production.json、桥、daemon.json、relay.config.json、v08 注册表、融合评估等）；
- `role_bindings`：角色 → 条目 id 映射，供消费脚本/调度快速按角色枚举；
- `notes`：全局纪律（凭据只登记路径、D2 待校准、差异点等）。

## 3. 如何登记新能力

1. **先验证存在性**：路径/二进制/端口必须真实存在或可探测；拿不准的字段留 `null` + note，**不得编造**。
2. **选节**：按 §63 分类放入对应 `sections` 节；跨分类的（如某 CLI 既是 Worker 又是 Reviewer）分别在对应节登记，用同一 `id` 前缀区分（如 `worker-codex-cli` / `r-e-lab-codex-cli`）。
3. **必填字段**：`id`（全库唯一）、`name`、`type`、`status`、`entry`、`health_check`；其余字段（cost/quota/reliability/permissions/adapter）按可用性填写，无数据写 `null` 并注明。
4. **health_check 三选一**：
   - `{"kind":"port","host":"127.0.0.1","port":N,"timeout_sec":2}`
   - `{"kind":"file","path":"..."}`
   - `{"kind":"command","command":[...],"expect":"...","read_only":true,"timeout_sec":N}`（仅登记只读探测命令；危险命令一律不登记为探测）
5. **登记 launch 建议（可选）**：Official 且可能停机的能力，登记 `launch.command`（仅建议，`registry-launch.py` 只打印）。
6. **凭据纪律**：会话注册.json、browser profile、proxy-key.dpapi 等一律只登记路径（`entry.kind="path"`），不复制内容、不读取、不外传。
7. **跑校验**：`python docs/ops/registry-validate.py` 通过（PASS）后再提交；跑消费脚本确认健康口径：`python docs/ops/registry-launch.py`。

## 4. Official / Experimental / Deprecated 判定规则

| 档位 | 判定条件 | 调度语义 |
|---|---|---|
| **Official** | 已在 `config/production.json` 或生产 `run.cmd` 中声明/接线，**且** health_check 有实测通过证据（或可复现探测） | 可作为默认依赖；调度可直接选择 |
| **Experimental** | 已登记且路径/二进制存在，但未在生产主链验证、当前停机、或属 construction_only 融合登记 | 不得作为生产默认依赖；需升档评审 |
| **Deprecated** | 已被新能力取代或明确不再使用（如 legacy bsk 无上传能力） | 调度不得选择；保留登记仅供审计 |

升档/降档必须在 `docs/DECISION_LEDGER.md` 记录 actor 与依据（注册表本身只反映事实，不自行裁决档位）。

## 5. 与 D2 成本路由 / §5 Adapter 的衔接点

- **D2 成本路由（§59）**：`costs` 与 `quotas` 节是 D2 的输入契约。
  - 当前所有 `cost_per_call`/`cost_model` 均为 `null`（注明"待 D2 校准"），D2 需按实测填充：chatgpt-web 会话成本、workbuddy/deepseek/codex API 成本、catpaw 9 模型定价、R 审查会话成本；
  - `quotas` 已有 2 个真实值：`quota-codex-strong-review`（24 次/天，来源 relay.config.json automation.strong_review_budget_per_day）、`quota-review-cycles`（3 次/任务，来源 production.json policy.max_review_cycles）；
  - D2 路由应消费 `capability_id` 关联到具体能力，实现 §59 的 Expected Total Cost 路由与 §61 SAFE_HALT 熔断。
- **§5 Adapter（Provider Independence）**：`adapters` 节登记了 7 个适配器，其中 WebSessionProvider/APIModelProvider 的 `contract` 对齐 `runtime/v08_adapter_registry.json`（V08_PROVIDER_CONTRACT）。
  - D1 R-Adapter（LiteLLM）落地时应把新 provider 以 `adapter-*` 条目追加进 `adapters`，并在对应 `providers` 条目上填 `adapter` 引用；
  - "资源可替换"的验证路径：同一角色（如 Brain）存在多个条目 + 各自 adapter，调度可按 §59 条件替换。

## 6. 机器验证（2026-08-30 实测）

```bash
python docs/ops/registry-validate.py              # schema 自检（期望 PASS）
python docs/ops/registry-launch.py                # 消费脚本 dry-run（期望 exit 0，production cross-check ok）
python docs/ops/registry-launch.py --probe-commands   # 额外执行只读命令探测（chatgpt_bridge status 等）
```

- `registry-validate.py`：验证 JSON 可解析、15 节齐全、id 唯一、adapter/capability/role_bindings 引用可解析、health_check 结构合法；
- `registry-launch.py`：逐条探测端口/文件/命令 → Official 且 DOWN 的能力打印 `launch.command`（不执行）→ 交叉核对 production.json 的 brains/workers/browser 均有注册表条目（"registry 被运行时消费"验收点）。

## 7. 已知差异点 / 待办

1. **production.json 差异**：`browser.generic_profile`（`E:\WB\state\ai-production-control\browser-profile`）2026-08-30 实测目录**不存在**，注册表已登记为 `experimental` 并告警；需 Controller 决定创建目录或修正配置（本任务不修改 production.json）。
2. **catpaw 停机**：反代 32177 当前停；`proxy-key.dpapi` 为 DPAPI 机器绑定密文，轮换执行主体=业主本人（S-06 清单）。
3. **D2 成本校准**：全部 cost 字段待 D2 按实测填充（见 §5）。
4. **可靠性指标**：全部 `待实测`，需累计真实调用数据后回填。
5. **W1 接线**：`tcb-verify`/`grant-auth` 属 S1/W1 后续施工，不在本注册表范围；`tool-runtime-run` 已登记其外发三门依赖。

## 8. 纪律声明

- 本批只写 `config/capability-registry.json` + `docs/ops/registry-*`，未触碰 `scripts/`、`runtime/`、`src/`、`config/production.json`、`PROJECT_STATE.*`、`docs/DECISION_LEDGER.md`。
- 未读取/复制任何凭据内容（会话注册.json、browser profile、proxy-key.dpapi 仅登记路径）。
- 未 push；提交由主理人统一执行。
