"""课程设置。"""

from __future__ import annotations

import io
from pathlib import Path

import flet as ft
from PIL import Image, ImageOps

import db
from .common import DIALOG_WIDTH, _dd, _opts, _stored_name, _teacher_opts, _tf


class SettingsMixin:
    """课程设置（ClassHoursApp 的一部分）。"""

    def _settings_view(self) -> ft.Column:
        cards: list[ft.Control] = [self._account_card()]
        if self.is_admin():
            cards += [
                self._poster_card(),
                self._levels_card(),
                self._class_types_card(),
                self._schools_card(),
                self._hour_types_card(),
                self._recompute_card(),
                self._users_card(),
            ]
        return ft.Column(
            [
                self._header(
                    "设置",
                    f"当前账号：{self._whoami()}（{db.ROLE_NAMES.get((self.user or {}).get('role'), '')}）",
                ),
                *cards,
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _poster_card(self) -> ft.Container:
        """发给家长的海报上印什么：机构名 + 联系方式 + 二维码。"""
        brand = ft.TextField(
            label="机构名（海报上角）",
            value=db.get_meta("poster_brand"),
            width=DIALOG_WIDTH,
            dense=True,
            hint_text="例如：拾光机器人编程",
        )
        contact = ft.TextField(
            label="联系方式（海报底部，可不填）",
            value=db.get_meta("poster_contact"),
            width=DIALOG_WIDTH,
            dense=True,
            hint_text="例如：微信/电话 138-0000-0000",
        )
        qr_name = (db.get_meta("poster_qr") or "").strip()
        qr_path = db.UPLOAD_DIR / Path(qr_name).name if qr_name else None
        if qr_path is not None and not qr_path.is_file():
            qr_path = None

        def save(e) -> None:
            db.set_meta("poster_brand", (brand.value or "").strip())
            db.set_meta("poster_contact", (contact.value or "").strip())
            self._toast("海报署名存好了")

        def save_poster_image(
            files: list,
            *,
            meta_key: str,
            prefix: str,
            noun: str,
        ) -> None:
            source = next(
                (
                    item
                    for item in files
                    if getattr(item, "bytes", None)
                    and (getattr(item, "name", "") or "").lower().endswith(
                        (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
                    )
                ),
                None,
            )
            if source is None:
                self._toast(f"请选一张{noun}图片")
                return
            try:
                image = Image.open(io.BytesIO(bytes(source.bytes)))
                image.load()
                image = ImageOps.exif_transpose(image)
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert(
                        "RGBA" if "transparency" in image.info else "RGB"
                    )
                image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                out = io.BytesIO()
                image.save(out, "PNG", optimize=True)
            except Exception:
                self._toast(f"这张图片读不出来，换一张 PNG 或 JPG {noun}")
                return
            stored = _stored_name(
                getattr(source, "name", "") or f"{prefix}.png",
                suffix=".png",
                prefix=prefix,
            )
            target = db.UPLOAD_DIR / stored
            try:
                target.write_bytes(out.getvalue())
            except OSError:
                self._toast(f"{noun}存不下来，检查 data 文件夹权限")
                return
            old_name = (db.get_meta(meta_key) or "").strip()
            db.set_meta(meta_key, stored)
            if old_name and Path(old_name).name != stored:
                try:
                    (db.UPLOAD_DIR / Path(old_name).name).unlink(missing_ok=True)
                except OSError:
                    pass
            self.render()
            self._toast(f"海报{noun}换好了")

        def save_qr(files: list) -> None:
            save_poster_image(
                files,
                meta_key="poster_qr",
                prefix="poster_qr",
                noun="二维码",
            )

        def save_logo(files: list) -> None:
            save_poster_image(
                files,
                meta_key="poster_logo",
                prefix="poster_logo",
                noun="Logo",
            )

        def remove_poster_image(meta_key: str, noun: str) -> None:
            old_name = (db.get_meta(meta_key) or "").strip()
            if old_name:
                try:
                    (db.UPLOAD_DIR / Path(old_name).name).unlink(missing_ok=True)
                except OSError:
                    pass
            db.set_meta(meta_key, "")
            self.render()
            self._toast(f"海报{noun}已移除")

        def choose_qr(e) -> None:
            self._files_callback = save_qr

        def choose_logo(e) -> None:
            self._files_callback = save_logo

        def image_controls(
            path: Path | None,
            *,
            meta_key: str,
            noun: str,
            height: int,
        ) -> list[ft.Control]:
            if path is None:
                return []
            return [
                ft.Container(
                    content=ft.Image(
                        src=f"/{path.name}",
                        width=180,
                        height=height,
                        fit=ft.BoxFit.CONTAIN,
                    ),
                    padding=8,
                    border_radius=12,
                    bgcolor=ft.Colors.WHITE,
                    border=ft.Border.all(1, ft.Colors.GREY_300),
                ),
                ft.TextButton(
                    f"移除{noun}",
                    icon=ft.Icons.DELETE_OUTLINE,
                    on_click=lambda e: remove_poster_image(meta_key, noun),
                ),
            ]

        qr_controls = image_controls(
            qr_path,
            meta_key="poster_qr",
            noun="二维码",
            height=150,
        )
        logo_name = (db.get_meta("poster_logo") or "").strip()
        logo_path = db.UPLOAD_DIR / Path(logo_name).name if logo_name else None
        if logo_path is not None and not logo_path.is_file():
            logo_path = None
        logo_controls = image_controls(
            logo_path,
            meta_key="poster_logo",
            noun="Logo",
            height=110,
        )
        logo_uploader = ft.Button(
            "更换 Logo" if logo_path is not None else "上传 Logo",
            icon=ft.Icons.IMAGE_OUTLINED,
            on_click=choose_logo,
            action=ft.PickFiles(
                self.picker,
                allow_multiple=False,
                with_data=True,
                compression_quality=0,
                file_type=ft.FilePickerFileType.IMAGE,
            ),
        )
        qr_uploader = ft.Button(
            "更换二维码" if qr_path is not None else "上传二维码",
            icon=ft.Icons.QR_CODE_2,
            on_click=choose_qr,
            action=ft.PickFiles(
                self.picker,
                allow_multiple=False,
                with_data=True,
                compression_quality=0,
                file_type=ft.FilePickerFileType.IMAGE,
            ),
        )

        return self._section(
            "海报署名",
            ft.Column(
                [
                    ft.Text(
                        "给家长的课堂海报会印上机构名、联系方式；Logo 和二维码都可不上传。",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    brand,
                    ft.Text(
                        "机构 Logo（建议透明背景 PNG，会显示在机构名左边）",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    *logo_controls,
                    logo_uploader,
                    contact,
                    ft.Text(
                        "联系二维码（建议清晰方形 PNG，海报底部居中显示）",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    *qr_controls,
                    qr_uploader,
                    ft.Row([ft.Button("保存", icon=ft.Icons.SAVE, on_click=save)]),
                ],
                spacing=10,
            ),
        )

    def _hour_types_card(self) -> ft.Container:
        rows = []
        for h in db.list_hour_types():
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(h["name"], size=14, weight=ft.FontWeight.W_600, expand=True),
                            ft.Switch(
                                label="剩余不足时提醒",
                                value=bool(h["warn"]),
                                on_change=lambda e, hid=h["id"]: self._set_hour_warn(
                                    hid, e.control.value
                                ),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        return self._section(
            "课时账户种类",
            ft.Column(
                [
                    ft.Text(
                        "勾上的账户，剩余少于 3 课时会在学员列表上亮提醒（一般只勾正课；"
                        "考级、竞赛这种送的小额用完就算了）。",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    *rows,
                ],
                spacing=10,
            ),
        )

    def _set_hour_warn(self, hour_type_id: int, value: bool) -> None:
        db.set_hour_type_warn(hour_type_id, bool(value))
        self.render()

    def _recompute_card(self) -> ft.Container:
        def run(e):
            count = db.recompute_all_hours()
            self.render()
            self._toast(f"重算完了（{count} 个孩子）")

        return self._section(
            "课时重算",
            ft.Column(
                [
                    ft.Text(
                        "如果以前出现过「竞赛课扣到正课」「先上课、后交的课时费」这类情况，"
                        "点一下会按现在的账，把所有孩子上课扣的课时重算一遍"
                        "（缴费和手工调整不动）。",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    ft.Row(
                        [
                            ft.Button(
                                "重算所有孩子的课时",
                                icon=ft.Icons.REFRESH,
                                on_click=run,
                            )
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                ],
                spacing=10,
            ),
        )

    def _account_card(self) -> ft.Container:
        return self._section(
            "我的账号",
            ft.Row(
                [
                    ft.TextButton(
                        "修改密码",
                        icon=ft.Icons.KEY,
                        on_click=lambda e: self._open_change_password(),
                    ),
                    ft.TextButton(
                        "退出登录",
                        icon=ft.Icons.LOGOUT,
                        on_click=lambda e: self.logout(),
                    ),
                ],
                spacing=8,
                wrap=True,
            ),
        )

    def _users_card(self) -> ft.Container:
        rows = []
        teachers = 0
        for u in db.list_users():
            bits = [db.ROLE_NAMES.get(u["role"], u["role"])]
            if u["is_teacher"]:
                teachers += 1
            else:
                bits.append("不排课")
            if u["phone"]:
                bits.append(u["phone"])
            if not u["active"]:
                bits.append("已停用")
            bits.append(f"用户名 {u['username']}")
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        u["display_name"] or u["username"],
                                        size=14,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    ft.Text(" · ".join(bits), size=12, color=ft.Colors.GREY_600),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(
                                ft.Icons.KEY,
                                tooltip="重设密码",
                                icon_size=18,
                                on_click=lambda e, uid=u["id"]: self._open_change_password(uid),
                            ),
                            ft.IconButton(
                                ft.Icons.EDIT,
                                tooltip="编辑",
                                icon_size=18,
                                on_click=lambda e, row=u: self._open_user_dialog(row),
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                tooltip="删除",
                                icon_size=18,
                                on_click=lambda e, row=u: self._ask_delete_account(row),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        return self._section(
            "老师账号",
            ft.Column(
                [
                    ft.Text(
                        "勾了「上课老师」的账号，才会出现在报名、缴费、排课的"
                        "「归属老师／上课老师」下拉里，并参与按老师的收入与课时统计。",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    ft.Text(
                        f"现在有 {teachers} 个上课老师。"
                        "老师能排课、点名、写教案课评、传照片、记积分兑换；"
                        "改课时、改缴费、删记录、改学员档案只有管理员能做。",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                    *rows,
                    ft.Row(
                        [
                            ft.TextButton(
                                "按课程默认老师补全归属",
                                icon=ft.Icons.RULE,
                                on_click=lambda e: self._backfill_attribution(),
                            ),
                            ft.TextButton(
                                "给没填的课次补上课老师",
                                icon=ft.Icons.ASSIGNMENT_IND,
                                on_click=lambda e: self._backfill_lesson_teachers(),
                            ),
                        ],
                        wrap=True,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                ],
                spacing=10,
            ),
            action=ft.Button(
                "新增老师", icon=ft.Icons.PERSON_ADD, on_click=lambda e: self._open_user_dialog()
            ),
        )

    def _ask_delete_account(self, row: dict) -> None:
        """删老师账号：名下有记录的不让删，提示改成停用。"""
        who = row["display_name"] or row["username"]

        def ok(e):
            self.page.pop_dialog()
            try:
                db.delete_user(row["id"])
            except ValueError as exc:
                self.render()
                self._toast(str(exc))
                return
            self.render()
            self._toast("账号已删除")

        self._show(
            self._dialog(
                "删除账号",
                ft.Text(f"确定删除「{who}」这个账号吗？"),
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("删除", on_click=ok),
                ],
            )
        )

    def _backfill_attribution(self) -> None:
        """给没指定过归属的老报名／老缴费／老点名，按课程默认老师补上；
        老报名还能对上课程的，也一起挂到课程上。"""
        count = db.backfill_teacher_attribution()
        linked = db.backfill_enrollment_classes()
        self.render()
        self._toast(
            f"补全完成：归属补了 {count} 条"
            + (f"，报名挂上课程的 {linked} 条" if linked else "")
            if (count or linked)
            else "没有要补的：要么都已经指定好，要么还没给课程设默认老师"
        )

    def _backfill_lesson_teachers(self) -> None:
        """老课次没填上课老师的：学生都归同一个老师就算他，否则按课程默认老师。"""
        count = db.backfill_lesson_teachers()
        self.render()
        self._toast(
            f"给 {count} 节老课补上了上课老师（只补了没填的，可以进去单改）"
            if count
            else "没有要补的课次：要么都填过了，要么这些课的孩子还没定归属、课程也没默认老师"
        )

    def _open_user_dialog(self, user: dict | None = None) -> None:
        editing = user is not None
        username = _tf("用户名（登录用）", user["username"] if editing else "", width=DIALOG_WIDTH)
        display = _tf("姓名", user["display_name"] if editing else "", width=DIALOG_WIDTH)
        phone = _tf("电话", user["phone"] if editing else "", width=DIALOG_WIDTH)
        password = _tf(
            "密码",
            "",
            width=DIALOG_WIDTH,
            password=True,
            hint_text="留空表示不改（改密码用钥匙图标）" if editing else "",
        )
        role = _dd(
            "身份",
            _opts([(db.ROLE_TEACHER, "老师"), (db.ROLE_ROOT, "管理员")]),
            value=user["role"] if editing else db.ROLE_TEACHER,
            width=DIALOG_WIDTH,
        )
        teaching = ft.Switch(
            label="也是上课老师（可以算归属、排课、算工资）",
            value=bool(user["is_teacher"]) if editing else True,
        )
        active = ft.Switch(label="启用这个账号", value=bool(user["active"]) if editing else True)
        if editing:
            username.read_only = True

        def save(e):
            if not editing:
                try:
                    db.create_user(
                        username.value or "",
                        password.value or "",
                        display.value or "",
                        role.value or db.ROLE_TEACHER,
                        phone.value or "",
                        bool(teaching.value),
                    )
                except ValueError as exc:
                    self._toast(str(exc))
                    return
                self._finish("老师账号建好了")
                return
            try:
                db.update_user(
                    user["id"],
                    display.value or "",
                    role.value or db.ROLE_TEACHER,
                    bool(active.value),
                    phone.value or "",
                    bool(teaching.value),
                )
                if (password.value or "").strip():
                    db.set_user_password(user["id"], password.value)
            except ValueError as exc:
                self._toast(str(exc))
                return
            self._finish("账号已更新")

        body = self._form_column(
            [username, display, phone, password, role, teaching, active]
            if editing
            else [username, display, phone, password, role, teaching]
        )
        self._show(
            self._dialog(
                "编辑账号" if editing else "新增老师",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )

    def _levels_card(self) -> ft.Container:
        levels = db.list_levels()
        rows = []
        for l in levels:
            used = db.count_level_usage(l["id"])
            used_text = db.level_usage_text(l["id"])
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(db.level_full_name(l), size=14, weight=ft.FontWeight.W_600),
                                    ft.Text(
                                        f"默认 {l['default_minutes']} 分钟"
                                        + (
                                            f" · 默认老师 {l['default_teacher_name']}"
                                            if l["default_teacher_name"]
                                            else " · 还没设默认老师"
                                        )
                                        + (
                                            f" · {used_text}在用（删了会清空这些记录上的等级）"
                                            if used_text
                                            else " · 还没人用"
                                        ),
                                        size=12,
                                        color=ft.Colors.GREY_600,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(
                                ft.Icons.EDIT,
                                tooltip="编辑",
                                icon_size=18,
                                on_click=lambda e, lv=l: self._open_level_dialog(lv),
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                tooltip="删除",
                                icon_size=18,
                                on_click=lambda e, lv=l: self._delete_level(lv),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        action = ft.Button("新增等级", icon=ft.Icons.ADD, on_click=lambda e: self._open_level_dialog(None))
        return self._section(
            "等级与默认时长",
            ft.Column(rows or [ft.Text("还没有等级", size=12, color=ft.Colors.GREY_600)], spacing=10),
            action=action,
        )

    def _schools_card(self) -> ft.Container:
        """学校字典：这里加过的学校，填学员档案时旁边下拉就能直接挑。"""
        rows = []
        for s in db.school_rows():
            hint = f"{s['used']} 个孩子在读" if s["used"] else "还没有孩子填这个学校"
            controls = [
                ft.Column(
                    [
                        ft.Text(s["name"], size=14, weight=ft.FontWeight.W_600),
                        ft.Text(hint, size=12, color=ft.Colors.GREY_600),
                    ],
                    spacing=2,
                    expand=True,
                )
            ]
            if s["id"] is not None:
                controls.append(
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE,
                        tooltip="从下拉里去掉",
                        icon_size=18,
                        on_click=lambda e, row=s: self._confirm(
                            "去掉这个学校",
                            (
                                f"「{row['name']}」还有 {row['used']} 个孩子在用，"
                                "要先把那些孩子的档案改成别的学校，它才会真的不见。"
                                if row["used"]
                                else f"确定把「{row['name']}」从下拉候选里去掉了？"
                            ),
                            lambda: db.delete_school(row["id"]),
                        ),
                    )
                )
            rows.append(
                ft.Container(
                    content=ft.Row(controls, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )

        new_name = _tf("新学校名", "", expand=True)

        def add(e):
            try:
                db.add_school(new_name.value or "")
            except ValueError:
                new_name.error = "请填学校名"
                new_name.update()
                return
            self.render()
            self._toast("学校加好了")

        return self._section(
            "学校",
            ft.Column(
                [
                    ft.Column(
                        rows or [ft.Text("还没有学校", size=12, color=ft.Colors.GREY_600)],
                        spacing=10,
                    ),
                    ft.Row(
                        [new_name, ft.Button("加进去", icon=ft.Icons.ADD, on_click=add)],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=12,
            ),
        )

    def _class_types_card(self) -> ft.Container:
        class_types = db.list_class_types()
        rows = []
        for c in class_types:
            if not c["deduct"]:
                rule = "不扣课时"
            else:
                rule = f"扣「{c['primary_name']}」课时"
                if c["fallback_name"]:
                    rule += f"，不够时补扣「{c['fallback_name']}」"
            rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(c["name"], size=14, weight=ft.FontWeight.W_600),
                                    ft.Text(rule, size=12, color=ft.Colors.GREY_600),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(
                                ft.Icons.EDIT,
                                tooltip="编辑",
                                icon_size=18,
                                on_click=lambda e, ct=c: self._open_class_type_dialog(ct),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    border_radius=10,
                    bgcolor=ft.Colors.GREY_50,
                )
            )
        return self._section("课型与扣课时规则", ft.Column(rows, spacing=10))

    def _delete_level(self, level) -> None:
        """删等级。有记录在用的话，说清楚会清空那些记录上的等级，再删。"""
        used = db.level_usage_text(level["id"])
        name = db.level_full_name(level)

        def ok(e):
            self.page.pop_dialog()
            try:
                db.delete_level(level["id"], force=True)
            except ValueError as exc:
                self.render()
                self._toast(str(exc))
                return
            self.render()
            self._toast(
                f"「{name}」删掉了" + ("（那些记录上的等级已清空）" if used else "")
            )

        message = (
            f"「{name}」现在有 {used} 在用它。\n\n"
            "删掉以后：课程、缴费、课次、报名这些记录都还在，"
            "只是它们上面记的等级会变成空。\n\n"
            "确定要删吗？"
            if used
            else f"确定删除「{name}」吗？"
        )
        self._show(
            self._dialog(
                "删除等级",
                ft.Text(message),
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("仍然删除" if used else "删除", on_click=ok),
                ],
            )
        )

    def _open_level_dialog(self, level) -> None:
        editing = level is not None
        subject = _tf("科目（如 GPL、STEM）", level["subject"] if editing else "", width=DIALOG_WIDTH)
        name = _tf("等级／阶段（如 Lvl-01）", level["name"] if editing else "", width=DIALOG_WIDTH)
        minutes = _tf(
            "默认时长（分钟）",
            level["default_minutes"] if editing else 90,
            width=DIALOG_WIDTH,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        teacher = _dd(
            "默认老师（报名时自动带出）",
            _teacher_opts("不指定"),
            value=(
                str(level["default_teacher_id"])
                if editing and level["default_teacher_id"]
                else ""
            ),
            width=DIALOG_WIDTH,
        )

        def save(e):
            if not (name.value or "").strip():
                name.error = "请填等级名称"
                name.update()
                return
            try:
                mins = int(float(minutes.value or 0))
            except ValueError:
                minutes.error = "请填数字"
                minutes.update()
                return
            if editing:
                db.update_level(
                    level["id"],
                    subject.value or "",
                    name.value,
                    mins,
                    int(teacher.value) if (teacher.value or "").strip() else None,
                )
            else:
                db.create_level(
                    subject.value or "",
                    name.value,
                    mins,
                    int(teacher.value) if (teacher.value or "").strip() else None,
                )
            self._finish("等级已保存")

        body = self._form_column([subject, name, minutes, teacher])
        self._show(
            self._dialog(
                "编辑等级" if editing else "新增等级",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )

    def _open_class_type_dialog(self, class_type) -> None:
        hour_types = db.list_hour_types()
        options = [ft.DropdownOption(key="", text="不扣")] + _opts(
            [(h["id"], h["name"]) for h in hour_types]
        )
        deduct = ft.Switch(label="这节课扣课时", value=bool(class_type["deduct"]))
        primary = _dd(
            "主扣账户",
            options,
            value=str(class_type["primary_hour_type_id"] or ""),
            width=DIALOG_WIDTH,
        )
        fallback = _dd(
            "账户不够时补扣",
            options,
            value=str(class_type["fallback_hour_type_id"] or ""),
            width=DIALOG_WIDTH,
        )

        def save(e):
            db.update_class_type(
                class_type["id"],
                bool(deduct.value),
                int(primary.value) if (primary.value or "").strip() else None,
                int(fallback.value) if (fallback.value or "").strip() else None,
            )
            self._finish("规则已保存")

        body = self._form_column([deduct, primary, fallback])
        self._show(
            self._dialog(
                f"课型：{class_type['name']}",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )
