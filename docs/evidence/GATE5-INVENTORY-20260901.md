# GATE-5 承诺面清点与处置报告（batch B，2026-09-01）

依据：HARDENING-PLAN-20260831.md GATE-5（承诺面收编——死机制逐个裁决：接线或矩阵降级"脚手架"）+ FINAL_PROMPT v16 §4-D（降级收窄：仅限依赖冻结资产/外部不可达条目+owner-notice 登记）。
清点方法：逐机制 grep 定义→grep 全部调用方→判定主链（生产入口 run.cmd→runtime.py→relay/worker→R review）触达性。清点子代理独立执行，主代理复核。

## 清点结论与处置

| # | 机制 | 定义位置 | 主链触达 | 处置 |
|---|---|---|---|---|
| 1 | workflow reconcile/resume（crash 对账+WAIT 恢复） | src/aicontrol/workflow.py:231/:195 | 未接线（唯一调用=tests/test_workflow.py:129；resume_wait 全仓零调用；Workflow 仅 legacy pipeline.py:72 引用，runtime.py 零触达） | **降级脚手架**：legacy aicontrol 链组件；生产主链 runtime.py 自带状态机与其等效；接线=向不运行 Workflow 的主链强插对象，违背等效性。owner-notice 登记。 |
| 2 | directives STOP（commit_directive/has_work_gate） | src/aicontrol/directives.py:53/:119 | 部分接线（仅 legacy pipeline.py:120/:231 消费；生产 dispatch=goal_contract_lite.py:408 无此闸） | **降级脚手架**：生产已有等效闸（parallel_scheduler.py:804/:891/:1237 独立 STOP 机制）；等效性成立故不强行接线。owner-notice 登记。 |
| 3 | spine COMPLETE 旁路封堵（FINAL_ACCEPTANCE 门） | src/aicontrol/spine.py:399-409 | **已接线有效**：全仓唯一 COMPLETE 写点受门保护，runtime.py 无旁路写 | 无需动。 |
| 4 | lineage voucher（issue_voucher/promote_by_voucher） | src/aicontrol/lineage.py:202/:224 | 未接线（全仓零调用含测试；事实发布链=controller.py:856→:890 create_candidate+:913 promote_by_review） | **降级脚手架**：事实机制为 promote_by_review（有测试有调用）；voucher 为预留发布通道。owner-notice 登记。 |
| 5 | effect_safety record_effect 后门 | runtime/effect_safety_lite.py:626 | 未接线（全仓零调用；生产发送链 run.cmd report→send_guard_lite.py:23 es.install→gated_cmd_send→prepare_effect，不经 record_effect） | **降级脚手架**：docstring 自认兼容 facade，旧调用方已不存在。owner-notice 登记。 |
| 6a | run.cmd APC_PY 硬编码 | runtime/run.cmd:5 | 生产入口每启必经 | **本批接线**：改 `if not defined APC_PY` 注入式（配置注入替代硬编码，规范默认保留）。⚠ E:\WB\tools 生产副本为冻结现役程序，同款修补属部署同步，留 owner-notice 待业主执行。 |
| 6b | harness_verify.py:27-29 路径 | runtime/harness_verify.py | 已有 APC_HARNESS_LAUNCHER/APC_HARNESS_PYTHON/CODEBUDDY_CONFIG_DIR 环境注入（:186/:249/:339/:373） | 无需动（已合规）。 |
| 6c | controller.py:972 node 硬编码 | src/aicontrol/controller.py | legacy 链（同 dict 其余路径均走 self.config） | **降级备忘**：legacy 链，config 注入列入 E2 §63/§64 能力注册表批次。 |
| 6d | runtimes.py:376 node.exe 硬编码 | src/aicontrol/runtimes.py | legacy 链 | **降级备忘**：同 6c。 |

## 汇总

- 死机制 3（#1/#4/#5）→ 全部降级脚手架（理由：legacy 链/等效机制存在/兼容 facade），owner-notice 登记；
- 部分接线 1（#2）→ 降级（生产等效闸在位）；
- 已接线 1（#3）→ 无需动；
- 硬编码 4 处未注入 → 1 处本批接线（6a），2 处 legacy 降级备忘（6c/6d），1 处已合规（6b）。
- 降级=能力矩阵中标注"脚手架（legacy 链/生产等效）"，非删除非隐藏；全部可见于本报告与 owner-notice。
