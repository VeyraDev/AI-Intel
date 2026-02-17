@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动本地服务（另开窗口）...
start "AI-Intel 本地服务" cmd /k "python -m http.server 8000"
timeout /t 2 /nobreak >nul
echo 正在打开浏览器...
start "" "http://localhost:8000/frontend/index.html"
echo 已打开页面。关闭「AI-Intel 本地服务」窗口即可停止服务。
timeout /t 3
