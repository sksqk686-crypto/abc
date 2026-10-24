"""감정 카드 HWPX 생성기.

base/ 폴더의 서식(글꼴·문단 모양·테두리)은 보내주신 양식에서 그대로 가져왔고,
본문(section0.xml)은 카드마다 새로 만든다. 표준 라이브러리만 사용한다
(Pillow가 있으면 사진을 JPEG로 줄여 파일 크기를 낮춘다).
"""
from __future__ import annotations

import datetime as _dt
import io
import os
import random
import struct
import zipfile
from xml.sax.saxutils import escape

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "base")

BULLET = "⦁ "
FOOTER = "DST 문화유산보존기술연구소"

# 표 치수(HWPUNIT) — 양식의 카드 표와 동일
TABLE_W, TABLE_H = 53359, 69562
COL_W = [8979, 13441, 6733, 8132, 6174, 9900]
ROW_H = [2713, 2897, 5100, 5483, 50817, 2552]
PHOTO_MAX_W, PHOTO_MAX_H = 48000, 46000

_CELL_MARGIN = '<hp:cellMargin left="510" right="510" top="141" bottom="141"/>'


def _sublist(paras: str) -> str:
    return (
        '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" '
        'linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" '
        f'hasNumRef="0">{paras}</hp:subList>'
    )


def _para(text: str, para_pr: int, char_pr: int, first: bool = True) -> str:
    pid = "2147483648" if first else "0"
    t = f"<hp:t>{escape(text)}</hp:t>" if text else "<hp:t/>"
    return (
        f'<hp:p id="{pid}" paraPrIDRef="{para_pr}" styleIDRef="0" pageBreak="0" '
        f'columnBreak="0" merged="0"><hp:run charPrIDRef="{char_pr}">{t}</hp:run></hp:p>'
    )


def _cell(col: int, row: int, colspan: int, width: int, height: int, paras: str, label: bool) -> str:
    bf = 4 if label else 3
    return (
        f'<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" '
        f'borderFillIDRef="{bf}">{_sublist(paras)}'
        f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/>'
        f'<hp:cellSpan colSpan="{colspan}" rowSpan="1"/>'
        f'<hp:cellSz width="{width}" height="{height}"/>{_CELL_MARGIN}</hp:tc>'
    )


def _label(col: int, row: int, text: str) -> str:
    return _cell(col, row, 1, COL_W[col], ROW_H[row], _para(text, 20, 8), True)


def _bullets(lines: list[str]) -> str:
    lines = [l.strip() for l in lines if l and l.strip()] or [""]
    out = []
    for i, line in enumerate(lines):
        if line and not line.startswith("⦁"):
            line = BULLET + line
        out.append(_para(line, 0, 9, first=(i == 0)))
    return "".join(out)


def _image_size(data: bytes) -> tuple[int, int]:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                return w, h
            seg = struct.unpack(">H", data[i + 2 : i + 4])[0]
            i += 2 + seg
    raise ValueError("지원하지 않는 이미지 형식 (PNG/JPEG만 가능)")


