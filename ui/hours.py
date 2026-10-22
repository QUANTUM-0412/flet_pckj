"""课时账户流水（只读，课时统一从缴费页增加）。"""

from __future__ import annotations

import flet as ft

import db
from .common import _chip, _date_text


class HoursMixin:
    """课时账户流水（ClassHoursApp 的一部分）。"""

    def _open_hour_ledger(self, student_id: int, hour_type_id: int | None) -> None:
        """某个课时账户的每一笔，只能查看。"""
        accounts = db.get_accounts(student_id)
        account = next(
            (a for a in accounts if a["hour_type_id"] == hour_type_id), accounts[0] if accounts else None
        )
        if account is None:
            self._toast("没有这个课时账户")
            return
        rows = [
            t
            for t in db.list_hour_transactions(student_id, limit=300)
            if t["hour_type_id"] == account["hour_type_id"]
        ]
        items = [self._hour_tx_row(t) for t in rows]
        if not items:
            items = [
                ft.Text(
                    "这个账户还没有流水。增加课时请到「缴费」页记一笔。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            ]
        body = ft.Column(
            [
                ft.Text(
                    f"现在 {db.num_text(account['balance'])} 课时"
                    + ("（不限课时）" if account["unlimited"] else ""),
                    size=13,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Text(
                    "这里的流水只供查看；课时统一从「缴费」页增加，"
                    "缴费产生的记录去「缴费」页修改，上课扣课时去课次里修改。",
                    size=11,
                    color=ft.Colors.GREY_600,
                ),
                ft.Container(
                    ft.Column(items, spacing=8, tight=True, scroll=ft.ScrollMode.AUTO),
                    height=300,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                    padding=8,
                ),
            ],
            spacing=8,
            tight=True,
        )
        actions = [ft.TextButton("关闭", on_click=self._close)]
        self._show(self._dialog(f"{account['name']} · 课时明细", body, actions))

    def _hour_tx_row(self, t: dict) -> ft.Control:
        change = float(t["change"] or 0)
        sign = "+" if change > 0 else ""
        source = t["source_type"] or "manual"
        if source.startswith("payment"):
            tag = _chip("缴费", ft.Colors.BLUE_600)
        elif source == "lesson":
            tag = _chip("上课", ft.Colors.GREEN_700)
        else:
            tag = _chip("手记", ft.Colors.GREY_600)
        controls: list[ft.Control] = [
            ft.Column(
                [
                    ft.Row(
                        [ft.Text(_date_text(t["happened_on"]), size=12, color=ft.Colors.GREY_600), tag],
                        spacing=6,
                    ),
                    ft.Text(
                        t["note"] or (t["hour_type_name"] or ""),
                        size=12,
                        color=ft.Colors.GREY_700,
                    ),
                ],
                spacing=2,
                expand=True,
            ),
            ft.Text(
                f"{sign}{db.num_text(change)}",
                size=14,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.GREEN_700 if change > 0 else ft.Colors.RED_600,
            ),
        ]
        return ft.Row(controls, spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _toggle_unlimited(self, student_id: int, hour_type_id: int, value: bool) -> None:
        current = next(
            (a for a in db.get_accounts(student_id) if a["hour_type_id"] == hour_type_id),
            None,
        )
        want = 1 if value else 0
        if current is not None and current["unlimited"] == want:
            # 有的控件在刚创建时会自己发一次事件，值没变就不用理会
            return
        db.set_unlimited(student_id, hour_type_id, bool(value))
        self.render()
