"""界面里到处要用的小零件：常量与纯函数。"""

from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

import flet as ft

import db

DIALOG_WIDTH = 300
WARN_BALANCE = db.WARN_BALANCE  # 剩余课时少于这个数就标红提醒
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
STATUS_FILTERS = [("全部", ""), ("在读", "在读"), ("停课", "停课")]
HOUR_MODE = [("充值", 1), ("扣减", -1)]


# ------------------------------------------------------------------ 小工具


def _stored_name(original: str, suffix: str | None = None) -> str:
    """给上传的文件起一个不会重名的名字。

    传了 suffix 就用它（照片压成 JPEG 之后要改成 .jpg）。
    """
    if suffix is None:
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


def _teacher_opts(none_text: str = "不指定") -> list[ft.DropdownOption]:
    """归属老师／上课老师下拉的选项（只有勾了"上课老师"的账号才列出来）。"""
    return [ft.DropdownOption(key="", text=none_text)] + _opts(
        [(t["id"], t["display_name"] or t["username"]) for t in db.list_teachers()]
    )


def _teacher_name(teacher_id) -> str:
    if not teacher_id:
        return ""
    try:
        return db.teacher_name_map().get(int(teacher_id), "")
    except (TypeError, ValueError):
        return ""


def _hour_mode_opts() -> list[ft.DropdownOption]:
    # HOUR_MODE 是 (名称, 正负号)，下拉显示名称，值也是名称
    return [ft.DropdownOption(key=name, text=name) for name, _ in HOUR_MODE]


def _status_opts() -> list[ft.DropdownOption]:
    return _opts([(s, s) for s in db.STUDENT_STATUS])


def _grade_opts() -> list[ft.DropdownOption]:
    return _opts([(g, g) for g in db.GRADE_OPTIONS])


def _school_inputs(value: str = "", width=None) -> tuple[ft.Control, ft.TextField]:
    """学校：一个手打的输入框，旁边挂一个"从填过的学校里挑"的下拉。

    不用 Flet 那个可编辑下拉框（editable=True）：它手打进去的字回不到 Python 这边，
    存的时候读到的是空的。这里把"填"和"挑"分开——填用输入框（取值可靠），
    挑用下拉，挑中了直接写进输入框。

    返回 (放进表单的那个控件, 真正用来取值的输入框)。
    """
    known = db.list_schools()
    if not known:
        # 还没填过任何学校，就是个普通输入框
        field = _tf("学校", value, width=width)
        return field, field
    # 有得选的时候：输入框吃掉剩下的宽度，右边留 112 给下拉
    field = _tf("学校", value, expand=True)
    picker = ft.Dropdown(
        label="选填过的",
        options=_opts([(s, s) for s in known]),
        dense=True,
        width=112,
        hint_text="下拉选",
        enable_filter=True,
    )

    def on_pick(e):
        name = (e.control.value or "").strip()
        if not name:
            return
        field.value = name
        e.control.value = None  # 下拉复位，下次还能再点同一个
        field.update()

    picker.on_select = on_pick
    box = ft.Row(
        [field, picker],
        spacing=6,
        width=width,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    return box, field


def _level_title(enrollment: dict) -> str:
    subject = (enrollment.get("subject") or "").strip()
    name = (enrollment.get("level_name") or "").strip()
    return f"{subject}-{name}" if subject else name


def _courses_text(enrollments) -> str:
    """把孩子的在读课程拼成一句话：等级（课程·老师）。选人时用来分清是哪门课的。"""
    bits = []
    for e in enrollments or []:
        if e.get("status") != "在读":
            continue
        tail = db.enrollment_class_label(e) or (e.get("class_type_name") or "")
        owner = (e.get("owner_teacher_name") or "").strip()
        if owner:
            tail = f"{tail}·{owner}" if tail else owner
        title = _level_title(e)
        bits.append(f"{title}（{tail}）" if tail else title)
    return "、".join(bits) or "还没报课"


def _date_text(iso: str) -> str:
    try:
        d = date.fromisoformat((iso or "").strip())
    except ValueError:
        return iso or ""
    return f"{d.month}月{d.day}日 {WEEKDAYS[d.weekday()]}"


def _week_start(iso: str = "") -> date:
    """这一天所在那一周的周一。空字符串就是今天。"""
    try:
        day = date.fromisoformat((iso or "").strip()) if (iso or "").strip() else date.today()
    except ValueError:
        day = date.today()
    return day - timedelta(days=day.weekday())


def _week_range_text(start: date) -> str:
    end = start + timedelta(days=6)
    if start.year != end.year:
        return f"{start.year}年{start.month}月{start.day}日 ~ {end.year}年{end.month}月{end.day}日"
    if start.month != end.month:
        return f"{start.month}月{start.day}日 ~ {end.month}月{end.day}日"
    return f"{start.month}月{start.day}日 ~ {end.day}日"


def _shift_month(month: str, delta: int) -> str:
    """'2026-10' 往前／往后挪几个月。"""
    try:
        year, mon = int(month[:4]), int(month[5:7])
    except (TypeError, ValueError):
        today = date.today()
        year, mon = today.year, today.month
    total = year * 12 + (mon - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _month_text(month: str) -> str:
    try:
        return f"{int(month[:4])} 年 {int(month[5:7])} 月"
    except (TypeError, ValueError):
        return month or ""


def _now_time() -> str:
    now = datetime.now()
    return f"{now.hour:02d}:{(now.minute // 15) * 15:02d}"


def _lessons_stats(lesson: dict) -> str:
    if not lesson.get("rolled", 1):
        # 排好了但还没点名：这时候课时和积分都还没算
        return f"{lesson.get('student_count') or 0} 人 · 待点名"
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
    '_grade_opts',
    '_school_inputs',
    '_level_title',
    '_courses_text',
    '_date_text',
    '_week_start',
    '_week_range_text',
    '_shift_month',
    '_month_text',
    '_now_time',
    '_lessons_stats',
    '_chip',
    '_attendance_calc',
]
