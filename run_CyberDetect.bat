@echo off
cd /d "%~dp0"
if not exist "%~dp0logs" mkdir "%~dp0logs"
"%~dp0venv\Scripts\python.exe" "%~dp0main.py" >> "%~dp0logs\runtime.log" 2>&1
