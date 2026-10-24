@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==== 진품명품 감정 카드: 설치 ====

set PY=
py -3 -c "import sys" >nul 2>nul && set PY=py -3
if not defined PY (
  python -c "import sys" >nul 2>nul && set PY=python
)
if not defined PY (
  echo [1/4] Python 설치 중... 잠시 기다려 주세요.
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
set PY=
  py -3 -c "import sys" >nul 2>nul && set PY=py -3
  if not defined PY (
    python -c "import sys" >nul 2>nul && set PY=python
  )
  
)
if not defined PY (
  echo.
  echo Python 설치를 마무리하려면 이 창을 닫고 install.bat 을 한 번 더 실행해 주세요.
  echo 그래도 이 메시지가 나오면 https://www.python.org/downloads/ 에서 직접 설치해 주세요.
  echo  - 설치 첫 화면에서 "Add python.exe to PATH" 체크
  pause
  exit /b
)
echo [1/4] Python 확인 완료: %PY%

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [2/4] ffmpeg 설치 중...
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
) else (
  echo [2/4] ffmpeg 확인 완료
)

echo [3/4] 필요한 모듈 설치 중...
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto fail
%PY% -m playwright install chromium

if exist .env goto done
echo.
echo [4/4] Gemini API 키를 붙여넣고 Enter (발급: https://aistudio.google.com/apikey)
set /p GKEY=키: 
>.env echo GEMINI_API_KEY=%GKEY%

:done
echo.
echo 설치 완료! 이 창을 닫고 run.bat 을 더블클릭하세요.
pause
exit /b

:fail
echo.
echo 설치 중 오류가 났습니다. 이 창을 캡처해서 보내 주세요.
pause
