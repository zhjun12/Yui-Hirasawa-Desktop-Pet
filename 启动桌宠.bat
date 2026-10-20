@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "dist\YuiCompanion\YuiCompanion.exe" (
    start "" "dist\YuiCompanion\YuiCompanion.exe"
    exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "app.py"
    exit /b
)
echo 请先解压完整的测试版压缩包，然后运行其中的 YuiCompanion.exe。
pause
