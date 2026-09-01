# OWNER-NOTICE 20260901-2 — GATE-5 降级登记（4 机制脚手架化）与生产部署同步请求

- 报备人：FINAL_PROMPT v16 收官会话（CatPaw 施工主代理）
- 性质：GATE-5 降级收窄条款要求的 owner-notice 登记（FINAL_PROMPT §4-D：降级仅限特定条目+owner-notice）
- 清点报告：docs/evidence/GATE5-INVENTORY-20260901.md（全表+调用链证据）

## 降级为"脚手架"的 4 机制（非删除，保留代码，能力矩阵标注）

1. workflow reconcile/resume（src/aicontrol/workflow.py:231/:195）——legacy aicontrol 链组件，生产主链（runtime.py）自带等效状态机，Workflow 本体未被主链引用。
2. directives STOP 闸（src/aicontrol/directives.py:53/:119）——仅 legacy pipeline 消费；生产 dispatch 已有等效 STOP（parallel_scheduler.py:804/:891/:1237）。
3. lineage voucher（src/aicontrol/lineage.py:202/:224）——全仓零调用；事实发布链=controller create_candidate+promote_by_review（有测试有调用）。
4. effect_safety record_effect（runtime/effect_safety_lite.py:626）——全仓零调用；生产发送链经 gated_cmd_send→prepare_effect；docstring 自认兼容 facade。

降级依据：生产等效机制在位/legacy 链组件/预留通道。接线它们=向不运行对应对象的主链强插调用，属为接线而接线。

## 请求业主执行/裁决的事项

1. 【部署同步】E:\WB\tools\ai-production-control\runtime\run.cmd 属冻结现役程序（本会话禁改）。仓内副本已改为 APC_PY 注入式（`if not defined APC_PY`）。请业主择机将同款两行修补同步至生产副本（或在下次部署窗口由授权方执行）。
2. 【追认】上述 4 项降级与 capability matrix 的"脚手架"标注。
3. 【备忘】controller.py:972 与 runtimes.py:376 的 node 硬编码（legacy 链）列入 E2 §63/§64 能力注册表批次的 config 注入范围。

回退方案：如业主裁决某机制必须接线而非降级，按 §0.2 在独立批次执行并重走双审。
