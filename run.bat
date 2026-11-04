@echo off
rem Double-click: proses semua gambar di folder "in" -> hasil di folder "out".
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
pause
