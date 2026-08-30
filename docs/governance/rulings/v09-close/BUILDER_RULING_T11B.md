# BUILDER_RULING_T11B — T11b 开设：runtime 出站许可接线（方案 B，有界授权）

裁决人：总设计师 / 主脑
执行对象：Builder（Qwen3.8 Flash 会话）
日期：2026-08-28
绑定：SPEC `3deccf58…41fa` · V14 `6fe3bb79…154df6` · 前裁决 `BUILDER_RULING_EGRESS`（de4ad566…d1ce）
候选：v0.9-b1/authority-effect-core@cb1af90（12 提交，其中 2 提交为纯文档）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §1 对你设计上报的核验与采信

- 停下触发正确（EGRESS 裁决 §3 IMPLEMENTATION_BOUNDARY 原文条款）。
- 取证链采信：`egress_allowed` 必需 `data_egress_policy`，runtime 侧零命中；
  四个失败套件子进程运行、仅 JSON state、无 Controller 可达 → **A 被证据排除**；
  C 使验收件退化为测试自证且引入新策略载体 → **排除**。
- 主脑补充核验：`runtime/goal_contract_lite.py` 无 egress 结构；
  但 send_guard 套件**已经**通过 `goal_contract_lite` 构造 goal contract
  （state 中已有 `goal_contract_hash`）。这为方案 B 提供了现成挂点，
  也定义了测试适配的合法形态（见 §3.4）。
- 结论：**方案 B 是唯一可行路线，予以授权**，边界如下。

## §2 T11b 授权范围（穷举）

- CASE：T11b（T11 的受控升级），目标不变 = 出站闸门"可被许可打开"，
  许可语义与矩阵 R27-R29 同源。
- ALLOWED_FILES：
  1) `runtime/runtime.py`——仅 run 创建/状态持久化位点的**增量字段写入与读取**；
  2) `runtime/goal_contract_lite.py`——仅当契约构造是许可派生的自然挂点时
     （提交说明中论证选址）；
  3) `runtime/effect_safety_lite.py`——仅 `_runtime_preconditions` 的 egress
     取值改为调用判定函数；
  4) `runtime/test_v09_close_egress_wiring_offline.py`（新增测试文件）；
  5) 四个失败套件 + `test_effect_safety_offline.py` 的**场景构造适配**
     （规则见 §3.4，期望与断言除外）。
- FORBIDDEN：其余一切；特别是——不得新增独立策略载体（文件/配置面），
  不得新增策略词汇，不得把判定逻辑搬离 `security.egress_allowed`，
  不得改动任何期望值/断言文本，不得结构性重构（函数搬家/拆分/改名）。
- **封印面说明**：`runtime/**` 不在项目 TCB 清单（TCB = src/aicontrol/**、
  ai-control.cmd、scripts/ai_control.py、config/production.json、
  package-lock.json），T11b **不扩大**既有封印缺口；封印仍按收口清单
  第 1 项由发布负责人执行。

## §3 设计约束（逐条强制）

1. **权威关系**：run state 中的出站许可必须由 Goal Contract 派生
   （契约构造/运行创建时刻写入），并与 state 既有的 `goal_contract_hash`
   绑定（许可投影携带其来源契约哈希；哈希不匹配/缺失 → 拒绝）。
   许可投影不得成为任何其它代码路径的独立可写策略面。
2. **判定函数 100% 复用** `src/aicontrol/security.egress_allowed`，
   输入 = 投影出的 `data_egress_policy` + 发送点既有四要素
   （classification/destination/provider/purpose）。零平行逻辑。
3. **最小投影**：只持久化判定所需（`data_egress_policy` + 来源契约哈希），
   不整包持久化 Goal Contract；选型差异在提交说明中论证。
4. **测试适配规则（AD-8）**：测试**场景构造**可以声明契约的出站策略
   （等价于生产里 GOAL/契约携带策略——矩阵 Fixture 在 canonical 侧
   同样自造 goal contract，先例成立）；但期望输出与断言一字不改。
   "测试写策略 = 测试自证放行"的担忧由两条纪律消除：
   (i) 闸门判定真实发生且负例证明其能拒绝；(ii) 每处适配逐条登记编号。
5. **兼容与失败语义**：schema 仅增量；旧 state 文件（无新字段）必须
   可加载且表现为"拒绝"（不得崩溃、不得默认放行）。
6. **写入者限制**：新字段只允许 runtime 自身代码路径写入；
   任何 Worker/模型输出通道不得触达（设计说明中点名写入者清单）。

## §4 验收与回归（出口判据）

1. 9 例红转绿，期望/断言零改动；全部 AD-8 适配逐条登记。
2. 新增负例（经 runtime 发送路径）：SECRET 恒拒、UNKNOWN 拒、
   scope/目的地不匹配拒——同一机制，证明非恒真。
3. 新增正例：策略许可成立 → 放行且效果被记录。
4. 回归面（你列 + 主脑确认）：`test_state_recovery_offline`（兼容性）、
   j4 跨进程一致性、Slice A 冻结契约（AC 清单）、`runtime/` 全量、
   `tests/` 137、CLOSE 40、矩阵 36/36（含 R34 忠实探针）。
5. doctor：除已裁决的 registry 滞后外零漂移。
6. 证据入 `docs/evidence/v09-close/`；DECISION_LEDGER 记
   （主脑：T11b 授权；Builder：实现、选址、写入者清单、AD-8 清单）。

## §5 停止阀（预先裁决，避免再来回）

实施中若发现任一情形，**停下上报，不得变通**：
a. "9 例期望不改转绿"在任何合法闸门语义下不可达（即某期望本身与
   真实闸门矛盾）——届时主脑将在"规范绑定的期望修订"与"登记已知红
   提请用户签署"之间裁决，你不预支该决定；
b. 最小实现需要超出 §2 文件集（例如 router 协议层）；
c. 任何"为翻绿而放宽默认值"的诱惑（默认许可 = 立即 HARD STOP）。

## §6 流程（不变）

T11b 收口 → 结果块 v4（精简：提交 + 全量对照 + 证据路径）→
独立审查一次审全量；T11b 改动区（runtime 出站接线 + AD-8 清单）
将在审查包中标为**最高审查权重区**。
