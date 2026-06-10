@echo off
REM Same as run.bat but restarts when webapp/*.py changes (Python development).
set COOMFY_RELOAD=1
call "%~dp0run.bat"
