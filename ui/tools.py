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


class ToolsMixin:
    """工具栏页面（ClassHoursApp 的一部分）。"""

    def _tools_view(self) -> ft.Column:
        weight = _tf(
            "耗材重量（克）",
            hint_text="例如 12.5",
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
        )
        duration = _tf(
            "打印时长（分钟）",
            hint_text="例如 70",
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
        )
        result = ft.Text(
            "—",
            size=32,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_700,
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
                duration_value = float((duration.value or "").strip())
            except ValueError:
                duration.error = "请填写数字"
                duration.update()
                return
            try:
                units = print_half_hour_units(duration_value)
                points = calculate_3d_print_points(weight_value, duration_value)
            except ValueError as err:
                duration.error = str(err)
                duration.update()
                return

            weight.update()
            duration.update()
            result.value = f"{db.num_text(points)} 积分"
            formula.value = (
                f"{db.num_text(weight_value)} 克 × 10 积分 × {units} 个半小时"
                f" = {db.num_text(points)} 积分"
            )
            result.update()
            formula.update()

        fields = ft.ResponsiveRow(
            [
                ft.Container(weight, col={"xs": 12, "md": 5}),
                ft.Container(duration, col={"xs": 12, "md": 5}),
                ft.Container(
                    ft.Button(
                        "计算积分",
                        icon=ft.Icons.CALCULATE,
                        on_click=calculate,
                    ),
                    col={"xs": 12, "md": 2},
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding.only(top=12),
                ),
            ],
            spacing=8,
            run_spacing=8,
        )

        rules = ft.ResponsiveRow(
            [
                ft.Container(
                    ft.Column(
                        [
                            ft.Text("耗材", size=11, color=ft.Colors.GREY_600),
                            ft.Text("每克 10 积分", weight=ft.FontWeight.W_600),
                        ],
                        spacing=2,
                        tight=True,
                    ),
                    col={"xs": 12, "md": 4},
                    padding=10,
                    border_radius=8,
                    bgcolor=ft.Colors.GREY_50,
                ),
                ft.Container(
                    ft.Column(
                        [
                            ft.Text("时长倍率", size=11, color=ft.Colors.GREY_600),
                            ft.Text("每 30 分钟 1 档", weight=ft.FontWeight.W_600),
                        ],
                        spacing=2,
                        tight=True,
                    ),
                    col={"xs": 12, "md": 4},
                    padding=10,
                    border_radius=8,
                    bgcolor=ft.Colors.GREY_50,
                ),
                ft.Container(
                    ft.Column(
                        [
                            ft.Text("不足半小时", size=11, color=ft.Colors.GREY_600),
                            ft.Text("也按 1 个半小时算", weight=ft.FontWeight.W_600),
                        ],
                        spacing=2,
                        tight=True,
                    ),
                    col={"xs": 12, "md": 4},
                    padding=10,
                    border_radius=8,
                    bgcolor=ft.Colors.GREY_50,
                ),
            ],
            spacing=8,
            run_spacing=8,
        )

        return ft.Column(
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
                            fields,
                            ft.Container(
                                ft.Column(
                                    [
                                        ft.Text(
                                            "本次应扣",
                                            size=12,
                                            color=ft.Colors.BLUE_800,
                                        ),
                                        result,
                                        formula,
                                    ],
                                    spacing=4,
                                    tight=True,
                                ),
                                padding=14,
                                border_radius=10,
                                bgcolor=ft.Colors.BLUE_50,
                            ),
                            ft.Text(
                                "计算规则：耗材重量（克）× 10 × 半小时档数。"
                                "例如 10 克打印 61 分钟，按 3 档计算，共 300 积分。",
                                size=12,
                                color=ft.Colors.GREY_600,
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
