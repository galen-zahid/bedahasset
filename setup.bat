@echo off
rem Double-click: instalasi sekali jalan. Tambahkan  -Gpu  untuk NVIDIA GPU.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
pause
