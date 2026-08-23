@echo off
rem Weak-AI Production Runtime V1 - single production entry
rem Post-entry environment diagnosis: if the canonical dependency is missing,
rem emit a stable machine status instead of a raw shell error.
set "APC_PY=C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%APC_PY%" (
  echo {"status":"RUNTIME_ENV_BLOCKED","missing":"%APC_PY%","instruction":"canonical Python dependency missing; report to user; do not substitute shells or edit PATH"}
  exit /b 90
)
"%APC_PY%" "E:\WB\tools\ai-production-control\runtime\runtime.py" %*
