"""课时记录平台 —— 界面层（组合入口）。

一套界面同时适配电脑浏览器和手机：屏幕窄就用底部导航，屏幕宽就用左侧导航。
界面代码按功能拆在 ui/ 包里，这里把各部分拼成一个完整的 ClassHoursApp。
"""

from __future__ import annotations

from datetime import date

import flet as ft

from ui.auth import AuthMixin
from ui.shell import ShellMixin
from ui.widgets import WidgetsMixin
from ui.students import StudentsMixin
from ui.schedule import ScheduleMixin
from ui.lessons import LessonsMixin
from ui.lesson_detail import LessonDetailMixin
from ui.lesson_dialogs import LessonDialogsMixin
from ui.payments import PaymentsMixin
from ui.points import PointsMixin
from ui.trials import TrialsMixin
from ui.reports import ReportsMixin
from ui.files import FilesMixin
from ui.hours import HoursMixin
from ui.enrollment import EnrollmentMixin
from ui.settings import SettingsMixin


class ClassHoursApp(
    AuthMixin,
    ShellMixin,
    WidgetsMixin,
    StudentsMixin,
    ScheduleMixin,
    LessonsMixin,
    LessonDetailMixin,
    LessonDialogsMixin,
    PaymentsMixin,
    PointsMixin,
    TrialsMixin,
    ReportsMixin,
    FilesMixin,
    HoursMixin,
    EnrollmentMixin,
    SettingsMixin,
):
    """整个应用的界面，由 ui/ 里各个功能模块拼成。"""

    def __init__(self, page: ft.Page):
        self.page = page
        self.tab = 0
        self.student_id: int | None = None
        self.lesson_id: int | None = None
        self.show_schedule = False
        self.schedule_date = date.today().isoformat()
        self.report_month = date.today().strftime("%Y-%m")
        self.keyword = ""
        self.filter_name = ""
        self.filter_phone = ""
        self.filter_grade = ""
        self.filter_school = ""
        self.filter_owner = ""
        self.lesson_keyword = ""
        self.lesson_week = ""  # 空着就是本周；否则存那一周的周一（YYYY-MM-DD）
        self.status_filter = ""
        self.trial_filter = ""
        self.payment_month = ""  # 空着就是本月；否则 YYYY-MM
        self._last_wide: bool | None = None
        self._row_refs: dict[int, dict] = {}
        self._upload_target: tuple[str, int, str] | None = None
        self.user: dict | None = None
        self._payment_items_map: dict[int, list[dict]] = {}

        self.picker = ft.FilePicker(on_result=self._on_files_picked)
        self.launcher = ft.UrlLauncher()
        page.services.append(self.picker)
        page.services.append(self.launcher)

        page.title = "课时记录"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.bgcolor = ft.Colors.GREY_100
        page.padding = 0
        page.on_resize = self._on_resize


__all__ = ["ClassHoursApp"]
