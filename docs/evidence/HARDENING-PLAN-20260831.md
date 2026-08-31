# HARDENING-PLAN-20260831 — P0 加固施工总纲

- 分支：`hardening/p0-gates-20260831`（自 v1.1-blackbox@21352f2）
- 施工：CatPaw（业主授权 2026-08-31）
- 审核流程：每闸口完成 → 内部审核（独立子智能体，仅凭 diff+证据，不见施工自述）→ 外部审核（业主 ChatGPT 通道，经桥投审）→ 双签后合入 v1.1-blackbox
- 纪律：默认 fail-closed；每改必测（含恶劣条件）；证据入仓；单测不得读写真实 state/；宣称必须附机器输出文件

## 闸口清单

### GATE-1 门禁封堵（P0，审计发现 1-5）
| # | 病灶 | 修法 | 验收 |
|---|---|---|---|
| 1 | run.cmd:25 report 不走 effect_safety/ec 闸 | report 路径接入与 work 同闸门 | 离线测试：report 无闸时拒发；闸在时放行 |
| 2 | relay_autopilot.py:299 伪造 40 位 hex commit | 缺 candidate-commit → fail-closed 拒投 | 测试：缺 commit 必 BLOCKED，无随机生成路径 |
| 3 | FROZEN verdict 未被三闸拦截 | verdict 枚举统一：SAFE_HALT∪FROZEN 均拒 | 测试：FROZEN goal 重投被拒 |
| 4 | 三闸 except fail-open（relay_autopilot.py:119/132/155） | 全改 fail-closed（异常=BLOCKED） | 测试：配置损坏/异常注入 → BLOCKED |
| 5 | OUTCOME_UNKNOWN 无对账出口（effect_safety_lite.py:848-864） | reconcile_effect 接 CLI 入口 + retry 解锁路径 | 测试：模拟 UNKNOWN → reconcile → 可重发 |

### GATE-2 并发原子性（P0，审计发现 6-9）
| # | 病灶 | 修法 | 验收 |
|---|---|---|---|
| 6 | controller_lease acquire 无锁竞态、无 fsync、revoked 不查、无 revoke | 文件锁原子 acquire + fsync + revoked 检查 + revoke API | 并发双 acquire 测试仅一胜者 |
| 7 | parallel_scheduler 锁不回滚死锁 + reap_stale 不停 CLI | 申请失败回滚已持锁 + 停止信号接 CLI 进程 | 反序申请不死锁；stale 进程被终止 |
| 8 | runtime.py RunLock 空文件竞态 / relay+guard mkdir 锁窗口 | 原子写（tmp+rename）、锁信息缺失=等待非抢占 | 并发锁测试 |
| 9 | controller.py:723 IndexError | 空 artifact fail-closed 报错 | 测试 |

### GATE-3 测试还账（P0，审计发现 10-13）
| # | 病灶 | 修法 | 验收 |
|---|---|---|---|
| 10 | 权威矩阵恒绿（test_v09_attack_matrix_on_b1_core.py:409） | 改真 unittest 断言（36 例全检） | 人为 MISMATCH 注入 → 测试红 |
| 11 | wiring 测试污染真实 state/ | cost/lease 闸注入 tmp state 根 | 哨兵测试证明 state/ 零触碰 |
| 12 | self_heal t08-t10 静默 skip | skip → 显式 FAIL（缺前置=红） | 移除 PRE_FIX 后必红 |
| 13 | 租约过期无 admission 负例 | 补"过期租约→BLOCKED"用例 | 新用例过 |

### GATE-4 治理清账
PROJECT_STATE.md 降级为历史快照+指向 json 唯一真源；TCB 按 AGENTS 口径重封（含 runtime 面，需重算 manifest）；state_doctor 移出自豁免；tmp-polaris/tmpm8v1c53r/state 测试残留清理；branch_registry 冻结锚统一口径（代码冻结@793fa41，治理文档后追加须声明）。

### GATE-5 承诺面收编
死机制逐个裁决：接线（workflow reconcile/resume、directives STOP、spine COMPLETE 旁路封堵、lineage voucher、effect_safety record_effect 后门）或矩阵降级"脚手架"；硬编码路径（C:\Program Files\nodejs、C:\Users\17838）改配置注入。

### GATE-6 两环转真
拆解：task_graph/brain_bridge 接 brain_bridge 真实契约（去关键词 stub，或明确标注规则模式）；并行：parallel_scheduler 接入 relay_autopilot 主链（真实执行器）。完成后北极星=全真链。

## 送审批次
- 批次 A：GATE-1+2+3（P0 硬修复）
- 批次 B：GATE-4+5
- 批次 C：GATE-6
每批：内部子代理审核（盲审 diff）→ 修正 → 桥投外部审 → 双签合入。

## 业主参与点
- 批次 A/B 审核通过后：无需业主
- GATE-6 后：业主提供 DeepSeek key（≈10 元）跑真实 Provider 项 + 真实业务目标
- 全部后：三条抽查命令 + §74 终裁
