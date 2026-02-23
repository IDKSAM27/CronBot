@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-cli.ps1" %*
endlocal
