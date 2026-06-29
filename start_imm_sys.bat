@echo off
chcp 65001 >nul

REM 设置项目路径
set PROJECT_PATH=D:\haitch\IMM_sys

REM 设置虚拟环境路径
set VENV_PATH=%PROJECT_PATH%\venv

echo 正在启动 IMM 系统...

REM 激活虚拟环境
call "%VENV_PATH%\Scripts\activate.bat"

REM 检查虚拟环境是否激活成功
if errorlevel 1 (
    echo 虚拟环境激活失败，请检查路径是否正确
    pause
    exit /b 1
)

echo 虚拟环境已激活

REM 检查是否有子目录 IMM_sys-main
if exist "%PROJECT_PATH%\IMM_sys-main" (
    REM 如果存在，则切换到子目录
    cd /d "%PROJECT_PATH%\IMM_sys-main"
) else (
    REM 如果不存在，则保持在项目根目录
    cd /d "%PROJECT_PATH%"
)

echo 正在启动 IMM 系统服务...
python run_server.py

pause