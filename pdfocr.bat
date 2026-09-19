@echo off
setlocal

set SCRIPT_DIR=%~dp0

where python >nul 2>nul
if %errorlevel%==0 (
    python "%SCRIPT_DIR%scan_to_docx.py" %*
    exit /b %errorlevel%
)

where py >nul 2>nul
if %errorlevel%==0 (
    py "%SCRIPT_DIR%scan_to_docx.py" %*
    exit /b %errorlevel%
)

echo Python not found on PATH. Install Python 3 and try again.
exit /b 1
