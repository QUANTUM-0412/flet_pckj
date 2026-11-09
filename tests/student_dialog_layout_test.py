"""新增学员弹窗的布局回归检查。"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="student-dialog-layout-test-")
os.environ["CLASS_HOURS_DB"] = str(pathlib.Path(TMP) / "test.db")

import flet as ft  # noqa: E402

import db  # noqa: E402
from app_ui import ClassHoursApp  # noqa: E402
from ui.common import DIALOG_WIDTH  # noqa: E402

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

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        if self.dialogs:
            self.dialogs.pop()


def walk(control):
    yield control
    for attr in ("controls", "content", "columns", "rows", "cells", "actions"):
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


db.init_db()
page = StubPage()
app = ClassHoursApp(page)
app.user = db.verify_user("root", db.DEFAULT_ADMIN_PASSWORD)
app._open_new_student()
dialog = page.dialogs[-1]

grade = field(dialog, "年级")
birth_date = field(dialog, "出生日期")
compact_row = next(
    control
    for control in walk(dialog)
    if isinstance(control, ft.Row)
    and grade in (control.controls or [])
    and field(dialog, "性别") in (control.controls or [])
)

fixed_width = sum(
    float(getattr(control, "width", 0) or 0)
    for control in compact_row.controls
    if not getattr(control, "expand", False)
)
occupied_width = fixed_width + compact_row.spacing * (
    len(compact_row.controls) - 1
)
assert occupied_width <= DIALOG_WIDTH, (
    f"性别／年级这一行需要 {occupied_width}px，"
    f"但弹窗内容只有 {DIALOG_WIDTH}px"
)
assert all(
    control.expand for control in compact_row.controls
), "短选择项应共同填满这一行"
assert len(compact_row.controls) == 2, "短选择项应保持两列，避免标签被挤成竖排"
assert birth_date not in compact_row.controls, "出生日期应独占一行"
assert birth_date.width == DIALOG_WIDTH, "出生日期应使用整行输入宽度"

print("✓ 新增学员的短选择项紧凑，出生日期使用整行宽度")
