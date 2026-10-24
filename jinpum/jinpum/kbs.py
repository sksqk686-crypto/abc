"""KBS 'TV쇼 진품명품' 회차 목록과 미리보기 게시판 사진."""
from __future__ import annotations

import datetime as _dt
import json
import re
import urllib.request

PROGRAM_CODE = "T2000-0057"
PREVIEW_BBS = "T2000-0057-04-542468"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

VOD_PAGE = (
    "https://vod.kbs.co.kr/index.html?source=episode&sname=vod&stype=vod"
    "&program_code={program_code}&program_id={program_id}&broadcast_complete_yn=N"
    "&local_station_code=00&section_code=05&section_sub_code=04"
)


def _get(url: str, binary: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://program.kbs.co.kr/"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else json.loads(data)


def episodes() -> list[dict]:
    """다시보기 전체 회차 (최신순)."""
    out, page = [], 1
    while True:
        d = _get(
            "https://static.api.kbs.co.kr/mediafactory/v1/contents?rtype=json"
            f"&sort_option=program_planned_date%7Cdesc&program_code={PROGRAM_CODE}"
            f"&descriptive_video_service_yn=N&page={page}&page_size=30"
        )
        out += d["data"]
        if page >= d["page_count"]:
            break
        page += 1
    eps = []
    for e in out:
        if not str(e.get("program_sequence_number") or "").isdigit():
            continue  # 회차 번호 없는 특집·클립
        subtitle = (e.get("program_subtitle") or "").strip()
        eps.append(
            {
                "episode": int(e["program_sequence_number"]),
                "date": e["program_planned_date"],
                "subtitle": subtitle,
                "titles": split_titles(subtitle),
                "program_id": e["program_id"],
                "vod_page": VOD_PAGE.format(program_code=PROGRAM_CODE, program_id=e["program_id"]),
                "play_urls": [m["play_url"] for m in (e.get("media_list") or []) if m.get("play_url")],
            }
        )
    return eps


def split_titles(subtitle: str) -> list[str]:
    """'그림 - 책거리 / 민속품 - 자개 찬합 / ...' -> ['그림 - 책거리', '민속품 - 자개 찬합', ...]"""
    if " - " not in subtitle and "-" not in subtitle:
        return []
    return [p.strip() for p in subtitle.split("/") if p.strip()]


def preview_photos() -> dict[str, list[str]]:
    """방송일(YYYYMMDD) -> 미리보기 게시글 사진 URL 목록(의뢰품 순서)."""
    result: dict[str, list[str]] = {}
    page = 1
    while True:
        d = _get(
            f"https://cfpbbsapi.kbs.co.kr/board/v1/list?bbs_id={PREVIEW_BBS}&page={page}"
            "&page_size=100&notice_yn=N&contents_yn=N&sort_order=01&kbs_board_auth=0"
        )
        rows = d.get("data") or []
        for p in rows:
            m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", p.get("post_title") or "")
            if not m:
                continue
            created = _dt.datetime.strptime(p["date_created"][:10], "%Y-%m-%d").date()
            month, day = int(m.group(1)), int(m.group(2))
            year = created.year
            # 12월 말에 올린 1월 방송 예고 등 연도 보정
            if month < created.month - 6:
                year += 1
            elif month > created.month + 6:
                year -= 1
            key = f"{year}{month:02d}{day:02d}"
            imgs = json.loads(p.get("post_cont_image") or "[]")
            if imgs and key not in result:
                result[key] = imgs
        if not rows or page * 100 >= d.get("total_count", 0):
            break
        page += 1
    return result


def download(url: str) -> bytes:
    return _get(url, binary=True)
