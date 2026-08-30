# AI 反代方案调研报告（GitHub 2026-08 版 · 18 候选）

- 生成：2026-08-30 00:50（修订 v7 最终）· 调研执行：DeepSeek-V4-Flash-20260829 · RUN: RUN-20260830-000926-cfb5
- 修订 v7 说明：按 R 六轮意见——Cognee（记忆平台）移出 B 类、Jan（桌面应用）移出 E 类（非代理/转发层）；C 类补 Envoy Gateway 至 3 个云原生网关；候选 18 项（A5+B3+C3+D4+E3）；分类/编号/总表/Top5 同步
- **数据核实方式**：全部 Star / License / 最近推送时间通过 GitHub API（api.github.com）于 2026-08-29/30 实测
- 核实状态：**【API 实测】** = 数据来自 GitHub API 仓库页（stars/license/pushed 三字段）；功能描述来自项目 README/官方文档
- 活跃度说明：**最近推送时间（pushed）仅为活跃度参考，不等于项目健康度**；活跃度需结合维护频率、issue 响应等多因素判断
- 声明：所有方案开源/自托管；聚合/转售 API 的合规性以各上游服务条款为准，使用前须自行审阅

---

## 一、分类总览（18 候选）

| 分类 | 项目 |
|---|---|
| A. 统一 LLM 网关（多 Provider 路由/负载均衡/成本管控） | LiteLLM、Portkey Gateway、Bifrost、plano、LLM Gateway |
| B. 缓存与可观测代理（降本/监控） | GPTCache、Helicone、semantic-router |
| C. 云原生 AI 网关（K8s 生态） | Higress、Envoy AI Gateway、Envoy Gateway |
| D. Key 聚合与免费档中转（个人自建） | one-api、new-api、OmniRoute、FreeLLMAPI |
| E. 本地推理代理/转发层（本地运行+统一接口） | Ollama、llama.cpp、LocalAI |

*候选共 18 项（A 5 + B 3 + C 3 + D 4 + E 3），全部 GitHub API 实测。*

---

## 二、逐项调研

### A. 统一 LLM 网关

#### 1. LiteLLM — 【API 实测】
- **仓库**: https://github.com/BerriAI/litellm · stars=57,533 · License: MIT（GitHub 标注 NOASSERTION）· 最近推送 2026-08-29
- **核心能力**（官方文档）：统一 OpenAI 兼容端点对接 100+ Provider；负载均衡、自动 fallback、支出追踪、虚拟 Key、预算管控
- **适用**：企业/团队统一网关、防限频、成本管控
- **部署复杂度**：低（Docker 或 pip；团队功能需 PostgreSQL）
- **契合度**：★★★★★

#### 2. Portkey Gateway — 【API 实测】
- **仓库**: https://github.com/Portkey-AI/gateway · stars=12,853 · License: MIT · 最近推送 2026-05-25
- **核心能力**（官方文档）：路由 1,600+ LLM；guardrails；条件路由；可观测
- **适用**：企业治理、受监管场景
- **部署复杂度**：中（云托管或自托管）
- **契合度**：★★★★

#### 3. Bifrost — 【API 实测】
- **仓库**: https://github.com/maximhq/bifrost · stars=7,642 · License: Apache-2.0 · 最近推送 2026-08-29
- **核心能力**（官方文档）：Go 网关，负载均衡、语义缓存、集群模式
- **适用**：高吞吐生产
- **部署复杂度**：低（NPX/Docker）
- **契合度**：★★★★

#### 4. plano（原 archgw）— 【API 实测】
- **仓库**: https://github.com/katanemo/plano · stars=7,022 · License: Apache-2.0 · 最近推送 2026-08-19
- **核心能力**（官方文档）：Rust AI-native 代理（Envoy 数据面）、语义路由、guardrails、可观测
- **适用**：Agentic 应用
- **部署复杂度**：中（Envoy）
- **契合度**：★★★

