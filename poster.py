"""把孩子的课堂照片和课评拼成一张「海报」，发给家长看。

只用 Pillow，不依赖网络和浏览器：一张 1080 宽的长图，微信里点开就是整张，
存下来也清楚。背景跟着科目走：科创（STEM）是蓝图格子＋电路齿轮，图形化编程
（Scratch／GPL）是积木块，无人机（UAV）是航线＋信号，Python 是代码，单片机
／电子是芯片电路；同一门课不同课次的花纹位置也会挪一挪，不会张张一样。
花纹都画得很淡，不抢照片和字的清楚。
"""

from __future__ import annotations

import io
import math
import random
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH = 1080
PADDING = 56
CARD_RADIUS = 26
PHOTO_RADIUS = 24

# 通用的墨色和纸色；每门课的主色在下面的 Theme 里定
INK = (36, 48, 60)
GREY = (110, 122, 134)
LINE = (226, 231, 236)
PAGE = (255, 255, 255)

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
    # 同一节课做出来的海报要一样，不同课次要不一样：这里塞课次信息当随机种子
    seed: str = ""


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


# ---------------------------------------------------------------- 背景风格
#
# 每门课的海报长得不一样：科创（STEM）走蓝图纸＋齿轮电路，图形化编程
# （Scratch／GPL）走积木块，无人机（UAV）走航线＋信号，Python 走代码，
# 单片机／乐高电子走芯片。同一门课的不同课次，花纹位置也跟着课次挪，
# 家长连着收几张不会觉得是同一张。

GRID_STEP = 46


@dataclass(frozen=True)
class Theme:
    """一门课的海报风格：配色 + 画什么花纹。"""

    key: str
    header_top: tuple[int, int, int]
    header_bottom: tuple[int, int, int]
    grid: tuple[int, int, int]
    grid_style: str  # square（蓝图纸）/ dot（点阵）/ map（地图格）
    accent: tuple[int, int, int]
    accent_dark: tuple[int, int, int]
    soft: tuple[int, int, int]
    motif: str  # circuit / blocks / drone / code / chip


THEME_STEM = Theme(
    key="stem",
    header_top=(27, 111, 209),
    header_bottom=(42, 178, 224),
    grid=(232, 240, 248),
    grid_style="square",
    accent=(27, 111, 209),
    accent_dark=(18, 80, 143),
    soft=(234, 242, 254),
    motif="circuit",
)

THEME_SCRATCH = Theme(
    key="scratch",
    header_top=(104, 62, 214),
    header_bottom=(184, 66, 196),
    grid=(240, 234, 252),
    grid_style="dot",
    accent=(244, 132, 36),
    accent_dark=(112, 46, 158),
    soft=(244, 238, 254),
    motif="blocks",
)

THEME_UAV = Theme(
    key="uav",
    header_top=(14, 72, 110),
    header_bottom=(24, 158, 190),
    grid=(228, 242, 247),
    grid_style="map",
    accent=(237, 130, 38),
    accent_dark=(12, 78, 112),
    soft=(230, 243, 247),
    motif="drone",
)

THEME_PY = Theme(
    key="python",
    header_top=(40, 70, 150),
    header_bottom=(48, 160, 140),
    grid=(234, 243, 244),
    grid_style="square",
    accent=(38, 138, 116),
    accent_dark=(26, 70, 122),
    soft=(232, 244, 242),
    motif="code",
)

THEME_HW = Theme(
    key="hardware",
    header_top=(14, 92, 72),
    header_bottom=(48, 168, 116),
    grid=(233, 246, 238),
    grid_style="square",
    accent=(24, 140, 96),
    accent_dark=(14, 84, 64),
    soft=(231, 246, 238),
    motif="chip",
)


