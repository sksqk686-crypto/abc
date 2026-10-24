# TV쇼 진품명품 감정 카드 만들기

KBS 'TV쇼 진품명품' 회차를 Gemini가 보고, 의뢰품마다 감정 카드(한글 .hwpx)를 분류별 새 파일로 만듭니다.

| 칸 | 어디서 가져오나 |
|---|---|
| 명칭 · 가격 · 유물 특징 | 회차 마지막의 감정 결과 카드 (추정 감정가 아래 `·` 문장) |
| 감정 내용 | 화면의 **감정 포인트** 자막 → 없으면 **답변** 자막 |
| 고유 번호 | `방송일-순서(회차)`, 예: `20261011-3(1542)` |
| 분류 | 자기·도기·토기·서화·서책·고문서·목제·금속·직물섬유·복합·기타 중 하나, 최신 회차가 (1)번 |
| 사진 | KBS 미리보기 게시판 사진 (없으면 영상 화면 캡처) |

결과는 `결과/` 폴더에 `01 자기.hwpx`, `04 서화.hwpx` … 처럼 분류별로 생기고, `결과/목록.csv`에 전체 목록이 정리됩니다.
실행할 때마다 `작업/`에 쌓인 회차 전체로 `결과/`를 새로 만듭니다.

## 왜 내 PC에서 돌려야 하나

KBS 다시보기는 **한국 IP에서만 재생**됩니다. 해외 서버(클라우드)에서는 전체 영상을 볼 수 없어서,
유튜브 클립이 있는 의뢰품(보통 회차당 1점)만 채울 수 있습니다. 한국에 있는 PC에서 실행하면 회차 전체를 분석합니다.

## 처음 한 번만 설치

1. **Python 3.10 이상**: https://www.python.org/downloads/ (설치할 때 "Add python.exe to PATH" 체크)
2. **ffmpeg**: Windows는 명령 프롬프트에서 `winget install Gyan.FFmpeg`, Mac은 `brew install ffmpeg`
3. 이 폴더에서:
   ```
   pip install -r requirements.txt
   python -m playwright install chromium
   ```
4. Gemini 키 넣기: 이 폴더에 `.env` 파일을 만들고 한 줄 적기
   ```
   GEMINI_API_KEY=여기에_키
   ```
   (키 발급: https://aistudio.google.com/apikey)

## 실행

```
python run.py --latest 3          # 최신 3회차
python run.py --latest 10         # 최신 10회차
python run.py --episodes 1543,1540
```

- 회차당 영상 받기(약 200MB) + Gemini 분석에 몇 분씩 걸립니다.
- 한 번 분석한 회차는 `작업/<회차>/`에 저장되어 다시 돌려도 Gemini를 또 부르지 않습니다.
  다시 분석하려면 그 회차의 `gemini_video.json`을 지우세요.
- 영상 받기가 실패하면 `--show-browser`를 붙여 브라우저 창을 보면서 확인할 수 있습니다.
- 결산·스페셜 회차는 의뢰품이 없어 자동으로 건너뜁니다.

## 클라우드에서처럼 유튜브 클립만으로 돌리기

```
python run.py --latest 3 --no-video --youtube 1542=https://www.youtube.com/watch?v=lsIq2183IbQ
```

## 파일 구성

- `run.py`: 전체 실행
- `jinpum/kbs.py`: KBS 회차 목록, 미리보기 게시판 사진
- `jinpum/video.py`: KBS 다시보기 영상 받기 (Playwright + ffmpeg, 한국 IP 필요)
- `jinpum/gemini.py`: Gemini 영상 분석 (프롬프트는 이 파일의 `PROMPT`)
- `jinpum/hwpx.py`: 감정 카드 한글 파일 생성
- `base/`: 보내주신 양식에서 가져온 서식(글꼴·칸 크기·테두리)
