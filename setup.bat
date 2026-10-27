@echo off
setlocal
rem One-time install. Downloads everything Stem Splitter needs (its own private Python,
rem PyTorch, Demucs) into one folder. Nothing is installed system-wide; to uninstall,
rem delete %USERPROFILE%\.stemsplitter

if "%STEMSPLITTER_HOME%"=="" set "STEMSPLITTER_HOME=%USERPROFILE%\.stemsplitter"
set "UV=%STEMSPLITTER_HOME%\uv\uv.exe"
set "VENV=%STEMSPLITTER_HOME%\venv"
set "UV_PYTHON_INSTALL_DIR=%STEMSPLITTER_HOME%\python"
set "UV_NO_CACHE=1"

echo.
echo  Stem Splitter setup
echo  -------------------
echo  This downloads about 3 GB with an NVIDIA graphics card, about 1 GB without.
echo  It only happens once.
echo.

if exist "%UV%" goto :have_uv
echo [1/4] Downloading the installer tool...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue';" ^
  "$zip = Join-Path $env:TEMP 'stemsplitter-uv.zip';" ^
  "Invoke-WebRequest 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' -OutFile $zip;" ^
  "Expand-Archive $zip -DestinationPath '%STEMSPLITTER_HOME%\uv' -Force; Remove-Item $zip"
if errorlevel 1 goto :fail
:have_uv

echo [2/4] Setting up Python...
"%UV%" venv "%VENV%" --python 3.12 --python-preference only-managed --clear --quiet
if errorlevel 1 goto :fail

rem NVIDIA card present -> GPU build of PyTorch, otherwise the smaller CPU build.
set "TORCH_INDEX=https://download.pytorch.org/whl/cpu"
set "TORCH_KIND=CPU"
where nvidia-smi >nul 2>&1
if errorlevel 1 goto :install_torch
set "TORCH_INDEX=https://download.pytorch.org/whl/cu128"
set "TORCH_KIND=NVIDIA GPU"
:install_torch

echo [3/4] Downloading PyTorch for %TORCH_KIND% (the big one, please wait)...
"%UV%" pip install --python "%VENV%\Scripts\python.exe" torch==2.7.1 torchaudio==2.7.1 --index-url %TORCH_INDEX%
if errorlevel 1 goto :fail

echo [4/4] Downloading Demucs and the app libraries...
"%UV%" pip install --python "%VENV%\Scripts\python.exe" -r "%~dp0requirements.txt"
if errorlevel 1 goto :fail

echo.
echo Setup complete.
if /i not "%~1"=="--from-launcher" pause
exit /b 0

:fail
echo.
echo Setup failed, see the error above. Check your internet connection and try again.
rem Remove the half-built environment so the next start retries setup.
if exist "%VENV%" rmdir /s /q "%VENV%"
pause
exit /b 1
