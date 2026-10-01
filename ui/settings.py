"""课程设置。"""

from __future__ import annotations

import flet as ft

import db
from .common import DIALOG_WIDTH, _dd, _opts, _tf


class SettingsMixin:
    """课程设置（ClassHoursApp 的一部分）。"""

    def _settings_view(self) -> ft.Column:
        cards: list[ft.Control] = [self._account_card()]
        if self.is_admin():
            cards += [
                self._levels_card(),
                self._class_types_card(),
                self._hour_types_card(),
                self._recompute_card(),
                self._users_card(),
            ]
        return ft.Column(
            [
                self._header(
                    "设置",
                    f"当前账号：{self._whoami()}（{db.ROLE_NAMES.get((self.user or {}).get('role'), '')}）",
                ),
                *cards,
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _hour_types_card(self) -> ft.Container:
        rows = []
        for h in db.list_hour_types():
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(h["name"], size=14, weight=ft.FontWeight.W_600, expand=True),
                            ft.Switch(
                                label="剩余不足时提醒",
                                value=bool(h["warn"]),
                                on_change=lambda e, hid=h["id"]: self._set_hour_warn(
                                    hid, e.control.value
                                ),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        return self._section(
            "课时账户种类",
            ft.Column(
                [
                    ft.Text(
                        "勾上的账户，剩余少于 3 课时会在学员列表上亮提醒（一般只勾正课；"
                        "考级、竞赛这种送的小额用完就算了）。",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    *rows,
                ],
                spacing=10,
            ),
        )

    def _set_hour_warn(self, hour_type_id: int, value: bool) -> None:
        db.set_hour_type_warn(hour_type_id, bool(value))
        self.render()

    def _recompute_card(self) -> ft.Container:
        def run(e):
            count = db.recompute_all_hours()
            self.render()
            self._toast(f"重算完了（{count} 个孩子）")

        return self._section(
            "课时重算",
            ft.Column(
                [
                    ft.Text(
                        "如果以前出现过「竞赛课扣到正课」「先上课、后交的课时费」这类情况，"
                        "点一下会按现在的账，把所有孩子上课扣的课时重算一遍"
                        "（缴费和手工调整不动）。",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    ft.Row(
                        [
                            ft.Button(
                                "重算所有孩子的课时",
                                icon=ft.Icons.REFRESH,
                                on_click=run,
                            )
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                ],
                spacing=10,
            ),
        )

    def _account_card(self) -> ft.Container:
        return self._section(
            "我的账号",
            ft.Row(
                [
                    ft.TextButton(
                        "修改密码",
                        icon=ft.Icons.KEY,
                        on_click=lambda e: self._open_change_password(),
                    ),
                    ft.TextButton(
                        "退出登录",
                        icon=ft.Icons.LOGOUT,
                        on_click=lambda e: self.logout(),
                    ),
                ],
                spacing=8,
                wrap=True,
            ),
        )

    def _users_card(self) -> ft.Container:
        rows = []
        for u in db.list_users():
            bits = [db.ROLE_NAMES.get(u["role"], u["role"])]
            if not u["active"]:
                bits.append("已停用")
            bits.append(f"用户名 {u['username']}")
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        u["display_name"] or u["username"],
                                        size=14,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    ft.Text(" · ".join(bits), size=12, color=ft.Colors.GREY_600),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(
                                ft.Icons.KEY,
                                tooltip="重设密码",
                                icon_size=18,
                                on_click=lambda e, uid=u["id"]: self._open_change_password(uid),
                            ),
                            ft.IconButton(
                                ft.Icons.EDIT,
                                tooltip="编辑",
                                icon_size=18,
                                on_click=lambda e, row=u: self._open_user_dialog(row),
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                tooltip="删除",
                                icon_size=18,
                                on_click=lambda e, row=u: self._confirm(
                                    "删除账号",
                                    f"确定删除「{row['display_name'] or row['username']}」这个账号吗？",
                                    lambda: db.delete_user(row["id"]),
                                ),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        return self._section(
            "老师账号",
            ft.Column(
                [
                    ft.Text(
                        "老师能排课、点名、写教案课评、传照片、记积分兑换；"
                        "改课时、改缴费、删记录、改学员档案只有管理员能做。",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    *rows,
                ],
                spacing=10,
            ),
            action=ft.Button(
                "新增老师", icon=ft.Icons.PERSON_ADD, on_click=lambda e: self._open_user_dialog()
            ),
        )

    def _open_user_dialog(self, user: dict | None = None) -> None:
        editing = user is not None
        username = _tf("用户名（登录用）", user["username"] if editing else "", width=DIALOG_WIDTH)
        display = _tf("姓名", user["display_name"] if editing else "", width=DIALOG_WIDTH)
        password = _tf(
            "密码",
            "",
            width=DIALOG_WIDTH,
            password=True,
            hint_text="留空表示不改（改密码用钥匙图标）" if editing else "",
        )
        role = _dd(
            "身份",
            _opts([(db.ROLE_TEACHER, "老师"), (db.ROLE_ROOT, "管理员")]),
            value=user["role"] if editing else db.ROLE_TEACHER,
            width=DIALOG_WIDTH,
        )
        active = ft.Switch(label="启用这个账号", value=bool(user["active"]) if editing else True)
        if editing:
            username.read_only = True

        def save(e):
            if not editing:
                try:
                    db.create_user(
                        username.value or "",
                        password.value or "",
                        display.value or "",
                        role.value or db.ROLE_TEACHER,
                    )
                except ValueError as exc:
                    self._toast(str(exc))
                    return
                self._finish("老师账号建好了")
                return
            try:
                db.update_user(
                    user["id"], display.value or "", role.value or db.ROLE_TEACHER, bool(active.value)
                )
                if (password.value or "").strip():
                    db.set_user_password(user["id"], password.value)
            except ValueError as exc:
                self._toast(str(exc))
                return
            self._finish("账号已更新")

        body = self._form_column(
            [username, display, password, role, active] if editing else [username, display, password, role]
        )
        self._show(
            self._dialog(
                "编辑账号" if editing else "新增老师",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )

    def _levels_card(self) -> ft.Container:
        levels = db.list_levels()
        rows = []
        for l in levels:
            used = db.count_level_usage(l["id"])
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(db.level_full_name(l), size=14, weight=ft.FontWeight.W_600),
                                    ft.Text(
                                        f"默认 {l['default_minutes']} 分钟"
                                        + (f" · {used} 个学员在用" if used else ""),
                                        size=12,
                                        color=ft.Colors.GREY_600,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(
                                ft.Icons.EDIT,
                                tooltip="编辑",
                                icon_size=18,
                                on_click=lambda e, lv=l: self._open_level_dialog(lv),
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                tooltip="删除",
                                icon_size=18,
                                on_click=lambda e, lv=l: self._confirm(
                                    "删除等级",
                                    f"确定删除「{db.level_full_name(lv)}」吗？",
                                    lambda: db.delete_level(lv["id"]),
                                ),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        action = ft.Button("新增等级", icon=ft.Icons.ADD, on_click=lambda e: self._open_level_dialog(None))
        return self._section(
            "等级与默认时长",
            ft.Column(rows or [ft.Text("还没有等级", size=12, color=ft.Colors.GREY_600)], spacing=10),
            action=action,
        )

    def _class_types_card(self) -> ft.Container:
        class_types = db.list_class_types()
        rows = []
        for c in class_types:
            if not c["deduct"]:
                rule = "不扣课时"
            else:
                rule = f"扣「{c['primary_name']}」课时"
                if c["fallback_name"]:
                    rule += f"，不够时补扣「{c['fallback_name']}」"
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(c["name"], size=14, weight=ft.FontWeight.W_600),
                                    ft.Text(rule, size=12, color=ft.Colors.GREY_600),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(
                                ft.Icons.EDIT,
                                tooltip="编辑",
                                icon_size=18,
                                on_click=lambda e, ct=c: self._open_class_type_dialog(ct),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        return self._section("课型与扣课时规则", ft.Column(rows, spacing=10))

    def _open_level_dialog(self, level) -> None:
        editing = level is not None
        subject = _tf("科目（如 GPL、STEM）", level["subject"] if editing else "", width=DIALOG_WIDTH)
        name = _tf("等级／阶段（如 Lvl-01）", level["name"] if editing else "", width=DIALOG_WIDTH)
        minutes = _tf(
            "默认时长（分钟）",
            level["default_minutes"] if editing else 90,
            width=DIALOG_WIDTH,
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        def save(e):
            if not (name.value or "").strip():
                name.error = "请填等级名称"
                name.update()
                return
            try:
                mins = int(float(minutes.value or 0))
            except ValueError:
                minutes.error = "请填数字"
                minutes.update()
                return
            if editing:
                db.update_level(level["id"], subject.value or "", name.value, mins)
            else:
                db.create_level(subject.value or "", name.value, mins)
            self._finish("等级已保存")

        body = self._form_column([subject, name, minutes])
        self._show(
            self._dialog(
                "编辑等级" if editing else "新增等级",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )

    def _open_class_type_dialog(self, class_type) -> None:
        hour_types = db.list_hour_types()
        options = [ft.DropdownOption(key="", text="不扣")] + _opts(
            [(h["id"], h["name"]) for h in hour_types]
        )
        deduct = ft.Switch(label="这节课扣课时", value=bool(class_type["deduct"]))
        primary = _dd(
            "主扣账户",
            options,
            value=str(class_type["primary_hour_type_id"] or ""),
            width=DIALOG_WIDTH,
        )
        fallback = _dd(
            "账户不够时补扣",
            options,
            value=str(class_type["fallback_hour_type_id"] or ""),
            width=DIALOG_WIDTH,
        )

        def save(e):
            db.update_class_type(
                class_type["id"],
                bool(deduct.value),
                int(primary.value) if (primary.value or "").strip() else None,
                int(fallback.value) if (fallback.value or "").strip() else None,
            )
            self._finish("规则已保存")

        body = self._form_column([deduct, primary, fallback])
        self._show(
            self._dialog(
                f"课型：{class_type['name']}",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )
