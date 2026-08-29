# BUILDER_RULING_EGRESS — egress 缺陷定性修正与 TASK-6 授权

裁决人：总设计师 / 主脑
执行对象：Builder（Qwen3.8 Flash 会话）
日期：2026-08-28
绑定规格：`V09_CLOSE_BUILD_SPEC.md` SPEC_SHA256 = `3deccf58…41fa`（不变）
候选：v0.9-b1/authority-effect-core@caedf5f3（10 提交）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §1 主脑独立核验 + 归因修正（重要）

你的判定链（唯一拒绝点、零生产者、规范要"可被许可打开的闸门"、
不改期望）全部核验成立，HARD STOP 行为正确。**但归因中"先于本施工线
存在"一句必须修正**——主脑对接受基座取证如下：

```
e8c53d4（接受基座）:runtime/effect_safety_lite.py
  L131  capability_permitted: bool = True, egress_permitted: bool = True
  —— egress 为参数式，默认 True；全仓无 effect_egress_permitted 状态键
     （基座上该键根本不存在，9 例套件在基座线为绿）

50cf8bd1（b1 replay）→ caedf5f3（候选）:
  effect_safety_lite.py:678  state.get("effect_egress_permitted", False)
  —— 重写为状态键式、默认 False，且未建任何生产者
```

**修正后的定性：这不是历史遗留缺陷，而是 b1 核心升级提交（50cf8bd1）
自身引入的能力回归。** 你的结论（缺陷、禁改期望）不变且反而更强：
规格 §6 第 7 条"已有能力不因 V0.9 修复而回归"直接要求在本轮修复，
**不得推迟到 V0.10**。证据文件 §4 的"先于基线即红"表述由本裁决勘误，
不追究——你对 (c) 做过 e8c53d4 对照、对 (b) 未做，属取证不对称，
本裁决补齐。

## §2 追认（两项主动偏离）

1. **(c) 推翻裁决假设：追认并记功。** 裁决预设"基座绿 + b1 红 = 能力回归
   → 预授权修复"，你实测证明根因是夹具陈旧（intent 缺 b1 必需绑定，
   action rows=0，断言空跑）、胶囊逻辑完好——改产品反会破坏 R33。
    deeper forensics 优于服从假设，这正是纪律想要的行为。
2. **m1 适配"两次 probe 不同 goal"：追认。** 为保真所需，属测试适配
   合理细节；审查包中注明，供审查者复核该保真判断。

## §3 TASK-6（T11）：修复 runtime egress 接线（REPAIR，有界授权）

**授权成立的理由**：回归由 V0.9 核心线引入，收口判据（§6.7）强制修复；
修复性质 = 给既有闸门接上规范要求的"许可判定源"，不是新能力、不是重构。
本裁决对 `runtime/` 的 FORBIDDEN 状态开出**单任务、单位点例外**，
边界如下，任何超出立即 HARD STOP。

- CASE_ID：非矩阵案例（基线回归修复），编号 T11，绑定 9 个具名测试。
- SPEC_CLAUSE：V14 §31 第9条 "Data Egress permits it"（闸门必须可被许可
  打开）；`DATA_EGRESS_POLICY.md`（许可为目的/接收方/provider/Goal/
  授权特定）；规格 §6 第7条（不回归）。
- CURRENT_B1_BEHAVIOR：runtime 发送路径 `egress_permitted` 恒假
  （无生产者），一切合法外发被永久拒绝（9 例绿转红）。
- REQUIRED_BEHAVIOR：
  1) 合法外发（符合 Goal Contract `data_egress_policy` + 数据分级）放行；
  2) 非法外发（SECRET / UNKNOWN / scope 不匹配）在 runtime 发送路径被拒；
  3) 判定输入缺失 → fail-closed（拒绝），不得退回默认放行；
  4) **判定函数必须复用 `src/aicontrol/security.egress_allowed`**
     （其语义已被矩阵 R27-R29 锚定）——禁止在 runtime/ 另写平行的
     egress 判定逻辑，禁止新增策略词汇。
- ROOT_CAUSE：b1 重写把 egress 从"参数传入"改为"状态键读取"，
  未建生产者；键默认 False。
- ALLOWED_FILES（例外清单，穷举）：
  `runtime/runtime.py`（仅发送路径接线）、
  `runtime/effect_safety_lite.py`（仅 `_runtime_preconditions` 取值来源，
  且仅当 runtime.py 无法持久获得判定输入时二选一——在提交说明中论证选址）、
  `runtime/test_v09_close_egress_wiring_offline.py`（新增测试文件）。
- FORBIDDEN_FILES：其余一切；特别是矩阵件、冻结件、`src/**`、
  `config/**`、runtime.py 的任何结构性改动（函数搬家/拆分/改名=越界）。
- IMPLEMENTATION_BOUNDARY：最小接线；若发现最小修复必须把 Goal Contract
  持久化穿过多层才能成立（即超出"接线"量级），**停下上报设计方案**，
  不得自行扩大。
- TEST_REQUIREMENTS：
  1) 9 例红转绿，**期望值一字不改**（它们是验收件）；
  2) 新增负例：经 runtime 发送路径的 SECRET / UNKNOWN / scope 不匹配
     必须被拒（证明不是翻成恒真）；
  3) 新增正例：许可成立时放行且效果被记录；
  4) 矩阵 36/36 保持；`runtime/` 其余套件保持；`tests/` 137 保持。
- REGRESSION_REQUIREMENTS：全量离线套件逐文件对照（目标：真正的全绿，
  达成规格 §4.3 原文判据）。
- EVIDENCE_REQUIREMENTS：接线说明 + 选址论证 + 前后对照入
  `docs/evidence/v09-close/`；DECISION_LEDGER 记两条
  （主脑：T11 授权与 runtime 例外；Builder：实现与选址）。
- EXIT_CRITERIA：全量离线套件零失败 + 矩阵 36/36 + 无新增漂移
  （§4 已裁决项除外）。

## §4 完成后的流程（不变）

TASK-6 收口 → 结果块 v3（精简版：T11 提交 + 全量对照 + 证据路径）→
**独立审查一次审全量**（审查对象 = 含 T11 的最终候选 SHA）。
收口清单遗留三项归属不变：封印（发布负责人）、审查记录（异模型审查者）、
收口状态更新（用户裁决）。

## §5 记录义务

`docs/DECISION_LEDGER.md` 追加（actor=主脑）：
- §1 归因修正（b1 引入，非历史遗留）；
- §2 两项追认；
- §3 T11 授权与 runtime/ FORBIDDEN 例外的边界声明。
