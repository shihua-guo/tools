@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%" >nul

set "CONFIG_PATH=%~1"
if not defined CONFIG_PATH set "CONFIG_PATH=%SCRIPT_DIR%issue-bridge.json"

if not exist "%CONFIG_PATH%" (
    echo Config file not found: "%CONFIG_PATH%"
    echo Copy issue-bridge.example.json to issue-bridge.json and update it before starting.
    goto :error
)

set "PYTHONPATH=%SCRIPT_DIR%src;%PYTHONPATH%"
set "PYTHON_EXE="
set "PYTHON_ARGS="

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"
)

if not defined PYTHON_EXE (
    where py >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_ARGS=-3"
    )
)

if not defined PYTHON_EXE (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
    echo Python 3 was not found in PATH.
    goto :error
)

echo Starting GitHub Issue Bridge...
echo Config: "%CONFIG_PATH%"
call "%PYTHON_EXE%" %PYTHON_ARGS% -m issue_bridge.main --config "%CONFIG_PATH%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo GitHub Issue Bridge exited with code %EXIT_CODE%.
    goto :error_with_code
)

popd >nul
endlocal
exit /b 0

:error_with_code
popd >nul
pause
endlocal & exit /b %EXIT_CODE%

:error
popd >nul
pause
endlocal & exit /b 1
