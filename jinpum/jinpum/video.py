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


M3U8_RE = re.compile(r"https?:[^\s\"'<>]+?\.m3u8[^\s\"'<>]*")


def _launch(p, headless: bool):
    """PC에 깔린 Edge/Chrome을 먼저 쓴다 (Playwright 기본 Chromium은 H.264 영상을 못 틀어서
    KBS 플레이어가 영상 주소를 요청하지 않는다)."""
    args = ["--autoplay-policy=no-user-gesture-required", "--mute-audio"]
    for channel in ("msedge", "chrome", None):
        try:
            kw = {"channel": channel} if channel else {}
            return p.chromium.launch(headless=headless, args=args, **kw), channel or "chromium"
        except Exception:
            continue
    raise RuntimeError("브라우저를 열 수 없습니다. install.bat 을 다시 실행해 주세요.")


def capture_stream(vod_page: str, play_urls: list[str] | None = None, hint: str = "",
                   headless: bool = True, log_path: str | None = None) -> tuple[str, dict]:
    """플레이어를 열고 본편 m3u8 URL과 요청 헤더(쿠키 포함)를 돌려준다."""
    from playwright.sync_api import sync_playwright

    log: list[str] = []
    cands: list[tuple[str, dict]] = []

    def add(url: str, headers: dict) -> None:
        url = url.replace("\\/", "/")
        if all(url != c[0] for c in cands):
            cands.append((url, headers))
            log.append(f"[m3u8] {url}")

    with sync_playwright() as p:
        browser, used = _launch(p, headless)
        log.append(f"browser: {used}")
        ctx = browser.new_context(user_agent=UA, locale="ko-KR")
        page = ctx.new_page()

        def on_request(req):
            log.append(f"{req.method} {req.url[:300]}")
            if ".m3u8" in req.url:
                add(req.url, req.headers)

        def on_response(resp):
            try:
                ctype = resp.headers.get("content-type", "")
                if resp.request.resource_type in ("xhr", "fetch") or "json" in ctype or "javascript" in ctype:
                    for u in M3U8_RE.findall(resp.text()):
                        add(u, resp.request.headers)
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)
        page.goto(vod_page, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(5000)

        def good():
            return [c for c in cands if (not hint or hint in c[0]) and "/ad" not in c[0].lower()]

        # 플레이어가 영상 주소를 부를 때까지 재생 버튼을 눌러 본다 (광고 포함 최대 약 3분)
        for _ in range(60):
            if good():
                break
            for sel in (".jw-icon-display", ".jw-display-icon-container", "button[aria-label*='재생']",
                        "button[aria-label*='Play']", "video"):
                try:
                    page.click(sel, timeout=500)
                    break
                except Exception:
                    pass
            page.wait_for_timeout(3000)

        # 그래도 없으면 API가 준 재생 주소를 이 브라우저의 쿠키로 직접 열어 본다
        if not good():
            for u in play_urls or []:
                try:
                    r = ctx.request.get(u, headers={"Referer": "https://vod.kbs.co.kr/"})
                    log.append(f"[direct] {r.status} {u}")
                    if r.ok and r.text().lstrip().startswith("#EXTM3U"):
                        add(u, {"referer": "https://vod.kbs.co.kr/"})
                except Exception as e:
                    log.append(f"[direct] 실패 {u}: {e}")
        cookies = ctx.cookies()
        try:
            text = page.inner_text("body")[:3000]
        except Exception:
            text = ""
        log.append("---- 화면 글자 ----\n" + text)
        browser.close()

    if log_path:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(log))
    picked = good() or [c for c in cands if "/ad" not in c[0].lower()]
    if not picked:
        if "Korea only" in text or "국내에서만" in text:
            raise RuntimeError("KBS가 해외 접속으로 판단해 재생을 막았습니다 (한국 IP 필요).")
        raise RuntimeError(f"재생 주소를 찾지 못했습니다. 기록 파일을 보내 주세요: {log_path}")
    url, req_headers = picked[0]
    headers = {k.title(): v for k, v in req_headers.items() if k.lower() in ("referer", "origin")}
    headers["User-Agent"] = UA
    headers.setdefault("Referer", "https://vod.kbs.co.kr/")
    host = urllib.parse.urlparse(url).hostname or ""
    jar = "; ".join(f"{c['name']}={c['value']}" for c in cookies
                    if host.endswith(c["domain"].lstrip(".")) or "kbs" in c["domain"])
    if jar:
        headers["Cookie"] = jar
    return url, headers


def download_episode(ep: dict, out_path: str, headless: bool = True) -> str:
    if os.path.exists(out_path) and os.path.getsize(out_path) > 10_000_000:
        return out_path
    hint = ""
    if ep.get("play_urls"):
        m = re.search(r"/vod/\d{4}/\d{2}/\d{2}/([0-9a-f]+)/", ep["play_urls"][0])
        hint = m.group(1) if m else ""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    log_path = os.path.join(os.path.dirname(out_path), "영상받기_기록.txt")
    url, headers = capture_stream(ep["vod_page"], ep.get("play_urls"), hint=hint,
                                  headless=headless, log_path=log_path)
    url = _lowest_variant(url, headers)
    tmp = out_path + ".part.mp4"
    header_arg = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-headers", header_arg, "-i", url, "-c", "copy", tmp],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n---- ffmpeg ----\n{url}\n{r.stderr}")
        raise RuntimeError(f"영상 저장 실패 (ffmpeg). 기록 파일을 보내 주세요: {log_path}\n{r.stderr[-300:]}")
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
