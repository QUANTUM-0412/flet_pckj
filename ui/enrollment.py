"""新增学员与报名课程。"""

from __future__ import annotations

import flet as ft

import db
from .common import DIALOG_WIDTH, _dd, _opts, _status_opts, _teacher_opts, _tf


class EnrollmentMixin:
    """新增学员与报名课程（ClassHoursApp 的一部分）。"""

    def _open_new_student(self) -> None:
        fields = self._student_fields(width=DIALOG_WIDTH)

        def save(e):
            values = self._student_values(fields)
            if values is None:
                return
            db.create_student(values)
            self._finish("已新增学员")

        body = self._form_column(
            [
                fields["name"],
                fields["gender"],
                fields["grade"],
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

    def _open_enrollment_dialog(self, student_id: int, enrollment: dict | None) -> None:
        levels = db.list_levels(active_only=True)
        if not levels:
            self._toast("请先到「课程设置」里加一个等级")
            return
        class_types = db.list_class_types()
        if not class_types:
            self._toast("请先到「课程设置」里加一个课型")
            return

        editing = enrollment is not None
        classes = db.list_templates()
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
            _opts([(l["id"], db.level_full_name(l)) for l in levels]),
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
            _teacher_opts("不指定"),
            value=(
                str(enrollment["owner_teacher_id"] or db.default_owner_teacher(student_id, enrollment["level_id"]) or "")
                if editing
                else ""
            ),
            width=DIALOG_WIDTH,
        )
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
            owner_dd.value = str(db.default_owner_teacher(student_id, level_id) or "")
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
                if c["teacher_id"]:
                    owner_dd.value = str(c["teacher_id"])
                for control in (level_dd, type_dd, minutes, owner_dd):
                    control.update()
                break

        class_dd.on_select = on_class

        def save(e):
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
                int(owner_dd.value) if (owner_dd.value or "").strip() else None,
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
