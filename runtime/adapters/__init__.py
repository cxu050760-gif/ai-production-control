"""runtime/adapters — D1 全角色 Adapter 独立模块（执衡 v1.1-blackbox）。

宪法 §5 Provider 独立：AI 是资源可替换——R / Brain / Worker 都应有 Adapter。
本包承载机器可完成部分的 Adapter 实现：

  r_adapter.py     R 审查者 Provider 适配层（LiteLLM 接入骨架：health/pick/review）
  worker_adapter.py CLI 型弱模型 Worker 适配层（run/list/health + mock 执行器）

红线（本包内所有模块共同遵守）：
  1) 凭据一律走环境变量（api_key_env），绝不硬编码、绝不入仓；
  2) 真实 Provider 调用（消耗真实 API key / 额度）属 L3 留业主，本包只提供骨架与 mock；
  3) 不修改 src/aicontrol/（Controller TCB 封印）、config/production.json、
     runtime/runtime.py（生产冻结）、config/capability-registry.json（R2 已审）。

Schema 约定（与既有 bridge 一致）：
  - 输出为 inert 数据（non_authority）；任何 authority 词只作数据呈现。
  - 退出码：0=成功；1=配置/输入错误；2=调用失败/超时/不可用。
"""

from __future__ import annotations

ADAPTERS_SCHEMA = "v1.1-d1-adapters"
ADAPTERS_VERSION = "1.0.0"

__all__ = ["ADAPTERS_SCHEMA", "ADAPTERS_VERSION"]
