@echo off
REM Cross-platform Python launcher for AI log hooks (Windows cmd.exe).
REM Prefer the project environment, then try py -3 -> python -> python3.
REM Exits 0 silently if no Python is found - hooks must never block the AI tool.

if exist "%~dp0..\.venv\Scripts\python.exe" (
  "%~dp0..\.venv\Scripts\python.exe" %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python %*
  exit /b %ERRORLEVEL%
)

where python3 >nul 2>nul
if %ERRORLEVEL%==0 (
  python3 %*
  exit /b %ERRORLEVEL%
)

exit /b 0
