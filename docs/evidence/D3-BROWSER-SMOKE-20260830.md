# D3 实测证据 — Reuse 门禁 / Supply Chain / Playwright（2026-08-30）

> 生成者：software-engineer-d3（v1.1-blackbox 开发线，S3 文件域）
> 生成时间：2026-08-30T17:38Z（UTC）
> 范围：§48-51 Reuse 门禁工具化 + §51 Supply Chain 检查清单 + §20 Playwright 通用网页适配器 + download 命令

## 1. Reuse 门禁三态验证（scripts/reuse_gate.py）

| # | 场景 | 结果 | 退出码 |
|---|---|---|---|
| 1 | `check --task "Playwright 通用网页下载工具" --search playwright download`（普通模式） | GATE_OK；本地命中 cap-browser-download + browser-playwright-cdp；F003 已失败路线警告（BrowserSkill 无通用 download 支持）；gh CLI 未装 → 输出搜索指引；verdict=reuse | 0 |
| 2 | `record --task "Playwright 通用网页下载工具" --decision reuse --evidence "https://playwright.dev/python/docs/downloads"` | 追加 `docs/evidence/reuse-decisions.ndjson`（D3-383007B5） | 0 |
| 3 | `check --task "Playwright 通用网页下载工具" --require-decision` | **GATE_OK**，covering_count=1（已有留痕） | 0 |
| 4 | `check --task "供应链依赖漏洞扫描工具" --require-decision` | **BUILD_BLOCKED**，covering_count=0（无留痕）→ 强制"无 Decision 不得 BUILD" | **1** |

留痕文件：`docs/evidence/reuse-decisions.ndjson`（追加式，每行一个 JSON Decision）。

## 2. Supply Chain 检查清单验证（scripts/supply_chain_check.py）

pip-audit 安装结果：**成功**（默认 PyPI + 代理；清华镜像 403 后兜底成功）。

| # | 场景 | 结果 |
|---|---|---|
| 1 | `check`（本项目 pyproject.toml） | litellm 1.83.0 → **OK**（pip-audit 真实扫描） |
| 2 | `check --packages "urllib3==1.26.4" "requests==2.32.5"` | urllib3 1.26.4 → **VULNERABLE**（PYSEC-2021-108 fix 1.26.5；PYSEC-2023-192 fix 1.26.17/2.0.6）；requests 2.32.5 → **VULNERABLE**（PYSEC-2026-2275 fix 2.33.0）；litellm 仍 OK |
| 3 | 未装 pip-audit 分支 | 全部包 UNKNOWN + 登记待补（代码路径验证，不伪造 OK） |

## 3. Playwright 通用网页适配器 + download（runtime/browser_adapter.py）

Playwright 安装状态：**已装**（chromium 多版本 + headless_shell 在位）；系统 Chrome 存在。
环境注意：全局 `NODE_OPTIONS=--use-system-ca` 会破坏 Playwright node driver → 适配器启动时清除。

### 3a. search 实测 1 次（真实 Bing，2026-08-30T17:37Z）

```
python runtime/browser_adapter.py search --query "playwright python download file" --max 5
```
结果：`result_count=5`，final_url=`https://cn.bing.com/search?q=...`；5 条真实结果（示例）：
1. Playwright 中文网 — https://playwright.nodejs.cn/
2. Playwright 简介 - 菜鸟教程 — https://www.runoob.com/playwright/playwright-intro.html
3. Fast and reliable end-to-end testing for modern web apps | Playwright — https://playwright.dev/
4. Playwright基础使用教程（附完整代码拆解） — https://blog.csdn.net/...
5. Installation | Playwright — https://playwright.dev/docs/intro
每条含 title/url/snippet，结构化 JSON 输出。

### 3b. fetch 实测 1 次（真实 example.com）

`fetch --url "https://example.com/"` → title="Example Domain"、body_text 正常、final_url 同 URL，body_chars=129。

### 3c. download 实测 1 次（真实小文件，§20 验收）

```
python runtime/browser_adapter.py download --url "https://www.python.org/static/img/python-logo.png" \
    --dest "E:/WB/outputs/ai-production-control"
```
结果：
- 文件：`E:\WB\outputs\ai-production-control\python-logo.png`
- mode：`playwright-request`（图片不触发 download 事件 → 走 Playwright APIRequest 流式，仍是 Playwright 机制）
- size：15770 bytes
- sha256：`9c121e619bfe02eaba582d7080eea46fd53ec0b50717e6794a948fada4ae8f3c`

### 3d. mock 冒烟（离线可复现）

`search --mock` → 3 条 mock 结果（标注 mock:true）；`download --mock` → 本地构造文件 + sha256。

## 4. 回归

`python -m unittest discover -s runtime -p "test_*offline.py"`：Ran 447 tests，FAILED (errors=9)——
9 个 ERROR 全部为文档化基线红（D006/D010：provenance/git 链测试），与 D3 新增文件无关；
本刀新增文件不参与 discovery（browser_adapter.py 不匹配 test_* 模式），未引入新失败。

## 5. 交付物清单（S3 文件域）

| 文件 | 类型 |
|---|---|
| `scripts/reuse_gate.py` | 新增：Reuse 门禁工具（check/record/list） |
| `scripts/supply_chain_check.py` | 新增：供应链检查清单 |
| `runtime/browser_adapter.py` | 新增：Playwright 适配器 + download |
| `docs/ops/reuse-gate-README.md` | 新增：说明 |
| `docs/ops/supply-chain-README.md` | 新增：说明 |
| `docs/ops/blackbox-card.md` | 追加：浏览器通用操作/download 用法 |
| `docs/evidence/reuse-decisions.ndjson` | 追加：Decision 留痕（D3-383007B5） |

## 6. 遗留/待办

1. pip-audit 已装但清华镜像偶发 403（默认 PyPI + 代理兜底成功）——README 已注明安装命令；
2. gh CLI 本机未装：reuse_gate `check` 自动回退"搜索指引"模式（GUIDANCE_ONLY），
   调用方用 WebSearch 实测搜索并把结果写入 Decision 留痕；
3. Playwright 全局 NODE_OPTIONS=--use-system-ca 已由适配器启动时清除（只影响子进程）；
4. 正式 test_*.py 由 S4 编写（§8a 分工：S3 只写命令实现 + 冒烟自检）。