def prepare_image(data: bytes) -> tuple[bytes, str]:
    """사진을 (데이터, 확장자)로 돌려준다. Pillow가 있으면 1280px JPEG로 줄인다."""
    try:
        from PIL import Image  # type: ignore

        im = Image.open(io.BytesIO(data)).convert("RGB")
        if im.width > 1280:
            im = im.resize((1280, round(im.height * 1280 / im.width)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
        return buf.getvalue(), "jpg"
    except ImportError:
        return data, "png" if data[:4] == b"\x89PNG" else "jpg"


def _picture(bin_id: str, px_w: int, px_h: int, uid: int) -> str:
    org_w, org_h = px_w * 75, px_h * 75
    scale = min(PHOTO_MAX_W / org_w, PHOTO_MAX_H / org_h)
    cw, ch = round(org_w * scale), round(org_h * scale)
    return (
        f'<hp:pic id="{uid}" zOrder="10" numberingType="PICTURE" textWrap="TOP_AND_BOTTOM" '
        'textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" href="" groupLevel="0" '
        f'instid="{uid + 1}" reverse="0">'
        '<hp:offset x="0" y="0"/>'
        f'<hp:orgSz width="{org_w}" height="{org_h}"/>'
        f'<hp:curSz width="{cw}" height="{ch}"/>'
        '<hp:flip horizontal="0" vertical="0"/>'
        f'<hp:rotationInfo angle="0" centerX="{cw // 2}" centerY="{ch // 2}" rotateimage="1"/>'
        '<hp:renderingInfo>'
        '<hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
        f'<hc:scaMatrix e1="{cw / org_w:.6f}" e2="0" e3="0" e4="0" e5="{ch / org_h:.6f}" e6="0"/>'
        '<hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
        '</hp:renderingInfo>'
        '<hp:imgRect>'
        f'<hc:pt0 x="0" y="0"/><hc:pt1 x="{org_w}" y="0"/>'
        f'<hc:pt2 x="{org_w}" y="{org_h}"/><hc:pt3 x="0" y="{org_h}"/>'
        '</hp:imgRect>'
        f'<hp:imgClip left="0" right="{org_w}" top="0" bottom="{org_h}"/>'
        '<hp:inMargin left="0" right="0" top="0" bottom="0"/>'
        f'<hp:imgDim dimwidth="{org_w}" dimheight="{org_h}"/>'
        f'<hc:img binaryItemIDRef="{bin_id}" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/>'
        '<hp:effects/>'
        f'<hp:sz width="{cw}" widthRelTo="ABSOLUTE" height="{ch}" heightRelTo="ABSOLUTE" protect="0"/>'
        '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" '
        'holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" '
        'vertOffset="0" horzOffset="0"/>'
        '<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
        '<hp:shapeComment>그림입니다.</hp:shapeComment>'
        '</hp:pic>'
    )


def card_table(item: dict, picture_xml: str, uid: int) -> str:
    """item: name, number, category, price, features[list], appraisal[list]"""
    rows = []
    rows.append(
        _label(0, 0, "명칭")
        + _cell(1, 0, 5, sum(COL_W[1:]), ROW_H[0], _para(item.get("name", ""), 22, 8), False)
    )
    rows.append(
        _label(0, 1, "고유 번호")
        + _cell(1, 1, 1, COL_W[1], ROW_H[1], _para(item.get("number", ""), 20, 9), False)
        + _label(2, 1, "분류")
        + _cell(3, 1, 1, COL_W[3], ROW_H[1], _para(item.get("category", ""), 20, 9), False)
        + _label(4, 1, "가격")
        + _cell(5, 1, 1, COL_W[5], ROW_H[1], _para(item.get("price", ""), 20, 9), False)
    )
    rows.append(
        _label(0, 2, "유물 특징")
        + _cell(1, 2, 5, sum(COL_W[1:]), ROW_H[2], _bullets(item.get("features", [])), False)
    )
    rows.append(
        _label(0, 3, "감정 내용")
        + _cell(1, 3, 5, sum(COL_W[1:]), ROW_H[3], _bullets(item.get("appraisal", [])), False)
    )
    photo_para = (
        '<hp:p id="2147483648" paraPrIDRef="20" styleIDRef="0" pageBreak="0" columnBreak="0" '
        f'merged="0"><hp:run charPrIDRef="1">{picture_xml}<hp:t/></hp:run></hp:p>'
    )
    rows.append(_cell(0, 4, 6, TABLE_W, ROW_H[4], photo_para, False))
    rows.append(_cell(0, 5, 6, TABLE_W, ROW_H[5], _para(FOOTER, 20, 8), False))
    trs = "".join(f"<hp:tr>{r}</hp:tr>" for r in rows)
    return (
        f'<hp:tbl id="{uid}" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" '
        'textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="1" '
        'rowCnt="6" colCnt="6" cellSpacing="0" borderFillIDRef="3" noAdjust="0">'
        f'<hp:sz width="{TABLE_W}" widthRelTo="ABSOLUTE" height="{TABLE_H}" heightRelTo="ABSOLUTE" protect="0"/>'
        '<hp:pos treatAsChar="0" affectLSpacing="0" flowWithText="1" allowOverlap="0" '
        'holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT" '
        'vertOffset="0" horzOffset="0"/>'
        '<hp:outMargin left="141" right="141" top="141" bottom="141"/>'
        '<hp:inMargin left="510" right="510" top="141" bottom="141"/>'
        f"{trs}</hp:tbl>"
    )


def _read(rel: str) -> bytes:
    with open(os.path.join(BASE_DIR, rel), "rb") as f:
        return f.read()


def write_cards(path: str, items: list[dict]) -> None:
    """items 각각에 photo(bytes 또는 None)를 넣어 주면 카드 한 장씩 만든다."""
    rnd = random.Random(path)
    images: list[tuple[str, str, bytes]] = []  # (id, href, data)
    tables = []
    for n, item in enumerate(items, 1):
        pic = ""
        photo = item.get("photo")
        if photo:
            data, ext = prepare_image(photo)
            w, h = _image_size(data)
            bin_id = f"image{len(images) + 1}"
            images.append((bin_id, f"BinData/{bin_id}.{ext}", data))
            pic = _picture(bin_id, w, h, rnd.randrange(10**9, 2 * 10**9))
        tables.append(card_table(item, pic, rnd.randrange(10**9, 2 * 10**9)))

    prefix = _read("Contents/section_prefix.xml").decode("utf-8")
    section = (
        prefix
        + '<hp:run charPrIDRef="0">'
        + "".join(tables)
        + "<hp:t/></hp:run></hp:p></hs:sec>"
    )

    hpf = _read("Contents/content.hpf").decode("utf-8")
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    import re

    hpf = re.sub(r'(name="(?:CreatedDate|ModifiedDate)" content="text">)[^<]*', rf"\g<1>{now}", hpf)
    manifest_items = "".join(
        f'<opf:item id="{i}" href="{href}" media-type="image/{"png" if href.endswith("png") else "jpeg"}" isEmbeded="1"/>'
        for i, href, _ in images
    )
    hpf = hpf.replace('<opf:item id="section0"', manifest_items + '<opf:item id="section0"', 1)

    preview = "\r\n".join(
        f"<명칭><{it.get('name','')}>\r\n<고유 번호><{it.get('number','')}><분류><{it.get('category','')}><가격><{it.get('price','')}>"
        for it in items[:3]
    )

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), _read("mimetype"), compress_type=zipfile.ZIP_STORED)
        z.writestr("version.xml", _read("version.xml"), compress_type=zipfile.ZIP_STORED)
        z.writestr("Contents/header.xml", _read("Contents/header.xml"), compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("Contents/section0.xml", section.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("Preview/PrvText.txt", preview.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("settings.xml", _read("settings.xml"), compress_type=zipfile.ZIP_DEFLATED)
        for _, href, data in images:
            z.writestr(href, data, compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.rdf", _read("META-INF/container.rdf"), compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("Contents/content.hpf", hpf.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("META-INF/container.xml", _read("META-INF/container.xml"), compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("META-INF/manifest.xml", _read("META-INF/manifest.xml"), compress_type=zipfile.ZIP_DEFLATED)
