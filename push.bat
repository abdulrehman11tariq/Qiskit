@echo off
rem Publish this folder to GitHub.   Usage:  push.bat "what changed"
cd /d "%~dp0"
rem first use: turn the folder into a git repository on branch main
if not exist .git (
  git init
  git symbolic-ref HEAD refs/heads/main
  git remote add origin https://github.com/abdulrehman11tariq/Qiskit.git
)
rem leftover from an early draft; the current copy lives in results\
if exist data\frontier_exact.png del data\frontier_exact.png
set "MSG=%~1"
if "%MSG%"=="" set "MSG=Quantum Relief: risk-diversified relief stockpiling with QAOA"
git add -A
git commit -m "%MSG%"
git push -u origin main
pause