def theme_for(subject: str) -> Theme:
    """按科目挑风格；认不出来的（空科目等）当科创，最稳妥。"""
    text = (subject or "").strip()
    upper = text.upper()
    if "UAV" in upper or "无人机" in text or "航拍" in text or "DRONE" in upper:
        return THEME_UAV
    if "STEM" in upper or "科创" in text or "创客" in text:
        return THEME_STEM
    if upper.startswith("PY") or "PYTHON" in upper or "派森" in text:
        return THEME_PY
    if "GPL" in upper or "SCRATCH" in upper or "图形化" in text or "积木" in text:
        return THEME_SCRATCH
    if (
        upper.startswith("MCU")
        or upper.startswith("EV3")
        or "ARDUINO" in upper
        or "单片机" in text
        or "电子" in text
        or "机器人" in text
    ):
        return THEME_HW
    return THEME_STEM


def _seed_of(data: "PosterData", theme: Theme) -> int:
    """同一节课做出来的海报要一样，不同课次要不一样——所以拿课次信息当种子。"""
    key = "|".join(
        bit or ""
        for bit in (theme.key, data.seed, data.date_line, data.class_line, data.student_name)
    )
    return zlib.crc32(key.encode("utf-8"))


def _lighten(color, ratio: float):
    """把颜色往白里调（ratio 越大越接近白）。"""
    return tuple(round(c + (255 - c) * ratio) for c in color)


def _wash(color, strength: float):
    """把颜色调得很淡，用来画不抢眼的背景花纹。"""
    return tuple(round(255 - (255 - c) * strength) for c in color)


def _gradient(width: int, height: int, top, bottom) -> Image.Image:
    """竖着的渐变，用来铺顶部彩条。"""
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


def _draw_block(
    draw: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float, color, width: int
) -> None:
    """一块图形化编程的积木：圆角方块 + 上面的凸起（Scratch 的味道）。"""
    draw.rounded_rectangle((x, y, x + w, y + h), radius=16, outline=color, width=width)
    notch = min(28.0, h * 0.5)
    nx = x + w * 0.30
    draw.ellipse(
        (nx, y - notch * 0.42, nx + notch * 1.5, y + notch * 0.42),
        outline=color,
        width=width,
    )


def _draw_propeller(
    draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float, color, width: int
) -> None:
    """一个螺旋桨：桨盘 + 转轴。"""
    draw.ellipse(
        (cx - radius, cy - radius * 0.42, cx + radius, cy + radius * 0.42),
        outline=color,
        width=width,
    )
    draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=color)


def _draw_drone(
    draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float, color, width: int
) -> None:
    """四轴无人机：机身 + 四条机臂 + 四个螺旋桨。"""
    body = radius * 0.34
    draw.rounded_rectangle(
        (cx - body, cy - body * 0.78, cx + body, cy + body * 0.78),
        radius=max(4, int(body * 0.5)),
        outline=color,
        width=width,
    )
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        ax = cx + sx * radius
        ay = cy + sy * radius * 0.64
        draw.line([(cx, cy), (ax, ay)], fill=color, width=width)
        _draw_propeller(draw, ax, ay, radius * 0.38, color, width)
    # 机腹下面挂的相机云台
    draw.ellipse(
        (cx - body * 0.34, cy + body * 0.6, cx + body * 0.34, cy + body * 1.28),
        outline=color,
        width=width,
    )


def _draw_signal(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    radii: tuple[float, ...],
    color,
    width: int,
    start: int = 196,
    end: int = 344,
) -> None:
    """一圈圈信号弧（遥控／图传的感觉）。"""
    for radius in radii:
        draw.arc(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            start=start,
            end=end,
            fill=color,
            width=width,
        )


def _draw_radar(
    draw: ImageDraw.ImageDraw, cx: float, cy: float, radii: tuple[float, ...], color, width: int
) -> None:
    """雷达圈：几道同心圆 + 一条扫描线。"""
    for radius in radii:
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=color, width=width)
    draw.line([(cx, cy), (cx + radii[-1], cy)], fill=color, width=width)


def _draw_waypoints(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    color,
    width: int,
    dash: int = 20,
    gap: int = 14,
    dot: int = 6,
) -> None:
    """虚线航线 + 拐点小圆圈，像地图上的飞行路线。"""
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 1:
            continue
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        pos = 0.0
        while pos < length:
            end = min(pos + dash, length)
            draw.line(
                [(x1 + ux * pos, y1 + uy * pos), (x1 + ux * end, y1 + uy * end)],
                fill=color,
                width=width,
            )
            pos += dash + gap
    for x, y in points:
        draw.ellipse((x - dot, y - dot, x + dot, y + dot), outline=color, width=width)


