# REVIEW-D1-2026-08-30-ARCH — D1 全角色 Adapter 独立架构审核（会签）

> 审核人：software-architect-d1（高见远，架构师实例，与 QA 审核者并行 D1 会签）
> 审核对象：`runtime/adapters/`（r_adapter.py / worker_adapter.py / __init__.py / config 示例 ×2 / 测试 ×2）+ `docs/ops/adapter-README.md`
> 审核日期：2026-08-30（worktree `C:\Users\17838\Documents\Qoder\2026-08-28\031cb4e3\b1`）
> 方法：独立上下文读源码 + 全量亲跑（39 用例 + CLI 冒烟 + LiteLLM 真实调用插桩）+ git 红线核查
> 判定：**APPROVED（附 4 项待办，非阻塞）**

---

## 0. 结论摘要

D1 交付的 R-Adapter 与 Worker-Adapter **架构一致、LiteLLM 复用真实、红线零违例、亲跑全部通过**。
- 四项核查：**架构一致性 PASS / LiteLLM 复用真实性 PASS / 亲跑复现 PASS / 红线核查 PASS（含 1 项审核期观察 OBS-1）**
- 39 用例全绿（R-Adapter 25 + Worker-Adapter 14）；CLI 冒烟 health/pick/review mock PASS+REWORK/review real 拒发/worker run mock 全部符合 README 声明。
- 发现 **4 项待办（1 项中危 DEF-1 建议 L3 前修复、3 项低危/文档）+ 1 项观察 OBS-1（审核期 pyproject.toml 并发修改）**，均不阻塞 D1 骨架合入，但建议在 D2/L3 接线前处理。

---

## 1. 架构一致性核查（PASS）

### 1.1 R-Adapter（r_adapter.py，630 行）
| 核查点 | 结论 | 证据 |
|---|---|---|
| health 探测 UNCONFIGURED 判定 | ✅ 正确 | L200-218：web_session / api_key_env 未声明 / env 缺失空 三分支均返回 UNCONFIGURED 且**不发起任何网络**；L207 `if not key_env`、L213 `if not key` 先于一切探测 |
| 无 key 绝不发真实网络 | ✅ | `_probe_litellm`（L242-268）仅在 env 有非空 key 时才被 L230 调用；当前环境全 UNCONFIGURED 已亲跑验证无网络副作用 |
| pick 仲裁状态优先级 | ✅ | L46 `STATUS_RANK = {"UP":3,"CONFIGURED":2,"UNCONFIGURED":1,"DOWN":0}`，L310-314 排序键 `(-rank, priority, id)`；UP > CONFIGURED > UNCONFIGURED > DOWN 语义正确 |
| priority 语义（数字小优先） | ✅ | L314 `int(p.get("priority",99))`；与 production.json `brains.fallbacks` 顺序一致（chatgpt-web→deepseek→codex，示例 config priority 1→2→3） |
| --prefer 条件 | ✅ | L322-327：仅当 prefer 对应 probe 状态 == UP 才采纳（L324），否则回退规则仲裁；已单测覆盖（test_pick_prefer_up_wins / test_pick_prefer_not_up_falls_back） |
| fallback_chain 输出 | ✅ | L329-337：全 provider 按 priority 升序（附健康状态），主 R 失败→依次切换语义正确；README §3.3 声明与实现一致 |
| review mock 走 LiteLLM Router | ✅ | L409-425 `_build_router_mock` 用 `litellm.Router` + `litellm_params.mock_response`（L423）；**插桩证实** `Router.completion` 被真实调用 1 次（model=mock-r），非自造 fake（见 §2） |
| real 模式保留接入点 | ✅ | L428-444 `_build_router_real` 从 keyed provider 构建 Router；L489-497 无 key 时返回 UNCONFIGURED 指引（亲跑 exit=1）；L498-512 真实调用路径完整保留留 L3 |

