# D1 全角色 Adapter — 操作说明（v1.1-blackbox）

> 执衡 v1.1-blackbox 开发线 · D1 任务 · 机器可完成部分
> 交付：`runtime/adapters/`（独立模块，符合"新增走独立模块"红线）

> **⚠️ 解释器要求（DEF-D1a）**：运行与测试**必须用 Python312（生产 APC_PY，
> 与 run.cmd 一致）**：
> `C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`
> （Python 3.12.10；litellm 1.83.0 只装在这个解释器）。默认 `python`（3.13.x）
> 未装 litellm，用它会报 `LITELLM_NOT_INSTALLED`——**不是依赖缺失，是解释器不对**。
> 本 README 所有命令示例均带 Python312 完整路径。

## 1. 定位

宪法 §5 Provider 独立：**AI 是资源可替换**——R / Brain / Worker 都应有 Adapter。
D1 交付 R-Adapter 与 Worker-Adapter 的机器可完成骨架：

| 模块 | 角色 | 协议 | 状态 |
|---|---|---|---|
| `runtime/adapters/r_adapter.py` | R 审查者 Provider 适配（LiteLLM） | CLI + LiteLLM Router | ✅ 骨架完成（mock 可用） |
| `runtime/adapters/worker_adapter.py` | CLI 型弱模型 Worker 适配 | CLI（stdin/stdout） | ✅ 骨架完成（mock 可用） |
| `runtime/adapters/r_adapter.config.example.json` | R-Adapter 示例配置 | — | ✅ |
| `runtime/adapters/worker_adapter.config.example.json` | Worker-Adapter 示例配置 | — | ✅ |
| `runtime/adapters/test_r_adapter_d1_offline.py` | R-Adapter 单测 | — | ✅ 30 用例绿 |
| `runtime/adapters/test_worker_adapter_d1_offline.py` | Worker-Adapter 单测 | — | ✅ 14 用例绿 |
| `docs/ops/adapter-README.md` | 本说明 | — | ✅ |

**红线（本包所有模块遵守）**：
- 凭据一律走环境变量（`api_key_env` 只登记变量名），**禁止硬编码/入仓**；
- 真实 Provider 调用（消耗真实 API key / 额度）= **留业主（L3）**；本包只做 mock 与骨架；
- 不改 `src/aicontrol/`（Controller TCB 封印）、`config/production.json`（生产冻结）、
  `runtime/runtime.py`（生产冻结）、`config/capability-registry.json`（R2 已审，只读衔接）；
- 输出为 inert 数据（`non_authority`）；任何 authority 词只作数据呈现，绝不代执行。

## 2. 依赖

- **解释器（必须）**：Python 3.12.10（生产 APC_PY，与 run.cmd 一致）：
  `C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`
- **LiteLLM 1.83.0**（仅 Python312 安装；`import litellm` OK；`completion` / `Router` 可用）
  - 依赖已登记：`pyproject.toml` `[project.optional-dependencies] adapters = ["litellm==1.83.0"]`
  - 安装：`C:/Users/17838/AppData/Local/Programs/Python/Python312/python.exe -m pip install -e ".[adapters]"`
  - 网络超时加 `--proxy http://127.0.0.1:7897` 或清华镜像
    `-i https://pypi.tuna.tsinghua.edu.cn/simple`（装不上先跳过，不因网络停摆）。
- **无需 litellm 也能用的命令**（DEF-D1b）：`health` / `pick` / `review --mode real`（无 key 时）
  都不 import litellm；仅 `review --mode mock` 与 `review --mode real`（有 key）需要 litellm。

## 3. R-Adapter（`runtime/adapters/r_adapter.py`）

### 3.1 子命令

```bat
C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe runtime/adapters/r_adapter.py health --config <F>
C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe runtime/adapters/r_adapter.py pick   --config <F> [--prefer <provider_id>]
C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe runtime/adapters/r_adapter.py review --config <F> --mode mock --mock-verdict PASS|REWORK [--payload '<json>']
C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe runtime/adapters/r_adapter.py review --config <F> --mode real    # 需 key；L3 业主接入点
```

退出码：`0`=成功；`1`=配置/输入错误；`2`=调用失败/不可用/参数非法。

### 3.2 健康探测（health）

