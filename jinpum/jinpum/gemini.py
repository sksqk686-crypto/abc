"""Gemini로 회차 영상을 보고 의뢰품별 감정 결과를 뽑는다."""
from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.error
import urllib.request

API = "https://generativelanguage.googleapis.com"
MODELS = [m for m in os.environ.get("JINPUM_GEMINI_MODEL", "gemini-3.7-flash,gemini-3.8-flash,gemini-3.5-flash").split(",") if m]

CATEGORIES = ["자기", "도기", "토기", "서화", "서책", "고문서", "목제", "금속", "직물섬유", "복합", "기타"]

PROMPT = """이 영상은 KBS 'TV쇼 진품명품' 한 회차(또는 그 일부)입니다.
이 회차의 의뢰품(방송 순서): {titles}

각 의뢰품에 대해 화면 자막을 그대로 옮겨 적어 주세요. 말을 지어내거나 요약해서 바꾸지 마세요.

- name: 마지막 감정 결과 카드(빨간 배경, 의뢰품 사진 아래 명칭과 '추정 감정가'가 나오는 화면)에 적힌 명칭.
  카드가 없으면 화면 자막의 명칭.
- price: 결과 카드의 '추정 감정가' 금액 그대로 (예: "300만 원", "1억 2천만 원"). 감정가가 나오지 않으면 "".
- features: 결과 카드에서 감정가 아래에 '·'로 나열된 문장들 (보통 2~3개). 없으면 [].
- appraisal_points: 감정위원 설명 중 화면 왼쪽 아래에 '감정 포인트'라는 제목과 함께 나오는 자막 문장 전부, 나온 순서대로.
- answers: '답변'이라는 제목과 함께 나오는 자막 문장 전부, 나온 순서대로.
- category: 의뢰품 재질/종류를 다음 중 하나로: {categories}
  (자기=청자·백자·분청사기 등 자기, 도기=도기·옹기, 토기=토기, 서화=그림·병풍·족자 그림,
   서책=고서·책·일기·만화책 등 책자, 고문서=글씨·간찰·교지·문서·신문, 목제=나무 가구·목공예,
   금속=금속 공예, 직물섬유=옷·자수·댕기 등 직물, 복합=여러 재질이 섞인 것이나 여러 점 묶음,
   기타=음반·사진 등 그 밖)
- result_card_time: 결과 카드가 처음 나오는 시각 "MM:SS" (1시간 넘으면 "H:MM:SS").
- photo_time: 의뢰품 전체가 자막 없이 화면에 크게 잘 보이는 시각.

order는 위 의뢰품 목록에서의 번호(1부터)입니다. 영상에 감정 장면이 나오지 않는 의뢰품은 넣지 마세요.
결산·스페셜처럼 새 의뢰품 감정이 없으면 items를 빈 배열로 두세요.
JSON만 출력하세요:
{{"items": [{{"order": 1, "name": "", "price": "", "features": [], "appraisal_points": [], "answers": [],
  "category": "", "result_card_time": "", "photo_time": ""}}]}}"""


def _key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        for path in (os.path.expanduser("~/.config/watch/.env"), ".env"):
            if os.path.exists(path):
                for line in open(path, encoding="utf-8"):
                    if line.startswith("GEMINI_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"')
                if key:
                    break
    if not key:
        raise SystemExit("GEMINI_API_KEY가 없습니다. .env 파일에 GEMINI_API_KEY=... 를 넣어 주세요.")
    return key


def _req(url: str, data: bytes | None = None, headers: dict | None = None, method: str | None = None):
    h = {"x-goog-api-key": _key(), **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return r.headers, r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini HTTP {e.code}: {e.read()[:500]!r}") from None


def upload(path: str) -> dict:
    size = os.path.getsize(path)
    mime = mimetypes.guess_type(path)[0] or "video/mp4"
    hdrs, _ = _req(
        f"{API}/upload/v1beta/files",
        data=json.dumps({"file": {"display_name": os.path.basename(path)}}).encode(),
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": mime,
            "Content-Type": "application/json",
        },
    )
    upload_url = hdrs["X-Goog-Upload-URL"]
    with open(path, "rb") as f:
        _, body = _req(
            upload_url,
            data=f.read(),
            headers={"X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"},
        )
    info = json.loads(body)["file"]
    while info.get("state") == "PROCESSING":
        time.sleep(10)
        _, body = _req(f"{API}/v1beta/{info['name']}")
        info = json.loads(body)
    if info.get("state") != "ACTIVE":
        raise RuntimeError(f"Gemini 파일 처리 실패: {info}")
    return info


def delete(name: str) -> None:
    try:
        _req(f"{API}/v1beta/{name}", method="DELETE")
    except Exception:
        pass


def analyze(source: str, titles: list[str]) -> dict:
    """source: 로컬 영상 경로 또는 YouTube URL."""
    uploaded = None
    if source.startswith("http"):
        part = {"file_data": {"file_uri": source}}
    else:
        uploaded = upload(source)
        part = {"file_data": {"file_uri": uploaded["uri"], "mime_type": uploaded["mimeType"]}}
    prompt = PROMPT.format(titles=" / ".join(titles) or "(목록 없음)", categories=", ".join(CATEGORIES))
    body = {
        "contents": [{"role": "user", "parts": [part, {"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }
    try:
        attempts = [(m, r) for r in range(3) for m in MODELS]
        for i, (model, _round) in enumerate(attempts):
            try:
                _, raw = _req(
                    f"{API}/v1beta/models/{model}:generateContent",
                    data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"},
                )
                break
            except RuntimeError as e:
                if i == len(attempts) - 1 or not any(c in str(e) for c in ("404", "429", "500", "503")):
                    raise
                if model == MODELS[-1]:
                    time.sleep(60 * (_round + 1))
        resp = json.loads(raw)
        text = "".join(p.get("text", "") for p in resp["candidates"][0]["content"]["parts"])
        result = json.loads(text[text.find("{") : text.rfind("}") + 1])
        result["_usage"] = resp.get("usageMetadata", {})
        result["_model"] = model
        return result
    finally:
        if uploaded:
            delete(uploaded["name"])


CLASSIFY_PROMPT = """KBS 'TV쇼 진품명품' 의뢰품 사진입니다. 방송 소개: "{title}"
이 의뢰품의 재질/종류를 다음 중 하나로만 답하세요: {categories}
(자기=청자·백자·분청사기, 도기=도기·옹기, 토기=토기, 서화=그림·병풍·족자 그림, 서책=고서·책자,
 고문서=글씨·간찰·교지·문서·신문, 목제=나무 가구·목공예, 금속=금속 공예, 직물섬유=옷·자수·댕기,
 복합=여러 재질이 섞였거나 여러 점 묶음, 기타=그 밖)
JSON만: {{"category": ""}}"""


def classify(photo: bytes | None, title: str) -> str:
    """영상 분석이 없는 의뢰품의 분류를 사진+제목으로 정한다."""
    import base64

    parts = []
    if photo:
        mime = "image/png" if photo[:4] == b"\x89PNG" else "image/jpeg"
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(photo).decode()}})
    parts.append({"text": CLASSIFY_PROMPT.format(title=title, categories=", ".join(CATEGORIES))})
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    for model in MODELS:
        try:
            _, raw = _req(
                f"{API}/v1beta/models/{model}:generateContent",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            resp = json.loads(raw)
            text = "".join(p.get("text", "") for p in resp["candidates"][0]["content"]["parts"])
            cat = json.loads(text[text.find("{") : text.rfind("}") + 1]).get("category", "")
            if cat in CATEGORIES:
                return cat
        except Exception:
            continue
    return "기타"
