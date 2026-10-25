"""论坛悬赏：学生和老师都可以发布、回答和采纳。"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from pathlib import Path

import flet as ft

import db
from .common import DIALOG_WIDTH, _chip, _date_text, _dd, _opts, _stored_name, _tf
from .files import _shrink_photo


class ForumMixin:
    """学生和老师共同使用的积分悬赏论坛。"""

    def _forum_view(self) -> ft.Control:
        all_bounties = db.list_forum_bounties()
        keyword = (self.forum_keyword or "").strip()
        bounties = [
            bounty
            for bounty in all_bounties
            if not keyword or keyword.casefold() in self._forum_search_blob(bounty)
        ]
        user_id = self._my_user_id() or 0
        balance = db.forum_points_balance(user_id)
        me = db.get_user(user_id) if user_id else None
        my_nickname = (me or {}).get("forum_nickname") or "匿名用户"
        mute = db.forum_mute_state(user_id)
        items = [
            self._forum_bounty_card(bounty)
            for bounty in bounties
        ] or [
            self._card(
                ft.Text(
                    (
                        "没有找到匹配的悬赏，换个关键词试试。"
                        if keyword
                        else "论坛里还没有悬赏。学生和老师都可以发布第一个问题。"
                    ),
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            )
        ]
        return ft.Column(
            [
                self._header(
                    "论坛悬赏",
                    f"我的昵称 {my_nickname} · 可用积分 {db.num_text(balance)}",
                    [
                        ft.TextButton(
                            "修改昵称",
                            icon=ft.Icons.EDIT,
                            on_click=lambda e: self._open_forum_nickname_dialog(),
                        ),
                        ft.TextButton(
                            "积分流水",
                            icon=ft.Icons.RECEIPT_LONG,
                            on_click=lambda e: self._open_forum_history_dialog(),
                        ),
                        ft.Button(
                            "发布悬赏",
                            icon=ft.Icons.ADD_COMMENT,
                            on_click=lambda e: self._open_forum_post_dialog(),
                            disabled=mute["active"],
                        )
                    ],
                ),
                ft.Row(
                    [
                        ft.TextField(
                            value=keyword,
                            hint_text="搜标题、内容、回答或昵称",
                            dense=True,
                            prefix_icon=ft.Icons.SEARCH,
                            expand=True,
                            on_submit=self._on_forum_search_submit,
                        ),
                        *(
                            [
                                ft.TextButton(
                                    "清空搜索",
                                    icon=ft.Icons.CLOSE,
                                    on_click=self._clear_forum_search,
                                )
                            ]
                            if keyword
                            else []
                        ),
                    ],
                    spacing=8,
                ),
                ft.Text(
                    "悬赏积分由发布者填写，可以先冻结积分，采纳答案后转给回答者；"
                    "无人采纳前可以取消并退回。学生和老师都能发布与回答。",
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
                *(
                    [
                        ft.Container(
                            ft.Text(
                                f"你已被禁言至 {mute['muted_until'][:16]}。"
                                f"原因：{mute['reason']}",
                                size=12,
                                color=ft.Colors.RED_600,
                            ),
                            padding=10,
                            border_radius=8,
                            bgcolor=ft.Colors.RED_50,
                        )
                    ]
                    if mute["active"]
                    else []
                ),
                ft.Text(
                    f"找到 {len(bounties)} 条悬赏" if keyword else f"共 {len(bounties)} 条悬赏",
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
                *items,
                ft.Container(height=8),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _open_forum_nickname_dialog(
        self, target_user_id: int | None = None
    ) -> None:
        user_id = int(target_user_id or self._my_user_id() or 0)
        target = db.get_user(user_id)
        if target is None:
            self._toast("账号不存在")
            return
        if not self.is_admin() and user_id != self._my_user_id():
            self._toast("只能修改自己的论坛昵称")
            return
        nickname = _tf(
            "论坛昵称",
            target.get("forum_nickname") or "",
            width=DIALOG_WIDTH,
            hint_text="2～16 个汉字、字母、数字或下划线",
        )

        def save(e):
            try:
                value = db.update_forum_nickname(
                    user_id,
                    nickname.value or "",
                    self._my_user_id(),
                )
            except ValueError as err:
                nickname.error = str(err)
                nickname.update()
                return
            if self.user and self.user.get("id") == user_id:
                self.user["forum_nickname"] = value
            self._finish("论坛昵称已更新")

        self._show(
            self._dialog(
                "修改论坛昵称",
                self._form_column(
                    [
                        ft.Text(
                            "昵称会显示在悬赏、回答和指定交易对象中。",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                        nickname,
                    ]
                ),
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("保存", on_click=save),
                ],
            )
        )

    def _forum_search_blob(self, bounty: dict) -> str:
        parts = [bounty.get("title") or "", bounty.get("content") or ""]
        parts.append(
            self._forum_person_name(
                bounty.get("author_name") or "",
                bounty.get("author_nickname") or "",
                bounty.get("author_role") or "",
            )
        )
        if bounty.get("target_user_id"):
            parts.append(
                self._forum_person_name(
                    bounty.get("target_name") or "",
                    bounty.get("target_nickname") or "",
                    bounty.get("target_role") or "",
                )
            )
        for answer in db.list_forum_answers(bounty["id"]):
            parts.append(answer.get("content") or "")
            parts.append(
                self._forum_person_name(
                    answer.get("author_name") or "",
                    answer.get("author_nickname") or "",
                    answer.get("author_role") or "",
                )
            )
        return "\n".join(parts).casefold()

    def _on_forum_search_submit(self, e) -> None:
        self.forum_keyword = (e.control.value or "").strip()
        self.render()

    def _clear_forum_search(self, e=None) -> None:
        self.forum_keyword = ""
        self.render()

    def _open_forum_history_dialog(self) -> None:
        rows = db.forum_point_history(self._my_user_id() or 0)
        items: list[ft.Control] = []
        for row in rows:
            change = float(row.get("change") or 0)
            items.append(
                ft.Row(
                    [
                        ft.Text(
                            _date_text(row.get("happened_on") or ""),
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    row.get("kind") or "积分变化",
                                    size=12,
                                    weight=ft.FontWeight.W_600,
                                ),
                                ft.Text(
                                    row.get("note") or "",
                                    size=11,
                                    color=ft.Colors.GREY_600,
                                ),
                            ],
                            spacing=1,
                            tight=True,
                            expand=True,
                        ),
                        ft.Text(
                            f"{'+' if change > 0 else ''}{db.num_text(change)}",
                            size=14,
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.GREEN_700
                            if change > 0
                            else ft.Colors.RED_600,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        if not items:
            items = [
                ft.Text(
                    "还没有论坛积分流水。发布悬赏或回答被采纳后会记录在这里。",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            ]
        self._show(
            self._dialog(
                "我的积分流水",
                ft.Container(
                    ft.Column(
                        items,
                        spacing=8,
                        tight=True,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    height=360,
                ),
                [ft.Button("关闭", on_click=self._close)],
            )
        )

    def _forum_role_name(self, role: str) -> str:
        return db.ROLE_NAMES.get(role, "")

    def _forum_person_name(
        self, real_name: str, nickname: str, role: str
    ) -> str:
        if self.is_student():
            return nickname or "匿名用户"
        return f"{real_name} · {self._forum_role_name(role)}（{nickname}）"

    def _forum_bounty_card(self, bounty: dict) -> ft.Container:
        user_id = self._my_user_id() or 0
        status_color = {
            "待解决": ft.Colors.ORANGE_700,
            "已完成": ft.Colors.GREEN_700,
            "已取消": ft.Colors.GREY_600,
        }.get(bounty["status"], ft.Colors.GREY_600)
        bounty_badge = ft.Container(
            ft.Row(
                [
                    ft.Icon(
                        ft.Icons.STARS,
                        size=17,
                        color=ft.Colors.WHITE,
                    ),
                    ft.Text(
                        f"{db.num_text(bounty['bounty_points'])} 积分",
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                ],
                spacing=4,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=11, vertical=5),
            border_radius=16,
            bgcolor=ft.Colors.ORANGE_700,
        )
        head = ft.Row(
            [
                ft.Text(
                    bounty["title"],
                    size=15,
                    weight=ft.FontWeight.W_600,
                    expand=True,
                ),
                bounty_badge,
                _chip(bounty["status"], status_color),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        meta = (
            f"{self._forum_person_name(bounty['author_name'], bounty['author_nickname'], bounty['author_role'])} · "
            f"{_date_text(bounty['created_at'])}"
        )
        if bounty.get("target_user_id"):
            target_name = self._forum_person_name(
                bounty.get("target_name") or "已停用用户",
                bounty.get("target_nickname") or "匿名用户",
                bounty.get("target_role") or "",
            )
            meta += f" · 指定给 {target_name}"
        else:
            meta += " · 公开悬赏"
        answers = db.list_forum_answers(bounty["id"])
        images = db.list_files("forum_bounty", bounty["id"], "图片")
        answer_controls: list[ft.Control] = []
        for answer in answers:
            accepted = bounty.get("accepted_answer_id") == answer["id"]
            answer_controls.append(
                ft.Container(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        self._forum_person_name(
                                            answer["author_name"],
                                            answer["author_nickname"],
                                            answer["author_role"],
                                        ),
                                        size=12,
                                        weight=ft.FontWeight.W_600,
                                        expand=True,
                                    ),
                                    *(
                                        [_chip("已采纳", ft.Colors.GREEN_700)]
                                        if accepted
                                        else []
                                    ),
                                ],
                                spacing=6,
                            ),
                            ft.Text(answer["content"], size=13),
                            *(
                                [
                                    ft.TextButton(
                                        "采纳这个答案",
                                        icon=ft.Icons.CHECK,
                                        on_click=lambda e, ans=answer: self._confirm(
                                            "采纳答案",
                                            f"采纳后会把 {db.num_text(bounty['bounty_points'])} "
                                            "积分转给回答者，确定吗？",
                                            lambda: db.accept_forum_answer(
                                                bounty["id"],
                                                ans["id"],
                                                user_id,
                                            ),
                                            ok_text="采纳",
                                            done_text="答案已采纳，积分已转给回答者",
                                        ),
                                    )
                                ]
                                if bounty["status"] == "待解决"
                                and bounty["author_user_id"] == user_id
                                else []
                            ),
                        ],
                        spacing=5,
                        tight=True,
                    ),
                    padding=10,
                    border_radius=8,
                    bgcolor=ft.Colors.GREEN_50 if accepted else ft.Colors.GREY_50,
                )
            )
        if not answers:
            answer_controls.append(
                ft.Text("还没有回答。", size=12, color=ft.Colors.GREY_500)
            )

        actions: list[ft.Control] = []
        if bounty["status"] == "待解决" and bounty["author_user_id"] == user_id:
            actions.append(
                ft.TextButton(
                    "取消悬赏",
                    on_click=lambda e, row=bounty: self._confirm(
                        "取消悬赏",
                        "取消后冻结的积分会退回，确定吗？",
                        lambda: db.cancel_forum_bounty(row["id"], user_id),
                        ok_text="取消悬赏",
                        done_text="悬赏已取消，积分已退回",
                    ),
                )
            )
        can_answer = (
            bounty["status"] == "待解决"
            and bounty["author_user_id"] != user_id
            and not db.forum_mute_state(user_id)["active"]
            and (
                not bounty.get("target_user_id")
                or int(bounty["target_user_id"]) == user_id
            )
        )
        if can_answer:
            actions.append(
                ft.Button(
                    "我来回答",
                    icon=ft.Icons.REPLY,
                    on_click=lambda e, row=bounty: self._open_forum_answer_dialog(row),
                )
            )
        if self.is_admin():
            actions.append(
                ft.TextButton(
                    "管理员扣分",
                    icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                    on_click=lambda e, row=bounty: self._open_forum_penalty_dialog(row),
                )
            )
            if bounty.get("author_role") != db.ROLE_ROOT:
                author_mute = db.forum_mute_state(bounty["author_user_id"])
                actions.append(
                    ft.TextButton(
                        "解除禁言" if author_mute["active"] else "禁言",
                        icon=ft.Icons.BLOCK
                        if not author_mute["active"]
                        else ft.Icons.LOCK_OPEN,
                        on_click=(
                            (lambda e, row=bounty: self._unmute_forum_author(row))
                            if author_mute["active"]
                            else (
                                lambda e, row=bounty: self._open_forum_mute_dialog(row)
                            )
                        ),
                    )
                )
        return self._card(
            ft.Column(
                [
                    head,
                    ft.Text(meta, size=11, color=ft.Colors.GREY_600),
                    ft.Text(bounty["content"], size=13, color=ft.Colors.GREY_800),
                    *(
                        [
                            ft.Row(
                                [
                                    ft.Container(
                                        ft.Image(
                                            src=db.file_url(image),
                                            width=110,
                                            height=110,
                                            fit=ft.BoxFit.COVER,
                                            border_radius=8,
                                        ),
                                        border_radius=8,
                                        ink=True,
                                        on_click=lambda e, row=image: self._open_forum_image(row),
                                        tooltip=image["filename"],
                                    )
                                    for image in images
                                ],
                                spacing=8,
                                wrap=True,
                                run_spacing=8,
                            )
                        ]
                        if images
                        else []
                    ),
                    *(
                        [
                            ft.Container(
                                ft.Column(
                                    [
                                        ft.Text(
                                            f"管理员扣除 {db.num_text(bounty['penalty_points'])} 积分",
                                            size=12,
                                            weight=ft.FontWeight.W_600,
                                            color=ft.Colors.RED_600,
                                        ),
                                        ft.Text(bounty["moderation_note"], size=12),
                                    ],
                                    spacing=2,
                                    tight=True,
                                ),
                                padding=8,
                                border_radius=8,
                                bgcolor=ft.Colors.RED_50,
                            )
                        ]
                        if float(bounty.get("penalty_points") or 0)
                        else []
                    ),
                    ft.Divider(height=1),
                    *answer_controls,
                    *(
                        [
                            ft.Row(
                                actions,
                                alignment=ft.MainAxisAlignment.END,
                                spacing=4,
                            )
                        ]
                        if actions
                        else []
                    ),
                ],
                spacing=8,
            )
        )

    def _open_forum_post_dialog(self) -> None:
        balance = db.forum_points_balance(self._my_user_id() or 0)
        selected_images: list = []
        title = _tf("悬赏标题 *", "", width=DIALOG_WIDTH)
        content = _tf(
            "问题内容 *",
            "",
            width=DIALOG_WIDTH,
            multiline=True,
            min_lines=4,
            max_lines=8,
        )
        points = _tf(
            "悬赏积分 *",
            "0",
            width=DIALOG_WIDTH,
            keyboard_type=ft.KeyboardType.NUMBER,
            hint_text=f"不能小于 0，最多 {db.num_text(balance)}",
        )
        forum_users = db.list_forum_users(self._my_user_id())
        def target_label(user: dict) -> str:
            if self.is_student():
                return user["forum_nickname"] or "匿名用户"
            return (
                f"{user['student_name'] or user['display_name'] or user['username']} · "
                f"{self._forum_role_name(user['role'])}（{user['forum_nickname']}）"
            )

        target = _dd(
            "指定交易对象（可选）",
            [ft.DropdownOption(key="", text="公开悬赏，任何人可回答")]
            + _opts(
                [
                    (u["id"], target_label(u))
                    for u in forum_users
                ]
            ),
            value="",
            width=DIALOG_WIDTH,
            enable_search=True,
            enable_filter=True,
            editable=True,
            menu_height=300,
            hint_text="可直接输入昵称或姓名搜索",
        )
        image_hint = ft.Text(
            "未选择图片（只能上传 1 张）",
            size=12,
            color=ft.Colors.GREY_600,
        )
        image_preview = ft.Image(
            src="",
            width=220,
            height=150,
            fit=ft.BoxFit.COVER,
            border_radius=8,
            visible=False,
        )
        image_preview_name = ft.Text(
            "",
            size=11,
            color=ft.Colors.GREY_600,
            visible=False,
        )
        image_preview_holder = ft.Container(
            ft.Column(
                [image_preview, image_preview_name],
                spacing=4,
                tight=True,
            ),
            padding=8,
            border_radius=10,
            bgcolor=ft.Colors.GREY_50,
            visible=False,
        )

        def pick_images(files: list) -> None:
            valid = [
                f
                for f in files
                if getattr(f, "bytes", None)
                and (getattr(f, "name", "") or "").lower().endswith(
                    (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
                )
            ]
            selected_images[:] = valid[:1]
            if selected_images:
                source = selected_images[0]
                name = getattr(source, "name", "") or "图片"
                suffix = Path(name).suffix.lower()
                preview_data, preview_suffix = _shrink_photo(
                    bytes(source.bytes), suffix
                )
                mime = (
                    "image/png"
                    if preview_suffix == ".png"
                    else "image/gif"
                    if preview_suffix == ".gif"
                    else "image/webp"
                    if preview_suffix == ".webp"
                    else "image/jpeg"
                )
                image_preview.src = (
                    f"data:{mime};base64,"
                    + base64.b64encode(preview_data).decode("ascii")
                )
                image_preview.visible = True
                image_preview_name.value = name
                image_preview_name.visible = True
                image_preview_holder.visible = True
            else:
                image_preview.src = ""
                image_preview.visible = False
                image_preview_name.value = ""
                image_preview_name.visible = False
                image_preview_holder.visible = False
            image_hint.value = (
                "已选择 1 张图片"
                if selected_images
                else "未选择图片（只能上传 1 张）"
            )
            image_hint.update()
            image_preview.update()
            image_preview_name.update()
            image_preview_holder.update()

        def choose_images(e) -> None:
            self._files_callback = pick_images

        image_button = ft.Button(
            "添加内容图片",
            icon=ft.Icons.ADD_PHOTO_ALTERNATE,
            on_click=choose_images,
            action=ft.PickFiles(
                self.picker,
                allow_multiple=False,
                with_data=True,
                compression_quality=0,
                file_type=ft.FilePickerFileType.IMAGE,
            ),
        )

        def save(e):
            try:
                value = float((points.value or "").strip() or 0)
            except ValueError:
                points.error = "请填写数字"
                points.update()
                return
            if value < 0:
                points.error = "不能小于 0"
                points.update()
                return
            if value > balance:
                points.error = f"不能超过可用积分 {db.num_text(balance)}"
                points.update()
                return
            target_key = (target.value or "").strip()
            if target_key and target_key not in {
                str(option.key) for option in target.options
            }:
                target.error_text = "请从搜索结果中选择一个交易对象"
                target.update()
                return
            try:
                bounty_id = db.create_forum_bounty(
                    self._my_user_id() or 0,
                    title.value or "",
                    content.value or "",
                    value,
                    int(target_key) if target_key else None,
                )
            except ValueError as err:
                self._toast(str(err))
                return
            for source in selected_images:
                data = bytes(source.bytes)
                name = getattr(source, "name", "") or "图片"
                suffix = Path(name).suffix.lower()[:10]
                data, suffix = _shrink_photo(data, suffix)
                stored = _stored_name(name, prefix=f"forum_b{bounty_id}")
                if suffix:
                    stored = f"{Path(stored).stem}{suffix}"
                try:
                    (db.UPLOAD_DIR / stored).write_bytes(data)
                except OSError:
                    continue
                db.add_file(
                    "forum_bounty",
                    bounty_id,
                    "图片",
                    name,
                    stored,
                    len(data),
                )
            self._finish("悬赏已发布，积分已冻结")

        body = self._form_column(
            [
                ft.Text(
                    f"当前可用积分：{db.num_text(balance)}",
                    size=12,
                    color=ft.Colors.GREY_600,
                ),
                title,
                content,
                image_button,
                image_hint,
                image_preview_holder,
                points,
                target,
            ]
        )
        self._show(
            self._dialog(
                "发布悬赏",
                body,
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("发布", on_click=save),
                ],
            )
        )

    def _open_forum_answer_dialog(self, bounty: dict) -> None:
        content = _tf(
            "我的回答 *",
            "",
            width=DIALOG_WIDTH,
            multiline=True,
            min_lines=4,
            max_lines=8,
        )

        def save(e):
            try:
                db.add_forum_answer(
                    bounty["id"],
                    self._my_user_id() or 0,
                    content.value or "",
                )
            except ValueError as err:
                content.error = str(err)
                content.update()
                return
            self._finish("回答已发布")

        self._show(
            self._dialog(
                "回答悬赏",
                self._form_column([content]),
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("发布回答", on_click=save),
                ],
            )
        )

    def _open_forum_penalty_dialog(self, bounty: dict) -> None:
        if not self.is_admin():
            self._toast("只有管理员可以手动扣分")
            return
        author_balance = db.forum_points_balance(bounty["author_user_id"])
        points = _tf(
            "扣除积分 *",
            "",
            width=DIALOG_WIDTH,
            keyboard_type=ft.KeyboardType.NUMBER,
            hint_text=f"最多 {db.num_text(author_balance)}",
        )
        reason = _tf(
            "扣分原因 *",
            "",
            width=DIALOG_WIDTH,
            multiline=True,
            min_lines=3,
            max_lines=6,
        )

        def save(e):
            try:
                db.deduct_forum_bounty_points(
                    bounty["id"],
                    self._my_user_id() or 0,
                    float((points.value or "").strip()),
                    reason.value or "",
                )
            except ValueError as err:
                if "积分" in str(err):
                    points.error = str(err)
                    points.update()
                else:
                    reason.error = str(err)
                    reason.update()
                return
            self._finish("论坛扣分已记录")

        self._show(
            self._dialog(
                "管理员扣分",
                self._form_column(
                    [
                        ft.Text(
                            f"发布者当前可用积分：{db.num_text(author_balance)}",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                        points,
                        reason,
                    ]
                ),
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("确认扣分", on_click=save),
                ],
            )
        )

    def _open_forum_image(self, row: dict) -> None:
        width = min(720, (self.page.width or 900) - 80)
        self._show(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(row["filename"] or "悬赏图片"),
                content=ft.Container(
                    ft.Image(
                        src=db.file_url(row),
                        width=width,
                        fit=ft.BoxFit.CONTAIN,
                    ),
                    width=width,
                ),
                actions=[ft.TextButton("关闭", on_click=self._close)],
            )
        )

    def _open_forum_mute_dialog(self, bounty: dict) -> None:
        if not self.is_admin():
            self._toast("只有管理员可以禁言")
            return
        default_until = (datetime.now() + timedelta(days=1)).strftime(
            "%Y-%m-%d %H:%M"
        )
        until = _tf(
            "禁言至 *",
            default_until,
            width=DIALOG_WIDTH,
            hint_text="2026-10-25 18:30",
        )
        reason = _tf(
            "禁言原因 *",
            "",
            width=DIALOG_WIDTH,
            multiline=True,
            min_lines=3,
            max_lines=6,
        )

        def save(e):
            try:
                db.mute_forum_user(
                    bounty["author_user_id"],
                    self._my_user_id() or 0,
                    until.value or "",
                    reason.value or "",
                )
            except ValueError as err:
                until.error = str(err)
                until.update()
                return
            self._finish("论坛账号已禁言")

        self._show(
            self._dialog(
                "禁言发布者",
                self._form_column(
                    [
                        ft.Text(
                            "禁言期间不能发布悬赏或回答，仍可查看内容。",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                        until,
                        reason,
                    ]
                ),
                [
                    ft.TextButton("取消", on_click=self._close),
                    ft.Button("确认禁言", on_click=save),
                ],
            )
        )

    def _unmute_forum_author(self, bounty: dict) -> None:
        if not self.is_admin():
            self._toast("只有管理员可以解除禁言")
            return
        db.unmute_forum_user(bounty["author_user_id"], self._my_user_id() or 0)
        self.render()
        self._toast("已解除禁言")


__all__ = ["ForumMixin"]
