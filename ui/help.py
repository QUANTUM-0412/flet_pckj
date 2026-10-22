"""学生帮助请求与老师处理。"""

from __future__ import annotations

import flet as ft

import db
from .common import DIALOG_WIDTH, _chip, _date_text, _tf


class HelpMixin:
    """学生提交问题，老师或管理员处理帮助请求。"""

    def _help_view(self) -> ft.Control:
        tickets = db.list_help_tickets()
        if not self.is_admin():
            tickets = [
                ticket
                for ticket in tickets
                if self._can_manage_student(ticket["student_id"])
            ]
        items = [
            self._help_ticket_card(ticket, staff=True)
            for ticket in tickets
        ] or [
            self._card(
                ft.Text(
                    "还没有帮助请求。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            )
        ]
        pending = sum(ticket["status"] == "待处理" for ticket in tickets)
        return ft.Column(
            [
                self._header(
                    "帮助请求",
                    f"待处理 {pending} 条 · 共 {len(tickets)} 条",
                ),
                *items,
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _student_help_view(self) -> ft.Control:
        student = self._student_profile()
        if student is None:
            return ft.Text("账号没有绑定有效学员。", color=ft.Colors.RED_600)
        tickets = db.list_help_tickets(student_id=student["id"])
        items = [
            self._help_ticket_card(ticket, staff=False)
            for ticket in tickets
        ] or [
            self._card(
                ft.Text(
                    "还没有提交过问题。学习中遇到困难时，点右上角「提交问题」。"
                    f"每次请求消耗 {db.num_text(db.help_request_cost())} 积分。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            )
        ]
        return ft.Column(
            [
                self._header(
                    "帮助请求",
                    f"我的问题 {len(tickets)} 条",
                    [
                        ft.Button(
                            "提交问题",
                            icon=ft.Icons.ADD_COMMENT,
                            on_click=lambda e: self._open_help_ticket_dialog(),
                        )
                    ],
                ),
                *items,
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _help_ticket_card(self, ticket: dict, *, staff: bool) -> ft.Container:
        status_color = {
            "待处理": ft.Colors.ORANGE_700,
            "已完成": ft.Colors.GREEN_700,
            "已拒绝": ft.Colors.RED_600,
        }.get(ticket["status"], ft.Colors.GREY_600)
        bits = [
            ft.Text(ticket["subject"], size=14, weight=ft.FontWeight.W_600),
            _chip(ticket["status"], status_color),
        ]
        details: list[ft.Control] = [
            ft.Row(bits, spacing=6, wrap=True),
            ft.Text(
                f"{ticket['student_name']} · {_date_text(ticket['created_at'])}",
                size=11,
                color=ft.Colors.GREY_600,
            ),
            ft.Text(ticket["content"], size=13, color=ft.Colors.GREY_800),
            ft.Text(
                f"消耗 {db.num_text(ticket.get('cost_points') or 0)} 积分",
                size=11,
                color=ft.Colors.GREY_600,
            ),
        ]
        if ticket.get("reply"):
            details.append(
                ft.Container(
                    ft.Column(
                        [
                            ft.Text(
                                f"完成说明 · {ticket.get('replier_name') or ''}",
                                size=11,
                                color=ft.Colors.BLUE_700,
                            ),
                            ft.Text(ticket["reply"], size=13),
                        ],
                        spacing=3,
                        tight=True,
                    ),
                    padding=10,
                    border_radius=8,
                    bgcolor=ft.Colors.BLUE_50,
                )
            )
        if ticket.get("rejected_reason"):
            details.append(
                ft.Container(
                    ft.Column(
                        [
                            ft.Text(
                                f"拒绝理由 · {ticket.get('replier_name') or ''}",
                                size=11,
                                color=ft.Colors.RED_600,
                            ),
                            ft.Text(ticket["rejected_reason"], size=13),
                            ft.Text(
                                "积分已退回",
                                size=11,
                                color=ft.Colors.GREEN_700,
                            ),
                        ],
                        spacing=3,
                        tight=True,
                    ),
                    padding=10,
                    border_radius=8,
                    bgcolor=ft.Colors.RED_50,
                )
            )
        actions: list[ft.Control] = []
        if (
            staff
            and ticket["status"] == "待处理"
            and self._can_manage_student(ticket["student_id"])
        ):
            actions.append(
                ft.TextButton(
                    "完成",
                    icon=ft.Icons.CHECK,
                    on_click=lambda e, row=ticket: self._open_help_complete_dialog(row),
                )
            )
            actions.append(
                ft.TextButton(
                    "拒绝",
                    icon=ft.Icons.CLOSE,
                    on_click=lambda e, row=ticket: self._open_help_reject_dialog(row),
                )
            )
        if actions:
            details.append(
                ft.Row(
                    actions,
                    alignment=ft.MainAxisAlignment.END,
                    spacing=4,
                )
            )
        return self._card(ft.Column(details, spacing=8))

    def _open_help_ticket_dialog(self) -> None:
        student = self._student_profile()
        if student is None:
            return
        subject = _tf("问题标题 *", "", width=DIALOG_WIDTH)
        content = _tf(
            "需要什么帮助 *",
            "",
            width=DIALOG_WIDTH,
            multiline=True,
            min_lines=4,
            max_lines=8,
        )
        cost = db.help_request_cost()

        def save(e):
            try:
                db.create_help_ticket(
                    student["id"],
                    self._my_user_id(),
                    subject.value or "",
                    content.value or "",
                )
            except ValueError as err:
                if "标题" in str(err):
                    subject.error = str(err)
                    subject.update()
                else:
                    content.error = str(err)
                    content.update()
                return
            self._finish("问题已提交给老师")

        body = self._form_column(
            [
                ft.Text(
                    f"提交后立即扣除 {db.num_text(cost)} 积分；"
                    "老师拒绝时积分会自动退回，完成后不退回。",
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
                subject,
                content,
            ]
        )
        self._show(
            self._dialog(
                "提交帮助请求",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("提交", on_click=save),
                ],
            )
        )

    def _open_help_complete_dialog(self, ticket: dict) -> None:
        result = _tf(
            "完成说明 *",
            "",
            width=DIALOG_WIDTH,
            multiline=True,
            min_lines=4,
            max_lines=8,
        )

        def save(e):
            try:
                db.complete_help_ticket(
                    ticket["id"],
                    result.value or "",
                    self._my_user_id(),
                )
            except ValueError as err:
                result.error = str(err)
                result.update()
                return
            self._finish("帮助请求已完成")

        self._show(
            self._dialog(
                "完成帮助请求",
                self._form_column([result]),
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("完成", on_click=save),
                ],
            )
        )

    def _open_help_reject_dialog(self, ticket: dict) -> None:
        reason = _tf(
            "拒绝理由 *",
            "",
            width=DIALOG_WIDTH,
            multiline=True,
            min_lines=4,
            max_lines=8,
        )

        def save(e):
            try:
                db.reject_help_ticket(
                    ticket["id"],
                    reason.value or "",
                    self._my_user_id(),
                )
            except ValueError as err:
                reason.error = str(err)
                reason.update()
                return
            self._finish("请求已拒绝，积分已退回")

        self._show(
            self._dialog(
                "拒绝帮助请求",
                self._form_column(
                    [
                        ft.Text(
                            "拒绝必须填写理由，提交后本次消耗的积分自动退回。",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                        reason,
                    ]
                ),
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("确认拒绝", on_click=save),
                ],
            )
        )


__all__ = ["HelpMixin"]
