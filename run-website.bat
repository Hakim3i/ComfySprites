@echo off
setlocal EnableExtensions

cd /d "%~dp0"

where node >nul 2>&1
if errorlevel 1 (
  echo Error: Node.js is not installed or not on PATH.
  echo Install Node.js 18+ from https://nodejs.org/
  exit /b 1
)

if not exist "node_modules\" (
  echo === Installing dependencies ===
  call npm install
  if errorlevel 1 exit /b 1
  echo.
)

if not defined PORT set "PORT=3000"

echo === Starting ComfySprites ===
echo Open: http://localhost:%PORT%
echo Press Ctrl+C to stop the server.
echo.

start "" "http://localhost:%PORT%"
call npm start
