@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
  echo [FAIL] .env absent. Lancez d'abord INSTALL_CORE.cmd ou INSTALL_RESET_FULL.cmd.
  pause
  exit /b 1
)

docker compose up -d spark-jupyter
if errorlevel 1 (
  echo [FAIL] Impossible de demarrer spark-jupyter.
  pause
  exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%A in (".env") do if "%%A"=="JUPYTER_TOKEN" set "JUPYTER_TOKEN_VALUE=%%B"
for /f "usebackq tokens=1,* delims==" %%A in (".env") do if "%%A"=="JUPYTER_PORT" set "JUPYTER_PORT_VALUE=%%B"
if not defined JUPYTER_TOKEN_VALUE (
  echo [FAIL] JUPYTER_TOKEN absent de .env. Relancez l'installation.
  pause
  exit /b 1
)
if not defined JUPYTER_PORT_VALUE set "JUPYTER_PORT_VALUE=8888"

start "" "http://127.0.0.1:%JUPYTER_PORT_VALUE%/lab?token=%JUPYTER_TOKEN_VALUE%"
echo [OK] JupyterLab: http://127.0.0.1:%JUPYTER_PORT_VALUE%/lab
endlocal