- 对 config 中每个 provider 做**机械探测**，输出结构化 JSON。
- 状态机：
  - `web_session`（如 R-PROD ChatGPT 网页会话）→ **UNCONFIGURED**（需会话 URL，凭据，L3 业主）；
  - `api_key_env` 未声明 → **UNCONFIGURED**；
  - `api_key_env` 声明的环境变量缺失/为空 → **UNCONFIGURED**（**当前施工环境输出 UNCONFIGURED 即正确**）；
  - 有 key 且非空 → 真探测（`health_check` 的 `file`/`command`/`port`，或 LiteLLM 最小 completion）→ **UP / DOWN**。
- 无 key 时绝不发起真实网络调用。

### 3.3 仲裁 / 热切换（pick）

规则（机械，不猜）：
1. 健康状态优先级：`UP > CONFIGURED > UNCONFIGURED > DOWN`；
2. 同状态内 `priority` 数字小者优先（与 production.json fallbacks 顺序一致）；
3. `--prefer <id>`：仅当该 provider 健康为 `UP` 才采纳；否则回退规则 1/2；
4. `fallback_chain` = 全部 provider 按 priority 升序（附健康状态）——**主 R 失败 -> 依次切换**，
   由调用方按链消费（本模块只出链，不代执行热切换）；
5. 当前全 UNCONFIGURED 时：仍返回最高优先级占位 provider，`degraded=true`，
   并注明"需要凭据（L3 业主）"。

### 3.4 mock Review（L2 模拟实测通道）

- `--mode mock`：**走 LiteLLM Router 接口但指向内置 mock provider**（`mock_response`），
  零额度、零 key、零网络。返回 `verdict: PASS|REWORK` + `raw_text` + `provider_used: mock-r`。
- `--payload`：JSON 字符串或纯文本，拼进审查提示（inert）。

### 3.5 真实调用（留业主 L3）

- `--mode real`：需要至少一个 provider 的 `api_key_env` 对应环境变量**非空**；
  当前环境无真实 key 时输出 `error: UNCONFIGURED`（正确行为）。
- **仲裁范围（DEF-1 架构会签）**：real 模式 `pick` **仅在已配置 key 的 provider 内仲裁**
  （Router 也只构建 keyed provider）；不会选中未配置 key 的 provider
  （如 web_session 恒 UNCONFIGURED 且 priority=1），避免 Router.completion
  BadRequestError → 误报 REAL_CALL_FAILED。无任何 keyed provider → UNCONFIGURED。
- 接入点：`do_review(cfg, mode="real", ...)` / `_build_router_real()`；
  模型名约定见 `litellm_model_name()`（`provider/model` 前缀拼接）。

### 3.6 与 A1 衔接（只读了解，不强制集成）

`scripts/relay_autopilot.py` 当前 R 单点排队（`R 并发度 = 1`：同时仅 1 个 run 处于
WAITING_REVIEW/REVIEWING）。D1 完成后，R-Adapter 可替代单点：
- 把 autopilot 的 `mock_review` 段替换为 `r_adapter.py review --mode mock` 调用（L2）；
- 真实审查替换为 `--mode real`（L3，需要 key）并按 `pick` 的 `fallback_chain` 实现
  多 R 热切换（主 R 失败 → 次 R），解除"只适配 ChatGPT 网页通道"的硬绑定。

## 4. Worker-Adapter（`runtime/adapters/worker_adapter.py`）

### 4.1 CLI 型协议（stdin/stdout）

```bat
C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe runtime/adapters/worker_adapter.py run --config <F> --goal-file <F> [--mode mock|cli] [--timeout SEC] [--worker <id>] [--mock-result <json>] [--mock-exit-code N]
C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe runtime/adapters/worker_adapter.py list   --config <F>
C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe runtime/adapters/worker_adapter.py health --config <F>
```

协议：**stdin 传 goal、stdout 收结果、stderr 收日志**；统一退出码：
- `0` = 成功
- `1` = 执行失败（子进程非零退出 / 输入错误）
- `2` = 超时

结果结构化 JSON：`exit_code / result / stdout_tail / stderr_tail / timed_out / elapsed_sec`。

- `--mode mock`：内置假 worker（sleep 短时 + 返回预设结果），**零消耗**（L2 测试通道）；
  `--mock-result` 覆盖预设结果，`--mock-exit-code` 模拟失败（默认 0）。
- `--mode cli`：按 config 的 `worker.entry.command` 构造子进程调用；
  `--timeout` 覆盖超时（默认取 `worker.timeout_sec` → `config.default_timeout_sec` = 300s）。
- `list`：按 `config/capability-registry.json workers` 节结构投影 Worker 接入接口
  （id/name/role/type/status/entry/health_check/timeout_sec/adapter/capabilities）。
