@echo off
rem Agent Meeting Bridge - start the meeting (Windows)
rem Double-click this file in your PRIVATE mailbox copy (not the public template).
cd /d "%~dp0"
where python >nul 2>nul || (echo Python is not installed or not on PATH. & pause & exit /b 1)
if not exist "bridge\bridge.config.json" (
  echo First run: copying the example config. Edit bridge\bridge.config.json
  echo and set project_dir to your project folder, then run this file again.
  copy "bridge\bridge.config.example.json" "bridge\bridge.config.json" >nul
  pause
  exit /b 0
)
python "bridge\bridge.py"
pause
