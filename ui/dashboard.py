"""员工登录后的今日工作台。"""

from __future__ import annotations

from datetime import date

import flet as ft

import db
from .common import _chip, _date_text


class DashboardMixin:
    """把今天要上的课和需要跟进的事项集中在一页。"""

    def _dashboard_view(self) -> ft.Column:
        today = date.today().isoformat()
        classes = self._dashboard_today_classes()
        pending_count = sum(not row["rolled"] for row in classes)

        if classes:
            summary = f"{_date_text(today)} · {len(classes)} 节课"
            if pending_count:
                summary += f"，{pending_count} 节待点名"
        else:
            summary = f"{_date_text(today)} · 今天没有排课"

        class_rows = (
            [self._dashboard_class_row(row) for row in classes]
            if classes
            else [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(
                                ft.Icons.EVENT_AVAILABLE_OUTLINED,
                                size=32,
                                color=ft.Colors.GREY_400,
                            ),
                            ft.Text(
                                "今天没有排课",
                                size=15,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                "可以查看本周课程，或者临时记一节课。",
                                size=12,
                                color=ft.Colors.GREY_600,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        spacing=6,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=24),
                    alignment=ft.Alignment.CENTER,
                )
            ]
        )

        makeups = self._dashboard_makeups()
        shortages = self._dashboard_shortages()
        trials = self._dashboard_trials()
        attention = ft.ResponsiveRow(
            [
                self._dashboard_attention_block(
                    "待补课",
                    makeups,
                    "没有待安排的补课",
                    "查看补课",
                    lambda e: self.open_schedule(True),
                ),
                self._dashboard_attention_block(
                    "课时不足",
                    shortages,
                    "暂时没有课时预警",
                    "查看学员",
                    lambda e: self._goto(0),
                ),
                self._dashboard_attention_block(
                    "试听跟进",
                    trials,
                    "没有需要跟进的试听",
                    "查看试听",
                    lambda e: self._goto(2),
                ),
            ],
            spacing=12,
            run_spacing=12,
        )

        return ft.Column(
            [
                self._header(
                    "今天",
                    summary,
                    [
                        ft.Button(
                            "记一节课",
                            icon=ft.Icons.POST_ADD,
                            on_click=lambda e: self._dashboard_new_lesson(),
                        )
                    ],
                ),
                self._section(
                    f"今天的课（{len(classes)}）",
                    ft.Column(class_rows, spacing=8),
                    action=ft.TextButton(
                        "完整课程表",
                        icon=ft.Icons.CALENDAR_VIEW_WEEK,
                        on_click=lambda e: self.open_schedule(True),
                    ),
                ),
                self._section("需要处理", attention),
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _dashboard_new_lesson(self) -> None:
        self.schedule_date = date.today().isoformat()
        self._open_lesson_dialog()

    def _dashboard_today_classes(self) -> list[dict]:
        today = date.today().isoformat()
        templates = db.templates_on(today)
        lessons = db.lessons_on(today)
        lesson_names = db.attendance_names([int(lesson["id"]) for lesson in lessons])
        teacher_names = db.teacher_name_map()
        me = self._my_user_id()
        admin = self.is_admin()
        by_template = {
            int(lesson["template_id"]): lesson
            for lesson in lessons
            if lesson.get("template_id")
        }
        used_lessons: set[int] = set()
        items: list[dict] = []

        for template in templates:
            lesson = by_template.get(int(template["id"]))
            if lesson is not None:
                used_lessons.add(int(lesson["id"]))
            teacher_id = int((lesson or template).get("teacher_id") or 0)
            if not admin and teacher_id != me:
                continue
            student_count = (
                len(lesson_names.get(int(lesson["id"]), []))
                if lesson is not None
                else len(db.template_student_ids(int(template["id"])))
            )
            items.append(
                {
                    "template": template,
                    "lesson": lesson,
                    "start_time": (lesson or template).get("start_time") or "",
                    "title": db.class_label(template),
                    "course": db.lesson_label(template),
                    "teacher": teacher_names.get(teacher_id, ""),
                    "student_count": student_count,
                    "rolled": bool(lesson and lesson.get("rolled")),
                }
            )

        for lesson in lessons:
            if int(lesson["id"]) in used_lessons:
                continue
            teacher_id = int(lesson.get("teacher_id") or 0)
            if not admin and teacher_id != me:
                continue
            linked = (
                db.get_template(int(lesson["template_id"]))
                if lesson.get("template_id")
                else None
            )
            names = lesson_names.get(int(lesson["id"]), [])
            items.append(
                {
                    "template": linked,
                    "lesson": lesson,
                    "start_time": lesson.get("start_time") or "",
                    "title": (
                        db.class_label(linked)
                        if linked is not None
                        else db.lesson_label(lesson)
                    ),
                    "course": db.lesson_label(lesson),
                    "teacher": teacher_names.get(teacher_id, ""),
                    "student_count": len(names),
                    "rolled": bool(lesson.get("rolled")),
                }
            )

        return sorted(
            items,
            key=lambda row: (
                str(row["start_time"]),
                0 if row["template"] is not None else 1,
                int((row["lesson"] or {}).get("id") or 0),
            ),
        )

    def _dashboard_class_row(self, row: dict) -> ft.Container:
        status = "已点名" if row["rolled"] else "待点名"
        color = ft.Colors.GREEN_700 if row["rolled"] else ft.Colors.ORANGE_700
        meta = " · ".join(
            value
            for value in (
                row["course"],
                row["teacher"],
                f"{row['student_count']} 人" if row["student_count"] else "",
            )
            if value
        )

        def open_class(e=None) -> None:
            if row["lesson"] is not None:
                self.open_lesson(int(row["lesson"]["id"]))
                return
            self.schedule_date = date.today().isoformat()
            self._roll_call(int(row["template"]["id"]))

        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        row["start_time"] or "时间待定",
                                        size=15,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    _chip(status, color),
                                ],
                                spacing=8,
                                tight=True,
                            ),
                            ft.Text(
                                row["title"],
                                size=15,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                meta,
                                size=12,
                                color=ft.Colors.GREY_600,
                            ),
                        ],
                        spacing=3,
                        expand=True,
                    ),
                    ft.Button(
                        "查看课堂" if row["rolled"] else "去点名",
                        icon=(
                            ft.Icons.VISIBILITY_OUTLINED
                            if row["rolled"]
                            else ft.Icons.FACT_CHECK_OUTLINED
                        ),
                        height=44,
                        on_click=open_class,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=12,
            border_radius=10,
            bgcolor=ft.Colors.GREY_50,
        )

    def _dashboard_makeups(self) -> list[dict]:
        me = self._my_user_id()
        rows = []
        for row in db.list_makeups("待补"):
            if not self.is_admin() and int(row.get("origin_teacher_id") or 0) != me:
                continue
            origin = _date_text(row.get("lesson_date") or "") or "原课时间未记录"
            rows.append(
                {
                    "title": row["student_name"],
                    "meta": f"{origin}请假 · 待安排",
                    "on_click": lambda e, sid=row["student_id"]: self._goto_student(sid),
                }
            )
        return rows

    def _dashboard_shortages(self) -> list[dict]:
        rows = []
        for item in db.list_students_with_summary():
            student = item["student"]
            if student["status"] == "离校":
                continue
            if not self.is_admin() and not self._can_manage_student(student["id"]):
                continue
            warnings = db.warning_accounts(item["accounts"])
            if not warnings:
                continue
            balance = " · ".join(
                f"{account['name']}剩 {db.num_text(account['balance'])}"
                for account in warnings
            )
            rows.append(
                {
                    "title": student["name"],
                    "meta": balance,
                    "on_click": lambda e, sid=student["id"]: self._goto_student(sid),
                }
            )
        return rows

    def _dashboard_trials(self) -> list[dict]:
        me = self._my_user_id()
        rows = []
        for trial in db.list_trials():
            if trial["status"] not in {"待试听", "已试听"}:
                continue
            if not self.is_admin() and int(trial.get("owner_teacher_id") or 0) != me:
                continue
            detail = " · ".join(
                value
                for value in (
                    trial["status"],
                    _date_text(trial.get("trial_on") or ""),
                    trial.get("owner_teacher_name") or "",
                )
                if value
            )
            rows.append(
                {
                    "title": trial["name"],
                    "meta": detail,
                    "on_click": lambda e, status=trial["status"]: self._open_dashboard_trials(status),
                }
            )
        return rows

    def _open_dashboard_trials(self, status: str) -> None:
        self.trial_filter = status
        self._goto(2)

    def _dashboard_attention_block(
        self,
        title: str,
        items: list[dict],
        empty_text: str,
        action_text: str,
        action,
    ) -> ft.Container:
        visible_items = items[:3]
        controls: list[ft.Control] = [
            ft.Text(
                f"{title}（{len(items)}）",
                size=15,
                weight=ft.FontWeight.W_600,
            )
        ]
        if visible_items:
            for item in visible_items:
                controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(
                                            item["title"],
                                            size=13,
                                            weight=ft.FontWeight.W_600,
                                        ),
                                        ft.Text(
                                            item["meta"],
                                            size=11,
                                            color=ft.Colors.GREY_600,
                                        ),
                                    ],
                                    spacing=1,
                                    expand=True,
                                ),
                                ft.Icon(
                                    ft.Icons.CHEVRON_RIGHT,
                                    size=18,
                                    color=ft.Colors.GREY_400,
                                ),
                            ],
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding.symmetric(horizontal=8, vertical=8),
                        border_radius=8,
                        ink=True,
                        on_click=item["on_click"],
                    )
                )
            if len(items) > len(visible_items):
                controls.append(
                    ft.Text(
                        f"还有 {len(items) - len(visible_items)} 项",
                        size=11,
                        color=ft.Colors.GREY_600,
                    )
                )
        else:
            controls.append(
                ft.Text(
                    empty_text,
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            )
        controls.append(
            ft.TextButton(
                action_text,
                on_click=action,
            )
        )
        block = ft.Container(
            content=ft.Column(controls, spacing=4, tight=True),
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            col={"xs": 12, "md": 4},
        )
        return block


__all__ = ["DashboardMixin"]
