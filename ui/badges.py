"""学员的考级与竞赛徽章。"""

from __future__ import annotations

from datetime import date

import flet as ft

import db
from .common import DIALOG_WIDTH, _date_text, _dd, _opts, _tf


class BadgesMixin:
    """考级与竞赛徽章。"""

    @staticmethod
    def _directory_category_label(category: str) -> str:
        return "竞技" if category == "竞赛" else category

    def _can_award_badge_student(self, item: dict) -> bool:
        if self.is_admin():
            return True
        me = self._my_user_id()
        return bool(
            me
            and int(me) in {
                int(teacher_id)
                for teacher_id in (item.get("teacher_ids") or [])
            }
        )

    def _badge_directory_view(self) -> ft.Control:
        levels = [
            level
            for level in db.list_levels()
            if db.badge_category_for_level(level)
        ]
        competition_count = sum(
            1 for level in levels if db.badge_category_for_level(level) == "竞赛"
        )
        exam_count = sum(
            1 for level in levels if db.badge_category_for_level(level) == "考级"
        )
        groups: list[ft.Control] = []
        for category in db.BADGE_CATEGORIES:
            category_label = self._directory_category_label(category)
            group_levels = [
                level
                for level in levels
                if db.badge_category_for_level(level) == category
            ]
            cards = [
                self._badge_level_card(level)
                for level in group_levels
            ]
            groups.append(
                self._section(
                    f"{category_label}目录（{len(group_levels)}）",
                    ft.Column(
                        cards
                        or [
                            ft.Text(
                                f"还没有关联的{category_label}级别。"
                                "请到「设置 → 课程设置」把等级的类别设为"
                                f"「{category_label}」。",
                                size=12,
                                color=ft.Colors.GREY_600,
                            )
                        ],
                        spacing=10,
                    ),
                )
            )
        return ft.Column(
            [
                self._header(
                    "竞技与考级",
                    f"竞技 {competition_count} 个 · 考级 {exam_count} 个",
                ),
                self._card(
                    ft.Text(
                        "这里按等级汇总已关联的学员。报名、缴费或上过对应课程的学员会自动出现；"
                        "比赛结束或考级完成后，点「本场颁发」一次登记每人的结果。"
                        "谁上的课谁颁发，其他老师只读。",
                        size=12,
                        color=ft.Colors.GREY_700,
                    )
                ),
                *groups,
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _badge_level_card(self, level: dict) -> ft.Container:
        category = db.badge_category_for_level(level)
        category_label = self._directory_category_label(category)
        participants = db.list_badge_level_participants(level["id"])
        awards = db.list_level_badges(level["id"])
        manageable = [
            student
            for student in participants
            if self._can_award_badge_student(student)
        ]
        detail = " · ".join(
            part
            for part in [
                f"默认老师 {level['default_teacher_name']}"
                if level["default_teacher_name"]
                else "还没设默认老师",
                (
                    (
                        f"考级 {level['badge_exam_level']}"
                        if level["badge_exam_level"]
                        else "考级级别未设置"
                    )
                    if category == "考级"
                    else "竞技徽章"
                ),
                f"已关联 {len(participants)} 人",
                f"已颁发 {len(awards)} 枚",
            ]
            if part
        )
        participant_rows = [
            ft.Container(
                ft.Row(
                    [
                        ft.Text(
                            student["name"],
                            size=13,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text(
                            " · ".join(
                                part
                                for part in [
                                    student.get("grade") or "",
                                    student.get("school") or "",
                                    (
                                        f"归属 {student['owner_teacher_name']}"
                                        if student.get("owner_teacher_name")
                                        else ""
                                    ),
                                ]
                                if part
                            ),
                            size=11,
                            color=ft.Colors.GREY_600,
                            expand=True,
                        ),
                        ft.Text(
                            student.get("status") or "",
                            size=10,
                            color=(
                                ft.Colors.GREEN_700
                                if student.get("status") == "在读"
                                else ft.Colors.GREY_600
                            ),
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=10, vertical=7),
                border_radius=8,
                bgcolor=ft.Colors.GREY_50,
            )
            for student in participants
        ]
        award_rows = [
            self._level_award_row(badge)
            for badge in awards
        ]
        body = ft.Column(
            [
                ft.Text(detail, size=12, color=ft.Colors.GREY_600),
                ft.Text(
                    "关联学员",
                    size=12,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Column(
                    participant_rows
                    or [
                        ft.Text(
                            "还没有关联学员。给学员报名该级别、缴对应课时或上对应课程后，会自动出现。",
                            size=11,
                            color=ft.Colors.GREY_500,
                        )
                    ],
                    spacing=5,
                ),
                ft.Text(
                    "颁发记录",
                    size=12,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Column(
                    award_rows
                    or [
                        ft.Text(
                            "还没有颁发记录。",
                            size=11,
                            color=ft.Colors.GREY_500,
                        )
                    ],
                    spacing=5,
                ),
            ],
            spacing=8,
        )
        action = (
            ft.Button(
                "本场颁发",
                icon=ft.Icons.MILITARY_TECH,
                on_click=lambda e, row=level: self._open_level_award_dialog(row),
            )
            if manageable
            else None
        )
        return self._card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        db.level_display_name(level),
                                        size=15,
                                        weight=ft.FontWeight.W_700,
                                    ),
                                    ft.Text(
                                        f"{category_label}级别",
                                        size=11,
                                        color=ft.Colors.BLUE_700,
                                    ),
                                ],
                                spacing=1,
                                expand=True,
                            ),
                            *( [action] if action else [] ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    body,
                ],
                spacing=10,
            )
        )

    def _level_award_row(self, badge: dict) -> ft.Control:
        bgcolor, color = self._badge_colors(badge)
        actions: list[ft.Control] = []
        if self._can_award_badge_student(badge):
            actions = [
                ft.IconButton(
                    ft.Icons.EDIT,
                    tooltip="编辑结果",
                    icon_size=16,
                    on_click=lambda e, row=badge: self._open_badge_dialog(row),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip="删除结果",
                    icon_size=16,
                    on_click=lambda e, row=badge: self._confirm(
                        "删除颁发记录",
                        f"确定删除「{row['student_name']} · {row['title']}」吗？",
                        lambda: db.delete_student_badge(row["id"]),
                    ),
                ),
            ]
        return ft.Container(
            ft.Row(
                [
                    ft.Text(
                        badge.get("student_name") or "",
                        size=12,
                        weight=ft.FontWeight.W_600,
                    ),
                    ft.Text(
                        f"{badge['result']} · {badge['title']}"
                        + (
                            f" · {_date_text(badge['happened_on'])}"
                            if badge.get("happened_on")
                            else ""
                        ),
                        size=11,
                        color=ft.Colors.GREY_700,
                        expand=True,
                    ),
                    *actions,
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=5),
            border_radius=8,
            bgcolor=bgcolor,
            border=ft.Border.all(1, color),
        )

    def _open_level_award_dialog(self, level: dict) -> None:
        participants = db.list_badge_level_participants(level["id"])
        manageable = [
            student
            for student in participants
            if self._can_award_badge_student(student)
        ]
        if not manageable:
            self._toast("这个级别里没有你可以颁发的学员")
            return
        category = db.badge_category_for_level(level)
        category_label = self._directory_category_label(category)
        choices = (
            db.COMPETITION_RESULTS
            if category == "竞赛"
            else db.EXAM_RESULTS
        )
        title = _tf(
            "比赛／考级名称 *",
            f"{db.level_display_name(level)} {category_label}",
            width=DIALOG_WIDTH,
        )
        happened_on = _tf(
            "日期 *",
            date.today().isoformat(),
            width=DIALOG_WIDTH,
        )
        note = _tf(
            "本场说明（可不填）",
            "",
            width=DIALOG_WIDTH,
            multiline=True,
            min_lines=2,
            max_lines=3,
        )
        rows: list[tuple[dict, ft.Checkbox, ft.Dropdown]] = []
        student_controls: list[ft.Control] = []
        for student in manageable:
            selected = ft.Checkbox(label=student["name"], value=False)
            result = _dd(
                f"{student['name']}的结果",
                [ft.DropdownOption(key="", text="请选择结果")]
                + _opts([(value, value) for value in choices]),
                value="",
                width=150,
            )
            rows.append((student, selected, result))
            student_controls.append(
                ft.Container(
                    ft.Row(
                        [selected, result],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                    border_radius=8,
                    bgcolor=ft.Colors.GREY_50,
                )
            )

        def save(e=None) -> None:
            awards: dict[int, str] = {}
            for student, selected, result in rows:
                if selected.value:
                    awards[int(student["id"])] = result.value or ""
            if not awards:
                self._toast("请先勾选本次获得结果的学员")
                return
            if any(not result for result in awards.values()):
                self._toast("勾选的学员都要选择比赛或考级结果")
                return
            try:
                count = db.save_badge_awards_for_level(
                    level["id"],
                    title.value or "",
                    awards,
                    happened_on.value or "",
                    note.value or "",
                )
            except ValueError as err:
                title.error = str(err)
                title.update()
                return
            self._finish(f"已为 {count} 名学员颁发{category_label}结果")

        self._show(
            self._dialog(
                f"颁发{category_label}结果",
                self._form_column(
                    [
                        ft.Text(
                            f"{db.level_display_name(level)} · 本次可颁发 {len(manageable)} 人",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                        title,
                        happened_on,
                        ft.Text(
                            "勾选本次有结果／获奖的学员",
                            size=12,
                            weight=ft.FontWeight.W_600,
                        ),
                        *student_controls,
                        note,
                    ]
                ),
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("确认颁发", on_click=save),
                ],
            )
        )

    def _badge_colors(self, badge: dict) -> tuple:
        result = badge.get("result") or "三等奖"
        if badge.get("category") == "考级":
            return ft.Colors.PURPLE_50, ft.Colors.PURPLE_700
        if result == "一等奖":
            return ft.Colors.AMBER_100, ft.Colors.ORANGE_900
        if result == "二等奖":
            return ft.Colors.BLUE_GREY_100, ft.Colors.BLUE_GREY_700
        if result == "三等奖":
            return ft.Colors.ORANGE_50, ft.Colors.BROWN_700
        return ft.Colors.BLUE_50, ft.Colors.BLUE_700

    def _badge_card(self, badge: dict, *, editable: bool = False) -> ft.Control:
        bgcolor, color = self._badge_colors(badge)
        bits = [
            badge.get("title") or badge.get("category"),
            badge.get("level_name") or "",
        ]
        detail = " · ".join(x for x in bits if x)
        actions: list[ft.Control] = []
        if editable:
            actions = [
                ft.IconButton(
                    ft.Icons.EDIT,
                    tooltip="编辑徽章",
                    icon_size=17,
                    on_click=lambda e, row=badge: self._open_badge_dialog(row),
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip="删除徽章",
                    icon_size=17,
                    on_click=lambda e, row=badge: self._confirm(
                        "删除徽章",
                        f"确定删除「{row['title']}」这枚徽章吗？",
                        lambda: db.delete_student_badge(row["id"]),
                    ),
                ),
            ]
        return ft.Container(
            ft.Row(
                [
                    ft.Icon(
                        ft.Icons.MILITARY_TECH if badge["category"] == "竞赛" else ft.Icons.WORKSPACE_PREMIUM,
                        color=color,
                        size=22,
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                f"{badge['category']} · {badge['result']}",
                                size=12,
                                weight=ft.FontWeight.BOLD,
                                color=color,
                            ),
                            ft.Text(detail, size=12),
                            *(
                                [
                                    ft.Text(
                                        _date_text(badge.get("happened_on") or ""),
                                        size=10,
                                        color=ft.Colors.GREY_600,
                                    )
                                ]
                                if badge.get("happened_on")
                                else []
                            ),
                        ],
                        spacing=1,
                        tight=True,
                        expand=True,
                    ),
                    *actions,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            border_radius=10,
            bgcolor=bgcolor,
            border=ft.Border.all(1, color),
        )

    def _student_badges_card(
        self, s: dict, *, title: str = "考级与竞赛徽章"
    ) -> ft.Container:
        badges = db.list_student_badges(s["id"])
        can_edit = self._can_manage_student(s["id"])
        cards = [
            self._badge_card(badge, editable=can_edit)
            for badge in badges
        ]
        body = ft.ResponsiveRow(
            [
                ft.Container(card, col={"xs": 12, "sm": 6, "md": 4})
                for card in cards
            ],
            spacing=8,
            run_spacing=8,
        ) if cards else ft.Text(
            "还没有考级或竞赛徽章。",
            size=12,
            color=ft.Colors.GREY_600,
        )
        return self._section(
            title,
            body,
            action=(
                ft.Button(
                    "添加徽章",
                    icon=ft.Icons.ADD,
                    on_click=lambda e: self._open_badge_dialog(student_id=s["id"]),
                )
                if can_edit
                else None
            ),
        )

    def _open_badge_dialog(
        self,
        badge: dict | None = None,
        *,
        student_id: int | None = None,
    ) -> None:
        editing = badge is not None
        target_student_id = int(badge["student_id"] if editing else student_id or 0)
        if not self._can_manage_student(target_student_id):
            self._toast("只能维护自己学员的徽章")
            return
        category = _dd(
            "徽章类别",
            _opts([(value, value) for value in db.BADGE_CATEGORIES]),
            value=badge["category"] if editing else "竞赛",
            width=DIALOG_WIDTH,
        )
        configured_levels = [
            level
            for level in db.list_levels(active_only=True)
            if level["badge_category"]
        ]

        def linked_options(category_value: str) -> list[ft.DropdownOption]:
            return [ft.DropdownOption(key="", text="不关联等级")] + _opts(
                [
                    (level["id"], db.level_display_name(level))
                    for level in configured_levels
                    if level["badge_category"] == category_value
                ]
            )

        initial_category = badge["category"] if editing else "竞赛"
        linked_level = _dd(
            "关联等级（可选）",
            linked_options(initial_category),
            value=(
                str(badge["level_id"])
                if editing and badge.get("level_id")
                else ""
            ),
            width=DIALOG_WIDTH,
        )
        title = _tf(
            "比赛／考级名称 *",
            badge["title"] if editing else "",
            width=DIALOG_WIDTH,
        )
        competition_level = _tf(
            "竞赛组别",
            (
                badge["level_name"]
                if editing and badge["category"] == "竞赛"
                else ""
            ),
            width=DIALOG_WIDTH,
            hint_text="例如：小低组、小学组",
            visible=(badge["category"] if editing else "竞赛") == "竞赛",
        )
        exam_level = _dd(
            "考级级别",
            _opts([(value, value) for value in db.EXAM_LEVELS]),
            value=(
                badge["level_name"]
                if editing
                and badge["category"] == "考级"
                and badge["level_name"] in db.EXAM_LEVELS
                else db.EXAM_LEVELS[0]
            ),
            width=DIALOG_WIDTH,
            visible=(badge["category"] if editing else "竞赛") == "考级",
        )
        result = _dd(
            "结果",
            _opts(
                [
                    (value, value)
                    for value in (
                        db.COMPETITION_RESULTS
                        if (badge["category"] if editing else "竞赛") == "竞赛"
                        else db.EXAM_RESULTS
                    )
                ]
            ),
            value=badge["result"] if editing else "一等奖",
            width=DIALOG_WIDTH,
        )
        happened_on = _tf(
            "日期",
            badge["happened_on"] if editing else date.today().isoformat(),
            width=DIALOG_WIDTH,
        )
        note = _tf(
            "说明（可不填）",
            badge["note"] if editing else "",
            width=DIALOG_WIDTH,
            multiline=True,
            min_lines=2,
            max_lines=4,
        )

        def on_category(e=None) -> None:
            is_exam = category.value == "考级"
            competition_level.visible = not is_exam
            exam_level.visible = is_exam
            linked_level.options = linked_options(category.value or "")
            if linked_level.value and not any(
                str(option.key) == str(linked_level.value)
                for option in linked_level.options
            ):
                linked_level.value = ""
            choices = (
                db.EXAM_RESULTS if is_exam else db.COMPETITION_RESULTS
            )
            result.options = _opts([(value, value) for value in choices])
            if result.value not in choices:
                result.value = choices[0]
            result.update()
            competition_level.update()
            exam_level.update()
            linked_level.update()

        category.on_select = on_category

        def on_linked_level(e=None) -> None:
            level = next(
                (
                    row
                    for row in configured_levels
                    if str(row["id"]) == str(linked_level.value or "")
                ),
                None,
            )
            if level is None:
                return
            if category.value == "考级":
                if level["badge_exam_level"] in db.EXAM_LEVELS:
                    exam_level.value = level["badge_exam_level"]
                    exam_level.update()
            else:
                competition_level.value = level["name"] or competition_level.value
                competition_level.update()

        linked_level.on_select = on_linked_level

        def save(e):
            try:
                db.save_student_badge(
                    target_student_id,
                    category.value or "",
                    title.value or "",
                    (
                        exam_level.value or ""
                        if category.value == "考级"
                        else competition_level.value or ""
                    ),
                    result.value or "",
                    happened_on.value or "",
                    note.value or "",
                    badge["id"] if editing else None,
                    int(linked_level.value)
                    if (linked_level.value or "").strip()
                    else None,
                )
            except ValueError as err:
                title.error = str(err)
                title.update()
                return
            self._finish("徽章已保存")

        self._show(
            self._dialog(
                "编辑徽章" if editing else "添加徽章",
                self._form_column(
                    [
                        category,
                        linked_level,
                        title,
                        competition_level,
                        exam_level,
                        result,
                        happened_on,
                        note,
                    ]
                ),
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )


__all__ = ["BadgesMixin"]
