"""外壳与导航。"""

from __future__ import annotations

import flet as ft


class ShellMixin:
    """外壳与导航（ClassHoursApp 的一部分）。"""

    def is_wide(self) -> bool:
        return (self.page.width or 1000) >= 820

    def _nav_items(self):
        return [
            (ft.Icons.PEOPLE_OUTLINE, ft.Icons.PEOPLE, "学员"),
            (ft.Icons.FACT_CHECK_OUTLINED, ft.Icons.FACT_CHECK, "上课记录"),
            (ft.Icons.PAYMENTS_OUTLINED, ft.Icons.PAYMENTS, "缴费"),
            (ft.Icons.STARS_OUTLINED, ft.Icons.STARS, "积分"),
            (ft.Icons.PERSON_SEARCH, ft.Icons.PERSON_SEARCH, "试听"),
            (ft.Icons.INSIGHTS_OUTLINED, ft.Icons.INSIGHTS, "报表"),
            (ft.Icons.SETTINGS_OUTLINED, ft.Icons.SETTINGS, "设置"),
        ]

    def render(self) -> None:
        self.page.clean()
        if self.user is None:
            self.page.add(self._login_view())
            self.page.update()
            return
        wide = self.is_wide()
        self._last_wide = wide
        body = ft.Container(
            content=self._body(),
            expand=True,
            padding=ft.Padding.symmetric(horizontal=14, vertical=12),
        )
        if wide:
            self.page.add(
                ft.Row(
                    [self._rail(), ft.VerticalDivider(width=1), body],
                    expand=True,
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                )
            )
        else:
            self.page.add(
                ft.Column(
                    [body, ft.Divider(height=1, thickness=1), self._bottom_bar()],
                    expand=True,
                    spacing=0,
                )
            )
        self.page.update()

    def _on_resize(self, e) -> None:
        if self.is_wide() != self._last_wide:
            self.render()

    def _goto(self, index: int) -> None:
        """切换页面。用明确的点击事件，避免控件自己乱跳。"""
        if (
            index == self.tab
            and self.student_id is None
            and self.lesson_id is None
            and not self.show_schedule
        ):
            return
        self.tab = index
        self.student_id = None
        self.lesson_id = None
        self.show_schedule = False
        self.render()

    def _nav_button(self, index: int, icon, selected_icon, label: str, wide: bool) -> ft.Container:
        active = self.tab == index
        color = ft.Colors.BLUE_700 if active else ft.Colors.GREY_600
        content = ft.Column(
            [
                ft.Icon(selected_icon if active else icon, color=color, size=24),
                ft.Text(
                    label,
                    size=11,
                    color=color,
                    weight=ft.FontWeight.W_600 if active else ft.FontWeight.NORMAL,
                ),
            ],
            spacing=3,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        )
        return ft.Container(
            content=content,
            width=72 if wide else None,
            height=64 if wide else 56,
            expand=None if wide else True,
            border_radius=16 if wide else 12,
            bgcolor=ft.Colors.BLUE_50 if active else None,
            ink=True,
            alignment=ft.Alignment.CENTER,
            on_click=lambda e, i=index: self._goto(i),
        )

    def _rail(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    self._nav_button(i, ic, sic, lb, True)
                    for i, (ic, sic, lb) in enumerate(self._nav_items())
                ],
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=96,
            padding=ft.Padding.symmetric(horizontal=6, vertical=12),
            bgcolor=ft.Colors.WHITE,
        )

    def _bottom_bar(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    self._nav_button(i, ic, sic, lb, False)
                    for i, (ic, sic, lb) in enumerate(self._nav_items())
                ],
                spacing=8,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
            bgcolor=ft.Colors.WHITE,
        )

    def _body(self) -> ft.Control:
        if self.tab == 0:
            return (
                self._students_view()
                if self.student_id is None
                else self._student_detail_view(self.student_id)
            )
        if self.tab == 1:
            if self.lesson_id is not None:
                return self._lesson_detail_view(self.lesson_id)
            return self._schedule_view() if self.show_schedule else self._lessons_view()
        if self.tab == 2:
            return self._payments_view()
        if self.tab == 3:
            return self._points_view()
        if self.tab == 4:
            return self._trials_view()
        if self.tab == 5:
            return self._reports_view()
        return self._settings_view()

    def open_lesson(self, lesson_id: int | None) -> None:
        self.lesson_id = lesson_id
        if lesson_id is None:
            self.show_schedule = False
        self.render()

    def open_schedule(self, show: bool = True) -> None:
        self.show_schedule = show
        self.lesson_id = None
        self.render()

    def open_student(self, student_id: int | None) -> None:
        self.student_id = student_id
        self.render()
