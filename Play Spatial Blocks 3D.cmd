@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch3d.ps1"
if errorlevel 1 pause
