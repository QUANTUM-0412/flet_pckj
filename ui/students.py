"""学员列表与学员详情。"""

from __future__ import annotations

from datetime import date

import flet as ft

import db
from .common import (
    DIALOG_WIDTH,
    STATUS_FILTERS,
    WARN_BALANCE,
    _chip,
    _dd,
    _grade_opts,
    _level_title,
    _opts,
    _school_inputs,
    _status_opts,
    _tf,
)


class StudentsMixin:
    """学员列表与学员详情（ClassHoursApp 的一部分）。"""

    # ------------------------------------------- 学员信息输入（几处对话框共用）

    def _student_fields(
        self,
        data: dict | None = None,
        *,
        readonly: bool = False,
        with_status: bool = True,
        with_note: bool = True,
        width=None,
    ) -> dict[str, ft.Control]:
        """姓名／性别／年级／学校／电话（／状态／备注）一组输入控件。

        新增学员、学员档案、缴费时顺手建档都用这一套，省得几处各写一遍。
        """
        s = data or {}
        school_box, school_field = _school_inputs(s.get("school", ""), width)
        fields: dict[str, ft.Control] = {
            "name": _tf("姓名 *", s.get("name", ""), width=width),
            "gender": _dd(
                "性别",
                _opts([(g, g) for g in db.GENDER_OPTIONS]),
                value=s.get("gender") or None,
                width=width,
            ),
            "grade": _dd("年级", _grade_opts(), value=s.get("grade") or None, width=width),
            "birth_date": _tf(
                "出生日期",
                s.get("birth_date", ""),
                width=width,
                hint_text="2020-05-18",
            ),
            "school": school_box,
            "phone": _tf("联系电话", s.get("phone", ""), width=width),
            "guardian": _tf("监护人姓名", s.get("guardian", ""), width=width),
            "owner": _dd(
                "归属老师（可改）",
                [
                    ft.DropdownOption(key="auto", text="跟缴费走（自动）"),
                    ft.DropdownOption(key="", text="不指定"),
                ]
                + _opts(
                    [
                        (t["id"], t["display_name"] or t["username"])
                        for t in db.list_teachers()
                    ]
                ),
                value=(
                    (str(s.get("owner_teacher_id")) if s.get("owner_teacher_id") else "")
                    if s.get("owner_manual")
                    else "auto"
                ),
                width=width,
            ),
        }
        def sync_grade_from_birth(e=None) -> None:
            raw = (fields["birth_date"].value or "").strip()
            inferred = db.grade_from_birth_date(raw) if raw else ""
            if raw:
                fields["grade"].disabled = True
                if inferred:
                    fields["grade"].value = inferred
                fields["grade"].update()
            else:
                fields["grade"].disabled = False
                fields["grade"].update()

        fields["birth_date"].on_change = sync_grade_from_birth
        fields["grade"].disabled = bool((s.get("birth_date") or "").strip())
        # 学校是"输入框 + 下拉"一对，取值只看里面的输入框
        fields["school_input"] = school_field
        if with_status:
            fields["status"] = _dd(
                "状态", _status_opts(), value=s.get("status") or "在读", width=width
            )
        if with_note:
            fields["note"] = _tf(
                "备注",
                s.get("note", ""),
                width=width,
                multiline=True,
                min_lines=2,
                max_lines=5,
            )
        if readonly:
            for field in fields.values():
                field.disabled = True
            for inner in getattr(fields["school"], "controls", []):
                inner.disabled = True
        return fields

    def _student_values(
        self, fields: dict, *, require_birth_date: bool = False
    ) -> dict | None:
        """把输入控件里的值取出来；姓名没填就标红并返回 None。"""
        name = (fields["name"].value or "").strip()
        if not name:
            fields["name"].error = "请填姓名"
            fields["name"].update()
            return None
        values = {
            "name": name,
            "gender": fields["gender"].value or "",
            "grade": fields["grade"].value or "",
            "birth_date": (fields["birth_date"].value or "").strip(),
            "school": (fields["school_input"].value or "").strip(),
            "phone": fields["phone"].value or "",
        }
        if values["birth_date"]:
            try:
                date.fromisoformat(values["birth_date"])
            except ValueError:
                fields["birth_date"].error = "写成 2020-05-18 这样"
                fields["birth_date"].update()
                return None
        elif require_birth_date:
            fields["birth_date"].error = "新学员请先绑定出生日期"
            fields["birth_date"].update()
            return None
        if values["birth_date"]:
            values["grade"] = db.grade_from_birth_date(values["birth_date"])
        if "guardian" in fields:
            values["guardian"] = fields["guardian"].value or ""
        if "owner" in fields:
            raw = (fields["owner"].value or "").strip()
            if raw == "auto":
                values["owner_teacher_id"] = None
                values["owner_manual"] = False
            else:
                values["owner_teacher_id"] = int(raw) if raw else None
                values["owner_manual"] = True
        if "status" in fields:
            values["status"] = fields["status"].value or "在读"
        if "note" in fields:
            values["note"] = fields["note"].value or ""
        return values

    def _students_view(self) -> ft.Column:
        db.advance_student_grades()
        db.sync_course_statuses()  # 课程到期了就自动结课，进来先过一遍
        wide = self.is_wide()
        if self.filter_owner is None:
            self._apply_user_defaults()
        rows = db.list_students_with_summary(
            keyword=self.keyword,
            status=self.status_filter,
            grade=self.filter_grade,
            school=self.filter_school,
            owner=self.filter_owner,
        )
        pending_ids = db.students_with_pending_makeups()

        search = ft.TextField(
            value=self.keyword,
            hint_text="搜姓名 / 电话 / 年级 / 学校 / 备注（随便敲）",
            dense=True,
            prefix_icon=ft.Icons.SEARCH,
            expand=True,
            on_submit=self._on_search_submit,
        )
        grade_dd = _dd(
            "年级",
            [ft.DropdownOption(key="", text="全部")] + _grade_opts(),
            value=self.filter_grade or "",
            width=110 if wide else 280,
            on_select=lambda e: filter_changed(),
        )
        school_dd = _dd(
            "学校",
            [ft.DropdownOption(key="", text="全部")]
            + _opts([(s, s) for s in db.list_schools()]),
            value=self.filter_school or "",
            width=130 if wide else 280,
            on_select=lambda e: filter_changed(),
        )
        owner_dd = _dd(
            "归属老师",
            [
                ft.DropdownOption(key="", text="全部"),
                ft.DropdownOption(key="__none__", text="未指定"),
            ]
            + _opts(
                [
                    (t["id"], t["display_name"] or t["username"])
                    for t in db.list_teachers()
                ]
            ),
            value=self.filter_owner or "",
            width=130 if wide else 280,
            on_select=lambda e: filter_changed(),
        )
        status_dd = _dd(
            "状态",
            _opts(STATUS_FILTERS),
            value=self.status_filter or "全部",
            width=120 if wide else 280,
            on_select=lambda e: filter_changed(),
        )

        def store_filters() -> None:
            self.filter_grade = grade_dd.value or ""
            self.filter_school = school_dd.value or ""
            self.filter_owner = owner_dd.value or ""
            self.status_filter = dict(STATUS_FILTERS).get(status_dd.value or "全部", "")

        def apply_filters() -> None:
            store_filters()
            self.render()

        def filter_changed() -> None:
            if wide:
                apply_filters()
            else:
                store_filters()

        def clear_filters(e=None) -> None:
            self.keyword = ""
            self.filter_grade = ""
            self.filter_school = ""
            self.filter_owner = ""
            self.status_filter = ""
            self.render()

        def close_filter_sheet() -> None:
            self.page.pop_dialog()

        def apply_mobile_filters(e=None) -> None:
            store_filters()
            close_filter_sheet()
            self.render()

        def clear_mobile_filters(e=None) -> None:
            self.keyword = ""
            self.filter_grade = ""
            self.filter_school = ""
            self.filter_owner = ""
            self.status_filter = ""
            close_filter_sheet()
            self.render()

        def active_filter_count() -> int:
            return sum(
                bool(value)
                for value in (
                    self.filter_grade,
                    self.filter_school,
                    self.filter_owner,
                    self.status_filter,
                )
            )

        def open_filter_sheet(e=None) -> None:
            if not wide:
                for control in (grade_dd, school_dd, owner_dd, status_dd):
                    control.col = {"xs": 12, "sm": 6}
            sheet = ft.BottomSheet(
                content=ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        "筛选学员",
                                        size=20,
                                        weight=ft.FontWeight.BOLD,
                                        expand=True,
                                    ),
                                    ft.IconButton(
                                        ft.Icons.CLOSE,
                                        tooltip="关闭",
                                        on_click=self._close,
                                    ),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.ResponsiveRow(
                                [grade_dd, school_dd, owner_dd, status_dd],
                                spacing=8,
                                run_spacing=8,
                            ),
                            ft.Row(
                                [
                                    ft.TextButton(
                                        "清空",
                                        icon=ft.Icons.FILTER_ALT_OFF,
                                        on_click=clear_mobile_filters,
                                    ),
                                    ft.Container(expand=True),
                                    ft.Button(
                                        "查看结果",
                                        height=48,
                                        on_click=apply_mobile_filters,
                                    ),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=14,
                        tight=True,
                    ),
                    padding=ft.Padding(left=16, top=8, right=16, bottom=24),
                ),
                show_drag_handle=True,
                use_safe_area=True,
                scrollable=True,
            )
            self._show(sheet)

        filter_row = ft.Row(
            [
                grade_dd,
                school_dd,
                owner_dd,
                status_dd,
                ft.TextButton(
                    "清空筛选", icon=ft.Icons.FILTER_ALT_OFF, on_click=clear_filters
                ),
            ],
            spacing=8,
            wrap=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        filter_count = active_filter_count()
        filter_button = ft.Button(
            f"筛选 · {filter_count}" if filter_count else "筛选",
            icon=ft.Icons.FILTER_ALT,
            height=48,
            on_click=open_filter_sheet,
        )
        cards = [self._student_card(item, pending_ids) for item in rows]
        if not cards:
            has_any_student = bool(db.list_students())
            cards = [
                self._card(
                    ft.Column(
                        [
                            ft.Icon(ft.Icons.PERSON_ADD_ALT, size=36, color=ft.Colors.GREY_400),
                            ft.Text(
                                "没有符合条件的学员" if has_any_student else "还没有学员",
                                color=ft.Colors.GREY_600,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    )
                )
            ]

        search_controls = (
            ft.Row([search], spacing=10)
            if wide
            else ft.Row(
                [search, filter_button],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
        is_my_default = (
            self.user
            and self.user.get("role") == db.ROLE_TEACHER
            and self.filter_owner == str(self._my_user_id())
        )
        return ft.Column(
            [
                self._header(
                    "学员",
                    (
                        f"我的学员 · {len(rows)} 人"
                        if is_my_default
                        else f"共 {len(rows)} 人"
                    ),
                    [
                        ft.Button(
                            "新增学员",
                            icon=ft.Icons.PERSON_ADD,
                            on_click=lambda e: self._open_new_student(),
                        )
                    ],
                ),
                search_controls,
                *([filter_row] if wide else []),
                *cards,
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _student_card(self, item: dict, pending_ids: set[int] | None = None) -> ft.Container:
        s = item["student"]
        pending_ids = pending_ids or set()
        all_enrollments = item["enrollments"]
        enrollments = [e for e in all_enrollments if e["status"] == "在读"]

        def course_bit(e: dict) -> str:
            cls_label = db.enrollment_class_label(e)
            bit = _level_title(e)
            if cls_label:
                bit += f"（{cls_label}）"
            elif e["status"] != "在读":
                bit += f"（{e['class_type_name']}）"
            if e["status"] != "在读":
                bit += f"·{e['status']}"
            return bit

        course_text = "、".join(course_bit(e) for e in all_enrollments) or "还没报课"
        owners = [
            row["name"] for row in db.student_owners(s["id"]) if row.get("name")
        ]
        owner_text = "、".join(owners)
        meta = " · ".join(x for x in [s["grade"], s["school"], s["phone"]] if x) or "—"
        hours = db.hours_text(item["accounts"])
        points = db.num_text(item.get("points") or 0)
        warn = bool(db.warning_accounts(item["accounts"]))

        badges = []
        if s["id"] in pending_ids:
            badges.append(_chip("待补课", ft.Colors.ORANGE_700))
        if all_enrollments and all(e["status"] == "结课" for e in all_enrollments):
            badges.append(_chip("课都结课了", ft.Colors.GREY_500))
        if s["status"] != "在读":
            badges.append(
                _chip(
                    s["status"],
                    ft.Colors.ORANGE_700
                    if s["status"] == "停课"
                    else ft.Colors.GREY_500,
                )
            )
        if warn:
            badges.append(ft.Icon(ft.Icons.ERROR_OUTLINE, size=16, color=ft.Colors.ORANGE_700))

        return ft.Container(
            content=ft.Row(
                [
                    ft.CircleAvatar(
                        content=ft.Text((s["name"] or "?")[:1]),
                        bgcolor=ft.Colors.BLUE_100,
                        color=ft.Colors.BLUE_800,
                    ),
                    ft.Column(
                        [
                            ft.Row(
                                [ft.Text(s["name"], size=15, weight=ft.FontWeight.W_600), *badges],
                                spacing=6,
                                tight=True,
                            ),
                            ft.Text(meta, size=12, color=ft.Colors.GREY_600),
                            ft.Text(f"课程：{course_text}", size=12, color=ft.Colors.GREY_600),
                            *(
                                [
                                    ft.Text(
                                        f"归属老师：{owner_text}",
                                        size=12,
                                        color=ft.Colors.BLUE_700,
                                    )
                                ]
                                if owner_text
                                else []
                            ),
                            ft.Text(f"课时：{hours} ｜ 积分：{points}", size=12, color=ft.Colors.GREY_600),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=ft.Colors.GREY_400),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, ft.Colors.GREY_300),
            ink=True,
            on_click=lambda e, sid=s["id"]: self.open_student(sid),
        )

    def _on_search_submit(self, e) -> None:
        self.keyword = (e.control.value or "").strip()
        self.render()

    def _on_status_select(self, e) -> None:
        label = e.control.value or "全部"
        self.status_filter = dict(STATUS_FILTERS).get(label, "")
        self.render()

    def _student_detail_view(self, student_id: int) -> ft.Column:
        s = db.get_student(student_id)
        if not s:
            self.student_id = None
            return self._students_view()

        accounts = db.get_accounts(student_id)
        enrollments = db.list_enrollments(student_id)
        points = db.student_points(student_id)

        back = ft.IconButton(
            ft.Icons.ARROW_BACK,
            tooltip="返回学员列表",
            on_click=lambda e: self.open_student(None),
        )
        header = ft.Row(
            [
                back,
                ft.Column(
                    [
                        ft.Text(s["name"], size=20, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            " · ".join(
                                x
                                for x in [
                                    s["status"],
                                    s["grade"],
                                    s["phone"],
                                    f"积分 {db.num_text(points)}",
                                ]
                                if x
                            ),
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Column(
            [
                header,
                self._student_makeups_card(s),
                self._profile_card(s, enrollments),
                self._student_badges_card(s),
                self._student_account_card(s),
                self._hours_card(s, accounts),
                self._enrollments_card(student_id, enrollments),
                self._student_lessons_card(s),
                self._payments_card(s),
                self._vouchers_card(s),
                self._points_card(s),
                self._danger_card(s),
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _profile_card(self, s: dict, enrollments: list[dict] | None = None) -> ft.Container:
        admin = self.is_admin()
        can_edit = self._can_manage_student(s["id"])
        editing = bool(can_edit and self._student_edit_id == s["id"])

        def owner_now() -> str:
            rows = [r for r in db.student_owners(s["id"]) if r.get("name")]
            if not rows:
                return "现在归属：还没定"
            names = "、".join(r["name"] for r in rows)
            source = {
                "缴费": "按缴费",
                "课程": "按课程（还没交过费）",
                "手动": "手动指定",
            }.get(rows[0]["source"], "")
            return f"现在归属：{names}" + (f"（{source}）" if source else "")

        def start_edit(e=None):
            self._student_edit_id = s["id"]
            self.render()

        def cancel_edit(e=None):
            self._student_edit_id = None
            self.render()

        if not editing:
            visible_rows = [
                ("姓名", s.get("name") or "—"),
                ("性别", s.get("gender") or "—"),
                ("状态", s.get("status") or "—"),
                ("年级", s.get("grade") or "—"),
                ("出生日期", s.get("birth_date") or "—"),
                ("学校", s.get("school") or "—"),
                ("联系电话", s.get("phone") or "—"),
                ("监护人", s.get("guardian") or "—"),
                ("归属", owner_now().removeprefix("现在归属：")),
                ("备注", s.get("note") or "—"),
            ]
            body = ft.ResponsiveRow(
                [
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    label,
                                    size=11,
                                    color=ft.Colors.GREY_600,
                                ),
                                ft.Text(value, size=13),
                            ],
                            spacing=2,
                            tight=True,
                        ),
                        col={"xs": 12, "sm": 6, "md": 4, "lg": 3},
                        padding=ft.Padding.symmetric(horizontal=12, vertical=9),
                        border_radius=10,
                        bgcolor=ft.Colors.GREY_50,
                    )
                    for label, value in visible_rows
                ],
                spacing=8,
                run_spacing=8,
            )
            action = (
                ft.TextButton(
                    "编辑",
                    icon=ft.Icons.EDIT,
                    on_click=start_edit,
                )
                if can_edit
                else None
            )
            return self._section("基本档案", body, action=action)

        fields = self._student_fields(s)
        if not admin:
            fields["owner"].disabled = True
            fields["owner"].label = "归属老师（由管理员管理）"

        def save(e):
            if not self._can_manage_student(s["id"]):
                self._toast("这是其他老师的学员，只能查看")
                return
            values = self._student_values(fields)
            if values is None:
                return
            if not admin:
                # 普通老师可以维护自己学员的资料，但不能把归属改给别的老师。
                values.pop("owner_teacher_id", None)
                values.pop("owner_manual", None)
            db.update_student(s["id"], values)
            self._student_edit_id = None
            self._finish("档案已保存")

        controls = [
            fields["name"],
            ft.Row([fields["gender"], fields["status"]], spacing=10, expand=False),
            ft.Row(
                [fields["grade"], fields["birth_date"]],
                spacing=10,
                expand=False,
            ),
            fields["school"],
            ft.Row([fields["phone"], fields["guardian"]], spacing=10, expand=False),
            ft.Text(owner_now(), size=13, weight=ft.FontWeight.W_600),
            ft.Text(
                (
                    "归属默认跟缴费走（谁收的钱，这个客户就算谁的）；"
                    "要钉住某位老师就在上面选他，选「跟缴费走（自动）」再放回自动。"
                    if admin
                    else "普通老师可以维护自己学员的资料和报名；"
                    "学员归属由管理员维护，其他人的学员只能查看。"
                ),
                size=11,
                color=ft.Colors.GREY_600,
            ),
            fields["owner"],
            fields["note"],
        ]
        controls.append(
            ft.Row(
                [
                    ft.TextButton("取消", on_click=cancel_edit),
                    ft.Button("保存", icon=ft.Icons.SAVE, on_click=save),
                ],
                alignment=ft.MainAxisAlignment.END,
            )
        )
        body = self._form_column(controls, scroll=False)
        for name in (
            "gender",
            "status",
            "grade",
            "birth_date",
            "school",
            "phone",
            "guardian",
        ):
            fields[name].expand = True
        return self._section("基本档案", body)

    def _student_account_card(self, s: dict) -> ft.Container:
        can_manage = self._can_manage_student(s["id"])
        if not can_manage:
            return ft.Container(visible=False)
        account = db.get_student_user(s["id"])
        if account is None:
            if not self.is_admin():
                return ft.Container(visible=False)
            return self._section(
                "学生账号",
                ft.Text(
                    "还没有学生账号。创建后，学生只能查看自己的信息、积分、课评和教案。",
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
                action=ft.Button(
                    "创建账号",
                    icon=ft.Icons.PERSON_ADD,
                    on_click=lambda e: self._open_student_account_dialog(s),
                ),
            )
        state = "已停用" if not account["active"] else "可使用"
        return self._section(
            "学生账号",
            ft.ResponsiveRow(
                [
                    ft.Container(
                        ft.Column(
                            [
                                ft.Text(
                                    account["username"],
                                    size=14,
                                    weight=ft.FontWeight.W_600,
                                ),
                                ft.Text(
                                    f"登录账号 · {state}",
                                    size=12,
                                    color=ft.Colors.GREY_600,
                                ),
                                ft.Text(
                                    f"论坛昵称：{account.get('forum_nickname') or '未设置'}",
                                    size=12,
                                    color=ft.Colors.GREY_600,
                                ),
                            ],
                            spacing=2,
                            tight=True,
                        ),
                        col={"xs": 12, "md": 8},
                        padding=10,
                        border_radius=10,
                        bgcolor=ft.Colors.GREY_50,
                    ),
                    ft.Container(
                        ft.Row(
                            [
                                ft.TextButton(
                                    "重设密码",
                                    icon=ft.Icons.KEY,
                                    on_click=lambda e: self._open_change_password(
                                        account["id"]
                                    ),
                                ),
                                *(
                                    [
                                        ft.TextButton(
                                            "修改昵称",
                                            icon=ft.Icons.BADGE_OUTLINED,
                                            on_click=lambda e: self._open_forum_nickname_dialog(
                                                account["id"]
                                            ),
                                        )
                                    ]
                                    if self.is_admin()
                                    else []
                                ),
                                *(
                                    [
                                        ft.TextButton(
                                            "删除账号",
                                            icon=ft.Icons.DELETE_OUTLINE,
                                            on_click=lambda e: self._confirm(
                                                "删除学生账号",
                                                f"确定删除「{account['username']}」这个学生账号吗？"
                                                "学员档案和学习记录不会删除。",
                                                lambda: db.delete_user(account["id"]),
                                            ),
                                        )
                                    ]
                                    if self.is_admin()
                                    else []
                                ),
                            ],
                            spacing=2,
                            wrap=True,
                        ),
                        col={"xs": 12, "md": 4},
                        alignment=ft.Alignment.CENTER_RIGHT,
                    ),
                ],
                spacing=8,
                run_spacing=8,
            ),
        )

    def _open_student_account_dialog(self, s: dict) -> None:
        if not self.is_admin():
            self._toast("只有管理员能创建学生账号")
            return
        username = _tf("登录用户名 *", "", width=DIALOG_WIDTH)
        password = _tf(
            "初始密码 *",
            "",
            width=DIALOG_WIDTH,
            password=True,
            can_reveal_password=True,
        )

        def save(e):
            try:
                db.create_user(
                    username.value or "",
                    password.value or "",
                    s["name"],
                    db.ROLE_STUDENT,
                    is_teacher=False,
                    student_id=s["id"],
                )
            except ValueError as err:
                username.error = str(err)
                username.update()
                return
            self._finish("学生账号建好了")

        self._show(
            self._dialog(
                "创建学生账号",
                self._form_column([username, password]),
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )

    def _open_hour_transfer_dialog(self, s: dict) -> None:
        if not self.is_admin():
            self._toast("只有管理员可以转入已有课时")
            return
        hour_types = db.list_hour_types()
        happened_on = _tf(
            "转入日期",
            date.today().isoformat(),
            width=DIALOG_WIDTH,
            hint_text="2026-10-30",
        )
        origin = _tf(
            "转入来源 *",
            "",
            width=DIALOG_WIDTH,
            hint_text="例如：原机构转入、家长自带课时",
        )
        note = _tf(
            "备注",
            "",
            width=DIALOG_WIDTH,
            multiline=True,
            min_lines=2,
            max_lines=4,
        )
        rows_holder = ft.Column(spacing=8, tight=True)
        rows: list[dict] = []
        total_text = ft.Text("合计 0 课时", size=14, weight=ft.FontWeight.W_600)

        def refresh_total(*_args) -> None:
            total = 0.0
            for row in rows:
                try:
                    total += float((row["hours"].value or "0").strip() or 0)
                except ValueError:
                    pass
            total_text.value = f"合计 {db.num_text(total)} 课时"

        def add_row(update: bool = True) -> None:
            type_dd = _dd(
                "课时类型 *",
                _opts([(h["id"], h["name"]) for h in hour_types]),
                value=str(hour_types[0]["id"]) if hour_types else None,
                width=150,
            )
            hours = _tf(
                "转入数量 *",
                "",
                width=90,
                keyboard_type=ft.KeyboardType.NUMBER,
                on_change=refresh_total,
            )
            row = {"type": type_dd, "hours": hours}

            def remove(e=None) -> None:
                if len(rows) <= 1:
                    self._toast("至少留一行")
                    return
                rows.remove(row)
                rows_holder.controls.remove(box)
                rows_holder.update()
                refresh_total()

            box = ft.Row(
                [
                    type_dd,
                    hours,
                    ft.IconButton(
                        ft.Icons.CLOSE,
                        tooltip="去掉这一行",
                        icon_size=18,
                        on_click=remove,
                    ),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            rows.append(row)
            rows_holder.controls.append(box)
            if update:
                rows_holder.update()
                refresh_total()

        add_row(update=False)

        def save(e=None) -> None:
            try:
                date.fromisoformat((happened_on.value or "").strip())
            except ValueError:
                happened_on.error = "写成 2026-10-30 这样"
                happened_on.update()
                return
            if not (origin.value or "").strip():
                origin.error = "请填写课时从哪里转来"
                origin.update()
                return

            items = []
            type_ids: set[int] = set()
            for row in rows:
                try:
                    hours_value = float((row["hours"].value or "").strip())
                except ValueError:
                    row["hours"].error = "填数字"
                    row["hours"].update()
                    return
                if hours_value <= 0:
                    row["hours"].error = "必须大于 0"
                    row["hours"].update()
                    return
                type_id = int(row["type"].value)
                if type_id in type_ids:
                    self._toast("同一种课时只能填一行")
                    return
                type_ids.add(type_id)
                items.append({"hour_type_id": type_id, "hours": hours_value})
            try:
                db.add_hour_transfer(
                    self._my_user_id(),
                    int(s["id"]),
                    (happened_on.value or "").strip(),
                    (origin.value or "").strip(),
                    note.value or "",
                    items,
                )
            except ValueError as err:
                self._toast(str(err))
                return
            total = sum(float(item["hours"]) for item in items)
            self._finish(f"已转入 {db.num_text(total)} 课时，不计入缴费收入")

        body = self._form_column(
            [
                ft.Text(
                    f"学员：{s['name']}",
                    size=13,
                    weight=ft.FontWeight.W_600,
                ),
                happened_on,
                origin,
                ft.Text("本次转入课时", size=14, weight=ft.FontWeight.W_600),
                rows_holder,
                ft.Row(
                    [
                        ft.TextButton(
                            "加一种课时",
                            icon=ft.Icons.ADD,
                            on_click=lambda e: add_row(),
                        )
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),
                total_text,
                note,
                ft.Text(
                    "转入课时会增加余额、参与上课扣课时和低课时提醒，"
                    "但不会生成缴费记录，也不会计入缴费收入。",
                    size=11,
                    color=ft.Colors.GREY_600,
                ),
            ]
        )
        self._show(
            self._dialog(
                "转入已有课时",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("确认转入", on_click=save),
                ],
            )
        )

    def _hours_card(self, s: dict, accounts: list[dict]) -> ft.Container:
        admin = self.is_admin()
        # 只显示有记录的账户；一个都没记录时，先显示"正课"
        shown = [a for a in accounts if a["charged"] or a["used"] or a["unlimited"]]
        if not shown:
            shown = [a for a in accounts if a["name"] == "正课"] or accounts[:1]
        rows = []
        for a in shown:
            unlimited = bool(a["unlimited"])
            balance = float(a["balance"] or 0)
            if unlimited:
                balance_color = ft.Colors.GREEN_700
            elif not a.get("warn"):
                balance_color = None
            elif balance <= 0 and a["charged"]:
                balance_color = ft.Colors.RED_600
            elif balance <= WARN_BALANCE and a["charged"]:
                balance_color = ft.Colors.ORANGE_700
            else:
                balance_color = None
            sources = []
            if a["paid"]:
                sources.append(f"缴费 {db.num_text(a['paid'])}")
            if a["transferred"]:
                sources.append(f"转入 {db.num_text(a['transferred'])}")
            if a["manual"]:
                sources.append(f"手工 {db.num_text(a['manual'])}")
            source_text = "来源：" + (" ＋ ".join(sources) or "暂无")
            rows.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(a["name"], size=14, weight=ft.FontWeight.W_600, expand=True),
                                    (
                                        ft.Switch(
                                            label="不限课时",
                                            value=unlimited,
                                            on_change=lambda e, ht=a["hour_type_id"]: self._toggle_unlimited(
                                                s["id"], ht, e.control.value
                                            ),
                                        )
                                        if admin
                                        else ft.Text(
                                            "不限课时" if unlimited else "",
                                            size=12,
                                            color=ft.Colors.GREY_600,
                                        )
                                    ),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Row(
                                [
                                    self._metric("总课时", db.num_text(a["charged"])),
                                    self._metric("已用", db.num_text(a["used"])),
                                    self._metric(
                                        "剩余",
                                        "不限" if unlimited else db.num_text(balance),
                                        color=balance_color,
                                    ),
                                ],
                                spacing=24,
                            ),
                            ft.Text(source_text, size=11, color=ft.Colors.GREY_500),
                            ft.Row(
                                [
                                    ft.TextButton(
                                        "明细",
                                        icon=ft.Icons.RECEIPT_LONG,
                                        on_click=lambda e, aid=a["hour_type_id"]: self._open_hour_ledger(
                                            s["id"], aid
                                        ),
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.END,
                            ),
                        ],
                        spacing=4,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        body = ft.Column(rows, spacing=10)
        hint = ft.Text(
            "只显示有记录的账户。上竞赛课先扣竞赛课时，竞赛课时不够会自动扣正课；考级课同理。"
            "常规课时统一走缴费；转学生自带的课时由管理员在这里转入。",
            size=11,
            color=ft.Colors.GREY_600,
        )
        return self._section(
            "课时账户",
            ft.Column([body, hint], spacing=10),
            action=(
                ft.Button(
                    "转入已有课时",
                    icon=ft.Icons.INPUT,
                    on_click=lambda e: self._open_hour_transfer_dialog(s),
                )
                if admin
                else None
            ),
        )

    def _enrollments_card(self, student_id: int, enrollments: list[dict]) -> ft.Container:
        admin = self.is_admin()
        can_edit_student = self._can_manage_student(student_id)
        items = []
        for e in enrollments:
            can_edit = admin or self._can_manage_enrollment(e)
            status_color = {
                "在读": ft.Colors.GREEN_700,
                "停课": ft.Colors.ORANGE_700,
                "离校": ft.Colors.GREY_600,
                "结课": ft.Colors.GREY_500,
            }.get(e["status"], ft.Colors.GREY_600)
            cls_label = db.enrollment_class_label(e)
            tail: list[ft.Control] = [
                _chip(e["status"], status_color)
            ]
            if can_edit:
                tail += [
                    ft.IconButton(
                        ft.Icons.EDIT,
                        tooltip="编辑",
                        icon_size=18,
                        on_click=lambda e2, en=e: self._open_enrollment_dialog(student_id, en),
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE,
                        tooltip="删除",
                        icon_size=18,
                        on_click=lambda e2, en=e: self._confirm(
                            "删除报名",
                            f"确定删除「{_level_title(en)} · {en['class_type_name']}」这条报名吗？",
                            lambda: db.delete_enrollment(en["id"]),
                        ),
                    ),
                ]
            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        (
                                            f"{cls_label} · {e['class_type_name']}"
                                            if cls_label
                                            else f"{_level_title(e)} · {e['class_type_name']}"
                                        ),
                                        size=14,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    ft.Text(
                                        f"单次 {e['minutes']} 分钟"
                                        + (
                                            f" · 归属 {e['owner_teacher_name']}"
                                            if e.get("owner_teacher_name")
                                            else " · 归属未指定"
                                        )
                                        + ("" if cls_label else " · 还没挂课程")
                                        + (f" · {e['note']}" if e["note"] else ""),
                                        size=12,
                                        color=ft.Colors.GREY_600,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            *tail,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        if not items:
            has_hours = any(
                a["charged"] or a["balance"] for a in db.get_accounts(student_id)
            )
            items = [
                ft.Text(
                    "还没报名课程。"
                    + (
                        "上面课时账户里已经有课时了；要让他在排课、点名里被选到，"
                        "先在这儿加一条报名课程（选等级和课型）。"
                        "下次记缴费时在缴费窗口里选上「等级」，系统就会顺手建好。"
                        if has_hours
                        else "点右上角新增一条；记缴费时在缴费窗口里选上「等级」也会自动建。"
                    ),
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            ]
        action = (
            ft.Button(
                "新增报名",
                icon=ft.Icons.ADD,
                on_click=lambda e: self._open_enrollment_dialog(student_id, None),
            )
            if can_edit_student
            else None
        )
        return self._section("报名课程", ft.Column(items, spacing=10), action=action)

    def _danger_card(self, s: dict) -> ft.Container:
        if not self.is_admin():
            return ft.Container(visible=False)
        return self._section(
            "其他",
            ft.Row(
                [
                    ft.Button(
                        "删除学员",
                        icon=ft.Icons.DELETE_FOREVER,
                        on_click=lambda e: self._confirm(
                            "删除学员",
                            f"确定删除「{s['name']}」吗？他的报名和课时记录会一起删掉，删了不能恢复。",
                            lambda: db.delete_student(s["id"]),
                            after=self._after_delete_student,
                        ),
                    )
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
        )

    def _after_delete_student(self) -> None:
        self.student_id = None
