# 진품명품 감정 카드 — Claude Code 작업 메모

- 실행: `python run.py --latest N`. 상세는 README.md.
- KBS 다시보기(vod.kbs.co.kr)는 한국 IP에서만 재생된다. `jinpum/video.py`의 `capture_stream`은
  해외 클라우드에서는 검증하지 못했다. 한국 PC에서 처음 돌릴 때 실패하면 `--show-browser`로 플레이어를 보고,
  본편 m3u8 요청(`mediafactory.play.kbs.co.kr/.../video/...m3u8`)과 서명 방식(쿠키 또는 쿼리스트링)을 확인해 고칠 것.
- 감정 카드 규칙(사용자 지정): 유물 특징 = 결과 카드의 `·` 문장, 감정 내용 = '감정 포인트' 자막 우선, 없으면 '답변' 자막.
  분류 번호는 최신 회차가 (1). 기존 양식 파일에 덧붙이지 말고 항상 새 파일로 만든다.
- hwpx 서식은 `base/`(사용자 양식에서 추출)를 그대로 쓰고 본문만 `jinpum/hwpx.py`가 만든다.
