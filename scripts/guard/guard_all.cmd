@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM ============================================================
REM  ZhihengGuard - R1 guardian layer (执衡 v1.1-blackbox)
REM  Scheduled task "ZhihengGuard" runs this every 2 minutes.
REM
REM  Scope (R1 / 宪法 §14/§61):
REM    a) watcher heartbeat liveness -> kill stale + restart relay
REM    b) bsk daemon (port 52900) probe -> restart if down
REM    c) Chrome extension connection check -> record + manual hint
REM       (never auto-opens Chrome; non-blocking)
REM    d) state integrity check -> record + upgrade hint
REM       (no auto recovery; state-recover not in production runtime)
REM
REM  Every action appends one JSON row to guard-actions.ndjson
REM  (timestamp/action/detail/ok). Script is idempotent: probes
REM  first, never re-launches an already-running process.
REM
REM  Only touches: this scripts/guard dir + guard-actions.ndjson
REM  ledger + runtime log files under the state root.
REM ============================================================

REM ---------- configuration ----------
set "RELAY_REPO=E:\WB\tools\Trae-Ralph"
set "STATE_ROOT=E:\WB\state\ai-production-control\construction-relay"
set "STATE_DIR=E:\WB\state\ai-production-control"
set "RELAY_CONFIG=%STATE_ROOT%\relay.config.json"
set "HEARTBEAT=%STATE_ROOT%\watcher-heartbeat.json"
set "LEDGER=%STATE_ROOT%\guard-actions.ndjson"
set "BSK_EXE=E:\WB\tools\bsk-file-bridge\dist\bsk-dev.exe"
set "BSK_HOME=E:/WB/tools/bsk-file-bridge/bsk-home"
REM BSK_PORT is resolved dynamically from daemon.json ws_port by
REM :read_bsk_port (the daemon rewrites daemon.json on every start).
REM Canonical port is 52900 = production blackbox runtime.py hardcodes it
REM (daemon start --port 52900; extension bakes ws://127.0.0.1:52900).
REM 52800 is the bsk-crate DEFAULT_WS_PORT and must NOT be used:
REM daemon would drift off the blackbox port and R transport breaks.
set "BSK_PORT=52900"
set "STALE_SECS=300"

REM ---------- single-instance lock (D2) ----------
REM mkdir-atomic lock dir + lock.json{token,at}. Stale when lock age
REM > LOCK_STALE_SECS OR lock.json missing/unreadable -> takeover.
REM (Deliberately token-based, NOT pid-based: a powershell spawned
REM inside for /f is parented to a transient cmd, so a stored pid
REM would look dead immediately and break concurrent mutual
REM exclusion. Token is used only for release matching.)
set "LOCK_DIR=%STATE_ROOT%\.zhg-lock"
set "LOCK_INFO=%LOCK_DIR%\lock.json"
set "LOCK_STALE_SECS=300"
set "LOCK_HELD=0"
set "LOCK_TOKEN="
set "LOCK_OWNER_TOKEN="
set "LOCK_AGE="

REM ---------- run timestamp ----------
set "NOW_ISO="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')"`) do set "NOW_ISO=%%A"
set "STAMP="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "Get-Date -Format 'yyyyMMddHHmmss'"`) do set "STAMP=%%A"
echo [%NOW_ISO%] ZhihengGuard run start

REM ---------- resolve node binary (robust under scheduled task) ----------
set "NODE_BIN="
for /f "usebackq delims=" %%A in (`where node`) do if not defined NODE_BIN set "NODE_BIN=%%A"
if not defined NODE_BIN set "NODE_BIN=C:\Program Files\nodejs\node.exe"

call :acquire_lock
if "!LOCK_HELD!"=="0" (
    echo [%NOW_ISO%] [SKIP] guard_lock: SKIP_LOCKED - another instance holds the lock owner_token=!LOCK_OWNER_TOKEN! age=!LOCK_AGE!s
    set "G_ACTION=guard_lock"
    set "G_DETAIL=SKIP_LOCKED owner_token=!LOCK_OWNER_TOKEN! age=!LOCK_AGE!s"
    set "G_OK=false"
    call :ledger
    exit /b 0
)
call :heartbeat_check
if "!HB_STALE!"=="1" (
    call :kill_stale
    call :start_watcher
    call :start_guard
)
call :bsk_check
call :chrome_check
call :state_check

call :release_lock
echo [%NOW_ISO%] ZhihengGuard run end
exit /b 0

REM ============================================================
REM  a) heartbeat liveness check (core)
REM ============================================================
:heartbeat_check
set "HB_AGE="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$f='%HEARTBEAT%'; try { $fs=[System.IO.File]::Open($f,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,[System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete); try { $sr=New-Object System.IO.StreamReader($fs); $txt=$sr.ReadToEnd() } finally { $sr.Close(); $fs.Close() }; $j=$txt | ConvertFrom-Json; $at=[datetime]::Parse($j.at).ToUniversalTime(); [math]::Round(((Get-Date).ToUniversalTime() - $at).TotalSeconds) } catch { Write-Output '-1' }"`) do set "HB_AGE=%%A"
if not defined HB_AGE set "HB_AGE=-1"
set "G_ACTION=heartbeat_check"
if "!HB_AGE!"=="-1" (
    set "HB_STALE=1"
    set "G_DETAIL=heartbeat file missing or unreadable"
    set "G_OK=false"
    echo [%NOW_ISO%] [WARN] heartbeat_check: !G_DETAIL! - treating watcher as DEAD
) else if !HB_AGE! GTR %STALE_SECS% (
    set "HB_STALE=1"
    set "G_DETAIL=heartbeat age=!HB_AGE!s threshold=%STALE_SECS%s"
    set "G_OK=false"
    echo [%NOW_ISO%] [WARN] heartbeat_check: age=!HB_AGE!s - watcher DEAD
) else (
    set "HB_STALE=0"
    set "G_DETAIL=heartbeat age=!HB_AGE!s threshold=%STALE_SECS%s"
    set "G_OK=true"
    echo [%NOW_ISO%] [OK] heartbeat_check: age=!HB_AGE!s - watcher ALIVE
)
call :ledger
exit /b 0

