@echo off
setlocal
cd /d "%~dp0"

where docker >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 Docker。请先安装并启动 Docker Desktop。
  pause
  exit /b 1
)

docker compose up -d --build
if errorlevel 1 (
  echo [错误] 启动失败，请查看上方 Docker 输出。
  pause
  exit /b 1
)

echo.
echo 功能控制中心已启动：http://localhost:8080
if exist "data\first-run.txt" (
  echo 首次使用请打开 data\first-run.txt 获取初始化码。
)
start "" "http://localhost:8080"
endlocal
