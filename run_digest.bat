@echo off
rem Runs the morning digest and adds it to your Gmail inbox.
rem Schedule it with Windows Task Scheduler (see README).
cd /d "%~dp0"
if not exist data mkdir data
.venv\Scripts\python.exe digest.py --deliver >> data\digest.log 2>&1
