@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==== 진품명품 감정 카드: 설치 ====

where python >nul 2>nul
if errorlevel 1 (
  echo [1/4] Python 설치 중...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo Python 설치가 끝났습니다. 이 창을 닫고 install.bat 을 한 번 더 실행해 주세요.
  pause
  exit /b
)
echo [1/4] Python 확인 완료

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [2/4] ffmpeg 설치 중...
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
) else (
  echo [2/4] ffmpeg 확인 완료
)

echo [3/4] 필요한 모듈 설치 중...
python -m pip install -r requirements.txt
python -m playwright install chromium

if exist .env goto done
echo.
echo [4/4] Gemini API 키를 붙여넣고 Enter (발급: https://aistudio.google.com/apikey)
set /p GKEY=키: 
>.env echo GEMINI_API_KEY=%GKEY%

:done
echo.
echo 설치 완료! 이제 run.bat 을 더블클릭하세요.
echo (ffmpeg를 방금 설치했다면 이 창을 닫은 뒤 run.bat 을 실행하세요)
pause
