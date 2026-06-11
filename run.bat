@echo off
REM Launch the ComfySprites dataset editor (development).
REM Binds 0.0.0.0 so ComfyUI on another machine can reach /api/build.
REM Override: set COOMFY_HOST=127.0.0.1 to lock to localhost only.
REM
REM Auto-reload is OFF by default (stable on Windows while editing the dataset).
REM   set COOMFY_RELOAD=1   before run.bat  — or use run-dev.bat
REM On Windows, --reload spawns a child process; if a .py file changes (or you
REM press Ctrl+C mid-restart) you can get a harmless multiprocessing traceback
REM and the server may stop — that is not caused by DELETE /api/characters.

if not defined COOMFY_HOST set COOMFY_HOST=0.0.0.0
if not defined COOMFY_PORT set COOMFY_PORT=8765

set "UVICORN_RELOAD="
if "%COOMFY_RELOAD%"=="1" set "UVICORN_RELOAD=--reload --reload-dir webapp --reload-dir webapp/comfyui/workflows --reload-delay 0.4"

pushd "%~dp0"
echo ComfySprites webapp: http://127.0.0.1:%COOMFY_PORT%
if "%COOMFY_RELOAD%"=="1" (
  echo Auto-reload: ON ^(webapp/*.py + workflows/*.json^)
) else (
  echo Auto-reload: OFF ^(set COOMFY_RELOAD=1 or run run-dev.bat for Python dev^)
)
echo Remote machines — use one of these URLs (not 127.0.0.1^):
powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.InterfaceAlias -match 'Wi-Fi|Ethernet|Tailscale' } | ForEach-Object { Write-Host ('  http://{0}:' + $env:COOMFY_PORT + '  ({1})' -f $_.IPAddress, $_.InterfaceAlias) }"
start "" http://127.0.0.1:%COOMFY_PORT%
python -m uvicorn webapp.main:app --host %COOMFY_HOST% --port %COOMFY_PORT% %UVICORN_RELOAD%
popd
