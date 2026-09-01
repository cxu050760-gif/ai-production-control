"""Supply Chain Check — §51 依赖供应链检查清单（v1.1-blackbox D3，S3 文件域）。

背景：§51 要求依赖供应链检查（pip-audit / osv-scanner 类）；报告 §7 已调研=直接复用
pip-audit（不重复造轮子，符合 §48 Reuse 门禁）。本工具输出机器可读检查清单：

  - check : 解析依赖（requirements.txt 或 pyproject.toml 的 [project]/optional 节），
            对每个包输出 名称/版本/来源(PyPI|本地)/漏洞状态(OK|VULNERABLE|UNKNOWN)/
            建议动作；若 pip-audit 可用则执行漏洞扫描并把结果映射到各包。

用法（独立 CLI；JSON 输出/退出码 0/1/2）：
    python scripts/supply_chain_check.py check
    python scripts/supply_chain_check.py check --requirements requirements.txt
    python scripts/supply_chain_check.py check --packages "requests==2.32.5" "litellm==1.83.0"

红线：
  1) 本工具只读扫描与报告，不做任何安装/卸载（pip-audit 扫描本身只读）；
  2) pip-audit 未安装时输出"依赖未安装，登记待补"，绝不因网络停摆伪造结果；
  3) 输出为 inert 数据（non_authority）；不改任何冻结文件。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "v1.1-d3-supply-chain"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PYPROJECT = PROJECT_ROOT / "pyproject.toml"
DEFAULT_REQUIREMENTS = PROJECT_ROOT / "requirements.txt"

_REQ_RE = re.compile(
    r"^\s*([A-Za-z0-9_.-]+)\s*(?:\[[^\]]*\])?\s*"
    r"(==|>=|<=|~=|!=|>|<|===)?\s*([A-Za-z0-9_.*+!-]*)\s*"
    r"(?:;\s*(.*))?$"
)


def _safe_text(value: Any, limit: int = 2000) -> str:
    """任意值 -> 干净 str，限长，剔除不可打印控制符。"""
    if value is None:
        return ""
    text = str(value)
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text[:limit]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# 依赖解析
# ---------------------------------------------------------------------------
def _is_local_source(spec: str) -> bool:
    """判断依赖来源：本地（file:// 或路径）或 PyPI。"""
    s = spec.strip().lower()
    return s.startswith("file:") or s.startswith("./") or s.startswith("../") or \
        s.startswith(".") or "\\" in s or "/" in s or s.startswith("http")


def parse_requirement_line(line: str) -> Optional[Dict[str, Any]]:
    """解析单行依赖（requirements.txt 风格或 pyproject 依赖字符串）。"""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("-"):
        return None
    # 去掉行内注释（# 前有空白）
    stripped = re.sub(r"\s+#.*$", "", stripped)
    if not stripped:
        return None
    # 本地路径/URL 依赖（file:、http:、./、../、绝对路径）
    if _is_local_source(stripped):
        return {"name": stripped, "specifier": None, "version": "",
                "source": "LOCAL", "raw": stripped}
    m = _REQ_RE.match(stripped)
    if not m:
        return None
    name = m.group(1)
    op = m.group(2) or ""
    ver = m.group(3) or ""
    return {
        "name": name,
        "specifier": op,
        "version": ver if op else "",
        "source": "PyPI",
        "raw": stripped,
    }


def parse_requirements_file(path: Path) -> List[Dict[str, Any]]:
    """解析 requirements.txt（每行一个包）。"""
    deps: List[Dict[str, Any]] = []
    if not path.exists():
        return deps
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return deps
    for line in text.splitlines():
        dep = parse_requirement_line(line)
        if dep:
            deps.append(dep)
    return deps


def parse_pyproject(path: Path) -> List[Dict[str, Any]]:
    """解析 pyproject.toml 的 [project] dependencies + optional-dependencies。

    使用标准库 tomllib（Python 3.11+；本项目规范解释器 3.12）。
    """
    deps: List[Dict[str, Any]] = []
    if not path.exists():
        return deps
    try:
        import tomllib  # Python 3.11+
        data = tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (ImportError, OSError, tomllib.TOMLDecodeError) as e:  # type: ignore[name-defined]
        return [{"name": f"<pyproject unreadable: {_safe_text(e, 200)}>",
                 "specifier": None, "version": "", "source": "LOCAL",
                 "raw": f"pyproject.toml parse error"}]
    project = data.get("project", {}) if isinstance(data, dict) else {}
    raw_deps = project.get("dependencies", []) or []
    if isinstance(raw_deps, list):
        for item in raw_deps:
            dep = parse_requirement_line(str(item))
            if dep:
                deps.append(dep)
    opt = project.get("optional-dependencies", {}) or {}
    if isinstance(opt, dict):
        for group, items in opt.items():
            if not isinstance(items, list):
                continue
            for item in items:
                dep = parse_requirement_line(str(item))
                if dep:
                    dep["optional_group"] = _safe_text(group, 100)
                    deps.append(dep)
    return deps


def resolve_installed_version(name: str) -> str:
    """通过 importlib.metadata 查已安装版本；未装返回 ''。"""
    try:
        from importlib import metadata
        dist = metadata.distribution(name)
        return dist.version or ""
    except Exception:  # noqa: BLE001 —— 查询失败返回空，不崩溃
        return ""


def build_dependency_manifest(requirements: Optional[Path],
                              packages: List[str]) -> Dict[str, Any]:
    """汇总依赖清单：requirements 文件 + pyproject + --packages 显式列表。"""
    manifest: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(dep: Dict[str, Any]) -> None:
        key = f"{dep.get('name')}|{dep.get('optional_group', '')}"
        if key in seen:
            return
        seen.add(key)
        manifest.append(dep)

    sources: List[str] = []
    if requirements is not None:
        for dep in parse_requirements_file(requirements):
            add(dep)
        sources.append(f"requirements:{requirements}")
    pyproject = DEFAULT_PYPROJECT
    if pyproject.exists():
        for dep in parse_pyproject(pyproject):
            add(dep)
        sources.append(f"pyproject:{pyproject}")
    for pkg in packages:
        dep = parse_requirement_line(pkg)
        if dep:
            add(dep)
        else:
            add({"name": pkg, "specifier": None, "version": "",
                 "source": "PyPI", "raw": pkg})
    if packages:
        sources.append("packages:--packages")
    return {"sources": sources, "dependencies": manifest}


# ---------------------------------------------------------------------------
# pip-audit 复用（§51 + §7 调研结论）
# ---------------------------------------------------------------------------
def pip_audit_available() -> bool:
    """探测 pip-audit 是否可用（`pip-audit` 命令或 `python -m pip_audit`）。"""
    if shutil.which("pip-audit"):
        return True
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--version"],
            capture_output=True, timeout=15, encoding="utf-8", errors="replace")
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def run_pip_audit(args: argparse.Namespace, requirements: Optional[Path],
                  project_dir: Path, packages: Optional[List[str]] = None) -> Dict[str, Any]:
    """执行 pip-audit 扫描（只读），返回结构化结果。

    优先级：
      1) --requirements 文件 -> `pip-audit -r <file>`；
      2) --packages 显式列表  -> 生成临时 requirements 文件再 `-r`；
      3) 缺省 -> 对项目目录 `--path <dir>` 扫描（自动读 pyproject.toml）。
    """
    base = ["pip-audit", "--format", "json"]
    target: List[str]
    kind = ""
    temp_req: Optional[Path] = None
    if requirements is not None and requirements.exists():
        base.append("--no-deps")  # --no-deps 仅可用于 -r 模式
        target = ["-r", str(requirements)]
        kind = "requirements"
    elif packages:
        base.append("--no-deps")
        temp_req = Path(tempfile.mkdtemp(prefix="sca_")) / "audit-requirements.txt"
        try:
            temp_req.write_text("\n".join(packages) + "\n", encoding="utf-8")
        except OSError as e:
            return {"ok": False, "kind": "packages",
                    "error": "TEMP_REQ_WRITE_FAILED",
                    "detail": _safe_text(e, 300), "vulnerabilities": []}
        target = ["-r", str(temp_req)]
        kind = "packages"
    else:
        target = ["--path", str(project_dir)]
        kind = "project-dir"
    try:
        proc = subprocess.run(
            base + target, capture_output=True, timeout=180,
            encoding="utf-8", errors="replace")
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"ok": False, "kind": kind,
                "error": "PIP_AUDIT_RUN_FAILED",
                "detail": _safe_text(e, 300), "vulnerabilities": []}
    finally:
        if temp_req is not None:
            try:
                shutil.rmtree(temp_req.parent, ignore_errors=True)
            except OSError:
                pass
    # pip-audit 发现漏洞时退出码非 0（1=发现漏洞），但 --format json 仍输出完整 JSON；
    # 先尝试解析 stdout，解析失败才按错误处理（exit 2=运行错误 / 3=依赖解析失败）。
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "kind": kind,
                "error": "PIP_AUDIT_EXIT_NONZERO",
                "exit_code": proc.returncode,
                "detail": _safe_text(proc.stdout or proc.stderr, 1500),
                "vulnerabilities": []}
    # pip-audit JSON 结构：顶层 dependencies[i] = {name, version, vulns:[...]}；
    # 展平为统一漏洞记录（供 map_vulnerabilities 消费）。
    flat: List[Dict[str, Any]] = []
    for dep in data.get("dependencies", []) or []:
        if not isinstance(dep, dict):
            continue
        dep_name = _safe_text(dep.get("name"), 200)
        dep_ver = _safe_text(dep.get("version"), 60)
        for vuln in dep.get("vulns", []) or []:
            if not isinstance(vuln, dict):
                continue
            flat.append({
                "id": _safe_text(vuln.get("id"), 120),
                "package": dep_name,
                "version": dep_ver,
                "fix_versions": vuln.get("fix_versions") or [],
                "description": _safe_text(vuln.get("description"), 400),
                "aliases": vuln.get("aliases") or [],
            })
    return {"ok": True, "kind": kind, "error": None, "detail": None,
            "exit_code": proc.returncode,
            "vulnerabilities": flat}


def map_vulnerabilities(deps: List[Dict[str, Any]],
                        audit: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """把 pip-audit 漏洞列表按包名映射（name -> vuln 列表）。"""
    mapping: Dict[str, List[Dict[str, Any]]] = {}
    for v in audit.get("vulnerabilities", []):
        pkg_name = _safe_text(v.get("package") or v.get("name"), 200)
        if not pkg_name:
            continue
        mapping.setdefault(pkg_name.lower(), []).append({
            "id": _safe_text(v.get("id"), 120),
            "package": pkg_name,
            "installed_version": _safe_text(v.get("version"), 60),
            "fixed_version": _safe_text(v.get("fix_versions") or [], 200),
            "description": _safe_text(v.get("description"), 400),
            "aliases": v.get("aliases") or [],
        })
    return mapping


# ---------------------------------------------------------------------------
# check 主流程
# ---------------------------------------------------------------------------
def cmd_check(args: argparse.Namespace) -> int:
    """输出依赖清单 + 已知漏洞检查结果（pip-audit 未装 -> UNKNOWN，不伪造）。"""
    requirements = None
    if args.requirements:
        requirements = Path(args.requirements)
        if not requirements.exists():
            print(json.dumps({"schema": SCHEMA, "command": "check", "ok": False,
                              "error": "REQUIREMENTS_NOT_FOUND",
                              "detail": f"{requirements} 不存在",
                              "instruction": "检查 --requirements 路径。"},
                             ensure_ascii=False, indent=2))
            return 2
    packages = []
    for group in (args.packages or []):
        for pkg in (group if isinstance(group, list) else [group]):
            pkg = pkg.strip()
            if pkg:
                packages.append(pkg)

    manifest = build_dependency_manifest(requirements, packages)
    deps = manifest["dependencies"]

    # 未 pin 版本的包：尝试用 importlib.metadata 解析已安装版本（仅报告）
    for dep in deps:
        if not dep.get("version") and dep.get("source") == "PyPI":
            inst = resolve_installed_version(dep["name"])
            dep["installed_version"] = inst
        else:
            dep["installed_version"] = dep.get("version", "")

    # pip-audit 可用性
    audit_available = pip_audit_available()
    audit: Dict[str, Any] = {}
    if audit_available:
        audit = run_pip_audit(args, requirements, PROJECT_ROOT, packages)
    else:
        audit = {
            "ok": False, "kind": None, "error": "PIP_AUDIT_NOT_INSTALLED",
            "detail": ("pip-audit 未安装；依赖漏洞状态一律 UNKNOWN。"
                       "登记待补：安装命令 "
                       "`python -m pip install pip-audit --proxy http://127.0.0.1:7897 "
                       "-i https://pypi.tuna.tsinghua.edu.cn/simple`。"),
            "vulnerabilities": [],
        }

    vuln_map = map_vulnerabilities(deps, audit) if audit.get("ok") else {}

    rows: List[Dict[str, Any]] = []
    vulnerable_count = 0
    unknown_count = 0
    for dep in deps:
        name = dep.get("name", "?")
        version = dep.get("installed_version") or dep.get("version") or "(未 pin)"
        source = dep.get("source", "PyPI")
        vulns = vuln_map.get(name.lower(), [])
        if vulns:
            status = "VULNERABLE"
            vulnerable_count += 1
            action = "升级到修复版本或替换依赖： " + "; ".join(
                f"{v.get('id')} -> fix {v.get('fixed_version')}" for v in vulns[:3])
        elif audit.get("ok"):
            status = "OK"
            action = "无已知漏洞（pip-audit 扫描通过）"
        else:
            status = "UNKNOWN"
            unknown_count += 1
            action = "pip-audit 不可用：登记待补，安装后重扫"
        rows.append({
            "name": name,
            "version": version,
            "source": source,
            "vuln_status": status,
            "vulnerabilities": vulns[:3],
            "action": action,
            "optional_group": dep.get("optional_group"),
        })

    summary = {
        "total": len(rows),
        "ok": sum(1 for r in rows if r["vuln_status"] == "OK"),
        "vulnerable": vulnerable_count,
        "unknown": unknown_count,
    }

    result = {
        "schema": SCHEMA, "command": "check", "ok": True,
        "checked_at": _now_iso(),
        "manifest_sources": manifest["sources"],
        "pip_audit": {
            "available": audit_available,
            "status": ("OK" if audit.get("ok") else audit.get("error")),
            "detail": audit.get("detail"),
            "raw_vulnerability_count": len(audit.get("vulnerabilities", [])),
        },
        "dependency_count": len(rows),
        "dependencies": rows,
        "summary": summary,
        "recommendations": [],
        "non_authority": True,
        "note": ("依赖漏洞状态依据 pip-audit（§51 复用，§7 调研结论）。"
                 "pip-audit 不可用时一律 UNKNOWN 并登记待补，不伪造 OK。"),
    }
    if vulnerable_count:
        result["recommendations"].append(
            f"发现 {vulnerable_count} 个已知漏洞依赖：升级到修复版本或替换（§51）。")
    if unknown_count:
        result["recommendations"].append(
            f"{unknown_count} 个包漏洞状态 UNKNOWN：安装 pip-audit 后重扫（登记待补）。")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # 退出码：0=完成（无论 OK/UNKNOWN）；发现漏洞仍为 0（报告性质，非门禁）
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Supply Chain Check: §51 依赖供应链检查清单（pip-audit 复用）")
    sub = ap.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="输出依赖清单 + 已知漏洞检查结果")
    p_check.add_argument("--requirements", dest="requirements", default="",
                         help="requirements.txt 路径（可选；缺省扫 pyproject.toml）")
    p_check.add_argument("--packages", dest="packages", action="append",
                         nargs="+", default=[],
                         help="显式依赖列表，如 --packages 'requests==2.32.5'（可多个/多次）")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.command == "check":
        return cmd_check(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
