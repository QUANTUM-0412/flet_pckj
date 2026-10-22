"""新增学员与报名课程。"""

from __future__ import annotations

import flet as ft

import db
from .common import DIALOG_WIDTH, _dd, _opts, _status_opts, _teacher_opts, _tf


class EnrollmentMixin:
    """新增学员与报名课程（ClassHoursApp 的一部分）。"""

    def _open_new_student(self) -> None:
        fields = self._student_fields(width=DIALOG_WIDTH)
        if not self.is_admin():
            teacher_id = self._my_user_id()
            fields["owner"].value = str(teacher_id)
            fields["owner"].disabled = True
            fields["owner"].label = "归属老师（新学员归你）"

        def save(e):
            values = self._student_values(fields, require_birth_date=True)
            if values is None:
                return
            student_id = db.create_student(values)
            account, password = db.ensure_student_account(student_id)
            self.page.pop_dialog()
            self.render()
            self._show_student_credentials(account, password)

        body = self._form_column(
            [
                fields["name"],
                fields["gender"],
                ft.Row([fields["grade"], fields["birth_date"]], spacing=10),
                fields["school"],
                fields["phone"],
                fields["guardian"],
                fields["status"],
                fields["owner"],
                fields["note"],
            ]
        )
        self._show(
            self._dialog(
                "新增学员",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )

    def _show_student_credentials(
        self, account: dict, password: str | None
    ) -> None:
        password_text = (
            password or "密码已设置过；如需修改，请到学员档案里重设。"
        )
        self._show(
            self._dialog(
                "学生账号已生成",
                self._form_column(
                    [
                        ft.Text(
                            "请把登录账号和初始密码交给学生，并提醒学生或老师"
                            "从学员档案里修改密码。",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                        ft.Text(
                            f"用户名：{account['username']}",
                            size=16,
                            weight=ft.FontWeight.W_600,
                            selectable=True,
                        ),
                        ft.Text(
                            f"初始密码：{password_text}",
                            size=16,
                            weight=ft.FontWeight.W_600,
                            selectable=True,
                        ),
                    ]
                ),
                [ft.Button("知道了", on_click=self._close)],
            )
        )

    def _open_enrollment_dialog(self, student_id: int, enrollment: dict | None) -> None:
        admin = self.is_admin()
        if enrollment is not None:
            if not self._can_manage_enrollment(enrollment):
                self._toast("这是其他老师的报名记录，只能查看")
                return
        elif not self._can_manage_student(student_id):
            self._toast("这是其他老师的学员，只能查看")
            return
        teacher_id = self._my_user_id()
        levels = db.list_levels(active_only=True)
        if not levels:
            self._toast("请先到「课程设置」里加一个等级")
            return
        class_types = db.list_class_types()
        if not class_types:
            self._toast("请先到「课程设置」里加一个课型")
            return

        editing = enrollment is not None
        classes = [
            c
            for c in db.list_templates()
            if admin or int(c.get("teacher_id") or 0) == int(teacher_id or 0)
        ]
        class_dd = _dd(
            "课程（可选）",
            [ft.DropdownOption(key="", text="不指定课程")]
            + _opts(
                [
                    (
                        c["id"],
                        f"{db.class_label(c)}"
                        + (f" · {c['teacher_name']}" if c["teacher_name"] else ""),
                    )
                    for c in classes
                ]
            ),
            value=(
                str(enrollment["class_id"])
                if editing and enrollment.get("class_id")
                else ""
            ),
            width=DIALOG_WIDTH,
        )
        level_dd = _dd(
            "科目-等级",
            _opts([(l["id"], db.level_display_name(l)) for l in levels]),
            value=str(enrollment["level_id"]) if editing and enrollment["level_id"] else None,
            width=DIALOG_WIDTH,
        )
        minutes = _tf(
            "单次时长（分钟）",
            enrollment["minutes"] if editing else "",
            width=DIALOG_WIDTH,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        type_dd = _dd(
            "课型",
            _opts([(c["id"], c["name"]) for c in class_types]),
            value=str(enrollment["class_type_id"]) if editing else None,
            width=DIALOG_WIDTH,
        )
        status_dd = _dd("状态", _status_opts(), value=enrollment["status"] if editing else "在读", width=DIALOG_WIDTH)
        owner_dd = _dd(
            "归属老师（算谁的客户）",
            (
                _teacher_opts("不指定")
                if admin
                else [
                    ft.DropdownOption(
                        key=str(teacher_id),
                        text=self._whoami(),
                    )
                ]
            ),
            value=(
                str(enrollment["owner_teacher_id"] or db.default_owner_teacher(student_id, enrollment["level_id"]) or "")
                if editing
                else ("" if admin else str(teacher_id))
            ),
            width=DIALOG_WIDTH,
        )
        if not admin:
            owner_dd.value = str(teacher_id)
            owner_dd.disabled = True
        note = _tf("备注", enrollment["note"] if editing else "", width=DIALOG_WIDTH)

        def on_level(e):
            level_id = int(level_dd.value) if (level_dd.value or "").strip() else None
            for l in levels:
                if str(l["id"]) == level_dd.value:
                    if not (minutes.value or "").strip():
                        minutes.value = str(l["default_minutes"])
                        minutes.update()
                    break
            # 换了等级，归属老师跟着这个课程的默认老师走（还能手动改）
            owner_dd.value = (
                str(db.default_owner_teacher(student_id, level_id) or "")
                if admin
                else str(teacher_id)
            )
            owner_dd.update()

        level_dd.on_select = on_level

        def on_class(e):
            """选了课程，等级／课型／时长／归属老师跟着课程填好。"""
            for c in classes:
                if str(c["id"]) != (class_dd.value or ""):
                    continue
                if c["level_id"]:
                    level_dd.value = str(c["level_id"])
                if c["class_type_id"]:
                    type_dd.value = str(c["class_type_id"])
                if c["minutes"]:
                    minutes.value = str(c["minutes"])
                if admin and c["teacher_id"]:
                    owner_dd.value = str(c["teacher_id"])
                elif not admin:
                    owner_dd.value = str(teacher_id)
                for control in (level_dd, type_dd, minutes, owner_dd):
                    control.update()
                break

        class_dd.on_select = on_class

        def save(e):
            if editing and not self._can_manage_enrollment(enrollment):
                self._toast("这是其他老师的报名记录，只能查看")
                return
            if not editing and not self._can_manage_student(student_id):
                self._toast("这是其他老师的学员，只能查看")
                return
            if not level_dd.value or not type_dd.value:
                self._toast("请选择等级和课型")
                return
            try:
                mins = int(float(minutes.value or 0))
            except ValueError:
                minutes.error = "请填数字"
                minutes.update()
                return
            if mins <= 0:
                minutes.error = "时长要大于 0"
                minutes.update()
                return
            data = (
                int(level_dd.value),
                int(type_dd.value),
                mins,
                status_dd.value or "在读",
                note.value or "",
                (
                    int(owner_dd.value)
                    if admin and (owner_dd.value or "").strip()
                    else teacher_id
                ),
                int(class_dd.value) if (class_dd.value or "").strip() else None,
            )
            if editing:
                db.update_enrollment(enrollment["id"], *data)
            else:
                db.create_enrollment(student_id, *data)
            self._finish("报名已保存")

        body = self._form_column(
            [class_dd, level_dd, type_dd, minutes, status_dd, owner_dd, note]
        )
        self._show(
            self._dialog(
                "编辑报名" if editing else "新增报名",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )
