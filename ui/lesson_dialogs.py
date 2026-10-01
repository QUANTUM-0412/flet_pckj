"""新增／编辑课次。"""

from __future__ import annotations

from datetime import date

import flet as ft

import db
from .common import DIALOG_WIDTH, _dd, _level_title, _now_time, _opts, _tf


class LessonDialogsMixin:
    """新增／编辑课次（ClassHoursApp 的一部分）。"""

    def _open_lesson_dialog(self, lesson: dict | None = None) -> None:
        levels = db.list_levels()
        class_types = db.list_class_types()
        editing = lesson is not None

        day = _tf("日期", lesson["lesson_date"] if editing else date.today().isoformat(), width=DIALOG_WIDTH)
        start = _tf("开始时间", lesson["start_time"] if editing else _now_time(), width=DIALOG_WIDTH)
        minutes = _tf(
            "时长（分钟）",
            lesson["minutes"] if editing else 90,
            width=DIALOG_WIDTH,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        type_dd = _dd(
            "课型",
            _opts([(c["id"], c["name"]) for c in class_types]),
            value=str(lesson["class_type_id"]) if editing else None,
            width=DIALOG_WIDTH,
        )
        level_dd = _dd(
            "等级（可不选）",
            [ft.DropdownOption(key="", text="不指定")] + _opts([(l["id"], db.level_full_name(l)) for l in levels]),
            value=str(lesson["level_id"]) if editing and lesson["level_id"] else "",
            width=DIALOG_WIDTH,
        )
        comment = _tf(
            "课评（一节课一份，全班共用）",
            lesson["comment"] if editing else "",
            width=DIALOG_WIDTH,
            multiline=True,
            min_lines=2,
            max_lines=4,
        )
        plan = _tf(
            "教案（备课用）",
            lesson["plan"] if editing else "",
            width=DIALOG_WIDTH,
            multiline=True,
            min_lines=2,
            max_lines=4,
        )

        def on_level(e):
            if editing:
                return
            for l in levels:
                if str(l["id"]) == level_dd.value:
                    minutes.value = str(l["default_minutes"])
                    minutes.update()
                    break

        level_dd.on_select = on_level

        picked: list[tuple[int, ft.Checkbox]] = []
        holder = None
        if not editing:
            for item in db.list_active_students():
                s = item["student"]
                courses = (
                    "、".join(
                        f"{_level_title(e)}（{e['class_type_name']}）"
                        for e in item["enrollments"]
                        if e["status"] == "在读"
                    )
                    or "还没报课"
                )
                picked.append((s["id"], ft.Checkbox(label=f"{s['name']}　{courses}", value=False)))
            listing = ft.Column([cb for _, cb in picked], spacing=0, tight=True)
            holder = ft.Container(
                content=listing,
                height=150 if (self.page.height or 900) < 820 else 220,
                border_radius=10,
                bgcolor=ft.Colors.GREY_50,
                padding=8,
            )

        def select_by_level(e):
            if holder is None or not level_dd.value:
                self._toast("先选一个等级")
                return
            level_id = int(level_dd.value)
            picked_students = {
                item["student"]["id"]: item
                for item in db.list_active_students()
            }
            for sid, cb in picked:
                item = picked_students.get(sid)
                cb.value = bool(
                    item
                    and any(
                        en["status"] == "在读" and en["level_id"] == level_id
                        for en in item["enrollments"]
                    )
                )
            holder.content = ft.Column([cb for _, cb in picked], spacing=0, tight=True)
            holder.update()

        def save(e):
            if not type_dd.value:
                self._toast("请选课型")
                return
            try:
                date.fromisoformat((day.value or "").strip())
            except ValueError:
                day.error = "日期写成 2026-09-05 这样"
                day.update()
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
            level_id = int(level_dd.value) if (level_dd.value or "").strip() else None
            args = (
                (day.value or "").strip(),
                (start.value or "").strip(),
                mins,
                int(type_dd.value),
                level_id,
                comment.value or "",
                plan.value or "",
                "",
            )
            if editing:
                db.update_lesson(lesson["id"], *args)
                self._finish("课次已更新")
                return
            lesson_id = db.create_lesson(*args)
            count = 0
            for sid, cb in picked:
                if cb.value:
                    db.add_attendance(lesson_id, sid)
                    count += 1
            self.lesson_id = lesson_id
            self._finish(f"课次已建好，点名 {count} 人")

        body_controls = [day, start, type_dd, level_dd, minutes, comment]
        if not editing:
            body_controls = [
                day,
                start,
                type_dd,
                ft.Row(
                    [level_dd, ft.TextButton("选中这个等级的孩子", on_click=select_by_level)],
                    spacing=6,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                minutes,
                ft.Text("勾上这节课来的孩子：", size=12, color=ft.Colors.GREY_600),
                holder,
                comment,
                plan,
            ]
        else:
            body_controls = [day, start, type_dd, level_dd, minutes, comment, plan]
        body = self._form_column(body_controls)
        self._show(
            self._dialog(
                "编辑课次" if editing else "记一节课",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )

    def _open_add_students_dialog(self, lesson: dict) -> None:
        have = {a["student_id"] for a in db.list_attendance(lesson["id"])}
        picked: list[tuple[int, ft.Checkbox]] = []
        for item in db.list_active_students():
            s = item["student"]
            if s["id"] in have:
                continue
            courses = (
                "、".join(
                    f"{_level_title(e)}（{e['class_type_name']}）"
                    for e in item["enrollments"]
                    if e["status"] == "在读"
                )
                or "还没报课"
            )
            picked.append((s["id"], ft.Checkbox(label=f"{s['name']}　{courses}", value=False)))
        if not picked:
            self._toast("在读的孩子都已经在这节课里了")
            return

        holder = ft.Container(
            content=ft.Column([cb for _, cb in picked], spacing=0, tight=True),
            height=240,
            border_radius=10,
            bgcolor=ft.Colors.GREY_50,
            padding=8,
        )

        def on_search(e):
            kw = (e.control.value or "").strip()
            holder.content = ft.Column(
                [cb for _, cb in picked if not kw or kw in str(cb.label)],
                spacing=0,
                tight=True,
            )
            holder.update()

        search = ft.TextField(
            hint_text="搜名字",
            dense=True,
            width=DIALOG_WIDTH,
            prefix_icon=ft.Icons.SEARCH,
            on_change=on_search,
        )

        def save(e):
            count = 0
            for sid, cb in picked:
                if cb.value:
                    db.add_attendance(lesson["id"], sid)
                    count += 1
            if not count:
                self._toast("还没有勾选孩子")
                return
            self._finish(f"加入 {count} 人")

        body = self._form_column([search, holder])
        self._show(
            self._dialog(
                "添加孩子",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("加入", on_click=save),
                ],
            )
        )
