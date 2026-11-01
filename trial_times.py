"""给家长看的试听可约时段长图。"""

from __future__ import annotations

import io
from datetime import date, datetime

from PIL import Image, ImageDraw, ImageOps

import poster

WIDTH = 1080
PADDING = 56
CARD_RADIUS = 24
INK = (36, 48, 60)
GREY = (104, 116, 128)
LINE = (224, 231, 238)
PAGE = (255, 255, 255)
BLUE = (25, 118, 210)
BLUE_SOFT = (232, 243, 255)
ORANGE_SOFT = (255, 245, 230)


def _slot_lines(slots: list[str]) -> list[str]:
    out: list[str] = []
    for start in slots:
        try:
            hour, minute = (int(part) for part in start.split(":"))
        except (TypeError, ValueError):
            continue
        end_minutes = hour * 60 + minute + 60
        out.append(f"{hour:02d}:{minute:02d}–{end_minutes // 60:02d}:{end_minutes % 60:02d}")
    return out


def _paste_square(base: Image.Image, blob: bytes, box: tuple[int, int, int, int]) -> None:
    if not blob:
        return
    try:
        source = Image.open(io.BytesIO(blob))
        source = source.convert("RGBA")
        source = ImageOps.fit(
            source,
            (box[2] - box[0], box[3] - box[1]),
            method=Image.Resampling.LANCZOS,
        )
        base.paste(source, (box[0], box[1]), source)
    except Exception:
        return


