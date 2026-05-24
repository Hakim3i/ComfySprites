@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "MSG=%*"
if not defined MSG (
  set /p MSG=Commit message: 
)

if not defined MSG (
  echo Error: commit message is required.
  exit /b 1
)

echo.
echo === Git status ===
git status -sb
if errorlevel 1 exit /b 1

echo.
echo === Staging changes ===
git add -A
if errorlevel 1 exit /b 1

echo.
echo === Committing ===
git commit -m "%MSG%"
if errorlevel 1 (
  echo Nothing to commit, or commit failed.
  exit /b 1
)

echo.
echo === Pushing ===
for /f "delims=" %%B in ('git branch --show-current') do set "BRANCH=%%B"
git push -u origin "%BRANCH%"
if errorlevel 1 exit /b 1

echo.
echo Done. Pushed "%BRANCH%" to origin.
exit /b 0
