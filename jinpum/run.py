"""TV쇼 진품명품 감정 카드 만들기.

예)  python run.py --latest 3
     python run.py --episodes 1543,1542
     python run.py --latest 3 --no-video --youtube 1542=https://www.youtube.com/watch?v=...

작업/<회차>/ 에 회차별 결과가 쌓이고, 매번 작업/ 전체로 결과/ 폴더의
분류별 한글 파일(.hwpx)을 새로 만든다 (최신 회차가 각 분류의 (1)번).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jinpum import gemini, hwpx, kbs  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TITLE_HINT = {"그림": "서화", "도자기": "자기", "고서": "서책", "글씨": "고문서"}


def _load(path, default=None):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _short_name(title: str) -> str:
    name = title.split(" - ", 1)[-1] if " - " in title else title
    return re.sub(r"['‘’\"]", "", name).strip()


def process_episode(ep: dict, photos: list[str], args) -> None:
    wdir = os.path.join(args.work, str(ep["episode"]))
    _save(os.path.join(wdir, "meta.json"), ep)
    print(f"\n=== {ep['episode']}회 ({ep['date']}) {ep['subtitle']}")
    if not ep["titles"]:
        print("  의뢰품 목록이 없는 회차(결산·스페셜 등) — 건너뜀")
        return

    # 1) 영상 분석 (전체 영상 > 유튜브 클립)
    analyses = []
    video_path = os.path.join(wdir, "video.mp4")
    if not args.no_video:
        cache = os.path.join(wdir, "gemini_video.json")
        res = _load(cache)
        if res is None:
            from jinpum import video

            try:
                print("  KBS 다시보기 영상 받는 중…")
                video.download_episode(ep, video_path, headless=not args.show_browser)
                print("  Gemini 분석 중… (회차당 몇 분 걸립니다)")
                res = gemini.analyze(video_path, ep["titles"])
                _save(cache, res)
            except Exception as e:
                print(f"  ! 영상 처리 실패: {e}")
        if res:
            analyses.append(res)
    for url in args.youtube.get(ep["episode"], []):
        vid = re.sub(r"\W", "", url.split("v=")[-1].split("&")[0])[-11:]
        cache = os.path.join(wdir, f"gemini_youtube_{vid}.json")
        if not os.path.exists(cache):
            print(f"  유튜브 클립 분석 중… {url}")
            try:
                res = gemini.analyze(url, ep["titles"])
                res["_source"] = url
                _save(cache, res)
            except Exception as e:
                print(f"  ! 유튜브 분석 실패: {e}")
    # 예전에 분석해 둔 유튜브 클립도 모두 쓴다
    for f in sorted(os.listdir(wdir)):
        if f.startswith("gemini_youtube") and f.endswith(".json"):
            analyses.append(_load(os.path.join(wdir, f)))

    # 직접 입력(캡처 보고 옮겨 적은 값)이 영상 분석보다 우선
    manual = _load(os.path.join(wdir, "manual.json"), {"items": []})
    by_order: dict[int, dict] = {}
    for res in [manual] + analyses:
        for it in res.get("items", []):
            by_order.setdefault(int(it.get("order") or 0), it)

    # 2) 의뢰품별 카드 데이터
    items = []
    for n, title in enumerate(ep["titles"], 1):
        info = by_order.get(n, {})
        photo_file = os.path.join(wdir, f"photo{n}.jpg")
        if not os.path.exists(photo_file):
            data = None
            if len(photos) == len(ep["titles"]):
                data = kbs.download(photos[n - 1])
            elif info.get("photo_time") and os.path.exists(video_path):
                from jinpum import video

                data = video.grab_frame(video_path, info["photo_time"])
            if data:
                data, _ = hwpx.prepare_image(data)
                with open(photo_file, "wb") as f:
                    f.write(data)
        category = info.get("category") if info.get("category") in gemini.CATEGORIES else ""
        if not category:
            category = TITLE_HINT.get(title.split(" - ")[0].strip(), "")
        if not category:
            prev = _load(os.path.join(wdir, "items.json"), [])
            category = next((p["category"] for p in prev if p["order"] == n and p.get("category")), "")
        if not category:
            photo = open(photo_file, "rb").read() if os.path.exists(photo_file) else None
            category = gemini.classify(photo, title)
        appraisal = info.get("appraisal_points") or info.get("answers") or []
        items.append(
            {
                "episode": ep["episode"],
                "date": ep["date"],
                "order": n,
                "title": title,
                "name": info.get("name") or _short_name(title),
                "number": f"{ep['date']}-{n}({ep['episode']})",
                "category": category,
                "price": info.get("price", ""),
                "features": info.get("features", []),
                "appraisal": appraisal,
                "appraisal_source": "감정 포인트" if info.get("appraisal_points") else ("답변" if appraisal else ""),
                "photo_file": os.path.basename(photo_file) if os.path.exists(photo_file) else "",
                "filled": bool(info),
            }
        )
        print(f"  {n}. {items[-1]['name']} [{category}] {items[-1]['price'] or '(가격 없음)'}")
    _save(os.path.join(wdir, "items.json"), items)


def build_outputs(args) -> None:
    all_items = []
    for d in os.listdir(args.work):
        it = _load(os.path.join(args.work, d, "items.json"))
        if it:
            all_items += it
    all_items.sort(key=lambda x: (-x["episode"], x["order"]))
    os.makedirs(args.out, exist_ok=True)
    for f in os.listdir(args.out):
        if f.endswith(".hwpx"):
            os.remove(os.path.join(args.out, f))
    counters: dict[str, list] = {c: [] for c in gemini.CATEGORIES}
    for it in all_items:
        counters.setdefault(it["category"] or "기타", []).append(it)
    rows = []
    for idx, cat in enumerate(gemini.CATEGORIES, 1):
        group = counters.get(cat) or []
        if not group:
            continue
        cards = []
        for k, it in enumerate(group, 1):
            pf = os.path.join(args.work, str(it["episode"]), it["photo_file"]) if it["photo_file"] else ""
            cards.append({**it, "category": f"{cat}({k})", "photo": open(pf, "rb").read() if pf else None})
            rows.append([f"{cat}({k})", it["number"], it["name"], it["price"], "O" if it["filled"] else "X"])
        path = os.path.join(args.out, f"{idx:02d} {cat}.hwpx")
        hwpx.write_cards(path, cards)
        print(f"  {path}  ({len(cards)}장)")
    with open(os.path.join(args.out, "목록.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["분류", "고유 번호", "명칭", "가격", "영상 분석"])
        w.writerows(rows)


def _count(text: str) -> int:
    """'60', '60회차', ' 60 ' 모두 60으로 받는다."""
    digits = re.sub(r"\D", "", text)
    if not digits:
        raise argparse.ArgumentTypeError(f"회차 수는 숫자로 입력해 주세요: {text!r}")
    return int(digits)


def main() -> None:
    ap = argparse.ArgumentParser(description="TV쇼 진품명품 감정 카드 만들기")
    ap.add_argument("--latest", type=_count, default=3, help="최신 N회차 (기본 3)")
    ap.add_argument("--episodes", help="회차 번호 목록, 예: 1543,1542")
    ap.add_argument("--no-video", action="store_true", help="KBS 다시보기 영상을 받지 않음")
    ap.add_argument("--youtube", action="append", default=[], help="회차=유튜브URL (여러 번 가능)")
    ap.add_argument("--show-browser", action="store_true", help="영상 받을 때 브라우저 창 보이기")
    ap.add_argument("--work", default=os.path.join(HERE, "작업"))
    ap.add_argument("--out", default=os.path.join(HERE, "결과"))
    args = ap.parse_args()

    yt: dict[int, list[str]] = {}
    for s in args.youtube:
        ep, url = s.split("=", 1)
        yt.setdefault(int(ep), []).append(url)
    args.youtube = yt

    print("KBS 회차 목록과 미리보기 사진 목록 받는 중…")
    eps = kbs.episodes()
    if args.episodes:
        want = {int(x) for x in args.episodes.split(",")}
        eps = [e for e in eps if e["episode"] in want]
    else:
        eps = eps[: args.latest]
    photos = kbs.preview_photos()
    for ep in eps:
        process_episode(ep, photos.get(ep["date"], []), args)
    print("\n한글 파일 만드는 중…")
    build_outputs(args)


if __name__ == "__main__":
    main()
