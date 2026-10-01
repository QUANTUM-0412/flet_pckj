"""上传与打开附件。"""

from __future__ import annotations

import flet as ft

import db
from .common import _stored_name


class FilesMixin:
    """上传与打开附件（ClassHoursApp 的一部分）。"""

    def _set_upload_target(self, owner_type: str, owner_id: int, kind: str) -> None:
        self._upload_target = (owner_type, owner_id, kind)

    def _upload_button(
        self,
        label: str,
        owner_type: str,
        owner_id: int,
        kind: str,
        images_only: bool = False,
        icon=ft.Icons.UPLOAD,
    ) -> ft.Button:
        return ft.Button(
            label,
            icon=icon,
            on_click=lambda e: self._set_upload_target(owner_type, owner_id, kind),
            action=ft.PickFiles(
                self.picker,
                allow_multiple=True,
                with_data=True,
                compression_quality=70 if images_only else 0,
                file_type=ft.FilePickerFileType.IMAGE
                if images_only
                else ft.FilePickerFileType.ANY,
            ),
        )

    def _on_files_picked(self, e) -> None:
        target = self._upload_target
        self._upload_target = None
        files = list(getattr(e, "files", None) or [])
        if not target or not files:
            return
        owner_type, owner_id, kind = target
        saved = 0
        for f in files:
            data = getattr(f, "bytes", None)
            name = getattr(f, "name", "") or "文件"
            if not data:
                continue
            stored = _stored_name(name)
            try:
                (db.UPLOAD_DIR / stored).write_bytes(bytes(data))
            except OSError:
                continue
            db.add_file(owner_type, owner_id, kind, name, stored, len(data))
            saved += 1
        self.render()
        self._toast(f"传好了 {saved} 个文件" if saved else "没有收到文件")

    def _open_photo(self, file_row: dict) -> None:
        width = min(520, (self.page.width or 900) - 100)
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(file_row["filename"] or "照片"),
            content=ft.Container(
                ft.Image(src=db.file_url(file_row), width=width, fit=ft.BoxFit.CONTAIN),
                width=width,
            ),
            actions=[
                ft.TextButton(
                    "删除",
                    icon=ft.Icons.DELETE_OUTLINE,
                    on_click=lambda e: self._delete_file_and_close(file_row),
                ),
                ft.TextButton("关闭", on_click=self._close),
            ],
        )
        self._show(dlg)

    async def _open_attachment(self, file_row: dict) -> None:
        await self.launcher.launch_url(
            db.file_url(file_row), web_only_window_name="_blank"
        )

    def _delete_file_and_close(self, file_row: dict) -> None:
        db.delete_file(file_row["id"])
        self.page.pop_dialog()
        self.render()
        self._toast("已删除")

    def _photo_strip(self, owner_id: int, photos: list[dict]) -> ft.Row:
        thumbs = []
        for photo in photos:
            thumbs.append(
                ft.Container(
                    content=ft.Image(
                        src=db.file_url(photo),
                        width=84,
                        height=84,
                        fit=ft.BoxFit.COVER,
                        border_radius=8,
                    ),
                    on_click=lambda e, row=photo: self._open_photo(row),
                    ink=True,
                    border_radius=8,
                    tooltip=photo["filename"],
                )
            )
        thumbs.append(
            self._upload_button(
                "加照片",
                "attendance",
                owner_id,
                "照片",
                images_only=True,
                icon=ft.Icons.ADD_A_PHOTO,
            )
        )
        return ft.Row(thumbs, spacing=8, wrap=True, run_spacing=8)
