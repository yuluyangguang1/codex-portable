@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Codex CLI Portable + CC Switch

REM Clear conflicting env vars from inherited environment
set "OPENAI_API_KEY="
set "OPENAI_BASE_URL="

REM Enable ANSI escape codes
for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"

echo(
echo %ESC%[38;5;45m  ============================================%ESC%[0m
echo %ESC%[38;5;33m     C O D E X   C L I   P O R T A B L E%ESC%[0m
echo %ESC%[38;5;45m  ============================================%ESC%[0m
echo(

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
set "BIN_DIR=%SCRIPT_DIR%bin\windows-x64"
set "PORTABLE_DATA=%SCRIPT_DIR%data"
set "PORTABLE_CCS=%PORTABLE_DATA%\.cc-switch"
set "PORTABLE_CODEX=%PORTABLE_DATA%\.codex"
set "LIB_DIR=%SCRIPT_DIR%lib"
set "LOCK_FILE=%PORTABLE_DATA%\.lock"
set "LOCK_FILE2=%PORTABLE_CCS%\.bind"
set "RUN_LOCK=%PORTABLE_DATA%\.running"

REM Remove trailing backslash from SCRIPT_DIR for PS scripts
set "SCRIPT_DIR_PS=%SCRIPT_DIR:~0,-1%"

set "SYS_CCS=%USERPROFILE%\.cc-switch"
set "SYS_CODEX=%USERPROFILE%\.codex"

if not exist "!BIN_DIR!\codex.exe" (
  echo [ERROR] Codex CLI not found: !BIN_DIR!\codex.exe
  pause
  exit /b 1
)

:: Handle --unlock
if /i "%~1"=="--unlock" goto :do_unlock
goto :after_unlock

:do_unlock
if exist "%LOCK_FILE%" del /f /q "%LOCK_FILE%" >nul 2>&1
if exist "%LOCK_FILE2%" del /f /q "%LOCK_FILE2%" >nul 2>&1
echo   [ok] Unlock complete. Next run will rebind to current location.
pause
exit /b 0

:after_unlock

:: Single-instance check (atomic via mkdir)
if not exist "!PORTABLE_DATA!" mkdir "!PORTABLE_DATA!" >nul 2>&1
if exist "%RUN_LOCK%" (
  set "PREV_PID="
  if exist "%RUN_LOCK%\pid" (
    for /f "usebackq delims=" %%P in ("%RUN_LOCK%\pid") do if not defined PREV_PID set "PREV_PID=%%P"
  )
  if defined PREV_PID (
    tasklist /fi "PID eq !PREV_PID!" 2>nul | find "!PREV_PID!" >nul
    if !errorlevel! EQU 0 (
      echo   [info] Another instance is already running ^(PID !PREV_PID!^).
      timeout /t 5 >nul 2>&1
      exit /b 1
    )
  )
  rd /s /q "%RUN_LOCK%" >nul 2>&1
)
mkdir "%RUN_LOCK%" 2>nul
if !errorlevel! NEQ 0 (
  echo   [info] Another instance is already running ^(concurrent start^).
  timeout /t 5 >nul 2>&1
  exit /b 1
)

:: Drive binding check
set "LOCK_PRESENT=0"
if exist "%LOCK_FILE%" set "LOCK_PRESENT=1"
if exist "%LOCK_FILE2%" set "LOCK_PRESENT=1"
if "!LOCK_PRESENT!"=="0" goto :binding_done
if not exist "%LIB_DIR%\binding.ps1" goto :binding_done

set "BIND_FAILED=0"
set "BIND_WARNED=0"
for %%L in ("%LOCK_FILE%","%LOCK_FILE2%") do (
  if exist "%%~L" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%LIB_DIR%\binding.ps1" check "%SCRIPT_DIR_PS%" "%%~L" >nul 2>&1
    set "EC=!errorlevel!"
    if "!EC!"=="1" set "BIND_FAILED=1"
    if "!EC!"=="3" set "BIND_WARNED=1"
  )
)
if "!BIND_FAILED!"=="1" goto :binding_failed
if "!BIND_WARNED!"=="1" echo   [warn] Could not verify drive binding (continuing).
goto :binding_done

:binding_failed
echo(
echo   [ERROR] This portable is locked to its original USB drive.
echo   Original owner can unbind with: CodexPortable.bat --unlock
echo(
pause
exit /b 1

:binding_done

:: Kill any existing cc-switch
set "WE_STARTED_CCS=0"
tasklist /fi "ImageName eq cc-switch.exe" 2>nul | find /i "cc-switch.exe" >nul
if !errorlevel! EQU 0 (
  echo   [info] Stopping existing CC Switch...
  taskkill /im cc-switch.exe /t >nul 2>&1
  timeout /t 2 >nul 2>&1
  taskkill /f /im cc-switch.exe /t >nul 2>&1
)

:: Setup portable directories
if not exist "%PORTABLE_CCS%" mkdir "%PORTABLE_CCS%"
if not exist "%PORTABLE_CODEX%" mkdir "%PORTABLE_CODEX%"

:: Create junctions
call :ensure_link "%SYS_CCS%" "%PORTABLE_CCS%"
if !errorlevel! NEQ 0 (
  echo   [ERROR] Cannot create link for .cc-switch
  echo   Try enabling Developer Mode in Windows Settings.
  pause
  exit /b 1
)
call :ensure_link "%SYS_CODEX%" "%PORTABLE_CODEX%"
if !errorlevel! NEQ 0 (
  echo   [ERROR] Cannot create link for .codex
  pause
  exit /b 1
)

:: Write run-lock (get cmd.exe PID via PowerShell parent chain)
:: $PID = powershell PID → its parent = cmd.exe (the /c child) → its parent = our bat
for /f "delims=" %%P in ('powershell -NoProfile -Command "$p1=$PID;$p2=(Get-CimInstance Win32_Process -Filter ProcessId=$p1).ParentProcessId;$p3=(Get-CimInstance Win32_Process -Filter ProcessId=$p2).ParentProcessId;Write-Output $p3" 2^>nul') do set "MY_PID=%%P"
if not defined MY_PID set "MY_PID=%RANDOM%%RANDOM%%RANDOM%"
(echo !MY_PID!)>"%RUN_LOCK%\pid"

:: Kill orphaned config server from previous Ctrl+C (ports 17590-17599)
for /L %%Q in (17590,1,17599) do (
  for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr ":%%Q " ^| findstr "LISTEN"') do (
    taskkill /pid %%P /f >nul 2>&1
  )
)

:: Always start config center (foreground popup)
set "CONFIG_SERVER=%LIB_DIR%\config_server.py"
set "WE_STARTED_CCS=0"

REM Find Python: system > bundled
set "PYTHON_CMD="
where python3 >nul 2>&1
if !errorlevel! equ 0 (
  python3 --version >nul 2>&1
  if !errorlevel! equ 0 set "PYTHON_CMD=python3"
)
if not defined PYTHON_CMD (
  where python >nul 2>&1
  if !errorlevel! equ 0 (
    python --version >nul 2>&1
    if !errorlevel! equ 0 set "PYTHON_CMD=python"
  )
)
if not defined PYTHON_CMD (
  if exist "!BIN_DIR!\python\python.exe" set "PYTHON_CMD=!BIN_DIR!\python\python.exe"
)

:: Always start config center (foreground popup)
if defined PYTHON_CMD (
  REM Test if Python actually works
  echo   Testing Python...
  "!PYTHON_CMD!" -c "import sys; print('Python', sys.version)" 2>&1
  if !errorlevel! neq 0 (
    echo   [!] Python test FAILED. Cannot start config center.
    echo   Python: !PYTHON_CMD!
    echo   Press any key to continue without config center...
    pause >nul
    goto :launch_codex
  )
  echo   Starting config center http://127.0.0.1:17590 ...
  echo   Select provider, fill key, test, save. Close browser tab when done.
  echo(
  REM Start config center with error logging
  if not exist "!PORTABLE_DATA!\logs" mkdir "!PORTABLE_DATA!\logs"
  start "" cmd /c "!PYTHON_CMD!" "!CONFIG_SERVER!" ^>"!PORTABLE_DATA!\logs\config-server.log" 2^>^&1
  set "WE_STARTED_CCS=1"
  REM Wait for config center to be ready
  set "_READY=0"
  for /L %%I in (1,1,15) do (
    if "!_READY!"=="0" (
      timeout /t 1 >nul 2>&1
      powershell -NoProfile -Command "try{$r=Invoke-WebRequest -Uri 'http://127.0.0.1:17590/api/heartbeat' -UseBasicParsing -TimeoutSec 1;exit 0}catch{exit 1}" >nul 2>&1
      if !errorlevel! equ 0 set "_READY=1"
    )
  )
  if "!_READY!"=="1" (
    echo   Config center ready at http://127.0.0.1:17590
    start http://127.0.0.1:17590
  ) else (
    echo   [!] Config center failed to start. Check logs:
    echo     !PORTABLE_DATA!\logs\config-server.log
    type "!PORTABLE_DATA!\logs\config-server.log" 2>nul
    echo.
    echo   Press any key to continue without config center...
    pause >nul
  )
) else (
  echo   [!] No Python found. Config center cannot start.
  echo   Continuing with existing config...
  timeout /t 3 >nul 2>&1
)

:launch_codex
:: Create binding lock
if not exist "%LIB_DIR%\binding.ps1" goto :binding_create_done
if exist "%LOCK_FILE%" goto :create_mirror
powershell -NoProfile -ExecutionPolicy Bypass -File "%LIB_DIR%\binding.ps1" create "%SCRIPT_DIR_PS%" "%LOCK_FILE%" >nul 2>&1
if exist "%LOCK_FILE%" echo   [ok] Bound to current drive.
:create_mirror
if exist "%LOCK_FILE2%" goto :binding_create_done
powershell -NoProfile -ExecutionPolicy Bypass -File "%LIB_DIR%\binding.ps1" create "%SCRIPT_DIR_PS%" "%LOCK_FILE2%" >nul 2>&1
:binding_create_done

:: Set CODEX_HOME and launch
echo   Mode: Direct ^| Data: portable folder
echo(
set "CODEX_HOME=%PORTABLE_CODEX%"
"%BIN_DIR%\codex.exe" %*
goto :final_cleanup

:error_cleanup
call :do_cleanup
pause
exit /b 1

:final_cleanup
call :do_cleanup
exit /b 0

:do_cleanup
if "!WE_STARTED_CCS!"=="1" (
  taskkill /im cc-switch.exe /t >nul 2>&1
  taskkill /f /im cc-switch.exe /t >nul 2>&1
)
call :remove_link "%SYS_CCS%"
call :remove_link "%SYS_CODEX%"
if exist "%RUN_LOCK%" rd /s /q "%RUN_LOCK%" >nul 2>&1
exit /b 0

:check_config
set "HAS_CONFIG=0"
if not exist "%PORTABLE_CODEX%\auth.json" exit /b 0
if exist "%LIB_DIR%\check-config.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%LIB_DIR%\check-config.ps1" "%PORTABLE_CODEX%\auth.json" >nul 2>&1
  if !errorlevel! EQU 0 set "HAS_CONFIG=1"
) else (
  for %%F in ("%PORTABLE_CODEX%\auth.json") do if %%~zF GTR 20 set "HAS_CONFIG=1"
)
exit /b 0

:ensure_link
set "LINK=%~1"
set "TARGET=%~2"
if not exist "%LINK%" (
  mklink /J "%LINK%" "%TARGET%" >nul 2>&1
  if !errorlevel! EQU 0 exit /b 0
  mklink /D "%LINK%" "%TARGET%" >nul 2>&1
  exit /b !errorlevel!
)
fsutil reparsepoint query "%LINK%" >nul 2>&1
if !errorlevel! EQU 0 exit /b 0
REM Real directory (pre-existing system install)
if exist "%LINK%\*" (
  set "TARGET_EMPTY=1"
  for /f %%X in ('dir /b /a "%TARGET%" 2^>nul ^| findstr /r ".*"') do set "TARGET_EMPTY=0"
  if "!TARGET_EMPTY!"=="1" (
    echo   [migrate] Moving existing %LINK% into portable folder...
    xcopy /e /i /y /q "%LINK%" "%TARGET%" >nul 2>&1
    if !errorlevel! EQU 0 (
      rd /s /q "%LINK%" 2>nul
    ) else (
      echo   [ERROR] xcopy failed, keeping %LINK% intact
      exit /b 1
    )
  ) else (
    for /f "delims=" %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMddHHmmss" 2^>nul') do set "TS=%%T"
    if not defined TS set "TS=%RANDOM%%RANDOM%"
    echo   [warn] Portable target not empty, backing up system dir...
    ren "%LINK%" "%~n1.before-portable.!TS!" >nul 2>&1
  )
  if exist "%LINK%" ren "%LINK%" "%~n1.bak.%RANDOM%" >nul 2>&1
)
if exist "%LINK%" rd "%LINK%" 2>nul
mklink /J "%LINK%" "%TARGET%" >nul 2>&1
if !errorlevel! EQU 0 exit /b 0
mklink /D "%LINK%" "%TARGET%" >nul 2>&1
exit /b !errorlevel!

:remove_link
set "LINK=%~1"
if not exist "%LINK%" exit /b 0
fsutil reparsepoint query "%LINK%" >nul 2>&1
if !errorlevel! EQU 0 rd "%LINK%" >nul 2>&1
exit /b 0
