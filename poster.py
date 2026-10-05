"""把孩子的课堂照片和课评拼成一张「海报」，发给家长看。

只用 Pillow，不依赖网络和浏览器：一张 1080 宽的长图，微信里点开就是整张，
存下来也清楚。背景是编程／STEM 味道的（电路走线、齿轮、代码符号、蓝图格子），
但都画得很淡，不抢照片和字的清楚。
"""

from __future__ import annotations

import io
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH = 1080
PADDING = 56
CARD_RADIUS = 26
PHOTO_RADIUS = 24

# 主色：STEM 蓝 → 青，活泼但不吵
BLUE = (27, 111, 209)
CYAN = (42, 178, 224)
BLUE_DARK = (18, 80, 143)
BLUE_SOFT = (234, 242, 254)
INK = (36, 48, 60)
GREY = (110, 122, 134)
LINE = (226, 231, 236)
PAGE = (255, 255, 255)
GRID = (232, 240, 248)

# 中文字体：Mac 上优先用黑体，Linux/WSL 上退到 Noto 或 Windows 自带的字体；
# 都没有就报错让调用方提示。
FONT_CANDIDATES: tuple[tuple[str, int, int], ...] = (
    # macOS
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0, 2),
    ("/System/Library/Fonts/STHeiti Medium.ttc", 1, 1),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 4, 1),
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 0, 0),
    ("/Library/Fonts/Arial Unicode.ttf", 0, 0),
    # Linux（Ubuntu/Debian 装 fonts-noto-cjk 就有）
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0, 1),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", 0, 1),
    ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", 0, 1),
    # WSL：不用额外装字体，直接用 Windows 自带的（/mnt/c 是 Windows 的 C 盘）
    ("/mnt/c/Windows/Fonts/msyh.ttc", 0, 1),  # 微软雅黑
    ("/mnt/c/Windows/Fonts/simhei.ttf", 0, 0),  # 黑体
    ("/mnt/c/Windows/Fonts/simsun.ttc", 0, 1),  # 宋体
    ("/mnt/c/Windows/Fonts/Deng.ttf", 0, 0),  # 等线
    # 其他 Linux 发行版
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0, 0),
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0, 0),
    ("/usr/share/fonts/truetype/arphic/uming.ttc", 0, 0),
)

_COMPOUND_SURNAMES = {
    "欧阳",
    "司马",
    "上官",
    "诸葛",
    "东方",
    "皇甫",
    "尉迟",
    "公孙",
    "慕容",
    "长孙",
    "司徒",
    "司空",
    "夏侯",
    "南宫",
    "西门",
    "独孤",
}

_ROLE_WORDS = {"管理员", "管理", "老板", "校长", "店长", "前台"}


class PosterError(RuntimeError):
    """做海报失败时抛这个，界面上直接显示原因。"""


@dataclass
class PosterData:
    """一张海报要显示的东西（都已经是排好版的短文本）。"""

    student_name: str
    date_line: str = ""
    class_line: str = ""
    subject: str = ""
    brand: str = ""
    contact: str = ""
    lesson_comment: str = ""
    student_comment: str = ""
    teacher_name: str = ""
    tags: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    photos: tuple[bytes, ...] = ()
    photo_labels: tuple[str, ...] = field(default=())


_font_cache: dict[tuple[bool, int], ImageFont.FreeTypeFont] = {}
_font_files_cache: tuple[str, int, str, int] | None = None


def teacher_label(name: str) -> str:
    """李昂 → 李老师；高正元 → 高老师。海报上不直呼老师的名字。"""
    text = (name or "").strip()
    if not text:
        return ""
    if text.endswith("老师"):
        return text
    if text in _ROLE_WORDS:  # 「管理员」这种不是人名，原样留着
        return text
    # 中文名取姓（第一个字），复姓（欧阳、司马…）取两个字
    if all("\u4e00" <= ch <= "\u9fff" for ch in text):
        surname = text[:2] if text[:2] in _COMPOUND_SURNAMES else text[:1]
        return f"{surname}老师"
    return f"{text}老师"