- `health`：机械探测（entry 存在性 / health_check file/port/command），**不调用真实 AI worker**。

**stdin 契约（DEF-2 架构会签）**：
- **回显型 worker**（如 `worker-echo`，entry 用 `python -c "import sys; print(sys.stdin.read(), end='')"`）：
  stdin 原文回显，自然语言 goal 也可直接回环——CLI 协议演示/L2 实测用这个。
- **脚本型 worker**（如 `worker-local-python`，entry 用 `python -`）：stdin 按 Python 源码解析，
  goal 必须是合法脚本；喂自然语言中文 goal 会 NameError。自然语言 goal 请走 AI_CLI worker
  （`worker-workbuddy-cli` / `worker-codex-cli`）或回显型 worker。
- 示例配置 `worker_adapter.config.example.json` 已同时含脚本型 + 回显型两个条目。

### 4.2 Web 型 / GUI 型（不实现，只登记说明）

- **网页型**：复用 `chatgpt_bridge` 模式（**已存在**，见 capability-registry
  `adapter-web-session` / `tool-chatgpt-bridge` / `r-prod-chatgpt-web`）；
- **GUI 型**：登记 **Experimental**（如 `provider-catpaw` 登录态、browser 型执行面），
  依赖人工登录（`login-catpaw-gui`：`OWNER_ONLY`），不做 CLI 协议。

### 4.3 costs/quotas（D2 成本路由，DEF-4 架构会签）

示例配置 `worker_adapter.config.example.json` / `r_adapter.config.example.json` **暂不含
costs/quotas 字段**——待 D2 成本路由时补充；`config/capability-registry.json` 已有
costs/quotas 数据面（只读衔接，本包不写入）。

## 5. 机器验证记录（D1 已执行）

| 项 | 命令（均用 Python312 生产解释器） | 结果 |
|---|---|---|
| R-Adapter 单测 | `Python312\python.exe -m unittest discover -s runtime/adapters -p "test_r_adapter_d1_offline.py"` | ✅ 30/30 |
| Worker-Adapter 单测 | `Python312\python.exe -m unittest discover -s runtime/adapters -p "test_worker_adapter_d1_offline.py"` | ✅ 14/14 |
| DEF-D1b 回归 | 单测内模拟无 litellm：health/pick 正常、real 无 key→UNCONFIGURED | ✅ 5/5 |
| L2 health | `r_adapter.py health --config r_adapter.config.example.json` | ✅ 全部 UNCONFIGURED（正确） |
| L2 pick | `r_adapter.py pick --config ...` | ✅ 仲裁合理（占位 + fallback 链） |
| L2 review mock | `review --mode mock --mock-verdict PASS / REWORK` | ✅ 走通 LiteLLM Router 接口 |
| L2 review real 无 key | `review --mode real`（无 key） | ✅ 返回 UNCONFIGURED（不碰 litellm） |
| L2 worker mock | `worker_adapter.py run --mode mock` | ✅ 假 worker 返回结果 |
| L2 worker cli | echo worker stdin/stdout 回环 | ✅ exit 0 |
| 既有测试合跑 | `python -m unittest discover -s runtime -p "test_*.py"` | ✅ 全绿（含新增 D1） |
| 语法/导入 | `py_compile` + import 自检 | ✅ |

## 6. 遗留（真实 key 接入点 = L3 业主）

1. **R-Adapter real**：为 `r_deepseek_v4_flash`（`DEEPSEEK_API_KEY`）、
   `r_codex_local`（`OPENAI_API_KEY`）等注入环境变量后，`review --mode real` 即可真实调用；
   real 模式 `pick` 仅对 keyed provider 仲裁（DEF-1）。web_session 需会话 URL
   （`E:/执衡/05_资源/会话注册.json` 只登记路径）。
2. **Worker-Adapter real AI worker**：`codebuddy` / `codex.cmd` 真实调用消耗额度（L3）；
   建议先确认各自 CLI 的 stdin 交互契约后再接入（脚本型 vs 回显型，见 §4.1 stdin 契约）。
3. **成本路由（D2）**：`capability-registry.json` costs/quotas 字段待 D2 校准；
   本包 config 示例暂不含 costs/quotas 字段（DEF-4），只读衔接、不写入。
4. **多 R 热切换接线**：将 `pick` 的 `fallback_chain` 接入 autopilot/Controller 调度
   （当前只出链，不代执行）。
