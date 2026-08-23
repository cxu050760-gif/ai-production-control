@echo off
rem Weak-AI Production Runtime V1 - single production entry
rem Post-entry environment diagnosis: if the canonical dependency is missing,
rem emit a stable machine status instead of a raw shell error.
set "APC_PY=C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%APC_PY%" (
  echo {"status":"RUNTIME_ENV_BLOCKED","missing":"%APC_PY%","instruction":"canonical Python dependency missing; report to user; do not substitute shells or edit PATH"}
  exit /b 90
)
rem V0.1 unattended Harness is a Runtime-owned subcommand that reuses the
rem existing WorkBuddy Parallel launcher through harness_verify.py.
if /I "%~1"=="harness-verify" goto harness_verify
"%APC_PY%" "E:\WB\tools\ai-production-control\runtime\runtime.py" %*
exit /b %errorlevel%

:harness_verify
"%APC_PY%" "%~dp0harness_verify.py" %*
exit /b %errorlevel%