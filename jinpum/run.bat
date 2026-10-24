@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
echo ==== 진품명품 감정 카드 만들기 ====
set N=
set /p N=최신 몇 회차를 할까요? (그냥 Enter = 3): 
if "%N%"=="" set N=3
python run.py --latest %N%
echo.
echo 끝났습니다. 결과 폴더를 엽니다.
start "" explorer "%~dp0결과"
pause
