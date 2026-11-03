@echo off
setlocal
cd /d "%~dp0"
echo [1/3] Creating Python 3.11 virtual environment...
py -3.11 -m venv .venv
if errorlevel 1 (
  echo Could not find Python 3.11. Install it from python.org and retry.
  pause
  exit /b 1
)
echo [2/3] Installing Python packages... (internet required for first setup)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo Package installation failed. Check your internet and Python installation.
  pause
  exit /b 1
)
echo [3/3] Installation complete.
echo Next: install Ollama, run: ollama pull qwen2.5:1.5b
echo Then double-click start_windows.bat
pause
