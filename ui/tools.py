"""日常小工具：先从 3D 打印积分计算开始。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_CEILING

import flet as ft

import db
from .common import DIALOG_WIDTH, _tf


PRINT_POINTS_PER_GRAM = Decimal("4")
PRINT_POINTS_PER_HALF_HOUR = Decimal("20")


def print_half_hour_units(duration_hours) -> int:
    """每开始一个 30 分钟按一档，不足 30 分钟也按一档。"""
    try:
        duration = Decimal(str(duration_hours))
    except (InvalidOperation, TypeError, ValueError) as err:
        raise ValueError("请填写打印时长") from err
    if duration <= 0:
        raise ValueError("打印时长必须大于 0")
    return int(
        (duration / Decimal("0.5")).to_integral_value(rounding=ROUND_CEILING)
    )


def calculate_3d_print_points(weight_g, duration_hours) -> float:
    """按耗材重量和打印时长分别计分，避免连乘后消耗过高。"""
    try:
        weight = Decimal(str(weight_g))
    except (InvalidOperation, TypeError, ValueError) as err:
        raise ValueError("请填写耗材重量") from err
    if weight <= 0:
        raise ValueError("耗材重量必须大于 0")
    units = print_half_hour_units(duration_hours)
    raw_points = (
        weight * PRINT_POINTS_PER_GRAM
        + Decimal(units) * PRINT_POINTS_PER_HALF_HOUR
    )
    return float(raw_points.to_integral_value(rounding=ROUND_CEILING))


def format_print_hours(duration_hours) -> str:
    """把时长写成简洁的小时数字，例如 1.8 小时。"""
    hours = Decimal(str(duration_hours))
    return f"{hours.normalize():f} 小时"


def parse_print_hours(value) -> Decimal:
    """把 1.8 这样的小时数转成计算结果使用的数字。"""
    text = str(value or "").strip()
    if text.endswith("小时"):
        text = text[:-2].strip()
    try:
        hours = Decimal(text)
    except (InvalidOperation, TypeError, ValueError) as err:
        raise ValueError("请填写小时数，例如 1.8") from err
    if hours <= 0:
        raise ValueError("打印时长必须大于 0")
    return hours


class ToolsMixin:
    """工具栏页面（ClassHoursApp 的一部分）。"""

    async def _open_web_tool(self, url: str) -> None:
        await self.launcher.launch_url(url, web_only_window_name="_blank")

    def _open_web_tool_dialog(self, tool: dict | None = None) -> None:
        if not self.is_admin():
            self._toast("只有管理员可以维护网站工具")
            return
        editing = tool is not None
        title = _tf(
            "网站名称 *",
            (tool or {}).get("title", ""),
            width=DIALOG_WIDTH,
            hint_text="例如 Scratch 官网",
        )
        url = _tf(
            "网址 *",
            (tool or {}).get("url", ""),
            width=DIALOG_WIDTH,
            hint_text="example.com 或 https://example.com",
        )

        def save(e=None) -> None:
            title.error = None
            url.error = None
            try:
                if editing:
                    db.update_web_tool(
                        tool["id"],
                        self._my_user_id() or 0,
                        title.value or "",
                        url.value or "",
                    )
                else:
                    db.create_web_tool(
                        self._my_user_id() or 0,
                        title.value or "",
                        url.value or "",
                    )
            except (PermissionError, ValueError) as err:
                message = str(err)
                if message == "只有管理员可以维护网站工具":
                    self._toast(message)
                elif "名称" in message:
                    title.error = message
                    title.update()
                else:
                    url.error = message
                    url.update()
                return
            self._finish("网站工具已更新" if editing else "网站工具已添加")

        self._show(
            self._dialog(
                "编辑网站工具" if editing else "添加网站工具",
                self._form_column(
                    [
                        title,
                        url,
                        ft.Text(
                            "网址可以省略 https://；所有人都能打开，只有管理员能修改。",
                            size=11,
                            color=ft.Colors.GREY_600,
                        ),
                    ]
                ),
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button(
                        "保存修改" if editing else "添加网站",
                        on_click=save,
                    ),
                ],
            )
        )

    def _web_tool_card(self, tool: dict) -> ft.Container:
        admin_actions = (
            [
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED,
                    tooltip="编辑网站工具",
                    on_click=lambda e, row=tool: self._open_web_tool_dialog(row),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip="删除网站工具",
                    on_click=lambda e, row=tool: self._confirm(
                        "删除网站工具",
                        f"确定删除「{row['title']}」吗？",
                        lambda: db.delete_web_tool(
                            row["id"], self._my_user_id() or 0
                        ),
                        done_text="网站工具已删除",
                    ),
                ),
            ]
            if self.is_admin()
            else []
        )
        return ft.Container(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                ft.Icon(
                                    ft.Icons.LANGUAGE,
                                    size=20,
                                    color=ft.Colors.BLUE_700,
                                ),
                                width=36,
                                height=36,
                                border_radius=8,
                                bgcolor=ft.Colors.BLUE_50,
                                alignment=ft.Alignment.CENTER,
                            ),
                            ft.Text(
                                "网站工具",
                                size=11,
                                color=ft.Colors.GREY_600,
                                expand=True,
                            ),
                            *admin_actions,
                        ],
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        tool["title"],
                        size=16,
                        weight=ft.FontWeight.W_600,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        tool["url"],
                        size=11,
                        color=ft.Colors.GREY_600,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Row(
                        [
                            ft.Button(
                                "打开网站",
                                icon=ft.Icons.OPEN_IN_NEW,
                                on_click=lambda e, row=tool: self.page.run_task(
                                    self._open_web_tool, row["url"]
                                ),
                            )
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=8,
                tight=True,
            ),
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, ft.Colors.GREY_300),
        )

    def _web_tools_view(self) -> ft.Control:
        tools = db.list_web_tools()
        if tools:
            body: ft.Control = ft.ResponsiveRow(
                [
                    ft.Container(
                        self._web_tool_card(tool),
                        col={"xs": 12, "md": 6},
                    )
                    for tool in tools
                ],
                spacing=12,
                run_spacing=12,
            )
        else:
            body = ft.Container(
                ft.Text(
                    (
                        "还没有网站工具。点右上角「添加网站」，每个网址都会成为一张独立工具卡。"
                        if self.is_admin()
                        else "管理员还没有添加网站工具。"
                    ),
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
                padding=14,
                border_radius=10,
                bgcolor=ft.Colors.GREY_50,
            )
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            f"网站工具（{len(tools)}）",
                            size=15,
                            weight=ft.FontWeight.W_600,
                            expand=True,
                        ),
                        ft.Text("全机构共用 · 仅管理员可维护", size=11, color=ft.Colors.GREY_500),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                body,
            ],
            spacing=8,
        )

    def _tools_view(self) -> ft.Control:
        weight = _tf(
            "耗材重量（克）",
            hint_text="例如 12.5",
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
        )
        duration = _tf(
            "打印时长（小时）",
            hint_text="例如 1.8",
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
                duration_value = parse_print_hours(duration.value)
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
                f"{format_print_hours(duration_value)} · "
                f"{db.num_text(weight_value)}g × "
                f"{db.num_text(float(PRINT_POINTS_PER_GRAM))} + {units} 档 × "
                f"{db.num_text(float(PRINT_POINTS_PER_HALF_HOUR))}"
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
                rule_chip(
                    f"每克 {db.num_text(float(PRINT_POINTS_PER_GRAM))} 积分"
                ),
                rule_chip(
                    "每半小时 "
                    f"+{db.num_text(float(PRINT_POINTS_PER_HALF_HOUR))} 积分"
                ),
                rule_chip("不足半小时按 1 档"),
                rule_chip("结果向上取整"),
            ],
            spacing=8,
            run_spacing=8,
            wrap=True,
        )
        duration_help = ft.Text(
            "直接填小时数 · 例如 1.8、2.5；不足半小时也按半小时算。",
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
                    "3D 打印计算器和全机构共用的网站工具。",
                    (
                        [
                            ft.Button(
                                "添加网站",
                                icon=ft.Icons.ADD,
                                on_click=lambda e: self._open_web_tool_dialog(),
                            )
                        ]
                        if self.is_admin()
                        else None
                    ),
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
                self._web_tools_view(),
            ],
            spacing=12,
        )
        return content
