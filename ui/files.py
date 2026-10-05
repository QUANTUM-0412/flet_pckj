"""上传与打开附件。"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import flet as ft

import db
import keywords
import poster
from .common import _attendance_calc, _date_text, _stored_name

# 课堂照片存下来的样子：长边最多这么多像素、JPEG 质量，压到目标大小以内。
# 手机原图常常 3-5 MB，压完一般 200-400 KB，投影/手机上给家长看够清楚。
PHOTO_MAX_SIDE = 1600
PHOTO_QUALITY = 82
PHOTO_TARGET_BYTES = 800 * 1024
PHOTO_SKIP_BYTES = 350 * 1024  # 本来就小的图不用重新编码


def _encode_jpeg(image, max_side: int, quality: int) -> bytes:
    from PIL import Image

    shrunk = image.copy()
    shrunk.thumbnail((max_side, max_side), Image.LANCZOS)
    out = io.BytesIO()
    shrunk.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()


def _encode_photo(image) -> bytes:
    """按「先清楚、再压小」的顺序挑一组参数，尽量压到目标大小以内。"""
    best = _encode_jpeg(image, PHOTO_MAX_SIDE, PHOTO_QUALITY)
    if len(best) > PHOTO_TARGET_BYTES:
        for max_side, quality in ((1400, 78), (1200, 75)):
            candidate = _encode_jpeg(image, max_side, quality)
            if len(candidate) < len(best):
                best = candidate
            if len(best) <= PHOTO_TARGET_BYTES:
                break
    return best


def _decode_photo(data: bytes):
    """把照片读成一张能重新编码的图；读不了就交给系统工具转一道。"""
    from PIL import Image, ImageOps

    image = Image.open(io.BytesIO(data))
    image.load()
    if getattr(image, "is_animated", False):  # 动图别动
        return None
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", image.size, "white")
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image if image.mode == "RGB" else image.convert("RGB")


def _shrink_photo(data: bytes, suffix: str) -> tuple[bytes, str]:
    """照片压一下再存：长边 1600 像素、JPEG 质量 82，尽量压到 800 KB 以内。

    给家长看的照片，要小也要看得清。压不了（格式不认识、库没装）就原样返回，
    绝不把照片弄丢。
    """
    try:
        image = _decode_photo(data)
    except Exception:
        # HEIC 这类 Pillow 解不开的，交给系统里的转换工具（sips / ImageMagick）
        return _shrink_photo_with_system_tool(data, suffix)
    if image is None:  # 动图
        return data, suffix
    if len(data) <= PHOTO_SKIP_BYTES and max(image.size) <= PHOTO_MAX_SIDE:
        return data, suffix  # 本来就小，不用再编一遍
    try:
        best = _encode_photo(image)
    except Exception:
        return data, suffix
    if len(best) >= len(data) and max(image.size) <= PHOTO_MAX_SIDE:
        return data, suffix
    return best, ".jpg"


def _system_convert_commands(source: Path, target: Path) -> list[list[str]]:
    """本机装了哪个系统工具，就按哪个把照片转成 JPEG。

    Mac 用自带的 sips；Linux/WSL 用 ImageMagick（magick 或老名字 convert），
    只装了 libheif 的话再用 heif-convert。都没装就返回空表，照片原样留着。
    """
    commands: list[list[str]] = []
    sips = shutil.which("sips")
    if sips:
        commands.append(
            [
                sips,
                "-s",
                "format",
                "jpeg",
                "-s",
                "formatOptions",
                str(PHOTO_QUALITY),
                "-Z",
                str(PHOTO_MAX_SIDE),
                str(source),
                "--out",
                str(target),
            ]
        )
    imagemagick = shutil.which("magick") or shutil.which("convert")
    if imagemagick:
        commands.append(
            [
                imagemagick,
                str(source),
                "-resize",
                f"{PHOTO_MAX_SIDE}x{PHOTO_MAX_SIDE}>",
                "-quality",
                str(PHOTO_QUALITY),
                str(target),
            ]
        )
    heif_convert = shutil.which("heif-convert")
    if heif_convert and source.suffix.lower() in (".heic", ".heif"):
        commands.append([heif_convert, str(source), str(target)])
    return commands


def _shrink_photo_with_system_tool(data: bytes, suffix: str) -> tuple[bytes, str]:
    """Pillow 解不开的照片（比如 iPhone 的 HEIC），借系统工具转成 JPEG 再压。"""
    if suffix not in (
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".webp",
        ".heic",
        ".heif",
        ".tif",
        ".tiff",
    ):
        return data, suffix
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / f"in{suffix}"
        source.write_bytes(data)
        target = Path(tmp) / "out.jpg"
        shrunk = b""
        for command in _system_convert_commands(source, target):
            try:
                subprocess.run(command, check=True, capture_output=True, timeout=60)
                shrunk = target.read_bytes()
            except Exception:
                shrunk = b""
                continue  # 这个工具不行，换下一个试试
            if shrunk:
                break
    if not shrunk:
        return data, suffix
    try:  # 转出来的是 JPEG，再按正常参数压一道，别让它比别的照片大一圈
        converted = _decode_photo(shrunk)
        if converted is not None:
            recoded = _encode_photo(converted)
            if len(recoded) < len(shrunk):
                shrunk = recoded
    except Exception:
        pass
    if len(shrunk) >= len(data):
        return data, suffix
    return shrunk, ".jpg"


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
                # 压缩交给后台做（浏览器端压缩在网页里并不生效），这样质量可控
                compression_quality=0,
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
            data = bytes(data)
            suffix = Path(name).suffix.lower()[:10]
            if kind == "照片":
                data, suffix = _shrink_photo(data, suffix)
            stored = _stored_name(name)
            if suffix:
                stored = f"{Path(stored).stem}{suffix}"
            try:
                (db.UPLOAD_DIR / stored).write_bytes(data)
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

    # ------------------------------------------------------------------ 海报

    def _poster_dir(self) -> Path:
        path = db.UPLOAD_DIR / "posters"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _poster_url(self, path: Path) -> str:
        # posters 就放在 assets 目录下面，浏览器直接就能打开
        return f"/{path.parent.name}/{path.name}"

    def _poster_data(self, a: dict, lesson: dict, photos: list[dict]) -> poster.PosterData:
        hours, points = _attendance_calc(a, lesson)
        present = int(a.get("attendance") or 0)
        # 这一行只放「每次会变、家长又关心」的东西：
        # 出勤/纪律/表现/时长基本每节都一样，就不占地方了
        tags: list[str] = []
        if present:
            if float(a.get("bonus") or 0):
                tags.append(f"突出发挥 +{db.num_text(a['bonus'])}")
            if points:
                tags.append(f"本次积分 +{db.num_text(points)}")
        else:
            tags.append("请假")
        month = (lesson.get("lesson_date") or "")[:7]
        present_times, month_times = db.month_attendance_summary(
            int(a.get("student_id") or 0), month, lesson.get("lesson_date") or ""
        )
        if month_times:
            tags.append(f"本月出勤 {present_times}/{month_times} 次")
        upcoming = db.next_lesson_for(
            int(a.get("student_id") or 0),
            lesson.get("lesson_date") or "",
            lesson.get("start_time") or "",
        )
        if upcoming:
            tags.append(
                f"下次课 {_date_text(upcoming['lesson_date'])} {upcoming['start_time']}"
            )

        raw_photos = []
        for row in photos[:4]:
            try:
                raw_photos.append((db.UPLOAD_DIR / row["stored_name"]).read_bytes())
            except OSError:
                continue

        class_bits = [
            db.lesson_class_label(lesson),
            db.lesson_label(lesson),
            f"{db.num_text(lesson.get('minutes') or 0)} 分钟",
        ]
        # 自动生成的班名（2026-2-STEM-Lvl-02-Cls-03）家长看不懂，就不往海报上放了
        if re.search(r"-Cls-\d+$", class_bits[0] or ""):
            class_bits[0] = ""
        date_line = " ".join(
            x for x in [_date_text(lesson["lesson_date"]), lesson.get("start_time") or ""] if x
        )
        return poster.PosterData(
            student_name=a.get("student_name") or "",
            date_line=date_line,
            class_line=" · ".join(x for x in class_bits if x),
            subject=lesson.get("subject") or "",
            brand=db.get_meta("poster_brand"),
            contact=db.get_meta("poster_contact"),
            lesson_comment=lesson.get("comment") or "",
            student_comment=a.get("comment") or "",
            keywords=tuple(
                keywords.extract_keywords(
                    f"{lesson.get('comment') or ''}\n{a.get('comment') or ''}"
                )
            ),
            teacher_name=poster.teacher_label(
                lesson.get("teacher_name") or a.get("owner_teacher_name") or ""
            ),
            tags=tuple(tags),
            photos=tuple(raw_photos),
        )

    def _make_poster(self, a: dict, lesson: dict, photos: list[dict]) -> Path:
        """做一张这个孩子的课堂海报，存到 data/files/posters 下面。"""
        data = self._poster_data(a, lesson, photos)
        blob = poster.build_poster(data)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r"[^\w\u4e00-\u9fff-]+", "", data.student_name) or "课堂"
        path = self._poster_dir() / f"{safe_name}_{lesson['lesson_date']}_{stamp}.jpg"
        path.write_bytes(blob)
        return path

    def _open_poster(self, a: dict, lesson: dict, photos: list[dict]) -> None:
        try:
            path = self._make_poster(a, lesson, photos)
        except poster.PosterError as err:
            self._toast(str(err))
            return
        except OSError:
            self._toast("海报存不下来，检查一下 data 文件夹的权限")
            return
        width = min(560, (self.page.width or 900) - 80)
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"{a.get('student_name') or ''} 的课堂海报"),
            scrollable=True,  # 海报是长图，手机上要能滑着看完
            content=ft.Container(
                ft.Column(
                    [
                        ft.Image(
                            src=self._poster_url(path),
                            width=width,
                            fit=ft.BoxFit.CONTAIN,
                        ),
                        ft.Text(
                            "手机上长按图片就能存进相册、发给家长；电脑上按「存到桌面」再发。",
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
                    "存到桌面",
                    icon=ft.Icons.SAVE_ALT,
                    on_click=lambda e: self._save_poster_to_desktop(path),
                ),
                ft.TextButton(
                    "在新窗口打开",
                    icon=ft.Icons.OPEN_IN_NEW,
                    on_click=lambda e: self.page.run_task(
                        self._open_url, self._poster_url(path)
                    ),
                ),
                ft.TextButton("关闭", on_click=self._close),
            ],
        )
        self._show(dlg)

    def _open_poster_for(self, attendance_id: int, lesson_id: int) -> None:
        """按钮点下去的时候再取一遍数据，保证海报上是改过之后的课评。"""
        a = db.get_attendance(attendance_id)
        lesson = db.get_lesson(lesson_id)
        if a is None or lesson is None:
            self._toast("这条点名记录找不到了")
            return
        photos = db.list_files("attendance", attendance_id, "照片")
        self._open_poster(a, lesson, photos)

    async def _open_url(self, url: str) -> None:
        await self.launcher.launch_url(url, web_only_window_name="_blank")

    def _save_poster_to_desktop(self, path: Path) -> None:
        """把海报复制一份到桌面，方便直接拖进微信。

        Linux / WSL 上一般没有「桌面」这个文件夹（服务器就更没有了），
        就退回 data/files/posters，提示语也跟着说清楚存哪儿了。
        """
        desktop = Path.home() / "Desktop"
        target_dir, where = (
            (desktop, "桌面") if desktop.is_dir() else (db.UPLOAD_DIR / "posters", "海报文件夹")
        )
        target = target_dir / path.name
        try:
            shutil.copyfile(path, target)
        except OSError:
            self._toast(f"复制不过去，海报在这里：{path}")
            return
        self._toast(f"存到{where}了：{target.name}")
