@echo off
rem Launch MultiTerm without a console window.
setlocal
if exist "%~dp0dist\MultiTerm.exe" (
  start "" "%~dp0dist\MultiTerm.exe"
  goto :eof
)
where pythonw.exe >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw.exe "%~dp0main.py"
  goto :eof
)
where py.exe >nul 2>nul
if %errorlevel%==0 (
  start "" py.exe -w "%~dp0main.py"
  goto :eof
)
echo Python 3.9+ was not found on PATH. Install it from python.org, then run install.bat.
pause
