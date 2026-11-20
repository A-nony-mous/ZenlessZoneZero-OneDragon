@echo off
chcp 65001 2>&1

cd %~dp0

rem Build exe
uv run pyinstaller --noconfirm --clean "OneDragon-Portable.spec"

echo Done
pause
