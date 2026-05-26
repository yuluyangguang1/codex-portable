@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Codex CLI Portable + CC Switch

REM Clear conflicting env vars from inherited environment
set "OPENAI_API_KEY="
set "OPENAI_BASE_URL="

REM Enable ANSI escape codes
for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"

echo.
echo %ESC%[38;5;45m   ██████╗ ██████╗ ██████╗ ███████╗██╗  ██╗%ESC%[0m
echo %ESC%[38;5;45m  ██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗██╔╝%ESC%[0m
echo %ESC%[38;5;33m  ██║     ██║   ██║██║  ██║█████╗   ╚███╔╝%ESC%[0m
echo %ESC%[38;5;33m  ██║     ██║   ██║██║  ██║██╔══╝   ██╔██╗%ESC%[0m
echo %ESC%[38;5;240m  ╚██████╗╚██████╔╝██████╔╝███████╗██╔╝ ██╗%ESC%[0m
echo %ESC%[38;5;240m   ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝%ESC%[0m
echo.
echo      Codex CLI Portable
echo.

set "SCRIPT_DIR=%~dp0"
set "BIN_DIR=%SCRIPT_DIR%bin\windows-x64"
set "PORTABLE_DATA=%SCRIPT_DIR%data"
set "PORTABLE_CCS=%PORTABLE_DATA%\.cc-switch"
set "PORTABLE_CODEX=%PORTABLE_DATA%\.codex"
set "LIB_DIR=%SCRIPT_DIR%lib"
set "LOCK_FILE=%PORTABLE_DATA%\.lock"
set "LOCK_FILE2=%PORTABLE_CCS%\.bind"
set "RUN_LOCK=%PORTABLE_DATA%\.running"

set "SCRIPT_DIR_PS=%SCRIPT_DIR%"
if "%SCRIPT_DIR_PS:~-1%"=="\" set "SCRIPT_DIR_PS=%SCRIPT_DIR_PS:~0,-1%"

set "SYS_CCS=%USERPROFILE%\.cc-switch"
set "SYS_CODEX=%USERPROFILE%\.codex"

if not exist "%BIN_DIR%\codex.exe" (
  echo [ERROR] Codex CLI not found: %BIN_DIR%\codex.exe
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

:: Single-instance check
if not exist "%PORTABLE_DATA%" mkdir "%PORTABLE_DATA%" >nul 2>&1
if not exist "%RUN_LOCK%" goto :run_lock_done
set "PREV_PID="
for /f "usebackq delims=" %%P in ("%RUN_LOCK%") do if not defined PREV_PID set "PREV_PID=%%P"
if not defined PREV_PID goto :clear_stale_lock
tasklist /fi "PID eq !PREV_PID!" 2>nul | find "!PREV_PID!" >nul
if !errorlevel! EQU 0 (
  echo   [info] Another instance is already running.
  timeout /t 5 >nul 2>&1
  exit /b 1
)
:clear_stale_lock
del /f /q "%RUN_LOCK%" >nul 2>&1
:run_lock_done

:: Drive binding check
set "LOCK_PRESENT=0"
if exist "%LOCK_FILE%" set "LOCK_PRESENT=1"
if exist "%LOCK_FILE2%" set "LOCK_PRESENT=1"
if "!LOCK_PRESENT!"=="0" goto :binding_done
if not exist "%LIB_DIR%\binding.ps1" goto :binding_done

set "ACTIVE_LOCK=%LOCK_FILE%"
if not exist "%LOCK_FILE%" set "ACTIVE_LOCK=%LOCK_FILE2%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%LIB_DIR%\binding.ps1" check "%SCRIPT_DIR_PS%" "!ACTIVE_LOCK!" >nul 2>&1
set "BIND_RESULT=!errorlevel!"
if "!BIND_RESULT!"=="1" goto :binding_failed
if "!BIND_RESULT!"=="3" echo   [warn] Could not verify drive binding (continuing).
goto :binding_done

:binding_failed
echo.
echo   ============================================================
echo   [ERROR] This portable is locked to its original USB drive.
echo   ============================================================
echo.
echo   Original owner can unbind with:
echo     CodexPortable.bat --unlock
echo.
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

:: Migrate existing data
if exist "%SYS_CCS%\cc-switch.db" (
  if not exist "%PORTABLE_CCS%\cc-switch.db" (
    echo   [migrate] Copying existing cc-switch data...
    xcopy /e /i /y /q "%SYS_CCS%" "%PORTABLE_CCS%" >nul 2>&1
  )
)
if exist "%SYS_CODEX%\auth.json" (
  if not exist "%PORTABLE_CODEX%\auth.json" (
    echo   [migrate] Copying existing codex data...
    xcopy /e /i /y /q "%SYS_CODEX%" "%PORTABLE_CODEX%" >nul 2>&1
  )
)

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

:: Write run-lock
echo %~1 > "%RUN_LOCK%"

:: Check config
call :check_config
if "!HAS_CONFIG!"=="1" goto :launch_codex

:: First-run: open CC Switch and wait
echo.
echo =====================================
echo   First Run - Configure API
echo =====================================
echo.
if exist "%BIN_DIR%\cc-switch.exe" (
  echo   Opening CC Switch GUI...
  echo   Add a Codex provider and save.
  echo.
  start "" "%BIN_DIR%\cc-switch.exe"
  set "WE_STARTED_CCS=1"
) else (
  echo   [warn] cc-switch GUI not found. Configure manually:
  echo     %PORTABLE_CODEX%\auth.json    -^> {"OPENAI_API_KEY": "..."}
  echo     %PORTABLE_CODEX%\config.toml  -^> [model_providers.xxx] ...
)

echo   Waiting for configuration...
set "WAIT_COUNT=0"
:wait_config
timeout /t 2 >nul 2>&1
set /a WAIT_COUNT+=1
call :check_config
if "!HAS_CONFIG!"=="1" goto :config_ready
if !WAIT_COUNT! GEQ 150 (
  echo   [!] Timeout waiting for configuration.
  goto :error_cleanup
)
goto :wait_config

:config_ready
echo   [ok] Configuration detected.
timeout /t 1 >nul 2>&1

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
echo.
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
  timeout /t 2 >nul 2>&1
  taskkill /f /im cc-switch.exe /t >nul 2>&1
)
call :remove_link "%SYS_CCS%"
call :remove_link "%SYS_CODEX%"
if exist "%RUN_LOCK%" del /f /q "%RUN_LOCK%" >nul 2>&1
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
rd "%LINK%" 2>nul
if exist "%LINK%" rd /s /q "%LINK%" 2>nul
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
