"""新增／编辑课次。"""

from __future__ import annotations

from datetime import date

import flet as ft

import db
from .common import (
    DIALOG_WIDTH,
    _courses_text,
    _dd,
    _level_title,
    _now_time,
    _opts,
    _teacher_opts,
    _tf,
)


class LessonDialogsMixin:
    """新增／编辑课次（ClassHoursApp 的一部分）。"""

    def _open_lesson_dialog(self, lesson: dict | None = None) -> None:
        levels = db.list_levels(active_only=True)
        class_types = db.list_class_types()
        classes = db.list_templates()
        editing = lesson is not None

        # 新记一节课：默认就用"你正在看的那天"（在课程页翻到哪天就是哪天），
        # 没翻过就是今天。旁边还有个「今天」按钮随手切回来。
        default_day = (
            lesson["lesson_date"]
            if editing
            else (self.schedule_date or date.today().isoformat())
        )
        day = _tf("日期", default_day, expand=True)

        def pick_today(e=None):
            day.value = date.today().isoformat()
            day.update()

        day_box = ft.Row(
            [day, ft.TextButton("今天", icon=ft.Icons.TODAY, on_click=pick_today)],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        start = _tf("开始时间", lesson["start_time"] if editing else _now_time(), width=DIALOG_WIDTH)
        minutes = _tf(
            "时长（分钟）",
            lesson["minutes"] if editing else 90,
            width=DIALOG_WIDTH,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        class_dd = _dd(
            "课程（可选，用来定归属）",
            [ft.DropdownOption(key="", text="不指定")]
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
            value=str(lesson["template_id"]) if editing and lesson["template_id"] else "",
            width=DIALOG_WIDTH,
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
        teacher_dd = _dd(
            "上课老师（谁上的课给谁）",
            _teacher_opts("不指定"),
            value=(
                str(lesson["teacher_id"])
                if editing and lesson["teacher_id"]
                else self._default_teacher_id()
            ),
            width=DIALOG_WIDTH,
        )
        # 新记一节课：默认只排上、先不点名，等上完课点「点名」才算课时。
        # 只有当场就要算数的（比如补录今天就上完的课），才勾「现在就点名」。
        immediate = None if editing else ft.Checkbox(
            label="现在就点名（立即扣课时、加积分）",
            value=False,
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

        # 每个候选孩子身上带着"他在读哪些等级"，好跟着上面的等级筛
        picked: list[tuple[int, ft.Checkbox, set]] = []
        holder = None
        show_all = None
        if not editing:
            for item in db.list_active_students():
                s = item["student"]
                courses = _courses_text(item["enrollments"])
                mine = {
                    e["level_id"]
                    for e in item["enrollments"]
                    if e["status"] == "在读" and e["level_id"]
                }
                picked.append(
                    (s["id"], ft.Checkbox(label=f"{s['name']}　{courses}", value=False), mine)
                )
            show_all = ft.Checkbox(label="也显示别的级别的孩子", value=False)
            holder = ft.Container(
                content=ft.Column([], spacing=0, tight=True, scroll=ft.ScrollMode.AUTO),
                height=200 if (self.page.height or 900) < 820 else 300,
                border_radius=10,
                bgcolor=ft.Colors.GREY_50,
                padding=8,
            )

        def render_list(update=True):
            if holder is None:
                return
            level_id = int(level_dd.value) if (level_dd.value or "").strip() else None
            rows = [
                cb
                for _sid, cb, mine in picked
                if not level_id or show_all.value or level_id in mine
            ]
            if not rows:
                rows = [
                    ft.Text(
                        "这个级别还没有报名的孩子"
                        if level_id and not show_all.value
                        else "没有孩子",
                        size=12,
                        color=ft.Colors.GREY_600,
                    )
                ]
            holder.content = ft.Column(rows, spacing=0, tight=True, scroll=ft.ScrollMode.AUTO)
            if update:
                holder.update()

        def on_level(e):
            if editing:
                return
            level_id = int(level_dd.value) if (level_dd.value or "").strip() else None
            for l in levels:
                if str(l["id"]) == level_dd.value:
                    minutes.value = str(l["default_minutes"])
                    minutes.update()
                    break
            # 上课老师默认跟着归属走：选了这个等级，就用这门课的默认老师
            default_teacher = db.default_owner_teacher(None, level_id)
            if default_teacher:
                teacher_dd.value = str(default_teacher)
                teacher_dd.update()
            # 等级定了，列表里就只留这个级别的孩子
            render_list()

        def on_class(e):
            """选了课程，课型／等级／时长／上课老师都照课程填好。"""
            for c in classes:
                if str(c["id"]) != (class_dd.value or ""):
                    continue
                if c["class_type_id"]:
                    type_dd.value = str(c["class_type_id"])
                if c["level_id"]:
                    level_dd.value = str(c["level_id"])
                if c["minutes"]:
                    minutes.value = str(c["minutes"])
                if c["teacher_id"]:
                    teacher_dd.value = str(c["teacher_id"])
                for control in (type_dd, level_dd, minutes, teacher_dd):
                    control.update()
                render_list()  # 新课时，候选名单跟着这个级别筛
                break

        class_dd.on_select = on_class

        def on_show_all(e):
            render_list()

        level_dd.on_select = on_level
        if show_all is not None:
            show_all.on_change = on_show_all
        render_list(update=False)

        def select_by_level(e):
            if holder is None or not level_dd.value:
                self._toast("先选一个等级")
                return
            level_id = int(level_dd.value)
            for _sid, cb, mine in picked:
                cb.value = level_id in mine
            render_list()

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
                db.update_lesson(
                    lesson["id"],
                    *args,
                    teacher_id=int(teacher_dd.value) if (teacher_dd.value or "").strip() else None,
                    template_id=int(class_dd.value) if (class_dd.value or "").strip() else None,
                )
                self._finish("课次已更新")
                return
            lesson_id = db.create_lesson(
                *args,
                teacher_id=int(teacher_dd.value) if (teacher_dd.value or "").strip() else None,
                template_id=int(class_dd.value) if (class_dd.value or "").strip() else None,
                rolled=1 if immediate is not None and immediate.value else 0,
            )
            count = 0
            for sid, cb, _mine in picked:
                if cb.value:
                    db.add_attendance(lesson_id, sid)
                    count += 1
            self.lesson_id = lesson_id
            if immediate is not None and immediate.value:
                self._finish(f"课次已建好，点名 {count} 人")
            else:
                self._finish(
                    f"课次已排好（{count} 人）：上完课进去点「点名」才算课时"
                )

        body_controls = [day_box, start, type_dd, level_dd, minutes, teacher_dd, comment]
        if not editing:
            body_controls = [
                day_box,
                start,
                class_dd,
                type_dd,
                ft.Row(
                    [level_dd, ft.TextButton("选中这个等级的孩子", on_click=select_by_level)],
                    spacing=6,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                minutes,
                teacher_dd,
                immediate,
                ft.Text(
                    "勾上这节课来的孩子（选定等级后只列这个级别的）：",
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
                holder,
                show_all,
                comment,
                plan,
            ]
        else:
            body_controls = [
                day_box,
                start,
                class_dd,
                type_dd,
                level_dd,
                minutes,
                teacher_dd,
                comment,
                plan,
            ]
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
        # 这节课的等级已经定了，就只列这个级别的孩子，
        # 免得从别的级别里挑人挑错（要挑也能把下面的开关打开）
        level_id = lesson["level_id"]
        subject = (lesson.get("subject") or "").strip()
        level_name = (lesson.get("level_name") or "").strip()
        level_text = f"{subject}-{level_name}" if subject else level_name

        picked: list[tuple[int, ft.Checkbox, bool]] = []
        for item in db.list_active_students():
            s = item["student"]
            if s["id"] in have:
                continue
            courses = _courses_text(item["enrollments"])
            same_level = bool(level_id) and any(
                e["status"] == "在读" and e["level_id"] == level_id
                for e in item["enrollments"]
            )
            picked.append(
                (s["id"], ft.Checkbox(label=f"{s['name']}　{courses}", value=False), same_level)
            )
        if not picked:
            self._toast("在读的孩子都已经在这节课里了")
            return

        search = ft.TextField(
            hint_text="搜名字",
            dense=True,
            width=DIALOG_WIDTH,
            prefix_icon=ft.Icons.SEARCH,
        )
        show_all = ft.Checkbox(label="也显示别的级别的孩子", value=False)
        holder = ft.Container(
            content=ft.Column([], spacing=0, tight=True, scroll=ft.ScrollMode.AUTO),
            height=300,
            border_radius=10,
            bgcolor=ft.Colors.GREY_50,
            padding=8,
        )

        def render_list(update=True):
            kw = (search.value or "").strip()
            rows = [
                cb
                for _sid, cb, same_level in picked
                if (same_level or show_all.value or not level_id)
                and (not kw or kw in str(cb.label))
            ]
            if not rows:
                rows = [
                    ft.Text(
                        f"这个级别还没有别的孩子"
                        if level_id and not show_all.value
                        else "没找到",
                        size=12,
                        color=ft.Colors.GREY_600,
                    )
                ]
            holder.content = ft.Column(rows, spacing=0, tight=True, scroll=ft.ScrollMode.AUTO)
            if update:
                holder.update()

        def on_search(e):
            render_list()

        def on_show_all(e):
            render_list()

        search.on_change = on_search
        show_all.on_change = on_show_all
        render_list(update=False)

        def save(e):
            count = 0
            for sid, cb, _same_level in picked:
                if cb.value:
                    db.add_attendance(lesson["id"], sid)
                    count += 1
            if not count:
                self._toast("还没有勾选孩子")
                return
            self._finish(f"加入 {count} 人")

        controls = []
        if level_text:
            controls.append(
                ft.Text(
                    f"这节课是 {level_text}，只列这个级别的孩子",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            )
        controls += [search, holder, show_all]
        body = self._form_column(controls)
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
