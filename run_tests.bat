@echo off
rem Full test suite: VT parser, logging, live shells, and the GUI.
cd /d "%~dp0"
python tests\test_vt.py
python tests\test_logging.py
python tests\test_live.py
python tests\test_gui.py
pause
