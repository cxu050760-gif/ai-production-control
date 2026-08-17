from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+"),
    re.compile(r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|cookie|session[_-]?secret)\s*[=:]\s*)[^\s,;\"']+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
)


class BoundaryError(ValueError):
    """Raised when an input crosses a declared trust or path boundary."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: os.PathLike[str] | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        if pattern.groups:
            redacted = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def atomic_write(path: os.PathLike[str] | str, data: str | bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = data.encode("utf-8") if isinstance(data, str) else data
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        fsync_file(target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def fsync_file(path: os.PathLike[str] | str) -> None:
    # Windows' CRT _commit (used by os.fsync) rejects a read-only descriptor.
    # Open without truncation but with write capability so the durability
    # barrier is real on both Windows and POSIX.
    with open(path, "rb+") as handle:
        os.fsync(handle.fileno())


def read_json(path: os.PathLike[str] | str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: os.PathLike[str] | str, value: Any) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _is_reparse(path: Path) -> bool:
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return False
    attrs = getattr(stat, "st_file_attributes", 0)
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _normal_case(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _inside(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((_normal_case(path), _normal_case(root))) == _normal_case(root)
    except ValueError:
        return False


def safe_resolve(
    raw_path: os.PathLike[str] | str,
    allowed_roots: Iterable[os.PathLike[str] | str],
    *,
    must_exist: bool = False,
    allow_root: bool = True,
) -> Path:
    text = str(raw_path)
    normalized_slashes = text.replace("/", "\\")
    if normalized_slashes.startswith(("\\\\", "\\?\\", "\\.\\")):
        raise BoundaryError("UNC and device paths are denied")
    candidate = Path(text)
    if not candidate.is_absolute():
        raise BoundaryError("relative paths are denied")
    if any(part == ".." for part in candidate.parts):
        raise BoundaryError("parent traversal is denied")
    if any("~" in part for part in candidate.parts[1:]):
        raise BoundaryError("8.3 aliases are denied")
    if len(candidate.drive) != 2 or candidate.drive[1] != ":":
        raise BoundaryError("non-drive paths are denied")

    existing_anchor = candidate
    while not existing_anchor.exists() and existing_anchor != existing_anchor.parent:
        existing_anchor = existing_anchor.parent
    if must_exist and not candidate.exists():
        raise BoundaryError("target does not exist")
    resolved = candidate.resolve(strict=must_exist)

    roots = [Path(root).resolve(strict=True) for root in allowed_roots]
    matched = next((root for root in roots if _inside(resolved, root)), None)
    if matched is None:
        raise BoundaryError("resolved target is outside allowed roots")
    if not allow_root and _normal_case(resolved) == _normal_case(matched):
        raise BoundaryError("allowed-root itself is not a valid target")

    cursor = existing_anchor.resolve(strict=True)
    while _inside(cursor, matched):
        if _is_reparse(cursor):
            raise BoundaryError(f"reparse-point component denied: {cursor}")
        if _normal_case(cursor) == _normal_case(matched):
            break
        cursor = cursor.parent
    return resolved


def tree_manifest(
    root: os.PathLike[str] | str,
    *,
    exclude_dirs: Iterable[str] = (".git", "node_modules", "__pycache__"),
    exclude_files: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], str, int]:
    base = Path(root).resolve(strict=True)
    excluded_dir_names = set(exclude_dirs)
    excluded_files = {item.replace("\\", "/") for item in exclude_files}
    entries: list[dict[str, Any]] = []
    total_size = 0
    for current, dirs, files in os.walk(base):
        dirs[:] = sorted(name for name in dirs if name not in excluded_dir_names)
        for filename in sorted(files):
            path = Path(current) / filename
            relative = path.relative_to(base).as_posix()
            if relative in excluded_files or filename.endswith((".pyc", ".pyo")):
                continue
            size = path.stat().st_size
            total_size += size
            entries.append({"path": relative, "size": size, "sha256": sha256_file(path)})
    digest = sha256_text(canonical_json(entries))
    return entries, digest, total_size


def windows_boot_session_id() -> str:
    if os.name != "nt":
        return sha256_text(str(os.getpid()))[:16]
    uptime_ms = ctypes.windll.kernel32.GetTickCount64()
    boot_epoch_ms = int(datetime.now(UTC).timestamp() * 1000) - int(uptime_ms)
    return sha256_text(str(boot_epoch_ms // 60_000))[:16]


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_expired(value: str) -> bool:
    return parse_iso(value) <= datetime.now(UTC)
