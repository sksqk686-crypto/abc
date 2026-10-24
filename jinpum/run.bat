@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
echo ==== 진품명품 감정 카드 만들기 ====
set PY=
py -3 -c "import sys" >nul 2>nul && set PY=py -3
if not defined PY (
  python -c "import sys" >nul 2>nul && set PY=python
)
if not defined PY (
  echo Python이 설치되어 있지 않습니다. install.bat 을 먼저 실행해 주세요.
  pause
  exit /b
)
set N=
set /p N=최신 몇 회차를 할까요? 숫자만 입력 (그냥 Enter = 3): 
if "%N%"=="" set N=3
%PY% run.py --latest "%N%"
if errorlevel 1 (
  echo.
  echo 오류가 났습니다. 이 창을 캡처해서 보내 주세요.
  pause
  exit /b
)
echo.
echo 끝났습니다. 결과 폴더를 엽니다.
start "" explorer "%~dp0결과"
pause
