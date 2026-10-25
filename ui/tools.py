"""日常小工具：先从 3D 打印积分计算开始。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_CEILING

import flet as ft

import db
from .common import _tf


def print_half_hour_units(duration_minutes) -> int:
    """每开始一个 30 分钟按一档，不足 30 分钟也按一档。"""
    try:
        duration = Decimal(str(duration_minutes))
    except (InvalidOperation, TypeError, ValueError) as err:
        raise ValueError("请填写打印时长") from err
    if duration <= 0:
        raise ValueError("打印时长必须大于 0")
    return int(
        (duration / Decimal("30")).to_integral_value(rounding=ROUND_CEILING)
    )


def calculate_3d_print_points(weight_g, duration_minutes) -> float:
    """按耗材重量、半小时档数计算 3D 打印消耗的积分。"""
    try:
        weight = Decimal(str(weight_g))
    except (InvalidOperation, TypeError, ValueError) as err:
        raise ValueError("请填写耗材重量") from err
    if weight <= 0:
        raise ValueError("耗材重量必须大于 0")
    units = print_half_hour_units(duration_minutes)
    return float(weight * Decimal("10") * units)


def format_print_duration(duration_minutes) -> str:
    """把总分钟数写成人容易核对的小时／分钟。"""
    hours, minutes = divmod(int(duration_minutes), 60)
    if hours and minutes:
        return f"{hours} 小时 {minutes} 分钟"
    if hours:
        return f"{hours} 小时"
    return f"{minutes} 分钟"


def parse_print_duration(value) -> int:
    """把 3:00 这样的「小时:分钟」转成总分钟。"""
    text = str(value or "").strip().replace("：", ":")
    if ":" not in text:
        raise ValueError("请按「小时:分钟」填写，例如 3:00")
    hour_text, minute_text = text.split(":", 1)
    try:
        hours = int(hour_text.strip())
        minutes = int(minute_text.strip())
    except ValueError as err:
        raise ValueError("请按「小时:分钟」填写，例如 3:00") from err
    if hours < 0 or minutes < 0 or minutes > 59:
        raise ValueError("小时不能小于 0，分钟请填 0～59")
    duration = hours * 60 + minutes
    if duration <= 0:
        raise ValueError("打印时长必须大于 0")
    return duration


class ToolsMixin:
    """工具栏页面（ClassHoursApp 的一部分）。"""

    def _tools_view(self) -> ft.Control:
        weight = _tf(
            "耗材重量（克）",
            hint_text="例如 12.5",
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
        )
        duration = _tf(
            "打印时长（小时:分钟）",
            hint_text="例如 3:00",
            prefix_icon=ft.Icons.SCHEDULE,
            expand=True,
        )
        result = ft.Text(
            "等待计算",
            size=16,
            color=ft.Colors.GREY_600,
        )
        formula = ft.Text(
            "填写耗材重量和打印时长后，点「计算积分」。",
            size=12,
            color=ft.Colors.GREY_700,
        )

        def calculate(e=None) -> None:
            weight.error = None
            duration.error = None
            try:
                weight_value = float((weight.value or "").strip())
            except ValueError:
                weight.error = "请填写数字"
                weight.update()
                return
            try:
                duration_value = parse_print_duration(duration.value)
                units = print_half_hour_units(duration_value)
                points = calculate_3d_print_points(weight_value, duration_value)
            except ValueError as err:
                duration.error = str(err)
                duration.update()
                return

            weight.update()
            duration.update()
            result.value = f"{db.num_text(points)} 积分"
            result.size = 32
            result.weight = ft.FontWeight.BOLD
            result.color = ft.Colors.BLUE_700
            formula.value = (
                f"{format_print_duration(duration_value)}（{duration_value} 分钟）"
                f" · {db.num_text(weight_value)}g × 10 × {units} 档"
                f" = {db.num_text(points)} 积分"
            )
            result.update()
            formula.update()

        def rule_chip(text: str) -> ft.Container:
            return ft.Container(
                ft.Text(text, size=12, color=ft.Colors.GREY_700),
                padding=ft.Padding.symmetric(horizontal=9, vertical=5),
                border_radius=16,
                bgcolor=ft.Colors.GREY_100,
            )

        rules = ft.Row(
            [
                rule_chip("每克 10 积分"),
                rule_chip("每 30 分钟 ×1 档"),
                rule_chip("不足半小时按 1 档"),
            ],
            spacing=8,
            run_spacing=8,
            wrap=True,
        )
        duration_help = ft.Text(
            "格式：小时:分钟 · 例如 3:00、1:30；不足半小时也按半小时算。",
            size=12,
            color=ft.Colors.GREY_600,
        )
        form = ft.Column(
            [
                weight,
                duration,
                duration_help,
                ft.Row(
                    [
                        ft.Button(
                            "计算积分",
                            icon=ft.Icons.CALCULATE,
                            on_click=calculate,
                        )
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            spacing=10,
            tight=True,
        )
        result_panel = ft.Container(
            ft.Column(
                [
                    ft.Text("应扣积分", size=12, color=ft.Colors.BLUE_800),
                    result,
                    formula,
                ],
                spacing=5,
                tight=True,
            ),
            padding=16,
            border_radius=10,
            bgcolor=ft.Colors.BLUE_50,
            alignment=ft.Alignment.CENTER_LEFT,
        )

        content = ft.Column(
            [
                self._header(
                    "工具栏",
                    "常用计算工具集中在这里；本工具只计算，不会自动扣除积分。",
                ),
                self._section(
                    "3D 打印积分",
                    ft.Column(
                        [
                            rules,
                            ft.ResponsiveRow(
                                [
                                    ft.Container(
                                        form,
                                        col={"xs": 12, "md": 7},
                                    ),
                                    ft.Container(
                                        result_panel,
                                        col={"xs": 12, "md": 5},
                                    ),
                                ],
                                spacing=12,
                                run_spacing=12,
                            ),
                        ],
                        spacing=12,
                    ),
                    action=ft.Row(
                        [
                            ft.Icon(ft.Icons.PRINT_OUTLINED, size=18),
                            ft.Text("工具 01", size=12, color=ft.Colors.BLUE_700),
                        ],
                        spacing=4,
                    ),
                ),
            ],
            spacing=12,
        )
        return content
