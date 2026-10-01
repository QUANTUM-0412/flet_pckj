"""新增学员与报名课程。"""

from __future__ import annotations

import flet as ft

import db
from .common import DIALOG_WIDTH, _dd, _opts, _status_opts, _tf


class EnrollmentMixin:
    """新增学员与报名课程（ClassHoursApp 的一部分）。"""

    def _open_new_student(self) -> None:
        name = _tf("姓名 *", "", width=DIALOG_WIDTH)
        gender = _dd(
            "性别",
            _opts([(g, g) for g in db.GENDER_OPTIONS]),
            width=DIALOG_WIDTH,
        )
        grade = _tf("年级", "", width=DIALOG_WIDTH)
        phone = _tf("联系电话", "", width=DIALOG_WIDTH)
        status = _dd("状态", _status_opts(), value="在读", width=DIALOG_WIDTH)
        note = _tf("备注", "", width=DIALOG_WIDTH, multiline=True, min_lines=2, max_lines=5)

        def save(e):
            if not (name.value or "").strip():
                name.error = "请填姓名"
                name.update()
                return
            db.create_student(
                {
                    "name": name.value,
                    "gender": gender.value or "",
                    "grade": grade.value or "",
                    "phone": phone.value or "",
                    "note": note.value or "",
                    "status": status.value or "在读",
                }
            )
            self._finish("已新增学员")

        body = self._form_column([name, gender, grade, phone, status, note])
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
        levels = db.list_levels()
        if not levels:
            self._toast("请先到「课程设置」里加一个等级")
            return
        class_types = db.list_class_types()
        if not class_types:
            self._toast("请先到「课程设置」里加一个课型")
            return

        editing = enrollment is not None
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
        note = _tf("备注", enrollment["note"] if editing else "", width=DIALOG_WIDTH)

        def on_level(e):
            for l in levels:
                if str(l["id"]) == level_dd.value:
                    if not (minutes.value or "").strip():
                        minutes.value = str(l["default_minutes"])
                        minutes.update()
                    break

        level_dd.on_select = on_level

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
            )
            if editing:
                db.update_enrollment(enrollment["id"], *data)
            else:
                db.create_enrollment(student_id, *data)
            self._finish("报名已保存")

        body = self._form_column([level_dd, type_dd, minutes, status_dd, note])
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
