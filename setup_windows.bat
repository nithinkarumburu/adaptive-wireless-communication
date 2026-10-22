@echo off
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo.
echo Setup complete. Now double-click run_windows.bat
pause
exit /b 0
:fail
echo Setup failed. Check that Python 3 is installed and available as py.
pause
exit /b 1
