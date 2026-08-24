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
rem Slice C Goal Contract Lite is an internal integration module, not a second
rem production entry. Contract-sensitive commands still enter only through
rem this run.cmd and then delegate to the frozen runtime.py implementation.
if /I "%~1"=="start" goto goal_contract
if /I "%~1"=="work" goto goal_contract
if /I "%~1"=="step" goto goal_contract
if /I "%~1"=="directive" goto goal_contract
if /I "%~1"=="send" goto goal_contract
if /I "%~1"=="recv" goto goal_contract
if /I "%~1"=="report" goto goal_contract
if /I "%~1"=="done" goto goal_contract
if /I "%~1"=="router-start" goto goal_contract
if /I "%~1"=="router-step" goto goal_contract
if /I "%~1"=="router-run" goto goal_contract
if /I "%~1"=="contract-revise" goto goal_contract
if /I "%~1"=="effect-gate" goto effect_safety
"%APC_PY%" "E:\WB\tools\ai-production-control\runtime\runtime.py" %*
exit /b %errorlevel%

:goal_contract
"%APC_PY%" "%~dp0goal_contract_lite.py" %*
exit /b %errorlevel%

:effect_safety
"%APC_PY%" "%~dp0effect_safety_lite.py" %*
exit /b %errorlevel%

:harness_verify
"%APC_PY%" "%~dp0harness_verify.py" %*
exit /b %errorlevel%