def build_trial_times_image(
    start_day: str,
    end_day: str,
    teacher_name: str,
    days: list[dict],
    *,
    brand: str = "",
    contact: str = "",
    qr_code: bytes = b"",
    logo: bytes = b"",
    generated_at: str = "",
) -> bytes:
    """用可约日期和 1 小时时段生成 1080 宽图片，不暴露班级或孩子姓名。"""
    shown_days = [
        {
            **day,
            "slot_lines": _slot_lines(list(day.get("slots") or [])),
            "card_height": 104
            + ((len(day.get("slots") or []) + 3) // 4) * 62,
        }
        for day in days
    ]
    body_height = max(
        144,
        sum(int(day["card_height"]) for day in shown_days),
    )
    footer_height = 260 if qr_code else 190
    height = max(1180, 250 + body_height + footer_height)
    image = Image.new("RGB", (WIDTH, height), PAGE)
    draw = ImageDraw.Draw(image)
    title_font = poster._font(True, 58)
    subtitle_font = poster._font(False, 28)
    section_font = poster._font(True, 34)
    body_font = poster._font(False, 27)
    slot_font = poster._font(True, 26)
    small_font = poster._font(False, 22)

    draw.rounded_rectangle(
        (0, 0, WIDTH, 205),
        radius=0,
        fill=(245, 249, 253),
    )
    draw.text((PADDING, 52), "试听可约时段", font=title_font, fill=INK)
    date_line = (
        f"{start_day} 至 {end_day} · 每次试听 1 小时"
        if start_day != end_day
        else f"{start_day} · 每次试听 1 小时"
    )
    draw.text((PADDING, 130), date_line, font=subtitle_font, fill=GREY)
    if teacher_name:
        teacher_font = poster._font(True, 28)
        teacher_text = f"试听老师：{poster.teacher_label(teacher_name)}"
        teacher_width = draw.textlength(teacher_text, font=teacher_font)
        draw.rounded_rectangle(
            (WIDTH - PADDING - teacher_width - 36, 118, WIDTH - PADDING, 174),
            radius=18,
            fill=BLUE_SOFT,
        )
        draw.text(
            (WIDTH - PADDING - teacher_width - 18, 130),
            teacher_text,
            font=teacher_font,
            fill=BLUE,
        )
    if logo:
        _paste_square(image, logo, (WIDTH - 150, 34, WIDTH - 56, 108))

    y = 248
    if not shown_days:
        draw.rounded_rectangle(
            (PADDING, y, WIDTH - PADDING, y + 220),
            radius=CARD_RADIUS,
            fill=ORANGE_SOFT,
        )
        draw.text(
            (PADDING + 34, y + 54),
            "近期暂无可约时段",
            font=section_font,
            fill=INK,
        )
        draw.text(
            (PADDING + 34, y + 112),
            "请联系老师确认其他时间。",
            font=body_font,
            fill=GREY,
        )
        y += 260
    else:
        weekday_names = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
        for day in shown_days:
            card_height = int(day["card_height"])
            try:
                current = date.fromisoformat(str(day.get("date") or ""))
                date_text = (
                    f"{current.month}月{current.day}日 "
                    f"{weekday_names[current.weekday()]}"
                )
            except ValueError:
                date_text = str(day.get("date") or "")
            draw.rounded_rectangle(
                (PADDING, y, WIDTH - PADDING, y + card_height - 12),
                radius=CARD_RADIUS,
                fill=(250, 251, 252),
                outline=LINE,
                width=2,
            )
            draw.text(
                (PADDING + 28, y + 22),
                date_text,
                font=section_font,
                fill=INK,
            )
            day_label = str(day.get("label") or "")
            if day_label:
                label_width = draw.textlength(day_label, font=small_font)
                draw.rounded_rectangle(
                    (
                        WIDTH - PADDING - label_width - 52,
                        y + 23,
                        WIDTH - PADDING - 22,
                        y + 61,
                    ),
                    radius=14,
                    fill=BLUE_SOFT,
                )
                draw.text(
                    (WIDTH - PADDING - label_width - 38, y + 29),
                    day_label,
                    font=small_font,
                    fill=BLUE,
                )
            slots = day["slot_lines"]
            if not slots:
                empty_text = (
                    "当天不安排试听"
                    if not day.get("is_open", True)
                    else "暂无可约时段"
                )
                draw.text(
                    (PADDING + 28, y + 70),
                    empty_text,
                    font=body_font,
                    fill=GREY,
                )
            chip_width = 218
            chip_height = 54
            gap = 12
            per_row = 4
            for index, slot in enumerate(slots):
                row, column = divmod(index, per_row)
                left = PADDING + 28 + column * (chip_width + gap)
                top = y + 72 + row * (chip_height + 8)
                draw.rounded_rectangle(
                    (left, top, left + chip_width, top + chip_height),
                    radius=14,
                    fill=BLUE_SOFT,
                )
                draw.text(
                    (left + 20, top + 12),
                    slot,
                    font=slot_font,
                    fill=BLUE,
                )
            y += card_height

    footer_top = max(y + 18, height - footer_height)
    draw.line((PADDING, footer_top, WIDTH - PADDING, footer_top), fill=LINE, width=2)
    contact_bits = [text for text in (brand, contact) if text]
    if contact_bits:
        draw.text(
            (PADDING, footer_top + 34),
            " · ".join(contact_bits),
            font=body_font,
            fill=INK,
        )
    note = "时段会随排课变化，请选好后联系老师确认。"
    draw.text((PADDING, footer_top + 88), note, font=small_font, fill=GREY)
    stamp = generated_at or datetime.now().strftime("%Y年%m月%d日 %H:%M")
    draw.text(
        (PADDING, footer_top + 132),
        f"生成时间：{stamp}",
        font=small_font,
        fill=(145, 154, 163),
    )
    if qr_code:
        box = 168
        left = WIDTH - PADDING - box
        top = footer_top + 26
        _paste_square(image, qr_code, (left, top, left + box, top + box))
        draw.text(
            (left + 26, top + box + 8),
            "扫码联系",
            font=small_font,
            fill=GREY,
        )

    out = io.BytesIO()
    image.save(out, "JPEG", quality=93, optimize=True, progressive=True)
    return out.getvalue()


__all__ = ["build_trial_times_image"]
