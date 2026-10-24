"""KBS 다시보기 영상 받기 (한국 IP에서만 동작).

KBS 플레이어 페이지를 Playwright 브라우저로 열어 재생 권한(쿠키/서명 URL)을
받은 뒤, ffmpeg로 가장 낮은 화질(약 500kbps)의 HLS를 mp4로 저장한다.
"""
from __future__ import annotations

import os
import re
import subprocess
import urllib.parse
import urllib.request

from .kbs import UA


def _lowest_variant(m3u8_url: str, headers: dict) -> str:
    req = urllib.request.Request(m3u8_url, headers=headers)
    text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    if "#EXT-X-STREAM-INF" not in text:
        return m3u8_url
    best = None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            bw = int((re.search(r"BANDWIDTH=(\d+)", line) or [0, 0])[1])
            uri = lines[i + 1].strip()
            if best is None or bw < best[0]:
                best = (bw, uri)
    url = urllib.parse.urljoin(m3u8_url, best[1])
    # 서명이 쿼리스트링에 붙어 있으면 하위 재생목록에도 그대로 붙인다
    q = urllib.parse.urlparse(m3u8_url).query
    if q and "?" not in best[1]:
        url += "?" + q
    return url


def capture_stream(vod_page: str, hint: str = "", headless: bool = True) -> tuple[str, dict]:
    """플레이어를 열고 본편 m3u8 URL과 요청 헤더(쿠키 포함)를 돌려준다."""
    from playwright.sync_api import sync_playwright

    found: dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(user_agent=UA, locale="ko-KR")
        page = ctx.new_page()

        def on_request(req):
            u = req.url
            if ".m3u8" in u and "mediafactory" in u and (not hint or hint in u):
                found.setdefault("url", u)
                found.setdefault("headers", req.headers)

        page.on("request", on_request)
        page.goto(vod_page, wait_until="domcontentloaded", timeout=90_000)
        for _ in range(90):  # 최대 약 3분 (광고 포함)
            if "url" in found:
                break
            for sel in (".jw-icon-display", ".jw-display-icon-container", "video"):
                try:
                    page.click(sel, timeout=500)
                    break
                except Exception:
                    pass
            page.wait_for_timeout(2000)
        cookies = ctx.cookies()
        text = page.inner_text("body")[:2000]
        browser.close()
    if "url" not in found:
        if "Korea only" in text or "국내" in text:
            raise RuntimeError("KBS가 해외 접속으로 판단해 재생을 막았습니다 (한국 IP 필요).")
        raise RuntimeError("재생 주소를 찾지 못했습니다. --show-browser 로 직접 확인해 주세요.")
    headers = {k: v for k, v in found["headers"].items() if k.lower() in ("referer", "origin", "user-agent")}
    headers.setdefault("User-Agent", UA)
    headers.setdefault("Referer", "https://vod.kbs.co.kr/")
    jar = "; ".join(f"{c['name']}={c['value']}" for c in cookies if "kbs" in c["domain"])
    if jar:
        headers["Cookie"] = jar
    return found["url"], headers


def download_episode(ep: dict, out_path: str, headless: bool = True) -> str:
    if os.path.exists(out_path) and os.path.getsize(out_path) > 10_000_000:
        return out_path
    hint = ""
    if ep.get("play_urls"):
        m = re.search(r"/vod/\d{4}/\d{2}/\d{2}/([0-9a-f]+)/", ep["play_urls"][0])
        hint = m.group(1) if m else ""
    url, headers = capture_stream(ep["vod_page"], hint=hint, headless=headless)
    url = _lowest_variant(url, headers)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".part.mp4"
    header_arg = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-headers", header_arg, "-i", url, "-c", "copy", tmp],
        check=True,
    )
    os.replace(tmp, out_path)
    return out_path


def grab_frame(video_path: str, timestamp: str) -> bytes | None:
    """영상의 timestamp("MM:SS")에서 화면 한 장을 JPEG로 뽑는다."""
    if not timestamp or not os.path.exists(video_path):
        return None
    r = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-ss", timestamp, "-i", video_path, "-frames:v", "1",
         "-f", "image2", "-c:v", "mjpeg", "-q:v", "3", "pipe:1"],
        capture_output=True,
    )
    return r.stdout or None