### 1.2 Worker-Adapter（worker_adapter.py，428 行）
| 核查点 | 结论 | 证据 |
|---|---|---|
| CLI 协议 stdin goal / stdout result / stderr log | ✅ | L168-217 `_run_cli`：`subprocess.run(cmd, input=goal, capture_output=True)`（L175-183）；stdout JSON 解析为 result（L199-204），stderr 收尾段 |
| 退出码 0/1/2 | ✅ | L206-216：ok=(not timed_out and exit_code==0)；超时→2（L189）；失败→1；成功→0；CLI 层 L355 透传 0/1/2 |
| 超时真实生效 | ✅ | 用 `subprocess.run(timeout=...)`（L179）——**非 signal/thread 自实现，直接复用 Python 子进程超时**；Windows 上由 Popen.communicate(timeout) + TimeoutExpired 驱动，子进程被杀（亲跑：sleep(30) 配 timeout=1 → 1s 内返回 timed_out=true exit=2） |
| mock 执行器 | ✅ | L141-162 `_run_mock`：sleep 短时 + 预设结果/退出码，零消耗，L2 测试通道 |
| 遵循既有 CLI 桥模式 | ✅ | 与 brain_bridge / capsule_bridge / blackbox_bridge 一致：JSON 输出、`non_authority: True`、退出码 0/1/2、UTF-8 输出重配置（L409-413） |

### 1.3 与既有 CLI 桥模式一致性（PASS）
- `__init__.py` 明示 schema 约定（L15-18）：inert 数据 + 退出码 0/1/2，与 blackbox_bridge（RESULT_SCHEMA v1.1-blackbox）一致。
- 输出均含 `non_authority: True`（r_adapter L284/372/484/518；worker L161/215/254/310），与宪法 authority 词只作数据呈现一致。
- 均有 `_safe_text` 消毒（对齐 blackbox_bridge L53-60），防 GBK console 崩溃（r_adapter L610-615 / worker L409-413）。

---

## 2. LiteLLM 复用真实性核查（PASS）

**结论：review mock 确实调用 `litellm.Router.completion` 并走 mock provider（`mock_response`），不是自造 fake；真实路径的 key 从环境变量读取。**

亲跑插桩证据：
```
monkeypatch Router.completion -> spy 记录调用并转发真实实现
do_review(cfg, mode="mock", mock_verdict="REWORK") 
=> verdict=REWORK, ok=True
=> Router.completion called: 1
=> model kwarg: mock-r
```
- `_build_router_mock`（L409-425）：`litellm.Router(model_list=[{"model_name":"mock-r","litellm_params":{"model":"gpt-3.5-turbo","api_key":"mock","mock_response": body}}])` —— 这是 **LiteLLM 官方 mock 机制**（`mock_response` 参数短路真实 Provider），复用 Router 接口而非自写 LLM 客户端。
- `_build_router_real`（L428-444）：`litellm_params: {"model": model, "api_key": key}`，key 来自 `_provider_api_key`（L110-119，读 `os.environ[api_key_env]`）；无硬编码 key（§4 红线扫描通过）。
- `_probe_litellm`（L242-268）：真实探测同样走 `Router.completion(max_tokens=1)`，失败吞异常返回 DOWN，符合"有 key 才真探测"。
- 环境核验：litellm 1.83.0 已装、`Router` import OK（`importlib.metadata.version('litellm') == '1.83.0'`）。§48 门禁调研确定的复用方案落地属实。

---

## 3. 亲跑复现核查（PASS）

| 项 | 命令 | 结果 |
|---|---|---|
| R-Adapter 单测 25 用例 | `python -m unittest runtime/adapters/test_r_adapter_d1_offline.py -v` | ✅ 25/25 OK（4.3s） |
| Worker-Adapter 单测 14 用例 | `python -m unittest runtime/adapters/test_worker_adapter_d1_offline.py -v` | ✅ 14/14 OK（2.5s） |
| 39 用例合计 | 上两项 | ✅ **39/39 全绿** |
| health（UNCONFIGURED） | `r_adapter.py health --config r_adapter.config.example.json` | ✅ ok=true, summary {UNCONFIGURED:4}，4 provider 均 UNCONFIGURED（无 key 正确） |
| pick（fallback_chain） | `r_adapter.py pick --config ...` | ✅ selected=r-prod-chatgpt-web(UNCONFIGURED, prio1), degraded=true, fallback_chain 按 priority 升序 [chatgpt-web, deepseek, codex, catpaw] |
| review mock PASS | `review --mode mock --mock-verdict PASS --payload '{"run_id":"RUN-1"}'` | ✅ verdict=PASS, provider_used=mock-r |
| review mock REWORK | `review --mode mock --mock-verdict REWORK` | ✅ verdict=REWORK |
| review real（无 key 拒发） | `review --mode real` | ✅ error=UNCONFIGURED, exit=1，**无真实网络调用** |
| worker run mock | `worker_adapter.py run --mode mock --worker worker-local-python` | ✅ exit=0, result="mock worker completed" |
| 既有全量回归 | `python -m unittest discover -s runtime -p "test_*.py"` | ⚠️ 382 测试，9 errors 全部在**既有** v08/v09/harness_verify 文件，单独运行均通过（全量并发/环境时序问题，与 D1 无关，D1 零修改既有文件） |
| LiteLLM 插桩 | Router.completion spy | ✅ mock review 真实调用 Router.completion 1 次 |

---

## 4. 红线核查（PASS）

| 红线 | 结论 | 证据 |
|---|---|---|
| git 只新增 runtime/adapters/ + adapter-README.md；零修改既有 | ⚠️ 审核期出现一次既有文件修改（见下方观察 OBS-1） | 审核开始时刻（00:57）`git status` 仅 `?? docs/ops/adapter-README.md`、`?? runtime/adapters/`；`git diff --stat` 为空。审核期间（01:02:44）出现 `M pyproject.toml` 并发修改（见 OBS-1） |
| src/aicontrol/ / config/production.json / runtime/runtime.py / capability-registry.json 零修改 | ✅ | git diff 空；r_adapter/worker_adapter 代码仅 import 自模块，不触碰上述文件（docstring 明确声明只读衔接） |

**OBS-1（观察项，非 D1 实现者审核对象内缺陷，需 team-lead/QA 关注）**：审核期间 `pyproject.toml` 被并发修改（mtime 01:02:44，早于本报告 01:04），新增：
```toml
[project.optional-dependencies]
adapters = ["litellm==1.83.0"]
```
- 内容为 D1 相关（LiteLLM 可选依赖声明），方向合理（R-Adapter 依赖可复现）；
- **pyproject.toml 不在冻结清单**（src/aicontrol/、config/production.json、runtime/runtime.py、config/capability-registry.json），故不构成硬红线违例；
- 但与 D1 brief "零修改既有" 表述不符，且发生在审核窗口内（疑似实现者收尾或 QA 并发），请 team-lead 确认归属与是否纳入 D1 交付范围；若接受，需在 HANDOFF/ledger 记录该变更。
| api_key 一律 env 变量名不入仓 | ✅ | 全仓扫描 `sk-*` / `api_key: "..."` / `Bearer` 零命中；config 示例仅 `api_key_env: "DEEPSEEK_API_KEY"` 等**变量名**，无任何真实 key |
| 无真实 Provider 调用 | ✅ | health 全 UNCONFIGURED 分支短路；review real 无 key 拒发（亲跑 exit=1）；mock 零额度 |

注：`tmpm8v1c53r/` 为 A1 遗留 L2 测试临时目录（autopilot-l2 goals + s/c.db），**早于 D1 交付时间戳**（00:37 vs 00:50），非 D1 新增，未入仓，建议后续清理（低危）。

---

## 5. LiteLLM 复用真实性结论（正式）

**结论：真实复用，符合 §7 Reuse 映射 / §48 门禁。**

1. mock review 通过 `litellm.Router.completion` + `mock_response` 短路返回，**复用 LiteLLM 官方 mock 通道**，非绕过、非自造 fake（插桩证实调用链真实经过 Router）。
2. 真实路径 `_build_router_real` 使用 LiteLLM Router 统一多 provider 接口（100+ Provider 语义由 LiteLLM 承担），key 从 `api_key_env` 对应环境变量读取。
3. 版本落地：litellm 1.83.0 已安装（与 README 声明一致）。
4. 唯一注意：`_probe_litellm` 的 "最小 completion 探测" 在**有 key 且无离线 health_check kind 时**会发真实请求（max_tokens=1）——设计如此（有 key 才真探测），README 已声明；当前环境无 key 不触发，属 L3 责任区。

---

## 6. 缺陷清单（含行号）

| ID | 严重度 | 文件:行 | 缺陷 | 建议 |
|---|---|---|---|---|
| DEF-1 | **中（L3 前必修）** | `r_adapter.py:490-506` | real 模式 `do_review` 用 `pick_provider(cfg, prefer, env)` 在**全部 provider**（含未配置 key 的）上仲裁，但 `_build_router_real(keyed, env)` 只构建 **keyed** provider 的 Router。若 pick 选中未配置 key 的 provider（如 r-prod-chatgpt-web 是 web_session 恒 UNCONFIGURED 且 priority=1），`router.completion(model=<unkeyed id>)` 会抛 BadRequestError（亲跑复现：`You passed in model=r-unconf. There are no healthy deployments`）→ 错误归类为 REAL_CALL_FAILED，掩盖"被选 provider 未配置"的真实语义 | 在 real 分支改为仅对 keyed provider 仲裁：`pick_provider({**cfg,"providers":keyed}, ...)`，或 `_build_router_real` 直接接收 pick 结果；至少在 README §3.5 注明 real 模式必须先保证选中 provider 有 key |
| DEF-2 | 低 | `worker_adapter.config.example.json:13-18` + README §5 L2 worker cli | 示例 worker-local-python 的 entry 是 `[python.exe, "-"]`（stdin 按 **Python 源码**解析），CLI 冒烟喂中文 goal → NameError（亲跑：`产出一份测试报告` → NameError，exit=1）。README 声称 "L2 worker cli echo 回环 ✅ exit 0" 依赖的是测试里 `python -c "print('GOT:'+sys.stdin.read()...)"` 回环，**与示例 config 不一致**，易误导 L3 | 示例 config 增加一个真正的 echo 型 worker（如 `python -c "import sys; print(sys.stdin.read())"`），或 README 明确 `python -` 只接受脚本型 goal |
| DEF-3 | 低 | `r_adapter.config.example.json:8-25` | web_session provider 配置了 `health_check.command`（chatgpt_bridge status），但 `probe_provider` 对 web_session 在 L200-206 **先短路返回 UNCONFIGURED**，health_check 永远不会执行——配置项是死配置，易误导 | 删除该 provider 的 health_check，或在 notes 注明 web_session 探测待 L3 会话注册接入 |
| DEF-4 | 低（文档） | `docs/ops/adapter-README.md §6.3` | D2 成本路由只提"capability-registry costs/quotas 待 D2 校准，本包只读衔接"——但本包 config 示例 **未包含任何 costs/quotas 字段**，D2 若要按 Expected Total Cost 路由需另立数据面（见 §7） | D2 在 adapter config schema 增加可选 `cost`/`quota` 引用段，或由 capability-registry 直接下发 |

---

## 7. 可演进性评估（D2 / A1 / L3 衔接建议）

### 7.1 A1 衔接（relay_autopilot R 单点 → R-Adapter）
- README §3.6 接线建议方向正确：autopilot `mock_review`（scripts/relay_autopilot.py:359）可替换为 `r_adapter.py review --mode mock`（L2），真实审查 `--mode real` + `pick` fallback_chain 实现多 R 热切换。
- **接线建议（架构视角）**：
  1. autopilot 应在 `WAITING_REVIEW→REVIEWING` 段调用 `r_adapter.review` 而非直接写 review-result.json（保持单一真源）；
  2. fallback_chain 消费语义：`do_review(mode=real)` 目前**不会**自动按链重试（只出链，不代执行），需要 autopilot 在 REAL_CALL_FAILED 时按 fallback_chain 顺序重试；建议 D2 把"链消费"做成显式循环并在 ledger 记录 fallback 跳转；
  3. R 并发度=1 的单点排队**不是** R-Adapter 能解的——并发控制仍在 autopilot 状态机（WAITING_REVIEW 门控），Adapter 只解决 Provider 可替换性，README 应避免暗示 adapter 能解并发。

### 7.2 D2 成本路由数据面
- capability-registry 已有 `costs`（8 条，cost_per_call 多为 null"待 D2 校准"）与 `quotas`（6 条，含 quota-codex-strong-review limit=24 次/天）——**数据面已在 registry，但 D1 adapter config 示例未消费**。
- **建议（D2 前置）**：adapter config provider 条目增加可选字段 `cost_ref: "cost-xxx"` / `quota_ref: "quota-xxx"`（引用 registry 节），`pick` 在 priority 相同或持平状态时可加入成本维度（Expected Total Cost）；`review` 返回可附加 `cost_estimate`。注意宪法 §5 语义：成本路由是**调度优化**，不应反向影响 Provider 独立契约。

### 7.3 Worker CLI 契约是否足够表达"弱模型执行/强模型审查"（§5）
- **基本足够，建议增强**：Worker-Adapter 用 `role=worker` + `capabilities` 表达执行面；R-Adapter 用 `kind=api_model/web_session` + review 语义表达审查面——模块边界已区分强弱角色。
- 增强建议：worker config 增加 `strength: "weak"|"strong"` 显式字段（或由 `adapter` 字段推断），使 §5 "资源可替换 + 强弱分工" 机器可读；当前语义散落在 role/type/name，L3 接线时易混淆。

### 7.4 mock/real 切换点清晰度（L3 业主接入）
- **清晰**：L3 只需为 provider 的 `api_key_env` 注入环境变量 → `health` 变 UP → `pick` 选中 → `review --mode real` 即真实调用；README §3.5/§6.1 已写明。
- 注意点：接入前需处理 DEF-1（real 模式选中 provider 必须 keyed）与 DEF-3（web_session 探测未实现）。

---

## 8. 判定

**APPROVED（附 4 项待办，非阻塞）**

- D1 交付满足宪法 §5（Provider 独立 / AI 资源可替换）、§7（LiteLLM 复用真实）、既有 CLI 桥模式一致、红线零违例、39 用例 + CLI 冒烟全过。
- DEF-1 建议在 D2/L3 接线前修复（real 模式仲裁范围与 Router 构建范围不一致）。
- DEF-2/3/4 为低危文档/配置项，随 D2 一并处理即可。
- 遗留：`tmpm8v1c53r/` A1 临时目录建议清理（非 D1 责任）。
- **OBS-1**：审核期间 `pyproject.toml` 出现并发修改（新增 `[project.optional-dependencies] adapters=["litellm==1.83.0"]`），不属冻结清单、方向合理，但与 brief"零修改既有"表述不符，已报 team-lead 确认归属。

---
*审核完毕 — software-architect-d1*

---

## 9. 复审记录（2026-08-30，DEF-1~4 修复闭环）

> 复审人：software-architect-d1（持原始上下文）
> 对象：实现者对 DEF-1~4 的修复 + 新增 TestDef1RealPickScope 3 用例
> 判定：**APPROVED（修复闭环，无需 REWORK）**

### 9.1 复审验证摘要

| 项 | 结果 |
|---|---|
| Python312 全量测试 | ✅ `Ran 47 tests ... OK`（R-Adapter 33 = 原 25 + TestDef1RealPickScope 3 + DEF-D1b litellm 缺失 5；Worker 14） |
| DEF-1 源码核对 | ✅ `do_review` real 分支 L515-522 新增 `cfg_keyed`（仅 keyed provider 子集），`pick_provider(cfg_keyed)` 与 `_build_router_real(keyed)` 范围一致；全无 key 仍先返回 UNCONFIGURED（L496-502） |
| DEF-1 回归测试 | ✅ TestDef1RealPickScope 3 用例：web_session 无 key priority=1 + api_model 有 key priority=2 → 选中 r-api（mock Router 断言 `fake.calls == ["r-api"]`）；prefer 无 key 不采纳回退 keyed；全无 key → UNCONFIGURED |
| DEF-2 config | ✅ worker-echo 条目存在（`python -c "import sys; print(sys.stdin.read(), end='')"`，L28-46）；worker-local-python entry.note 注明脚本型 stdin 契约（L17） |
| DEF-2 README | ✅ §4.1 stdin 契约小节（L131-137）：回显型 vs 脚本型明确区分 |
| DEF-2 亲跑 | ✅ worker-echo 中文 goal 回环 exit 0，**数据层保真**（goal 与 stdout_tail 逐字符一致 MATCH=True；早期 CLI 管道显示乱码系 git bash 终端 GBK 混显，非 adapter 缺陷） |
| DEF-3 config | ✅ r-prod-chatgpt-web health_check 已删除（hc=None），notes 注明 web_session 不适用 file/port 探测 |
| DEF-4 config+README | ✅ 两个 config 示例 top note 均注明 costs/quotas 待 D2（registry 已有数据面）；README §4.3 新增成本路由说明 |

### 9.2 补充观察（非阻塞）
- **编码说明**：worker-echo 中文回环在 Windows 控制台直显可能显示为乱码，但 JSON 输出层（stdout_tail/result）数据保真；建议 L3 调用方以 JSON 解析消费，勿依赖控制台直读（与既有 bridge 的 UTF-8 输出约定一致）。
- **DEF-D1b 加固确认**：新增 5 个 litellm 缺失测试（health/pick/review-real-无key 不依赖 litellm）与实现者 DEF-D1a/D1b 修复呼应，架构上正确——litellm 仅 review-mock / review-real-有key 需要。

### 9.3 复审结论
- 四项 DEF 修复全部到位且验证通过；DEF-1 中危项已由 cfg_keyed 范围收敛解决（含回归测试），D2/L3 接线前无需再改。
- 原 §6 缺陷清单 DEF-1~4 状态：**DEF-1 已修复 / DEF-2 已修复 / DEF-3 已修复 / DEF-4 已修复（文档）**。
- 遗留 OBS-1（pyproject.toml 并发修改归属）与 tmpm8v1c53r 清理仍待 team-lead 处理，与本次复审无关。

*复审完毕 — software-architect-d1*
