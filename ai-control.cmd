@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "AI_CONTROL_ROOT=%~dp0"
"C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe" "%~dp0scripts\ai_control.py" %*
exit /b %ERRORLEVEL%
