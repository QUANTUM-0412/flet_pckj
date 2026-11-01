"""试听记录。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import flet as ft

import db
import trial_times
from .common import (
    DIALOG_WIDTH,
    _chip,
    _date_text,
    _dd,
    _grade_opts,
    _opts,
    _school_inputs,
    _stored_name,
    _teacher_opts,
    _tf,
)


class TrialsMixin:
    """试听记录（ClassHoursApp 的一部分）。"""

    def _trials_view(self) -> ft.Column:
        trials = db.list_trials(self.trial_filter)
        counts = db.trial_counts()
        cards = [self._trial_card(t) for t in trials]
        if not cards:
            cards = [
                self._card(
                    ft.Column(
                        [
                            ft.Icon(ft.Icons.PERSON_SEARCH, size=36, color=ft.Colors.GREY_400),
                            ft.Text(
                                "还没有试听记录" if not self.trial_filter else "这个状态下还没有人",
                                color=ft.Colors.GREY_600,
                            ),
                            ft.Text(
                                "来试听的孩子记在这里，方便后面跟进；试听不扣课时。",
                                size=12,
                                color=ft.Colors.GREY_500,
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
                    "试听跟进",
                    f"待试听 {counts.get('待试听', 0)} 人 · 已试听 {counts.get('已试听', 0)} 人"
                    f" · 已报名 {counts.get('已报名', 0)} 人",
                    [
                        ft.Button(
                            "新增试听",
                            icon=ft.Icons.PERSON_ADD,
                            on_click=lambda e: self._open_trial_dialog(),
                        )
                    ],
                ),
                _dd(
                    "状态",
                    _opts([("", "全部")] + [(s, s) for s in db.TRIAL_STATUS]),
                    value=self.trial_filter or "",
                    width=140,
                    on_select=lambda e: self._set_trial_filter(e.control.value or ""),
                ),
                self._trial_schedule_card(),
                *cards,
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _set_trial_filter(self, status: str) -> None:
        self.trial_filter = status
        self.render()

    def _trial_selected_teacher_id(self) -> int:
        teachers = db.list_teachers()
        if not teachers:
            self.trial_schedule_teacher_id = ""
            return 0
        allowed = {str(item["id"]) for item in teachers}
        selected = str(self.trial_schedule_teacher_id or "")
        if selected not in allowed:
            selected = self._default_teacher_id()
        if selected not in allowed:
            selected = str(teachers[0]["id"])
        self.trial_schedule_teacher_id = selected
        return int(selected)

    def _set_trial_schedule_teacher(self, teacher_id: str) -> None:
        self.trial_schedule_teacher_id = (teacher_id or "").strip()
        self.render()

    def _shift_trial_week(self, delta: int) -> None:
        try:
            current = date.fromisoformat(self.trial_schedule_day)
        except ValueError:
            current = date.today()
        self.trial_schedule_day = (current + timedelta(days=7 * delta)).isoformat()
        self.render()

    def _select_trial_day(self, day: str) -> None:
        self.trial_schedule_day = day
        self.render()

    def _trial_schedule_card(self) -> ft.Container:
        teachers = db.list_teachers()
        if not teachers:
            return self._section(
                "试听时间表",
                ft.Text(
                    "还没有可排试听的老师，请先在设置里添加并勾选「上课老师」。",
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
            )
        teacher_id = self._trial_selected_teacher_id()
        teacher_name = next(
            (
                item["display_name"] or item["username"]
                for item in teachers
                if int(item["id"]) == teacher_id
            ),
            "",
        )
        try:
            anchor = date.fromisoformat(self.trial_schedule_day)
        except ValueError:
            anchor = date.today()
            self.trial_schedule_day = anchor.isoformat()
        monday = anchor - timedelta(days=anchor.weekday())
        days = [monday + timedelta(days=index) for index in range(7)]
        day_infos = [db.trial_calendar_day(day.isoformat()) for day in days]
        wide = self.is_wide()
        teacher_filter = _dd(
            "试听老师",
            _opts(
                [
                    (item["id"], item["display_name"] or item["username"])
                    for item in teachers
                ]
            ),
            value=str(teacher_id),
            width=180,
            on_select=lambda e: self._set_trial_schedule_teacher(
                e.control.value or ""
            ),
        )
        week_start = days[0]
        week_end = days[-1]
        range_text = (
            f"{week_start.month}月{week_start.day}日 ~ "
            f"{week_end.month}月{week_end.day}日"
        )
        head = ft.Row(
            [
                ft.IconButton(
                    ft.Icons.CHEVRON_LEFT,
                    tooltip="上一周",
                    on_click=lambda e: self._shift_trial_week(-1),
                ),
                ft.Text(
                    range_text,
                    size=14,
                    weight=ft.FontWeight.W_600,
                    expand=True,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.IconButton(
                    ft.Icons.CHEVRON_RIGHT,
                    tooltip="下一周",
                    on_click=lambda e: self._shift_trial_week(1),
                ),
            ],
            spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        if wide:
            column_width = max(
                84,
                min(
                    168,
                    ((self.page.width or 1200) - 260) // 7,
                ),
            )
            timeline: ft.Control = ft.Row(
                [
                    self._trial_day_column(
                        info,
                        teacher_id,
                        expand=False,
                        width=column_width,
                    )
                    for info in day_infos
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        else:
            selected_day = self.trial_schedule_day
            date_buttons = []
            for info in day_infos:
                active = info["date"] == selected_day
                current = date.fromisoformat(info["date"])
                date_buttons.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    ("一", "二", "三", "四", "五", "六", "日")[
                                        current.weekday()
                                    ],
                                    size=11,
                                    color=(
                                        ft.Colors.BLUE_700
                                        if active
                                        else ft.Colors.GREY_600
                                    ),
                                ),
                                ft.Text(
                                    str(current.day),
                                    size=15,
                                    weight=ft.FontWeight.W_600,
                                    color=(
                                        ft.Colors.BLUE_700
                                        if active
                                        else ft.Colors.GREY_800
                                    ),
                                ),
                            ],
                            spacing=0,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            tight=True,
                        ),
                        width=44,
                        height=52,
                        alignment=ft.Alignment.CENTER,
                        border_radius=10,
                        bgcolor=ft.Colors.BLUE_50 if active else ft.Colors.GREY_50,
                        ink=True,
                        on_click=lambda e, value=info["date"]: (
                            self._select_trial_day(value)
                        ),
                    )
                )
            selected_info = next(
                item
                for item in day_infos
                if item["date"] == self.trial_schedule_day
            )
            timeline = ft.Column(
                [
                    ft.Row(date_buttons, spacing=6, scroll=ft.ScrollMode.AUTO),
                    self._trial_day_column(
                        selected_info,
                        teacher_id,
                        expand=False,
                    ),
                ],
                spacing=8,
            )
        generate_button = ft.Button(
            "生成家长时段图",
            icon=ft.Icons.IMAGE_OUTLINED,
            on_click=lambda e: self._generate_trial_times_image(teacher_id),
        )
        teacher_summary = f"{teacher_name} · 每次 1 小时"
        teacher_controls: ft.Control
        if wide:
            teacher_controls = ft.Row(
                [
                    ft.Text(
                        teacher_summary,
                        size=12,
                        color=ft.Colors.GREY_600,
                        expand=True,
                    ),
                    teacher_filter,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        else:
            teacher_controls = ft.Column(
                [
                    ft.Text(
                        teacher_summary,
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    teacher_filter,
                ],
                spacing=6,
                tight=True,
            )
        return self._section(
            "试听时间表",
            ft.Column(
                [
                    teacher_controls,
                    head,
                    timeline,
                ],
                spacing=10,
            ),
            action=generate_button,
        )

    def _trial_day_column(
        self,
        info: dict,
        teacher_id: int,
        *,
        expand: bool,
        width: int | None = None,
    ) -> ft.Container:
        current = date.fromisoformat(info["date"])
        weekday = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")[
            current.weekday()
        ]
        trials = [
            row
            for row in db.trials_for_day(info["date"])
            if int(row.get("trial_teacher_id") or 0) == int(teacher_id)
            and (row.get("trial_start_time") or "").strip()
        ]
        busy = [
            item
            for item in db.trial_busy_intervals(info["date"], teacher_id)
            if item["kind"] == "课程"
        ]
        slots = db.trial_slot_candidates(
            info["date"],
            teacher_id,
            include_past=info["date"] < date.today().isoformat(),
        )
        entries: list[tuple[int, ft.Control]] = []
        for item in busy:
            entries.append(
                (
                    int(item["start"]),
                    ft.Container(
                        ft.Text(
                            f"{item['start'] // 60:02d}:{item['start'] % 60:02d}"
                            f"–{item['end'] // 60:02d}:{item['end'] % 60:02d}"
                            f" 课程",
                            size=10,
                            color=ft.Colors.GREY_600,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        padding=ft.Padding.symmetric(horizontal=7, vertical=5),
                        border_radius=7,
                        bgcolor=ft.Colors.GREY_100,
                    ),
                )
            )
        terminal = {"爽约", "已取消"}
        for trial in trials:
            try:
                start = db._time_minutes(trial["trial_start_time"])
            except ValueError:
                continue
            status = str(trial.get("appointment_status") or "已预约")
            color = (
                ft.Colors.GREY_500
                if status in terminal
                else ft.Colors.ORANGE_700
                if trial.get("status") == "待试听"
                else ft.Colors.GREEN_700
            )
            entries.append(
                (
                    start,
                    ft.Container(
                        ft.Column(
                            [
                                ft.Text(
                                    f"{trial['trial_start_time']} {trial['name']}",
                                    size=11,
                                    weight=ft.FontWeight.W_600,
                                    color=color,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(
                                    f"试听 · {status}",
                                    size=10,
                                    color=color,
                                ),
                            ],
                            spacing=0,
                            tight=True,
                        ),
                        padding=7,
                        border_radius=8,
                        bgcolor=ft.Colors.WHITE,
                        border=ft.Border.all(1, ft.Colors.GREY_300),
                        ink=True,
                        on_click=lambda e, row=trial: self._open_trial_dialog(row),
                    ),
                )
            )
        for start_time in slots:
            entries.append(
                (
                    db._time_minutes(start_time),
                    ft.Container(
                        ft.Text(
                            f"可约 {start_time}",
                            size=10,
                            color=ft.Colors.BLUE_700,
                        ),
                        height=34,
                        padding=ft.Padding.symmetric(horizontal=7, vertical=5),
                        border_radius=7,
                        bgcolor=ft.Colors.BLUE_50,
                        ink=True,
                        on_click=lambda e, day=info["date"], start=start_time: (
                            self._open_trial_dialog(
                                None,
                                prefill={
                                    "trial_on": day,
                                    "trial_start_time": start,
                                    "trial_teacher_id": str(teacher_id),
                                },
                            )
                        ),
                    ),
                )
            )
        if info["is_open"] and not slots:
            empty = ft.Text(
                "没有可约时段",
                size=11,
                color=ft.Colors.GREY_500,
            )
        elif not info["is_open"]:
            empty = ft.Text(
                info.get("warning")
                or info.get("note")
                or "机构休息",
                size=11,
                color=(
                    ft.Colors.ORANGE_700
                    if info.get("warning")
                    else ft.Colors.GREY_500
                ),
            )
        else:
            empty = None
        body: list[ft.Control] = [
            ft.Text(
                f"{weekday} {current.month}/{current.day}",
                size=13,
                weight=ft.FontWeight.W_600,
                color=(
                    ft.Colors.BLUE_700
                    if info["date"] == date.today().isoformat()
                    else ft.Colors.GREY_800
                ),
            ),
            ft.Text(
                info["label"],
                size=10,
                color=ft.Colors.GREY_600,
            ),
            *([empty] if empty is not None else []),
            *[control for _start, control in sorted(entries, key=lambda row: row[0])],
        ]
        if info.get("warning"):
            body.append(
                ft.Text(
                    "节假日数据待更新",
                    size=10,
                    color=ft.Colors.ORANGE_700,
                    tooltip=info["warning"],
                )
            )
        return ft.Container(
            ft.Column(body, spacing=5, tight=True),
            expand=expand,
            width=width,
            padding=8,
            border_radius=10,
            bgcolor=(
                ft.Colors.BLUE_50
                if info["date"] == date.today().isoformat()
                else ft.Colors.GREY_50
            ),
            border=ft.Border.all(1, ft.Colors.GREY_200),
        )

    def _trial_image_dir(self) -> Path:
        path = db.UPLOAD_DIR / "trial_times"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _generate_trial_times_image(self, teacher_id: int) -> None:
        """直接用时间表当前显示的一周生成家长图，不再让用户二次选周。"""
        try:
            anchor = date.fromisoformat(self.trial_schedule_day)
        except ValueError:
            anchor = date.today()
        first = anchor - timedelta(days=anchor.weekday())
        last = first + timedelta(days=6)
        teachers = db.list_teachers()
        selected_name = next(
            (
                item["display_name"] or item["username"]
                for item in teachers
                if int(item["id"]) == int(teacher_id)
            ),
            "",
        )
        if not selected_name:
            self._toast("请先选择试听老师")
            return
        days = []
        missing_calendar_days = []
        current = first
        while current <= last:
            info = db.trial_calendar_day(current.isoformat())
            if info.get("warning"):
                missing_calendar_days.append(current.isoformat())
            days.append(
                {
                    **info,
                    "slots": db.trial_slot_candidates(
                        current.isoformat(), int(teacher_id)
                    ),
                }
            )
            current += timedelta(days=1)
        if missing_calendar_days:
            self._toast(
                f"节假日库还没有 {missing_calendar_days[0][:4]} 年数据，"
                "请更新节假日库，或先在试听日历里设置这段日期"
            )
            return
        blob = trial_times.build_trial_times_image(
            first.isoformat(),
            last.isoformat(),
            selected_name,
            days,
            brand=db.get_meta("poster_brand"),
            contact=db.get_meta("poster_contact"),
            qr_code=self._poster_qr_bytes(),
            logo=self._poster_logo_bytes(),
        )
        stored = _stored_name(
            "trial_times.jpg",
            suffix=".jpg",
            prefix=f"trial_times_t{int(teacher_id)}",
        )
        target = self._trial_image_dir() / stored
        try:
            target.write_bytes(blob)
        except OSError:
            self._toast("试听时段图存不下来，检查 data 文件夹权限")
            return
        self._show_trial_times_image(target, first, last)

    def _show_trial_times_image(
        self, path: Path, first: date, last: date
    ) -> None:
        width = min(560, (self.page.width or 900) - 80)
        url = f"/trial_times/{path.name}"
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("试听可约时段"),
            scrollable=True,
            content=ft.Container(
                ft.Column(
                    [
                        ft.Image(src=url, width=width, fit=ft.BoxFit.CONTAIN),
                        ft.Text(
                            f"已按时间表当前显示的一周生成："
                            f"{first.month}月{first.day}日 周一 ~ "
                            f"{last.month}月{last.day}日 周日。"
                            "手机可长按保存，电脑可用「在新窗口打开」后保存。",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                    ],
                    spacing=8,
                    tight=True,
                ),
                width=width,
            ),
            actions=[
                ft.TextButton(
                    "在新窗口打开",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda e: self.page.run_task(
                        self._open_url, url
                    ),
                ),
                ft.TextButton("关闭", on_click=self._close),
            ],
        )
        self._show(dlg)

    def _trial_card(self, t: dict) -> ft.Container:
        colors = {
            "待试听": ft.Colors.ORANGE_700,
            "已试听": ft.Colors.BLUE_600,
            "已报名": ft.Colors.GREEN_700,
            "没意向": ft.Colors.GREY_500,
        }
        lines = [
            ft.Row(
                [
                    ft.Text(t["name"], size=15, weight=ft.FontWeight.W_600, expand=True),
                    _chip(t["status"], colors.get(t["status"], ft.Colors.GREY_500)),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        ]
        meta = " · ".join(
            x
            for x in [
                t["grade"],
                t["school"],
                f"家长：{t['parent_name']}" if t["parent_name"] else "",
                t["phone"],
                f"跟进：{t['owner_teacher_name']}" if t.get("owner_teacher_name") else "",
                t["source"],
            ]
            if x
        )
        if meta:
            lines.append(ft.Text(meta, size=12, color=ft.Colors.GREY_600))
        if t["trial_on"]:
            slot = ""
            if t.get("trial_start_time"):
                try:
                    start = db._time_minutes(t["trial_start_time"])
                    slot = (
                        f" {t['trial_start_time']}–"
                        f"{db._minutes_time(start + int(t.get('trial_minutes') or 60))}"
                    )
                except ValueError:
                    slot = f" {t['trial_start_time']}"
            lines.append(
                ft.Text(
                    f"试听时间：{_date_text(t['trial_on'])}{slot}"
                    + (
                        f" · {t['trial_teacher_name']}"
                        if t.get("trial_teacher_name")
                        else ""
                    )
                    + (
                        f" · {t.get('appointment_status')}"
                        if t.get("appointment_status")
                        else ""
                    ),
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            )
        if t["note"]:
            lines.append(ft.Text(t["note"], size=12, color=ft.Colors.GREY_700))

        buttons = []
        if t["student_id"]:
            buttons.append(
                ft.TextButton(
                    "看学员",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda e, sid=t["student_id"]: self._goto_student(sid),
                )
            )
        elif self.is_admin():
            buttons.append(
                ft.TextButton(
                    "转正式学员",
                    icon=ft.Icons.PERSON_ADD,
                    on_click=lambda e, row=t: self._confirm(
                        "转成正式学员",
                        f"把「{row['name']}」转成正式学员？会建一份正式档案，"
                        "然后你可以去他的档案里报名课程、记缴费。",
                        lambda: self._convert_trial_with_account(row),
                        ok_text="转正式",
                        done_text="已转成正式学员，去他的档案里报名和缴费",
                    ),
                )
            )
        else:
            buttons.append(
                ft.Text("已跟进，等管理员转正式", size=11, color=ft.Colors.GREY_500)
            )
        buttons.append(
            ft.TextButton("编辑", icon=ft.Icons.EDIT, on_click=lambda e, row=t: self._open_trial_dialog(row))
        )
        if (
            t.get("trial_start_time")
            and t.get("appointment_status") == "已预约"
            and not t.get("student_id")
        ):
            buttons.append(
                ft.TextButton(
                    "标记到访",
                    icon=ft.Icons.HOW_TO_REG,
                    on_click=lambda e, row=t: self._confirm(
                        "确认孩子已到访",
                        f"「{row['name']}」已经完成这次试听了吗？"
                        "确认后跟进状态会改成「已试听」。",
                        lambda: db.set_trial_appointment_status(
                            row["id"], "已到访"
                        ),
                        ok_text="已到访",
                        done_text="已标记到访",
                    ),
                )
            )
            buttons.append(
                ft.TextButton(
                    "爽约",
                    on_click=lambda e, row=t: self._confirm(
                        "标记爽约",
                        f"「{row['name']}」这次没有来试听吗？"
                        "这条预约会保留，但不再占用可约时段。",
                        lambda: db.set_trial_appointment_status(
                            row["id"], "爽约"
                        ),
                        ok_text="确认爽约",
                        done_text="已标记爽约",
                    ),
                )
            )
        if self.is_admin():
            buttons.append(
                ft.TextButton(
                    "删除",
                    icon=ft.Icons.DELETE_OUTLINE,
                    on_click=lambda e, row=t: self._confirm(
                        "删除试听记录",
                        f"确定删除「{row['name']}」这条试听记录吗？",
                        lambda: db.delete_trial(row["id"]),
                    ),
                )
            )
        lines.append(ft.Row(buttons, spacing=4, wrap=True, alignment=ft.MainAxisAlignment.END))
        return self._card(ft.Column(lines, spacing=6))

    def _convert_trial_with_account(self, trial: dict) -> int:
        """试听本身不建账号；转成正式学员时建档并自动生成账号。"""
        student_id = db.convert_trial_to_student(trial["id"])
        account, password = db.ensure_student_account(student_id)
        self._pending_student_credentials = (account, password)
        return student_id

    def _goto_student(self, student_id: int) -> None:
        self.tab = 0
        self.student_id = student_id
        self.render()

    def _open_trial_dialog(
        self,
        trial: dict | None = None,
        *,
        prefill: dict | None = None,
    ) -> None:
        editing = trial is not None
        seed = dict(trial or prefill or {})
        name = _tf(
            "孩子姓名 *",
            trial["name"] if editing else "",
            width=DIALOG_WIDTH,
        )
        grade = _dd(
            "年级",
            _grade_opts(),
            value=(trial["grade"] if editing else "") or None,
            width=DIALOG_WIDTH,
        )
        school_box, school_field = _school_inputs(
            trial["school"] if editing else "", DIALOG_WIDTH
        )
        gender = _dd(
            "性别",
            _opts([(g, g) for g in db.GENDER_OPTIONS]),
            value=(trial["gender"] if editing else "") or None,
            width=DIALOG_WIDTH,
        )
        parent = _tf("家长称呼（妈妈／爸爸）", trial["parent_name"] if editing else "", width=DIALOG_WIDTH)
        phone = _tf("联系电话", trial["phone"] if editing else "", width=DIALOG_WIDTH)
        source = _tf(
            "来源",
            trial["source"] if editing else "",
            width=DIALOG_WIDTH,
            hint_text="朋友介绍／路过／抖音…",
        )
        status = _dd(
            "跟进状态",
            _opts([(s, s) for s in db.TRIAL_STATUS]),
            value=trial["status"] if editing else "待试听",
            width=DIALOG_WIDTH,
        )
        owner = _dd(
            "跟进老师（算谁的客户）",
            _teacher_opts("不指定"),
            value=(
                str(trial["owner_teacher_id"])
                if editing and trial["owner_teacher_id"]
                else self._default_teacher_id()
            ),
            width=DIALOG_WIDTH,
        )
        trial_on = _tf(
            "试听日期 *",
            str(seed.get("trial_on") or ""),
            width=DIALOG_WIDTH,
            hint_text="2026-09-30",
        )
        trial_teacher = _dd(
            "试听老师 *",
            _teacher_opts("请选择"),
            value=(
                str(seed.get("trial_teacher_id") or "")
                or (
                    str(trial["owner_teacher_id"])
                    if editing and trial.get("owner_teacher_id")
                    else self._default_teacher_id()
                )
            ),
            width=DIALOG_WIDTH,
        )
        trial_time = _dd(
            "试听开始时间 *",
            [],
            value=str(seed.get("trial_start_time") or "") or None,
            width=DIALOG_WIDTH,
            hint_text="先选老师和日期",
        )
        appointment = _dd(
            "预约状态",
            _opts([(value, value) for value in db.TRIAL_APPOINTMENT_STATUS]),
            value=str(seed.get("appointment_status") or "已预约"),
            width=DIALOG_WIDTH,
            visible=editing,
        )
        note = _tf(
            "备注（孩子情况、家长想法…）",
            trial["note"] if editing else "",
            width=DIALOG_WIDTH,
            multiline=True,
            min_lines=3,
            max_lines=6,
        )

        def refresh_slots(update: bool = False, reset: bool = False) -> None:
            day = (trial_on.value or "").strip()
            try:
                date.fromisoformat(day)
            except ValueError:
                trial_time.options = []
                trial_time.value = None
                trial_time.hint_text = "先填正确的试听日期"
                if update:
                    trial_time.update()
                return
            teacher_value = (trial_teacher.value or "").strip()
            if not teacher_value:
                trial_time.options = []
                trial_time.value = None
                trial_time.hint_text = "先选试听老师"
                if update:
                    trial_time.update()
                return
            current = None if reset else (trial_time.value or "").strip()
            slots = db.trial_slot_candidates(
                day,
                int(teacher_value),
                exclude_trial_id=int(trial["id"]) if editing else None,
                include_past=editing or day < date.today().isoformat(),
            )
            if current and current not in slots:
                slots.insert(0, current)
            trial_time.options = _opts(
                [
                    (
                        value,
                        value
                        + (
                            f"–{db._minutes_time(db._time_minutes(value) + 60)}"
                        ),
                    )
                    for value in slots
                ]
            )
            trial_time.value = (
                current if current in slots else (slots[0] if slots else None)
            )
            trial_time.hint_text = (
                "每次固定 1 小时"
                if slots
                else "这天没有可约时段"
            )
            trial_time.disabled = not bool(slots)
            if update:
                trial_time.update()

        trial_on.on_change = lambda e: refresh_slots(update=True, reset=True)
        trial_teacher.on_select = lambda e: refresh_slots(update=True, reset=True)
        refresh_slots(update=False)

        def save(e):
            if not (name.value or "").strip():
                name.error = "请填姓名"
                name.update()
                return
            day = (trial_on.value or "").strip()
            if day:
                try:
                    date.fromisoformat(day)
                except ValueError:
                    trial_on.error = "日期写成 2026-09-30 这样"
                    trial_on.update()
                    return
            if not day:
                trial_on.error = "请选择试听日期"
                trial_on.update()
                return
            if not (trial_teacher.value or "").strip():
                trial_teacher.error = "请选择试听老师"
                trial_teacher.update()
                return
            refresh_slots(update=False, reset=False)
            if not (trial_time.value or "").strip():
                trial_time.error = "请选择试听开始时间"
                trial_time.update()
                return
            data = {
                "name": name.value,
                "gender": gender.value or "",
                "grade": grade.value or "",
                "school": (school_field.value or "").strip(),
                "parent_name": parent.value or "",
                "phone": phone.value or "",
                "source": source.value or "",
                "status": status.value or "待试听",
                "trial_on": day,
                "trial_start_time": (trial_time.value or "").strip(),
                "trial_teacher_id": int(trial_teacher.value),
                "appointment_status": (
                    "已预约"
                    if editing
                    and (trial_time.value or "").strip()
                    and appointment.value in (None, "", "未安排")
                    else appointment.value
                    if editing and appointment.value
                    else "已预约"
                ),
                "note": note.value or "",
                "owner_teacher_id": (
                    int(owner.value) if (owner.value or "").strip() else None
                ),
            }
            try:
                if editing:
                    db.update_trial(trial["id"], data)
                    self._finish("试听记录已更新")
                else:
                    db.create_trial(data)
                    self._finish("试听已经排好，时间是 1 小时")
            except ValueError as err:
                trial_time.error = str(err)
                trial_time.update()

        body = self._form_column(
            [
                name,
                grade,
                school_box,
                gender,
                parent,
                phone,
                source,
                status,
                owner,
                trial_on,
                trial_teacher,
                trial_time,
                appointment,
                ft.Text(
                    "试听统一 1 小时，从 19:30 往前每小时一档；"
                    "工作日从 16:30 开始。"
                    "周末和假期按试听日历判断。",
                    size=11,
                    color=ft.Colors.GREY_600,
                ),
                note,
            ],
            scroll=True,
        )
        self._show(
            self._dialog(
                "编辑试听记录" if editing else "新增试听",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )
