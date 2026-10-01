"""缴费。"""

from __future__ import annotations

from datetime import date

import flet as ft

import db
from .common import DIALOG_WIDTH, _date_text, _dd, _opts, _tf


class PaymentsMixin:
    """缴费（ClassHoursApp 的一部分）。"""

    def _payments_view(self) -> ft.Column:
        payments = db.list_payments()
        self._payment_items_map = db.items_by_payment([p["id"] for p in payments])
        month = date.today().strftime("%Y-%m")
        month_total = db.income_total(month=month)
        total = db.income_total()
        cards = [self._payment_card(p) for p in payments]
        if not cards:
            cards = [
                self._card(
                    ft.Column(
                        [
                            ft.Icon(ft.Icons.PAYMENTS, size=36, color=ft.Colors.GREY_400),
                            ft.Text("还没有缴费记录", color=ft.Colors.GREY_600),
                            ft.Text(
                                "点右上角「记一笔」，课时会自动加到孩子的账户上。",
                                size=12,
                                color=ft.Colors.GREY_500,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    )
                )
            ]
        return ft.Column(
            [
                self._header(
                    "缴费记录",
                    f"本月 {db.num_text(month_total)} 元 · 一共 {db.num_text(total)} 元",
                    (
                        [
                            ft.Button(
                                "记一笔",
                                icon=ft.Icons.ADD,
                                on_click=lambda e: self._open_payment_dialog(),
                            )
                        ]
                        if self.is_admin()
                        else []
                    ),
                ),
                *cards,
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _payment_card(self, p: dict) -> ft.Container:
        detail_bits = self._payment_item_bits(p)
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(_date_text(p["paid_on"]), size=12, color=ft.Colors.GREY_600),
                            ft.Text(p["student_name"], size=15, weight=ft.FontWeight.W_600),
                            ft.Text(" · ".join(detail_bits) or "—", size=12, color=ft.Colors.GREY_600),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Text(
                        f"{db.num_text(p['amount'])} 元",
                        size=16,
                        weight=ft.FontWeight.W_600,
                    ),
                    *(
                        [
                            ft.IconButton(
                                ft.Icons.EDIT,
                                tooltip="编辑",
                                icon_size=18,
                                on_click=lambda e, pay=p: self._open_payment_dialog(pay),
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                tooltip="删除",
                                icon_size=18,
                                on_click=lambda e, pay=p: self._confirm(
                                    "删除这笔缴费",
                                    f"确定删除「{pay['student_name']} "
                                    f"{db.num_text(pay['amount'])} 元」这笔吗？对应的课时会一起扣掉。",
                                    lambda: db.delete_payment(pay["id"]),
                                ),
                            ),
                        ]
                        if self.is_admin()
                        else []
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, ft.Colors.GREY_300),
        )

    def _payment_item_bits(self, p: dict) -> list[str]:
        items = getattr(self, "_payment_items_map", {}).get(p["id"])
        if items is None:
            items = db.list_payment_items(p["id"])
        bits = []
        for item in items:
            text = f"{item['hour_type_name'] or '课时'} {db.num_text(item['hours'])} 课时"
            if not item["amount"]:
                text += "（送）"
            bits.append(text)
        if p["note"]:
            bits.append(p["note"])
        return bits

    def _open_payment_dialog(self, payment: dict | None = None, student_id: int | None = None) -> None:
        students = db.list_students()
        if not students:
            self._toast("先添加学员，再来记缴费")
            return
        hour_types = db.list_hour_types()
        levels = db.list_levels()
        editing = payment is not None

        student_dd = _dd(
            "孩子",
            _opts(
                [
                    (s["id"], s["name"] + (f"（{s['grade']}）" if s["grade"] else ""))
                    for s in students
                ]
            ),
            value=str(payment["student_id"] if editing else (student_id or students[0]["id"])),
            width=DIALOG_WIDTH,
        )
        day = _tf("日期", payment["paid_on"] if editing else date.today().isoformat(), width=DIALOG_WIDTH)
        note = _tf("备注", payment["note"] if editing else "", width=DIALOG_WIDTH)
        rows_holder = ft.Column(spacing=8, tight=True)
        rows: list[dict] = []
        total_text = ft.Text("", size=13, weight=ft.FontWeight.W_600)

        def _number(field) -> float:
            try:
                return float((field.value or "0").strip() or 0)
            except ValueError:
                raise ValueError("数字填得不对")

        def refresh_total(update=True, *_):
            total = 0.0
            for row in rows:
                try:
                    total += _number(row["amount"])
                except ValueError:
                    pass
            total_text.value = f"合计 {db.num_text(total)} 元"
            if update:
                total_text.update()

        def add_row(hour_type_id=None, hours="", amount="", level_id=None, update=True):
            type_dd = _dd(
                "课时类型",
                _opts([(h["id"], h["name"]) for h in hour_types]),
                value=str(hour_type_id or hour_types[0]["id"]),
                width=96,
            )
            level_dd = _dd(
                "报的等级",
                [ft.DropdownOption(key="", text="不指定")]
                + _opts([(l["id"], db.level_full_name(l)) for l in levels]),
                value=str(level_id) if level_id else "",
                width=148,
            )
            hours_f = _tf(
                "数量（课时）",
                hours,
                expand=True,
                keyboard_type=ft.KeyboardType.NUMBER,
                hint_text="例如 24",
            )
            amount_f = _tf(
                "金额（元）",
                amount,
                expand=True,
                keyboard_type=ft.KeyboardType.NUMBER,
                hint_text="0 就是赠送",
                on_change=refresh_total,
            )
            row = {
                "type": type_dd,
                "level": level_dd,
                "hours": hours_f,
                "amount": amount_f,
            }

            def remove(e):
                if len(rows) <= 1:
                    self._toast("至少留一行")
                    return
                rows.remove(row)
                rows_holder.controls.remove(box)
                rows_holder.update()
                refresh_total()

            box = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                type_dd,
                                level_dd,
                                ft.IconButton(
                                    ft.Icons.CLOSE,
                                    tooltip="去掉这一行",
                                    icon_size=18,
                                    on_click=remove,
                                ),
                            ],
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row([hours_f, amount_f], spacing=8),
                    ],
                    spacing=6,
                ),
                padding=10,
                border_radius=10,
                bgcolor=ft.Colors.GREY_50,
            )
            rows.append(row)
            rows_holder.controls.append(box)
            if update:
                rows_holder.update()
                refresh_total()
            return row

        if editing:
            for item in db.list_payment_items(payment["id"]):
                add_row(
                    item["hour_type_id"],
                    db.num_text(item["hours"]),
                    db.num_text(item["amount"]),
                    item["level_id"],
                    update=False,
                )
        else:
            add_row("", "", "", None, update=False)

        def collect() -> list[dict]:
            items = []
            for row in rows:
                try:
                    hours_value = _number(row["hours"])
                    amount_value = _number(row["amount"])
                except ValueError:
                    self._toast("数量或金额填得不对")
                    return []
                if hours_value <= 0:
                    continue
                items.append(
                    {
                        "hour_type_id": int(row["type"].value),
                        "level_id": int(row["level"].value)
                        if (row["level"].value or "").strip()
                        else None,
                        "hours": hours_value,
                        "amount": amount_value,
                    }
                )
            return items

        def save(e):
            try:
                date.fromisoformat((day.value or "").strip())
            except ValueError:
                day.error = "日期写成 2026-09-05 这样"
                day.update()
                return
            items = collect()
            if not items:
                self._toast("至少填一行的课时数")
                return
            args = (
                int(student_dd.value),
                (day.value or "").strip(),
                items,
                note.value or "",
            )
            if editing:
                db.update_payment(payment["id"], *args)
                self._finish("缴费记录已更新")
            else:
                db.create_payment(*args)
                self._finish("缴费记好了，课时已经加上")

        # 弹窗还没挂到页面上，先只算数值，别急着刷新
        refresh_total(False)
        body = self._form_column(
            [
                student_dd,
                day,
                ft.Text(
                    "这次买的课时（可以加多行：买的、送的都记上；"
                    "选上等级就会顺手建好「报名课程」）",
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
                rows_holder,
                ft.Row(
                    [ft.TextButton("+ 加一行", icon=ft.Icons.ADD, on_click=lambda e: add_row())],
                    alignment=ft.MainAxisAlignment.END,
                ),
                total_text,
                note,
            ]
        )
        self._show(
            self._dialog(
                "编辑缴费" if editing else "记一笔缴费",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )

    def _student_lessons_card(self, s: dict) -> ft.Container:
        """这个孩子上过哪些课。"""
        rows = db.student_recent_lessons(s["id"], limit=10)
        items = []
        for r in rows:
            present = int(r["attendance"] or 0)
            if present:
                points = (
                    1 + int(r["discipline"] or 0) + int(r["performance"] or 0)
                ) * 10 + float(r["bonus"] or 0)
                hours = float(r["minutes"] or 0) / 60 if r["class_type_deduct"] else 0
                state = ft.Text("出勤", size=12, color=ft.Colors.GREEN_700)
            else:
                points = 0
                hours = 0
                state = ft.Text("请假", size=12, color=ft.Colors.ORANGE_700)
            tail = []
            if points:
                tail.append(f"+{db.num_text(points)} 分")
            if hours:
                tail.append(f"扣 {db.num_text(hours)} 课时")
            if present and not hours:
                tail.append("不扣课时")
            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        f"{_date_text(r['lesson_date'])} {r['start_time']}",
                                        size=13,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    ft.Text(
                                        f"{db.lesson_label(r)}",
                                        size=12,
                                        color=ft.Colors.GREY_600,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Column(
                                [
                                    state,
                                    ft.Text(
                                        " · ".join(tail) or "—",
                                        size=11,
                                        color=ft.Colors.GREY_600,
                                    ),
                                ],
                                spacing=2,
                                horizontal_alignment=ft.CrossAxisAlignment.END,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        if not items:
            items = [
                ft.Text(
                    "还没有上过课。到「上课记录」里点他的名字加上就行。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            ]
        return self._section(f"上课记录（最近 {len(rows)} 次）", ft.Column(items, spacing=10))

    def _payments_card(self, s: dict) -> ft.Container:
        admin = self.is_admin()
        payments = db.list_payments(s["id"], limit=5)
        self._payment_items_map = db.items_by_payment([p["id"] for p in payments])
        total = db.income_total(student_id=s["id"])
        items = []
        for p in payments:
            bits = self._payment_item_bits(p)
            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(_date_text(p["paid_on"]), size=13, weight=ft.FontWeight.W_600),
                                    ft.Text(" · ".join(bits) or "—", size=12, color=ft.Colors.GREY_600),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Text(f"{db.num_text(p['amount'])} 元", size=14, weight=ft.FontWeight.W_600),
                            *(
                                [
                                    ft.IconButton(
                                        ft.Icons.DELETE_OUTLINE,
                                        tooltip="删除",
                                        icon_size=18,
                                        on_click=lambda e, pay=p: self._confirm(
                                            "删除这笔缴费",
                                            f"确定删除这笔 {db.num_text(pay['amount'])} 元吗？"
                                            "对应的课时会一起扣掉。",
                                            lambda: db.delete_payment(pay["id"]),
                                        ),
                                    )
                                ]
                                if admin
                                else []
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        if not items:
            items = [ft.Text("还没交过费", size=12, color=ft.Colors.GREY_600)]
        return self._section(
            f"缴费记录（累计 {db.num_text(total)} 元）",
            ft.Column(items, spacing=10),
            action=(
                ft.Button(
                    "记一笔",
                    icon=ft.Icons.ADD,
                    on_click=lambda e: self._open_payment_dialog(None, s["id"]),
                )
                if admin
                else None
            ),
        )
