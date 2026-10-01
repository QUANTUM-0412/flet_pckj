"""通用零件（卡片、对话框、提示）。"""

from __future__ import annotations

import flet as ft

from .common import DIALOG_WIDTH


class WidgetsMixin:
    """通用零件（卡片、对话框、提示）（ClassHoursApp 的一部分）。"""

    def _header(self, title: str, subtitle: str = "", actions=None) -> ft.Row:
        lines = [ft.Text(title, size=20, weight=ft.FontWeight.BOLD)]
        if subtitle:
            lines.append(ft.Text(subtitle, size=12, color=ft.Colors.GREY_600))
        return ft.Row(
            [ft.Column(lines, spacing=2, expand=True), *(actions or [])],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )

    def _card(self, content, **kw) -> ft.Container:
        return ft.Container(
            content=content,
            padding=14,
            border_radius=12,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, ft.Colors.GREY_300),
            **kw,
        )

    def _section(self, title: str, body, action=None) -> ft.Container:
        head = ft.Row(
            [
                ft.Text(title, size=15, weight=ft.FontWeight.W_600, expand=True),
                *( [action] if action else [] ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return self._card(ft.Column([head, body], spacing=12))

    def _metric(self, label: str, value: str, color=None) -> ft.Column:
        return ft.Column(
            [
                ft.Text(label, size=11, color=ft.Colors.GREY_600),
                ft.Text(value, size=16, weight=ft.FontWeight.W_600, color=color),
            ],
            spacing=1,
            tight=True,
        )

    def _dialog(self, title: str, body, actions) -> ft.AlertDialog:
        return ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Container(body, width=DIALOG_WIDTH),
            actions=actions,
        )

    def _show(self, dlg) -> None:
        self.page.show_dialog(dlg)
        self.page.update()

    def _close(self, e=None) -> None:
        self.page.pop_dialog()
        self.page.update()

    def _toast(self, message: str) -> None:
        self.page.show_dialog(ft.SnackBar(content=ft.Text(message)))
        self.page.update()

    def _finish(self, message: str) -> None:
        """关掉对话框、刷新页面、弹一句提示。"""
        self.page.pop_dialog()
        self.render()
        self._toast(message)

    def _form_column(self, controls, scroll: bool = False) -> ft.Column:
        return ft.Column(
            controls,
            spacing=10,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.AUTO if scroll else None,
        )

    def _confirm(
        self,
        title: str,
        message: str,
        on_ok,
        ok_text: str = "删除",
        after=None,
        done_text: str = "已删除",
    ) -> None:
        def ok(e):
            self.page.pop_dialog()
            on_ok()
            if after:
                after()
            self.render()
            self._toast(done_text)

        dlg = self._dialog(
            title,
            ft.Text(message),
            [
                ft.TextButton("取消", on_click=self._close),
                ft.Button(ok_text, on_click=ok),
            ],
        )
        self._show(dlg)

    def _close_dialogs(self, count: int = 1) -> None:
        for _ in range(count):
            self.page.pop_dialog()
