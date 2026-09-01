"""R-Adapter — R 审查者 Provider 适配层（宪法 §5 Provider 独立，v1.1-blackbox D1）。

背景：当前 R 硬绑 ChatGPT 网页通道（chatgpt_bridge），Worker 只适配 TRAE。
宪法 §5 要求 AI 是资源可替换：R / Brain / Worker 都应有 Adapter。
本模块为 R-Adapter 机器可完成部分（LiteLLM 接入骨架）：

  - health : 对 config 中每个 provider 做健康探测；无 key 一律标记 UNCONFIGURED
             （有 key 且非空才真探测；当前施工环境无真实 key，输出 UNCONFIGURED 即正确）。
  - pick   : 按 health + priority 仲裁选主 R，输出 fallback 链（主 R 失败 -> 次 R）。
  - review : 走 LiteLLM Router 接口但指向内置 mock provider（mock_response，
             不消耗真实额度、不触真实 API key），返回结构化审查判定 PASS/REWORK；
             这是 L2 模拟实测的通道。真实调用路径保留但需要 key（留业主 L3）。

用法（独立 CLI，仿 brain_bridge / capsule_bridge / blackbox_bridge 模式）：
    python r_adapter.py health --config runtime/adapters/r_adapter.config.example.json
    python r_adapter.py pick   --config <F> [--prefer <provider_id>]
    python r_adapter.py review --config <F> --mode mock --mock-verdict PASS \
            [--payload '{"run_id":"RUN-1","goal":"..."}']
    python r_adapter.py review --config <F> --mode real   # 需 key；L3 业主接入点

红线：
  1) api_key 一律从环境变量读（api_key_env 字段声明变量名），禁止硬编码/入仓；
  2) 本模块不做真实 Provider 调用（真实调用 = 留业主 L3）；mock 不消耗任何额度；
  3) 输出为 inert 数据（non_authority）；任何 authority 词只作数据呈现，绝不代执行；
  4) 不改 src/aicontrol/、config/production.json、runtime/runtime.py、
     config/capability-registry.json（只读衔接）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "v1.1-d1-r-adapter"
CONFIG_SCHEMA = "R_ADAPTER_CONFIG"
VERDICT_RE = re.compile(r"^===REVIEW_VERDICT===\s*([A-Za-z_]+)\s*$", re.MULTILINE)

# 健康状态机（rank 越大越优先）
STATUS_RANK = {"UP": 3, "CONFIGURED": 2, "UNCONFIGURED": 1, "DOWN": 0}

# 可离线探测的 health_check kind（无网络副作用）
_OFFLINE_PROBE_KINDS = ("file", "command", "port")

# 默认最大输出/截断
_MAX_TAIL = 2000


def _safe_text(value: Any, limit: int = 2000) -> str:
    """任意值 -> 干净 str，限长，剔除不可打印控制符。"""
    if value is None:
        return ""
    text = str(value)
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text[:limit]


# ---------------------------------------------------------------------------
# Config 加载 / 校验
# ---------------------------------------------------------------------------
def load_config(path: str) -> Dict[str, Any]:
    """从 JSON 文件读 R-Adapter 配置（provider 列表骨架）。

    配置结构（生产参考 config/capability-registry.json providers 节 + production.json
    brains.default_primary/fallbacks，只读衔接）：
    {
      "schema": "R_ADAPTER_CONFIG",
      "schema_version": 1,
      "default_timeout_sec": 120,
      "providers": [
        {
          "id": "r-deepseek-v4-flash",
          "name": "DeepSeek V4 Flash via LiteLLM",
          "kind": "api_model",            # api_model | web_session
          "type": "API_MODEL",
          "model": "deepseek/deepseek-chat",   # LiteLLM model name（含 provider 前缀）
          "provider": "deepseek",
          "api_key_env": "DEEPSEEK_API_KEY",   # 环境变量名；空 = 该 provider 永不配置 key
          "priority": 2,                       # 数字越小越优先（仲裁用）
          "health_timeout_sec": 10,
          "health_check": {"kind": "file", "path": "..."}   # 可选：file/command/port
        }
      ]
    }
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config not found: {p}")
    try:
        cfg = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"config unreadable: {p} ({e})") from e
    if not isinstance(cfg, dict) or "providers" not in cfg:
        raise ValueError(f"config missing 'providers' list: {p}")
    if not isinstance(cfg["providers"], list) or not cfg["providers"]:
        raise ValueError(f"config 'providers' must be non-empty list: {p}")
    return cfg


