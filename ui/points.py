"""积分：学员页的积分明细卡片 + 兑换对话框。

（积分榜和兑换记录清单在"报表"页里，这个模块只管跟某个孩子相关的部分。）
"""

from __future__ import annotations

from datetime import date

import flet as ft

import db
from .common import DIALOG_WIDTH, _date_text, _dd, _opts, _tf


class PointsMixin:
    """积分兑换（ClassHoursApp 的一部分）。"""

    def _open_redemption_dialog(self, redemption: dict | None = None, student_id: int | None = None) -> None:
        balances = db.points_balances()
        if not balances:
            self._toast("先添加学员，再来记兑换")
            return
        editing = redemption is not None
        names = {b["id"]: b for b in balances}
        student_dd = _dd(
            "孩子",
            _opts(
                [
                    (b["id"], b["name"] + (f"（{b['grade']}）" if b["grade"] else ""))
                    for b in balances
                ]
            ),
            value=str(redemption["student_id"] if editing else (student_id or balances[0]["id"])),
            width=DIALOG_WIDTH,
        )
        first = names.get(int(student_dd.value or 0))
        balance_hint = ft.Text(
            f"他现在有 {db.num_text(first['points'])} 分" if first else "",
            size=12,
            color=ft.Colors.GREY_600,
        )
        day = _tf(
            "日期",
            redemption["happened_on"] if editing else date.today().isoformat(),
            width=DIALOG_WIDTH,
        )
        points = _tf(
            "扣多少分",
            db.num_text(abs(float(redemption["change"]))) if editing else "",
            width=DIALOG_WIDTH,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        note = _tf(
            "换了什么（可不填）",
            redemption["note"] if editing else "",
            width=DIALOG_WIDTH,
        )

        def refresh_hint(e=None):
            info = names.get(int(student_dd.value or 0))
            if info:
                balance_hint.value = f"他现在有 {db.num_text(info['points'])} 分"
                balance_hint.update()

        student_dd.on_select = refresh_hint

        def save(e):
            try:
                value = float((points.value or "").strip())
            except ValueError:
                points.error = "请填数字"
                points.update()
                return
            if value <= 0:
                points.error = "要大于 0"
                points.update()
                return
            try:
                date.fromisoformat((day.value or "").strip())
            except ValueError:
                day.error = "日期写成 2026-09-05 这样"
                day.update()
                return
            args = (
                int(student_dd.value),
                value,
                (day.value or "").strip(),
                note.value or "",
            )
            if editing:
                db.update_redemption(redemption["id"], *args)
                self._finish("兑换记录已更新")
            else:
                db.add_redemption(*args)
                self._finish("兑换记好了，积分已经扣掉")

        body = self._form_column([student_dd, balance_hint, day, points, note])
        self._show(
            self._dialog(
                "编辑兑换" if editing else "记一笔兑换",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )

    def _points_card(self, s: dict) -> ft.Container:
        points = db.student_points(s["id"])
        rows = db.list_point_transactions(s["id"], limit=8)
        items = []
        for t in rows:
            change = float(t["change"] or 0)
            if change > 0:
                color = ft.Colors.GREEN_700
            elif change < 0:
                color = ft.Colors.RED_600
            else:
                color = ft.Colors.GREY_500
            text = f"{t['kind']}"
            if t["note"]:
                text += f" · {t['note']}"
            items.append(
                ft.Row(
                    [
                        ft.Text(_date_text(t["happened_on"]), size=12, color=ft.Colors.GREY_600),
                        ft.Text(text, size=12, color=ft.Colors.GREY_700, expand=True),
                        ft.Text(
                            f"{'+' if change > 0 else ''}{db.num_text(change)}",
                            size=14,
                            weight=ft.FontWeight.W_600,
                            color=color,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        if not items:
            items = [ft.Text("还没有积分记录", size=12, color=ft.Colors.GREY_600)]
        return self._section(
            f"积分明细（现在 {db.num_text(points)} 分）",
            ft.Column(items, spacing=8),
            action=ft.Button(
                "兑换",
                icon=ft.Icons.REDEEM,
                on_click=lambda e: self._open_redemption_dialog(None, s["id"]),
            ),
        )
