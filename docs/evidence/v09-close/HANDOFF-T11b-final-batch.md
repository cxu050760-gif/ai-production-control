# HANDOFF — T11b 最终批续作检查点（Builder 上下文极限移交）

生成：2026-08-28 · 生成者：Builder（Qwen3.8 Flash 会话，上下文近极限）
裁决链：SPEC `3deccf58…41fa` · R1/R2 `dd9b89e5…b083` · R18 `7e1a714d…467a` ·
R3/R4 `34c18b74…765a1` · TIER2 `17f46a12…765a1→d803` · EGRESS `de4ad566…d1ce` ·
T11B `866b2004…806c` · **AD8TCB `a32e14a4…d8da`（已核验，本工单来源）**
V14 `6fe3bb79…154df6` · BASE `50cf8bd1` · 当前候选 `c0ed87ef250e820404c10112010a8742d1d047c0`（13 提交）

## 0 现场状态（已核）

- worktree `C:/Users/17838/Documents/Qoder/2026-08-28/031cb4e3/b1`，**工作树干净**，
  `LOCAL == origin/v0.9-b1 == c0ed87e`。b2 冻结线仍 `f74d48e`，全程未触。
- 施工位点 = b1 的 worktree（既有线，非新版本线；AD8TCB §1 已核验范围合规）。
- 调用规范：`cd tests && python test_v09_close_*.py`（裸导入共享 Harness）。
- 网络：GitHub 须经本机代理 `127.0.0.1:7897`（shell 不继承系统代理）。
  Python 3.12.10 canonical；**无 pytest**，一律 unittest / 脚本 main()。
- 冻结件现状：`runtime/test_v09_attack_matrix_offline.py` 对 `a0ce691` blob 仍 IDENTICAL；
  夹具仍仅 `spec_anchor` 单行差异。**不得改**（R18 §3 / T0 唯一授权改动）。

## 1 已落地并验证（不需重做）

| 位点 | 内容 | 状态 |
|---|---|---|
| `goal_contract_lite.build_contract` | 新增 `data_egress_policy` 参数，**不入哈希核** | 绿（goal_contract 19/19、Slice A 55/55） |
| `goal_contract_lite.persist_contract` | 写最小投影 `egress_policy_projection{data_egress_policy, source_contract_hash}`；唯一写入者 | 实测 hashbound=True |
| `goal_contract_lite._extract_contract_options` | `--egress-policy-file`（非 JSON object 即拒） | 实测生效 |
| `effect_safety_lite._runtime_egress_permitted` | 判定 100% 委托 `security.egress_allowed`；缺投影/哈希不符/空策略/缺要素 → 拒 | 四向实测 |
| `effect_safety_lite._runtime_preconditions` | 改为 egress 判定；新增可选 destination/provider/purpose | 绿 |
| `_prepare_runtime_send` / `_begin_runtime_send` | 传入四要素（begin 用 record 内值） | 绿 |
| 旧 `effect_egress_permitted` 状态键 | 已不再作为许可来源（防第二块可写策略面） | 绿（effect_safety 5/5） |

egress 单闸门四向实测（`--egress-policy-file` 真值）：无投影拒 / `{}` 拒 /
`{"default":["PUBLIC","INTERNAL"]}` **egress 放行** / 含 SECRET 仍拒 / 仅他目的地策略拒。

全量对照（`c0ed87e`，逐项实测）：矩阵 36/36 + R34 忠实探针 FAIL_CLOSED；
`tests/` 137 全绿；CLOSE 40 全绿；runtime 21 件绿；红 = 4 件（9 例）+ 冻结原件运行器（§4.2 容忍）。
doctor = 1 WARN（journal staleness，预告合法）+ 1 DRIFT（§4 已裁决 registry 滞后），除此之外零漂移。

## 2 **续作必读的新发现：发送路径是三道门串联，不是两道**

AD8TCB §3 工单假设"补 `--egress-policy-file` + TCB 声明"即可让 9 例转绿。
本会话末段实测：egress 放行后依次撞上

