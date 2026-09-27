@echo off
setlocal
cd /d "%~dp0"
docker compose exec -T ubuntu-vnc /opt/venv/bin/python /app/code/note_collector.py --once
set EXIT_CODE=%ERRORLEVEL%
echo.
if not "%EXIT_CODE%"=="0" echo note collector exited with code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
