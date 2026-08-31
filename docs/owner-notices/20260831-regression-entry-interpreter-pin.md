# OWNER-NOTICE 20260831 — FINAL_PROMPT 回归入口锚定修订报备（三元→四元：钉死生产解释器全路径）

- 报备人：FINAL_PROMPT v16 收官会话（CatPaw 施工主代理）
- 时间：2026-08-31（会话内实时报备，不等待，按 §0.2 报备即动继续）
- 性质：**§9 规定的"施工 AI 修订=新提交+owner-notice，可见不可藏"**——修订对象为
  FINAL_PROMPT.md §5③ 与 §9 对账任务书模板中的回归入口命令口径（仅加法澄清，不改判据）。

## 发现（8-31 实测）

git bash 中裸 `python` 解析到 `C:\Users\17838\.meituan-catpaw\runtimes\python\versions\3.12.13\python.exe`
（CatPaw 托管运行时 Python 3.12.13），该环境**无 litellm、无 playwright**：
- `runtime/adapters/test_r_adapter_d1_offline.py` 5 例假失败（mock review 走 `from litellm import Router`
  → ImportError → LITELLM_NOT_INSTALLED 路径 → ok=False）；
- `runtime/test_browser_adapter_d3_offline.py` 1 例假失败（`chromium_installed()` 内
  `import playwright` ImportError → except → False，仅 test_true 断言 True 故红）。

用生产解释器全路径 `C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`
（Python 3.12.10，litellm/playwright 齐备）复跑同套件 → 全绿定性（真断言、无产品缺陷）。
第 1 轮全量回归以钉死解释器执行：runtime 639 OK + tests 219 OK，95s，state/ 零污染。

## 修订内容（两处，纯加法）

1. §5③ "3 连绿"亲验入口命令：钉死生产解释器全路径，**禁裸 `python`**；锚定由三元
   （工作目录/状态根/入口命令）扩为四元（+解释器）。
2. §9 对账代理任务书模板：同步同一解释器钉死口径（防对账代理亲跑踩同一坑 → 误判
   REWORK"回归不绿"）。

## 为何必须修订（不修订的后果）

任务书原文只写 `python -m unittest discover`，对账代理在 clone 中亲跑时若解析到托管运行时
Python，将稳定复现 6 假失败 → 整里程碑被误判 REWORK；反之若对账代理"解释器不同也放行"，
则又违反独立复判。钉死解释器使主代理 2 轮直录与对账亲跑**同解释器同口径**，数字才可对照
（§5②"regression log 关键行与亲跑结果数字对照"才可执行）。

## 请求业主

追认本修订（或批示回退）。回退不影响继续施工：判据本身（639+219 全绿）不变，
仅解释器口径表述变化。
