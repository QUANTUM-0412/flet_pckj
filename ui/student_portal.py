"""学生登录后的只读门户：本人档案、积分和课程课评／教案。"""

from __future__ import annotations

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
        lessons = db.student_course_lessons(student["id"])
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
                self._header("我的课程", f"共 {len(lessons)} 次"),
                *cards,
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
        comment = (lesson.get("comment") or "").strip()
        plan = (lesson.get("plan") or "").strip()
        if comment:
            details.append(
                ft.Text(f"课评：{comment}", size=12, color=ft.Colors.GREY_700)
            )
        elif not compact:
            details.append(
                ft.Text("课评：老师暂未填写", size=12, color=ft.Colors.GREY_500)
            )
        if plan and not compact:
            details.append(
                ft.Text(f"教案：{plan}", size=12, color=ft.Colors.GREY_700)
            )
        return self._card(ft.Column(details, spacing=6))


__all__ = ["StudentPortalMixin"]
