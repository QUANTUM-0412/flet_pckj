"""学生登录后的只读门户：本人档案、积分和课程课评／教案。"""

from __future__ import annotations

from datetime import date, datetime

import flet as ft

import db
from .common import _date_text, _level_title


class StudentPortalMixin:
    """学生端页面，不展示课时余额、缴费、代金券或任何金额。"""

    def _student_profile(self) -> dict | None:
        student_id = int((self.user or {}).get("student_id") or 0)
        return db.get_student(student_id) if student_id else None

    def _student_tile(self, label: str, value: str, col=4) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(label, size=11, color=ft.Colors.GREY_600),
                    ft.Text(value or "—", size=14),
                ],
                spacing=2,
                tight=True,
            ),
            col={"xs": 12, "sm": 6, "md": col},
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=10,
            bgcolor=ft.Colors.GREY_50,
        )

    def _student_points_row(self, transaction: dict) -> ft.Row:
        change = float(transaction.get("change") or 0)
        color = (
            ft.Colors.GREEN_700
            if change > 0
            else ft.Colors.RED_600
            if change < 0
            else ft.Colors.GREY_500
        )
        detail = str(transaction.get("kind") or "")
        if transaction.get("note"):
            detail += f" · {transaction['note']}"
        return ft.Row(
            [
                ft.Text(
                    _date_text(transaction.get("happened_on") or ""),
                    size=11,
                    color=ft.Colors.GREY_600,
                    width=76,
                ),
                ft.Text(
                    detail,
                    size=12,
                    color=ft.Colors.GREY_700,
                    expand=True,
                ),
                ft.Text(
                    f"{'+' if change > 0 else ''}{db.num_text(change)}",
                    size=14,
                    weight=ft.FontWeight.W_600,
                    color=color,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _open_student_points_history(self, student: dict) -> None:
        current_month = date.today().strftime("%Y-%m")
        selected_month = {"value": current_month}

        month_label = ft.Text("", size=14, weight=ft.FontWeight.W_600)
        month_summary = ft.Text("", size=12, color=ft.Colors.GREY_600)
        rows_holder = ft.Container(
            ft.Column([], spacing=8, scroll=ft.ScrollMode.AUTO),
            height=min(480, max(240, (self.page.height or 720) - 280)),
        )

        def shift_month(month: str, delta: int) -> str:
            year, number = (int(part) for part in month.split("-"))
            index = year * 12 + number - 1 + delta
            return f"{index // 12:04d}-{index % 12 + 1:02d}"

        def month_text(month: str) -> str:
            year, number = month.split("-")
            return f"{year}年{int(number)}月"

        def render_month(update: bool = True) -> None:
            month = selected_month["value"]
            transactions = db.list_point_transactions(
                student["id"], limit=500, month=month
            )
            rows = [
                self._student_points_row(transaction)
                for transaction in transactions
            ] or [
                ft.Text(
                    "这个月还没有积分流水。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            ]
            gained = sum(
                float(transaction["change"] or 0)
                for transaction in transactions
                if float(transaction["change"] or 0) > 0
            )
            spent = -sum(
                float(transaction["change"] or 0)
                for transaction in transactions
                if float(transaction["change"] or 0) < 0
            )
            month_label.value = month_text(month)
            month_summary.value = (
                f"本月获得 +{db.num_text(gained)} · "
                f"本月扣除 -{db.num_text(spent)} · "
                f"当前积分 {db.num_text(db.student_points(student['id']))}"
            )
            rows_holder.content = ft.Column(
                rows,
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
            )
            next_button.disabled = month >= current_month
            if update:
                month_label.update()
                month_summary.update()
                rows_holder.update()
                next_button.update()

        previous_button = ft.TextButton(
            "← 上月",
            on_click=lambda e: (
                selected_month.__setitem__(
                    "value", shift_month(selected_month["value"], -1)
                ),
                render_month(),
            ),
        )
        next_button = ft.TextButton(
            "下月 →",
            on_click=lambda e: (
                selected_month.__setitem__(
                    "value", shift_month(selected_month["value"], 1)
                ),
                render_month(),
            ),
        )
        this_month_button = ft.TextButton(
            "本月",
            on_click=lambda e: (
                selected_month.__setitem__("value", current_month),
                render_month(),
            ),
        )
        render_month(update=False)
        self._show(
            self._dialog(
                "积分流水",
                ft.Column(
                    [
                        ft.Text(
                            "按月查看积分获得、兑换、悬赏和管理员调整。",
                            size=11,
                            color=ft.Colors.GREY_600,
                        ),
                        ft.Row(
                            [
                                previous_button,
                                month_label,
                                next_button,
                                this_month_button,
                            ],
                            spacing=4,
                            wrap=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        month_summary,
                        ft.Divider(height=1, color=ft.Colors.GREY_200),
                        rows_holder,
                    ],
                    spacing=10,
                ),
                [ft.TextButton("关闭", on_click=self._close)],
            )
        )

    def _student_points_card(self, student: dict) -> ft.Container:
        points = db.student_points(student["id"])
        month = date.today().strftime("%Y-%m")
        transactions = db.list_point_transactions(
            student["id"], limit=6, month=month
        )
        rows = [
            self._student_points_row(transaction)
            for transaction in transactions
        ] or [ft.Text("本月还没有积分流水。", size=12, color=ft.Colors.GREY_600)]
        month_text = f"{month[:4]}年{int(month[5:])}月"
        return self._section(
            f"积分流水（{month_text} · 当前 {db.num_text(points)} 分）",
            ft.Column(rows, spacing=8),
            action=ft.TextButton(
                "查看全部",
                icon=ft.Icons.RECEIPT_LONG,
                on_click=lambda e: self._open_student_points_history(student),
            ),
        )

    def _student_upcoming_card(self, student: dict) -> ft.Container:
        start_day = date.today().isoformat()
        start_time = datetime.now().strftime("%H:%M")
        lessons = db.student_upcoming_lessons(
            student["id"],
            days=7,
            start_day=start_day,
            start_time=start_time,
        )
        rows = []
        for lesson in lessons:
            course = lesson.get("class_name") or db.lesson_label(lesson)
            bits = [
                lesson.get("start_time") or "",
                course,
                lesson.get("teacher_name") or "",
            ]
            rows.append(
                ft.Container(
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.EVENT,
                                size=20,
                                color=ft.Colors.BLUE_700,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        _date_text(lesson["lesson_date"]),
                                        size=14,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    ft.Text(
                                        " · ".join(bit for bit in bits if bit),
                                        size=12,
                                        color=ft.Colors.GREY_700,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            *(
                                [
                                    ft.Text(
                                        "补课",
                                        size=11,
                                        color=ft.Colors.ORANGE_700,
                                    )
                                ]
                                if lesson.get("kind") == "补课"
                                else []
                            ),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=9),
                    border_radius=10,
                    bgcolor=ft.Colors.BLUE_50,
                )
            )
        return self._section(
            f"未来 7 天要上的课（{len(lessons)}）",
            ft.Column(
                rows
                or [
                    ft.Text(
                        "未来 7 天暂时没有排好的课。",
                        size=12,
                        color=ft.Colors.GREY_600,
                    )
                ],
                spacing=8,
            ),
        )

    def _student_portal_view(self) -> ft.Control:
        student = self._student_profile()
        if student is None:
            return self._section(
                "我的信息",
                ft.Text("账号没有绑定有效学员，请联系管理员。", color=ft.Colors.RED_600),
            )
        points = db.student_points(student["id"])
        enrollments = [
            e for e in db.list_enrollments(student["id"]) if e["status"] == "在读"
        ]
        courses = "、".join(_level_title(e) for e in enrollments) or "—"
        lessons = db.student_course_lessons(student["id"], limit=3)
        recent = [
            self._student_lesson_card(lesson, compact=True)
            for lesson in lessons
        ] or [ft.Text("还没有课程记录。", size=12, color=ft.Colors.GREY_600)]
        return ft.Column(
            [
                self._header(
                    "我的学习",
                    student["name"],
                    [
                        ft.TextButton(
                            "修改密码",
                            icon=ft.Icons.KEY,
                            on_click=lambda e: self._open_change_password(),
                        ),
                        ft.TextButton(
                            "退出",
                            icon=ft.Icons.LOGOUT,
                            on_click=lambda e: self.logout(),
                        ),
                    ],
                ),
                self._section(
                    "我的信息",
                    ft.ResponsiveRow(
                        [
                            self._student_tile(
                                "姓名", student["name"], col=3
                            ),
                            self._student_tile(
                                "年级", student["grade"], col=3
                            ),
                            self._student_tile(
                                "学校", student["school"], col=3
                            ),
                            self._student_tile(
                                "当前积分", f"{db.num_text(points)} 分", col=3
                            ),
                            self._student_tile("在读课程", courses, col=12),
                        ],
                        spacing=8,
                        run_spacing=8,
                    ),
                ),
                self._student_upcoming_card(student),
                self._student_points_card(student),
                self._section(
                    "最近课程",
                    ft.Column(recent, spacing=8),
                ),
                self._student_badges_card(student, title="我的徽章"),
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _student_course_view(self) -> ft.Control:
        student = self._student_profile()
        if student is None:
            return ft.Text("账号没有绑定有效学员。", color=ft.Colors.RED_600)
        today = date.today().isoformat()
        lessons = [
            lesson
            for lesson in db.student_course_lessons(student["id"])
            if lesson["lesson_date"] < today
            or (
                lesson["lesson_date"] == today
                and int(lesson.get("rolled") or 0)
            )
        ]
        cards = [
            self._student_lesson_card(lesson)
            for lesson in lessons
        ] or [
            self._card(
                ft.Text(
                    "还没有课程记录。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            )
        ]
        return ft.Column(
            [
                self._header("我的课程", f"上课记录 {len(lessons)} 次"),
                self._section(
                    "上课记录",
                    ft.Column(cards, spacing=8),
                ),
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _student_lesson_card(
        self, lesson: dict, *, compact: bool = False
    ) -> ft.Container:
        present = bool(lesson.get("attendance"))
        status = "出勤" if present else "请假"
        date_line = " ".join(
            x
            for x in [
                _date_text(lesson.get("lesson_date") or ""),
                lesson.get("start_time") or "",
            ]
            if x
        )
        course = " · ".join(
            x
            for x in [
                lesson.get("class_name") or "",
                db.lesson_label(lesson),
            ]
            if x
        )
        facts = [status]
        if present:
            facts.append(f"积分 {db.num_text(lesson.get('points') or 0)}")
        if lesson.get("teacher_name"):
            facts.append(f"上课老师 {lesson['teacher_name']}")
        if lesson.get("kind") == "补课":
            facts.append("补课")
        details: list[ft.Control] = [
            ft.Row(
                [
                    ft.Text(date_line, size=13, weight=ft.FontWeight.W_600),
                    ft.Text(" · ".join(facts), size=12, color=ft.Colors.GREY_600),
                ],
                spacing=8,
                wrap=True,
            ),
            ft.Text(course or "课程", size=13, weight=ft.FontWeight.W_600),
        ]
        if not compact and (
            (lesson.get("comment") or "").strip()
            or (lesson.get("plan") or "").strip()
        ):
            details.append(
                ft.TextButton(
                    "查看课评 / 教案",
                    icon=ft.Icons.ARTICLE_OUTLINED,
                    on_click=lambda e, row=lesson: self._open_student_lesson_detail(
                        row
                    ),
                )
            )
        return self._card(ft.Column(details, spacing=6))

    def _open_student_lesson_detail(self, lesson: dict) -> None:
        comment = (lesson.get("comment") or "").strip()
        plan = (lesson.get("plan") or "").strip()
        self._show(
            self._dialog(
                "课程内容",
                ft.Column(
                    [
                        ft.Text(
                            f"{_date_text(lesson['lesson_date'])} "
                            f"{lesson.get('start_time') or ''} · "
                            f"{lesson.get('class_name') or db.lesson_label(lesson)}",
                            size=13,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text(
                            "课评",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                        ft.Text(
                            comment or "老师暂未填写课评。",
                            size=13,
                            color=ft.Colors.GREY_800,
                            selectable=True,
                        ),
                        ft.Divider(height=1, color=ft.Colors.GREY_200),
                        ft.Text(
                            "教案",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                        *(
                            [
                                ft.Markdown(
                                    plan,
                                    selectable=True,
                                    extension_set=ft.MarkdownExtensionSet.GITHUB_FLAVORED,
                                    soft_line_break=True,
                                )
                            ]
                            if plan
                            else [
                                ft.Text(
                                    "老师暂未上传教案。",
                                    size=13,
                                    color=ft.Colors.GREY_500,
                                )
                            ]
                        ),
                    ],
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                ),
                [ft.TextButton("关闭", on_click=self._close)],
            )
        )


__all__ = ["StudentPortalMixin"]
