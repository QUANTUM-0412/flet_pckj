"""课表与排课模板。"""

from __future__ import annotations

from datetime import date, timedelta

import flet as ft

import db
from .common import (
    DIALOG_WIDTH,
    WEEKDAYS,
    _chip,
    _courses_text,
    _date_text,
    _dd,
    _lessons_stats,
    _level_title,
    _opts,
    _teacher_opts,
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

    def _shift_week(self, days: int) -> None:
        self._shift_day(days)

    def _goto_day(self, iso: str) -> None:
        self.schedule_date = iso
        self.render()

    def _week_view(self) -> ft.Control:
        """这一周的课表：周一到周日，每天排了什么课都摆出来。"""
        try:
            anchor = date.fromisoformat(self.schedule_date)
        except ValueError:
            anchor = date.today()
        monday = anchor - timedelta(days=anchor.weekday())
        days = [monday + timedelta(days=i) for i in range(7)]
        today_iso = date.today().isoformat()
        wide = self.is_wide()

        blocks = []
        for day in days:
            iso = day.isoformat()
            cards = []
            done_templates: set[int] = set()
            for lesson in db.lessons_on(iso):
                pending = not lesson.get("rolled", 1)
                if lesson.get("template_id"):
                    done_templates.add(int(lesson["template_id"]))
                cards.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    f"{lesson['start_time']} "
                                    + (
                                        db.lesson_class_label(lesson)
                                        or db.lesson_label(lesson)
                                    ),
                                    size=12,
                                    weight=ft.FontWeight.W_600,
                                ),
                                ft.Text(
                                    db.lesson_label(lesson)
                                    + f" · {lesson['student_count']} 人"
                                    + (" · 待点名" if pending else ""),
                                    size=11,
                                    color=ft.Colors.ORANGE_700
                                    if pending
                                    else ft.Colors.GREY_600,
                                ),
                            ],
                            spacing=1,
                            tight=True,
                        ),
                        padding=6,
                        border_radius=8,
                        bgcolor=ft.Colors.WHITE,
                        border=ft.Border.all(1, ft.Colors.GREY_300),
                        ink=True,
                        on_click=lambda e, lid=lesson["id"]: self.open_lesson(lid),
                    )
                )
            # 还没点名、还没建课次的课程，也摆在这一天（浅一点，点一下去那天）
            for template in db.templates_on(iso):
                if int(template["id"]) in done_templates:
                    continue
                cards.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    f"{template['start_time']} "
                                    + (
                                        (template.get("name") or "").strip()
                                        or db.lesson_label(template)
                                    ),
                                    size=12,
                                    weight=ft.FontWeight.W_600,
                                    color=ft.Colors.GREY_700,
                                ),
                                ft.Text(
                                    "待点名 · " + db.lesson_label(template),
                                    size=11,
                                    color=ft.Colors.ORANGE_700,
                                ),
                            ],
                            spacing=1,
                            tight=True,
                        ),
                        padding=6,
                        border_radius=8,
                        bgcolor=ft.Colors.GREY_50,
                        border=ft.Border.all(1, ft.Colors.GREY_300),
                    )
                )
            if not cards:
                cards = [ft.Text("没有课", size=11, color=ft.Colors.GREY_500)]
            blocks.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                WEEKDAYS[day.weekday()],
                                size=13,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.BLUE_700 if iso == today_iso else None,
                            ),
                            ft.Text(
                                f"{day.month}/{day.day}",
                                size=11,
                                color=ft.Colors.GREY_600,
                            ),
                            *cards,
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    padding=8,
                    border_radius=10,
                    bgcolor=ft.Colors.BLUE_50 if iso == today_iso else ft.Colors.GREY_50,
                    expand=wide,
                    ink=True,
                    on_click=lambda e, d=iso: self._goto_day(d),
                )
            )

        head = ft.Row(
            [
                ft.IconButton(
                    ft.Icons.CHEVRON_LEFT,
                    tooltip="上一周",
                    on_click=lambda e: self._shift_week(-7),
                ),
                ft.Text(
                    f"{days[0].month}月{days[0].day}日 ~ {days[-1].month}月{days[-1].day}日",
                    size=14,
                    weight=ft.FontWeight.W_600,
                    expand=True,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.IconButton(
                    ft.Icons.CHEVRON_RIGHT,
                    tooltip="下一周",
                    on_click=lambda e: self._shift_week(7),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        body = ft.Row(blocks, spacing=8, vertical_alignment=ft.CrossAxisAlignment.START) if wide else ft.Column(blocks, spacing=8)
        return self._section("这一周的课", ft.Column([head, body], spacing=10))

    def _schedule_view(self) -> ft.Column:
        db.sync_course_statuses()  # 课程到期了就自动结课
        try:
            day = date.fromisoformat(self.schedule_date)
        except ValueError:
            day = date.today()
            self.schedule_date = day.isoformat()
        today_iso = date.today().isoformat()

        keyword = self.lesson_keyword
        search = ft.TextField(
            value=keyword,
            hint_text="搜孩子名字 / 课型 / 等级 / 日期 / 课评（全时间段找）",
            dense=True,
            prefix_icon=ft.Icons.SEARCH,
            expand=True,
            on_submit=self._on_lesson_search,
        )
        head = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("课程排课", size=20, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "一门课程 = 名字 + 老师 + 开班／结课日期 + 每周时间 + 学生名单",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.Button(
                    "新增课程",
                    icon=ft.Icons.ADD,
                    on_click=lambda e: self._open_template_dialog(),
                ),
                ft.TextButton(
                    "记一节课",
                    icon=ft.Icons.FACT_CHECK_OUTLINED,
                    on_click=lambda e: self._open_lesson_dialog(),
                ),
                ft.TextButton(
                    "规范课程名",
                    icon=ft.Icons.RULE,
                    tooltip="按 年份-学期-等级-Cls-序号 统一改名",
                    on_click=lambda e: self._normalize_course_names(),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        if keyword:
            cards, count = self._lesson_search_cards()
            return ft.Column(
                [
                    head,
                    ft.Row(
                        [
                            search,
                            ft.TextButton(
                                "清空搜索",
                                icon=ft.Icons.CLOSE,
                                on_click=lambda e: self._clear_lesson_search(),
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.Text(
                        f"搜的是「{keyword}」，共 {count} 节课",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    *cards,
                    ft.Container(height=8),
                ],
                expand=True,
                scroll=ft.ScrollMode.AUTO,
                spacing=12,
            )

        day_templates = db.templates_on(self.schedule_date)
        day_lessons = db.lessons_on(self.schedule_date)
        names = db.attendance_names([l["id"] for l in day_lessons])
        used_ids: set[int] = set()
        rows: list[ft.Control] = []
        # 这天已经建出来的课次，按"属于哪门课程"对号入座
        by_template = {
            int(l["template_id"]): l for l in day_lessons if l.get("template_id")
        }
        for t in day_templates:
            found = by_template.get(int(t["id"]))
            if found:
                used_ids.add(int(found["id"]))
            rows.append(
                self._schedule_row(
                    t, found, names.get(int(found["id"]), []) if found else []
                )
            )
        # 时间不定的课程、临时加课、补课，也都放在「这天的课」里
        for lesson in day_lessons:
            if int(lesson["id"]) in used_ids:
                continue
            linked = (
                db.get_template(int(lesson["template_id"]))
                if lesson.get("template_id")
                else None
            )
            # 属于某门课程的（比如"时间不定"的竞赛课），跟别的课程一样显示
            rows.append(
                self._schedule_row(linked, lesson, names.get(int(lesson["id"]), []))
                if linked is not None
                else self._day_lesson_row(lesson, names.get(int(lesson["id"]), []))
            )
        if not rows:
            rows = [
                ft.Text(
                    "这天没有课。可以加一门课程，或者直接「记一节课」。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            ]

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

        all_courses = db.list_templates()
        template_rows = [self._template_row(t) for t in all_courses]
        if not template_rows:
            template_rows = [
                ft.Text(
                    "还没有课程。点右上角「新增课程」，把课程名、老师、" 
                    "开课／结课日期、每周上课时间和学生定好，以后到那天点一下「点名」就行。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            ]

        return ft.Column(
            [
                head,
                ft.Row([search], spacing=10),
                *([self._makeups_card(db.list_makeups("待补"))] if db.list_makeups("待补") else []),
                self._week_view(),
                self._card(date_row),
                self._section(
                    f"这天的课（{_date_text(self.schedule_date)}）",
                    ft.Column(rows, spacing=10),
                ),
                self._section(
                    f"课程（{len(all_courses)} 个"
                    + (
                        f"，{sum(1 for t in all_courses if not (t.get('end_date') or '').strip())} 个还没填结课日"
                        if any(not (t.get("end_date") or "").strip() for t in all_courses)
                        else ""
                    )
                    + "）",
                    ft.Column(template_rows, spacing=10),
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

    def _day_lesson_row(
        self, lesson: dict, students: list[dict] | None = None
    ) -> ft.Container:
        """这天另外记的课（补课、临时加课、没建课程的）也摆在「这天的课」里。"""
        tags = []
        if lesson.get("kind") == "补课":
            tags.append(_chip("补课", ft.Colors.BLUE_600))
        elif not lesson.get("template_id"):
            tags.append(_chip("临时", ft.Colors.GREY_500))
        title = db.lesson_class_label(lesson) or db.lesson_label(lesson)
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        f"{lesson['start_time']} · {title}",
                                        size=14,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    *tags,
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            ft.Text(
                                db.lesson_label(lesson)
                                + " · "
                                + _lessons_stats(lesson),
                                size=12,
                                color=ft.Colors.GREY_600,
                            ),
                            *(
                                [
                                    ft.Text(
                                        "、".join(
                                            s["name"]
                                            + ("" if s["attendance"] else "（请假）")
                                            for s in students
                                        ),
                                        size=12,
                                        color=ft.Colors.GREY_600,
                                    )
                                ]
                                if students
                                else []
                            ),
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

    def _schedule_row(
        self, template: dict, found: dict | None, students: list[dict] | None = None
    ) -> ft.Container:
        headcount = (
            found.get("student_count") if found else template["student_count"]
        )
        bits = [db.lesson_label(template), f"{headcount} 人"]
        if template.get("teacher_name"):
            bits.append(f"老师：{template['teacher_name']}")
        if template["note"]:
            bits.append(template["note"])
        bits.append(
            f"时间 {db.num_text((found or {}).get('minutes') or template['minutes'])} 分钟"
        )
        if found and found.get("rolled", 1):
            bits.append("已点名")
            hours = round(float(found.get("attended_minutes") or 0) / 60, 2)
            points = float(found.get("points") or 0)
            if hours:
                bits.append(f"扣 {db.num_text(hours)} 课时")
            if points:
                bits.append(f"积分 +{db.num_text(points)}")
        elif found:
            bits.append("待点名")
        if found and found.get("rolled", 1):
            action = ft.TextButton(
                "已点名 · 进去看",
                icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                on_click=lambda e, lid=found["id"]: self.open_lesson(lid),
            )
        elif found:
            action = ft.Row(
                [
                    ft.Button(
                        "去点名",
                        icon=ft.Icons.FACT_CHECK,
                        on_click=lambda e, lid=found["id"]: self.open_lesson(lid),
                    ),
                    ft.TextButton(
                        "顺延一周",
                        icon=ft.Icons.KEYBOARD_TAB,
                        tooltip="这门课还没点名的课，从这周起整体往后挪一周",
                        on_click=lambda e, t=template: self._postpone_template(t),
                    ),
                ],
                spacing=4,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        else:
            action = ft.Row(
                [
                    ft.Button(
                        "点名",
                        icon=ft.Icons.FACT_CHECK,
                        on_click=lambda e, tid=template["id"]: self._roll_call(tid),
                    ),
                    ft.TextButton(
                        "这天不上",
                        tooltip="这天不算上课，从课表上去掉",
                        on_click=lambda e, tid=template["id"]: self._skip_course_day(
                            tid, self.schedule_date
                        ),
                    ),
                    ft.TextButton(
                        "顺延一周",
                        icon=ft.Icons.KEYBOARD_TAB,
                        tooltip="这门课还没点名的课，从这周起整体往后挪一周",
                        on_click=lambda e, t=template: self._postpone_template(t),
                    ),
                ],
                spacing=4,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                f"{(found.get('start_time') if found else template['start_time'])} · "
                                + (
                                    (template.get("name") or "").strip()
                                    or db.lesson_label(template)
                                ),
                                size=14,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                " · ".join(bits),
                                size=12,
                                color=ft.Colors.GREY_600,
                            ),
                            *(
                                [
                                    ft.Text(
                                        "、".join(
                                            s["name"]
                                            + ("" if s["attendance"] else "（请假）")
                                            for s in students
                                        ),
                                        size=12,
                                        color=ft.Colors.GREY_600,
                                    )
                                ]
                                if students
                                else []
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
            bgcolor=(
                ft.Colors.GREEN_50
                if found and found.get("rolled", 1)
                else (ft.Colors.ORANGE_50 if found else ft.Colors.GREY_50)
            ),
        )

    def _template_row(self, template: dict) -> ft.Container:
        bits = [
            f"{db.weekday_text(template['weekday'])} {template['start_time']}",
            db.lesson_label(template),
            f"{template['student_count']} 人",
        ]
        if template.get("teacher_name"):
            bits.append(f"老师：{template['teacher_name']}")
        if template["note"]:
            bits.append(template["note"])
        status = db.course_status(template)
        status_color = {
            "在读": ft.Colors.GREEN_700,
            "未开课": ft.Colors.BLUE_600,
            "已结课": ft.Colors.GREY_500,
        }.get(status, ft.Colors.GREY_600)
        first = (template.get("start_date") or "").strip()
        last = (template.get("end_date") or "").strip()
        if first and last:
            lessons = db.template_lessons(template["id"])
            done = sum(1 for l in lessons if l["rolled"])
            bits.append(f"开班 {first} ~ {last} 结课")
            bits.append(f"已排 {len(lessons)} 节" + (f"，上了 {done} 节" if done else ""))
        elif first:
            bits.append(f"开班 {first} · 还没填结课日")
        else:
            bits.append("还没填开班日和结课日")
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        db.class_label(template),
                                        size=14,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    _chip(status, status_color),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            ft.Text(" · ".join(bits), size=12, color=ft.Colors.GREY_600),
                            *(
                                [
                                    ft.Row(
                                        [
                                            ft.TextButton(
                                                "排整学期",
                                                icon=ft.Icons.CALENDAR_MONTH,
                                                on_click=lambda e, t=template: self._generate_semester(t),
                                            ),
                                        ],
                                        spacing=0,
                                    )
                                ]
                                if self.is_admin()
                                else []
                            ),
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
        template = db.get_template(template_id)
        if template is not None and not db.course_covers(
            template, self.schedule_date
        ):
            self._toast(
                f"「{db.class_label(template)}」{self.schedule_date} 不在开班～结课范围内"
            )
            return
        try:
            lesson_id = db.create_lesson_from_template(template_id, self.schedule_date)
        except ValueError as err:
            self._toast(str(err))
            return
        self.show_schedule = False
        self.lesson_id = lesson_id
        self.render()
        self._toast("课次建好了，进去点名才算课时")

    def _generate_semester(self, template: dict) -> None:
        """一次把这个学期的课排出来（先排课，不点名、不扣课时）。"""
        dates = db.template_dates(template)
        if not dates:
            try:
                weekday = int(template["weekday"])
            except (TypeError, ValueError):
                weekday = -1
            if not (0 <= weekday <= 6):
                self._toast(
                    "这门课程没定星期几（时间不定），不能用「排整学期」；"
                    "用「记一节课」一次一次记"
                )
                return
            self._toast("先填这张课表的开课日和结课日")
            self._open_template_dialog(template)
            return
        existing = {l["lesson_date"] for l in db.template_lessons(template["id"])}
        todo = [d for d in dates if d not in existing]
        body = ft.Column(
            [
                ft.Text(
                    f"{db.weekday_text(template['weekday'])} {template['start_time']} · "
                    f"{db.lesson_label(template)}",
                    size=13,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Text(
                    f"从 {dates[0]} 到 {dates[-1]}，一共 {len(dates)} 次课。",
                    size=12,
                    color=ft.Colors.GREY_700,
                ),
                ft.Text(
                    (
                        f"其中 {len(todo)} 次还没排，这次一并排上；"
                        f"已经排过的 {len(dates) - len(todo)} 次不动。"
                        if len(todo) != len(dates)
                        else f"{len(todo)} 次课都会排上（那几天还有别的安排，回头单独删）。"
                    ),
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
                ft.Text(
                    "排出来的课先不点名：名单已经在，课时和积分等上了课点完名再算。",
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
                *(
                    [ft.Text("这次要排的日期：" + "、".join(d[5:] for d in todo), size=12, color=ft.Colors.GREY_600)]
                    if todo and len(todo) <= 30
                    else []
                ),
            ],
            spacing=6,
            tight=True,
        )

        def ok(e):
            self.page.pop_dialog()
            try:
                result = db.generate_template_lessons(template["id"])
            except ValueError as err:
                self._toast(str(err))
                return
            self.render()
            self._toast(f"排好了 {len(result['made'])} 节课")

        self._show(
            self._dialog(
                "排整学期",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button(
                        "就这么排" if todo else "已经排完了",
                        on_click=ok if todo else self._close,
                    ),
                ],
            )
        )

    def _postpone_template(self, template: dict, days: int = 7) -> None:
        """整体顺延：还没点名的课往后挪（开班日、结课日不动）。"""
        pending = [l for l in db.template_lessons(template["id"]) if not l["rolled"]]
        if not pending:
            self._toast("这门课没有还没点名的课，顺延不动任何东西")
            return
        message = (
            f"把「{db.weekday_text(template['weekday'])} {template['start_time']} "
            f"{db.lesson_label(template)}」还没点名的 {len(pending)} 节课整体往后挪 "
            f"{days} 天。\n"
            "开班日和结课日都不动；已经上过、点过名的课也不动。"
        )

        def do():
            moved = db.postpone_template(template["id"], days)
            self._toast(f"{moved} 节课顺延了 {days} 天（开班日、结课日没动）")

        self._confirm("顺延一周", message, do, ok_text="顺延", done_text="顺延好了")

    def _skip_course_day(self, template_id: int, day: str) -> None:
        """某天的课不上了：那天从课表上去掉。"""
        template = db.get_template(template_id)
        title = db.class_label(template) if template else "这门课"
        self._confirm(
            "这天不上课",
            f"{_date_text(day)} 的「{title}」不上？"
            "这天就不会再出现在课表上，也不会建课次（以后想上回来，"
            "在课程里点「恢复」）。",
            lambda: db.skip_course_day(template_id, day),
            ok_text="确定",
            done_text="这天标成「不上」了",
        )

    def _restore_course_day(self, template_id: int, day: str) -> None:
        db.unskip_course_day(template_id, day)
        self.page.pop_dialog()
        self.render()
        self._toast(f"{_date_text(day)} 恢复上课")

    def _normalize_course_names(self) -> None:
        """把现有课程名统一成 年份-学期-等级-Cls-序号。"""
        count = db.normalize_course_names()
        self.render()
        self._toast(
            f"把 {count} 门课程名按规范改好了" if count else "课程名都已经符合规范"
        )

    def _open_template_dialog(self, template: dict | None = None) -> None:
        levels = db.list_levels(active_only=True)
        class_types = db.list_class_types()
        editing = template is not None
        today = date.today()

        name = _tf(
            "课程名（自动生成，也可自己改）",
            template["name"] if editing else "",
            width=DIALOG_WIDTH,
            hint_text="如 2026-2-STEM-Lvl-02-Cls-01",
        )
        gen_year = _tf(
            "年份",
            template["year"] if editing and template.get("year") else str(today.year),
            width=90,
        )
        gen_term = _dd(
            "学期",
            [
                ft.DropdownOption(key="1", text="1 · 上半年"),
                ft.DropdownOption(key="2", text="2 · 下半年"),
            ],
            value=(
                str(template["term"])
                if editing and template.get("term")
                else ("2" if today.month >= 7 else "1")
            ),
            width=150,
        )
        gen_seq = _tf(
            "班级序号",
            f"{int(template['seq']):02d}"
            if editing and template.get("seq")
            else "",
            width=90,
            hint_text="自动",
        )
        weekday = _dd(
            "星期几（选填）",
            [ft.DropdownOption(key="-1", text="不指定（时间不定）")]
            + _opts([(i, f"每{WEEKDAYS[i]}") for i in range(7)]),
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
        teacher_dd = _dd(
            "课程老师（这门课归谁）",
            _teacher_opts("不指定"),
            value=(
                str(template["teacher_id"])
                if editing and template["teacher_id"]
                else self._default_teacher_id()
            ),
            width=DIALOG_WIDTH,
        )
        note = _tf("备注", template["note"] if editing else "", width=DIALOG_WIDTH)
        start_date = _tf(
            "开班日",
            template["start_date"] if editing else "",
            width=145,
            hint_text="2026-09-01",
        )
        end_date = _tf(
            "结课日（到期自动结课）",
            template["end_date"] if editing else "",
            width=145,
            hint_text="2027-01-15",
        )

        chosen = set(db.template_student_ids(template["id"])) if editing else set()
        # 每个候选孩子身上带着"他在读哪些等级"，好跟着上面的等级筛
        picked: list[tuple[int, ft.Checkbox, set]] = []
        for item in db.list_active_students():
            s = item["student"]
            courses = _courses_text(item["enrollments"])
            mine = {
                e["level_id"]
                for e in item["enrollments"]
                if e["status"] == "在读" and e["level_id"]
            }
            picked.append(
                (
                    s["id"],
                    ft.Checkbox(label=f"{s['name']}　{courses}", value=s["id"] in chosen),
                    mine,
                )
            )
        show_all = ft.Checkbox(label="也显示别的级别的孩子", value=False)
        holder = ft.Container(
            content=ft.Column([], spacing=0, tight=True),
            height=150 if (self.page.height or 900) < 820 else 200,
            border_radius=10,
            bgcolor=ft.Colors.GREY_50,
            padding=8,
        )

        def render_list(update=True):
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
            holder.content = ft.Column(rows, spacing=0, tight=True)
            if update:
                holder.update()

        def on_level(e):
            level_id = int(level_dd.value) if (level_dd.value or "").strip() else None
            for l in levels:
                if str(l["id"]) == level_dd.value:
                    minutes.value = str(l["default_minutes"])
                    minutes.update()
                    break
            if not (teacher_dd.value or "").strip():
                teacher_dd.value = str(db.default_owner_teacher(None, level_id) or "")
                teacher_dd.update()
            refresh_seq()
            # 等级定了，列表里就只留这个级别的孩子
            render_list()

        def level_text() -> str:
            for l in levels:
                if str(l["id"]) == (level_dd.value or ""):
                    return db.level_full_name(l)
            return ""

        name_touched = False

        def mark_name_touched(e=None) -> None:
            nonlocal name_touched
            name_touched = True

        name.on_change = mark_name_touched

        def build_name() -> str | None:
            text = level_text()
            if not text:
                return None
            try:
                seq = int((gen_seq.value or "1").strip() or 1)
            except ValueError:
                seq = 1
            return db.make_course_name(
                gen_year.value or "", gen_term.value or "", text, seq
            )

        def generate_name(e=None, force: bool = True) -> None:
            nonlocal name_touched
            if force:
                name_touched = False
            new_name = build_name()
            if not new_name:
                if force:
                    self._toast("先在上面选好等级，再生成课程名")
                return
            name.value = new_name
            name.error = None
            name.update()

        def refresh_seq(update: bool = True) -> None:
            """按 年份＋学期＋等级 自动填下一个班级序号，并顺手填好课程名。"""
            level_id = (
                int(level_dd.value) if (level_dd.value or "").strip() else None
            )
            if not level_id:
                return
            n = db.next_course_seq(
                gen_year.value or "",
                gen_term.value or "",
                level_id,
                template["id"] if editing else None,
            )
            gen_seq.value = f"{n:02d}"
            if not name_touched:
                auto = build_name()
                if auto:
                    name.value = auto
                    name.error = None
                    if update:
                        name.update()
            if update:
                gen_seq.update()

        gen_year.on_change = lambda e: refresh_seq()
        gen_term.on_select = lambda e: refresh_seq()
        gen_seq.on_change = lambda e: generate_name(force=False)
        if not editing:
            refresh_seq(update=False)

        def on_show_all(e):
            render_list()

        level_dd.on_select = on_level
        show_all.on_change = on_show_all
        render_list(update=False)

        def select_by_level(e):
            if not level_dd.value:
                self._toast("先选一个等级")
                return
            level_id = int(level_dd.value)
            for _sid, cb, mine in picked:
                cb.value = level_id in mine
            render_list()

        def save(e):
            if not (name.value or "").strip():
                name.error = "请填课程名（每门课的名字不能重复）"
                name.update()
                return
            if not type_dd.value:
                self._toast("请选课型")
                return
            for field, label in ((start_date, "开课日"), (end_date, "结课日")):
                day = (field.value or "").strip()
                if not day:
                    continue
                try:
                    date.fromisoformat(day)
                except ValueError:
                    field.error = f"{label}写成 2026-09-01 这样"
                    field.update()
                    return
            first = (start_date.value or "").strip()
            last = (end_date.value or "").strip()
            if first and last and last < first:
                end_date.error = "结课日不能早于开课日"
                end_date.update()
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
                int(weekday.value) if (weekday.value or "").strip() else -1,
                (start.value or "").strip(),
                mins,
                int(type_dd.value),
                level_id,
                note.value or "",
                first,
                last,
            )
            teacher_id = int(teacher_dd.value) if (teacher_dd.value or "").strip() else None
            try:
                seq_value = int((gen_seq.value or "0").strip() or 0) or None
            except ValueError:
                seq_value = None
            extra = {
                "name": name.value or "",
                "year": gen_year.value or "",
                "term": gen_term.value or "",
                "seq": seq_value,
            }
            try:
                if editing:
                    db.update_template(
                        template["id"], *args, teacher_id=teacher_id, **extra
                    )
                    template_id = template["id"]
                else:
                    template_id = db.create_template(
                        *args, teacher_id=teacher_id, **extra
                    )
            except ValueError as err:
                name.error = str(err)
                name.update()
                return
            db.set_template_students(template_id, [sid for sid, cb, _m in picked if cb.value])
            self._finish("课表存好了")

        body = self._form_column(
            [
                ft.Text(
                    "课程名 = 年份-学期-等级-Cls-序号（例：2026-2-STEM-Lvl-02-Cls-01）",
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
                ft.Row([gen_year, gen_term], spacing=8),
                ft.Row(
                    [
                        gen_seq,
                        ft.TextButton(
                            "生成课程名",
                            icon=ft.Icons.AUTO_FIX_HIGH,
                            on_click=generate_name,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                name,
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
                teacher_dd,
                ft.Row([start_date, end_date], spacing=10),
                ft.Text(
                    "填了开班日和结课日：① 到了结课日，这门课自动变「已结课」，"
                    "课里的学生也跟着结课（改日期就能改回来）；"
                    "② 还能一次把这个学期的课都排出来（右上角「排整学期」）。",
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
                note,
                ft.Text(
                    "这个课程的学生（选定等级后只列这个级别的）：",
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
                holder,
                show_all,
                *(
                    [
                        ft.Column(
                            [
                                ft.Text(
                                    "已取消（不上课）的日子，点「恢复」就上回来：",
                                    size=12,
                                    color=ft.Colors.GREY_600,
                                ),
                                *[
                                    ft.Row(
                                        [
                                            ft.Text(
                                                _date_text(s["skip_date"]),
                                                size=12,
                                                expand=True,
                                            ),
                                            ft.TextButton(
                                                "恢复",
                                                on_click=lambda e, d=s["skip_date"]: self._restore_course_day(
                                                    template["id"], d
                                                ),
                                            ),
                                        ],
                                        spacing=4,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    )
                                    for s in db.course_skips(template["id"])
                                ],
                            ],
                            spacing=4,
                            tight=True,
                        )
                    ]
                    if editing and db.course_skips(template["id"])
                    else []
                ),
            ]
        )
        self._show(
            self._dialog(
                "编辑课程" if editing else "新增课程",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )
