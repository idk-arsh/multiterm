@echo off
rem Build a standalone dist\MultiTerm.exe (needs: pip install pyinstaller)
cd /d "%~dp0"
python tools\build_exe.py
pause
