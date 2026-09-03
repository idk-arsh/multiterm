@echo off
rem One-time setup: installs pywinpty, builds the icon, creates shortcuts.
where python.exe >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0tools\install.py"
) else (
  py "%~dp0tools\install.py"
)
pause
