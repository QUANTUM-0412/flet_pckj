"""报表与导出。"""

from __future__ import annotations

from datetime import date, datetime

import flet as ft

import db
import xlsx_writer
from .common import _date_text


class ReportsMixin:
    """报表与导出（ClassHoursApp 的一部分）。"""

    def _reports_view(self) -> ft.Column:
        month = self.report_month or date.today().strftime("%Y-%m")
        stats = db.month_stats(month)
        alerts = db.hour_alerts()
        counts = db.month_lesson_counts(month)
        teachers = db.teacher_report(month)
        points = [b for b in db.points_balances() if b["points"]]
        redemptions = db.list_redemptions()

        alert_rows = []
        for a in alerts:
            bits = [f"{a['account']} 剩 {db.num_text(a['balance'])} 课时"]
            if a["grade"]:
                bits.append(a["grade"])
            if a["phone"]:
                bits.append(a["phone"])
            alert_rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(a["student"], size=14, weight=ft.FontWeight.W_600),
                            ft.Text(" · ".join(bits), size=12, color=ft.Colors.GREY_700, expand=True),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=8,
                    border_radius=8,
                    bgcolor=ft.Colors.ORANGE_50,
                )
            )
        if not alert_rows:
            alert_rows = [ft.Text("暂时没有要提醒的。", size=12, color=ft.Colors.GREY_600)]

        count_rows = [
            ft.Row(
                [
                    ft.Text(c["name"], size=13, weight=ft.FontWeight.W_600, expand=True),
                    ft.Text(
                        f"{int(c['times'])} 次 · {db.num_text(round(float(c['minutes']) / 60, 1))} 课时",
                        size=12,
                        color=ft.Colors.GREY_700,
                    ),
                ]
            )
            for c in counts
        ] or [ft.Text("这个月还没有点名记录。", size=12, color=ft.Colors.GREY_600)]

        teacher_rows = []
        for t in teachers:
            bits = [
                f"归属实收 {db.num_text(t['income'])} 元",
                f"上课 {t['lessons']} 节 · {db.num_text(t['hours'])} 课时",
                f"在读学生 {t['students']} 人",
            ]
            if t["trials_open"]:
                bits.append(f"跟进中试听 {t['trials_open']} 人")
            if t["phone"]:
                bits.append(t["phone"])
            teacher_rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(t["name"] or "—", size=14, weight=ft.FontWeight.W_600),
                            ft.Text(
                                " · ".join(bits),
                                size=12,
                                color=ft.Colors.GREY_700,
                                expand=True,
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        if not teacher_rows:
            teacher_rows = [
                ft.Text(
                    "还没有上课老师。到「设置 → 老师账号」里加老师，并勾上「也是上课老师」。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            ]

        point_rows = [
            ft.Row(
                [
                    ft.Text(f"{i + 1}. {b['name']}", size=13, expand=True),
                    ft.Text(f"{db.num_text(b['points'])} 分", size=13, weight=ft.FontWeight.W_600),
                ]
            )
            for i, b in enumerate(points)
        ] or [ft.Text("还没有积分。", size=12, color=ft.Colors.GREY_600)]

        def shift_month(delta: int):
            def handler(e):
                year, mon = (int(x) for x in (self.report_month or month).split("-"))
                total = year * 12 + (mon - 1) + delta
                self.report_month = f"{total // 12:04d}-{total % 12 + 1:02d}"
                self.render()

            return handler

        return ft.Column(
            [
                self._header(
                    "报表",
                    "一眼看清要提醒谁、这个月收了多少、谁上得多",
                    [
                        ft.Button(
                            "导出 Excel",
                            icon=ft.Icons.FILE_DOWNLOAD,
                            on_click=lambda e: self._export_excel(),
                        )
                    ],
                ),
                self._section(
                    f"课时不够要提醒的（{len(alerts)} 个）",
                    ft.Column(alert_rows, spacing=6),
                ),
                self._card(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.IconButton(
                                        ft.Icons.CHEVRON_LEFT,
                                        tooltip="上个月",
                                        on_click=shift_month(-1),
                                    ),
                                    ft.Text(
                                        f"{month[:4]} 年 {int(month[5:])} 月",
                                        size=16,
                                        weight=ft.FontWeight.W_600,
                                        expand=True,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    ft.IconButton(
                                        ft.Icons.CHEVRON_RIGHT,
                                        tooltip="下个月",
                                        on_click=shift_month(1),
                                    ),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Row(
                                [
                                    self._metric("收入", f"{db.num_text(stats['income'])} 元"),
                                    *(
                                        [
                                            self._metric(
                                                "用券抵扣",
                                                f"{db.num_text(stats['voucher_used'])} 元",
                                            )
                                        ]
                                        if stats.get("voucher_used")
                                        else []
                                    ),
                                    self._metric("缴费", f"{stats['payments']} 笔"),
                                    self._metric("上课", f"{stats['lessons']} 节"),
                                    self._metric("点名", f"{stats['attendance']} 人次"),
                                    self._metric("消耗课时", db.num_text(stats["hours"])),
                                ],
                                spacing=22,
                                wrap=True,
                            ),
                        ],
                        spacing=8,
                    )
                ),
                self._section("这个月谁上得多", ft.Column(count_rows, spacing=6)),
                self._section(
                    f"按老师（{month[:4]} 年 {int(month[5:])} 月）",
                    ft.Column(
                        [
                            ft.Text(
                                "「归属实收」是算给这个老师的学生交的钱（按缴费行归属）；"
                                "「上课」是按实际上课老师算的（谁上的课给谁）。",
                                size=12,
                                color=ft.Colors.GREY_600,
                            ),
                            *teacher_rows,
                        ],
                        spacing=10,
                    ),
                ),
                self._section("积分榜", ft.Column(point_rows, spacing=6)),
                self._section(
                    f"兑换记录（{len(redemptions)} 笔）",
                    ft.Column(self._redemption_rows(redemptions), spacing=10),
                ),
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _redemption_rows(self, redemptions: list[dict]) -> list[ft.Control]:
        if not redemptions:
            return [
                ft.Text(
                    "还没有兑换记录。孩子上课赚的积分会自动累加，兑换的时候在这记一笔。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            ]
        rows = []
        for r in redemptions:
            bits = []
            if r["note"]:
                bits.append(r["note"])
            bits.append(f"扣 {db.num_text(abs(float(r['change'])))} 分")
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(_date_text(r["happened_on"]), size=12, color=ft.Colors.GREY_600),
                                    ft.Text(r["student_name"], size=15, weight=ft.FontWeight.W_600),
                                    ft.Text(" · ".join(bits), size=12, color=ft.Colors.GREY_600),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            *(
                                [
                                    ft.IconButton(
                                        ft.Icons.EDIT,
                                        tooltip="编辑",
                                        icon_size=18,
                                        on_click=lambda e, row=r: self._open_redemption_dialog(row),
                                    ),
                                    ft.IconButton(
                                        ft.Icons.DELETE_OUTLINE,
                                        tooltip="删除",
                                        icon_size=18,
                                        on_click=lambda e, row=r: self._confirm(
                                            "删除这条兑换",
                                            f"确定删除「{row['student_name']} 扣 "
                                            f"{db.num_text(abs(float(row['change'])))} 分」这条吗？"
                                            "积分会加回去。",
                                            lambda: db.delete_redemption(row["id"]),
                                        ),
                                    ),
                                ]
                                if self.is_admin()
                                else []
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        return rows

    def _export_excel(self) -> None:
        sheets = db.export_tables()
        data = xlsx_writer.build_xlsx(sheets)
        db.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        pretty = f"课时记录-{date.today().isoformat()}.xlsx"
        stored = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        try:
            (db.EXPORT_DIR / stored).write_bytes(data)
        except OSError:
            stored = ""
        total_rows = sum(len(rows) for _name, _head, rows in sheets)
        self._last_export = (pretty, data)
        # 数据可能被搬到项目外面（服务器上常见），提示里就照实写路径
        try:
            where = db.EXPORT_DIR.relative_to(db.APP_DIR)
        except ValueError:
            where = db.EXPORT_DIR
        self._show(
            self._dialog(
                "导出好了",
                ft.Column(
                    [
                        ft.Text(f"{pretty}", size=14, weight=ft.FontWeight.W_600),
                        ft.Text(
                            f"一共 {len(sheets)} 张表、{total_rows} 行："
                            + "、".join(name for name, _h, _r in sheets),
                            size=12,
                            color=ft.Colors.GREY_700,
                        ),
                        ft.Text(
                            f"电脑上也存了一份：{where}/" + (stored or "（没存上）"),
                            size=11,
                            color=ft.Colors.GREY_600,
                        ),
                    ],
                    spacing=6,
                    tight=True,
                ),
                [
                    ft.TextButton("关闭", on_click=self._close),
                    ft.Button(
                        "下载",
                        icon=ft.Icons.DOWNLOAD,
                        on_click=lambda e: self.page.run_task(self._download_export),
                    ),
                ],
            )
        )

    async def _download_export(self) -> None:
        name, data = getattr(self, "_last_export", (None, None))
        if not data:
            return
        await self.picker.save_file(file_name=name, src_bytes=data)
