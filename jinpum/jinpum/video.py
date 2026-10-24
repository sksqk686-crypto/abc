"""KBS 다시보기 영상 받기 (한국 IP에서만 동작).

KBS 플레이어 페이지를 PC의 Edge/Chrome으로 열어 재생 권한(쿠키/서명 URL)을 받고,
같은 브라우저 안에서 가장 낮은 화질(약 500kbps)의 HLS 조각을 내려받은 뒤
ffmpeg로 이어 붙여 mp4로 저장한다. 브라우저 밖(urllib/ffmpeg)에서 받으면
재생 권한이 빠져 KBS가 403으로 막는다.
"""
from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import urllib.parse

from .kbs import UA

M3U8_RE = re.compile(r"https?:[^\s\"'<>]+?\.m3u8[^\s\"'<>]*")
MIN_EPISODE_SEC = 20 * 60  # 이보다 짧으면 광고·예고로 보고 다른 주소를 쓴다


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


class _Fetcher:
    """브라우저의 재생 권한을 그대로 써서 주소를 받는다."""

    def __init__(self, ctx, page, log: list[str]):
        self.ctx, self.page, self.log = ctx, page, log
        self.headers = {"Referer": "https://vod.kbs.co.kr/", "Origin": "https://vod.kbs.co.kr"}

    def get(self, url: str) -> bytes | None:
        try:
            r = self.ctx.request.get(url, headers=self.headers, timeout=60_000)
            if r.ok:
                return r.body()
            self.log.append(f"[get] {r.status} {url[:200]}")
        except Exception as e:
            self.log.append(f"[get] 오류 {url[:200]}: {e}")
        # 페이지 안에서 fetch (플레이어와 똑같은 조건)
        try:
            b64 = self.page.evaluate(
                """async (u) => {
                    const r = await fetch(u, {credentials: 'include'});
                    if (!r.ok) return 'ERR' + r.status;
                    const b = new Uint8Array(await r.arrayBuffer());
                    let s = ''; for (let i = 0; i < b.length; i += 32768)
                        s += String.fromCharCode.apply(null, b.subarray(i, i + 32768));
                    return btoa(s);
                }""",
                url,
            )
            if b64.startswith("ERR"):
                self.log.append(f"[fetch] {b64[3:]} {url[:200]}")
                return None
            return base64.b64decode(b64)
        except Exception as e:
            self.log.append(f"[fetch] 오류 {url[:200]}: {e}")
            return None

    def get_child(self, parent: str, uri: str) -> tuple[str, bytes | None]:
        """재생목록 안의 상대 주소를 받는다. 서명이 부모 주소 쿼리에 있으면 붙여서 다시 시도."""
        url = urllib.parse.urljoin(parent, uri)
        data = self.get(url)
        q = urllib.parse.urlparse(parent).query
        if data is None and q and "?" not in uri:
            url = url + "?" + q
            data = self.get(url)
        return url, data


def _duration(playlist: str) -> float:
    return sum(float(x) for x in re.findall(r"#EXTINF:([\d.]+)", playlist))


def _resolve_media_playlist(f: _Fetcher, url: str) -> tuple[str, str] | None:
    data = f.get(url)
    if not data or not data.lstrip().startswith(b"#EXTM3U"):
        return None
    text = data.decode("utf-8", "replace")
    if "#EXT-X-STREAM-INF" in text:
        lines = text.splitlines()
        variants = []
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
                bw = int((re.search(r"BANDWIDTH=(\d+)", line) or [0, 0])[1])
                variants.append((bw, lines[i + 1].strip()))
        for _, uri in sorted(variants):  # 낮은 화질부터
            child, body = f.get_child(url, uri)
            if body and body.lstrip().startswith(b"#EXTM3U"):
                return child, body.decode("utf-8", "replace")
        return None
    return url, text


