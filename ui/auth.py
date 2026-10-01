"""登录与账号。"""

from __future__ import annotations

import flet as ft

import db
from .common import DIALOG_WIDTH


class AuthMixin:
    """登录与账号（ClassHoursApp 的一部分）。"""

    def _login_view(self) -> ft.Control:
        username = ft.TextField(label="用户名", width=240, dense=True, autofocus=True)
        password = ft.TextField(
            label="密码",
            width=240,
            dense=True,
            password=True,
            can_reveal_password=True,
        )
        error = ft.Text("", size=12, color=ft.Colors.RED_600)

        def do_login(e=None):
            user = db.verify_user(username.value or "", password.value or "")
            if user is None:
                error.value = "用户名或密码不对"
                error.update()
                return
            self.user = {
                "id": user["id"],
                "username": user["username"],
                "display_name": user["display_name"],
                "role": user["role"],
            }
            self.render()
            self._toast(f"欢迎，{self._whoami()}")

        password.on_submit = do_login
        card = self._card(
            ft.Column(
                [
                    ft.Icon(ft.Icons.LOCK_OUTLINE, size=32, color=ft.Colors.BLUE_700),
                    ft.Text("课时记录", size=22, weight=ft.FontWeight.BOLD),
                    ft.Text("请用账号登录", size=12, color=ft.Colors.GREY_600),
                    ft.Container(height=6),
                    username,
                    password,
                    error,
                    ft.Button("登录", icon=ft.Icons.LOGIN, on_click=do_login),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
                tight=True,
            ),
            width=300,
        )
        return ft.Container(
            content=ft.Column([card], spacing=0, tight=True),
            expand=True,
            bgcolor=ft.Colors.GREY_100,
            padding=20,
            alignment=ft.Alignment.CENTER,
        )

    def logout(self) -> None:
        self.user = None
        self.tab = 0
        self.student_id = None
        self.lesson_id = None
        self.show_schedule = False
        self.render()

    def _open_change_password(self, user_id: int | None = None) -> None:
        """不传 user_id 就是改自己的密码。"""
        target = user_id or (self.user or {}).get("id")
        record = db.get_user(target) if target else None
        if record is None:
            self._toast("账号不存在")
            return
        old = ft.TextField(label="当前密码", width=DIALOG_WIDTH, dense=True, password=True)
        new1 = ft.TextField(label="新密码", width=DIALOG_WIDTH, dense=True, password=True)
        new2 = ft.TextField(label="再输一遍新密码", width=DIALOG_WIDTH, dense=True, password=True)
        only_new = user_id is not None

        def save(e):
            if not only_new:
                if db.verify_user(record["username"], old.value or "") is None:
                    old.error = "当前密码不对"
                    old.update()
                    return
            if len((new1.value or "").strip()) < 4:
                new1.error = "至少 4 位"
                new1.update()
                return
            if (new1.value or "") != (new2.value or ""):
                new2.error = "两次输入不一样"
                new2.update()
                return
            db.set_user_password(record["id"], new1.value)
            self._finish("密码改好了")

        body = self._form_column(
            [ft.Text(f"账号：{record['username']}（{db.ROLE_NAMES.get(record['role'], '')}）", size=12, color=ft.Colors.GREY_600)]
            + ([] if only_new else [old])
            + [new1, new2]
        )
        self._show(
            self._dialog(
                "重设密码" if only_new else "修改密码",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )

    def is_admin(self) -> bool:
        return bool(self.user and self.user.get("role") == db.ROLE_ROOT)

    def _whoami(self) -> str:
        if not self.user:
            return ""
        return self.user.get("display_name") or self.user.get("username") or ""
