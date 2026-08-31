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
rem V0.8 Adapter Core: thin dispatch only; runtime.py remains untouched.
if /I "%~1"=="adapter-check" goto v08_adapter
if /I "%~1"=="adapter-invoke" goto v08_adapter
rem Slice C Goal Contract Lite is an internal integration module, not a second
rem production entry. Contract-sensitive commands still enter only through
rem this run.cmd and then delegate to the frozen runtime.py implementation.
if /I "%~1"=="start" goto goal_contract
if /I "%~1"=="work" goto goal_contract
if /I "%~1"=="step" goto goal_contract
if /I "%~1"=="directive" goto goal_contract
if /I "%~1"=="send" goto send_guard
if /I "%~1"=="recv" goto goal_contract
rem HARDENING GATE-1#1 (2026-08-31): report is the ONLY production outbound
rem path (cmd_report -> cmd_send). It previously routed to goal_contract only,
rem which bypassed the Effect Gate -- the same defect send_guard_lite docstring
rem records for `send` before Slice J2. report now rides the identical three-
rem gate chain (contract -> effect_safety -> ec), outermost-first, fail-closed.
if /I "%~1"=="report" goto send_guard
if /I "%~1"=="done" goto goal_contract
if /I "%~1"=="router-start" goto send_guard
if /I "%~1"=="router-step" goto send_guard
if /I "%~1"=="router-run" goto send_guard
if /I "%~1"=="router-continue" goto send_guard
if /I "%~1"=="contract-revise" goto goal_contract
if /I "%~1"=="effect-gate" goto effect_safety
if /I "%~1"=="weak-ai-acceptance" goto weak_ai_acceptance
rem V0.6 EC-lite: execution correction is a rules-only Runtime adapter module,
rem entered through the single official entry like every other subcommand.
if /I "%~1"=="ec-record" goto ec_lite
if /I "%~1"=="ec-check" goto ec_lite
if /I "%~1"=="ec-gate" goto ec_lite
"%APC_PY%" "E:\WB\tools\ai-production-control\runtime\runtime.py" %*
exit /b %errorlevel%

:goal_contract
"%APC_PY%" "%~dp0goal_contract_lite.py" %*
exit /b %errorlevel%

:send_guard
"%APC_PY%" "%~dp0send_guard_lite.py" %*
exit /b %errorlevel%

:effect_safety
"%APC_PY%" "%~dp0effect_safety_lite.py" %*
exit /b %errorlevel%

:weak_ai_acceptance
"%APC_PY%" "%~dp0weak_ai_acceptance.py" %*
exit /b %errorlevel%

:ec_lite
"%APC_PY%" "%~dp0ec_lite.py" %*
exit /b %errorlevel%

:harness_verify
"%APC_PY%" "%~dp0harness_verify.py" %*
exit /b %errorlevel%

:v08_adapter
"%APC_PY%" "%~dp0v08_adapter.py" %*
exit /b %errorlevel%
