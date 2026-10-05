"""课次详情与点名。"""

from __future__ import annotations

import flet as ft

import db
from .common import _attendance_calc, _date_text, _lessons_stats


class LessonDetailMixin:
    """课次详情与点名（ClassHoursApp 的一部分）。"""

    def _lesson_detail_view(self, lesson_id: int) -> ft.Column:
        lesson = db.get_lesson(lesson_id)
        if not lesson:
            self.lesson_id = None
            return self._schedule_view()
        self._row_refs = {}

        stats = ft.Text(_lessons_stats(lesson), size=12, color=ft.Colors.GREY_600)
        self._lesson_stats = stats
        header = ft.Row(
            [
                ft.IconButton(
                    ft.Icons.ARROW_BACK,
                    tooltip="返回",
                    on_click=lambda e: self.open_lesson(None),
                ),
                ft.Column(
                    [
                        ft.Text(
                            f"{_date_text(lesson['lesson_date'])} {lesson['start_time']}",
                            size=20,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(db.lesson_label(lesson), size=13, color=ft.Colors.GREY_700),
                        stats,
                    ],
                    spacing=2,
                    expand=True,
                ),
                *(
                    [
                        ft.Button(
                            "点名",
                            icon=ft.Icons.FACT_CHECK,
                            on_click=lambda e: self._ask_roll_call(lesson),
                        )
                    ]
                    if not lesson.get("rolled", 1)
                    else []
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        info = self._card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(f"时长 {lesson['minutes']} 分钟", size=13),
                            *(
                                [
                                    ft.Text(
                                        f"课程：{db.lesson_class_label(lesson)}",
                                        size=13,
                                        color=ft.Colors.GREY_700,
                                    )
                                ]
                                if db.lesson_class_label(lesson)
                                else []
                            ),
                            ft.Text(
                                f"上课老师：{lesson.get('teacher_name') or '未指定'}",
                                size=13,
                                color=ft.Colors.GREY_700,
                            ),
                            *(
                                [
                                    ft.Text(
                                        f"归属：{lesson['owner_names']}",
                                        size=13,
                                        color=ft.Colors.GREY_700,
                                    )
                                ]
                                if lesson.get("owner_names")
                                else []
                            ),
                        ],
                        spacing=14,
                        wrap=True,
                    ),
                    ft.Row(
                        [
                            ft.Container(expand=True),
                            ft.Button(
                                "编辑课次",
                                icon=ft.Icons.EDIT,
                                on_click=lambda e: self._open_lesson_dialog(lesson),
                            ),
                            *(
                                [
                                    ft.TextButton(
                                        "删除",
                                        icon=ft.Icons.DELETE_OUTLINE,
                                        on_click=lambda e: self._confirm(
                                            "删除这节课",
                                            "确定删除吗？这节课的点名、扣的课时和积分会一起撤销。",
                                            lambda: db.delete_lesson(lesson_id),
                                            after=lambda: setattr(self, "lesson_id", None),
                                        ),
                                    )
                                ]
                                if self.is_admin()
                                else []
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text("课评", size=12, color=ft.Colors.GREY_600),
                    ft.Text(
                        lesson["comment"] or "还没写课评",
                        size=13,
                        color=ft.Colors.GREY_700 if lesson["comment"] else ft.Colors.GREY_500,
                    ),
                    ft.Text("教案", size=12, color=ft.Colors.GREY_600),
                    ft.Text(
                        lesson["plan"] or "还没写教案",
                        size=13,
                        color=ft.Colors.GREY_700 if lesson["plan"] else ft.Colors.GREY_500,
                    ),
                    *(
                        [
                            ft.Text("备注", size=12, color=ft.Colors.GREY_600),
                            ft.Text(lesson["note"], size=13, color=ft.Colors.GREY_700),
                        ]
                        if lesson["note"]
                        else []
                    ),
                ],
                spacing=8,
            )
        )

        makeup_link = db.get_makeup_by_lesson(lesson_id) if lesson["kind"] == "补课" else None
        makeup_card = (
            self._card(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.EVENT_REPEAT, color=ft.Colors.BLUE_700),
                        ft.Column(
                            [
                                ft.Text(
                                    f"这是给「{makeup_link['student_name']}」补的一节课",
                                    size=14,
                                    weight=ft.FontWeight.W_600,
                                ),
                                ft.Text(
                                    f"补的是 {_date_text(makeup_link['lesson_date'])} "
                                    f"{makeup_link['start_time']} 请假的那节",
                                    size=12,
                                    color=ft.Colors.GREY_700,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        *(
                            [
                                ft.TextButton(
                                    "看原课",
                                    icon=ft.Icons.OPEN_IN_NEW,
                                    on_click=lambda e, lid=makeup_link["lesson_id"]: self.open_lesson(
                                        lid
                                    ),
                                )
                            ]
                            if makeup_link.get("lesson_id")
                            else []
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
            if makeup_link
            else None
        )

        rows = db.list_attendance(lesson_id)
        photos = db.files_by_owner("attendance", [r["id"] for r in rows], "照片")
        items = [self._attendance_row(a, lesson, photos.get(a["id"], [])) for a in rows]
        if not items:
            items = [
                ft.Text("还没点名，点右上角把上课的孩子加进来。", size=12, color=ft.Colors.GREY_600)
            ]
        roll = self._section(
            f"点名（{len(rows)} 人）",
            ft.Column(items, spacing=10),
            action=ft.Button(
                "添加孩子",
                icon=ft.Icons.PERSON_ADD,
                on_click=lambda e: self._open_add_students_dialog(lesson),
            ),
        )

        return ft.Column(
            [
                header,
                *([makeup_card] if makeup_card else []),
                info,
                self._lesson_files_card(lesson),
                roll,
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _ask_roll_call(self, lesson: dict) -> None:
        """这节课真上完了：点名之后才开始扣课时、加积分。"""
        rows = db.list_attendance(lesson["id"])
        hours = 0.0
        points = 0.0
        for a in rows:
            h, p = _attendance_calc(a, lesson)
            hours += h
            points += p
        self._confirm(
            "点名",
            f"按现在的名单算：{len(rows)} 人，扣 {db.num_text(hours)} 课时、"
            f"加 {db.num_text(points)} 分。点完还能改。",
            lambda: db.roll_call(lesson["id"]),
            ok_text="点名",
            done_text="点完名了，课时和积分算上了",
        )


    def _lesson_files_card(self, lesson: dict) -> ft.Container:
        files = db.list_files("lesson", lesson["id"], "附件")
        rows = []
        for f in files:
            rows.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.ATTACH_FILE, size=18, color=ft.Colors.GREY_600),
                        ft.Column(
                            [
                                ft.Text(f["filename"] or "文件", size=13),
                                ft.Text(db.human_size(f["size"]), size=11, color=ft.Colors.GREY_500),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.TextButton(
                            "打开",
                            on_click=lambda e, row=f: self.page.run_task(
                                self._open_attachment, row
                            ),
                        ),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE,
                            tooltip="删除",
                            icon_size=18,
                            on_click=lambda e, row=f: self._confirm(
                                "删除附件",
                                f"确定删除「{row['filename']}」吗？",
                                lambda: db.delete_file(row["id"]),
                            ),
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        if not rows:
            rows = [
                ft.Text(
                    "还没传附件。课件、讲义、证书都可以放这儿。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            ]
        return self._section(
            f"附件（{len(files)} 个）",
            ft.Column(rows, spacing=8),
            action=self._upload_button(
                "上传附件", "lesson", lesson["id"], "附件", icon=ft.Icons.UPLOAD_FILE
            ),
        )

    def _attendance_row(self, a: dict, lesson: dict, photos: list[dict]) -> ft.Container:
        hours, points = _attendance_calc(a, lesson)
        present = int(a["attendance"] or 0)
        summary = ft.Text(
            f"本次扣 {db.num_text(hours)} 课时 · 积分 +{db.num_text(points)}"
            if present
            else "请假：不扣课时、不加分",
            size=12,
            color=ft.Colors.GREY_600,
        )
        balance = ft.Text(self._student_hours_text(a["student_id"], lesson), size=12, color=ft.Colors.GREY_600)

        def flag_handler(field, current):
            return lambda e: self._save_attendance_flag(a["id"], field, current, e.control.value)

        cb_att = ft.Checkbox(
            label="出勤",
            width=90,
            value=bool(present),
            on_change=flag_handler("attendance", a["attendance"]),
        )
        cb_dis = ft.Checkbox(
            label="纪律",
            width=90,
            value=bool(a["discipline"]),
            on_change=flag_handler("discipline", a["discipline"]),
        )
        cb_per = ft.Checkbox(
            label="表现",
            width=90,
            value=bool(a["performance"]),
            on_change=flag_handler("performance", a["performance"]),
        )
        bonus = ft.TextField(
            value=db.num_text(a["bonus"]),
            width=70,
            dense=True,
            text_size=13,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_blur=lambda e: self._save_attendance_value(a["id"], "bonus", a["bonus"], e.control.value),
            on_submit=lambda e: self._save_attendance_value(a["id"], "bonus", a["bonus"], e.control.value),
        )
        minutes = ft.TextField(
            value=db.num_text(a["minutes"]),
            width=80,
            dense=True,
            text_size=13,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_blur=lambda e: self._save_attendance_value(a["id"], "minutes", a["minutes"], e.control.value),
            on_submit=lambda e: self._save_attendance_value(a["id"], "minutes", a["minutes"], e.control.value),
        )
        comment = ft.TextField(
            value=a["comment"],
            dense=True,
            text_size=13,
            hint_text="这个孩子的点评（可选）",
            on_blur=lambda e: self._save_attendance_value(a["id"], "comment", a["comment"], e.control.value),
            on_submit=lambda e: self._save_attendance_value(a["id"], "comment", a["comment"], e.control.value),
        )

        self._row_refs[a["id"]] = {
            "attendance": cb_att,
            "discipline": cb_dis,
            "performance": cb_per,
            "bonus": bonus,
            "minutes": minutes,
            "comment": comment,
            "summary": summary,
            "balance": balance,
        }

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(a["student_name"], size=15, weight=ft.FontWeight.W_600, expand=True),
                            *(
                                [
                                    ft.Text(
                                        f"归属 {a['owner_teacher_name']}",
                                        size=12,
                                        color=ft.Colors.BLUE_700,
                                    )
                                ]
                                if a.get("owner_teacher_name")
                                else []
                            ),
                            balance,
                            ft.IconButton(
                                ft.Icons.CLOSE,
                                tooltip="把这个人从这节课去掉",
                                icon_size=18,
                                on_click=lambda e: self._confirm(
                                    "移出这节课",
                                    f"把「{a['student_name']}」从这节课的名单里去掉吗？",
                                    lambda: db.delete_attendance(a["id"]),
                                ),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row([cb_att, cb_dis, cb_per], spacing=4, wrap=True),
                    ft.Row(
                        [
                            ft.Text("突出发挥", size=12, color=ft.Colors.GREY_600),
                            bonus,
                            ft.Text("时长（分钟）", size=12, color=ft.Colors.GREY_600),
                            minutes,
                        ],
                        spacing=8,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    comment,
                    ft.Row(
                        [
                            self._photo_strip(a["id"], photos),
                            ft.Button(
                                "做海报",
                                icon=ft.Icons.AUTO_AWESOME,
                                tooltip="把孩子的照片和课评拼成一张图，发给家长",
                                on_click=lambda e, att_id=a["id"], lid=lesson["id"]: (
                                    self._open_poster_for(att_id, lid)
                                ),
                            ),
                        ],
                        spacing=8,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    summary,
                ],
                spacing=6,
            ),
            padding=10,
            border_radius=10,
            bgcolor=ft.Colors.GREY_50,
        )

    def _student_hours_text(self, student_id: int, lesson: dict) -> str:
        primary = lesson.get("primary_hour_type_id")
        if not primary:
            return ""
        for account in db.get_accounts(student_id):
            if account["hour_type_id"] == primary:
                if account["unlimited"]:
                    return "不限课时"
                return f"剩余 {db.num_text(account['balance'])}"
        return ""

    def _save_attendance_flag(self, att_id: int, field: str, current, value) -> None:
        new = 1 if value else 0
        if new == int(current or 0):
            return
        fields = {field: new}
        if field == "attendance" and not new:
            # 请假了，另外两个勾就不算了
            fields["discipline"] = 0
            fields["performance"] = 0
        db.update_attendance(att_id, **fields)
        self._refresh_attendance_row(att_id)

    def _save_attendance_value(self, att_id: int, field: str, current, value) -> None:
        text = (value or "").strip()
        if field in ("bonus", "minutes"):
            try:
                new = float(text or 0)
            except ValueError:
                return
            if field == "minutes" and new <= 0:
                return
            if abs(float(current or 0) - new) < 1e-6:
                return
        else:
            if (current or "") == text:
                return
            new = text
        db.update_attendance(att_id, **{field: new})
        self._refresh_attendance_row(att_id)

    def _refresh_attendance_row(self, att_id: int) -> None:
        refs = self._row_refs.get(att_id)
        a = db.get_attendance(att_id)
        if refs is None or a is None:
            self.render()
            return
        lesson = db.get_lesson(a["lesson_id"])
        if lesson is None:
            self.render()
            return
        present = int(a["attendance"] or 0)
        hours, points = _attendance_calc(a, lesson)
        refs["attendance"].value = bool(present)
        refs["discipline"].value = bool(a["discipline"])
        refs["performance"].value = bool(a["performance"])
        refs["bonus"].value = db.num_text(a["bonus"])
        refs["minutes"].value = db.num_text(a["minutes"])
        refs["comment"].value = a["comment"]
        refs["summary"].value = (
            f"本次扣 {db.num_text(hours)} 课时 · 积分 +{db.num_text(points)}"
            if present
            else "请假：不扣课时、不加分"
        )
        refs["balance"].value = self._student_hours_text(a["student_id"], lesson)
        for control in refs.values():
            control.update()
        self._refresh_lesson_stats(a["lesson_id"])

    def _refresh_lesson_stats(self, lesson_id: int) -> None:
        lesson = db.get_lesson(lesson_id)
        stats = getattr(self, "_lesson_stats", None)
        if lesson and stats is not None:
            stats.value = _lessons_stats(lesson)
            stats.update()
