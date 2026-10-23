"""缴费。"""

from __future__ import annotations

from datetime import date

import flet as ft

import db
from .common import (
    DIALOG_WIDTH,
    _date_text,
    _dd,
    _level_title,
    _month_text,
    _opts,
    _shift_month,
    _teacher_opts,
    _tf,
)

# 「孩子」下拉里代表"这人还没档案，顺手建一个"的那一项
NEW_STUDENT = "__new__"


class PaymentsMixin:
    """缴费（ClassHoursApp 的一部分）。"""

    def _payments_view(self) -> ft.Column:
        month = self._payment_month_value()
        payments = db.list_payments(month=month)
        self._payment_items_map = db.items_by_payment([p["id"] for p in payments])
        month_total = db.income_total(month=month)
        total = db.income_total()

        # 一个月的缴费按天分块，从新到旧
        blocks: list[ft.Control] = []
        by_day: dict[str, list[dict]] = {}
        for p in payments:
            by_day.setdefault(p["paid_on"], []).append(p)
        for day in sorted(by_day, reverse=True):
            rows = by_day[day]
            day_total = sum(float(r["amount"] or 0) for r in rows)
            blocks.append(
                ft.Row(
                    [
                        ft.Text(
                            _date_text(day),
                            size=13,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text(
                            f"{len(rows)} 笔 · {db.num_text(day_total)} 元",
                            size=12,
                            color=ft.Colors.GREY_600,
                            expand=True,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
            blocks += [self._payment_card(p) for p in rows]
        if not blocks:
            blocks = [
                self._card(
                    ft.Column(
                        [
                            ft.Icon(ft.Icons.PAYMENTS, size=36, color=ft.Colors.GREY_400),
                            ft.Text("这个月还没有缴费记录", color=ft.Colors.GREY_600),
                            ft.Text(
                                "点右上角「记一笔」，课时会自动加到孩子的账户上；"
                                "要翻别的月份，用上面的 ← → 。",
                                size=12,
                                color=ft.Colors.GREY_500,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    )
                )
            ]

        is_this_month = month == date.today().strftime("%Y-%m")
        month_bar = ft.Row(
            [
                ft.IconButton(
                    ft.Icons.CHEVRON_LEFT,
                    tooltip="上个月",
                    on_click=lambda e: self._shift_payment_month(-1),
                ),
                ft.Text(
                    f"{_month_text(month)} · {len(payments)} 笔"
                    + ("（本月）" if is_this_month else ""),
                    size=15,
                    weight=ft.FontWeight.W_600,
                    expand=True,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.IconButton(
                    ft.Icons.CHEVRON_RIGHT,
                    tooltip="下个月",
                    on_click=lambda e: self._shift_payment_month(1),
                ),
                ft.TextButton("本月", on_click=lambda e: self._this_payment_month()),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return ft.Column(
            [
                self._header(
                    "缴费记录",
                    f"{_month_text(month)}收入 {db.num_text(month_total)} 元"
                    f" · 一共 {db.num_text(total)} 元",
                    [
                        ft.Button(
                            "记一笔",
                            icon=ft.Icons.ADD,
                            on_click=lambda e: self._open_payment_dialog(),
                        )
                    ],
                ),
                month_bar,
                *blocks,
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _payment_month_value(self) -> str:
        text = (self.payment_month or "").strip()
        if len(text) == 7 and text[4] == "-":
            return text
        return date.today().strftime("%Y-%m")

    def _shift_payment_month(self, delta: int) -> None:
        self.payment_month = _shift_month(self._payment_month_value(), delta)
        self.render()

    def _this_payment_month(self) -> None:
        self.payment_month = ""
        self.render()

    def _payment_card(self, p: dict) -> ft.Container:
        detail_bits = self._payment_item_bits(p)
        voucher_bits = []
        if p.get("voucher_amount"):
            voucher_bits.append(f"用券抵 {db.num_text(p['voucher_amount'])} 元")
        mine = [v for v in db.list_vouchers(p["student_id"]) if v["payment_id"] == p["id"]]
        if mine:
            v = mine[0]
            voucher_bits.append(f"送券 {v['count']} 张 × {db.num_text(v['face'])} 元")
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(_date_text(p["paid_on"]), size=12, color=ft.Colors.GREY_600),
                            ft.Text(p["student_name"], size=15, weight=ft.FontWeight.W_600),
                            ft.Text(" · ".join(detail_bits) or "—", size=12, color=ft.Colors.GREY_600),
                            *(
                                [
                                    ft.Text(
                                        " · ".join(voucher_bits),
                                        size=12,
                                        color=ft.Colors.BLUE_700,
                                    )
                                ]
                                if voucher_bits
                                else []
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Text(
                        f"{db.num_text(p['amount'])} 元",
                        size=16,
                        weight=ft.FontWeight.W_600,
                    ),
                    *(
                        [
                            ft.IconButton(
                                ft.Icons.EDIT,
                                tooltip="编辑",
                                icon_size=18,
                                on_click=lambda e, pay=p: self._open_payment_dialog(pay),
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                tooltip="删除",
                                icon_size=18,
                                on_click=lambda e, pay=p: self._confirm(
                                    "删除这笔缴费",
                                    f"确定删除「{pay['student_name']} "
                                    f"{db.num_text(pay['amount'])} 元」这笔吗？对应的课时会一起扣掉。",
                                    lambda: db.delete_payment(pay["id"]),
                                ),
                            ),
                        ]
                        if self.is_admin()
                        else []
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, ft.Colors.GREY_300),
        )

    def _payment_item_bits(self, p: dict) -> list[str]:
        items = getattr(self, "_payment_items_map", {}).get(p["id"])
        if items is None:
            items = db.list_payment_items(p["id"])
        bits = []
        for item in items:
            text = f"{item['hour_type_name'] or '课时'} {db.num_text(item['hours'])} 课时"
            if not item["amount"]:
                text += "（送）"
            cls_label = db.enrollment_class_label(item)
            who = item.get("owner_teacher_name") or ""
            if cls_label and who:
                text += f"（{cls_label} · 归 {who}）"
            elif cls_label:
                text += f"（{cls_label}）"
            elif who:
                text += f"（归 {who}）"
            bits.append(text)
        if p["note"]:
            bits.append(p["note"])
        return bits

    def _open_payment_dialog(self, payment: dict | None = None, student_id: int | None = None) -> None:
        admin = self.is_admin()
        editing = payment is not None
        if editing and not admin:
            self._toast("已有缴费只能由管理员修改")
            return
        if student_id and not self._can_manage_student(student_id):
            self._toast("只能给自己名下的学员记缴费")
            return
        students = [
            s
            for s in db.list_students()
            if admin or self._can_manage_student(s["id"])
        ]
        packages = db.list_course_packages(active_only=True)
        selected_package_id = (
            payment.get("package_id") if editing and payment.get("package_id") else None
        )
        if selected_package_id and not any(
            int(p["id"]) == int(selected_package_id) for p in packages
        ):
            old_package = db.get_course_package(selected_package_id)
            if old_package:
                packages.append(old_package)
        hour_types = db.list_hour_types()
        levels = db.list_levels(active_only=True)

        # 家长来交钱的时候，学员档案常常还没建，所以这里可以直接建一个
        new_fields = self._student_fields(with_status=False, with_note=False)
        if not admin:
            owner_id = self._my_user_id()
            new_fields["owner"].value = str(owner_id)
            new_fields["owner"].disabled = True
        new_holder = ft.Column(
            [
                ft.Text("新学员，先填一下（保存时一并建档）", size=12, color=ft.Colors.GREY_600),
                new_fields["name"],
                ft.Row([new_fields["gender"], new_fields["grade"]], spacing=10, expand=False),
                new_fields["birth_date"],
                new_fields["school"],
                new_fields["phone"],
                new_fields["guardian"],
            ],
            spacing=10,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            visible=False,
        )
        if editing or student_id:
            default_student = str(payment["student_id"] if editing else student_id)
        elif students:
            default_student = str(students[0]["id"])
        else:
            default_student = NEW_STUDENT
        student_dd = _dd(
            "孩子",
            _opts(
                [
                    (s["id"], s["name"] + (f"（{s['grade']}）" if s["grade"] else ""))
                    for s in students
                ]
                + [(NEW_STUDENT, "＋ 新建学员…")]
            ),
            value=default_student,
            width=DIALOG_WIDTH,
        )
        new_holder.visible = default_student == NEW_STUDENT

        def sync_new_block(e=None):
            new_holder.visible = student_dd.value == NEW_STUDENT
            refresh_vouchers(False)
            apply_owner_defaults()
            refresh_enrollment_rows(False)
            # 整页重画：局部控件的 .update() 要求它已经挂在页面上，
            # 没挂上会直接抛错，这里统一用 page 更稳
            self.page.update()

        # Flet 1.0 的 Dropdown 没有 on_change 事件（那是给输入框的），
        # 选中的事件叫 on_select；写成 on_change 会静默失效
        student_dd.on_select = sync_new_block
        day = _tf("日期", payment["paid_on"] if editing else date.today().isoformat(), width=DIALOG_WIDTH)
        note = _tf("备注", payment["note"] if editing else "", width=DIALOG_WIDTH)
        package_dd = _dd(
            "固定课包（可选）",
            [ft.DropdownOption(key="", text="不用课包（普通缴费）")]
            + _opts(
                [
                    (
                        p["id"],
                        f"{p['name']} · {db.num_text(p['price'])} 元",
                    )
                    for p in packages
                ]
            ),
            value=str(selected_package_id) if selected_package_id else "",
            width=DIALOG_WIDTH,
        )
        package_hint = ft.Text(
            "课包会自动填入固定课时和金额；普通缴费不会送代金券。",
            size=11,
            color=ft.Colors.GREY_600,
        )
        package_level = _dd(
            "报的等级（课包统一）",
            [ft.DropdownOption(key="", text="不指定")]
            + _opts([(l["id"], db.level_display_name(l)) for l in levels]),
            value="",
            width=DIALOG_WIDTH,
            visible=False,
        )
        package_table_holder = ft.Container(visible=False)
        gift_holder = ft.Column(spacing=6, tight=True, visible=False)
        gift_rows: list[dict] = []
        rows_holder = ft.Column(spacing=8, tight=True)
        rows: list[dict] = []
        total_text = ft.Text("", size=13, weight=ft.FontWeight.W_600)
        voucher_hint = ft.Text("", size=12, color=ft.Colors.GREY_600)
        voucher_dd = _dd("用代金券", [], value="", width=DIALOG_WIDTH)
        voucher_dd.options = [ft.DropdownOption(key="", text="不用")]
        if editing and payment["voucher_id"]:
            voucher_dd.value = str(payment["voucher_id"])

        def picked_student_id():
            """现在这个"孩子"是谁（要新建的话就是 None）。"""
            if not student_dd.value or student_dd.value == NEW_STUDENT:
                return None
            try:
                return int(student_dd.value)
            except (TypeError, ValueError):
                return None

        def usable_vouchers():
            sid = picked_student_id()
            return db.available_vouchers(sid) if sid else []

        def chosen_voucher():
            if not (voucher_dd.value or "").strip():
                return None
            want = str(voucher_dd.value)
            for v in usable_vouchers():
                if str(v["id"]) == want:
                    return v
            # 编辑老单子时，它自己用掉的那张可能已经不在"可用"里了
            if editing and str(payment["voucher_id"] or "") == want:
                return next(
                    (v for v in db.list_vouchers(picked_student_id()) if str(v["id"]) == want),
                    None,
                )
            return None

        def refresh_vouchers(update=True):
            sid = picked_student_id()
            rows_v = usable_vouchers()
            list_rows = list(rows_v)
            if editing and payment["voucher_id"] and not any(
                int(v["id"]) == int(payment["voucher_id"]) for v in rows_v
            ):
                mine = next(
                    (
                        v
                        for v in db.list_vouchers(sid)
                        if int(v["id"]) == int(payment["voucher_id"])
                    ),
                    None,
                )
                if mine:
                    list_rows.append(mine)
            voucher_dd.options = [ft.DropdownOption(key="", text="不用")] + [
                ft.DropdownOption(
                    key=str(v["id"]),
                    text=f"{db.num_text(v['face'])} 元 · 还剩 {v['remain']} 张 · {v['expires_on']} 到期",
                )
                for v in list_rows
            ]
            if voucher_dd.value and not any(
                str(v["id"]) == str(voucher_dd.value) for v in list_rows
            ):
                voucher_dd.value = ""
            if not list_rows:
                voucher_hint.value = (
                    "这个孩子还没有可用的代金券（满 3000 元且含正课的固定课包才送，"
                    "但券可以用在任何一笔缴费上）"
                )
            if update:
                voucher_dd.update()
                voucher_hint.update()

        def _number(field) -> float:
            try:
                return float((field.value or "0").strip() or 0)
            except ValueError:
                raise ValueError("数字填得不对")

        issue_hint = ft.Text("", size=12, color=ft.Colors.GREY_600)

        def selected_package() -> dict | None:
            value = (package_dd.value or "").strip()
            if not value:
                return None
            return next(
                (p for p in packages if str(p["id"]) == value),
                None,
            )

        def issue_text() -> str:
            package = selected_package()
            if not package:
                return "普通缴费不送代金券；只有含正课且满 3000 元的固定课包才送"
            face, count = db.voucher_plan(
                float(package["price"] or 0),
                package_selected=True,
                has_regular=any(
                    item["hour_type_name"] == "正课"
                    and float(item["hours"] or 0) > 0
                    for item in package.get("items", [])
                ),
            )
            if face:
                return (
                    f"这个课包 {db.num_text(package['price'])} 元 → 送 {count} 张 "
                    f"{db.num_text(face)} 元的代金券（{db.VOUCHER_MONTHS} 个月有效）"
                )
            if not any(
                item["hour_type_name"] == "正课"
                and float(item["hours"] or 0) > 0
                for item in package.get("items", [])
            ):
                return "这个课包不含正课课时，不送代金券；手里的券照样能抵这笔"
            return (
                f"这个课包未满 {db.num_text(db.VOUCHER_MIN_PACKAGE_PRICE)} 元，不送代金券；"
                "手里的券照样能抵这笔"
            )

        def refresh_total(update=True, *_):
            package = selected_package()
            if package:
                total = float(package["price"] or 0)
            else:
                total = 0.0
                for row in rows:
                    try:
                        total += _number(row["amount"])
                    except ValueError:
                        pass
            voucher = chosen_voucher()
            cut = float(voucher["face"]) if voucher else 0.0
            if cut:
                total_text.value = (
                    f"合计：实收 {db.num_text(max(0.0, total - cut))} 元"
                    f"（用券抵 {db.num_text(cut)} 元）"
                )
            else:
                total_text.value = f"合计 {db.num_text(total)} 元"
            issue_hint.value = issue_text()
            if update:
                total_text.update()
                issue_hint.update()

        def hour_type_for_class_type(class_type_name: str):
            if not class_type_name:
                return None
            for h in hour_types:
                if h["name"] == class_type_name:
                    return h["id"]
            if class_type_name == "替课":
                return next((h["id"] for h in hour_types if h["name"] == "正课"), None)
            return None

        def student_enrollments() -> list[dict]:
            sid = picked_student_id()
            rows = db.list_enrollments(sid) if sid else []
            return [
                en
                for en in rows
                if admin or self._can_manage_enrollment(en)
            ]

        def enroll_options() -> list[ft.DropdownOption]:
            options = [ft.DropdownOption(key="", text="不指定（按等级和老师算）")]
            for en in student_enrollments():
                cls_label = db.enrollment_class_label(en)
                label = (
                    f"{_level_title(en)} · {cls_label or en['class_type_name']}"
                    f" · {en['owner_teacher_name'] or '归属未指定'}"
                )
                if en["status"] != "在读":
                    label += f"（{en['status']}）"
                options.append(ft.DropdownOption(key=str(en["id"]), text=label))
            return options

        def refresh_enrollment_rows(update: bool = True) -> None:
            """孩子换了，每一行的「哪门课」候选也要跟着换。"""
            for row in rows:
                control = row.get("enroll")
                if control is None:
                    continue
                control.options = enroll_options()
                if control.value and not any(
                    str(o.key) == str(control.value) for o in control.options
                ):
                    control.value = ""
                if update:
                    control.update()

        def add_row(
            hour_type_id=None,
            hours="",
            amount="",
            level_id=None,
            owner_teacher_id=None,
            enrollment_id=None,
            locked=False,
            update=True,
        ):
            enroll_dd = _dd(
                "哪门课程（报名）",
                enroll_options(),
                value=str(enrollment_id) if enrollment_id else "",
                width=DIALOG_WIDTH,
            )
            type_dd = _dd(
                "课时类型",
                _opts([(h["id"], h["name"]) for h in hour_types]),
                value=str(hour_type_id or hour_types[0]["id"]),
                width=96,
                on_select=refresh_total,
            )
            level_dd = _dd(
                "报的等级",
                [ft.DropdownOption(key="", text="不指定")]
                + _opts([(l["id"], db.level_display_name(l)) for l in levels]),
                value=str(level_id) if level_id else "",
                width=148,
            )
            owner_dd = _dd(
                "归属老师（算谁的客户）",
                (
                    _teacher_opts("不指定")
                    if admin
                    else [
                        ft.DropdownOption(
                            key=str(self._my_user_id()),
                            text=self._whoami(),
                        )
                    ]
                ),
                value=(
                    str(owner_teacher_id)
                    if admin and owner_teacher_id
                    else ("" if admin else str(self._my_user_id()))
                ),
                width=148,
            )
            if not admin:
                owner_dd.disabled = True
            hours_f = _tf(
                "数量（课时）",
                hours,
                expand=True,
                keyboard_type=ft.KeyboardType.NUMBER,
                hint_text="例如 24",
            )
            amount_f = _tf(
                "金额（元）",
                amount,
                expand=True,
                keyboard_type=ft.KeyboardType.NUMBER,
                hint_text="0 就是赠送",
                on_change=refresh_total,
            )
            if locked:
                for control in (type_dd, owner_dd, hours_f, amount_f):
                    control.disabled = True
            row = {
                "enroll": enroll_dd,
                "type": type_dd,
                "level": level_dd,
                "hours": hours_f,
                "amount": amount_f,
                "owner": owner_dd,
                "owner_touched": bool(owner_teacher_id),
                "package_item": False,
            }

            def on_enroll(e=None):
                """选了哪门课，等级／课时类型／归属老师就照这条报名填上。"""
                want = (enroll_dd.value or "").strip()
                if not want:
                    return
                for en in student_enrollments():
                    if str(en["id"]) != want:
                        continue
                    if en.get("level_id"):
                        level_dd.value = str(en["level_id"])
                    hour_id = hour_type_for_class_type(en.get("class_type_name"))
                    if hour_id and not locked:
                        type_dd.value = str(hour_id)
                    if admin and en.get("owner_teacher_id"):
                        owner_dd.value = str(en["owner_teacher_id"])
                        row["owner_touched"] = True
                    elif not admin:
                        owner_dd.value = str(self._my_user_id())
                    for control in (level_dd, type_dd, owner_dd):
                        control.update()
                    refresh_total()
                    break

            enroll_dd.on_select = on_enroll

            def mark_owner_touched(e=None):
                row["owner_touched"] = True

            def on_row_level(e=None):
                # 选了等级，归属老师跟着这个孩子这门课的归属走（除非手动改过）
                if row["owner_touched"]:
                    return
                lid = int(level_dd.value) if (level_dd.value or "").strip() else None
                default = (
                    db.default_owner_teacher(picked_student_id(), lid)
                    if admin
                    else self._my_user_id()
                )
                owner_dd.value = str(default) if default else ""
                owner_dd.update()

            owner_dd.on_select = mark_owner_touched
            level_dd.on_select = on_row_level

            def remove(e):
                if len(rows) <= 1:
                    self._toast("至少留一行")
                    return
                rows.remove(row)
                rows_holder.controls.remove(box)
                rows_holder.update()
                refresh_total()

            remove_button = ft.IconButton(
                ft.Icons.CLOSE,
                tooltip="去掉这一行",
                icon_size=18,
                on_click=remove,
                visible=not locked,
            )
            box = ft.Container(
                content=ft.Column(
                    [
                        enroll_dd,
                        ft.Row(
                            [
                                type_dd,
                                level_dd,
                                remove_button,
                            ],
                            spacing=4,
                            wrap=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        owner_dd,
                        ft.Row([hours_f, amount_f], spacing=8),
                    ],
                    spacing=6,
                ),
                padding=10,
                border_radius=10,
                bgcolor=ft.Colors.GREY_50,
            )
            rows.append(row)
            rows_holder.controls.append(box)
            if update:
                rows_holder.update()
                refresh_total()
            return row

        rows_actions = ft.Row(
            [
                ft.TextButton(
                    "+ 加一行",
                    icon=ft.Icons.ADD,
                    on_click=lambda e: add_row(),
                )
            ],
            alignment=ft.MainAxisAlignment.END,
        )
        gift_actions = ft.Row(
            [
                ft.TextButton(
                    "+ 额外赠送考级／比赛课时",
                    icon=ft.Icons.CARD_GIFTCARD,
                    on_click=lambda e: add_gift(),
                )
            ],
            alignment=ft.MainAxisAlignment.END,
            visible=False,
        )

        def clear_rows() -> None:
            rows.clear()
            rows_holder.controls.clear()

        def package_table(package: dict) -> ft.Row:
            table = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("课时类型", size=12)),
                    ft.DataColumn(ft.Text("数量", size=12), numeric=True),
                    ft.DataColumn(ft.Text("金额", size=12), numeric=True),
                ],
                rows=[
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(item["hour_type_name"], size=12)),
                            ft.DataCell(
                                ft.Text(f"{db.num_text(item['hours'])} 节", size=12)
                            ),
                            ft.DataCell(
                                ft.Text(
                                    (
                                        f"{db.num_text(package['price'])} 元"
                                        if index == 0
                                        else "赠送"
                                    ),
                                    size=12,
                                )
                            ),
                        ]
                    )
                    for index, item in enumerate(package["items"])
                ],
                column_spacing=18,
                horizontal_lines=ft.BorderSide(1, ft.Colors.GREY_200),
                heading_row_height=34,
                data_row_min_height=34,
                data_row_max_height=40,
            )
            return ft.Row([table], scroll=ft.ScrollMode.AUTO)

        gift_hour_types = [h for h in hour_types if h["name"] != "正课"]

        def add_gift(update: bool = True) -> None:
            type_dd = _dd(
                "赠送课时类型",
                _opts([(h["id"], h["name"]) for h in gift_hour_types]),
                value=str(gift_hour_types[0]["id"]) if gift_hour_types else "",
                width=180,
            )
            hours = _tf(
                "赠送数量",
                "",
                width=140,
                keyboard_type=ft.KeyboardType.NUMBER,
            )
            row = {"type": type_dd, "hours": hours}

            def remove(e=None):
                gift_rows.remove(row)
                gift_holder.controls.remove(box)
                gift_holder.update()

            box = ft.Row(
                [
                    type_dd,
                    hours,
                    ft.IconButton(
                        ft.Icons.CLOSE,
                        tooltip="去掉这项赠送",
                        icon_size=18,
                        on_click=remove,
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            gift_rows.append(row)
            gift_holder.controls.append(box)
            if update:
                gift_holder.update()

        def refresh_package_ui(update: bool = True) -> None:
            package = selected_package()
            has_package = package is not None
            package_table_holder.content = package_table(package) if package else None
            package_table_holder.visible = has_package
            package_level.visible = has_package
            gift_holder.visible = has_package
            rows_holder.visible = not has_package
            rows_actions.visible = not has_package
            gift_actions.visible = has_package
            package_hint.value = (
                f"已选「{package['name']}」：固定 {db.num_text(package['price'])} 元。"
                if package
                else "课包会自动填入固定课时和金额；普通缴费不会送代金券。"
            )
            if update:
                package_table_holder.update()
                package_level.update()
                gift_holder.update()
                rows_holder.update()
                rows_actions.update()
                gift_actions.update()
                package_hint.update()
                refresh_total()

        def apply_package(update: bool = True) -> None:
            clear_rows()
            if not selected_package():
                add_row("", "", "", None, update=False)
            apply_owner_defaults()
            refresh_package_ui(update=update)

        if editing:
            package = selected_package()
            payment_items = db.list_payment_items(payment["id"])
            if package:
                level_value = next(
                    (str(item["level_id"]) for item in payment_items if item["level_id"]),
                    "",
                )
                package_level.value = level_value
                expected_left = {
                    int(item["hour_type_id"]): float(item["hours"])
                    for item in package["items"]
                }
                for item in payment_items:
                    type_id = int(item["hour_type_id"])
                    hours_value = float(item["hours"] or 0)
                    used = min(hours_value, expected_left.get(type_id, 0.0))
                    expected_left[type_id] = expected_left.get(type_id, 0.0) - used
                    extra = hours_value - used
                    if extra > 0:
                        add_gift(update=False)
                        gift_rows[-1]["type"].value = str(type_id)
                        gift_rows[-1]["hours"].value = db.num_text(extra)
            else:
                for item in payment_items:
                    add_row(
                        hour_type_id=item["hour_type_id"],
                        hours=db.num_text(item["hours"]),
                        amount=db.num_text(item["amount"]),
                        level_id=item["level_id"],
                        owner_teacher_id=item["owner_teacher_id"],
                        enrollment_id=item["enrollment_id"],
                        update=False,
                    )
        else:
            add_row("", "", "", None, update=False)

        def apply_owner_defaults():
            """把没手动改过的行的归属老师，按「这个孩子这门课」的归属补上。"""
            sid = picked_student_id()
            for row in rows:
                if row.get("owner_touched"):
                    continue
                lid = (
                    int(row["level"].value)
                    if (row["level"].value or "").strip()
                    else None
                )
                default = (
                    db.default_owner_teacher(sid, lid)
                    if admin
                    else self._my_user_id()
                )
                row["owner"].value = str(default) if default else ""

        if not editing:
            apply_owner_defaults()

        package_dd.on_select = lambda e: apply_package()
        package_level.on_select = lambda e: refresh_total()
        refresh_package_ui(update=False)

        def collect() -> list[dict]:
            items = []
            package = selected_package()
            level_id = (
                int(package_level.value)
                if (package_level.value or "").strip()
                else None
            )
            if package:
                for index, item in enumerate(package["items"]):
                    items.append(
                        {
                            "hour_type_id": int(item["hour_type_id"]),
                            "level_id": level_id,
                            "hours": float(item["hours"]),
                            "amount": float(package["price"]) if index == 0 else 0,
                            "owner_teacher_id": (
                                None if admin else self._my_user_id()
                            ),
                            "enrollment_id": None,
                            "package_item": True,
                        }
                    )
                for gift in gift_rows:
                    try:
                        hours_value = _number(gift["hours"])
                    except ValueError:
                        self._toast("赠送数量填得不对")
                        return []
                    if hours_value <= 0:
                        continue
                    items.append(
                        {
                            "hour_type_id": int(gift["type"].value),
                            "level_id": level_id,
                            "hours": hours_value,
                            "amount": 0,
                            "owner_teacher_id": (
                                None if admin else self._my_user_id()
                            ),
                            "enrollment_id": None,
                            "package_item": False,
                        }
                    )
            else:
                for row in rows:
                    try:
                        hours_value = _number(row["hours"])
                        amount_value = _number(row["amount"])
                    except ValueError:
                        self._toast("数量或金额填得不对")
                        return []
                    if hours_value <= 0:
                        continue
                    items.append(
                        {
                            "hour_type_id": int(row["type"].value),
                            "level_id": int(row["level"].value)
                            if (row["level"].value or "").strip()
                            else None,
                            "hours": hours_value,
                            "amount": amount_value,
                            "owner_teacher_id": (
                                int(row["owner"].value)
                                if admin and (row["owner"].value or "").strip()
                                else (None if admin else self._my_user_id())
                            ),
                            "enrollment_id": (
                                int(row["enroll"].value)
                                if (row["enroll"].value or "").strip()
                                else None
                            ),
                            "package_item": False,
                        }
                    )
            return items

        def save(e):
            if editing and not admin:
                self._toast("已有缴费只能由管理员修改")
                return
            try:
                date.fromisoformat((day.value or "").strip())
            except ValueError:
                day.error = "日期写成 2026-09-05 这样"
                day.update()
                return
            items = collect()
            if not items:
                self._toast("至少填一行的课时数")
                return
            gifts = [
                item
                for item in items
                if not item.get("package_item")
                and float(item.get("amount") or 0) <= 0
            ]
            if gifts:
                zhengke_id = next(
                    (h["id"] for h in hour_types if h["name"] == "正课"),
                    None,
                )
                if zhengke_id and any(
                    int(item["hour_type_id"]) == int(zhengke_id)
                    for item in gifts
                ):
                    self._toast("正课不能作为赠送课时手动添加")
                    return
                if not (note.value or "").strip():
                    note.error = "赠送课时必须写明原因"
                    note.update()
                    return
            # 课时数没问题了，再决定挂到哪个孩子名下（没有档案就当场建一个）
            credentials = None
            if student_dd.value == NEW_STUDENT:
                values = self._student_values(new_fields, require_birth_date=True)
                if values is None:
                    return
                target_id = db.create_student(values)
                credentials = db.ensure_student_account(target_id)
            else:
                target_id = int(student_dd.value)
            if not self._can_manage_student(target_id):
                self._toast("只能给自己名下的学员记缴费")
                return
            args = (
                target_id,
                (day.value or "").strip(),
                items,
                note.value or "",
                int(voucher_dd.value) if (voucher_dd.value or "").strip() else None,
                int(package_dd.value) if (package_dd.value or "").strip() else None,
            )
            try:
                if editing:
                    db.update_payment(payment["id"], *args)
                    self._finish("缴费记录已更新")
                else:
                    db.create_payment(*args)
                    if credentials:
                        self.page.pop_dialog()
                        self.render()
                        self._show_student_credentials(*credentials)
                    else:
                        self._finish("缴费记好了，课时已经加上")
            except ValueError as err:
                self._toast(str(err))

        # 弹窗还没挂到页面上，先只算数值，别急着刷新
        refresh_vouchers(False)
        refresh_total(False)
        body = self._form_column(
            [
                student_dd,
                new_holder,
                day,
                package_dd,
                package_hint,
                package_table_holder,
                package_level,
                ft.Text(
                    "这次买的课时（可以加多行：买的、送的都记上；"
                    "选上等级就会顺手建好「报名课程」）",
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
                ft.Text(
                    "「哪门课程」用来关联孩子已经报过的班；新学员还没有报名时"
                    "选「不指定」，选好每个等级的课时后会顺手创建报名。",
                    size=11,
                    color=ft.Colors.GREY_600,
                ),
                rows_holder,
                rows_actions,
                gift_actions,
                gift_holder,
                voucher_dd,
                voucher_hint,
                total_text,
                issue_hint,
                ft.Text(
                    "手动赠送考级／比赛课时时，必须填写备注原因；"
                    "正课不能作为赠送课时手动添加。",
                    size=11,
                    color=ft.Colors.GREY_600,
                ),
                note,
            ]
        )
        self._show(
            self._dialog(
                "编辑缴费" if editing else "记一笔缴费",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )

    def _vouchers_card(self, s: dict) -> ft.Container:
        """这个孩子名下的代金券：还剩几张、什么时候到期、用在哪几笔缴费。"""
        batches = db.list_vouchers(s["id"])
        total_left = sum(v["remain"] for v in batches if not v["expired"])
        rows = []
        for v in batches:
            if v["expired"]:
                state = f"已过期（{v['expires_on']}）"
                color = ft.Colors.GREY_500
            elif v["remain"] <= 0:
                state = "已用完"
                color = ft.Colors.GREY_500
            else:
                state = f"还剩 {v['remain']} 张 · {v['expires_on']} 到期"
                color = ft.Colors.GREEN_700
            lines = [
                ft.Text(
                    f"{v['count']} 张 × {db.num_text(v['face'])} 元",
                    size=14,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Text(f"{v['issued_on']} 发放（缴费送的）", size=12, color=ft.Colors.GREY_600),
                ft.Text(state, size=12, color=color),
            ]
            for use in db.voucher_uses(v["id"]):
                lines.append(
                    ft.Text(
                        f"{use['paid_on']} 抵扣了 {db.num_text(use['voucher_amount'])} 元",
                        size=12,
                        color=ft.Colors.BLUE_700,
                    )
                )
            rows.append(
                ft.Container(
                    content=ft.Column(lines, spacing=2),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        if not rows:
            rows = [
                ft.Text(
                    "还没有代金券。交正课课时费的时候会自动送（面额 = 正课金额 ÷ 10，一次 10 张）。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            ]
        return self._section(f"代金券（还能用 {total_left} 张）", ft.Column(rows, spacing=10))

    def _student_lessons_card(self, s: dict) -> ft.Container:
        """这个孩子上过哪些课。"""
        rows = db.student_recent_lessons(s["id"], limit=10)
        items = []
        for r in rows:
            present = int(r["attendance"] or 0)
            if present:
                points = db.attendance_points(r)
                hours = float(r["minutes"] or 0) / 60 if r["class_type_deduct"] else 0
                state = ft.Text("出勤", size=12, color=ft.Colors.GREEN_700)
            else:
                points = 0
                hours = 0
                state = ft.Text("请假", size=12, color=ft.Colors.ORANGE_700)
            tail = []
            if points:
                tail.append(f"+{db.num_text(points)} 分")
            if hours:
                tail.append(f"扣 {db.num_text(hours)} 课时")
            if present and not hours:
                tail.append("不扣课时")
            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        f"{_date_text(r['lesson_date'])} {r['start_time']}",
                                        size=13,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    ft.Text(
                                        f"{db.lesson_label(r)}",
                                        size=12,
                                        color=ft.Colors.GREY_600,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Column(
                                [
                                    state,
                                    ft.Text(
                                        " · ".join(tail) or "—",
                                        size=11,
                                        color=ft.Colors.GREY_600,
                                    ),
                                ],
                                spacing=2,
                                horizontal_alignment=ft.CrossAxisAlignment.END,
                            ),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=ft.Colors.GREY_400),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                    ink=True,
                    on_click=lambda e, lid=r["lesson_id"]: self.open_lesson(lid),
                )
            )
        if not items:
            items = [
                ft.Text(
                    "还没有上过课。到「上课记录」里点他的名字加上就行。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            ]
        return self._section(
            f"上课记录（最近 {len(rows)} 次 · 点一条看详情）",
            ft.Column(items, spacing=10),
        )

    def _payments_card(self, s: dict) -> ft.Container:
        admin = self.is_admin()
        payments = db.list_payments(s["id"], limit=5)
        self._payment_items_map = db.items_by_payment([p["id"] for p in payments])
        total = db.income_total(student_id=s["id"])
        items = []
        for p in payments:
            bits = self._payment_item_bits(p)
            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(_date_text(p["paid_on"]), size=13, weight=ft.FontWeight.W_600),
                                    ft.Text(" · ".join(bits) or "—", size=12, color=ft.Colors.GREY_600),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Text(f"{db.num_text(p['amount'])} 元", size=14, weight=ft.FontWeight.W_600),
                            *(
                                [
                                    ft.IconButton(
                                        ft.Icons.DELETE_OUTLINE,
                                        tooltip="删除",
                                        icon_size=18,
                                        on_click=lambda e, pay=p: self._confirm(
                                            "删除这笔缴费",
                                            f"确定删除这笔 {db.num_text(pay['amount'])} 元吗？"
                                            "对应的课时会一起扣掉。",
                                            lambda: db.delete_payment(pay["id"]),
                                        ),
                                    )
                                ]
                                if admin
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
        if not items:
            items = [ft.Text("还没交过费", size=12, color=ft.Colors.GREY_600)]
        return self._section(
            f"缴费记录（累计 {db.num_text(total)} 元）",
            ft.Column(items, spacing=10),
            action=(
                ft.Button(
                    "记一笔",
                    icon=ft.Icons.ADD,
                    on_click=lambda e: self._open_payment_dialog(None, s["id"]),
                )
                if self._can_manage_student(s["id"])
                else None
            ),
        )
