@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-BigDataLab.ps1" -RunTrainingProject -RunProjectWithAirflow -UseElastic
pause
