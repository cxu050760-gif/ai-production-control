from __future__ import annotations

import ctypes
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .util import BoundaryError, redact, safe_resolve, sha256_text, utc_now


@dataclass(frozen=True)
class ProcessResult:
    executable: str
    argv: list[str]
    cwd: str
    pid: int
    process_start_identity: str
    started_at: str
    finished_at: str
    duration_ms: int
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool

    def safe_record(self) -> dict:
        value = asdict(self)
        value["stdout"] = redact(value["stdout"])
        value["stderr"] = redact(value["stderr"])
        return value


if os.name == "nt":
    from ctypes import wintypes

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


class JobObject:
    """Windows Job Object with kill-on-close containment."""

    def __init__(self) -> None:
        self.handle = None
        if os.name != "nt":
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        self.handle = kernel32.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = kernel32.SetInformationJobObject(
            self.handle,
            9,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            self.close()
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")

    def assign(self, process: subprocess.Popen[str]) -> None:
        if os.name != "nt" or not self.handle:
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        if not kernel32.AssignProcessToJobObject(self.handle, wintypes.HANDLE(process._handle)):
            error = ctypes.get_last_error()
            self.close()
            raise OSError(error, "AssignProcessToJobObject failed")

    def close(self) -> None:
        if os.name == "nt" and self.handle:
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "JobObject":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


def run_structured(
    executable: str,
    argv: Sequence[str],
    *,
    cwd: str,
    allowed_cwd_roots: Sequence[str],
    env: Mapping[str, str] | None = None,
    timeout_seconds: float = 60,
    register: Callable[[dict], None] | None = None,
    hidden: bool = True,
) -> ProcessResult:
    if not isinstance(argv, (list, tuple)) or not all(isinstance(item, str) for item in argv):
        raise BoundaryError("argv must be a sequence of strings")
    executable_path = Path(executable).resolve(strict=True)
    cwd_path = safe_resolve(cwd, allowed_cwd_roots, must_exist=True)
    merged_env = os.environ.copy()
    if env:
        for key, value in env.items():
            if not re_env_name(key):
                raise BoundaryError(f"invalid environment key: {key}")
            if "\x00" in value:
                raise BoundaryError("NUL in environment value")
            merged_env[key] = value

    creationflags = 0
    startupinfo = None
    if os.name == "nt":
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        if hidden:
            creationflags |= subprocess.CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

    started_at = utc_now()
    started_ns = time.time_ns()
    command = [str(executable_path), *argv]
    with JobObject() as job:
        process = subprocess.Popen(
            command,
            cwd=str(cwd_path),
            env=merged_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
        job.assign(process)
        process_identity = sha256_text(f"{process.pid}:{started_ns}:{executable_path}")[:24]
        if register:
            register(
                {
                    "pid": process.pid,
                    "process_start_identity": process_identity,
                    "executable": str(executable_path),
                    "argv": list(argv),
                    "cwd": str(cwd_path),
                    "started_at": started_at,
                }
            )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            # Descendants may inherit stdout/stderr pipe handles. Closing the
            # Job before the second communicate kills the whole process tree
            # and prevents the inherited handles from deadlocking collection.
            job.close()
            stdout, stderr = process.communicate(timeout=10)
        finished_ns = time.time_ns()
        finished_at = utc_now()
        return ProcessResult(
            executable=str(executable_path),
            argv=list(argv),
            cwd=str(cwd_path),
            pid=process.pid,
            process_start_identity=process_identity,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=max(0, (finished_ns - started_ns) // 1_000_000),
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
        )


def re_env_name(value: str) -> bool:
    return bool(value) and value.replace("_", "a").isalnum() and not value[0].isdigit()
