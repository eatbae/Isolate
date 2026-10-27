@echo off
title Stem Splitter
if "%STEMSPLITTER_HOME%"=="" set "STEMSPLITTER_HOME=%USERPROFILE%\.stemsplitter"
set "VENV=%STEMSPLITTER_HOME%\venv"

if exist "%VENV%\Scripts\python.exe" goto :start
call "%~dp0setup.bat" --from-launcher
if errorlevel 1 exit /b 1

:start
cd /d "%~dp0"
echo Starting Stem Splitter... it will open in your browser. Close this window to quit.
"%VENV%\Scripts\python.exe" app.py
pause
