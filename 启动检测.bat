@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 启动 CS Pilot 寄生式自动检测...
python gui.py
if errorlevel 1 (
  echo.
  echo 运行出错，请把本窗口的报错信息截图保存。
  pause
)
