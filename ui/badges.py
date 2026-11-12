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
                for teacher_id in (
                    (item.get("teacher_ids") or [])
                    + (item.get("manual_award_teacher_ids") or [])
                )
            }
        )

    def _manual_award_candidates(
        self, participants: list[dict], *, category: str
    ) -> list[dict]:
        """可补录的参赛学生：只列当前老师自己管理、还没关联到该级别的孩子。"""
        if category != "竞赛":
            return []
        linked_ids = {int(student["id"]) for student in participants}
        return [
            dict(student)
            for student in db.list_students(status="在读")
            if int(student["id"]) not in linked_ids
            and self._can_manage_student(int(student["id"]))
        ]

    def _badge_directory_view(self) -> ft.Control:
        levels = [
            level
            for level in db.list_levels()
            if db.badge_category_for_level(level)
        ]
        award_projects: dict[tuple[str, str], list[dict]] = {}
        for level in levels:
            category = db.badge_category_for_level(level)
            project_key = (
                (level["badge_event_name"] or "").strip()
                or f"level:{int(level['id'])}"
            )
            award_projects.setdefault(
                (category, project_key), []
            ).append(dict(level))
        competition_count = sum(
            1 for category, _ in award_projects if category == "竞赛"
        )
        exam_count = sum(
            1 for category, _ in award_projects if category == "考级"
        )
        groups: list[ft.Control] = []
        for category in db.BADGE_CATEGORIES:
            category_label = self._directory_category_label(category)
            cards = [
                self._badge_award_project_card(project_levels, category)
                for (project_category, _), project_levels in award_projects.items()
                if project_category == category
            ]
            count_text = len(cards)
            groups.append(
                self._section(
                    f"{category_label}目录（{count_text}）",
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
                        "竞技按「比赛名称」汇总，考级按「考级名称」汇总；"
                        "同一场活动的不同组别会放在一张卡片里一起颁发。"
                        "报名、缴费或上过对应课程的学员会自动出现。"
                        "没报竞赛课但实际参赛的孩子，可以在颁发时补录。"
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

    def _badge_award_project_card(
        self, levels: list[dict], category: str
    ) -> ft.Container:
        levels = [dict(level) for level in levels]
        if not levels:
            return ft.Container()
        project_name = (
            (levels[0].get("badge_event_name") or "").strip()
            or "未命名比赛／考级"
        )
        category_label = self._directory_category_label(category)
        participants: list[dict] = []
        awards: list[dict] = []
        for level in levels:
            for student in db.list_badge_level_participants(level["id"]):
                item = dict(student)
                item["award_level_id"] = int(level["id"])
                item["award_group_name"] = db.badge_group_name(level)
                participants.append(item)
            for badge in db.list_level_badges(level["id"]):
                item = dict(badge)
                item["award_group_name"] = db.badge_group_name(level)
                awards.append(item)
        manageable = [
            student
            for student in participants
            if self._can_award_badge_student(student)
        ]
        manual_candidates = self._manual_award_candidates(
            participants, category=category
        )
        group_names = "、".join(
            dict.fromkeys(
                name
                for level in levels
                if (name := db.badge_group_name(level))
            )
        )
        detail = " · ".join(
            [
                f"{len(levels)} 个组别",
                group_names,
                f"已关联 {len(participants)} 人",
                f"已颁发 {len(awards)} 枚",
            ]
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
                            f"{student['award_group_name']} · "
                            + " · ".join(
                                part
                                for part in [
                                    student.get("grade") or "",
                                    student.get("school") or "",
                                ]
                                if part
                            ),
                            size=11,
                            color=ft.Colors.GREY_600,
                            expand=True,
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
        award_rows = [self._level_award_row(badge) for badge in awards]
        action = (
            ft.Button(
                "本场颁发",
                icon=ft.Icons.MILITARY_TECH,
                on_click=lambda e: self._open_badge_award_dialog(levels),
            )
            if manageable or manual_candidates
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
                                        f"{project_name} · {category_label}",
                                        size=15,
                                        weight=ft.FontWeight.W_700,
                                    ),
                                    ft.Text(
                                        detail,
                                        size=12,
                                        color=ft.Colors.GREY_600,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            *([action] if action else []),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        "关联学员",
                        size=12,
                        weight=ft.FontWeight.W_600,
                    ),
                    ft.Column(
                        participant_rows
                        or [
                            ft.Text(
                                "还没有关联学员。报名对应组别、缴费、上课或颁发后会自动出现。",
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
                spacing=10,
            )
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
        manual_candidates = self._manual_award_candidates(
            participants, category=category
        )
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
                            "还没有关联学员。给学员报名该级别、缴对应课时或上对应课程后，会自动出现；"
                            "比赛时也可以从「本场颁发」补录自己名下的学员。",
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
            if manageable or manual_candidates
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
                            f" · {badge['award_group_name']}"
                            if badge.get("award_group_name")
                            else ""
                        )
                        + (
                            f" · {_date_text(badge['happened_on'])}"
                            if badge.get("happened_on")
                            else ""
                        ),
                        expand=True,
                        size=11,
                        color=ft.Colors.GREY_700,
                    ),
                    *(
                        [
                            ft.Text(
                                f"+{db.num_text(badge['points_awarded'])} 分",
                                size=11,
                                weight=ft.FontWeight.W_700,
                                color=ft.Colors.GREEN_700,
                            )
                        ]
                        if badge.get("category") == "竞赛"
                        and float(badge.get("points_awarded") or 0) > 0
                        else []
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
        self._open_badge_award_dialog([level])

    def _open_badge_award_dialog(self, levels: list[dict]) -> None:
        levels = [dict(level) for level in levels]
        if not levels:
            return
        category = db.badge_category_for_level(levels[0])
        if any(db.badge_category_for_level(level) != category for level in levels):
            self._toast("本场颁发只能包含同一种竞技或考级结果")
            return
        participants = [
            dict(student, award_level_id=int(level["id"]))
            for level in levels
            for student in db.list_badge_level_participants(level["id"])
        ]
        manageable = [
            student
            for student in participants
            if self._can_award_badge_student(student)
        ]
        manual_candidates = self._manual_award_candidates(
            participants, category=category
        )
        if not manageable and not manual_candidates:
            self._toast("这个级别里没有你可以颁发的学员")
            return
        category_label = self._directory_category_label(category)
        project_name = (
            (levels[0].get("badge_event_name") or "").strip()
            or (
                db.badge_group_name(levels[0])
                if category == "竞赛"
                else db.level_display_name(levels[0])
            )
        )
        levels_by_id = {int(level["id"]): level for level in levels}
        choices = (
            db.COMPETITION_RESULTS
            if category == "竞赛"
            else db.EXAM_RESULTS
        )
        title = _tf(
            "比赛／考级名称 *",
            f"{project_name} {category_label}",
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
        point_fields: dict[str, ft.TextField] = {}
        if category == "竞赛":
            for choice in choices:
                point_fields[choice] = _tf(
                    f"{choice}积分",
                    "0",
                    width=100,
                    keyboard_type=ft.KeyboardType.NUMBER,
                )

        rows: list[
            tuple[dict, dict, ft.Checkbox, ft.Dropdown, ft.Text, bool]
        ] = []
        rows_column = ft.Column([], spacing=6)

        def update_point_hint(row) -> None:
            _, _, _, result, hint, _ = row
            if category != "竞赛" or not result.value:
                hint.value = ""
            else:
                field = point_fields.get(result.value)
                try:
                    points = float((field.value or "").strip()) if field else 0
                except ValueError:
                    hint.value = "积分待填写"
                else:
                    hint.value = (
                        f"+{db.num_text(points)} 分" if points > 0 else "0 分"
                    )
            hint.update()

        def refresh_point_hints(e=None) -> None:
            for row in rows:
                update_point_hint(row)

        for field in point_fields.values():
            field.on_change = refresh_point_hints

        def add_student_row(
            level: dict,
            student: dict,
            *,
            selected_value: bool,
            manual: bool = False,
            refresh: bool = False,
        ) -> None:
            group_name = db.badge_group_name(level)
            checkbox_label = (
                f"{student['name']}（{group_name}）"
                if len(levels) > 1
                else student["name"]
            )
            selected = ft.Checkbox(label=checkbox_label, value=False)
            result = _dd(
                f"{student['name']}的结果",
                [ft.DropdownOption(key="", text="请选择结果")]
                + _opts([(value, value) for value in choices]),
                value="",
                width=160,
            )
            selected.value = selected_value
            hint = ft.Text("", size=11, color=ft.Colors.GREEN_700, width=72)
            row = (level, student, selected, result, hint, manual)
            rows.append(row)
            result.on_select = lambda e, current=row: update_point_hint(current)
            rows_column.controls.append(
                ft.Container(
                    ft.Row(
                        [
                            selected,
                            ft.Text(
                                group_name,
                                size=10,
                                color=ft.Colors.BLUE_700,
                                width=110,
                            ),
                            result,
                            hint,
                            *(
                                [
                                    ft.Text(
                                        "补录",
                                        size=10,
                                        color=ft.Colors.BLUE_700,
                                    )
                                ]
                                if manual
                                else []
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                    border_radius=8,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
            if refresh:
                rows_column.update()

        for student in manageable:
            add_student_row(
                levels_by_id[int(student["award_level_id"])],
                student,
                selected_value=False,
            )

        manual_picker: ft.Dropdown | None = None
        manual_group_picker: ft.Dropdown | None = None
        add_manual_button: ft.Button | None = None
        if manual_candidates:
            manual_picker = _dd(
                "补录参赛学生",
                _opts(
                    [
                        (
                            student["id"],
                            student["name"]
                            + (f"（{student['grade']}）" if student.get("grade") else ""),
                        )
                        for student in manual_candidates
                    ]
                ),
                value="",
                width=DIALOG_WIDTH if len(levels) == 1 else None,
            )
            if len(levels) > 1:
                manual_picker.expand = True
                manual_group_picker = _dd(
                    "补录组别",
                    _opts(
                        [
                            (level["id"], db.badge_group_name(level))
                            for level in levels
                        ]
                    ),
                    value=str(levels[0]["id"]),
                    width=180,
                )

            def add_manual_student(e=None) -> None:
                student = next(
                    (
                        row
                        for row in manual_candidates
                        if str(row["id"]) == str(manual_picker.value or "")
                    ),
                    None,
                )
                if student is None:
                    self._toast("请先选择要补录的学员")
                    return
                level = levels_by_id.get(
                    int(
                        manual_group_picker.value
                        if manual_group_picker is not None
                        else levels[0]["id"]
                    )
                )
                if level is None:
                    self._toast("请选择补录到哪个组别")
                    return
                add_student_row(
                    level,
                    student,
                    selected_value=True,
                    manual=True,
                    refresh=True,
                )
                manual_picker.options = [
                    option
                    for option in manual_picker.options
                    if str(option.key) != str(student["id"])
                ]
                manual_picker.value = ""
                manual_picker.update()

            add_manual_button = ft.Button(
                "加入本场",
                icon=ft.Icons.PERSON_ADD,
                on_click=add_manual_student,
            )

        def read_award_points() -> dict[str, float] | None:
            points: dict[str, float] = {}
            for result, field in point_fields.items():
                raw = (field.value or "").strip() or "0"
                try:
                    value = float(raw)
                except ValueError:
                    field.error = "请填数字"
                    field.update()
                    return None
                if value < 0:
                    field.error = "不能小于 0"
                    field.update()
                    return None
                field.error = ""
                points[result] = value
            return points

        def save(e=None) -> None:
            awards_by_level: dict[int, dict[int, str]] = {}
            extras_by_level: dict[int, set[int]] = {}
            selected_results: list[str] = []
            for level, student, selected, result, _, manual in rows:
                if selected.value:
                    level_id = int(level["id"])
                    awards_by_level.setdefault(level_id, {})[
                        int(student["id"])
                    ] = result.value or ""
                    selected_results.append(result.value or "")
                    if manual:
                        extras_by_level.setdefault(level_id, set()).add(
                            int(student["id"])
                        )
            if not awards_by_level:
                self._toast("请先勾选本次获得结果的学员")
                return
            if any(not result for result in selected_results):
                self._toast("勾选的学员都要选择比赛或考级结果")
                return
            points_by_result = read_award_points() if category == "竞赛" else None
            if category == "竞赛" and points_by_result is None:
                return
            try:
                count = 0
                for level_id, awards in awards_by_level.items():
                    count += db.save_badge_awards_for_level(
                        level_id,
                        title.value or "",
                        awards,
                        happened_on.value or "",
                        note.value or "",
                        points_by_result=points_by_result,
                        extra_student_ids=extras_by_level.get(level_id, set()),
                        awarded_by_user_id=self._my_user_id(),
                    )
            except ValueError as err:
                title.error = str(err)
                title.update()
                return
            if category == "竞赛":
                total_points = sum(
                    (points_by_result or {}).get(result, 0)
                    for result in selected_results
                )
                message = (
                    f"已为 {count} 名学员颁发{category_label}结果，"
                    f"发放 {db.num_text(total_points)} 积分"
                )
            else:
                message = f"已为 {count} 名学员颁发{category_label}结果"
            self._finish(message)

        self._show(
            self._dialog(
                f"颁发{category_label}结果",
                self._form_column(
                    [
                        ft.Text(
                            f"{project_name} · 本次可颁发 "
                            f"{len(manageable)} 人"
                            + (
                                f" · 可补录 {len(manual_candidates)} 人"
                                if manual_candidates
                                else ""
                            ),
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                        title,
                        happened_on,
                        *(
                            [
                                ft.Text(
                                    "本场奖励积分",
                                    size=12,
                                    weight=ft.FontWeight.W_600,
                                ),
                                ft.Row(
                                    list(point_fields.values()),
                                    spacing=8,
                                    wrap=True,
                                ),
                            ]
                            if point_fields
                            else []
                        ),
                        *(
                            [
                                ft.Text(
                                    "没报竞赛课但参加了比赛的孩子，可以从这里补录。",
                                    size=11,
                                    color=ft.Colors.GREY_600,
                                ),
                                ft.Row(
                                    [
                                        manual_picker,
                                        *(
                                            [manual_group_picker]
                                            if manual_group_picker is not None
                                            else []
                                        ),
                                        add_manual_button,
                                    ],
                                    spacing=8,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                            ]
                            if manual_picker is not None
                            else []
                        ),
                        ft.Text(
                            "勾选本次参赛、需要颁证的学员",
                            size=12,
                            weight=ft.FontWeight.W_600,
                        ),
                        rows_column,
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
        if result == "鼓励奖":
            return ft.Colors.GREEN_50, ft.Colors.GREEN_700
        return ft.Colors.BLUE_50, ft.Colors.BLUE_700

    def _badge_card(self, badge: dict, *, editable: bool = False) -> ft.Control:
        bgcolor, color = self._badge_colors(badge)
        bits = [
            badge.get("title") or badge.get("category"),
            badge.get("level_name") or "",
            (
                f"奖励 +{db.num_text(badge.get('points_awarded'))} 分"
                if badge.get("category") == "竞赛"
                and float(badge.get("points_awarded") or 0) > 0
                else ""
            ),
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
        points_awarded = _tf(
            "本次奖励积分",
            (
                db.num_text(badge.get("points_awarded"))
                if editing and float(badge.get("points_awarded") or 0)
                else "0"
            ),
            width=DIALOG_WIDTH,
            keyboard_type=ft.KeyboardType.NUMBER,
            visible=(badge["category"] if editing else "竞赛") == "竞赛",
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
            points_awarded.visible = not is_exam
            points_awarded.update()
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
            points = 0.0
            if category.value == "竞赛":
                try:
                    points = float((points_awarded.value or "").strip() or "0")
                except ValueError:
                    points_awarded.error = "请填数字"
                    points_awarded.update()
                    return
                if points < 0:
                    points_awarded.error = "不能小于 0"
                    points_awarded.update()
                    return
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
                    points_awarded=points if category.value == "竞赛" else 0,
                    awarded_by_user_id=self._my_user_id(),
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
                        points_awarded,
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