def _provider_id(provider: Dict[str, Any]) -> str:
    return _safe_text(provider.get("id") or provider.get("name") or "?", 80)


def _provider_api_key(provider: Dict[str, Any], env: Optional[Dict[str, str]] = None) -> str:
    """从环境变量读 api_key（凭据纪律：禁止硬编码/入仓）。

    返回 '' 表示未配置。env 为 None 时读 os.environ（测试可注入）。
    """
    env_map = os.environ if env is None else env
    key_env = _safe_text(provider.get("api_key_env"), 128).strip()
    if not key_env:
        return ""
    return _safe_text(env_map.get(key_env, ""), 4096).strip()


def litellm_model_name(provider: Dict[str, Any]) -> str:
    """构造 LiteLLM 模型名（含 provider 前缀，如 deepseek/deepseek-chat）。

    若 model 字段已含 '/' 则原样使用；否则用 provider 字段拼前缀。
    """
    model = _safe_text(provider.get("model"), 256).strip()
    if not model:
        return ""
    if "/" in model:
        return model
    prefix = _safe_text(provider.get("provider"), 128).strip()
    return f"{prefix}/{model}" if prefix else model


# ---------------------------------------------------------------------------
# 健康探测
# ---------------------------------------------------------------------------
def _probe_file(health: Dict[str, Any]) -> Dict[str, Any]:
    target = _safe_text(health.get("path"), 1024)
    if not target:
        return {"ok": False, "detail": "health_check.path missing"}
    exists = Path(target).exists()
    return {"ok": exists, "detail": f"file exists={exists}: {target}"}


def _probe_port(health: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    host = _safe_text(health.get("host") or "127.0.0.1", 256)
    port = int(health.get("port", 0) or 0)
    if port <= 0 or port > 65535:
        return {"ok": False, "detail": f"invalid port: {port}"}
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"ok": True, "detail": f"port open: {host}:{port}"}
    except OSError as e:
        return {"ok": False, "detail": f"port closed: {host}:{port} ({e})"}