REM ============================================================
REM  kill stale review-relay watch / outer-guard watch trees
REM  (match by command line of node.exe; never by WINDOWTITLE)
REM ============================================================
:kill_stale
set "G_ACTION=kill_stale"
set "KILLED=0"
set "KILL_FAIL=0"
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' -and ($_.CommandLine -match 'review-relay\.js\s+watch' -or $_.CommandLine -match 'outer-guard\.js\s+watch') } | ForEach-Object { $_.ProcessId }"`) do (
    echo [%NOW_ISO%] [ACTION] kill_stale: taskkill /F /T pid=%%P
    taskkill /F /T /PID %%P >nul 2>&1
    if errorlevel 1 (
        set "KILL_FAIL=1"
    ) else (
        set "KILLED=1"
    )
)
if "!KILL_FAIL!"=="1" (
    set "G_DETAIL=taskkill failed for one or more stale processes"
    set "G_OK=false"
    echo [%NOW_ISO%] [WARN] kill_stale: !G_DETAIL!
) else if "!KILLED!"=="1" (
    set "G_DETAIL=stale watcher/guard process trees killed"
    set "G_OK=true"
    echo [%NOW_ISO%] [OK] kill_stale: !G_DETAIL!
) else (
    set "G_DETAIL=no stale watcher/guard processes found"
    set "G_OK=true"
    echo [%NOW_ISO%] [OK] kill_stale: !G_DETAIL!
)
call :ledger
exit /b 0

REM ============================================================
REM  start review-relay.js watch (official entry, detached)
REM ============================================================
:start_watcher
set "G_ACTION=start_watcher"
set "WPID="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' } | Where-Object { $_.CommandLine -match 'review-relay\.js\s+watch' } | ForEach-Object { $_.ProcessId }"`) do set "WPID=%%P"
if defined WPID (
    set "G_DETAIL=already running pid=!WPID!"
    set "G_OK=true"
    echo [%NOW_ISO%] [OK] start_watcher: already running pid=!WPID!
) else (
    echo [%NOW_ISO%] [ACTION] start_watcher: node src\review-relay.js watch --config %RELAY_CONFIG%
    pushd "%RELAY_REPO%"
    start "" /b "%NODE_BIN%" src\review-relay.js watch --config "%RELAY_CONFIG%" >> "%STATE_ROOT%\zhg-watcher-%STAMP%.out.log" 2>> "%STATE_ROOT%\zhg-watcher-%STAMP%.err.log"
    popd
    set "WPID="
    for /l %%i in (1,1,8) do (
        if not defined WPID (
            for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' } | Where-Object { $_.CommandLine -match 'review-relay\.js\s+watch' } | ForEach-Object { $_.ProcessId }"`) do set "WPID=%%P"
        )
        if not defined WPID ping -n 2 127.0.0.1 >nul
    )
    if defined WPID (
        set "G_DETAIL=started pid=!WPID!"
        set "G_OK=true"
        echo [%NOW_ISO%] [OK] start_watcher: started pid=!WPID!
    ) else (
        set "G_DETAIL=start command issued but watcher process not detected within 8s"
        set "G_OK=false"
        echo [%NOW_ISO%] [WARN] start_watcher: !G_DETAIL!
    )
)
call :ledger
exit /b 0

