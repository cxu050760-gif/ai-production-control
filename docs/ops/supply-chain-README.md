# Supply Chain Check README — §51 依赖供应链检查清单（D3）

> 对应宪法：§51 Supply Chain 依赖供应链检查（pip-audit / osv-scanner 类）。
> 报告 §7 已调研结论 = **直接复用 pip-audit**（不重复造轮子，符合 §48 Reuse 门禁）。
> 本工具输出机器可读检查清单：依赖名/版本/来源/漏洞状态(OK|VULNERABLE|UNKNOWN)/建议动作。

## 一句话

```
python scripts/supply_chain_check.py check
```

- 扫描本项目 `pyproject.toml` 的依赖（含 optional-dependencies）→ 输出清单。
- 若 pip-audit 可用，执行真实漏洞扫描并映射到每个包；不可用时一律 `UNKNOWN` + 登记待补，
  **绝不因网络停摆伪造结果**。

## 用法

```bash
# 默认：扫本项目 pyproject.toml
python scripts/supply_chain_check.py check

# 指定 requirements.txt
python scripts/supply_chain_check.py check --requirements requirements.txt

# 显式依赖列表（会生成临时 requirements 交给 pip-audit 真实扫描）
python scripts/supply_chain_check.py check --packages "requests==2.32.5" "urllib3==1.26.4"
```

## 输出字段

每行依赖项（`dependencies[]`）：

| 字段 | 含义 |
|---|---|
| `name` | 包名 |
| `version` | 声明版本 / 已安装版本（未 pin 时经 importlib.metadata 解析） |
| `source` | `PyPI`（外部）或 `LOCAL`（本地路径/URL 依赖） |
| `vuln_status` | `OK`（pip-audit 扫描无漏洞）\| `VULNERABLE`（有已知漏洞）\| `UNKNOWN`（pip-audit 不可用） |
| `vulnerabilities` | 漏洞明细（id / fix_versions / aliases / description） |
| `action` | 建议动作（升级到修复版本 / 登记待补） |

顶层 `pip_audit` 字段报告扫描器状态：`available` + `status`（OK / PIP_AUDIT_NOT_INSTALLED / 运行错误）。

## pip-audit 安装（网络坑已实测）

```bash
# 首选：代理 + 清华镜像（注意：清华镜像偶发 403，失败则用下面纯代理）
C:/Users/17838/AppData/Local/Programs/Python/Python312/python.exe -m pip install pip-audit \
    --proxy http://127.0.0.1:7897 -i https://pypi.tuna.tsinghua.edu.cn/simple

# 兜底：默认 PyPI + 代理（2026-08-30 实测成功）
C:/Users/17838/AppData/Local/Programs/Python/Python312/python.exe -m pip install pip-audit \
    --proxy http://127.0.0.1:7897
```

**pip-audit 装不上不阻塞**：脚本探测不到 pip-audit 时所有包标 `UNKNOWN` 并输出安装指引，
工具登记"待补"状态继续（§8 纪律：不因网络停摆）。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 检查完成（无论 OK/UNKNOWN；发现漏洞仍为 0，报告性质，非门禁） |
| 1 | 运行错误（如 requirements 文件缺失→返回 2；写临时文件失败等） |
| 2 | 用法错误（requirements 文件不存在） |

## 红线

1. 本工具只读扫描与报告，不做任何安装/卸载（pip-audit 扫描本身只读）；
2. pip-audit 不可用时输出 `UNKNOWN` 并登记待补，不伪造 `OK`；
3. 不改任何冻结文件；输出为 inert 数据（`non_authority`）。

## 实测记录（2026-08-30，D3 冒烟）

| 场景 | 结果 |
|---|---|
| `check`（本项目 pyproject.toml） | litellm 1.83.0 → **OK**（pip-audit 真实扫描通过） |
| `check --packages "urllib3==1.26.4" "requests==2.32.5"` | urllib3 → **VULNERABLE**（PYSEC-2021-108 / PYSEC-2023-192）；requests 2.32.5 → **VULNERABLE**（PYSEC-2026-2275） |
| pip-audit 未装场景 | 全部包 `UNKNOWN` + 登记待补（代码路径验证，未伪造 OK） |
