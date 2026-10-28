@echo off
title Isolate
if not "%ISOLATE_HOME%"=="" goto :home_set
set "ISOLATE_HOME=%USERPROFILE%\.isolate"
rem Installs from before the rename (v1.0.0, "Stem Splitter") live in .stemsplitter; reuse them.
if exist "%ISOLATE_HOME%\venv\Scripts\python.exe" goto :home_set
if exist "%USERPROFILE%\.stemsplitter\venv\Scripts\python.exe" set "ISOLATE_HOME=%USERPROFILE%\.stemsplitter"
:home_set
set "VENV=%ISOLATE_HOME%\venv"

if exist "%VENV%\Scripts\python.exe" goto :start
call "%~dp0setup.bat" --from-launcher
if errorlevel 1 exit /b 1

:start
cd /d "%~dp0"
echo Starting Isolate... it will open in your browser. Close this window to quit.
"%VENV%\Scripts\python.exe" app.py
pause