REM ============================================================
REM  start outer-guard.js watch (official entry, detached)
REM  Started only after watcher is confirmed up, so outer-guard's
REM  first cycle sees a live watcher and does not double-spawn.
REM ============================================================
:start_guard
set "G_ACTION=start_guard"
set "GPID="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' } | Where-Object { $_.CommandLine -match 'outer-guard\.js\s+watch' } | ForEach-Object { $_.ProcessId }"`) do set "GPID=%%P"
if defined GPID (
    set "G_DETAIL=already running pid=!GPID!"
    set "G_OK=true"
    echo [%NOW_ISO%] [OK] start_guard: already running pid=!GPID!
) else (
    echo [%NOW_ISO%] [ACTION] start_guard: node src\relay\outer-guard.js watch --config %RELAY_CONFIG%
    pushd "%RELAY_REPO%"
    start "" /b "%NODE_BIN%" src\relay\outer-guard.js watch --config "%RELAY_CONFIG%" >> "%STATE_ROOT%\zhg-guard-%STAMP%.out.log" 2>> "%STATE_ROOT%\zhg-guard-%STAMP%.err.log"
    popd
    set "GPID="
    for /l %%i in (1,1,8) do (
        if not defined GPID (
            for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' } | Where-Object { $_.CommandLine -match 'outer-guard\.js\s+watch' } | ForEach-Object { $_.ProcessId }"`) do set "GPID=%%P"
        )
        if not defined GPID ping -n 2 127.0.0.1 >nul
    )
    if defined GPID (
        set "G_DETAIL=started pid=!GPID!"
        set "G_OK=true"
        echo [%NOW_ISO%] [OK] start_guard: started pid=!GPID!
    ) else (
        set "G_DETAIL=start command issued but guard process not detected within 8s"
        set "G_OK=false"
        echo [%NOW_ISO%] [WARN] start_guard: !G_DETAIL!
    )
)
call :ledger
exit /b 0

REM ============================================================
REM  b) bsk daemon probe -> restart if down
REM     Port is read dynamically from daemon.json ws_port because
REM     the daemon rewrites daemon.json every start; we launch it with
REM     --port 52900 (canonical blackbox port) so it can never drift.
REM ============================================================
:bsk_check
set "G_ACTION=bsk_check"
call :read_bsk_port
netstat -ano | findstr ":%BSK_PORT%" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    set "G_DETAIL=port %BSK_PORT% not listening - starting daemon"
    set "G_OK=false"
    echo [%NOW_ISO%] [ACTION] bsk_check: port %BSK_PORT% DOWN - starting daemon
    pushd "E:\WB\tools\bsk-file-bridge"
    set "BSK_HOME=E:/WB/tools/bsk-file-bridge/bsk-home"
    start "" /b "%BSK_EXE%" daemon start --port 52900 >> "%BSK_HOME%\zhg-bsk-start-%STAMP%.log" 2>&1
    popd
    set "G_ACTION=bsk_start"
    ping -n 3 127.0.0.1 >nul
    call :read_bsk_port
    netstat -ano | findstr ":%BSK_PORT%" | findstr "LISTENING" >nul 2>&1
    if errorlevel 1 (
        set "G_DETAIL=daemon start issued but port %BSK_PORT% still not listening"
        set "G_OK=false"
        echo [%NOW_ISO%] [WARN] bsk_start: !G_DETAIL!
    ) else (
        set "G_DETAIL=daemon start issued, port %BSK_PORT% now listening"
        set "G_OK=true"
        echo [%NOW_ISO%] [OK] bsk_start: port %BSK_PORT% listening
    )
) else (
    set "G_DETAIL=port %BSK_PORT% listening"
    set "G_OK=true"
    echo [%NOW_ISO%] [OK] bsk_check: port %BSK_PORT% listening - bsk OK
)
call :ledger
exit /b 0

