"""新学员从建档、报名到首笔缴费的连续流程。"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="new-student-enrollment-test-")
os.environ["CLASS_HOURS_DB"] = str(pathlib.Path(TMP) / "test.db")

import flet as ft  # noqa: E402

import db  # noqa: E402
from app_ui import ClassHoursApp  # noqa: E402

ft.BaseControl.update = lambda self: None


class StubPage:
    def __init__(self):
        self.width = 1200
        self.height = 900
        self.controls = []
        self.dialogs = []
        self.services = []
        self.overlay = []
        self.run_task = lambda *args, **kwargs: None
        self.update = lambda: None

    def clean(self):
        self.controls.clear()

    def add(self, *controls):
        self.controls.extend(controls)

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        if self.dialogs:
            self.dialogs.pop()


def walk(control):
    yield control
    for attr in (
        "controls",
        "content",
        "columns",
        "rows",
        "cells",
        "actions",
        "title",
        "leading",
        "trailing",
    ):
        value = getattr(control, attr, None)
        if isinstance(value, list):
            for child in value:
                if isinstance(child, ft.BaseControl):
                    yield from walk(child)
        elif isinstance(value, ft.BaseControl):
            yield from walk(value)


def field(control, label):
    for child in walk(control):
        if isinstance(child, (ft.TextField, ft.Dropdown)) and child.label == label:
            return child
    raise AssertionError(f"找不到输入框：{label}")


def button(control, label):
    for child in walk(control):
        if isinstance(child, (ft.Button, ft.TextButton)) and child.content == label:
            return child
    raise AssertionError(f"找不到按钮：{label}")


db.init_db()
level = next(l for l in db.list_levels() if l["level_type"] == "正课")
course_id = db.create_template(
    0,
    "15:00",
    int(level["default_minutes"]),
    db.class_type_id_for_level(level["id"]),
    level["id"],
    teacher_id=1,
    name="周一启蒙班",
)

page = StubPage()
app = ClassHoursApp(page)
app.user = db.verify_user("root", db.DEFAULT_ADMIN_PASSWORD)
app.render()

button(page.controls[0], "新学员报名").on_click(None)
dialog = page.dialogs[-1]
course = field(dialog, "报读课程")
assert any(str(option.key) == str(course_id) for option in course.options), (
    "新学员报名时应直接列出已建好的课程"
)

field(dialog, "姓名 *").value = "新报名学员"
field(dialog, "出生日期").value = "2015-06-18"
field(dialog, "联系电话").value = "13800138000"
course.value = str(course_id)
course.on_select(None)
button(dialog, "建档并报名").on_click(None)

student = next(s for s in db.list_students() if s["name"] == "新报名学员")
enrollments = db.list_enrollments(student["id"])
assert len(enrollments) == 1, "建档和报名应在同一次保存里完成"
assert enrollments[0]["class_id"] == course_id, "报名应直接挂到刚选的课程"
assert student["id"] in db.template_student_ids(course_id), (
    "报名后应同时进入课程的学员名单"
)
assert (
    db.enroll_student_in_course(student["id"], course_id)
    == enrollments[0]["id"]
), "重复加入同一门课程时应复用原报名"
assert len(db.list_enrollments(student["id"])) == 1, (
    "同一门课程不应生成重复报名"
)

summary = page.dialogs[-1]
button(summary, "记首笔缴费").on_click(None)
payment = page.dialogs[-1]
assert field(payment, "孩子").value == str(student["id"]), (
    "首笔缴费应自动选中刚建档的学员"
)
assert field(payment, "哪门课程（报名）").value == str(enrollments[0]["id"]), (
    "首笔缴费应自动选中刚报的课程，而不是让人重新找"
)

package = db.list_course_packages(active_only=True)[0]
package_picker = field(payment, "缴费方式")
package_picker.value = str(package["id"])
package_picker.on_select(None)
assert field(payment, "报的等级（课包统一）").value == str(level["id"]), (
    "选固定课包时，报的等级仍应跟着刚报的课程"
)
button(payment, "保存").on_click(None)

payments = db.list_payments(student["id"])
items = db.list_payment_items(payments[0]["id"])
assert len(payments) == 1, "首笔缴费应保存成功"
assert items[0]["enrollment_id"] == enrollments[0]["id"], (
    "普通缴费和固定课包都应落到刚报名的课程上"
)

print("✓ 新学员建档、报名和首笔缴费可以在一条连续流程里完成")