#### 5. LLM Gateway — 【API 实测】
- **仓库**: https://github.com/theopenco/llmgateway · stars=1,586 · License: NOASSERTION · 最近推送 2026-08-29
- **核心能力**（官方文档）：TypeScript 网关，多 Provider 路由、用量分析，OpenAI 兼容
- **适用**：轻量自建、统一接入
- **部署复杂度**：低
- **契合度**：★★★

### B. 缓存与可观测代理

#### 6. GPTCache — 【API 实测】
- **仓库**: https://github.com/zilliztech/GPTCache · stars=8,172 · License: MIT · 最近推送 2025-07-11（维护放缓）
- **核心能力**（官方文档）：语义缓存中间件（向量相似度命中）
- **适用**：高频重复查询降本
- **部署复杂度**：中（需向量库）
- **契合度**：★★★

#### 7. Helicone — 【API 实测】
- **仓库**: https://github.com/Helicone/helicone · stars=6,114 · License: Apache-2.0 · 最近推送 2026-08-26
- **核心能力**（官方文档）：反代网关 + 可观测；响应缓存、限流、成本追踪
- **适用**：生产监控
- **部署复杂度**：中
- **契合度**：★★★


#### 8. semantic-router — 【API 实测】
- **仓库**: https://github.com/aurelio-labs/semantic-router · stars=3,849 · License: MIT · 最近推送 2026-08-24
- **核心能力**（官方文档）：超快速语义路由（按意图分发请求）
- **适用**：智能路由、意图分发
- **部署复杂度**：低
- **契合度**：★★★

### C. 云原生 AI 网关

#### 9. Higress — 【API 实测】
- **仓库**: https://github.com/higress-group/higress · stars=9,237 · License: Apache-2.0 · 最近推送 2026-08-29
- **核心能力**（官方文档）：云原生 AI API 网关 + K8s Ingress；协议转换、模型代理、语义缓存、MCP 托管
- **适用**：K8s 环境
- **部署复杂度**：高（K8s）
- **契合度**：★★★

#### 10. Envoy AI Gateway — 【API 实测】
- **仓库**: https://github.com/envoyproxy/ai-gateway · stars=1,974 · License: Apache-2.0 · 最近推送 2026-08-28
- **核心能力**（官方文档）：CNCF/K8s 原生统一 GenAI 访问
- **适用**：K8s 原生团队
- **部署复杂度**：高（K8s）
- **契合度**：★★

#### 11. Envoy Gateway — 【API 实测】
- **仓库**: https://github.com/envoyproxy/gateway · stars=2,997 · License: Apache-2.0 · 最近推送 2026-08-28
- **核心能力**（官方文档）：Envoy 作为独立或 K8s 应用的网关管理（Envoy AI Gateway 的底层基础设施）
- **适用**：K8s 网关基础设施
- **部署复杂度**：高（K8s）
- **契合度**：★★



### D. Key 聚合与免费档中转

#### 12. one-api — 【API 实测】
- **仓库**: https://github.com/songquanpeng/one-api · stars=36,640 · License: MIT · 最近推送 2026-01-09（更新放缓，生态成熟）
- **核心能力**（官方文档）：统一 OpenAI 格式对接几乎所有模型；Key 管理、渠道负载均衡、故障切换、额度管控
- **适用**：个人自用、小型中转
- **部署复杂度**：极低（Docker）
- **注意事项**：项目 README 含服务合规提示，个人自用场景
- **契合度**：★★★★★

#### 13. new-api — 【API 实测】
- **仓库**: https://github.com/QuantumNous/new-api · stars=46,736 · License: AGPL-3.0 · 最近推送 2026-08-29
- **核心能力**（官方文档）：one-api 增强版：多租户、细粒度计费、内置支付、监控、Ollama 接入
- **适用**：多租户/商用
- **部署复杂度**：低（Docker）
- **契合度**：★★★★★