def _pick_font_files() -> tuple[str, int, str, int]:
    """挑一套能用的中文字体，返回 (常规字体, 常规序号, 粗体, 粗体序号)。"""
    global _font_files_cache
    if _font_files_cache is None:
        for path, regular, bold in FONT_CANDIDATES:
            if not Path(path).exists():
                continue
            try:
                ImageFont.truetype(path, 32, index=regular)
                ImageFont.truetype(path, 32, index=bold)
            except OSError:
                continue
            _font_files_cache = (path, regular, path, bold)
            break
        else:
            raise PosterError("这台电脑上找不到中文字体，海报做不出来")
    return _font_files_cache


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    key = (bold, size)
    if key not in _font_cache:
        regular_path, regular_index, bold_path, bold_index = _pick_font_files()
        path, index = (bold_path, bold_index) if bold else (regular_path, regular_index)
        _font_cache[key] = ImageFont.truetype(path, size, index=index)
    return _font_cache[key]


def _wrap(text: str, font, max_width: float) -> list[str]:
    """中文按字断行，英文数字尽量不断开。"""
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines: list[str] = []
    for raw in (text or "").splitlines():
        para = raw.strip()
        if not para:
            lines.append("")
            continue
        tokens: list[str] = []
        buffer = ""
        for ch in para:
            if ch.isascii() and not ch.isspace():
                buffer += ch
                continue
            if buffer:
                tokens.append(buffer)
                buffer = ""
            tokens.append(ch)
        if buffer:
            tokens.append(buffer)
        current = ""
        for token in tokens:
            if draw.textlength(current + token, font=font) <= max_width or not current:
                current += token
            else:
                lines.append(current)
                current = token if not token.isspace() else ""
        lines.append(current)
    return lines


def _draw_paragraph(
    draw: ImageDraw.ImageDraw, text: str, font, fill, x: float, y: float, max_width: float
) -> float:
    """画一段会自动换行的字，返回下一行的 y。"""
    line_height = int(font.size * 1.52)
    for line in _wrap(text, font, max_width):
        if line:
            draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def _cover(image: Image.Image, width: int, height: int) -> Image.Image:
    """等比缩放后居中裁切，填满给定的框（不变形）。"""
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.LANCZOS,
    )
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _rounded(image: Image.Image, radius: int) -> Image.Image:
    """把图切成圆角（放大 4 倍画遮罩再缩回来，边缘才不毛）。"""
    mask = Image.new("L", (image.width * 4, image.height * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, image.width * 4 - 1, image.height * 4 - 1), radius=radius * 4, fill=255
    )
    mask = mask.resize(image.size, Image.LANCZOS)
    out = Image.new("RGB", image.size, PAGE)
    out.paste(image, (0, 0), mask)
    return out


def _decode_photo(data: bytes) -> Image.Image | None:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception:
        return None
    if getattr(image, "is_animated", False):
        image.seek(0)
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", image.size, PAGE)
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image if image.mode == "RGB" else image.convert("RGB")


# ------------------------------------------------------------------ 背景装饰


def _gradient(width: int, height: int, top, bottom) -> Image.Image:
    """竖着的渐变，用来铺顶部蓝条。"""
    strip = Image.new("RGB", (1, height))
    pixels = strip.load()
    for y in range(height):
        ratio = y / max(1, height - 1)
        pixels[0, y] = tuple(
            round(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)
        )
    return strip.resize((width, height), Image.BILINEAR)


def _draw_gear(
    draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float, color, width: int
) -> None:
    """画一个齿轮轮廓（编程／机器人课的味道）。"""
    teeth = 10
    draw.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius), outline=color, width=width
    )
    draw.ellipse(
        (cx - radius * 0.34, cy - radius * 0.34, cx + radius * 0.34, cy + radius * 0.34),
        outline=color,
        width=width,
    )
    for index in range(teeth):
        angle = 2 * math.pi * index / teeth
        inner = radius * 0.92
        outer = radius * 1.16
        draw.line(
            [
                (cx + inner * math.cos(angle), cy + inner * math.sin(angle)),
                (cx + outer * math.cos(angle), cy + outer * math.sin(angle)),
            ],
            fill=color,
            width=width + 2,
        )


def _draw_circuit(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    color,
    rng,
    x_min: int = 0,
) -> None:
    """电路板走线：直来直去的线 + 焊点小圆圈。"""
    for _ in range(7):
        x = rng.randrange(max(0, x_min), width)
        y = rng.randrange(0, height)
        points = [(x, y)]
        for _ in range(rng.randint(2, 4)):
            if rng.random() < 0.5:
                x = min(
                    width - 10,
                    max(x_min, x + rng.choice([-1, 1]) * rng.randint(60, 190)),
                )
            else:
                y = min(height - 10, max(10, y + rng.choice([-1, 1]) * rng.randint(40, 130)))
            points.append((x, y))
        draw.line(points, fill=color, width=3, joint="curve")
        for px, py in (points[0], points[-1]):
            draw.ellipse((px - 7, py - 7, px + 7, py + 7), outline=color, width=3)


def _rotated_text(text: str, font, color) -> Image.Image:
    """把一小段字画成一张透明小图，当装饰用。"""
    probe = Image.new("RGBA", (10, 10))
    box = ImageDraw.Draw(probe).textbbox((0, 0), text, font=font)
    tile = Image.new("RGBA", (box[2] - box[0] + 12, box[3] - box[1] + 12), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((6 - box[0], 6 - box[1]), text, font=font, fill=color)
    return tile


def _alpha_paste(
    base: Image.Image, overlay: Image.Image, xy: tuple[int, int], alpha: int
) -> None:
    if alpha < 255:
        overlay = overlay.copy()
        overlay.putalpha(overlay.getchannel("A").point(lambda v: v * alpha // 255))
    base.alpha_composite(overlay, xy)


def _decorate_header(layer: Image.Image) -> None:
    """顶部的电路走线、齿轮和代码符号（画得淡，不抢字）。"""
    width, height = layer.size
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rng = random.Random(20261004)
    # 走线走右边这片（左边留给机构名和孩子的名字），齿轮贴着右下角露一角
    _draw_circuit(
        draw, width, int(height * 0.72), (255, 255, 255, 74), rng, x_min=int(width * 0.42)
    )
    _draw_gear(draw, width - 60, height - 24, 128, (255, 255, 255, 52), 5)
    _draw_gear(draw, width - 262, height - 4, 66, (255, 255, 255, 40), 4)
    code_font = _font(True, 48)
    for text, xy, alpha in (
        ("</>", (width - 196, 26), 84),
        ("{ }", (width - 356, 96), 56),
        ("0101", (width - 300, height - 128), 38),
    ):
        _alpha_paste(
            overlay, _rotated_text(text, code_font, (255, 255, 255, 255)), xy, alpha
        )
    layer.alpha_composite(overlay)


def _paint_page(canvas: Image.Image) -> None:
    """整页的底色：极淡的蓝图格子 + 右下角的小装饰。"""
    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size
    step = 46
    for x in range(0, width, step):
        draw.line([(x, 0), (x, height)], fill=GRID, width=1)
    for y in range(0, height, step):
        draw.line([(0, y), (width, y)], fill=GRID, width=1)

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    _draw_gear(odraw, width - 70, height - 150, 92, (198, 220, 241, 150), 4)
    _draw_gear(odraw, width - 150, height - 40, 54, (206, 227, 245, 130), 3)
    code_font = _font(True, 46)
    for text, xy, alpha in (
        ("{}", (54, height - 210), 60),
        ("1 0 1", (60, height - 140), 52),
    ):
        _alpha_paste(overlay, _rotated_text(text, code_font, (163, 193, 222, 255)), xy, alpha)
    canvas.alpha_composite(overlay)


def _photo_layout(count: int) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """算照片怎么摆，返回 (每块宽, 每块高, [(x, y, w, h), ...])。"""
    inner = WIDTH - PADDING * 2
    gap = 20
    if count <= 1:
        return inner, 640, [(PADDING, 0, inner, 640)]
    if count == 2:
        box_w = (inner - gap) // 2
        return box_w, 620, [
            (PADDING, 0, box_w, 620),
            (PADDING + box_w + gap, 0, box_w, 620),
        ]
    box = (inner - gap) // 2
    boxes = []
    for index in range(min(count, 4)):
        row, col = divmod(index, 2)
        boxes.append((PADDING + col * (box + gap), row * (box + gap), box, box))
    return box, box, boxes


def _tag_colors(tag: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """小标签按内容配色，比一水儿蓝的活泼些。"""
    if tag.startswith("出勤"):
        return (228, 246, 235), (24, 122, 74)
    if tag.startswith("请假"):
        return (255, 242, 224), (158, 92, 6)
    if tag.startswith("纪律"):
        return (232, 240, 254), (18, 80, 143)
    if tag.startswith("表现"):
        return (241, 234, 254), (92, 46, 158)
    if tag.startswith("突出"):
        return (255, 243, 222), (154, 91, 0)
    if tag.startswith("本次积分"):
        return (255, 236, 231), (176, 58, 27)
    if tag.startswith("下次课"):
        return (232, 240, 254), (18, 80, 143)
    if tag.startswith("本月出勤"):
        return (228, 246, 235), (24, 122, 74)
    if tag.startswith("时长"):
        return (241, 243, 245), (74, 85, 97)
    return BLUE_SOFT, BLUE_DARK


def build_poster(data: PosterData) -> bytes:
    """拼出海报图片，返回 JPEG 字节。"""
    margin = PADDING
    inner = WIDTH - margin * 2
    height_guess = 2800
    canvas = Image.new("RGBA", (WIDTH, height_guess), PAGE + (255,))
    _paint_page(canvas)
    draw = ImageDraw.Draw(canvas)

    # —— 顶部蓝条：机构署名 + 孩子名字 + 日期/班次
    header_top = 40
    header_pad = 40
    name_font = _font(True, 76)
    meta_font = _font(False, 34)
    brand_font = _font(False, 30)

    meta_line = " · ".join(x for x in (data.date_line, data.class_line) if x)
    # 留出右边一片给装饰和科目牌子，日期那行不往那边压
    meta_lines = _wrap(meta_line, meta_font, inner - 300) if meta_line else []
    header_height = header_pad + 46 + 100
    header_height += int(meta_font.size * 1.52) * len(meta_lines)
    header_height += 44

    header = _gradient(WIDTH, header_height, BLUE, CYAN).convert("RGBA")
    _decorate_header(header)
    mask = Image.new("L", (WIDTH, header_height), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, WIDTH - 1, header_height - 1), radius=44, fill=255
    )
    header.putalpha(mask)
    canvas.alpha_composite(header, (0, header_top))

    text_y = header_top + header_pad
    draw.text(
        (margin, text_y), data.brand or "课堂分享", font=brand_font, fill=(212, 233, 252)
    )
    text_y += 50
    draw.text(
        (margin, text_y),
        data.student_name or "课堂分享",
        font=name_font,
        fill=(255, 255, 255),
    )
    text_y += 100
    if meta_line:
        _draw_paragraph(
            draw, meta_line, meta_font, (255, 255, 255), margin, text_y, inner - 300
        )

    # 科目小牌子（STEM / PY / MCU…）
    subject = (data.subject or "").strip()
    if subject:
        badge_font = _font(True, 32)
        badge_w = int(draw.textlength(subject, font=badge_font)) + 48
        badge = Image.new("RGBA", (badge_w, 62), (255, 255, 255, 0))
        bdraw = ImageDraw.Draw(badge)
        bdraw.rounded_rectangle((0, 0, badge_w - 1, 61), radius=31, fill=(255, 255, 255, 205))
        bdraw.text((24, 11), subject, font=badge_font, fill=BLUE_DARK + (255,))
        canvas.alpha_composite(badge, (WIDTH - margin - badge_w, header_top + header_pad - 8))

    y = header_top + header_height + 40

    # —— 照片
    photos = [p for p in (_decode_photo(raw) for raw in data.photos) if p is not None][:4]
    if photos:
        _, _, boxes = _photo_layout(len(photos))
        for image, (bx, by, bw, bh) in zip(photos, boxes):
            canvas.paste(_rounded(_cover(image, bw, bh), PHOTO_RADIUS), (bx, y + by))
        last = boxes[-1]
        y += last[1] + last[3] + 34

    def card(title: str, body: str) -> None:
        nonlocal y
        body = (body or "").strip()
        if not body:
            return
        title_font = _font(True, 36)
        body_font = _font(False, 36)
        body_lines = _wrap(body, body_font, inner - 56)
        card_height = 28 + 52 + int(body_font.size * 1.52) * len(body_lines) + 26
        draw.rounded_rectangle(
            (margin + 3, y + 5, WIDTH - margin + 3, y + card_height + 5),
            radius=CARD_RADIUS,
            fill=(228, 236, 245),
        )
        draw.rounded_rectangle(
            (margin, y, WIDTH - margin, y + card_height),
            radius=CARD_RADIUS,
            fill=PAGE,
            outline=LINE,
            width=2,
        )
        # 标题左边一小段彩色竖条，看着有精神
        draw.rounded_rectangle(
            (margin + 24, y + 26, margin + 32, y + 62), radius=4, fill=BLUE
        )
        draw.text((margin + 48, y + 22), title, font=title_font, fill=BLUE_DARK)
        _draw_paragraph(draw, body, body_font, INK, margin + 28, y + 88, inner - 56)
        y += card_height + 24

    card("课评", data.lesson_comment)
    card("老师点评", data.student_comment)

    # —— 小标签：本次积分、本月出勤、下次课，加上从课评里认出的知识点
    chips: list[tuple[str, tuple[int, int, int], tuple[int, int, int], tuple[int, int, int] | None]] = []
    for tag in data.tags:
        fill, ink = _tag_colors(tag)
        chips.append((tag, fill, ink, None))
    for word in data.keywords:
        # 知识点用白底描边的样式，跟「本次积分」这些状态标签区分开
        chips.append((word, PAGE, BLUE_DARK, (168, 203, 238)))
    if chips:
        tag_font = _font(False, 32)
        cx, cy = margin, y + 6
        row_height = 74
        for text, fill, ink, outline in chips:
            tag_width = int(draw.textlength(text, font=tag_font)) + 44
            if cx + tag_width > WIDTH - margin:
                cx = margin
                cy += row_height
            draw.rounded_rectangle(
                (cx, cy, cx + tag_width, cy + 58),
                radius=29,
                fill=fill,
                outline=outline,
                width=2 if outline else 0,
            )
            draw.text((cx + 22, cy + 11), text, font=tag_font, fill=ink)
            cx += tag_width + 16
        y = cy + 58 + 30

    # —— 页脚
    footer_bits = [
        bit
        for bit in (
            data.teacher_name and f"上课老师 {data.teacher_name}",
            data.contact,
        )
        if bit
    ]
    if footer_bits:
        footer_font = _font(False, 30)
        draw.text((margin, y + 6), " · ".join(footer_bits), font=footer_font, fill=GREY)
        y += 50

    result = canvas.crop((0, 0, WIDTH, min(height_guess, y + margin))).convert("RGB")
    out = io.BytesIO()
    result.save(out, "JPEG", quality=92, optimize=True, progressive=True)
    return out.getvalue()