def _download_hls(f: _Fetcher, url: str, text: str, out_path: str, log: list[str]) -> None:
    tmp = out_path + ".parts"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    local, n_seg = [], 0
    segs = [l for l in text.splitlines() if l.strip() and not l.startswith("#")]
    for line in text.splitlines():
        s = line.strip()
        m = re.search(r'URI="([^"]+)"', s)
        if s.startswith(("#EXT-X-KEY", "#EXT-X-MAP")) and m:
            name = f"k{len(local)}.bin"
            _, data = f.get_child(url, m.group(1))
            if data is None:
                raise RuntimeError(f"영상 키/헤더를 받지 못했습니다: {m.group(1)[:100]}")
            open(os.path.join(tmp, name), "wb").write(data)
            local.append(s.replace(m.group(1), name))
        elif s and not s.startswith("#"):
            n_seg += 1
            name = f"s{n_seg:05d}.ts"
            _, data = f.get_child(url, s)
            if data is None:
                raise RuntimeError(f"영상 조각 {n_seg}/{len(segs)} 을 받지 못했습니다.")
            open(os.path.join(tmp, name), "wb").write(data)
            local.append(name)
            if n_seg % 50 == 0 or n_seg == len(segs):
                print(f"    영상 조각 {n_seg}/{len(segs)}", flush=True)
        else:
            local.append(s)
    playlist = os.path.join(tmp, "local.m3u8")
    open(playlist, "w", encoding="utf-8").write("\n".join(local))
    part = out_path + ".part.mp4"
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-allowed_extensions", "ALL",
         "-protocol_whitelist", "file,crypto,data", "-i", playlist, "-c", "copy", part],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        log.append(f"---- ffmpeg ----\n{r.stderr}")
        raise RuntimeError(f"영상 합치기 실패 (ffmpeg): {r.stderr[-300:]}")
    os.replace(part, out_path)
    shutil.rmtree(tmp, ignore_errors=True)


def download_episode(ep: dict, out_path: str, headless: bool = True) -> str:
    if os.path.exists(out_path) and os.path.getsize(out_path) > 10_000_000:
        return out_path
    from playwright.sync_api import sync_playwright

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    log_path = os.path.join(os.path.dirname(out_path), "영상받기_기록.txt")
    log: list[str] = []
    hint = ""
    if ep.get("play_urls"):
        m = re.search(r"/vod/\d{4}/\d{2}/\d{2}/([0-9a-f]+)/", ep["play_urls"][0])
        hint = m.group(1) if m else ""

    req_cands: list[str] = []   # 플레이어가 실제로 요청한 주소 (서명 포함) — 가장 믿을 만함
    body_cands: list[str] = []  # 페이지 데이터에 적힌 주소

    try:
        with sync_playwright() as p:
            browser, used = _launch(p, headless)
            log.append(f"browser: {used}")
            ctx = browser.new_context(user_agent=UA, locale="ko-KR")
            page = ctx.new_page()

            def on_request(req):
                log.append(f"{req.method} {req.url[:300]}")
                if ".m3u8" in req.url and req.url not in req_cands:
                    req_cands.append(req.url)

            def on_response(resp):
                try:
                    ctype = resp.headers.get("content-type", "")
                    if resp.request.resource_type in ("xhr", "fetch", "script") or "json" in ctype:
                        for u in M3U8_RE.findall(resp.text()):
                            u = u.replace("\\/", "/")
                            if u not in body_cands:
                                body_cands.append(u)
                except Exception:
                    pass

            page.on("request", on_request)
            page.on("response", on_response)
            page.goto(ep["vod_page"], wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(5000)

            def player_found():
                return [u for u in req_cands if (not hint or hint in u) and "/ad" not in u.lower()]

            for _ in range(60):  # 광고 포함 최대 약 3분
                if player_found():
                    break
                for sel in (".jw-icon-display", ".jw-display-icon-container",
                            "button[aria-label*='재생']", "button[aria-label*='Play']", "video"):
                    try:
                        page.click(sel, timeout=500)
                        break
                    except Exception:
                        pass
                page.wait_for_timeout(3000)

            f = _Fetcher(ctx, page, log)
            ordered = player_found() + [u for u in req_cands if u not in player_found()]
            ordered += [u for u in (ep.get("play_urls") or []) + body_cands if u not in ordered]
            log.append("후보 주소:\n" + "\n".join(ordered))
            for cand in ordered:
                res = _resolve_media_playlist(f, cand)
                if not res:
                    continue
                url, text = res
                dur = _duration(text)
                log.append(f"[playlist] {dur / 60:.1f}분 {url[:200]}")
                if dur < MIN_EPISODE_SEC:
                    continue
                print(f"    영상 {dur / 60:.0f}분 받는 중…", flush=True)
                _download_hls(f, url, text, out_path, log)
                return out_path
            try:
                log.append("---- 화면 글자 ----\n" + page.inner_text("body")[:3000])
            except Exception:
                pass
            browser.close()
        raise RuntimeError(f"받을 수 있는 영상 주소가 없습니다. 기록 파일을 보내 주세요: {log_path}")
    finally:
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(log))


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
