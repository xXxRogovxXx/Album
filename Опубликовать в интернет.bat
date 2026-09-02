@echo off
chcp 65001>nul
cd /d "%~dp0"
echo Zagruzka izmeneniy na sayt...
echo.
git add -A
git commit -m "Obnovlenie alboma"
git push
echo.
echo Gotovo. Sayt obnovitsya cherez 1-2 minuty.
pause
