"""课时账户流水。"""

from __future__ import annotations

from datetime import date

import flet as ft

import db
from .common import DIALOG_WIDTH, HOUR_MODE, _chip, _date_text, _dd, _hour_mode_opts, _opts, _tf


class HoursMixin:
    """课时账户流水（ClassHoursApp 的一部分）。"""

    def _open_hour_ledger(self, student_id: int, hour_type_id: int | None) -> None:
        """某个课时账户的每一笔：能看、能改、能删。"""
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
        admin = self.is_admin()
        items = [self._hour_tx_row(t, student_id, admin) for t in rows]
        if not items:
            items = [
                ft.Text(
                    "这个账户还没有流水。点下面「记一笔」加课时。",
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
                    "手记的充值／扣减可以直接改或删；"
                    "缴费产生的去「缴费」页改，上课扣的去课次里改。",
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
        if admin:
            actions.insert(
                0,
                ft.Button(
                    "记一笔",
                    icon=ft.Icons.ADD,
                    on_click=lambda e: self._open_hours_dialog(
                        student_id, account["hour_type_id"]
                    ),
                ),
            )
        self._show(self._dialog(f"{account['name']} · 课时明细", body, actions))

    def _hour_tx_row(self, t: dict, student_id: int, admin: bool) -> ft.Control:
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
        if admin and db.is_manual_hour_transaction(t):
            controls.append(
                ft.IconButton(
                    ft.Icons.EDIT,
                    tooltip="改这一笔",
                    icon_size=18,
                    on_click=lambda e, row=t: self._open_hours_dialog(
                        student_id, row["hour_type_id"], row
                    ),
                )
            )
            controls.append(
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip="删这一笔",
                    icon_size=18,
                    on_click=lambda e, row=t: self._confirm(
                        "删掉这一笔",
                        f"确定删掉「{_date_text(row['happened_on'])} "
                        f"{db.num_text(row['change'])} 课时」这一笔吗？删了课时会跟着变。",
                        lambda: db.delete_hour_transaction(row["id"]),
                        done_text="这一笔删掉了",
                    ),
                )
            )
        return ft.Row(controls, spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _open_hours_dialog(
        self,
        student_id: int,
        hour_type_id: int | None,
        transaction: dict | None = None,
    ) -> None:
        accounts = db.get_accounts(student_id)
        if not accounts:
            self._toast("还没有课时账户")
            return
        editing = transaction is not None
        change = float(transaction["change"] or 0) if editing else 0.0
        acc_dd = _dd(
            "课时账户",
            _opts([(a["hour_type_id"], a["name"]) for a in accounts]),
            value=str(
                (transaction["hour_type_id"] if editing else hour_type_id)
                or accounts[0]["hour_type_id"]
            ),
            width=DIALOG_WIDTH,
        )
        mode_dd = _dd(
            "类型",
            _hour_mode_opts(),
            value="扣减" if editing and change < 0 else "充值",
            width=DIALOG_WIDTH,
        )
        amount = _tf(
            "数量（课时）",
            db.num_text(abs(change)) if editing else "",
            width=DIALOG_WIDTH,
            keyboard_type=ft.KeyboardType.NUMBER,
            hint_text="例如 24 或 1.5",
        )
        day = _tf(
            "日期",
            transaction["happened_on"] if editing else date.today().isoformat(),
            width=DIALOG_WIDTH,
        )
        note = _tf(
            "备注",
            transaction["note"] if editing else "",
            width=DIALOG_WIDTH,
            hint_text="例如：缴费 3000 元",
        )

        def save(e):
            try:
                value = float((amount.value or "").strip())
            except ValueError:
                amount.error = "请填数字"
                amount.update()
                return
            if value <= 0:
                amount.error = "数量要大于 0"
                amount.update()
                return
            sign = dict(HOUR_MODE)[mode_dd.value or "充值"]
            if editing:
                db.update_hour_transaction(
                    transaction["id"],
                    int(acc_dd.value),
                    value * sign,
                    (day.value or "").strip(),
                    note.value or "",
                )
                target = int(acc_dd.value)
                self._close_dialogs(2)
                self.render()
                self._open_hour_ledger(student_id, target)
                self._toast("这一笔改好了")
                return
            db.add_hours(
                student_id,
                int(acc_dd.value),
                value * sign,
                kind=mode_dd.value or "充值",
                happened_on=(day.value or "").strip(),
                note=note.value or "",
                source_type="manual",
            )
            self._finish("课时已更新")

        body = self._form_column([acc_dd, mode_dd, amount, day, note])
        actions = [ft.TextButton("取消", on_click=self._close)]
        if editing:
            actions.append(
                ft.TextButton(
                    "删掉这一笔",
                    icon=ft.Icons.DELETE_OUTLINE,
                    on_click=lambda e: self._confirm(
                        "删掉这一笔",
                        "确定删掉这一笔吗？课时会跟着变。",
                        lambda: db.delete_hour_transaction(transaction["id"]),
                        done_text="这一笔删掉了",
                        after=lambda: self._close_dialogs(2),
                    ),
                )
            )
        actions.append(ft.Button("保存", on_click=save))
        self._show(
            self._dialog(
                "改这一笔" if editing else "调整课时",
                body,
                actions,
            )
        )

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
