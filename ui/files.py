"""上传与打开附件。"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

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

MARKDOWN_SUFFIXES = (".md", ".markdown")
MARKDOWN_IMAGE_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".heic",
    ".heif",
    ".tif",
    ".tiff",
)
MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
MD_HTML_IMAGE_RE = re.compile(
    r'(<img\b[^>]*\bsrc=["\'])([^"\']+)(["\'])', re.IGNORECASE
)


def _markdown_text(data: bytes) -> str:
    """中文 Markdown 常常是 UTF-8，也有从 Windows 存成 GBK 的。"""
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _markdown_target(raw: str) -> tuple[str, str]:
    """把 ``图片.png "标题"``／``<图片 名字.png>`` 拆成地址和后面的标题。"""
    raw = (raw or "").strip()
    if raw.startswith("<") and ">" in raw:
        end = raw.index(">")
        return raw[1:end].strip(), raw[end + 1 :].strip()
    match = re.match(r"^(\S+)(\s+.+)?$", raw)
    if match:
        return match.group(1), match.group(2) or ""
    return raw, ""


def _local_image_basename(target: str) -> str | None:
    """本地图片取文件名；网络图片、已经上传的 ``/xxx.jpg`` 不动。"""
    target = (target or "").strip()
    if not target or target.startswith("#"):
        return None
    if target.lower().startswith("file://"):
        target = unquote(target[7:])
    elif not re.match(r"^[A-Za-z]:[\\/]", target) and re.match(
        r"^[A-Za-z][A-Za-z0-9+.-]*:", target
    ):
        return None  # http:、https:、data: 这类网络地址
    target = unquote(target).split("?", 1)[0].split("#", 1)[0].replace("\\", "/")
    if target.startswith("/") and target.count("/") == 1:
        return None  # 已经是上传后能直接访问的 /文件名
    name = PurePosixPath(target).name
    return name if "." in name else None


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
        files = list(getattr(e, "files", None) or [])
        if not files:  # 用户点了取消
            self._files_callback = None
            self._upload_target = None
            return
        callback = self._files_callback
        if callback is not None:
            self._files_callback = None
            callback(files)
            return
        target = self._upload_target
        self._upload_target = None
        if not target:
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
            owner_tag = "a" if owner_type == "attendance" else "l"
            prefix = f"{'photo' if kind == '照片' else 'file'}_{owner_tag}{owner_id}"
            stored = _stored_name(name, prefix=prefix)
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

    def _pick_files_action(self) -> ft.PickFiles:
        return ft.PickFiles(
            self.picker,
            allow_multiple=True,
            with_data=True,
            compression_quality=0,
            file_type=ft.FilePickerFileType.ANY,
        )

    def _prepare_markdown_upload(
        self, files: list, prefix: str = "planimg"
    ) -> tuple[str, list[dict], list[str]] | None:
        """读 Markdown，把本地图片换成本系统的地址。

        图片先放在内存里，等课次保存成功再写盘；中途取消不会留下孤儿文件。
        """
        markdown = next(
            (
                f
                for f in files
                if (getattr(f, "name", "") or "").lower().endswith(MARKDOWN_SUFFIXES)
            ),
            None,
        )
        if markdown is None:
            self._toast("请选择 .md 文件（图片可以一起选）")
            return None
        data = getattr(markdown, "bytes", None)
        if not data:
            self._toast("这个 Markdown 文件是空的")
            return None

        images: dict[str, object] = {}
        for f in files:
            name = getattr(f, "name", "") or ""
            payload = getattr(f, "bytes", None)
            if not name.lower().endswith(MARKDOWN_IMAGE_SUFFIXES) or not payload:
                continue
            images[Path(name).name.lower()] = f

        pending: list[dict] = []
        used: dict[str, dict] = {}
        missing: list[str] = []

        def image_url(name: str) -> str | None:
            key = name.lower()
            source = images.get(key)
            if source is None:
                if name not in missing:
                    missing.append(name)
                return None
            entry = used.get(key)
            if entry is None:
                filename = getattr(source, "name", "") or name
                entry = {
                    "stored_name": _stored_name(filename, prefix=prefix),
                    "filename": filename,
                    "data": bytes(source.bytes),
                }
                used[key] = entry
                pending.append(entry)
            return f"/{entry['stored_name']}"

        def replace_md(match) -> str:
            alt, raw = match.group(1), match.group(2)
            target, title = _markdown_target(raw)
            name = _local_image_basename(target)
            if not name:
                return match.group(0)
            url = image_url(name)
            if not url:
                return match.group(0)
            return f"![{alt}]({url}{title})"

        def replace_html(match) -> str:
            prefix, raw, suffix = match.groups()
            name = _local_image_basename(raw)
            if not name:
                return match.group(0)
            url = image_url(name)
            if not url:
                return match.group(0)
            return f"{prefix}{url}{suffix}"

        text = MD_IMAGE_RE.sub(replace_md, _markdown_text(bytes(data)))
        text = MD_HTML_IMAGE_RE.sub(replace_html, text)
        return text, pending, missing

    def _save_plan_uploads(self, lesson_id: int, pending: list[dict]) -> int:
        saved = 0
        for item in pending:
            path = db.UPLOAD_DIR / item["stored_name"]
            try:
                path.write_bytes(item["data"])
            except OSError:
                continue
            db.add_file(
                "lesson",
                lesson_id,
                "教案图片",
                item["filename"],
                item["stored_name"],
                len(item["data"]),
            )
            saved += 1
        return saved

    def _plan_upload_button(self, lesson_id: int) -> ft.Button:
        """课次详情里的「上传 Markdown」：连同本地图片一起导入。"""

        def picked(files: list) -> None:
            result = self._prepare_markdown_upload(
                files, prefix=f"planimg_l{lesson_id}"
            )
            if result is None:
                return
            text, pending, missing = result
            saved = self._save_plan_uploads(lesson_id, pending)
            db.set_lesson_plan(lesson_id, text)
            db.cleanup_plan_images(lesson_id, text)
            self.render()
            if missing:
                self._toast(
                    f"教案已导入；还缺 {len(missing)} 张图片："
                    + "、".join(missing[:4])
                    + ("…" if len(missing) > 4 else "")
                )
            else:
                self._toast(
                    f"教案已导入，上传了 {saved} 张图片" if saved else "教案已导入"
                )

        def open_picker(e) -> None:
            self._files_callback = picked

        return ft.Button(
            "上传 Markdown",
            icon=ft.Icons.UPLOAD_FILE,
            tooltip=".md 里引用的本地图片可以一起选中，会自动上传并改好链接",
            action=self._pick_files_action(),
            on_click=open_picker,
        )

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

    def _photo_strip(
        self,
        owner_id: int,
        photos: list[dict],
        owner_type: str = "attendance",
        add_label: str = "加照片",
        action=None,
    ) -> ft.Row:
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
                add_label,
                owner_type,
                owner_id,
                "照片",
                images_only=True,
                icon=ft.Icons.ADD_A_PHOTO,
            )
        )
        if action is not None:
            thumbs.append(action)
        return ft.Row(thumbs, spacing=8, wrap=True, run_spacing=8)

    # ------------------------------------------------------------------ 海报

    def _poster_dir(self) -> Path:
        path = db.UPLOAD_DIR / "posters"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _poster_url(self, path: Path) -> str:
        # posters 就放在 assets 目录下面，浏览器直接就能打开
        return f"/{path.parent.name}/{path.name}"

    def _poster_qr_bytes(self) -> bytes:
        stored = (db.get_meta("poster_qr") or "").strip()
        if not stored:
            return b""
        try:
            return (db.UPLOAD_DIR / Path(stored).name).read_bytes()
        except OSError:
            return b""

    def _poster_logo_bytes(self) -> bytes:
        stored = (db.get_meta("poster_logo") or "").strip()
        if not stored:
            return b""
        try:
            return (db.UPLOAD_DIR / Path(stored).name).read_bytes()
        except OSError:
            return b""

    def _poster_photo_parts(
        self,
        photos: list[dict],
        main_photo_id: int | None = None,
    ) -> tuple[bytes, tuple[bytes, ...]]:
        """按老师选的主照片拆成「主图」和叠在左下角的作品照片。"""
        selected = photos[:4]
        loaded: list[tuple[dict, bytes]] = []
        for row in selected:
            try:
                loaded.append((row, (db.UPLOAD_DIR / row["stored_name"]).read_bytes()))
            except OSError:
                continue
        if not loaded:
            return b"", ()
        main_row = next(
            (
                row
                for row, _raw in loaded
                if main_photo_id is not None
                and int(row.get("id") or 0) == int(main_photo_id)
            ),
            None,
        )
        if main_row is None:
            main_row = next(
                (
                    row
                    for row, _raw in loaded
                    if row.get("owner_type") == "attendance"
                ),
                loaded[0][0],
            )
        main = next(raw for row, raw in loaded if row is main_row)
        works = tuple(raw for row, raw in loaded if row is not main_row)
        return main, works

    def _poster_data(
        self,
        a: dict,
        lesson: dict,
        photos: list[dict],
        main_photo_id: int | None = None,
    ) -> poster.PosterData:
        hours, points = _attendance_calc(a, lesson)
        present = int(a.get("attendance") or 0)
        # 这一行只放「每次会变、家长又关心」的东西：
        # 出勤/纪律/学习/时长基本每节都一样，就不占地方了
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

        portrait_photo, work_photos = self._poster_photo_parts(
            photos, main_photo_id
        )

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
        # 同一节课多次做海报结果要一样，不同课次要不一样：拿课次＋孩子当种子
        seed = "|".join(
            x
            for x in (
                lesson.get("lesson_date") or "",
                lesson.get("start_time") or "",
                str(a.get("student_id") or ""),
            )
            if x
        )
        return poster.PosterData(
            # 海报画面不出现孩子名字；课评和标签已经够家长看了。
            student_name="",
            date_line=date_line,
            class_line=" · ".join(x for x in class_bits if x),
            subject=lesson.get("subject") or "",
            brand=db.get_meta("poster_brand"),
            logo=self._poster_logo_bytes(),
            contact=db.get_meta("poster_contact"),
            qr_code=self._poster_qr_bytes(),
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
            portrait_photo=portrait_photo,
            work_photos=tuple(work_photos),
            points_text=next(
                (tag for tag in tags if tag.startswith("本次积分")),
                "",
            ),
            point_marks=(
                poster.PointMark("出勤", bool(present), 10 if present else 0),
                poster.PointMark(
                    "纪律",
                    bool(present),
                    db.discipline_points(a) if present else 0,
                ),
                poster.PointMark(
                    "学习",
                    bool(present),
                    db.learning_points(a) if present else 0,
                ),
                poster.PointMark(
                    "突出",
                    float(a.get("bonus") or 0) > 0,
                    float(a.get("bonus") or 0),
                ),
            ),
            seed=seed,
        )

    def _make_poster(
        self,
        a: dict,
        lesson: dict,
        photos: list[dict],
        main_photo_id: int | None = None,
    ) -> Path:
        """做一张这个孩子的课堂海报，存到 data/files/posters 下面。"""
        data = self._poster_data(a, lesson, photos, main_photo_id)
        blob = poster.build_poster(data)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = (
            self._poster_dir()
            / f"poster_s{int(a.get('student_id') or 0)}_l{int(lesson.get('id') or 0)}"
            f"_{lesson['lesson_date']}_{stamp}.jpg"
        )
        path.write_bytes(blob)
        return path

    def _open_poster(
        self,
        a: dict,
        lesson: dict,
        photos: list[dict],
        main_photo_id: int | None = None,
    ) -> None:
        try:
            path = self._make_poster(a, lesson, photos, main_photo_id)
        except poster.PosterError as err:
            self._toast(str(err))
            return
        except OSError:
            self._toast("海报存不下来，检查一下 data 文件夹的权限")
            return
        self._show_poster_dialog(path, "课堂海报")

    def _show_poster_dialog(self, path: Path, title: str) -> None:
        width = min(560, (self.page.width or 900) - 80)
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
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
                            "手机上可长按图片保存；电脑上可用「在新窗口打开」后保存。",
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
        # 孩子自己的照片放前面，全班合影补在后面。一张全班照传一次，
        # 每个孩子的海报都能用上，不用挨个重复上传。
        photos = db.list_files("attendance", attendance_id, "照片")
        photos += db.list_files("lesson", lesson_id, "照片")
        if len(photos) > 1:
            self._choose_poster_photos(
                photos,
                lambda chosen, main_id: self._open_poster(
                    a, lesson, chosen, main_id
                ),
            )
            return
        self._open_poster(
            a, lesson, photos, int(photos[0]["id"]) if photos else None
        )

    def _class_poster_data(
        self,
        template: dict,
        lesson: dict,
        photos: list[dict],
        main_photo_id: int | None = None,
    ) -> poster.PosterData:
        """班级海报：整班共用课评和课堂照片，不带某个孩子的点评."""
        portrait_photo, work_photos = self._poster_photo_parts(
            photos, main_photo_id
        )

        class_name = db.class_label(template)
        if re.search(r"-Cls-\d+$", class_name or ""):
            class_name = ""
        class_bits = [
            class_name,
            db.lesson_label(lesson),
            f"{db.num_text(lesson.get('minutes') or 0)} 分钟",
        ]
        date_line = " ".join(
            x
            for x in [_date_text(lesson["lesson_date"]), lesson.get("start_time") or ""]
            if x
        )
        seed = "|".join(
            x
            for x in (
                "class",
                str(template.get("id") or ""),
                lesson.get("lesson_date") or "",
                lesson.get("start_time") or "",
            )
            if x
        )
        return poster.PosterData(
            student_name="班级课堂分享",
            date_line=date_line,
            class_line=" · ".join(x for x in class_bits if x),
            subject=lesson.get("subject") or template.get("subject") or "",
            brand=db.get_meta("poster_brand"),
            logo=self._poster_logo_bytes(),
            contact=db.get_meta("poster_contact"),
            qr_code=self._poster_qr_bytes(),
            lesson_comment=lesson.get("comment") or "",
            student_comment="",
            teacher_name=poster.teacher_label(
                lesson.get("teacher_name") or template.get("teacher_name") or ""
            ),
            keywords=tuple(keywords.extract_keywords(lesson.get("comment") or "")),
            portrait_photo=portrait_photo,
            work_photos=work_photos,
            seed=seed,
        )

    def _make_class_poster(
        self,
        template: dict,
        lesson: dict,
        photos: list[dict],
        main_photo_id: int | None = None,
    ) -> Path:
        data = self._class_poster_data(
            template, lesson, photos, main_photo_id
        )
        blob = poster.build_poster(data)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = (
            self._poster_dir()
            / f"poster_c{int(template['id'])}_{lesson['lesson_date']}_{stamp}.jpg"
        )
        path.write_bytes(blob)
        return path

    def _open_class_poster(
        self,
        template: dict,
        lesson: dict,
        photos: list[dict],
        main_photo_id: int | None = None,
    ) -> None:
        try:
            path = self._make_class_poster(
                template, lesson, photos, main_photo_id
            )
        except poster.PosterError as err:
            self._toast(str(err))
            return
        except OSError:
            self._toast("海报存不下来，检查一下 data 文件夹的权限")
            return
        self._show_poster_dialog(path, "班级课堂海报")

    def _class_poster_button(self, lesson: dict) -> ft.Button:
        """课堂内容里的班级海报按钮：照片旁边就能点。"""
        return ft.Button(
            "做海报",
            icon=ft.Icons.AUTO_AWESOME,
            tooltip="用这节课的课评和课堂照片做一张班级海报",
            on_click=lambda e: self._make_class_poster_for_lesson(lesson),
        )

    def _make_class_poster_for_lesson(
        self, lesson: dict, template: dict | None = None
    ) -> None:
        fresh = db.get_lesson(int(lesson["id"]))
        if fresh is not None:
            lesson = fresh
        photos = db.list_files("lesson", int(lesson["id"]), "照片")
        if not (lesson.get("comment") or "").strip() and not photos:
            self._toast("这节课还没有课评和课堂照片，先写一点再做海报")
            return
        if template is None:
            template = (
                db.get_template(int(lesson["template_id"]))
                if lesson.get("template_id")
                else None
            )
        if template is None:
            template = {
                "id": 0,
                "name": "",
                "subject": lesson.get("subject") or "",
                "teacher_name": lesson.get("teacher_name") or "",
            }
        if len(photos) > 1:
            self._choose_poster_photos(
                photos,
                lambda chosen, main_id: self._open_class_poster(
                    template, lesson, chosen, main_id
                ),
            )
            return
        self._open_class_poster(
            template, lesson, photos, int(photos[0]["id"]) if photos else None
        )

    def _choose_poster_photos(self, photos: list[dict], on_confirm) -> None:
        """照片不止一张时，先让老师挑这次海报用哪几张。"""
        picked: list[tuple[ft.Checkbox, dict]] = []
        photo_options: list[ft.DropdownOption] = []
        cards = []
        for index, row in enumerate(photos):
            tag = "作品／课堂" if row.get("owner_type") == "lesson" else "孩子人像"
            box = ft.Checkbox(label=tag, value=index < 4)
            picked.append((box, row))
            photo_options.append(
                ft.DropdownOption(
                    key=str(row["id"]),
                    text=f"{index + 1}. {row['filename'] or '照片'}",
                )
            )
            cards.append(
                ft.Column(
                    [
                        ft.Image(
                            src=db.file_url(row),
                            width=128,
                            height=128,
                            fit=ft.BoxFit.COVER,
                            border_radius=8,
                            tooltip=row["filename"],
                        ),
                        ft.Text(
                            row["filename"] or "照片",
                            size=10,
                            color=ft.Colors.GREY_600,
                            width=128,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        box,
                    ],
                    spacing=3,
                    width=140,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        main_dd = ft.Dropdown(
            label="主照片（铺满大图）",
            options=photo_options[:4],
            value=str(photos[0]["id"]) if photos else None,
            width=420,
            dense=True,
        )

        def selected_rows() -> list[dict]:
            return [row for box, row in picked if box.value]

        def refresh_main_options(e=None) -> None:
            rows = selected_rows()
            main_dd.options = [
                ft.DropdownOption(
                    key=str(row["id"]),
                    text=f"{next(i + 1 for i, r in enumerate(photos) if r is row)}. "
                    f"{row['filename'] or '照片'}",
                )
                for row in rows
            ]
            ids = {str(row["id"]) for row in rows}
            if main_dd.value not in ids:
                main_dd.value = str(rows[0]["id"]) if rows else None
            if e is not None:
                main_dd.update()

        for box, _row in picked:
            box.on_change = refresh_main_options

        def make_poster(e) -> None:
            selected = selected_rows()
            if len(selected) > 4:
                self._toast("海报最多放 4 张照片，取消勾选几张再试")
                return
            selected_ids = {str(row["id"]) for row in selected}
            main_id = (
                int(main_dd.value)
                if (main_dd.value or "") in selected_ids
                else (int(selected[0]["id"]) if selected else None)
            )
            self.page.pop_dialog()
            on_confirm(selected, main_id)

        width = min(720, (self.page.width or 900) - 80)
        rows = max(1, (len(cards) + 3) // 4)
        height = min(560, (self.page.height or 800) - 220, 130 + rows * 190)
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("选照片做海报"),
            content=ft.Container(
                ft.Column(
                    [
                        ft.Text(
                            "最多选 4 张；一张都不选也可以，海报会只用课评。"
                            "主照片会铺满大图，其他照片作为作品叠在左下角。",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                        main_dd,
                        ft.Row(
                            cards,
                            spacing=12,
                            run_spacing=12,
                            wrap=True,
                            alignment=ft.MainAxisAlignment.START,
                        ),
                    ],
                    spacing=10,
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=width,
                height=height,
            ),
            actions=[
                ft.TextButton("取消", on_click=self._close),
                ft.Button("做海报", icon=ft.Icons.AUTO_AWESOME, on_click=make_poster),
            ],
        )
        self._show(dlg)

    async def _open_url(self, url: str) -> None:
        await self.launcher.launch_url(url, web_only_window_name="_blank")
