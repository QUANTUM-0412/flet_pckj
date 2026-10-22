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
                    else [
                        ft.TextButton(
                            "撤销点名",
                            icon=ft.Icons.UNDO,
                            tooltip="改回「待点名」：这节课扣的课时、加的积分都退回",
                            on_click=lambda e: self._ask_unroll_call(lesson),
                        )
                    ]
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
                self._lesson_content_card(lesson),
                self._lesson_files_card(lesson),
                roll,
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _lesson_content_card(self, lesson: dict) -> ft.Container:
        """课评、教案、课堂照片放在一起，做海报和回看都从这里找。"""
        comment = (lesson.get("comment") or "").strip()
        plan = (lesson.get("plan") or "").strip()
        class_photos = db.list_files("lesson", lesson["id"], "照片")

        comment_field = ft.TextField(
            value=comment,
            multiline=True,
            min_lines=2,
            max_lines=8,
            dense=True,
            text_size=13,
            hint_text="写这节课的课评…（离开输入框自动保存）",
            on_blur=lambda e: self._save_lesson_comment(lesson["id"], e.control.value),
            on_submit=lambda e: self._save_lesson_comment(lesson["id"], e.control.value),
        )

        plan_editor = ft.TextField(
            value=plan,
            multiline=True,
            min_lines=6,
            max_lines=20,
            dense=True,
            text_size=13,
            hint_text="直接写 Markdown…",
            visible=False,
        )
        plan_view = (
            ft.Markdown(
                plan,
                visible=bool(plan),
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_FLAVORED,
                soft_line_break=True,
                auto_follow_links=True,
                auto_follow_links_target=ft.UrlTarget.BLANK,
                image_error_content=ft.Text(
                    "图片没加载出来，确认上传时把它一起选中了",
                    size=11,
                    color=ft.Colors.RED_400,
                ),
            )
        )
        plan_empty = ft.Text(
            "还没写教案",
            size=13,
            color=ft.Colors.GREY_500,
            visible=not plan,
        )

        def show_plan_editor(e) -> None:
            fresh = db.get_lesson(lesson["id"])
            plan_editor.value = (fresh or {}).get("plan") or ""
            plan_editor.visible = True
            plan_actions.visible = True
            edit_plan_button.visible = False
            plan_upload_button.visible = False
            plan_view.visible = False
            plan_empty.visible = False
            for control in (
                plan_editor,
                plan_actions,
                edit_plan_button,
                plan_upload_button,
                plan_view,
                plan_empty,
            ):
                control.update()

        def close_plan_editor() -> None:
            text = (plan_editor.value or "").strip()
            plan_view.value = text
            plan_view.visible = bool(text)
            plan_empty.visible = not bool(text)
            plan_editor.visible = False
            plan_actions.visible = False
            edit_plan_button.visible = True
            plan_upload_button.visible = True
            for control in (
                plan_editor,
                plan_actions,
                edit_plan_button,
                plan_upload_button,
                plan_view,
                plan_empty,
            ):
                control.update()

        def save_plan(e) -> None:
            self._save_lesson_plan(lesson["id"], plan_editor.value or "")
            close_plan_editor()

        edit_plan_button = ft.TextButton(
            "编辑教案",
            icon=ft.Icons.EDIT,
            on_click=show_plan_editor,
        )
        plan_upload_button = self._plan_upload_button(lesson["id"])
        plan_actions = ft.Row(
            [
                ft.Button("保存教案", icon=ft.Icons.SAVE, on_click=save_plan),
                ft.TextButton("取消", on_click=lambda e: close_plan_editor()),
            ],
            spacing=8,
            visible=False,
        )
        return self._section(
            "课堂内容",
            ft.Column(
                [
                    ft.Text("课评", size=12, color=ft.Colors.GREY_600),
                    comment_field,
                    ft.Row(
                        [
                            ft.Text(
                                "教案 · 支持 Markdown",
                                size=12,
                                color=ft.Colors.GREY_600,
                                expand=True,
                            ),
                            edit_plan_button,
                            plan_upload_button,
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    plan_view,
                    plan_empty,
                    plan_editor,
                    plan_actions,
                    ft.Text(
                        "上传 .md 时，把里面引用的本地图片一起选中；"
                        "图片会自动传上来，链接也会自动改好。",
                        size=11,
                        color=ft.Colors.GREY_600,
                    ),
                    ft.Divider(height=1, color=ft.Colors.GREY_200),
                    ft.Text(
                        f"课堂照片（{len(class_photos)} 张）",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    self._photo_strip(
                        lesson["id"],
                        class_photos,
                        owner_type="lesson",
                        add_label="加课堂照片",
                        action=self._class_poster_button(lesson),
                    ),
                    ft.Text(
                        "全班合影传一次就够了；给每个孩子做海报时也会一起用上。",
                        size=11,
                        color=ft.Colors.GREY_600,
                    ),
                ],
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        )

    def _save_lesson_comment(self, lesson_id: int, value: str) -> None:
        text = (value or "").strip()
        current = db.get_lesson(lesson_id)
        if current is None or (current["comment"] or "").strip() == text:
            return
        db.set_lesson_comment(lesson_id, text)
        self._toast("课评已保存")

    def _save_lesson_plan(self, lesson_id: int, value: str) -> None:
        text = (value or "").strip()
        current = db.get_lesson(lesson_id)
        if current is None or (current["plan"] or "").strip() == text:
            return
        db.set_lesson_plan(lesson_id, text)
        db.cleanup_plan_images(lesson_id, text)
        self._toast("教案已保存")

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

    def _ask_unroll_call(self, lesson: dict) -> None:
        """撤销点名：先把要退回的课时、积分说清楚，确认了才改。"""
        rows = db.list_attendance(lesson["id"])
        hours = 0.0
        points = 0.0
        for a in rows:
            h, p = _attendance_calc(a, lesson)
            hours += h
            points += p
        self._confirm(
            "撤销点名",
            f"这节课现在是「已点名」：{len(rows)} 人，已扣 {db.num_text(hours)} 课时、"
            f"已加 {db.num_text(points)} 分。\n"
            "撤销后变回「待点名」：这笔课时和积分都退回，名单、课评、照片都还在，"
            "以后可以再点一次名。确定撤销吗？",
            lambda: db.unroll_lesson(lesson["id"]),
            ok_text="确认撤销",
            done_text="已改回待点名，课时和积分退回来了",
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
        discipline_good = bool(a["discipline"])
        discipline_score_value = float(a["discipline_score"] or 0)
        performance_good = bool(a["performance"])
        performance_score_value = float(a["performance_score"] or 0)
        bonus_value = float(a["bonus"] or 0)
        summary = ft.Text(
            f"本次扣 {db.num_text(hours)} 课时 · 积分 +{db.num_text(points)}"
            if present
            else "请假：不扣课时、不加分",
            size=12,
            color=ft.Colors.GREY_600,
        )
        balance = ft.Text(self._student_hours_text(a["student_id"], lesson), size=12, color=ft.Colors.GREY_600)

        def flag_handler(field):
            return lambda e: self._save_attendance_flag(a["id"], field, e.control.value)

        cb_att = ft.Checkbox(
            label="出勤",
            width=90,
            value=bool(present),
            on_change=flag_handler("attendance"),
        )
        cb_dis = ft.Checkbox(
            label="纪律",
            width=90,
            value=discipline_good,
            on_change=flag_handler("discipline"),
        )
        cb_per = ft.Checkbox(
            label="学习",
            width=90,
            value=performance_good,
            on_change=flag_handler("performance"),
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
        discipline_score = ft.TextField(
            value=db.num_text(discipline_score_value),
            dense=True,
            text_size=13,
            label="纪律分（-10 < x < 10）",
            hint_text="纪律不好时由老师填写，例如 3、0、-4.5",
            visible=bool(present and not discipline_good),
            on_blur=lambda e: self._save_behavior_score(
                a["id"],
                "discipline_score",
                "纪律分",
                a["discipline_score"],
                e.control.value,
                e.control,
            ),
            on_submit=lambda e: self._save_behavior_score(
                a["id"],
                "discipline_score",
                "纪律分",
                a["discipline_score"],
                e.control.value,
                e.control,
            ),
        )
        poor_discipline_reason = ft.TextField(
            value=a["poor_discipline_reason"],
            dense=True,
            text_size=13,
            label="纪律不好原因",
            hint_text="例如：多次打断课堂、影响其他同学",
            error=(
                "请写明纪律不好的原因"
                if present
                and not discipline_good
                and not (a["poor_discipline_reason"] or "").strip()
                else None
            ),
            visible=bool(present and not discipline_good),
            on_blur=lambda e: self._save_attendance_value(
                a["id"],
                "poor_discipline_reason",
                a["poor_discipline_reason"],
                e.control.value,
            ),
            on_submit=lambda e: self._save_attendance_value(
                a["id"],
                "poor_discipline_reason",
                a["poor_discipline_reason"],
                e.control.value,
            ),
        )
        bonus_reason = ft.TextField(
            value=a["bonus_reason"],
            dense=True,
            text_size=13,
            label="突出发挥原因",
            hint_text="例如：主动帮助同学完成搭建",
            error=(
                "请写明突出发挥的原因"
                if present and bonus_value and not (a["bonus_reason"] or "").strip()
                else None
            ),
            visible=bool(present and bonus_value),
            on_blur=lambda e: self._save_attendance_value(
                a["id"], "bonus_reason", a["bonus_reason"], e.control.value
            ),
            on_submit=lambda e: self._save_attendance_value(
                a["id"], "bonus_reason", a["bonus_reason"], e.control.value
            ),
        )
        performance_score = ft.TextField(
            value=db.num_text(performance_score_value),
            dense=True,
            text_size=13,
            label="学习分（-10 < x < 10）",
            hint_text="学习不好时由老师填写，例如 3、0、-4.5",
            visible=bool(present and not performance_good),
            on_blur=lambda e: self._save_behavior_score(
                a["id"],
                "performance_score",
                "学习分",
                a["performance_score"],
                e.control.value,
                e.control,
            ),
            on_submit=lambda e: self._save_behavior_score(
                a["id"],
                "performance_score",
                "学习分",
                a["performance_score"],
                e.control.value,
                e.control,
            ),
        )
        poor_reason = ft.TextField(
            value=a["poor_performance_reason"],
            dense=True,
            text_size=13,
            label="学习不好原因",
            hint_text="例如：注意力不集中，未能按步骤完成",
            error=(
                "请写明学习不好的原因"
                if present
                and not performance_good
                and not (a["poor_performance_reason"] or "").strip()
                else None
            ),
            visible=bool(present and not performance_good),
            on_blur=lambda e: self._save_attendance_value(
                a["id"],
                "poor_performance_reason",
                a["poor_performance_reason"],
                e.control.value,
            ),
            on_submit=lambda e: self._save_attendance_value(
                a["id"],
                "poor_performance_reason",
                a["poor_performance_reason"],
                e.control.value,
            ),
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
            "discipline_score": discipline_score,
            "poor_discipline_reason": poor_discipline_reason,
            "performance": cb_per,
            "performance_score": performance_score,
            "bonus": bonus,
            "bonus_reason": bonus_reason,
            "poor_performance_reason": poor_reason,
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
                    ft.Text(
                        "「纪律」和「学习」任意一项不勾选时，"
                        "分别填写大于 -10 且小于 10 的分数和原因；突出发挥可另外加分。",
                        size=11,
                        color=ft.Colors.GREY_600,
                    ),
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
                    discipline_score,
                    poor_discipline_reason,
                    performance_score,
                    bonus_reason,
                    poor_reason,
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

    def _save_attendance_flag(self, att_id: int, field: str, value) -> None:
        row = db.get_attendance(att_id)
        if row is None:
            return
        new = 1 if value else 0
        if new == int(row[field] or 0):
            # 即使数据库已经是这个值，也把界面同步一次，避免只勾了外观。
            self._refresh_attendance_row(att_id)
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

    def _save_behavior_score(
        self,
        att_id: int,
        field: str,
        title: str,
        current,
        value: str,
        control: ft.TextField,
    ) -> None:
        text = (value or "").strip()
        try:
            new = float(text)
        except ValueError:
            control.error = "请填写数字"
            control.update()
            return
        if not db.BEHAVIOR_SCORE_MIN < new < db.BEHAVIOR_SCORE_MAX:
            control.error = f"{title}必须大于 -10 且小于 10"
            control.update()
            return
        if abs(float(current or 0) - new) < 1e-6:
            control.error = None
            control.update()
            return
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
        for field, good in (
            ("discipline_score", a["discipline"]),
            ("performance_score", a["performance"]),
        ):
            score_value = float(a[field] or 0)
            score_valid = (
                db.BEHAVIOR_SCORE_MIN
                < score_value
                < db.BEHAVIOR_SCORE_MAX
            )
            refs[field].value = db.num_text(score_value)
            refs[field].visible = bool(present and not good)
            refs[field].error = (
                "必须大于 -10 且小于 10"
                if present and not good and not score_valid
                else None
            )
        refs["poor_discipline_reason"].value = a["poor_discipline_reason"]
        refs["poor_discipline_reason"].visible = bool(
            present and not a["discipline"]
        )
        refs["poor_discipline_reason"].error = (
            "请写明纪律不好的原因"
            if present
            and not a["discipline"]
            and not (a["poor_discipline_reason"] or "").strip()
            else None
        )
        refs["bonus"].value = db.num_text(a["bonus"])
        refs["bonus_reason"].value = a["bonus_reason"]
        refs["bonus_reason"].visible = bool(
            present and float(a["bonus"] or 0)
        )
        refs["bonus_reason"].error = (
            "请写明突出发挥的原因"
            if present
            and float(a["bonus"] or 0)
            and not (a["bonus_reason"] or "").strip()
            else None
        )
        refs["poor_performance_reason"].value = a["poor_performance_reason"]
        refs["poor_performance_reason"].visible = bool(
            present and not a["performance"]
        )
        refs["poor_performance_reason"].error = (
            "请写明学习不好的原因"
            if present
            and not a["performance"]
            and not (a["poor_performance_reason"] or "").strip()
            else None
        )
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
