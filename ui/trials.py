"""试听记录。"""

from __future__ import annotations

from datetime import date

import flet as ft

import db
from .common import (
    DIALOG_WIDTH,
    _chip,
    _date_text,
    _dd,
    _grade_opts,
    _opts,
    _school_inputs,
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
            lines.append(
                ft.Text(f"试听时间：{_date_text(t['trial_on'])}", size=12, color=ft.Colors.GREY_600)
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
                        lambda: db.convert_trial_to_student(row["id"]),
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

    def _goto_student(self, student_id: int) -> None:
        self.tab = 0
        self.student_id = student_id
        self.render()

    def _open_trial_dialog(self, trial: dict | None = None) -> None:
        editing = trial is not None
        name = _tf("孩子姓名 *", trial["name"] if editing else "", width=DIALOG_WIDTH)
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
            "试听日期（可不填）",
            trial["trial_on"] if editing else "",
            width=DIALOG_WIDTH,
            hint_text="2026-09-30",
        )
        note = _tf(
            "备注（孩子情况、家长想法…）",
            trial["note"] if editing else "",
            width=DIALOG_WIDTH,
            multiline=True,
            min_lines=3,
            max_lines=6,
        )

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
                "note": note.value or "",
                "owner_teacher_id": (
                    int(owner.value) if (owner.value or "").strip() else None
                ),
            }
            if editing:
                db.update_trial(trial["id"], data)
                self._finish("试听记录已更新")
            else:
                db.create_trial(data)
                self._finish("记下了，记得跟进")

        body = self._form_column(
            [name, grade, school_box, gender, parent, phone, source, status, owner, trial_on, note]
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
