@echo off
rem Builds dist\Whisky\Whisky.exe and installer\Output\Whisky-Setup-<ver>.exe
cd /d "%~dp0"
taskkill /F /IM Whisky.exe >nul 2>&1
.venv\Scripts\pyinstaller --noconfirm --clean whisky.spec || exit /b 1
set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
"%ISCC%" installer\whisky.iss || exit /b 1
echo Done: installer\Output