1. egress（本批已通）
2. `Controller TCB is not VERIFIED for external effect`
   ← 场景声明 `state["effect_tcb_verified"] = True` **可通过**（已实测；
   注意 `tcb_status="VERIFIED"` 单独设置会转由 EC_GATE 以
   `lifecycle frozen: PAUSE/STOP` 拒绝，rc=5，属不同子系统，勿用此路径）
3. **`EFFECT_SAFETY_DENIED: no authorization bound to effect`**
   ← 需要 run state 内 `effect_authorizations` 有一枚与该 logical effect
   绑定的有效授权（holder/scope/quota/generation/revocation_epoch），
   常规由 `effect_safety_lite.ensure_valid_authorization(rt, state, holder=…, scope=…)` 建立。

⇒ 三处均满足后 9 例才可能转绿。第 3 道门**本会话未验证可行性**（上下文耗尽）。
若第 3 道门需要产品侧签发位点（而非 per-run state 声明）才能满足，
则触及 AD8TCB §2 纪律 1（"声明仅限场景构造，不得触碰产品默认值/闸门逻辑"）
与 T11B §5.b（"最小实现需超出 §2 文件集"）→ **应停下上报，不得自行扩写产品路径**。

## 3 剩余工单（AD8TCB §3 逐条 + 上述修正）

1. **7 处 start 调用**（行号为 `c0ed87e` 时点，续作请重新 grep `"start"` 确认）：
   - `runtime/test_send_guard_offline.py:63`
   - `runtime/test_ec_gate_offline.py:102`（走 RUNTIME）、`:221`（走 ADAPTER）
   - `runtime/test_ec_telemetry_offline.py:89`（RUNTIME）、`:122`（GC）、`:144`、`:157`（ADAPTER）
   每处需：写场景 egress 策略文件并加 `--egress-policy-file`；
   按 §2 用 `effect_tcb_verified=True`（**不要**用 `tcb_status`）；
   以及第 2 节第 3 门所需的授权绑定（先验证是否可纯 per-run state 声明）。
   **期望与断言一字不改**（AD8TCB §2 纪律 4）。
2. `runtime/test_v09_close_egress_wiring_offline.py`（新增，§2 纪律 2 明列验收件，**不得跳过**）：
   - egress 四向负例（§1 表末已实测，落文件即可）；
   - **TCB 负例**：策略齐备但 TCB 未声明 → 拒（证明第二道门未被场景声明架空）；
   - 授权缺失负例（若第 3 门成立）；
   - 正例：三门齐备 → 放行且效果被记录（transport log 有行、状态非 HARD_BLOCKED）。
3. AD-8 登记册（§2 纪律 3）：逐点位列出全部适配（egress 策略文件 7 处 + TCB 声明 7 处 +
   授权绑定各处），每条注明"场景构造，期望未改"。
4. 台账：D014（主脑：AD8TCB 裁定，actor=主脑 转录）+ 实现条目（actor=Builder，
   含三门链与选址论证）。
5. 出口判据：全量离线套件**真正全绿**（§4.3 原文判据首次达成，届时冻结原件运行器
   仍按 §4.2 单独口径处理）+ 矩阵 36/36 + `tests/` 137 + CLOSE 40 + 无新增漂移。

## 4 一键复现探针（本会话用它取证，续作可直接沿用）

`send_guard_lite.py start --egress-policy-file` + 改 `state.json` 的 `effect_tcb_verified`，
再 `send`，逐 key 打印 rc 与 reason —— 见本文件 §2 的三个观测值来源。
注意：`--r-url` 必须是 `https://chatgpt.com/c/<uuid>` 形态，否则 `start` 直接 rc=3 `INVALID_R_URL`。

## 5 边界自证（本会话未越界）

本次检查点提交**仅新增本文件**；未改任何产品代码、测试、期望、断言、状态字段。
`release_status` 仍 `PRODUCT_NOT_READY`；开发头仍 `b2@a0ce691`（未晋升）；
TCB 仍 `UNVERIFIED_AFTER_CONTROLLER_CHANGE`（收口清单第 1 项，属发布负责人）。
