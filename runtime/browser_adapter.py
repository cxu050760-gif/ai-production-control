"""Browser Adapter — Playwright 通用网页适配器 + download 命令（v1.1-blackbox D3，S3）。

背景：宪法 §20 浏览器是通用生产执行面。SUCCESSOR 报告 §20 记录 download ❌
（从 ChatGPT 下载文件未开发）且通用网页操作（非 ChatGPT 站）未开发。
本模块用 Playwright（微软官方，§48 Reuse 门禁结论：Reuse>Build）补齐：

  - search   : 打开搜索引擎（默认 bing）抓取结果标题/URL/摘要 -> 结构化 JSON
  - fetch    : 抓取页面正文文本/标题/最终 URL -> JSON
  - download : 下载文件到 dest（Playwright download 事件或 APIRequest 流式）
                -> 输出文件路径/大小/校验和(sha256)
  - status   : Playwright 可用性报告（含 bsk 边界说明）

边界（README 亦注明）：
  - 登录态敏感站（ChatGPT 等需登录态）走 bsk（52900 桥 / chatgpt_bridge）；
  - 通用站（无需登录态）走本适配器（Playwright headless）。
  - 本模块一律使用独立临时 profile，绝不触碰凭据 / browser-profile（只登记路径）。

环境注意（本机实测）：全局 NODE_OPTIONS=--use-system-ca 会令 Playwright 的
node driver 启动失败，本模块在启动时清除 NODE_OPTIONS（仅影响子进程）。

用法（独立 CLI，仿 blackbox_bridge / r_adapter 模式；JSON 输出/退出码 0/1/2）：
    python runtime/browser_adapter.py status
    python runtime/browser_adapter.py search --query "playwright 下载文件" --max 5
    python runtime/browser_adapter.py fetch --url https://example.com/
    python runtime/browser_adapter.py download --url <U> --dest E:/WB/outputs/ai-production-control

红线：
  1) 不写凭据/不触碰 browser-profile；profile 一律临时目录、用完删除；
  2) 输出为 inert 数据（non_authority）；headless 通用抓取不依赖登录态；
  3) 不改 src/aicontrol/、config/production.json、runtime/runtime.py。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "v1.1-d3-browser-adapter"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = Path(r"E:\WB\outputs\ai-production-control")
# 与 config/production.json browser.chrome_executable 对齐（只读引用；缺省用 Playwright 自带 chromium）
CHROME_EXECUTABLE = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")

_BING_URL = "https://www.bing.com/search"
_MAX_BODY_CHARS = 20000
_DOWNLOAD_EVENT_TIMEOUT_MS = 12000


def _safe_text(value: Any, limit: int = 2000) -> str:
    """任意值 -> 干净 str，限长，剔除不可打印控制符。"""
    if value is None:
        return ""
    text = str(value)
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return text[:limit]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitize_node_options() -> None:
    """清除会破坏 Playwright node driver 的 NODE_OPTIONS（本机实测 --use-system-ca）。"""
    os.environ.pop("NODE_OPTIONS", None)


def playwright_available() -> bool:
    """探测 Playwright 是否可导入（懒加载，status 在未装时也能工作）。"""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def chromium_installed() -> bool:
    """探测 Playwright 自带 chromium 是否已安装（ms-playwright 目录）。"""
    try:
        import playwright  # noqa: F401
        pkg_dir = Path(playwright.__file__).resolve().parent
        # 常见安装位置：%LOCALAPPDATA%/ms-playwright
        home = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        pw_dir = home / "ms-playwright"
        if pw_dir.exists():
            return any(p.name.startswith("chromium") or p.name.startswith("chromium_headless_shell")
                       for p in pw_dir.iterdir())
        return False
    except Exception:  # noqa: BLE001
        return False


def _launch_kwargs(proxy: str, headed: bool, timeout_ms: int) -> Dict[str, Any]:
    """构造 launch_persistent_context 参数（独立临时 profile，不触碰凭据）。"""
    kwargs: Dict[str, Any] = {
        "headless": not headed,
        "args": ["--no-sandbox", "--disable-dev-shm-usage",
                 "--disable-blink-features=AutomationControlled"],
        "timeout": timeout_ms,
        "viewport": {"width": 1280, "height": 900},
    }
    if proxy:
        kwargs["proxy"] = {"server": proxy}
    return kwargs


def _get_playwright():
    """懒导入 playwright sync_api（未装时抛 ImportError，由调用方捕获）。"""
    from playwright.sync_api import sync_playwright
    return sync_playwright()


def _close_profile(user_data_dir: str) -> None:
    """删除临时 profile 目录（ignore_errors，绝不保留凭据残留）。"""
    shutil.rmtree(user_data_dir, ignore_errors=True)


def _build_mock_search_page(query: str, max_results: int) -> str:
    """构造 mock 搜索结果页（离线冒烟用；标记 mock 供调用方识别）。"""
    items = "".join(
        f'<li class="b_algo"><h2><a href="https://mock.example.com/result{i}">'
        f'Mock Result {i} for {query}</a></h2>'
        f'<div class="b_caption"><p>Mock snippet {i}：这是离线冒烟数据，'
        f'不代表真实搜索结果。</p></div></li>'
        for i in range(1, max_results + 1)
    )
    return (f"<html><head><title>mock search: {query}</title></head>"
            f"<body><ol id='b_results'>{items}</ol></body></html>")


def _parse_bing_results(page: Any, max_results: int) -> List[Dict[str, Any]]:
    """从 Bing 结果页解析结果（li.b_algo；带通用回退）。"""
    results: List[Dict[str, Any]] = []
    try:
        items = page.query_selector_all("li.b_algo")
    except Exception:  # noqa: BLE001
        items = []
    for li in items[:max_results]:
        try:
            a = li.query_selector("h2 a") or li.query_selector("a")
            title = _safe_text(a.inner_text(), 300) if a else ""
            href = a.get_attribute("href") if a else ""
            cap = li.query_selector(".b_caption") or li.query_selector("p")
            snippet = _safe_text(cap.inner_text(), 1000) if cap else ""
        except Exception:  # noqa: BLE001
            continue
        if href:
            results.append({"title": title, "url": href, "snippet": snippet})
        if len(results) >= max_results:
            break
    # 回退：无 li.b_algo 时收集所有外链
    if not results:
        try:
            links = page.query_selector_all("a[href^='http']")
            for a in links[:max_results * 2]:
                href = a.get_attribute("href") or ""
                text = _safe_text(a.inner_text(), 200)
                if href and text and "bing.com" not in href and "microsoft" not in href:
                    results.append({"title": text, "url": href, "snippet": ""})
                    if len(results) >= max_results:
                        break
        except Exception:  # noqa: BLE001
            pass
    return results


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------
def cmd_status(args: argparse.Namespace) -> int:
    """Playwright 可用性报告（含 bsk 边界说明）。"""
    _sanitize_node_options()
    avail = playwright_available()
    chrome = CHROME_EXECUTABLE.exists()
    browsers = chromium_installed() if avail else False
    detail: List[str] = []
    if not avail:
        detail.append("playwright 未安装：`python -m pip install playwright "
                      "--proxy http://127.0.0.1:7897 "
                      "-i https://pypi.tuna.tsinghua.edu.cn/simple`，随后 "
                      "`python -m playwright install chromium`")
        status = "PLAYWRIGHT_NOT_INSTALLED"
    elif not browsers:
        detail.append("playwright 已装但 chromium 未装："
                      "`python -m playwright install chromium`（或仅核心）")
        status = "PLAYWRIGHT_INSTALLED_NO_BROWSER"
    else:
        detail.append("playwright + chromium 就绪，可 headless 通用抓取")
        status = "PLAYWRIGHT_READY"
    print(json.dumps({
        "schema": SCHEMA, "command": "status", "ok": True,
        "status": status,
        "playwright_installed": avail,
        "chromium_installed": browsers,
        "system_chrome_exists": chrome,
        "system_chrome_path": str(CHROME_EXECUTABLE),
        "detail": "；".join(detail) if detail else "OK",
        "boundary": {
            "playwright": "通用站（无需登录态）：search/fetch/download，headless 独立临时 profile",
            "bsk": "登录态敏感站（ChatGPT 等）：走 bsk（52900 桥 / chatgpt_bridge），"
                   "与本适配器互不依赖",
            "credential": "本适配器不触碰凭据/browser-profile；profile 一律临时、用完删除",
        },
        "non_authority": True,
    }, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------
def cmd_search(args: argparse.Namespace) -> int:
    """搜索引擎抓取：打开 bing（或 mock），解析结果 -> JSON。"""
    _sanitize_node_options()
    query = _safe_text(args.query, 500).strip()
    if not query:
        print(json.dumps({"schema": SCHEMA, "command": "search", "ok": False,
                          "error": "QUERY_REQUIRED",
                          "instruction": "--query 不能为空。"},
                         ensure_ascii=False, indent=2))
        return 2
    max_n = max(1, min(int(args.max), 20))
    engine = (args.engine or "bing").lower()

    if args.mock:
        return _search_mock(query, max_n)

    if not playwright_available():
        print(json.dumps({"schema": SCHEMA, "command": "search", "ok": False,
                          "error": "PLAYWRIGHT_NOT_INSTALLED",
                          "detail": "playwright 未安装（安装命令见 status 输出）",
                          "instruction": "先安装 playwright + chromium；或使用 --mock 冒烟。"},
                         ensure_ascii=False, indent=2))
        return 1

    profile = tempfile.mkdtemp(prefix="pw_search_")
    try:
        with _get_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=profile, **_launch_kwargs(args.proxy, args.headed, 30000))
            page = ctx.new_page()
            if engine == "bing":
                url = f"{_BING_URL}?q={urllib.parse.quote(query)}"
            elif engine == "duckduckgo":
                url = f"https://duckduckgo.com/?q={urllib.parse.quote(query)}"
            else:
                url = f"{_BING_URL}?q={urllib.parse.quote(query)}"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.0)  # 等待结果渲染（Bing 常见异步）
            results = _parse_bing_results(page, max_n)
            final_url = _safe_text(page.url, 500)
            ctx.close()
    except Exception as e:  # noqa: BLE001 —— 网络/页面失败即报错，不伪造
        print(json.dumps({"schema": SCHEMA, "command": "search", "ok": False,
                          "error": "SEARCH_FAILED",
                          "detail": _safe_text(e, 500),
                          "instruction": "检查网络/代理（--proxy http://127.0.0.1:7897）；"
                                         "或 --mock 离线冒烟。"},
                         ensure_ascii=False, indent=2))
        return 1
    finally:
        _close_profile(profile)

    print(json.dumps({
        "schema": SCHEMA, "command": "search", "ok": True,
        "query": query, "engine": engine, "mock": False,
        "result_count": len(results), "final_url": final_url,
        "results": results,
        "fetched_at": _now_iso(),
        "non_authority": True,
        "note": "通用搜索引擎抓取（headless，不依赖登录态）；登录态敏感站请走 bsk。",
    }, ensure_ascii=False, indent=2))
    return 0


def _search_mock(query: str, max_n: int) -> int:
    """离线冒烟：解析本地构造的 mock 结果页（明确标注 mock）。"""
    html = _build_mock_search_page(query, max_n)
    # 用 Playwright 解析本地 HTML（若可用）；否则手工解析
    results: List[Dict[str, Any]] = []
    if playwright_available():
        profile = tempfile.mkdtemp(prefix="pw_search_mock_")
        try:
            with _get_playwright() as p:
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=profile, headless=True,
                    args=["--no-sandbox"])
                page = ctx.new_page()
                page.set_content(html)
                results = _parse_bing_results(page, max_n)
                ctx.close()
        except Exception:  # noqa: BLE001
            results = []
        finally:
            _close_profile(profile)
    if not results:
        for i in range(1, max_n + 1):
            results.append({
                "title": f"Mock Result {i} for {query}",
                "url": f"https://mock.example.com/result{i}",
                "snippet": f"Mock snippet {i}：这是离线冒烟数据，不代表真实搜索结果。",
            })
    print(json.dumps({
        "schema": SCHEMA, "command": "search", "ok": True,
        "query": query, "engine": "mock", "mock": True,
        "result_count": len(results), "final_url": "mock://local",
        "results": results,
        "fetched_at": _now_iso(),
        "non_authority": True,
        "note": "MOCK 冒烟：本地构造页面，不代表真实搜索结果；真实抓取请联网运行。",
    }, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------
def cmd_fetch(args: argparse.Namespace) -> int:
    """抓取页面正文文本/标题/最终 URL -> JSON。"""
    _sanitize_node_options()
    url = _safe_text(args.url, 1000).strip()
    if not url:
        print(json.dumps({"schema": SCHEMA, "command": "fetch", "ok": False,
                          "error": "URL_REQUIRED", "instruction": "--url 不能为空。"},
                         ensure_ascii=False, indent=2))
        return 2

    if args.mock:
        print(json.dumps({
            "schema": SCHEMA, "command": "fetch", "ok": True, "mock": True,
            "url": url, "final_url": "mock://local",
            "title": "Mock Page Title", "body_text": "这是离线冒烟正文，"
            "不代表真实页面内容。", "body_chars": 18,
            "fetched_at": _now_iso(), "non_authority": True,
            "note": "MOCK 冒烟：本地构造内容；真实抓取请联网运行。",
        }, ensure_ascii=False, indent=2))
        return 0

    if not playwright_available():
        print(json.dumps({"schema": SCHEMA, "command": "fetch", "ok": False,
                          "error": "PLAYWRIGHT_NOT_INSTALLED",
                          "detail": "playwright 未安装（安装命令见 status 输出）",
                          "instruction": "先安装 playwright + chromium；或 --mock 冒烟。"},
                         ensure_ascii=False, indent=2))
        return 1

    profile = tempfile.mkdtemp(prefix="pw_fetch_")
    try:
        with _get_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=profile, **_launch_kwargs(args.proxy, args.headed, 30000))
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(0.5)
            title = _safe_text(page.title(), 500)
            final_url = _safe_text(page.url, 1000)
            try:
                body = page.inner_text("body")
            except Exception:  # noqa: BLE001
                body = ""
            body = _safe_text(body, _MAX_BODY_CHARS)
            ctx.close()
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"schema": SCHEMA, "command": "fetch", "ok": False,
                          "error": "FETCH_FAILED", "detail": _safe_text(e, 500),
                          "instruction": "检查 URL/网络/代理；或 --mock 冒烟。"},
                         ensure_ascii=False, indent=2))
        return 1
    finally:
        _close_profile(profile)

    print(json.dumps({
        "schema": SCHEMA, "command": "fetch", "ok": True, "mock": False,
        "url": url, "final_url": final_url,
        "title": title, "body_text": body, "body_chars": len(body),
        "fetched_at": _now_iso(), "non_authority": True,
        "note": "通用页面抓取（headless，不依赖登录态）；登录态敏感站请走 bsk。",
    }, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_playwright(url: str, dest_dir: Path, proxy: str,
                         timeout_ms: int) -> Dict[str, Any]:
    """Playwright 下载：优先 download 事件；未触发时用 APIRequest 流式保存。

    返回 {"mode": "playwright-download"|"playwright-request", "path": str, ...}。
    """
    _sanitize_node_options()
    profile = tempfile.mkdtemp(prefix="pw_dl_")
    try:
        with _get_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=profile, **_launch_kwargs(proxy, False, timeout_ms))
            page = ctx.new_page()
            # 策略 1：download 事件（内容协商为附件时触发）
            try:
                with page.expect_download(timeout=_DOWNLOAD_EVENT_TIMEOUT_MS) as dl_info:
                    page.goto(url, timeout=timeout_ms)
                dl = dl_info.value
                name = dl.suggested_filename or Path(urllib.parse.urlparse(url).path).name \
                    or "download.bin"
                target = dest_dir / name
                dl.save_as(str(target))
                ctx.close()
                return {"mode": "playwright-download", "path": str(target),
                        "suggested_filename": dl.suggested_filename}
            except Exception:  # noqa: BLE001 —— 无 download 事件，回退策略 2
                pass
            # 策略 2：APIRequest 流式（仍是 Playwright 机制）
            resp = ctx.request.get(url, timeout=timeout_ms)
            if resp.status != 200:
                ctx.close()
                raise RuntimeError(f"download http status={resp.status}")
            body = resp.body()
            content_type = resp.headers.get("content-type", "")
            name = Path(urllib.parse.urlparse(url).path).name or "download.bin"
            if not name or name == "/":
                name = "download.bin"
            target = dest_dir / name
            target.write_bytes(body)
            ctx.close()
            return {"mode": "playwright-request", "path": str(target),
                    "content_type": content_type}
    finally:
        _close_profile(profile)


def _download_requests(url: str, dest_dir: Path, proxy: str,
                       timeout_sec: int) -> Dict[str, Any]:
    """requests 流式下载（strategy=requests 或 playwright 不可用时的回退）。"""
    import requests
    kwargs: Dict[str, Any] = {"timeout": timeout_sec, "stream": True}
    if proxy:
        kwargs["proxies"] = {"http": proxy, "https": proxy}
    with requests.get(url, **kwargs) as r:
        r.raise_for_status()
        cd = r.headers.get("content-disposition", "")
        name = ""
        m = re.search(r"filename\*?=(?:UTF-8'')?[\"']?([^\"';]+)", cd, re.IGNORECASE)
        if m:
            name = urllib.parse.unquote(m.group(1).strip())
        if not name:
            name = Path(urllib.parse.urlparse(url).path).name or "download.bin"
        target = dest_dir / name
        with open(target, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
        return {"mode": "requests", "path": str(target),
                "content_type": r.headers.get("content-type", "")}


def cmd_download(args: argparse.Namespace) -> int:
    """下载文件到 dest（Playwright download 事件 / APIRequest / requests 流式）。"""
    _sanitize_node_options()
    url = _safe_text(args.url, 1000).strip()
    if not url:
        print(json.dumps({"schema": SCHEMA, "command": "download", "ok": False,
                          "error": "URL_REQUIRED", "instruction": "--url 不能为空。"},
                         ensure_ascii=False, indent=2))
        return 2
    dest = Path(args.dest) if args.dest else DEFAULT_DEST
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(json.dumps({"schema": SCHEMA, "command": "download", "ok": False,
                          "error": "DEST_UNWRITABLE", "detail": _safe_text(e, 300),
                          "instruction": "检查 --dest 目录权限。"},
                         ensure_ascii=False, indent=2))
        return 1

    if args.mock:
        target = dest / "mock-download.txt"
        payload = f"mock download from {url} at {_now_iso()}\n"
        target.write_text(payload, encoding="utf-8")
        size = target.stat().st_size
        print(json.dumps({
            "schema": SCHEMA, "command": "download", "ok": True, "mock": True,
            "url": url, "dest": str(dest), "file": str(target),
            "size": size, "sha256": _sha256(target),
            "fetched_at": _now_iso(), "non_authority": True,
            "note": "MOCK 冒烟：本地构造文件，不代表真实下载；真实下载请联网运行。",
        }, ensure_ascii=False, indent=2))
        return 0

    strategy = (args.strategy or "auto").lower()
    timeout_sec = max(10, int(args.timeout))

    try:
        if strategy in ("auto", "playwright"):
            if not playwright_available():
                if strategy == "playwright":
                    raise RuntimeError("playwright 未安装")
                # auto + 无 playwright -> requests 回退
                result = _download_requests(url, dest, args.proxy, timeout_sec)
            else:
                result = _download_playwright(url, dest, args.proxy, timeout_sec * 1000)
        else:
            result = _download_requests(url, dest, args.proxy, timeout_sec)
    except Exception as e:  # noqa: BLE001 —— 下载失败即报错，不伪造
        print(json.dumps({"schema": SCHEMA, "command": "download", "ok": False,
                          "error": "DOWNLOAD_FAILED", "detail": _safe_text(e, 500),
                          "instruction": "检查 URL/网络/代理；或 --mock 冒烟。"},
                         ensure_ascii=False, indent=2))
        return 1

    path = Path(result["path"])
    size = path.stat().st_size
    print(json.dumps({
        "schema": SCHEMA, "command": "download", "ok": True, "mock": False,
        "url": url, "dest": str(dest), "file": str(path),
        "mode": result.get("mode", ""),
        "suggested_filename": result.get("suggested_filename"),
        "content_type": result.get("content_type"),
        "size": size, "sha256": _sha256(path),
        "fetched_at": _now_iso(), "non_authority": True,
        "note": "通用下载（Playwright/requests 流式，headless）；登录态敏感站请走 bsk。",
    }, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Browser Adapter: Playwright 通用网页适配器 + download（宪法 §20）")
    sub = ap.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Playwright 可用性报告（含 bsk 边界）")

    p_search = sub.add_parser("search", help="搜索引擎抓取结果（默认 bing）")
    p_search.add_argument("--query", dest="query", required=True)
    p_search.add_argument("--max", dest="max", type=int, default=5,
                          help="最大结果数（默认 5）")
    p_search.add_argument("--engine", dest="engine", default="bing",
                          choices=("bing", "duckduckgo"))
    p_search.add_argument("--proxy", dest="proxy", default="",
                          help="代理，如 http://127.0.0.1:7897")
    p_search.add_argument("--headed", dest="headed", action="store_true",
                          help="有头模式（调试用；默认 headless）")
    p_search.add_argument("--mock", dest="mock", action="store_true",
                          help="离线冒烟（本地构造页面）")

    p_fetch = sub.add_parser("fetch", help="抓取页面正文/标题/最终 URL")
    p_fetch.add_argument("--url", dest="url", required=True)
    p_fetch.add_argument("--proxy", dest="proxy", default="")
    p_fetch.add_argument("--headed", dest="headed", action="store_true")
    p_fetch.add_argument("--mock", dest="mock", action="store_true")

    p_dl = sub.add_parser("download", help="下载文件到 dest（输出路径/大小/校验和）")
    p_dl.add_argument("--url", dest="url", required=True)
    p_dl.add_argument("--dest", dest="dest", default="",
                      help=f"目标目录（默认 {DEFAULT_DEST}）")
    p_dl.add_argument("--strategy", dest="strategy", default="auto",
                      choices=("auto", "playwright", "requests"))
    p_dl.add_argument("--proxy", dest="proxy", default="")
    p_dl.add_argument("--timeout", dest="timeout", type=int, default=60)
    p_dl.add_argument("--mock", dest="mock", action="store_true")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    # 控制台统一 UTF-8 输出，避免 GBK console UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    _sanitize_node_options()
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "search":
        return cmd_search(args)
    if args.command == "fetch":
        return cmd_fetch(args)
    if args.command == "download":
        return cmd_download(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
