"""课表与排课模板。"""

from __future__ import annotations

from datetime import date, timedelta

import flet as ft

import db
from .common import (
    DIALOG_WIDTH,
    WEEKDAYS,
    _date_text,
    _dd,
    _lessons_stats,
    _level_title,
    _opts,
    _tf,
)


class ScheduleMixin:
    """课表与排课模板（ClassHoursApp 的一部分）。"""

    def _shift_day(self, days: int) -> None:
        try:
            day = date.fromisoformat(self.schedule_date)
        except ValueError:
            day = date.today()
        self.schedule_date = (day + timedelta(days=days)).isoformat()
        self.render()

    def _schedule_view(self) -> ft.Column:
        try:
            day = date.fromisoformat(self.schedule_date)
        except ValueError:
            day = date.today()
            self.schedule_date = day.isoformat()
        today_iso = date.today().isoformat()

        day_templates = db.list_templates(weekday=day.weekday())
        day_lessons = db.lessons_on(self.schedule_date)
        used_ids: set[int] = set()
        rows = []
        for t in day_templates:
            found = db.find_lesson_for_template(t, self.schedule_date)
            if found:
                used_ids.add(int(found["id"]))
            rows.append(self._schedule_row(t, found))
        if not rows:
            rows = [
                ft.Text(
                    "这天没有排课。可以加一条固定课表，或者直接「记一节课」。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            ]
        others = [l for l in day_lessons if int(l["id"]) not in used_ids]
        other_rows = []
        for lesson in others:
            other_rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        f"{lesson['start_time']} · {db.lesson_label(lesson)}",
                                        size=14,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    ft.Text(_lessons_stats(lesson), size=12, color=ft.Colors.GREY_600),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.TextButton(
                                "进去看",
                                on_click=lambda e, lid=lesson["id"]: self.open_lesson(lid),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )

        date_row = ft.Row(
            [
                ft.IconButton(
                    ft.Icons.CHEVRON_LEFT,
                    tooltip="前一天",
                    on_click=lambda e: self._shift_day(-1),
                ),
                ft.Column(
                    [
                        ft.Text(_date_text(self.schedule_date), size=16, weight=ft.FontWeight.W_600),
                        ft.Text(
                            "今天" if self.schedule_date == today_iso else "",
                            size=11,
                            color=ft.Colors.GREY_600,
                        ),
                    ],
                    spacing=0,
                    expand=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.IconButton(
                    ft.Icons.CHEVRON_RIGHT,
                    tooltip="后一天",
                    on_click=lambda e: self._shift_day(1),
                ),
                ft.TextButton(
                    "今天",
                    on_click=lambda e: self._goto_today(),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        template_rows = [self._template_row(t) for t in db.list_templates()]
        if not template_rows:
            template_rows = [
                ft.Text(
                    "还没有固定课表。点右上角「新增固定课」，把每周的课排好，"
                    "以后到那天点一下「点名」就行。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            ]

        return ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(
                            ft.Icons.ARROW_BACK,
                            tooltip="返回上课记录",
                            on_click=lambda e: self.open_schedule(False),
                        ),
                        ft.Column(
                            [
                                ft.Text("排课表", size=20, weight=ft.FontWeight.BOLD),
                                ft.Text("先把每周固定的课排好", size=12, color=ft.Colors.GREY_600),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Button(
                            "新增固定课",
                            icon=ft.Icons.ADD,
                            on_click=lambda e: self._open_template_dialog(),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self._card(date_row),
                self._section(
                    f"这天的课（{_date_text(self.schedule_date)}）",
                    ft.Column(rows, spacing=10),
                ),
                self._section(
                    f"固定课表（{len(db.list_templates())} 条）",
                    ft.Column(template_rows, spacing=10),
                ),
                *(
                    [self._section("这天另外记的课", ft.Column(other_rows, spacing=10))]
                    if other_rows
                    else []
                ),
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _goto_today(self) -> None:
        self.schedule_date = date.today().isoformat()
        self.render()

    def _schedule_row(self, template: dict, found: dict | None) -> ft.Container:
        bits = [db.lesson_label(template), f"{template['student_count']} 人"]
        if template["note"]:
            bits.append(template["note"])
        action = (
            ft.TextButton(
                "已点名 · 进去看",
                icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                on_click=lambda e, lid=found["id"]: self.open_lesson(lid),
            )
            if found
            else ft.Button(
                "点名",
                icon=ft.Icons.FACT_CHECK,
                on_click=lambda e, tid=template["id"]: self._roll_call(tid),
            )
        )
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                f"{template['start_time']} · " + " · ".join(bits),
                                size=14,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                "时间 " + db.num_text(template["minutes"]) + " 分钟",
                                size=12,
                                color=ft.Colors.GREY_600,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    action,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=10,
            border_radius=10,
            bgcolor=ft.Colors.GREEN_50 if found else ft.Colors.GREY_50,
        )

    def _template_row(self, template: dict) -> ft.Container:
        bits = [db.lesson_label(template), f"{template['student_count']} 人"]
        if template["note"]:
            bits.append(template["note"])
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                f"每{WEEKDAYS[int(template['weekday'])]} {template['start_time']}",
                                size=14,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(" · ".join(bits), size=12, color=ft.Colors.GREY_600),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.IconButton(
                        ft.Icons.EDIT,
                        tooltip="编辑",
                        icon_size=18,
                        on_click=lambda e, t=template: self._open_template_dialog(t),
                    ),
                    *(
                        [
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                tooltip="删除",
                                icon_size=18,
                                on_click=lambda e, t=template: self._confirm(
                                    "删除这条课表",
                                    f"确定删除「每{WEEKDAYS[int(t['weekday'])]} "
                                    f"{t['start_time']} {db.lesson_label(t)}」吗？"
                                    "以前上过的课不受影响。",
                                    lambda: db.delete_template(t["id"]),
                                ),
                            )
                        ]
                        if self.is_admin()
                        else []
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=10,
            border_radius=10,
            bgcolor=ft.Colors.GREY_50,
        )

    def _roll_call(self, template_id: int) -> None:
        lesson_id = db.create_lesson_from_template(template_id, self.schedule_date)
        self.show_schedule = False
        self.lesson_id = lesson_id
        self.render()
        self._toast("课次建好了，名单照课表点上了")

    def _open_template_dialog(self, template: dict | None = None) -> None:
        levels = db.list_levels()
        class_types = db.list_class_types()
        editing = template is not None

        weekday = _dd(
            "星期几",
            _opts([(i, f"每{WEEKDAYS[i]}") for i in range(7)]),
            value=str(template["weekday"]) if editing else "5",
            width=DIALOG_WIDTH,
        )
        start = _tf(
            "开始时间",
            template["start_time"] if editing else "10:00",
            width=DIALOG_WIDTH,
        )
        minutes = _tf(
            "时长（分钟）",
            template["minutes"] if editing else 90,
            width=DIALOG_WIDTH,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        type_dd = _dd(
            "课型",
            _opts([(c["id"], c["name"]) for c in class_types]),
            value=str(template["class_type_id"]) if editing else None,
            width=DIALOG_WIDTH,
        )
        level_dd = _dd(
            "等级（可不选）",
            [ft.DropdownOption(key="", text="不指定")]
            + _opts([(l["id"], db.level_full_name(l)) for l in levels]),
            value=str(template["level_id"]) if editing and template["level_id"] else "",
            width=DIALOG_WIDTH,
        )
        note = _tf("备注", template["note"] if editing else "", width=DIALOG_WIDTH)

        chosen = set(db.template_student_ids(template["id"])) if editing else set()
        picked: list[tuple[int, ft.Checkbox]] = []
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
            picked.append(
                (s["id"], ft.Checkbox(label=f"{s['name']}　{courses}", value=s["id"] in chosen))
            )
        holder = ft.Container(
            content=ft.Column([cb for _, cb in picked], spacing=0, tight=True),
            height=150 if (self.page.height or 900) < 820 else 200,
            border_radius=10,
            bgcolor=ft.Colors.GREY_50,
            padding=8,
        )

        def on_level(e):
            for l in levels:
                if str(l["id"]) == level_dd.value:
                    minutes.value = str(l["default_minutes"])
                    minutes.update()
                    break

        level_dd.on_select = on_level

        def select_by_level(e):
            if not level_dd.value:
                self._toast("先选一个等级")
                return
            level_id = int(level_dd.value)
            for item in db.list_active_students():
                sid = item["student"]["id"]
                hit = any(
                    en["status"] == "在读" and en["level_id"] == level_id
                    for en in item["enrollments"]
                )
                for cb_sid, cb in picked:
                    if cb_sid == sid:
                        cb.value = hit
            holder.content = ft.Column([cb for _, cb in picked], spacing=0, tight=True)
            holder.update()

        def save(e):
            if not type_dd.value:
                self._toast("请选课型")
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
                int(weekday.value or 0),
                (start.value or "").strip(),
                mins,
                int(type_dd.value),
                level_id,
                note.value or "",
            )
            if editing:
                db.update_template(template["id"], *args)
                template_id = template["id"]
            else:
                template_id = db.create_template(*args)
            db.set_template_students(template_id, [sid for sid, cb in picked if cb.value])
            self._finish("课表存好了")

        body = self._form_column(
            [
                weekday,
                start,
                type_dd,
                ft.Row(
                    [level_dd, ft.TextButton("选中这个等级的孩子", on_click=select_by_level)],
                    spacing=6,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                minutes,
                note,
                ft.Text("这节课固定来的孩子：", size=12, color=ft.Colors.GREY_600),
                holder,
            ]
        )
        self._show(
            self._dialog(
                "编辑固定课" if editing else "新增固定课",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )
