"""界面里到处要用的小零件：常量与纯函数。"""

from __future__ import annotations

import secrets
from datetime import date, datetime
from pathlib import Path

import flet as ft

import db

DIALOG_WIDTH = 300
WARN_BALANCE = db.WARN_BALANCE  # 剩余课时少于这个数就标红提醒
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
STATUS_FILTERS = [("全部", ""), ("在读", "在读"), ("停课", "停课"), ("结课", "结课")]
HOUR_MODE = [("充值", 1), ("扣减", -1)]


# ------------------------------------------------------------------ 小工具


def _stored_name(original: str) -> str:
    """给上传的文件起一个不会重名的名字。"""
    suffix = Path(original or "").suffix.lower()[:10]
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{stamp}_{secrets.token_hex(4)}{suffix}"


def _tf(label: str, value="", width=None, **kw) -> ft.TextField:
    return ft.TextField(
        label=label,
        value="" if value is None else str(value),
        dense=True,
        width=width,
        **kw,
    )


def _dd(label: str, options: list[ft.DropdownOption], value=None, width=None, **kw) -> ft.Dropdown:
    return ft.Dropdown(
        label=label,
        options=options,
        value=value,
        dense=True,
        width=width,
        **kw,
    )


def _opts(pairs) -> list[ft.DropdownOption]:
    return [ft.DropdownOption(key=str(k), text=str(v)) for k, v in pairs]


def _hour_mode_opts() -> list[ft.DropdownOption]:
    # HOUR_MODE 是 (名称, 正负号)，下拉显示名称，值也是名称
    return [ft.DropdownOption(key=name, text=name) for name, _ in HOUR_MODE]


def _status_opts() -> list[ft.DropdownOption]:
    return _opts([(s, s) for s in db.STUDENT_STATUS])


def _level_title(enrollment: dict) -> str:
    subject = (enrollment.get("subject") or "").strip()
    name = (enrollment.get("level_name") or "").strip()
    return f"{subject}-{name}" if subject else name


def _date_text(iso: str) -> str:
    try:
        d = date.fromisoformat((iso or "").strip())
    except ValueError:
        return iso or ""
    return f"{d.month}月{d.day}日 {WEEKDAYS[d.weekday()]}"


def _now_time() -> str:
    now = datetime.now()
    return f"{now.hour:02d}:{(now.minute // 15) * 15:02d}"


def _lessons_stats(lesson: dict) -> str:
    hours = round(float(lesson.get("attended_minutes") or 0) / 60, 2)
    points = float(lesson.get("points") or 0)
    parts = [f"{lesson.get('student_count') or 0} 人"]
    if hours:
        parts.append(f"扣 {db.num_text(hours)} 课时")
    if points:
        parts.append(f"积分 +{db.num_text(points)}")
    return " · ".join(parts)


def _chip(text: str, bgcolor) -> ft.Container:
    return ft.Container(
        ft.Text(text, size=11, color=ft.Colors.WHITE),
        bgcolor=bgcolor,
        padding=ft.Padding.symmetric(horizontal=6, vertical=1),
        border_radius=6,
    )


def _attendance_calc(a: dict, lesson: dict) -> tuple[float, float]:
    """算出这条点名记录扣多少课时、给多少分。"""
    present = int(a.get("attendance") or 0)
    if not present:
        return 0.0, 0.0
    points = (
        (present + int(a.get("discipline") or 0) + int(a.get("performance") or 0)) * 10
        + float(a.get("bonus") or 0)
    )
    hours = float(a.get("minutes") or lesson.get("minutes") or 0) / 60
    if not lesson.get("class_type_deduct"):
        hours = 0.0
    return round(hours, 2), points


__all__ = [
    'DIALOG_WIDTH',
    'WARN_BALANCE',
    'WEEKDAYS',
    'STATUS_FILTERS',
    'HOUR_MODE',
    '_stored_name',
    '_tf',
    '_dd',
    '_opts',
    '_hour_mode_opts',
    '_status_opts',
    '_level_title',
    '_date_text',
    '_now_time',
    '_lessons_stats',
    '_chip',
    '_attendance_calc',
]
