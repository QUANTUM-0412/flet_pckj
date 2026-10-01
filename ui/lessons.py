"""上课记录列表与补课。"""

from __future__ import annotations

from datetime import date

import flet as ft

import db
from .common import DIALOG_WIDTH, _chip, _date_text, _lessons_stats, _now_time, _tf


class LessonsMixin:
    """上课记录列表与补课（ClassHoursApp 的一部分）。"""

    def _lessons_view(self) -> ft.Column:
        lessons = db.list_lessons()
        makeups = db.list_makeups("待补")
        names = db.attendance_names([l["id"] for l in lessons])
        links = db.makeups_by_lesson([l["id"] for l in lessons])
        cards = [
            self._lesson_card(l, names.get(l["id"], []), links.get(l["id"]))
            for l in lessons
        ]
        if not cards:
            cards = [
                self._card(
                    ft.Column(
                        [
                            ft.Icon(ft.Icons.EVENT_NOTE, size=36, color=ft.Colors.GREY_400),
                            ft.Text("还没有上课记录", color=ft.Colors.GREY_600),
                            ft.Text(
                                "上完课点右上角「记一节课」，勾出勤、算积分和课时。",
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
                    "上课记录",
                    f"共 {len(lessons)} 节课",
                    [
                        ft.TextButton(
                            "排课表",
                            icon=ft.Icons.CALENDAR_MONTH,
                            on_click=lambda e: self.open_schedule(True),
                        ),
                        ft.Button(
                            "记一节课",
                            icon=ft.Icons.ADD,
                            on_click=lambda e: self._open_lesson_dialog(),
                        )
                    ],
                ),
                *([self._makeups_card(makeups)] if makeups else []),
                *cards,
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _lesson_card(
        self, lesson: dict, students: list[dict], makeup: dict | None = None
    ) -> ft.Container:
        tags = []
        if lesson["kind"] == "补课":
            tags.append(_chip("补课", ft.Colors.BLUE_600))
        if not lesson["class_type_deduct"]:
            tags.append(_chip("不扣课时", ft.Colors.GREY_500))
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        f"{_date_text(lesson['lesson_date'])} {lesson['start_time']}",
                                        size=15,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    *tags,
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            ft.Text(db.lesson_label(lesson), size=12, color=ft.Colors.GREY_700),
                            ft.Text(_lessons_stats(lesson), size=12, color=ft.Colors.GREY_600),
                            *(
                                [
                                    ft.Text(
                                        f"补 {makeup['student_name']} "
                                        f"{_date_text(makeup['lesson_date'])} 请假的那节",
                                        size=12,
                                        color=ft.Colors.BLUE_700,
                                    )
                                ]
                                if makeup
                                else []
                            ),
                            ft.Text(
                                "、".join(
                                    s["name"] + ("" if s["attendance"] else "（请假）")
                                    for s in students
                                )
                                or "还没点名",
                                size=12,
                                color=ft.Colors.GREY_600,
                            ),
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
            on_click=lambda e, lid=lesson["id"]: self.open_lesson(lid),
        )

    def _makeups_card(self, makeups: list[dict]) -> ft.Container:
        return self._section(
            f"待补课（{len(makeups)} 条）", ft.Column(self._makeup_rows(makeups), spacing=10)
        )

    def _makeup_rows(self, makeups: list[dict]) -> list[ft.Control]:
        rows = []
        for m in makeups:
            rows.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(m["student_name"], size=15, weight=ft.FontWeight.W_600, expand=True),
                                    _chip("待补", ft.Colors.ORANGE_700),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Text(
                                f"请假的那节：{_date_text(m['lesson_date'])} {m['start_time']}"
                                f" · {db.lesson_label(m)}",
                                size=12,
                                color=ft.Colors.GREY_700,
                            ),
                            ft.Row(
                                [
                                    ft.Button(
                                        "安排补课",
                                        icon=ft.Icons.EVENT_AVAILABLE,
                                        on_click=lambda e, row=m: self._open_arrange_makeup_dialog(row),
                                    ),
                                    ft.TextButton(
                                        "不补了",
                                        on_click=lambda e, row=m: self._confirm(
                                            "不补了",
                                            f"「{row['student_name']}」{_date_text(row['lesson_date'])}"
                                            "这节课不补了？这条待办会关掉。",
                                            lambda: db.cancel_makeup(row["id"], "不补了"),
                                            ok_text="确定",
                                            done_text="这条待补课关掉了",
                                        ),
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.END,
                                spacing=6,
                            ),
                        ],
                        spacing=6,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.ORANGE_50,
                )
            )
        return rows

    def _student_makeups_card(self, s: dict) -> ft.Container:
        """这个孩子要不要补课，一眼能看出来。"""
        pending = db.list_makeups("待补", s["id"])
        done = db.list_makeups("已补", s["id"])
        body: list[ft.Control] = []
        if pending:
            body += self._makeup_rows(pending)
        else:
            body.append(
                ft.Text("现在没有要补的课。", size=12, color=ft.Colors.GREY_600)
            )
        if done:
            body.append(
                ft.Text(
                    "已经补过的："
                    + "、".join(
                        f"{_date_text(m['lesson_date'])} → {_date_text(m['makeup_date'])}"
                        for m in done[:5]
                    ),
                    size=11,
                    color=ft.Colors.GREY_500,
                )
            )
        title = f"补课情况（有 {len(pending)} 节要补）" if pending else "补课情况"
        return self._section(title, ft.Column(body, spacing=10))

    def _open_arrange_makeup_dialog(self, makeup: dict) -> None:
        day = _tf("补课日期", date.today().isoformat(), width=DIALOG_WIDTH)
        start = _tf("开始时间", makeup["start_time"] or _now_time(), width=DIALOG_WIDTH)
        minutes = _tf(
            "时长（分钟）",
            makeup["lesson_minutes"] or 90,
            width=DIALOG_WIDTH,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        hint = ft.Text(
            f"给「{makeup['student_name']}」补 {_date_text(makeup['lesson_date'])} 那节课。"
            "补课照扣课时，用的还是原来那门课的账户。",
            size=12,
            color=ft.Colors.GREY_600,
        )

        def save(e):
            try:
                date.fromisoformat((day.value or "").strip())
            except ValueError:
                day.error = "日期写成 2026-09-05 这样"
                day.update()
                return
            try:
                mins = int(float(minutes.value or 0))
            except ValueError:
                minutes.error = "请填数字"
                minutes.update()
                return
            if mins <= 0:
                minutes.error = "时长要大于 0"
                minutes.update()
                return
            lesson_id = db.arrange_makeup(
                makeup["id"], (day.value or "").strip(), (start.value or "").strip(), mins
            )
            self.lesson_id = lesson_id
            self._finish("补课安排好了，课时已扣")

        body = self._form_column([hint, day, start, minutes])
        self._show(
            self._dialog(
                "安排补课",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )
