@echo off
chcp 65001>nul
cd /d "%~dp0"
python -X utf8 album_tool.py
if errorlevel 9009 py -3 -X utf8 album_tool.py
if errorlevel 1 (
  echo.
  echo Chto-to poshlo ne tak. Proverte, chto ustanovlen Python.
  pause
)
