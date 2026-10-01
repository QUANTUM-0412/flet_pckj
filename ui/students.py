"""学员列表与学员详情。"""

from __future__ import annotations

import flet as ft

import db
from .common import (
    STATUS_FILTERS,
    WARN_BALANCE,
    _chip,
    _dd,
    _level_title,
    _opts,
    _status_opts,
    _tf,
)


class StudentsMixin:
    """学员列表与学员详情（ClassHoursApp 的一部分）。"""

    def _students_view(self) -> ft.Column:
        rows = db.list_students_with_summary(self.keyword, self.status_filter)
        pending_ids = db.students_with_pending_makeups()

        search = ft.TextField(
            value=self.keyword,
            hint_text="搜索姓名 / 年级 / 电话",
            dense=True,
            prefix_icon=ft.Icons.SEARCH,
            expand=True,
            on_submit=self._on_search_submit,
        )
        status_dd = _dd(
            "状态",
            _opts(STATUS_FILTERS),
            value=self.status_filter or "全部",
            width=120,
            on_select=self._on_status_select,
        )
        cards = [self._student_card(item, pending_ids) for item in rows]
        if not cards:
            cards = [
                self._card(
                    ft.Column(
                        [
                            ft.Icon(ft.Icons.PERSON_ADD_ALT, size=36, color=ft.Colors.GREY_400),
                            ft.Text(
                                "还没有学员" if not self.keyword and not self.status_filter else "没有符合条件的学员",
                                color=ft.Colors.GREY_600,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    )
                )
            ]

        return ft.Column(
            [
                self._header(
                    "学员",
                    f"共 {len(rows)} 人",
                    (
                        [
                            ft.Button(
                                "新增学员",
                                icon=ft.Icons.PERSON_ADD,
                                on_click=lambda e: self._open_new_student(),
                            )
                        ]
                        if self.is_admin()
                        else []
                    ),
                ),
                ft.Row([search, status_dd], spacing=10),
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
        enrollments = [e for e in item["enrollments"] if e["status"] == "在读"]
        course_text = "、".join(
            f"{_level_title(e)}（{e['class_type_name']}）" for e in enrollments
        ) or "还没报课"
        meta = " · ".join(x for x in [s["grade"], s["phone"]] if x) or "—"
        hours = db.hours_text(item["accounts"])
        points = db.num_text(item.get("points") or 0)
        warn = any(
            a.get("warn")
            and a["charged"]
            and not a["unlimited"]
            and a["balance"] <= WARN_BALANCE
            for a in item["accounts"]
        )

        badges = []
        if s["id"] in pending_ids:
            badges.append(_chip("待补课", ft.Colors.ORANGE_700))
        if s["status"] != "在读":
            badges.append(_chip(s["status"], ft.Colors.GREY_500))
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
                self._profile_card(s),
                self._hours_card(s, accounts),
                self._enrollments_card(student_id, enrollments),
                self._student_lessons_card(s),
                self._payments_card(s),
                self._points_card(s),
                self._danger_card(s),
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _profile_card(self, s: dict) -> ft.Container:
        admin = self.is_admin()
        name = _tf("姓名 *", s["name"])
        gender = _dd("性别", _opts([(g, g) for g in db.GENDER_OPTIONS]), value=s["gender"] or None)
        status = _dd("状态", _status_opts(), value=s["status"])
        grade = _tf("年级", s["grade"])
        phone = _tf("联系电话", s["phone"])
        note = _tf("备注", s["note"], multiline=True, min_lines=2, max_lines=5)
        if not admin:
            for field in (name, gender, status, grade, phone, note):
                field.read_only = True

        def save(e):
            if not (name.value or "").strip():
                name.error = "请填姓名"
                name.update()
                return
            db.update_student(
                s["id"],
                {
                    "name": name.value,
                    "gender": gender.value or "",
                    "grade": grade.value or "",
                    "phone": phone.value or "",
                    "note": note.value or "",
                    "status": status.value or "在读",
                },
            )
            self._finish("档案已保存")

        controls = [
            name,
            ft.Row([gender, status], spacing=10, expand=False),
            grade,
            phone,
            note,
        ]
        if admin:
            controls.append(
                ft.Row(
                    [ft.Button("保存", icon=ft.Icons.SAVE, on_click=save)],
                    alignment=ft.MainAxisAlignment.END,
                )
            )
        body = self._form_column(controls, scroll=False)
        gender.expand = True
        status.expand = True
        return self._section("基本档案", body)

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
            source_text = f"来源：缴费 {db.num_text(a['paid'])} ＋ 手工 {db.num_text(a['manual'])}"
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
                                    *([ft.TextButton(
                                        "调整课时",
                                        icon=ft.Icons.EDIT_NOTE,
                                        on_click=lambda e, aid=a["hour_type_id"]: self._open_hours_dialog(
                                            s["id"], aid
                                        ),
                                    )] if admin else []),
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
            "要给其它账户加课时，点「调整课时」。",
            size=11,
            color=ft.Colors.GREY_600,
        )
        return self._section(
            "课时账户",
            ft.Column([body, hint], spacing=10),
        )

    def _enrollments_card(self, student_id: int, enrollments: list[dict]) -> ft.Container:
        admin = self.is_admin()
        items = []
        for e in enrollments:
            tail: list[ft.Control] = [ft.Text(e["status"], size=12, color=ft.Colors.GREY_600)]
            if admin:
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
                                        f"{_level_title(e)} · {e['class_type_name']}",
                                        size=14,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    ft.Text(
                                        f"单次 {e['minutes']} 分钟"
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
            if admin
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