def _probe_command(health: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    cmd = health.get("command")
    if not isinstance(cmd, list) or not cmd:
        return {"ok": False, "detail": "health_check.command missing"}
    expect = _safe_text(health.get("expect"), 512)
    try:
        proc = subprocess.run(
            [str(c) for c in cmd],
            capture_output=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired as e:
        return {"ok": False, "detail": f"command timeout >{timeout}s: {cmd}"}
    except OSError as e:
        return {"ok": False, "detail": f"command spawn failed: {cmd} ({e})"}
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return {"ok": False, "detail": f"command exit={proc.returncode}: {cmd}"}
    if expect and expect not in out:
        return {"ok": False, "detail": f"command output missing expect {expect!r}: {cmd}"}
    return {"ok": True, "detail": f"command ok (exit=0): {cmd}"}


def probe_provider(provider: Dict[str, Any],
                   env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """对单个 provider 做健康探测，返回结构化状态记录。

    规则（机械，不猜）：
      - kind == web_session        -> UNCONFIGURED（R 网页会话需会话 URL，属凭据，L3 业主）
      - api_key_env 未声明         -> UNCONFIGURED
      - api_key_env 声明的环境变量缺失/为空 -> UNCONFIGURED
      - 有 key 且非空              -> 真探测（health_check file/command/port，或
                                      LiteLLM 最小 completion）-> UP / DOWN
    """
    pid = _provider_id(provider)
    kind = _safe_text(provider.get("kind") or provider.get("type") or "api_model", 64)
    key = _provider_api_key(provider, env)
    key_env = _safe_text(provider.get("api_key_env"), 128).strip()
    health = provider.get("health_check") or {}
    timeout = float(provider.get("health_timeout_sec") or health.get("timeout_sec") or 10)

    if kind == "web_session":
        return {
            "id": pid, "status": "UNCONFIGURED",
            "reason": ("web session 需要 R 会话 URL（凭据，唯一来源=会话注册.json，"
                       "L3 业主接入）；api_key_env 不适用"),
            "probe": None, "priority": int(provider.get("priority", 99)),
        }
    if not key_env:
        return {
            "id": pid, "status": "UNCONFIGURED",
            "reason": "api_key_env 未在 config 中声明", "probe": None,
            "priority": int(provider.get("priority", 99)),
        }
    if not key:
        return {
            "id": pid, "status": "UNCONFIGURED",
            "reason": f"环境变量 {key_env} 缺失/为空（凭据由 L3 业主注入）",
            "probe": None, "priority": int(provider.get("priority", 99)),
        }

    # 有 key：真探测（离线 kind 优先；无 health_check 时走 LiteLLM 最小探测）
    hkind = _safe_text(health.get("kind"), 64)
    if hkind in _OFFLINE_PROBE_KINDS:
        if hkind == "file":
            probe = _probe_file(health)
        elif hkind == "port":
            probe = _probe_port(health, timeout)
        else:
            probe = _probe_command(health, timeout)
    else:
        probe = _probe_litellm(provider, key, timeout)

    status = "UP" if probe.get("ok") else "DOWN"
    return {
        "id": pid, "status": status,
        "reason": probe.get("detail", ""),
        "probe": {"kind": hkind or "litellm", "detail": probe.get("detail", "")},
        "priority": int(provider.get("priority", 99)),
        "api_key_env": key_env,
    }


def _probe_litellm(provider: Dict[str, Any], api_key: str, timeout: float) -> Dict[str, Any]:
    """LiteLLM 最小 completion 探测（仅在有真实 key 时被调用；当前环境不会触发）。

    失败一律返回 ok=False（不崩溃），具体错误进 detail。
    """
    try:
        from litellm import Router
    except ImportError as e:
        return {"ok": False, "detail": f"litellm not installed: {e}"}
    model = litellm_model_name(provider)
    if not model:
        return {"ok": False, "detail": "provider.model missing"}
    try:
        router = Router(model_list=[{
            "model_name": provider.get("id") or model,
            "litellm_params": {"model": model, "api_key": api_key},
        }])
        resp = router.completion(
            model=provider.get("id") or model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1, timeout=timeout,
        )
        if resp is None or not getattr(resp, "choices", None):
            return {"ok": False, "detail": "litellm probe returned empty response"}
        return {"ok": True, "detail": "litellm completion ok (max_tokens=1)"}
    except Exception as e:  # noqa: BLE001 —— 探测失败即 DOWN，绝不崩溃
        return {"ok": False, "detail": f"litellm probe failed: {_safe_text(e, 400)}"}


def health_probe_all(cfg: Dict[str, Any],
                     env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """对 config 全部 provider 做健康探测，返回结构化清单 + 汇总。"""
    providers = cfg["providers"]
    results = [probe_provider(p, env) for p in providers]
    counts: Dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    results.sort(key=lambda r: (-STATUS_RANK.get(r["status"], -1),
                                r.get("priority", 99)))
    return {
        "schema": SCHEMA, "command": "health", "ok": True,
        "providers": results, "summary": counts,
        "non_authority": True,
        "note": ("无 key 的 provider 一律 UNCONFIGURED（正确行为）；"
                 "真实探测仅在 api_key_env 对应环境变量非空时进行。"),
    }


# ---------------------------------------------------------------------------
# 仲裁 / 热切换（pick）
# ---------------------------------------------------------------------------
def pick_provider(cfg: Dict[str, Any],
                  prefer: Optional[str] = None,
                  env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """按 health + priority 仲裁选主 R，并输出 fallback 链。

    规则（机械，不猜）：
      1) 健康状态优先级：UP > CONFIGURED > UNCONFIGURED > DOWN；
      2) 同状态内 priority 数字小者优先；
      3) --prefer 指定的 provider 若为 UP 则直接选中；否则回退到规则 1/2；
      4) fallback_chain = 全部 provider 按 priority 升序（附健康状态），
         主 R 失败 -> 依次切换（热切换由调用方按链消费，本模块只出链）。
      5) 当前施工环境全部 UNCONFIGURED：仍返回最高优先级占位 provider，
         但 degraded=true 并注明"需要凭据（L3 业主）"。
    """
    providers = cfg["providers"]
    probes = {r["id"]: r for r in health_probe_all(cfg, env)["providers"]}

    def sort_key(p: Dict[str, Any]) -> tuple:
        # 高 rank（健康优先）在前；同 rank 内 priority 数字小（更优先）在前
        pid = _provider_id(p)
        st = probes.get(pid, {}).get("status", "DOWN")
        return (-STATUS_RANK.get(st, -1), int(p.get("priority", 99)), pid)

    ordered = sorted(providers, key=sort_key)
    best = ordered[0] if ordered else None
    best_id = _provider_id(best) if best else None

    # --prefer 处理：仅当该 provider 健康为 UP 才采纳（否则回退规则仲裁）
    prefer_used = False
    if prefer:
        pref_probe = probes.get(prefer)
        if pref_probe and pref_probe.get("status") == "UP":
            best = next((p for p in providers if _provider_id(p) == prefer), best)
            best_id = _provider_id(best) if best else None
            prefer_used = True

    fallback_chain = [
        {
            "id": _provider_id(p),
            "priority": int(p.get("priority", 99)),
            "status": probes.get(_provider_id(p), {}).get("status", "DOWN"),
        }
        for p in sorted(providers, key=lambda p: (int(p.get("priority", 99)),
                                                  _provider_id(p)))
    ]

    if not best:
        return {"schema": SCHEMA, "command": "pick", "ok": False,
                "error": "NO_PROVIDERS", "selected": None,
                "fallback_chain": [], "reason": "config 无可用 provider"}

    best_status = probes.get(best_id, {}).get("status", "DOWN")
    degraded = best_status != "UP"
    reasons = []
    if prefer_used:
        reasons.append(f"--prefer 指定且健康 UP：选中 {best_id}")
    else:
        reasons.append(f"按 health+priority 仲裁：best status={best_status}, "
                       f"priority={int(best.get('priority', 99))}")
    if degraded:
        reasons.append("当前无健康 UP 的 provider（凭据未注入）：返回占位选择，"
                       "真实调用需 L3 业主配置 api_key_env 对应环境变量")
    reasons.append("fallback 链已生成：主 R 失败 -> 依次切换（按 priority 升序）")

    return {
        "schema": SCHEMA, "command": "pick", "ok": True,
        "selected": {
            "id": best_id,
            "name": _safe_text(best.get("name"), 200),
            "kind": _safe_text(best.get("kind") or best.get("type"), 64),
            "status": best_status,
            "priority": int(best.get("priority", 99)),
            "api_key_env": _safe_text(best.get("api_key_env"), 128),
        },
        "reason": "；".join(reasons),
        "degraded": degraded,
        "prefer_used": prefer_used,
        "fallback_chain": fallback_chain,
        "health": probes,
        "non_authority": True,
    }


# ---------------------------------------------------------------------------
# Review（LiteLLM Router 接口；mock 通道不消耗真实额度）
# ---------------------------------------------------------------------------
def _review_prompt(payload: Dict[str, Any]) -> str:
    """把 payload 组装成 R 审查提示（inert：模型只输出判定，不代执行）。"""
    parts = [
        "你是执衡生产系统的 R 审查者。请对以下任务证据给出机械判定。",
        "输出格式（必须）:",
        "===REVIEW_VERDICT=== PASS|REWORK",
        "===NEXT_ACTION===",
        "结论正文（若 REWORK，列出必须修改的问题）。",
        "---payload---",
    ]
    if isinstance(payload, dict):
        parts.append(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        parts.append(_safe_text(payload, 8000))
    return "\n".join(parts)


def parse_verdict(text: str) -> str:
    """从模型输出机械解析 verdict；解析不到 -> UNKNOWN（不猜）。"""
    m = VERDICT_RE.search(text or "")
    if m:
        return m.group(1).strip().upper()
    upper = (text or "").upper()
    if "REWORK" in upper:
        return "REWORK"
    if "PASS" in upper:
        return "PASS"
    return "UNKNOWN"


def _build_router_mock(mock_verdict: str) -> Any:
    """构建指向内置 mock provider 的 LiteLLM Router（mock_response，零额度）。"""
    from litellm import Router
    body = (
        f"===REVIEW_VERDICT=== {mock_verdict}\n\n"
        "===NEXT_ACTION===\n"
        f"[mock] R-Adapter 内置 mock provider 返回判定 {mock_verdict}；"
        "不消耗真实额度，仅用于 L2 模拟实测。"
    )
    return Router(model_list=[{
        "model_name": "mock-r",
        "litellm_params": {
            "model": "gpt-3.5-turbo",
            "api_key": "mock",
            "mock_response": body,
        },
    }])


def _build_router_real(providers: List[Dict[str, Any]],
                       env: Optional[Dict[str, str]]) -> Any:
    """构建指向真实 provider（含 key）的 LiteLLM Router（L3 业主接入点）。"""
    from litellm import Router
    model_list = []
    for p in providers:
        key = _provider_api_key(p, env)
        model = litellm_model_name(p)
        if not key or not model:
            continue
        model_list.append({
            "model_name": _provider_id(p),
            "litellm_params": {"model": model, "api_key": key},
        })
    if not model_list:
        raise ValueError("NO_CONFIGURED_PROVIDERS")
    return Router(model_list=model_list)


def do_review(cfg: Dict[str, Any], mode: str, mock_verdict: str,
              payload: Any, prefer: Optional[str] = None,
              env: Optional[Dict[str, str]] = None,
              max_tokens: int = 1024) -> Dict[str, Any]:
    """执行一次结构化 review。

    mode=mock: 走 LiteLLM Router 接口但指向内置 mock provider（零额度、零 key）；
               litellm import 推迟到 _build_router_mock 之前（DEF-D1b）。
    mode=real: 需 key（L3 业主）；先查 keyed，无 key 直接返回 UNCONFIGURED
               （不碰 litellm，DEF-D1b）；有 key 才 import litellm。
    保证：无 litellm 时 health/pick/review-real-无key 均正常工作；
          仅 review-real-有key 与 review-mock 需要 litellm。
    """
    prompt = _review_prompt(payload if payload is not None else {})

    if mode == "mock":
        try:
            from litellm import Router  # noqa: F401  确保 litellm 可用
        except ImportError as e:
            return {"schema": SCHEMA, "command": "review", "ok": False,
                    "error": "LITELLM_NOT_INSTALLED",
                    "detail": f"需要 litellm（Python312 已装 1.83.0；如缺失 "
                              f"pip install litellm）：{e}",
                    "instruction": "用生产解释器 Python312 运行，或安装 litellm 后重试。"}
        try:
            router = _build_router_mock(mock_verdict or "PASS")
            resp = router.completion(
                model="mock-r", messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens)
            text = resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001
            return {"schema": SCHEMA, "command": "review", "ok": False,
                    "error": "MOCK_ROUTER_FAILED",
                    "detail": _safe_text(e, 600),
                    "instruction": "mock 通道异常，请报告工程师；不消耗真实额度。"}
        return {
            "schema": SCHEMA, "command": "review", "ok": True,
            "mode": "mock", "provider_used": "mock-r",
            "verdict": parse_verdict(text), "raw_text": _safe_text(text, 4000),
            "mock_verdict": mock_verdict or "PASS",
            "payload": payload if payload is not None else {},
            "non_authority": True,
            "note": "mock review：走 LiteLLM Router 接口但指向内置 mock provider，"
                    "不消耗真实额度、不触真实 API key（L2 模拟实测通道）。",
        }

    # mode == real（L3 业主接入点；当前无 key 时给出 UNCONFIGURED 指引）
    # 先查 keyed，无 key 直接 UNCONFIGURED，不碰 litellm（DEF-D1b）
    providers = cfg["providers"]
    keyed = [p for p in providers if _provider_api_key(p, env)]
    if not keyed:
        return {"schema": SCHEMA, "command": "review", "ok": False,
                "error": "UNCONFIGURED",
                "instruction": ("真实 Provider 调用=留业主（L3）：需要为至少一个 "
                                "provider 的 api_key_env 注入非空环境变量。"
                                "当前环境无真实 key，输出 UNCONFIGURED 即正确。")}
    try:
        from litellm import Router  # noqa: F401  确保 litellm 可用
    except ImportError as e:
        return {"schema": SCHEMA, "command": "review", "ok": False,
                "error": "LITELLM_NOT_INSTALLED",
                "detail": f"需要 litellm（Python312 已装 1.83.0；如缺失 "
                          f"pip install litellm）：{e}",
                "instruction": "用生产解释器 Python312 运行，或安装 litellm 后重试。"}
    # DEF-1（架构会签）：real 模式 pick 仅对 keyed provider 仲裁——
    # Router 只构建 keyed provider；若 pick 在全部 provider 上仲裁，可能选中
    # 未配置 key 的 provider（如 web_session 恒 UNCONFIGURED 且 priority=1），
    # 导致 Router.completion BadRequestError -> 误报 REAL_CALL_FAILED。
    cfg_keyed: Dict[str, Any] = {
        "schema": cfg.get("schema"), "schema_version": cfg.get("schema_version"),
        "default_timeout_sec": cfg.get("default_timeout_sec"),
        "providers": keyed,
    }
    try:
        router = _build_router_real(keyed, env)
        chosen = pick_provider(cfg_keyed, prefer, env)
        model_name = chosen.get("selected", {}).get("id")
        if not model_name:
            model_name = _provider_id(keyed[0])
        resp = router.completion(
            model=model_name, messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens)
        text = resp.choices[0].message.content or ""
    except Exception as e:  # noqa: BLE001
        return {"schema": SCHEMA, "command": "review", "ok": False,
                "error": "REAL_CALL_FAILED",
                "detail": _safe_text(e, 600),
                "instruction": "真实调用失败；检查 key/网络/模型名（L3 业主）。"}
    return {
        "schema": SCHEMA, "command": "review", "ok": True,
        "mode": "real", "provider_used": model_name,
        "verdict": parse_verdict(text), "raw_text": _safe_text(text, 4000),
        "payload": payload if payload is not None else {},
        "non_authority": True,
        "note": "真实 review：消耗真实额度；调用方需确保授权合规（L3）。",
    }


# ---------------------------------------------------------------------------
# CLI 子命令
# ---------------------------------------------------------------------------
def cmd_health(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(json.dumps({"schema": SCHEMA, "command": "health", "ok": False,
                          "error": "CONFIG_ERROR", "detail": _safe_text(e, 600)},
                         ensure_ascii=False, indent=2))
        return 1
    result = health_probe_all(cfg)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_pick(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(json.dumps({"schema": SCHEMA, "command": "pick", "ok": False,
                          "error": "CONFIG_ERROR", "detail": _safe_text(e, 600)},
                         ensure_ascii=False, indent=2))
        return 1
    result = pick_provider(cfg, prefer=args.prefer or None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def cmd_review(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(json.dumps({"schema": SCHEMA, "command": "review", "ok": False,
                          "error": "CONFIG_ERROR", "detail": _safe_text(e, 600)},
                         ensure_ascii=False, indent=2))
        return 1
    payload = None
    if args.payload:
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError:
            payload = args.payload  # 非 JSON 视为纯文本 payload
    if args.mode == "mock" and args.mock_verdict not in ("PASS", "REWORK"):
        print(json.dumps({"schema": SCHEMA, "command": "review", "ok": False,
                          "error": "BAD_MOCK_VERDICT",
                          "detail": "mock-verdict 必须是 PASS 或 REWORK",
                          "instruction": "重新指定 --mock-verdict PASS|REWORK"},
                         ensure_ascii=False, indent=2))
        return 2
    result = do_review(cfg, mode=args.mode, mock_verdict=args.mock_verdict or "PASS",
                       payload=payload, prefer=args.prefer or None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        return 2 if result.get("error") in ("REAL_CALL_FAILED", "MOCK_ROUTER_FAILED",
                                            "BAD_MOCK_VERDICT") else 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="R-Adapter: R 审查者 Provider 适配层（LiteLLM 接入骨架）")
    sub = ap.add_subparsers(dest="command", required=True)

    p_health = sub.add_parser("health", help="对全部 provider 做健康探测（无 key=UNCONFIGURED）")
    p_health.add_argument("--config", dest="config", required=True,
                          help="R-Adapter JSON 配置文件")

    p_pick = sub.add_parser("pick", help="按 health+priority 仲裁选主 R，输出 fallback 链")
    p_pick.add_argument("--config", dest="config", required=True)
    p_pick.add_argument("--prefer", dest="prefer", default="",
                        help="优先选中的 provider id（仅当其健康 UP 才采纳）")

    p_review = sub.add_parser("review", help="执行结构化审查（LiteLLM Router 接口）")
    p_review.add_argument("--config", dest="config", required=True)
    p_review.add_argument("--mode", dest="mode", default="mock",
                          choices=("mock", "real"),
                          help="mock=内置 mock provider（零额度）；real=需 key（L3 业主）")
    p_review.add_argument("--mock-verdict", dest="mock_verdict", default="PASS",
                          help="mock 判定的期望值 PASS|REWORK")
    p_review.add_argument("--payload", dest="payload", default="",
                          help="审查 payload（JSON 字符串或纯文本）")
    p_review.add_argument("--prefer", dest="prefer", default="",
                          help="real 模式选主 provider id")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    # 控制台统一 UTF-8 输出，避免 GBK console UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.command == "health":
        return cmd_health(args)
    if args.command == "pick":
        return cmd_pick(args)
    if args.command == "review":
        return cmd_review(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