REM ---------- resolve bsk ws_port from daemon.json (non-locking read) ----------
:read_bsk_port
set "BSK_PORT="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$f='E:/WB/tools/bsk-file-bridge/bsk-home/daemon.json'; try { $fs=[System.IO.File]::Open($f,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,[System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete); try { $sr=New-Object System.IO.StreamReader($fs); $txt=$sr.ReadToEnd() } finally { $sr.Close(); $fs.Close() }; $j=$txt | ConvertFrom-Json; if ($null -ne $j.ws_port) { $j.ws_port } else { '52900' } } catch { '52900' }"`) do set "BSK_PORT=%%A"
if not defined BSK_PORT set "BSK_PORT=52900"
exit /b 0

REM ============================================================
REM  c) Chrome extension connection check (record + hint only)
REM ============================================================
:chrome_check
set "G_ACTION=chrome_check"
set "LOGDATE="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd'"`) do set "LOGDATE=%%A"
set "CHROME_STATE="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$f='%BSK_HOME%\daemon.log.%LOGDATE%'; if (Test-Path -LiteralPath $f) { $m = Get-Content -LiteralPath $f | Where-Object { $_ -match 'browser connected|browser disconnected' } | Select-Object -Last 1; if ($m) { if ($m -match 'browser connected') { 'CONNECTED' } else { 'DISCONNECTED' } } else { 'NO_EVENT' } } else { 'NO_LOG' }"`) do set "CHROME_STATE=%%A"
if not defined CHROME_STATE set "CHROME_STATE=UNKNOWN"
if "!CHROME_STATE!"=="CONNECTED" (
    set "G_DETAIL=chrome extension connected to bsk daemon"
    set "G_OK=true"
    echo [%NOW_ISO%] [OK] chrome_check: connected
) else (
    set "G_DETAIL=chrome extension NOT connected (state=!CHROME_STATE!) - manual action required, auto-open skipped by design"
    set "G_OK=false"
    echo [%NOW_ISO%] [WARN] chrome_check: !CHROME_STATE! - record + manual hint only, non-blocking
)
call :ledger
exit /b 0

REM ============================================================
REM  d) state integrity check (record + upgrade hint only)
REM ============================================================
:state_check
set "G_ACTION=state_check"
set "DB_STATE="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$f='%STATE_DIR%\control.db'; if (Test-Path -LiteralPath $f) { if ((Get-Item -LiteralPath $f).Length -gt 0) { 'OK' } else { 'EMPTY' } } else { 'MISSING' }"`) do set "DB_STATE=%%A"
if not defined DB_STATE set "DB_STATE=UNKNOWN"
set "HEALTH_STATE="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$f='%STATE_DIR%\runtime-v1\health.json'; try { $j = Get-Content -LiteralPath $f -Raw | ConvertFrom-Json; if ($null -ne $j.ready) { 'OK' } else { 'INVALID' } } catch { 'INVALID' }"`) do set "HEALTH_STATE=%%A"
if not defined HEALTH_STATE set "HEALTH_STATE=UNKNOWN"
set "STATE_BAD=0"
if not "!DB_STATE!"=="OK" set "STATE_BAD=1"
if not "!HEALTH_STATE!"=="OK" set "STATE_BAD=1"
set "G_DETAIL=control.db=!DB_STATE! runtime-v1\health.json=!HEALTH_STATE!"
if "!STATE_BAD!"=="1" (
    set "G_OK=false"
    echo [%NOW_ISO%] [WARN] state_check: !G_DETAIL! - UPGRADE REQUIRED - manual recovery; state-recover not available in production runtime
) else (
    set "G_OK=true"
    echo [%NOW_ISO%] [OK] state_check: !G_DETAIL!
)
call :ledger
exit /b 0

REM ============================================================
REM  D2 single-instance lock: acquire / stale takeover
REM  Lock dir created with mkdir (atomic). lock.json holds
REM  {token, at}. Stale = lock age > LOCK_STALE_SECS OR lock.json
REM  missing/unreadable. Token-based (NOT pid) so release matches
REM  only our own instance; no dependency on process liveness.
REM ============================================================
:acquire_lock
set "LOCK_TOKEN=%STAMP%-%RANDOM%%RANDOM%"
mkdir "%LOCK_DIR%" 2>nul
if not errorlevel 1 (
    set "LOCK_HELD=1"
    set "G_ACTION=guard_lock"
    set "G_DETAIL=lock acquired token=!LOCK_TOKEN!"
    set "G_OK=true"
    powershell -NoProfile -Command "$row = @{ token=$env:LOCK_TOKEN; at=$env:NOW_ISO }; Add-Content -LiteralPath $env:LOCK_INFO -Value ($row | ConvertTo-Json -Compress) -Encoding ascii"
    echo [%NOW_ISO%] [OK] guard_lock: lock acquired token=!LOCK_TOKEN!
    call :ledger
    exit /b 0
)
REM lock dir already exists - read lock.json
set "LOCK_OWNER_TOKEN="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$f='%LOCK_INFO%'; if (Test-Path -LiteralPath $f) { try { $j = Get-Content -LiteralPath $f -Raw | ConvertFrom-Json; $j.token } catch { 'MISSING' } } else { 'MISSING' }"`) do set "LOCK_OWNER_TOKEN=%%A"
if not defined LOCK_OWNER_TOKEN set "LOCK_OWNER_TOKEN=MISSING"
set "LOCK_AGE="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$f='%LOCK_INFO%'; try { $j = Get-Content -LiteralPath $f -Raw | ConvertFrom-Json; [math]::Round(((Get-Date).ToUniversalTime() - [datetime]::Parse($j.at).ToUniversalTime()).TotalSeconds) } catch { '-1' }"`) do set "LOCK_AGE=%%A"
if not defined LOCK_AGE set "LOCK_AGE=-1"
set "LOCK_STALE=0"
if "!LOCK_OWNER_TOKEN!"=="MISSING" set "LOCK_STALE=1"
if "!LOCK_STALE!"=="0" if "!LOCK_AGE!"=="-1" set "LOCK_STALE=1"
if "!LOCK_STALE!"=="0" if !LOCK_AGE! GTR %LOCK_STALE_SECS% set "LOCK_STALE=1"
REM GATE-2#9 (2026-08-31): MISSING lock.json is a claimable state (the lock
REM file itself is the atomic claim in the matching Python implementation).
REM Take over directly with non-recursive deletion only (lock dir holds
REM lock.json alone; rmdir without /s fails closed if anything else lives there).
if "!LOCK_STALE!"=="1" (
    echo [%NOW_ISO%] [ACTION] guard_lock: stale lock takeover owner_token=!LOCK_OWNER_TOKEN! age=!LOCK_AGE!s
    del /q "%LOCK_DIR%\lock.json" 2>nul
    rmdir "%LOCK_DIR%" 2>nul
    mkdir "%LOCK_DIR%" 2>nul
    if errorlevel 1 (
        set "LOCK_HELD=0"
        echo [%NOW_ISO%] [SKIP] guard_lock: SKIP_LOCKED - takeover race lost
        exit /b 0
    )
    set "LOCK_HELD=1"
    set "G_ACTION=guard_lock"
    set "G_DETAIL=stale lock takeover owner_token=!LOCK_OWNER_TOKEN! age=!LOCK_AGE!s new_token=!LOCK_TOKEN!"
    set "G_OK=true"
    powershell -NoProfile -Command "$row = @{ token=$env:LOCK_TOKEN; at=$env:NOW_ISO }; Add-Content -LiteralPath $env:LOCK_INFO -Value ($row | ConvertTo-Json -Compress) -Encoding ascii"
    call :ledger
    exit /b 0
)
set "LOCK_HELD=0"
exit /b 0

REM ---------- release lock only if it is ours (token match) ----------
:release_lock
if not exist "%LOCK_INFO%" exit /b 0
set "LOCK_FILE_TOKEN="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$f='%LOCK_INFO%'; try { $j = Get-Content -LiteralPath $f -Raw | ConvertFrom-Json; $j.token } catch { '-1' }"`) do set "LOCK_FILE_TOKEN=%%A"
if "!LOCK_FILE_TOKEN!"=="!LOCK_TOKEN!" (
    del /f /q "%LOCK_INFO%" 2>nul
    rmdir "%LOCK_DIR%" 2>nul
)
exit /b 0

REM ============================================================
REM  ledger append (one JSON row per action)
REM ============================================================
:ledger
powershell -NoProfile -Command "$row = @{ timestamp=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ'); action=$env:G_ACTION; detail=$env:G_DETAIL; ok=($env:G_OK -eq 'true') }; Add-Content -LiteralPath $env:LEDGER -Value ($row | ConvertTo-Json -Compress) -Encoding ascii"
exit /b 0