#### 14. OmniRoute — 【API 实测】
- **仓库**: https://github.com/diegosouzapw/OmniRoute · stars=57,921 · License: MIT · 最近推送 2026-08-29
- **核心能力**（官方文档）：一个端点对接多 Provider；Combos 自动 failover；免费档聚合
- **适用**：个人多 Provider 聚合、防限频
- **部署复杂度**：低（npm/Docker）
- **契合度**：★★★★★

#### 15. FreeLLMAPI — 【API 实测】
- **仓库**: https://github.com/tashfeenahmed/freellmapi · stars=22,070 · License: MIT · 最近推送 2026-08-28
- **核心能力**（官方文档）：OpenAI 兼容代理聚合多家免费档；自动 failover、加密 Key 存储
- **适用**：个人免费档聚合
- **注意事项**：聚合第三方免费档合规风险最高，使用前必须自行审阅上游条款
- **契合度**：★★★

---

## 三、对比总表（18 项全字段）
| 1 | LiteLLM | 57,533 | MIT | 2026-08-29 | 低 | 统一网关/负载均衡/成本 | 企业统一接入 | API 实测 |
| 2 | Portkey | 12,853 | MIT | 2026-05-25 | 中 | 路由/guardrails | 企业治理 | API 实测 |
| 3 | Bifrost | 7,642 | Apache-2.0 | 2026-08-29 | 低 | 高吞吐网关/语义缓存 | 生产高并发 | API 实测 |
| 4 | plano | 7,022 | Apache-2.0 | 2026-08-19 | 中 | Agentic 代理 | Agent 应用 | API 实测 |
| 5 | LLM Gateway | 1,586 | NOASSERTION | 2026-08-29 | 低 | 多Provider路由+分析 | 轻量自建 | API 实测 |
| 6 | GPTCache | 8,172 | MIT | 2025-07-11 | 中 | 语义缓存 | 高频查询降本 | API 实测 |
| 7 | Helicone | 6,114 | Apache-2.0 | 2026-08-26 | 中 | 反代+可观测 | 生产监控 | API 实测 |
| 8 | semantic-router | 3,849 | MIT | 2026-08-24 | 低 | 语义路由 | 意图分发 | API 实测 |
| 9 | Higress | 9,237 | Apache-2.0 | 2026-08-29 | 高 | 云原生网关/MCP | K8s 环境 | API 实测 |
| 10 | Envoy AI GW | 1,974 | Apache-2.0 | 2026-08-28 | 高 | K8s 原生网关 | K8s 原生 | API 实测 |
| 11 | Envoy Gateway | 2,997 | Apache-2.0 | 2026-08-28 | 高 | Envoy 网关管理 | K8s 基础设施 | API 实测 |
| 12 | one-api | 36,640 | MIT | 2026-01-09 | 极低 | Key 聚合/中转 | 个人自用 | API 实测 |
| 13 | new-api | 46,736 | AGPL-3.0 | 2026-08-29 | 低 | 多租户中转 | 商用 | API 实测 |
| 14 | OmniRoute | 57,921 | MIT | 2026-08-29 | 低 | 多 Provider 聚合/failover | 个人聚合 | API 实测 |
| 15 | FreeLLMAPI | 22,070 | MIT | 2026-08-28 | 低 | 免费档聚合 | 个人免费聚合 | API 实测 |
| 16 | Ollama | 179,721 | MIT | 2026-08-29 | 低 | 本地推理+统一API | 本地/离线 | API 实测 |
| 17 | llama.cpp | 126,210 | MIT | 2026-08-29 | 中 | 高性能推理引擎 | 裸金属推理 | API 实测 |
| 18 | LocalAI | 48,745 | MIT | 2026-08-29 | 低 | 本地OpenAI兼容 | 本地服务 | API 实测 |
## 四、Top 5 推荐（个人多 Provider 聚合 / 防限频 / 成本管控场景）

| 排名 | 项目 | 选择依据（对目标场景的实际能力） |
|---|---|---|
| 1 | LiteLLM | 目标场景核心能力全覆盖：100+ Provider 统一接口、自动 fallback（防限频）、支出追踪与虚拟 Key（成本管控）；社区最大、活跃；个人部署门槛低（Docker） |
| 2 | OmniRoute | 专为"多 Provider 聚合 + 自动 failover"设计（Combos 策略）；个人场景开箱即用（npm/Docker）；活跃 |
| 3 | one-api | 轻量自用门槛最低（SQLite Docker 一键）；Key/渠道管理完整；适合个人中转；注意更新放缓（2026-01） |
| 4 | new-api | 在 one-api 基础上补多租户/细粒度计费/监控，适合从个人走向多用户；活跃（2026-08-29） |
| 5 | Bifrost | 高吞吐生产场景的性能补充选项（Go 实现、低开销）；若个人场景对延迟/并发敏感可选 |

*推荐依据 = 与"个人多 Provider 聚合、防限频、成本管控"目标场景的能力匹配度 + 活跃度，非单纯 Star 排序。*

---

### E. 本地推理代理/转发层

#### 16. Ollama — 【API 实测】
- **仓库**: https://github.com/ollama/ollama · stars=179,721 · License: MIT · 最近推送 2026-08-29
- **核心能力**（官方文档）：本地模型运行器，OpenAI 兼容 API（localhost:11434），一键拉取/运行数千模型
- **适用**：本地/离线推理、隐私优先
- **部署复杂度**：低（安装即用）
- **契合度**：★★★★★（执衡本地链天然搭档）

#### 17. llama.cpp — 【API 实测】
- **仓库**: https://github.com/ggml-org/llama.cpp · stars=126,210 · License: MIT · 最近推送 2026-08-29
- **核心能力**（官方文档）：底层 C++ 推理引擎，最高性能、结构化输出（grammar 约束）
- **适用**：性能压测、裸金属推理
- **部署复杂度**：中（需手动管理模型文件）
- **契合度**：★★★★


#### 18. LocalAI — 【API 实测】
- **仓库**: https://github.com/mudler/LocalAI · stars=48,745 · License: MIT · 最近推送 2026-08-29
- **核心能力**（官方文档）：自托管 OpenAI 兼容 API，本地模型+容器化部署，多后端
- **适用**：本地 OpenAI 兼容服务
- **部署复杂度**：低（Docker）
- **契合度**：★★★★


## 六、注意事项（通用）

1. **合规**：聚合/转售 API 的合规性以各上游服务条款为准（多数厂商禁止未授权转售/再分发）；对国内公众提供生成式 AI 服务涉及备案要求。**个人自用相对安全，对外服务需专业法务审阅**
2. **供应链安全**：部署开源网关应锁定版本并校验依赖哈希（供应链风险属通用安全实践）
3. **默认凭据**：部署自托管网关后应立即修改管理员口令（遵循项目 README 指引）
4. **免费档稳定性**：免费聚合类项目（OmniRoute/FreeLLMAPI）的可用性依赖上游免费档政策，勿作生产硬依赖
5. **活跃度**：GPTCache（2025-07 停止推送）、one-api（2026-01 放缓）——选型时权衡生态成熟度 vs 持续维护

## 七、与执衡项目本地链的对接建议

执衡当前生产链路 = catpaw 反代 + chatgpt_bridge + bsk + Runtime V1。扩展多 Provider 聚合/防限频：
- **首选**：LiteLLM 或 OmniRoute 作为统一网关层（复用成熟资产原则）
- **备选**：one-api 轻量自用
- **缓存降本**：GPTCache 可选叠加
- **本地推理**：Ollama 补充隐私场景
- 接入方式登记见 `docs/ops/local-chain-calls.md` 与 `docs/ops/fusion-access.md`
