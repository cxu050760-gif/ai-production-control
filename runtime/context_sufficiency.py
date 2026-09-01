#!/usr/bin/env python3
"""Context Sufficiency — 宪法 §55 Context Sufficiency（v1.1 D5，黑盒线）。

外部 Brain 信息不足时，自动路由五选一（按策略文件依次尝试）：
  ① SWITCH_LOCAL_BRAIN      换本地 Brain（fallbacks 链，registry brains 节）
  ② SWITCH_ALLOWED_PROVIDER 换允许 Provider（registry providers 节）
  ③ DESENSITIZE_RETRY       脱敏重试（敏感字段打码后重试）
  ④ HUMAN_AUTHORIZATION     输出授权请求（明确请求 Human 授权）
  ⑤ BLOCKED                 明确阻塞 + 原因（fail-closed）

输入：任务上下文（可用信息 key->{value,source,trust,sensitive}）、所需信息清单、
可用 Brain/Provider 注册（config/capability-registry.json 只读）、策略（阈值）。

输出：路由决策 + 理由 + 中间状态（branches_tried）+ 具体动作（routing_action）。

红线：只读 registry；不真实调用 AI（L3 之外）；敏感值脱敏后不落盘原文于输出。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "v1.1-d5-context-sufficiency"

BRANCH_ORDER = [
    "SWITCH_LOCAL_BRAIN",
    "SWITCH_ALLOWED_PROVIDER",
    "DESENSITIZE_RETRY",
    "HUMAN_AUTHORIZATION",
    "BLOCKED",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _safe_text(value: Any, limit: int = 2000) -> str:
    return "" if value is None else str(value)[:limit]


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------- 策略


def default_policy() -> Dict[str, Any]:
    return {
        "completeness_threshold": 1.0,   # 所需信息 100% 齐备才算 SUFFICIENT
        "trust_threshold": 0.5,          # 可信度低于此值视为不可用
        "allow_human_authorization": True,
        "min_fallback_brains": 2,        # 至少 2 个可用本地 Brain 才走分支 ①
        "min_alternate_providers": 2,    # 至少 2 个可用 Provider 才走分支 ②
    }


def _load_registry(path: Optional[str] = None) -> Dict[str, Any]:
    p = Path(path) if path else (_repo_root() / "config" / "capability-registry.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_policy(path: Optional[str] = None) -> Dict[str, Any]:
    if path:
        p = Path(path)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                pol = default_policy()
                pol.update(data.get("context_sufficiency", {}) or {})
                return pol
            except Exception:
                pass
    return default_policy()


# ---------------------------------------------------------------- 敏感识别/脱敏


_SENSITIVE_PATTERNS = [
    re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)"),                    # 手机号
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),                      # 邮箱
    re.compile(r"\b\d{17}[\dXx]\b"),                              # 身份证
    re.compile(r"(?:Bearer\s+)[A-Za-z0-9\-._~+/=]+", re.IGNORECASE),  # Bearer token
    re.compile(r"(?:password|密码|authorization|api[_-]?key|secret|token)\s*[:=]\s*\S+", re.IGNORECASE),
]

_SENSITIVE_KEYS = ("password", "密码", "token", "authorization", "api_key", "apikey",
                   "secret", "credential", "凭据", "手机号", "email", "身份证", "phone")


def _is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return any(s in k for s in _SENSITIVE_KEYS)


def _is_sensitive_value(value: Any) -> bool:
    text = _safe_text(value, 1000)
    return any(p.search(text) for p in _SENSITIVE_PATTERNS)


def mask_value(value: Any, key: str = "") -> str:
    """脱敏：手机/邮箱/身份证/口令类字段打码；输出不含敏感原文。"""
    text = _safe_text(value, 1000)
    # 手机号
    m = re.search(r"(?<!\d)(1[3-9]\d{9})(?!\d)", text)
    if m:
        return text.replace(m.group(1), m.group(1)[:3] + "****" + m.group(1)[-4:])
    # 身份证
    m = re.search(r"\b(\d{17}[\dXx])\b", text)
    if m:
        return text.replace(m.group(1), m.group(1)[:4] + "**********" + m.group(1)[-2:])
    # 邮箱
    m = re.search(r"([\w.+-]+)@([\w-]+\.[\w.-]+)", text)
    if m:
        name, domain = m.group(1), m.group(2)
        masked_name = (name[0] + "****") if len(name) > 1 else "****"
        return text.replace(m.group(0), f"{masked_name}@{domain}")
    # Bearer token / 口令键值
    m = re.search(r"(Bearer\s+)[A-Za-z0-9\-._~+/=]+", text, re.IGNORECASE)
    if m:
        return text.replace(m.group(0), m.group(1) + "******")
    m = re.search(r"((?:password|密码|authorization|api[_-]?key|secret|token)\s*[:=]\s*)\S+", text, re.IGNORECASE)
    if m:
        return text.replace(m.group(0), m.group(1) + "******")
    # 通用兜底：非空敏感值一律遮罩（保守）
    return "******"


# ---------------------------------------------------------------- 数据模型


@dataclass
class InfoItem:
    key: str
    value: Any = None
    source: str = ""
    trust: float = 1.0
    sensitive: bool = False
    masked_value: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "source": self.source,
            "trust": self.trust,
            "sensitive": self.sensitive,
            "masked": self.masked_value is not None,
        }


def _normalize_context(context: Dict[str, Any]) -> Dict[str, InfoItem]:
    items: Dict[str, InfoItem] = {}
    for key, raw in (context or {}).items():
        if isinstance(raw, dict):
            value = raw.get("value")
            source = _safe_text(raw.get("source", ""), 256)
            trust = float(raw.get("trust", 1.0) or 1.0)
            sensitive = bool(raw.get("sensitive", False)) or _is_sensitive_key(key) or _is_sensitive_value(value)
        else:
            value = raw
            source = "context"
            trust = 1.0
            sensitive = _is_sensitive_key(key) or _is_sensitive_value(value)
        items[key] = InfoItem(key=key, value=value, source=source, trust=trust, sensitive=sensitive)
    return items


def _normalize_required(required_info: Any) -> List[str]:
    if required_info is None:
        return []
    if isinstance(required_info, str):
        return [required_info]
    out: List[str] = []
    for r in required_info:
        if isinstance(r, dict):
            out.append(str(r.get("key", "")))
        else:
            out.append(str(r))
    return [k for k in out if k]


# ---------------------------------------------------------------- 状态评估


def _item_status(item: Optional[InfoItem], policy: Dict[str, Any]) -> str:
    """OK | SENSITIVE | MISSING。

    - 无值 -> MISSING
    - 可信度低于阈值 -> MISSING（不可用）
    - 敏感（需脱敏后才可用）-> SENSITIVE
    - 其余 -> OK
    """
    if item is None or item.value is None or item.value == "":
        return "MISSING"
    if float(item.trust) < float(policy.get("trust_threshold", 0.5)):
        return "MISSING"
    if item.sensitive:
        return "SENSITIVE"
    return "OK"


def _usable_fallback_brains(registry: Dict[str, Any]) -> List[str]:
    brains = (registry.get("sections") or {}).get("brains") or []
    return sorted({
        b.get("id") for b in brains
        if isinstance(b, dict) and b.get("id") and b.get("type") == "API_MODEL"
        and b.get("status") == "official"
    })


def _usable_providers(registry: Dict[str, Any]) -> List[str]:
    providers = (registry.get("sections") or {}).get("providers") or []
    return sorted({
        p.get("id") for p in providers
        if isinstance(p, dict) and p.get("id") and p.get("status") == "official"
    })


# ---------------------------------------------------------------- 五分支路由


def route(context: Dict[str, Any], required_info: Any,
          registry: Optional[Dict[str, Any]] = None,
          policy: Optional[Dict[str, Any]] = None,
          registry_path: Optional[str] = None) -> Dict[str, Any]:
    """§55 五分支自动路由主入口。

    依次尝试五分支，返回第一个「可用且适用」的分支作为决策；
    若都不适用 -> BLOCKED（fail-closed）。
    """
    policy = dict(policy or _load_policy(None))
    registry = registry if registry is not None else _load_registry(registry_path)
    items = _normalize_context(context)
    keys = _normalize_required(required_info)
    if not keys:
        return {
            "schema": SCHEMA,
            "decision": "SUFFICIENT",
            "reason": "无所需信息清单，视为充分",
            "completeness": {"total": 0, "ok": 0, "sensitive": 0, "missing": 0, "ratio": 1.0},
            "branches_tried": [],
            "routing_action": None,
            "authorization_request": None,
            "blocked_reason": None,
            "policy": policy,
            "trace": {
                "model": None,
                "ai": "rule-based-context-router",
                "tool": "context_sufficiency.py route",
                "reason_retry": None,
                "cost": None,
            },
        }

    statuses = {k: _item_status(items.get(k), policy) for k in keys}
    ok = sum(1 for s in statuses.values() if s == "OK")
    sensitive = sum(1 for s in statuses.values() if s == "SENSITIVE")
    missing = sum(1 for s in statuses.values() if s == "MISSING")
    total = len(keys)
    ratio = round(ok / total, 4) if total else 1.0
    completeness = {"total": total, "ok": ok, "sensitive": sensitive,
                    "missing": missing, "ratio": ratio}

    if ratio >= float(policy.get("completeness_threshold", 1.0)) and missing == 0 and sensitive == 0:
        return {
            "schema": SCHEMA,
            "decision": "SUFFICIENT",
            "reason": f"所需信息齐备（{ok}/{total}），无需路由",
            "completeness": completeness,
            "branches_tried": [],
            "routing_action": None,
            "authorization_request": None,
            "blocked_reason": None,
            "policy": policy,
            "trace": {
                "model": None,
                "ai": "rule-based-context-router",
                "tool": "context_sufficiency.py route",
                "reason_retry": None,
                "cost": None,
            },
        }

    brains = _usable_fallback_brains(registry)
    providers = _usable_providers(registry)
    missing_keys = [k for k in keys if statuses[k] == "MISSING"]
    sensitive_keys = [k for k in keys if statuses[k] == "SENSITIVE"]

    branches_tried: List[Dict[str, Any]] = []
    decision: Optional[str] = None
    reason = ""
    routing_action: Optional[Dict[str, Any]] = None

    # ① 换本地 Brain（fallbacks 链）
    if len(brains) >= int(policy.get("min_fallback_brains", 2)) and missing_keys:
        decision = "SWITCH_LOCAL_BRAIN"
        reason = (f"信息不足：{missing} 项缺失；本地 Brain fallback 链可用 "
                  f"({', '.join(brains)})，换本地 Brain 尝试补充")
        routing_action = {
            "branch": decision,
            "fallback_chain": brains,
            "target_keys": missing_keys,
        }
        branches_tried.append({"branch": decision, "ok": True, "skipped": False, "reason": reason})
    else:
        branches_tried.append({"branch": "SWITCH_LOCAL_BRAIN", "ok": False, "skipped": True,
                               "reason": "无可用 fallback 链或无缺失项"})

    # ② 换允许 Provider（registry providers）
    if decision is None:
        if len(providers) >= int(policy.get("min_alternate_providers", 2)) and missing_keys:
            decision = "SWITCH_ALLOWED_PROVIDER"
            reason = (f"本地 Brain 不可用；允许 Provider 可切换 "
                      f"({', '.join(providers)})，换 Provider 尝试")
            routing_action = {
                "branch": decision,
                "allowed_providers": providers,
                "target_keys": missing_keys,
            }
            branches_tried.append({"branch": decision, "ok": True, "skipped": False, "reason": reason})
        else:
            branches_tried.append({"branch": "SWITCH_ALLOWED_PROVIDER", "ok": False, "skipped": True,
                                   "reason": "无可切换 Provider 或无缺失项"})

    # ③ 脱敏重试（敏感字段打码）
    if decision is None:
        if sensitive_keys:
            masked = {k: mask_value(items[k].value, k) for k in sensitive_keys}
            decision = "DESENSITIZE_RETRY"
            reason = f"信息含敏感字段 {len(sensitive_keys)} 项；脱敏后重试"
            routing_action = {
                "branch": decision,
                "masked_keys": [{"key": k, "masked_value": masked[k]} for k in sensitive_keys],
            }
            branches_tried.append({"branch": decision, "ok": True, "skipped": False, "reason": reason})
        else:
            branches_tried.append({"branch": "DESENSITIZE_RETRY", "ok": False, "skipped": True,
                                   "reason": "无敏感字段需脱敏"})

    # ④ Human Authorization
    if decision is None:
        unresolved = [k for k in keys if statuses[k] != "OK"]
        if bool(policy.get("allow_human_authorization", True)) and unresolved:
            decision = "HUMAN_AUTHORIZATION"
            reason = f"自动分支均无法补齐 {len(unresolved)} 项信息；输出授权请求，等待 Human 决策"
            routing_action = {
                "branch": decision,
                "requested_keys": unresolved,
                "request_id": f"CS-{_now_iso().replace(':', '').replace('-', '')[:15]}",
            }
            branches_tried.append({"branch": decision, "ok": True, "skipped": False, "reason": reason})
        else:
            branches_tried.append({"branch": "HUMAN_AUTHORIZATION", "ok": False, "skipped": True,
                                   "reason": "策略禁止 Human 授权或已无未决项"})

    # ⑤ BLOCKED
    if decision is None:
        decision = "BLOCKED"
        reason = "五分支均无法解决信息不足；fail-closed 阻塞执行"
        branches_tried.append({"branch": "BLOCKED", "ok": True, "skipped": False, "reason": reason})

    authorization_request = None
    blocked_reason = None
    if decision == "HUMAN_AUTHORIZATION" and routing_action:
        authorization_request = {
            "request_id": routing_action["request_id"],
            "requested_keys": routing_action["requested_keys"],
            "policy": "Human Gate Trust Root（V14-FROZEN）",
            "note": "人工审查后通过 self_heal / controller 既有授权路径放行",
        }
    if decision == "BLOCKED":
        blocked_reason = "信息不足且无可用分支（fallbacks/Provider/脱敏/Human 均不可用或不允许）"

    return {
        "schema": SCHEMA,
        "decision": decision,
        "reason": reason,
        "completeness": completeness,
        "branches_tried": branches_tried,
        "routing_action": routing_action,
        "authorization_request": authorization_request,
        "blocked_reason": blocked_reason,
        "policy": policy,
        "trace": {
            "model": None,
            "ai": "rule-based-context-router",
            "tool": "context_sufficiency.py route",
            "reason_retry": None,
            "cost": None,
        },
    }


# ---------------------------------------------------------------- CLI


def _cmd_route(args: argparse.Namespace) -> int:
    context: Dict[str, Any] = {}
    if args.context:
        p = Path(args.context)
        if not p.exists():
            print(json.dumps({"schema": SCHEMA, "valid": False, "error": "CONTEXT_NOT_FOUND"},
                             ensure_ascii=False))
            return 1
        context = json.loads(p.read_text(encoding="utf-8"))
    required: Any = args.required
    if args.required_file:
        p = Path(args.required_file)
        if not p.exists():
            print(json.dumps({"schema": SCHEMA, "valid": False, "error": "REQUIRED_NOT_FOUND"},
                             ensure_ascii=False))
            return 1
        required = json.loads(p.read_text(encoding="utf-8"))
    elif required:
        required = [k.strip() for k in required.split(",") if k.strip()]
    policy = _load_policy(args.policy) if args.policy else None
    result = route(context, required, registry_path=args.registry, policy=policy)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Context Sufficiency (v1.1 D5)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("route", help="五分支自动路由")
    p.add_argument("--context", default="", help="JSON 上下文文件（key -> {value,source,trust,sensitive}）")
    p.add_argument("--required", default="", help="逗号分隔所需信息 key 列表")
    p.add_argument("--required-file", default="", help="JSON 所需信息列表文件")
    p.add_argument("--registry", default="", help="capability-registry.json 路径（默认 config/）")
    p.add_argument("--policy", default="", help="策略 JSON 文件路径（可选）")
    p.set_defaults(func=_cmd_route)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