def _draw_chip(
    draw: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float, color, width: int
) -> None:
    """芯片：方块身体 + 里面一小块 + 四边引脚。"""
    draw.rounded_rectangle((x, y, x + w, y + h), radius=12, outline=color, width=width)
    draw.rounded_rectangle(
        (x + w * 0.30, y + h * 0.30, x + w * 0.70, y + h * 0.70),
        radius=6,
        outline=color,
        width=width,
    )
    cols = max(3, int(w // 44))
    for i in range(cols):
        px = x + (i + 0.5) * w / cols
        draw.line([(px, y - 12), (px, y)], fill=color, width=width)
        draw.line([(px, y + h), (px, y + h + 12)], fill=color, width=width)
    rows = max(2, int(h // 44))
    for i in range(rows):
        py = y + (i + 0.5) * h / rows
        draw.line([(x - 12, py), (x, py)], fill=color, width=width)
        draw.line([(x + w, py), (x + w + 12, py)], fill=color, width=width)


def _draw_code_lines(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    w: float,
    rows: int,
    color,
    rng,
    line: int = 40,
) -> None:
    """几行长短不一的代码条，像写得满满一屏。"""
    for i in range(rows):
        indent = rng.choice([0, 0, 26, 26, 52])
        length = (w - indent) * rng.uniform(0.34, 1.0)
        yy = y + i * line
        draw.rounded_rectangle(
            (x + indent, yy, x + indent + max(36.0, length), yy + 11), radius=5, fill=color
        )


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


_CODE_GLYPHS = ("</>", "{ }", "0101", "[ ]", "= =", "#!", "::", "1 0 1")


def _header_circuit(overlay, width: int, height: int, rng, white) -> None:
    """科创：电路走线 + 齿轮 + 代码符号。"""
    draw = ImageDraw.Draw(overlay)
    # 走线走右边这片（左边留给机构名和孩子的名字），齿轮贴着右下角露一角
    _draw_circuit(
        draw, width, int(height * 0.72), white + (74,), rng, x_min=int(width * 0.42)
    )
    _draw_gear(draw, width - 60, height - 24, 128, white + (52,), 5)
    _draw_gear(draw, width - 262, height - 4, 66, white + (40,), 4)
    code_font = _font(True, 48)
    spots = ((width - 196, 26), (width - 356, 96), (width - 300, height - 128))
    for text, xy, alpha in zip(rng.sample(_CODE_GLYPHS, len(spots)), spots, (84, 56, 38)):
        _alpha_paste(overlay, _rotated_text(text, code_font, white + (255,)), xy, alpha)


def _header_blocks(overlay, width: int, height: int, rng, white) -> None:
    """图形化编程：堆起来的积木 + 事件／循环块。"""
    draw = ImageDraw.Draw(overlay)
    for i in range(3):
        w = rng.choice([148, 178, 206, 236])
        y = int(height * (0.14 + 0.28 * i)) + rng.randint(-8, 10)
        # 最上面那块往左让一让，别压到右上角的科目小牌子
        limit = 268 if y < 104 else 44
        x = min(width - limit - w, width - rng.randint(320, 470))
        _draw_block(draw, x, y, w, 52, white + (76 - i * 12,), 5)
    # 事件积木：一块带小旗的扁积木
    fx = width - rng.randint(168, 214)
    fy = int(height * rng.uniform(0.80, 0.90)) - 52
    draw.rounded_rectangle((fx, fy, fx + 132, fy + 50), radius=16, outline=white + (66,), width=5)
    draw.polygon(
        [(fx + 26, fy + 14), (fx + 26, fy + 36), (fx + 52, fy + 25)], fill=white + (72,)
    )
    # 循环箭头
    draw.arc((fx + 62, fy + 10, fx + 118, fy + 44), start=40, end=330, fill=white + (72,), width=5)


def _header_drone(overlay, width: int, height: int, rng, white) -> None:
    """无人机：四轴机 + 虚线航线 + 信号弧。"""
    draw = ImageDraw.Draw(overlay)
    _draw_drone(draw, width - rng.randint(140, 196), height * rng.uniform(0.40, 0.52), 104, white + (88,), 4)
    _draw_drone(draw, width - rng.randint(300, 380), height * rng.uniform(0.84, 0.94), 46, white + (54,), 3)
    route = [
        (width, int(height * 0.12)),
        (width - rng.randint(130, 200), int(height * 0.24)),
        (width - 34, int(height * 0.58)),
        (width - rng.randint(232, 300), int(height * 0.88)),
    ]
    _draw_waypoints(draw, route, white + (56,), 3)
    _draw_signal(draw, width - 76, height - 18, (40, 66, 92), white + (46,), 3)


def _header_code(overlay, width: int, height: int, rng, white) -> None:
    """Python：一屏代码条 + 几个代码符号。"""
    draw = ImageDraw.Draw(overlay)
    _draw_code_lines(
        draw,
        width - rng.randint(300, 356),
        int(height * rng.uniform(0.10, 0.18)),
        280,
        rng.randint(4, 6),
        white + (48,),
        rng,
        line=38,
    )
    code_font = _font(True, 46)
    spots = (("def", (width - 148, 20), 82), (">>>", (width - 300, int(height * 0.52)), 46))
    for text, xy, alpha in spots:
        _alpha_paste(overlay, _rotated_text(text, code_font, white + (255,)), xy, alpha)
    _alpha_paste(
        overlay,
        _rotated_text("[ ]", code_font, white + (255,)),
        (width - 224, height - 92),
        58,
    )


def _header_chip(overlay, width: int, height: int, rng, white) -> None:
    """单片机／电子：芯片 + 走线 + 二进制。"""
    draw = ImageDraw.Draw(overlay)
    _draw_chip(
        draw,
        width - rng.randint(232, 288),
        int(height * rng.uniform(0.24, 0.38)),
        168,
        118,
        white + (74,),
        4,
    )
    _draw_circuit(draw, width, int(height * 0.92), white + (46,), rng, x_min=int(width * 0.52))
    code_font = _font(True, 44)
    for text, xy, alpha in (("0101", (width - 122, 24), 68), ("{}", (width - 344, height - 118), 48)):
        _alpha_paste(overlay, _rotated_text(text, code_font, white + (255,)), xy, alpha)


_HEADER_DECOR = {
    "circuit": _header_circuit,
    "blocks": _header_blocks,
    "drone": _header_drone,
    "code": _header_code,
    "chip": _header_chip,
}


def _decorate_header(layer: Image.Image, theme: Theme, rng) -> None:
    """顶部花纹：按科目画不同的东西（画得淡，不抢字）。"""
    width, height = layer.size
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    _HEADER_DECOR.get(theme.motif, _header_circuit)(overlay, width, height, rng, (255, 255, 255))
    layer.alpha_composite(overlay)


def _paint_page(canvas: Image.Image, theme: Theme, rng) -> None:
    """整页的底色：按风格铺极淡的花纹，再在角上点几笔（都画在内容下面）。"""
    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size
    step = GRID_STEP
    if theme.grid_style == "dot":
        phase = rng.randrange(step)
        for x in range(phase, width, step):
            for y in range(phase, height, step):
                draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=theme.grid)
    else:
        offset = rng.randrange(step)
        for x in range(offset, width, step):
            draw.line([(x, 0), (x, height)], fill=theme.grid, width=1)
        for y in range(offset, height, step):
            draw.line([(0, y), (width, y)], fill=theme.grid, width=1)

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    ink = _wash(theme.accent, 0.34)
    faint = _wash(theme.accent, 0.22)
    # 花纹都摆在右下这一片：左边要留给彩色小标签和页脚，不压字
    if theme.motif == "blocks":
        for i, w in enumerate(rng.sample([110, 150, 190], 3)):
            _draw_block(
                odraw,
                width - 60 - w - rng.choice([0, 30]),
                height - 246 + i * 66,
                w,
                48,
                faint + (255,),
                4,
            )
    elif theme.motif == "drone":
        _draw_radar(odraw, width - 86, height - 120, (92, 62, 34), faint + (255,), 3)
        _draw_waypoints(
            odraw,
            [
                (width - 40, height - 40),
                (width - 152, height - 168),
                (width - 72, height - 292),
            ],
            ink + (255,),
            3,
        )
        _draw_drone(odraw, width - 122, height - 344, 54, faint + (255,), 3)
    elif theme.motif == "code":
        _draw_code_lines(odraw, width - 340, height - 240, 280, 4, faint + (255,), rng, line=42)
    elif theme.motif == "chip":
        _draw_chip(odraw, width - 250, height - 240, 150, 108, faint + (255,), 3)
    else:
        _draw_gear(odraw, width - 70, height - 150, 92, ink + (255,), 4)
        _draw_gear(odraw, width - 150, height - 40, 54, faint + (255,), 3)
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


def _tag_colors(tag: str, theme: Theme) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
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
    return theme.soft, theme.accent_dark


def build_poster(data: PosterData) -> bytes:
    """拼出海报图片，返回 JPEG 字节。"""
    margin = PADDING
    inner = WIDTH - margin * 2
    theme = theme_for(data.subject)
    # 同一节课的可复现，不同课次的花纹位置会变（种子含日期／班次／学号）
    rng = random.Random(_seed_of(data, theme))
    height_guess = 3200
    # 先把内容画在一张透明图上，等算完总高再铺背景——这样背景花纹不会被裁掉，
    # 也不会盖在照片和字上面。
    canvas = Image.new("RGBA", (WIDTH, height_guess), (0, 0, 0, 0))
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

    header = _gradient(WIDTH, header_height, theme.header_top, theme.header_bottom).convert("RGBA")
    _decorate_header(header, theme, rng)
    mask = Image.new("L", (WIDTH, header_height), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, WIDTH - 1, header_height - 1), radius=44, fill=255
    )
    header.putalpha(mask)
    canvas.alpha_composite(header, (0, header_top))

    text_y = header_top + header_pad
    draw.text(
        (margin, text_y),
        data.brand or "课堂分享",
        font=brand_font,
        fill=_lighten(theme.header_bottom, 0.74),
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
        # 白底要够实：花纹（齿轮、无人机的桨）从底下透出来会显得脏
        bdraw.rounded_rectangle((0, 0, badge_w - 1, 61), radius=31, fill=(255, 255, 255, 242))
        bdraw.text((24, 11), subject, font=badge_font, fill=theme.accent_dark + (255,))
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
            (margin + 24, y + 26, margin + 32, y + 62), radius=4, fill=theme.accent
        )
        draw.text((margin + 48, y + 22), title, font=title_font, fill=theme.accent_dark)
        _draw_paragraph(draw, body, body_font, INK, margin + 28, y + 88, inner - 56)
        y += card_height + 24

    card("课评", data.lesson_comment)
    card("老师点评", data.student_comment)

    # —— 小标签：本次积分、本月出勤、下次课，加上从课评里认出的知识点
    chips: list[tuple[str, tuple[int, int, int], tuple[int, int, int], tuple[int, int, int] | None]] = []
    for tag in data.tags:
        fill, ink = _tag_colors(tag, theme)
        chips.append((tag, fill, ink, None))
    for word in data.keywords:
        # 知识点用白底描边的样式，跟「本次积分」这些状态标签区分开
        chips.append((word, PAGE, theme.accent_dark, _lighten(theme.accent, 0.62)))
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

    used = max(600, min(height_guess, y + margin))
    page = Image.new("RGBA", (WIDTH, used), PAGE + (255,))
    _paint_page(page, theme, rng)
    page.alpha_composite(canvas.crop((0, 0, WIDTH, used)))
    result = page.convert("RGB")
    out = io.BytesIO()
    result.save(out, "JPEG", quality=92, optimize=True, progressive=True)
    return out.getvalue()
