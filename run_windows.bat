@echo off
cd /d "%~dp0"
py -3 -m software_audit
if errorlevel 1 pause
