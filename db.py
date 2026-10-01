"""课时记录平台 —— 数据层。

所有数据存在 data/app.db 这一个文件里，备份的时候直接拷这个文件就行。
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CLASS_HOURS_DB") or (APP_DIR / "data" / "app.db"))
# 上传的照片和附件都放在数据库旁边，备份时拷 data 这一个文件夹就够了
UPLOAD_DIR = Path(os.environ.get("CLASS_HOURS_FILES") or (DB_PATH.parent / "files"))
EXPORT_DIR = UPLOAD_DIR / "exports"
WARN_BALANCE = 3  # 剩余课时少于这个数就提醒

# --------------------------------------------------------------- 初始化的字典

# 课时账户种类：孩子报的每一种课，都有自己的课时本子
HOUR_TYPES = ["正课", "考级", "竞赛", "托管", "社团"]

# 课型：(名称, 是否扣课时, 主扣账户, 主扣不够时补扣的账户)
DEFAULT_CLASS_TYPES: list[tuple[str, int, str | None, str | None]] = [
    ("正课", 1, "正课", None),
    ("考级", 1, "考级", "正课"),
    ("竞赛", 1, "竞赛", "正课"),
    ("托管", 1, "托管", None),
    ("校内社团", 1, "社团", None),
    ("试听", 0, None, None),
    ("替课", 1, "正课", None),  # 老师替课，课照上，课时照扣
]

# (科目, 等级, 默认时长／分钟) —— 照抄现在 Excel 里的等级
DEFAULT_LEVELS: list[tuple[str, str, int]] = [
    ("GPL", "Lvl-01", 90),
    ("GPL", "Lvl-03", 90),
    ("PY", "Lvl-01", 60),
    ("STEM", "Lvl-02", 120),
    ("GPL-竞赛", "小低组", 120),
    ("UAV-社团", "Lvl-01", 60),
    ("MCU", "Lvl-02", 120),
]

STUDENT_STATUS = ["在读", "停课", "结课"]
GENDER_OPTIONS = ["男", "女"]
TRIAL_STATUS = ["待试听", "已试听", "已报名", "没意向"]
ROLE_ROOT = "root"
ROLE_TEACHER = "teacher"
ROLE_NAMES = {ROLE_ROOT: "管理员", ROLE_TEACHER: "老师"}
DEFAULT_ADMIN_USER = "root"
DEFAULT_ADMIN_PASSWORD = "1234"

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    gender      TEXT    NOT NULL DEFAULT '',
    grade       TEXT    NOT NULL DEFAULT '',
    phone       TEXT    NOT NULL DEFAULT '',
    note        TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT '在读',
    created_at  TEXT    NOT NULL DEFAULT ''
);

-- 课时账户种类（正课／考级／竞赛／托管／社团）
CREATE TABLE IF NOT EXISTS hour_types (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT    NOT NULL UNIQUE,
    sort    INTEGER NOT NULL DEFAULT 0,
    warn    INTEGER NOT NULL DEFAULT 0
);

-- 课型：一节课属于哪一类，以及这节课扣哪个课时账户
CREATE TABLE IF NOT EXISTS class_types (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    name                    TEXT    NOT NULL UNIQUE,
    deduct                  INTEGER NOT NULL DEFAULT 1,
    primary_hour_type_id    INTEGER REFERENCES hour_types(id),
    fallback_hour_type_id   INTEGER REFERENCES hour_types(id),
    sort                    INTEGER NOT NULL DEFAULT 0
);

-- 等级：科目 + 阶段，带默认时长
CREATE TABLE IF NOT EXISTS levels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subject         TEXT    NOT NULL DEFAULT '',
    name            TEXT    NOT NULL,
    default_minutes INTEGER NOT NULL DEFAULT 90,
    sort            INTEGER NOT NULL DEFAULT 0,
    UNIQUE(subject, name)
);

-- 报名：一个孩子报的一门课
CREATE TABLE IF NOT EXISTS enrollments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    level_id      INTEGER REFERENCES levels(id),
    class_type_id INTEGER NOT NULL REFERENCES class_types(id),
    minutes       INTEGER NOT NULL DEFAULT 90,
    status        TEXT    NOT NULL DEFAULT '在读',
    note          TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL DEFAULT ''
);

-- 课时账户的开关（目前只有"不限课时"）
CREATE TABLE IF NOT EXISTS hour_accounts (
    student_id   INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    hour_type_id INTEGER NOT NULL REFERENCES hour_types(id),
    unlimited    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (student_id, hour_type_id)
);

-- 课时流水：正数是充值／增加，负数是扣除
CREATE TABLE IF NOT EXISTS hour_transactions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id   INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    hour_type_id INTEGER NOT NULL REFERENCES hour_types(id),
    change       REAL    NOT NULL,
    kind         TEXT    NOT NULL DEFAULT '充值',
    happened_on  TEXT    NOT NULL DEFAULT '',
    note         TEXT    NOT NULL DEFAULT '',
    source_type  TEXT    NOT NULL DEFAULT '',
    source_id    INTEGER,
    created_at   TEXT    NOT NULL DEFAULT ''
);

-- 积分流水：正数是赚的，负数是兑换掉的
CREATE TABLE IF NOT EXISTS point_transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    change      REAL    NOT NULL,
    kind        TEXT    NOT NULL DEFAULT '上课',
    happened_on TEXT    NOT NULL DEFAULT '',
    note        TEXT    NOT NULL DEFAULT '',
    source_type TEXT    NOT NULL DEFAULT '',
    source_id   INTEGER,
    created_at  TEXT    NOT NULL DEFAULT ''
);

-- 一节课
CREATE TABLE IF NOT EXISTS lessons (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_date   TEXT    NOT NULL,
    start_time    TEXT    NOT NULL DEFAULT '',
    minutes       INTEGER NOT NULL DEFAULT 90,
    class_type_id INTEGER NOT NULL REFERENCES class_types(id),
    level_id      INTEGER REFERENCES levels(id),
    comment       TEXT    NOT NULL DEFAULT '',
    plan          TEXT    NOT NULL DEFAULT '',
    note          TEXT    NOT NULL DEFAULT '',
    kind          TEXT    NOT NULL DEFAULT '正常',
    created_at    TEXT    NOT NULL DEFAULT ''
);

-- 点名：每个孩子一条
CREATE TABLE IF NOT EXISTS attendance (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id     INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    student_id    INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    enrollment_id INTEGER REFERENCES enrollments(id) ON DELETE SET NULL,
    attendance    INTEGER NOT NULL DEFAULT 1,
    discipline    INTEGER NOT NULL DEFAULT 1,
    performance   INTEGER NOT NULL DEFAULT 1,
    bonus         REAL    NOT NULL DEFAULT 0,
    minutes       REAL    NOT NULL DEFAULT 90,
    comment       TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL DEFAULT ''
);

-- 缴费：一笔钱买了哪种课时
CREATE TABLE IF NOT EXISTS payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id   INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    paid_on      TEXT    NOT NULL,
    amount       REAL    NOT NULL DEFAULT 0,
    hour_type_id INTEGER REFERENCES hour_types(id),
    hours        REAL    NOT NULL DEFAULT 0,
    note         TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL DEFAULT ''
);

-- 缴费里的每一行课时（正课 24 ＋ 赠送考级 1 ＋ 赠送竞赛 1 这种）
CREATE TABLE IF NOT EXISTS payment_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id   INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
    hour_type_id INTEGER REFERENCES hour_types(id),
    level_id     INTEGER REFERENCES levels(id),
    hours        REAL    NOT NULL DEFAULT 0,
    amount       REAL    NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL DEFAULT ''
);

-- 待补课：孩子请假以后自动生成一条
CREATE TABLE IF NOT EXISTS makeups (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id           INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    lesson_id            INTEGER REFERENCES lessons(id) ON DELETE SET NULL,
    attendance_id        INTEGER REFERENCES attendance(id) ON DELETE CASCADE,
    makeup_lesson_id     INTEGER REFERENCES lessons(id) ON DELETE SET NULL,
    makeup_attendance_id INTEGER REFERENCES attendance(id) ON DELETE SET NULL,
    status               TEXT    NOT NULL DEFAULT '待补',
    note                 TEXT    NOT NULL DEFAULT '',
    created_at           TEXT    NOT NULL DEFAULT ''
);

-- 试听／客户跟进：还不是正式学员
CREATE TABLE IF NOT EXISTS trials (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    gender      TEXT    NOT NULL DEFAULT '',
    grade       TEXT    NOT NULL DEFAULT '',
    parent_name TEXT    NOT NULL DEFAULT '',
    phone       TEXT    NOT NULL DEFAULT '',
    source      TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT '待试听',
    trial_on    TEXT    NOT NULL DEFAULT '',
    note        TEXT    NOT NULL DEFAULT '',
    student_id  INTEGER REFERENCES students(id) ON DELETE SET NULL,
    created_at  TEXT    NOT NULL DEFAULT ''
);

-- 照片和附件
CREATE TABLE IF NOT EXISTS files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_type  TEXT    NOT NULL,
    owner_id    INTEGER NOT NULL,
    kind        TEXT    NOT NULL DEFAULT '附件',
    filename    TEXT    NOT NULL DEFAULT '',
    stored_name TEXT    NOT NULL DEFAULT '',
    size        INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT    NOT NULL DEFAULT ''
);

-- 固定课表：每周几、几点、哪个等级，哪些孩子
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    salt          TEXT    NOT NULL,
    display_name  TEXT    NOT NULL DEFAULT '',
    role          TEXT    NOT NULL DEFAULT 'teacher',
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS schedule_templates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    weekday       INTEGER NOT NULL DEFAULT 0,
    start_time    TEXT    NOT NULL DEFAULT '',
    minutes       INTEGER NOT NULL DEFAULT 90,
    class_type_id INTEGER NOT NULL REFERENCES class_types(id),
    level_id      INTEGER REFERENCES levels(id),
    note          TEXT    NOT NULL DEFAULT '',
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS schedule_students (
    template_id INTEGER NOT NULL REFERENCES schedule_templates(id) ON DELETE CASCADE,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    PRIMARY KEY (template_id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_enroll_student ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_hour_tx_student ON hour_transactions(student_id);
CREATE INDEX IF NOT EXISTS idx_point_tx_student ON point_transactions(student_id);
CREATE INDEX IF NOT EXISTS idx_lesson_date ON lessons(lesson_date);
CREATE INDEX IF NOT EXISTS idx_attendance_lesson ON attendance(lesson_id);
CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id);
CREATE INDEX IF NOT EXISTS idx_payments_student ON payments(student_id);
CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(paid_on);
CREATE INDEX IF NOT EXISTS idx_makeups_status ON makeups(status);
CREATE INDEX IF NOT EXISTS idx_makeups_student ON makeups(student_id);
CREATE INDEX IF NOT EXISTS idx_trials_status ON trials(status);
CREATE INDEX IF NOT EXISTS idx_files_owner ON files(owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_schedule_weekday ON schedule_templates(weekday);
CREATE INDEX IF NOT EXISTS idx_payment_items ON payment_items(payment_id);
"""


# ------------------------------------------------------------------ 连接管理


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    """建表并写入初始的等级／课型（只在第一次运行时写）。"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as con:
        con.executescript(SCHEMA)
        _migrate(con)
        _seed(con)
    ensure_default_admin()


def _migrate(con: sqlite3.Connection) -> None:
    """老数据库补新字段。"""
    columns = {r["name"] for r in con.execute("PRAGMA table_info(hour_transactions)")}
    if "source_type" not in columns:
        con.execute(
            "ALTER TABLE hour_transactions ADD COLUMN source_type TEXT NOT NULL DEFAULT ''"
        )
    if "source_id" not in columns:
        con.execute("ALTER TABLE hour_transactions ADD COLUMN source_id INTEGER")
    lesson_columns = {r["name"] for r in con.execute("PRAGMA table_info(lessons)")}
    if "kind" not in lesson_columns:
        con.execute("ALTER TABLE lessons ADD COLUMN kind TEXT NOT NULL DEFAULT '正常'")
    if "plan" not in lesson_columns:
        con.execute("ALTER TABLE lessons ADD COLUMN plan TEXT NOT NULL DEFAULT ''")
    hour_columns = {r["name"] for r in con.execute("PRAGMA table_info(hour_types)")}
    if "warn" not in hour_columns:
        con.execute("ALTER TABLE hour_types ADD COLUMN warn INTEGER NOT NULL DEFAULT 0")
        # 默认只有正课提醒
        con.execute("UPDATE hour_types SET warn = 1 WHERE name = '正课'")
    # 老的"一笔缴费一种课时"拆成明细行
    item_columns = {r["name"] for r in con.execute("PRAGMA table_info(payment_items)")}
    if "level_id" not in item_columns:
        con.execute("ALTER TABLE payment_items ADD COLUMN level_id INTEGER REFERENCES levels(id)")
    empty = con.execute("SELECT COUNT(*) AS c FROM payment_items").fetchone()
    if int(empty["c"] or 0) == 0:
        for p in con.execute("SELECT * FROM payments").fetchall():
            if p["hour_type_id"]:
                con.execute(
                    """INSERT INTO payment_items(payment_id, hour_type_id, hours, amount, created_at)
                       VALUES(?, ?, ?, ?, ?)""",
                    (p["id"], p["hour_type_id"], p["hours"], p["amount"], _today()),
                )


def _seed(con: sqlite3.Connection) -> None:
    for i, name in enumerate(HOUR_TYPES):
        con.execute(
            "INSERT OR IGNORE INTO hour_types(name, sort, warn) VALUES(?, ?, ?)",
            (name, i, 1 if name == "正课" else 0),
        )
    hours = {r["name"]: r["id"] for r in con.execute("SELECT id, name FROM hour_types")}
    for i, (name, deduct, primary, fallback) in enumerate(DEFAULT_CLASS_TYPES):
        con.execute(
            """INSERT OR IGNORE INTO class_types
                   (name, deduct, primary_hour_type_id, fallback_hour_type_id, sort)
               VALUES(?, ?, ?, ?, ?)""",
            (
                name,
                deduct,
                hours.get(primary) if primary else None,
                hours.get(fallback) if fallback else None,
                i,
            ),
        )
    for i, (subject, name, minutes) in enumerate(DEFAULT_LEVELS):
        con.execute(
            """INSERT OR IGNORE INTO levels(subject, name, default_minutes, sort)
               VALUES(?, ?, ?, ?)""",
            (subject, name, minutes, i),
        )


def _today() -> str:
    return date.today().isoformat()


# -------------------------------------------------------------------- 学员档案

def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    ).hex()


def ensure_default_admin() -> None:
    """第一次运行时建一个管理员账号。"""
    with _connect() as con:
        row = con.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        if int(row["c"] or 0) > 0:
            return
        salt = secrets.token_hex(8)
        con.execute(
            """INSERT INTO users
                   (username, password_hash, salt, display_name, role, created_at)
               VALUES(?, ?, ?, ?, 'root', ?)""",
            (
                DEFAULT_ADMIN_USER,
                _hash_password(DEFAULT_ADMIN_PASSWORD, salt),
                salt,
                "管理员",
                _today(),
            ),
        )


def verify_user(username: str, password: str) -> dict | None:
    with _connect() as con:
        row = con.execute(
            "SELECT * FROM users WHERE username = ? AND active = 1",
            ((username or "").strip(),),
        ).fetchone()
    if row is None:
        return None
    if _hash_password(password or "", row["salt"]) != row["password_hash"]:
        return None
    return dict(row)


def get_user(user_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            "SELECT * FROM users ORDER BY CASE role WHEN 'root' THEN 0 ELSE 1 END, username"
        ).fetchall()
    return [dict(r) for r in rows]


def create_user(
    username: str, password: str, display_name: str = "", role: str = ROLE_TEACHER
) -> int:
    username = (username or "").strip()
    if not username:
        raise ValueError("用户名不能为空")
    if not password:
        raise ValueError("密码不能为空")
    salt = secrets.token_hex(8)
    with _connect() as con:
        exists = con.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if exists:
            raise ValueError("这个用户名已经有了")
        cur = con.execute(
            """INSERT INTO users
                   (username, password_hash, salt, display_name, role, created_at)
               VALUES(?, ?, ?, ?, ?, ?)""",
            (
                username,
                _hash_password(password, salt),
                salt,
                display_name or username,
                role if role in ROLE_NAMES else ROLE_TEACHER,
                _today(),
            ),
        )
        return int(cur.lastrowid)


def set_user_password(user_id: int, password: str) -> None:
    if not password:
        raise ValueError("密码不能为空")
    salt = secrets.token_hex(8)
    with _connect() as con:
        con.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
            (_hash_password(password, salt), salt, user_id),
        )


def update_user(user_id: int, display_name: str, role: str, active: bool) -> None:
    role = role if role in ROLE_NAMES else ROLE_TEACHER
    with _connect() as con:
        if role != ROLE_ROOT or not active:
            roots = con.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = 'root' AND active = 1 AND id != ?",
                (user_id,),
            ).fetchone()
            if int(roots["c"] or 0) == 0:
                raise ValueError("至少要留一个能用的管理员")
        con.execute(
            "UPDATE users SET display_name = ?, role = ?, active = ? WHERE id = ?",
            (display_name, role, 1 if active else 0, user_id),
        )


def delete_user(user_id: int) -> None:
    with _connect() as con:
        row = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return
        if row["role"] == ROLE_ROOT:
            roots = con.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = 'root' AND active = 1 AND id != ?",
                (user_id,),
            ).fetchone()
            if int(roots["c"] or 0) == 0:
                raise ValueError("至少要留一个管理员，不能删")
        con.execute("DELETE FROM users WHERE id = ?", (user_id,))


def list_students(keyword: str = "", status: str = "") -> list[sqlite3.Row]:
    sql = "SELECT * FROM students WHERE 1 = 1"
    args: list[Any] = []
    if keyword:
        like = f"%{keyword}%"
        sql += " AND (name LIKE ? OR grade LIKE ? OR phone LIKE ? OR note LIKE ?)"
        args += [like, like, like, like]
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY CASE status WHEN '在读' THEN 0 ELSE 1 END, name"
    with _connect() as con:
        return list(con.execute(sql, args))


def list_students_with_summary(keyword: str = "", status: str = "") -> list[dict]:
    out = []
    for row in list_students(keyword, status):
        sid = row["id"]
        out.append(
            {
                "student": dict(row),
                "enrollments": list_enrollments(sid),
                "accounts": get_accounts(sid),
                "points": student_points(sid),
            }
        )
    return out


def list_active_students() -> list[dict]:
    """在读的孩子，带各自的报名，给点名选人用。"""
    return [
        {"student": dict(row), "enrollments": list_enrollments(row["id"])}
        for row in list_students(status="在读")
    ]


def get_student(student_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    return dict(row) if row else None


def create_student(data: dict) -> int:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("姓名不能为空")
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO students(name, gender, grade, phone, note, status, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                data.get("gender", ""),
                data.get("grade", ""),
                data.get("phone", ""),
                data.get("note", ""),
                data.get("status") or "在读",
                _today(),
            ),
        )
        return int(cur.lastrowid)


def update_student(student_id: int, data: dict) -> None:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("姓名不能为空")
    with _connect() as con:
        con.execute(
            """UPDATE students
                  SET name = ?, gender = ?, grade = ?, phone = ?, note = ?, status = ?
                WHERE id = ?""",
            (
                name,
                data.get("gender", ""),
                data.get("grade", ""),
                data.get("phone", ""),
                data.get("note", ""),
                data.get("status") or "在读",
                student_id,
            ),
        )


def delete_student(student_id: int) -> None:
    with _connect() as con:
        con.execute("DELETE FROM students WHERE id = ?", (student_id,))


# ------------------------------------------------------------------ 等级／课型


def list_levels() -> list[sqlite3.Row]:
    with _connect() as con:
        return list(
            con.execute("SELECT * FROM levels ORDER BY sort, subject, name")
        )


def level_full_name(row: sqlite3.Row | dict) -> str:
    subject = (row["subject"] or "").strip()
    name = (row["name"] or "").strip()
    return f"{subject}-{name}" if subject else name


def create_level(subject: str, name: str, minutes: int) -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("等级名称不能为空")
    with _connect() as con:
        cur = con.execute(
            "INSERT INTO levels(subject, name, default_minutes, sort) VALUES(?, ?, ?, 100)",
            ((subject or "").strip(), name, int(minutes)),
        )
        return int(cur.lastrowid)


def update_level(level_id: int, subject: str, name: str, minutes: int) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("等级名称不能为空")
    with _connect() as con:
        con.execute(
            "UPDATE levels SET subject = ?, name = ?, default_minutes = ? WHERE id = ?",
            ((subject or "").strip(), name, int(minutes), level_id),
        )


def count_level_usage(level_id: int) -> int:
    with _connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS c FROM enrollments WHERE level_id = ?", (level_id,)
        ).fetchone()
    return int(row["c"])


def delete_level(level_id: int) -> None:
    if count_level_usage(level_id):
        raise ValueError("已经有学员报了这个等级，不能删除。可以先把它改个名字。")
    with _connect() as con:
        con.execute("DELETE FROM levels WHERE id = ?", (level_id,))


def list_hour_types() -> list[sqlite3.Row]:
    with _connect() as con:
        return list(con.execute("SELECT * FROM hour_types ORDER BY sort, id"))


def list_class_types() -> list[sqlite3.Row]:
    with _connect() as con:
        return list(
            con.execute(
                """SELECT ct.*,
                          p.name AS primary_name,
                          f.name AS fallback_name
                     FROM class_types ct
                     LEFT JOIN hour_types p ON p.id = ct.primary_hour_type_id
                     LEFT JOIN hour_types f ON f.id = ct.fallback_hour_type_id
                    ORDER BY ct.sort, ct.id"""
            )
        )


def update_class_type(
    class_type_id: int,
    deduct: bool,
    primary_hour_type_id: int | None,
    fallback_hour_type_id: int | None,
) -> None:
    with _connect() as con:
        con.execute(
            """UPDATE class_types
                  SET deduct = ?, primary_hour_type_id = ?, fallback_hour_type_id = ?
                WHERE id = ?""",
            (
                1 if deduct else 0,
                primary_hour_type_id,
                fallback_hour_type_id,
                class_type_id,
            ),
        )


# ---------------------------------------------------------------------- 报名


def list_enrollments(student_id: int) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            """SELECT e.*, l.subject, l.name AS level_name, l.default_minutes,
                      ct.name AS class_type_name
                 FROM enrollments e
                 LEFT JOIN levels l ON l.id = e.level_id
                 LEFT JOIN class_types ct ON ct.id = e.class_type_id
                WHERE e.student_id = ?
                ORDER BY e.id""",
            (student_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def create_enrollment(
    student_id: int,
    level_id: int | None,
    class_type_id: int,
    minutes: int,
    status: str = "在读",
    note: str = "",
) -> int:
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO enrollments
                   (student_id, level_id, class_type_id, minutes, status, note, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (student_id, level_id, class_type_id, int(minutes), status, note, _today()),
        )
        return int(cur.lastrowid)


def update_enrollment(
    enrollment_id: int,
    level_id: int | None,
    class_type_id: int,
    minutes: int,
    status: str,
    note: str,
) -> None:
    with _connect() as con:
        con.execute(
            """UPDATE enrollments
                  SET level_id = ?, class_type_id = ?, minutes = ?, status = ?, note = ?
                WHERE id = ?""",
            (level_id, class_type_id, int(minutes), status, note, enrollment_id),
        )


def delete_enrollment(enrollment_id: int) -> None:
    with _connect() as con:
        con.execute("DELETE FROM enrollments WHERE id = ?", (enrollment_id,))


# ------------------------------------------------------------------ 课时账户


def get_accounts(student_id: int) -> list[dict]:
    """每个课时账户的 总课时／已用／剩余／是否不限。"""
    with _connect() as con:
        rows = con.execute(
            """SELECT ht.id AS hour_type_id,
                      ht.name AS name,
                      ht.warn AS warn,
                      COALESCE(SUM(CASE WHEN t.change > 0 THEN t.change ELSE 0 END), 0) AS charged,
                      COALESCE(SUM(CASE WHEN t.change > 0 AND t.source_type LIKE 'payment%'
                                        THEN t.change ELSE 0 END), 0) AS paid,
                      COALESCE(SUM(CASE WHEN t.change > 0
                                         AND (t.source_type = '' OR t.source_type = 'manual')
                                        THEN t.change ELSE 0 END), 0) AS manual,
                      COALESCE(SUM(CASE WHEN t.change < 0 THEN -t.change ELSE 0 END), 0) AS used,
                      COALESCE(SUM(t.change), 0) AS balance,
                      COALESCE(a.unlimited, 0) AS unlimited
                 FROM hour_types ht
                 LEFT JOIN hour_transactions t
                        ON t.hour_type_id = ht.id AND t.student_id = ?
                 LEFT JOIN hour_accounts a
                        ON a.hour_type_id = ht.id AND a.student_id = ?
                GROUP BY ht.id, ht.name, ht.warn, a.unlimited
                ORDER BY ht.sort, ht.id""",
            (student_id, student_id),
        ).fetchall()
    return [dict(r) for r in rows]


def set_hour_type_warn(hour_type_id: int, warn: bool) -> None:
    """这个课时账户要不要"剩余不足就提醒"。"""
    with _connect() as con:
        con.execute(
            "UPDATE hour_types SET warn = ? WHERE id = ?",
            (1 if warn else 0, hour_type_id),
        )


def set_unlimited(student_id: int, hour_type_id: int, unlimited: bool) -> None:
    with _connect() as con:
        con.execute(
            """INSERT INTO hour_accounts(student_id, hour_type_id, unlimited)
               VALUES(?, ?, ?)
               ON CONFLICT(student_id, hour_type_id)
               DO UPDATE SET unlimited = excluded.unlimited""",
            (student_id, hour_type_id, 1 if unlimited else 0),
        )


def add_hours(
    student_id: int,
    hour_type_id: int,
    change: float,
    kind: str = "充值",
    happened_on: str = "",
    note: str = "",
    source_type: str = "",
    source_id: int | None = None,
) -> int:
    if change == 0:
        raise ValueError("数量不能为 0")
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO hour_transactions
                   (student_id, hour_type_id, change, kind, happened_on, note,
                    source_type, source_id, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                student_id,
                hour_type_id,
                float(change),
                kind,
                happened_on or _today(),
                note,
                source_type,
                source_id,
                _today(),
            ),
        )
        new_id = int(cur.lastrowid)
    if source_type != "lesson":
        # 账户变了，这个孩子上课扣的课时要按新余额重算
        recompute_student(student_id)
    return new_id


def list_hour_transactions(student_id: int, limit: int = 50) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            """SELECT t.*, ht.name AS hour_type_name
                 FROM hour_transactions t
                 JOIN hour_types ht ON ht.id = t.hour_type_id
                WHERE t.student_id = ?
                ORDER BY t.happened_on DESC, t.id DESC
                LIMIT ?""",
            (student_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_hour_transaction(transaction_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute(
            """SELECT t.*, ht.name AS hour_type_name
                 FROM hour_transactions t
                 JOIN hour_types ht ON ht.id = t.hour_type_id
                WHERE t.id = ?""",
            (transaction_id,),
        ).fetchone()
    return dict(row) if row else None


def is_manual_hour_transaction(row: dict) -> bool:
    """手记的充值／扣减才能直接改，缴费和上课产生的要去各自的地方改。"""
    return (row.get("source_type") or "") in ("", "manual")


def update_hour_transaction(
    transaction_id: int,
    hour_type_id: int,
    change: float,
    happened_on: str = "",
    note: str = "",
) -> None:
    row = get_hour_transaction(transaction_id)
    if row is None:
        raise ValueError("这笔流水不存在")
    if not is_manual_hour_transaction(row):
        raise ValueError("这笔是缴费或上课产生的，请到对应的页面改")
    if not change:
        raise ValueError("数量不能为 0")
    with _connect() as con:
        con.execute(
            """UPDATE hour_transactions
                  SET hour_type_id = ?, change = ?, happened_on = ?, note = ?
                WHERE id = ?""",
            (hour_type_id, float(change), happened_on or row["happened_on"], note, transaction_id),
        )
    recompute_student(int(row["student_id"]))


def delete_hour_transaction(transaction_id: int) -> None:
    row = get_hour_transaction(transaction_id)
    if row is None:
        return
    if not is_manual_hour_transaction(row):
        raise ValueError("这笔是缴费或上课产生的，请到对应的页面删")
    with _connect() as con:
        con.execute("DELETE FROM hour_transactions WHERE id = ?", (transaction_id,))
    recompute_student(int(row["student_id"]))


def hours_text(accounts: list[dict]) -> str:
    """把课时账户拼成一句话，给列表页用。"""
    parts = []
    for a in accounts:
        if a["unlimited"]:
            parts.append(f"{a['name']} 不限")
        elif a["balance"] or a["charged"]:
            parts.append(f"{a['name']} {_num(a['balance'])}")
    return " · ".join(parts) if parts else "还没有课时"


def _num(value: float) -> str:
    value = round(float(value or 0), 2)
    return str(int(value)) if value == int(value) else f"{value:g}"


def num_text(value: float) -> str:
    return _num(value)


# -------------------------------------------------------------- 上课与点名


def create_lesson(
    lesson_date: str,
    start_time: str,
    minutes: int,
    class_type_id: int,
    level_id: int | None,
    comment: str = "",
    plan: str = "",
    note: str = "",
    kind: str = "正常",
) -> int:
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO lessons
                   (lesson_date, start_time, minutes, class_type_id, level_id,
                    comment, plan, note, kind, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lesson_date,
                start_time,
                int(minutes),
                class_type_id,
                level_id,
                comment,
                plan,
                note,
                kind,
                _today(),
            ),
        )
        return int(cur.lastrowid)


def update_lesson(
    lesson_id: int,
    lesson_date: str,
    start_time: str,
    minutes: int,
    class_type_id: int,
    level_id: int | None,
    comment: str = "",
    plan: str = "",
    note: str = "",
) -> None:
    with _connect() as con:
        con.execute(
            """UPDATE lessons
                  SET lesson_date = ?, start_time = ?, minutes = ?, class_type_id = ?,
                      level_id = ?, comment = ?, plan = ?, note = ?
                WHERE id = ?""",
            (
                lesson_date,
                start_time,
                int(minutes),
                class_type_id,
                level_id,
                comment,
                plan,
                note,
                lesson_id,
            ),
        )
    recompute_lesson(lesson_id)


_LESSON_SELECT = """
    SELECT l.*,
           ct.name  AS class_type_name,
           ct.deduct AS class_type_deduct,
           ct.primary_hour_type_id  AS primary_hour_type_id,
           ct.fallback_hour_type_id AS fallback_hour_type_id,
           lv.subject AS subject,
           lv.name    AS level_name,
           (SELECT COUNT(*) FROM attendance a WHERE a.lesson_id = l.id) AS student_count,
           (SELECT COALESCE(SUM(CASE WHEN a.attendance = 1 THEN a.minutes ELSE 0 END), 0)
              FROM attendance a WHERE a.lesson_id = l.id) AS attended_minutes,
           (SELECT COALESCE(SUM((a.attendance + a.discipline + a.performance) * 10 + a.bonus), 0)
              FROM attendance a WHERE a.lesson_id = l.id) AS points
      FROM lessons l
      LEFT JOIN class_types ct ON ct.id = l.class_type_id
      LEFT JOIN levels lv ON lv.id = l.level_id
"""


def get_lesson(lesson_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute(_LESSON_SELECT + " WHERE l.id = ?", (lesson_id,)).fetchone()
    return dict(row) if row else None


def list_lessons(limit: int = 200) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            _LESSON_SELECT + " ORDER BY l.lesson_date DESC, l.start_time DESC, l.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_lesson(lesson_id: int) -> None:
    with _connect() as con:
        students = [
            int(r["student_id"])
            for r in con.execute(
                "SELECT DISTINCT student_id FROM attendance WHERE lesson_id = ?",
                (lesson_id,),
            ).fetchall()
        ]
        rows = con.execute(
            "SELECT id FROM attendance WHERE lesson_id = ?", (lesson_id,)
        ).fetchall()
        for row in rows:
            _remove_files(con, "attendance", int(row["id"]))
        _remove_files(con, "lesson", lesson_id)
        con.execute(
            "DELETE FROM hour_transactions WHERE source_type = 'lesson' AND source_id = ?",
            (lesson_id,),
        )
        con.execute(
            "DELETE FROM point_transactions WHERE source_type = 'lesson' AND source_id = ?",
            (lesson_id,),
        )
        con.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
    for student_id in students:
        recompute_student(student_id)


def list_attendance(lesson_id: int) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            """SELECT a.*,
                      s.name AS student_name,
                      e.level_id AS enroll_level_id,
                      lv.subject AS subject,
                      lv.name AS level_name
                 FROM attendance a
                 JOIN students s ON s.id = a.student_id
                 LEFT JOIN enrollments e ON e.id = a.enrollment_id
                 LEFT JOIN levels lv ON lv.id = e.level_id
                WHERE a.lesson_id = ?
                ORDER BY a.id""",
            (lesson_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_attendance(attendance_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute(
            """SELECT a.*, s.name AS student_name
                 FROM attendance a JOIN students s ON s.id = a.student_id
                WHERE a.id = ?""",
            (attendance_id,),
        ).fetchone()
    return dict(row) if row else None


def find_enrollment(student_id: int, level_id: int | None = None) -> dict | None:
    """找一个孩子在读的报名；优先挑跟这节课同等级的。"""
    rows = [e for e in list_enrollments(student_id) if e["status"] == "在读"]
    if not rows:
        rows = list_enrollments(student_id)
    if level_id:
        for e in rows:
            if e["level_id"] == level_id:
                return e
    return rows[0] if rows else None


def add_attendance(
    lesson_id: int,
    student_id: int,
    enrollment_id: int | None = None,
    minutes: float | None = None,
) -> int:
    lesson = get_lesson(lesson_id)
    if lesson is None:
        raise ValueError("这节课不存在")
    if enrollment_id is None:
        enrollment = find_enrollment(student_id, lesson["level_id"])
        enrollment_id = enrollment["id"] if enrollment else None
    if minutes is None:
        enrollment = find_enrollment(student_id, lesson["level_id"])
        minutes = (
            enrollment["minutes"]
            if enrollment and enrollment["level_id"] == lesson["level_id"]
            else lesson["minutes"]
        )
    with _connect() as con:
        exists = con.execute(
            "SELECT id FROM attendance WHERE lesson_id = ? AND student_id = ?",
            (lesson_id, student_id),
        ).fetchone()
        if exists:
            return int(exists["id"])
        cur = con.execute(
            """INSERT INTO attendance
                   (lesson_id, student_id, enrollment_id, minutes, created_at)
               VALUES(?, ?, ?, ?, ?)""",
            (lesson_id, student_id, enrollment_id, float(minutes), _today()),
        )
        new_id = int(cur.lastrowid)
    recompute_lesson(lesson_id)
    return new_id


_ATT_FIELDS = {"attendance", "discipline", "performance", "bonus", "minutes", "comment"}


def update_attendance(attendance_id: int, **fields) -> None:
    data = {k: v for k, v in fields.items() if k in _ATT_FIELDS}
    if not data:
        return
    sql = ", ".join(f"{k} = ?" for k in data)
    with _connect() as con:
        row = con.execute(
            "SELECT lesson_id FROM attendance WHERE id = ?", (attendance_id,)
        ).fetchone()
        if row is None:
            return
        con.execute(
            f"UPDATE attendance SET {sql} WHERE id = ?",
            (*data.values(), attendance_id),
        )
    recompute_lesson(int(row["lesson_id"]))
    if "attendance" in data:
        sync_makeup_for_attendance(attendance_id)


def delete_attendance(attendance_id: int) -> None:
    with _connect() as con:
        row = con.execute(
            "SELECT lesson_id FROM attendance WHERE id = ?", (attendance_id,)
        ).fetchone()
        if row is None:
            return
        _remove_files(con, "attendance", attendance_id)
        con.execute("DELETE FROM attendance WHERE id = ?", (attendance_id,))
    recompute_lesson(int(row["lesson_id"]))


def recompute_lesson(lesson_id: int) -> None:
    """按点名的结果，重新生成这节课的积分，并把涉及到的孩子的课时重算一遍。"""
    lesson = get_lesson(lesson_id)
    if lesson is None:
        return
    rows = list_attendance(lesson_id)
    with _connect() as con:
        con.execute(
            "DELETE FROM point_transactions WHERE source_type = 'lesson' AND source_id = ?",
            (lesson_id,),
        )
        day = lesson["lesson_date"]
        label = lesson_label(lesson)
        for a in rows:
            present = int(a["attendance"] or 0)
            # 请假不算分：出勤为 0 时，后面三个勾和加分都不算
            points = (
                (present + int(a["discipline"] or 0) + int(a["performance"] or 0)) * 10
                + float(a["bonus"] or 0)
                if present
                else 0.0
            )
            if points:
                con.execute(
                    """INSERT INTO point_transactions
                           (student_id, change, kind, happened_on, note,
                            source_type, source_id, created_at)
                       VALUES(?, ?, '上课', ?, ?, 'lesson', ?, ?)""",
                    (a["student_id"], float(points), day, label, lesson_id, _today()),
                )
    # 课时按这个孩子的全部上课记录重算（先上课后缴费也能归位）
    for a in rows:
        recompute_student(int(a["student_id"]))


def recompute_student(student_id: int) -> None:
    """把这个孩子上课扣的课时重算一遍。

    缴费和手工调整不动，只按"上课时间顺序"重新扣课时：
    竞赛课就先扣竞赛账户，不够再扣正课 —— 后来补交了竞赛课时，之前的课也会归位。
    """
    with _connect() as con:
        rows = con.execute(
            """SELECT a.attendance, a.minutes,
                      l.id AS lesson_id, l.lesson_date, l.start_time,
                      l.minutes AS lesson_minutes,
                      ct.deduct AS class_deduct,
                      ct.primary_hour_type_id AS primary_id,
                      ct.fallback_hour_type_id AS fallback_id,
                      ct.name AS class_type_name,
                      lv.subject AS subject,
                      lv.name AS level_name
                 FROM attendance a
                 JOIN lessons l ON l.id = a.lesson_id
                 LEFT JOIN class_types ct ON ct.id = l.class_type_id
                 LEFT JOIN levels lv ON lv.id = l.level_id
                WHERE a.student_id = ?
                ORDER BY l.lesson_date, l.start_time, l.id""",
            (student_id,),
        ).fetchall()
        con.execute(
            "DELETE FROM hour_transactions WHERE student_id = ? AND source_type = 'lesson'",
            (student_id,),
        )
        names = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM hour_types")}
        for row in rows:
            if not row["attendance"] or not row["class_deduct"]:
                continue
            hours = round(float(row["minutes"] or row["lesson_minutes"] or 0) / 60, 4)
            if hours <= 0 or row["primary_id"] is None:
                continue
            label = " · ".join(
                x
                for x in [
                    f"{row['subject'] or ''}-{row['level_name'] or ''}".strip("-"),
                    row["class_type_name"] or "",
                ]
                if x
            )
            parts = _split_deduction(
                con, student_id, hours, row["primary_id"], row["fallback_id"]
            )
            borrowed = any(ht != row["primary_id"] for ht, _ in parts)
            note = f"{label} · 点名" if label else "点名"
            if borrowed:
                note += (
                    f"（{names.get(row['primary_id'], '课时')}不够，"
                    f"从{names.get(row['fallback_id'], '正课')}扣的）"
                )
            for hour_type_id, amount in parts:
                con.execute(
                    """INSERT INTO hour_transactions
                           (student_id, hour_type_id, change, kind, happened_on, note,
                            source_type, source_id, created_at)
                       VALUES(?, ?, ?, '上课', ?, ?, 'lesson', ?, ?)""",
                    (
                        student_id,
                        hour_type_id,
                        -amount,
                        row["lesson_date"],
                        note,
                        row["lesson_id"],
                        _today(),
                    ),
                )


def recompute_all_hours() -> int:
    """把所有孩子的上课扣课时重算一遍。"""
    count = 0
    for student in list_students():
        recompute_student(int(student["id"]))
        count += 1
    return count


def _split_deduction(
    con: sqlite3.Connection,
    student_id: int,
    hours: float,
    primary_id: int,
    fallback_id: int | None,
) -> list[tuple[int, float]]:
    """从主账户扣，不够再补扣备用账户；账户是"不限"就直接跳过。"""
    if hours <= 0:
        return []
    if _is_unlimited(con, student_id, primary_id):
        return []
    balance = _balance(con, student_id, primary_id)
    take = round(min(hours, max(balance, 0.0)), 4)
    out: list[tuple[int, float]] = []
    if take > 0:
        out.append((primary_id, take))
    rest = round(hours - take, 4)
    if rest > 0:
        if fallback_id is None:
            out.append((primary_id, rest))  # 没有备用账户就记成欠课时
        elif not _is_unlimited(con, student_id, fallback_id):
            out.append((fallback_id, rest))
    return out


def _balance(con: sqlite3.Connection, student_id: int, hour_type_id: int) -> float:
    row = con.execute(
        """SELECT COALESCE(SUM(change), 0) AS b FROM hour_transactions
            WHERE student_id = ? AND hour_type_id = ?""",
        (student_id, hour_type_id),
    ).fetchone()
    return float(row["b"] or 0)


def _is_unlimited(con: sqlite3.Connection, student_id: int, hour_type_id: int) -> bool:
    row = con.execute(
        "SELECT unlimited FROM hour_accounts WHERE student_id = ? AND hour_type_id = ?",
        (student_id, hour_type_id),
    ).fetchone()
    return bool(row and row["unlimited"])


def lesson_label(lesson: dict) -> str:
    subject = (lesson.get("subject") or "").strip()
    level = (lesson.get("level_name") or "").strip()
    name = f"{subject}-{level}" if subject else level
    parts = [p for p in [name, lesson.get("class_type_name") or ""] if p]
    return " · ".join(parts) or "上课"


# ---------------------------------------------------------------------- 积分


def student_points(student_id: int) -> float:
    with _connect() as con:
        row = con.execute(
            "SELECT COALESCE(SUM(change), 0) AS p FROM point_transactions WHERE student_id = ?",
            (student_id,),
        ).fetchone()
    return float(row["p"] or 0)


def points_map(student_ids: list[int]) -> dict[int, float]:
    if not student_ids:
        return {}
    marks = ",".join("?" * len(student_ids))
    with _connect() as con:
        rows = con.execute(
            f"""SELECT student_id, COALESCE(SUM(change), 0) AS p
                  FROM point_transactions
                 WHERE student_id IN ({marks})
                 GROUP BY student_id""",
            student_ids,
        ).fetchall()
    return {int(r["student_id"]): float(r["p"]) for r in rows}


def list_point_transactions(student_id: int, limit: int = 50) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            """SELECT * FROM point_transactions
                WHERE student_id = ?
                ORDER BY happened_on DESC, id DESC LIMIT ?""",
            (student_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def add_redemption(
    student_id: int, points: float, happened_on: str = "", note: str = ""
) -> int:
    """兑换：从积分里扣掉。"""
    value = abs(float(points or 0))
    if value <= 0:
        raise ValueError("兑换的积分数要大于 0")
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO point_transactions
                   (student_id, change, kind, happened_on, note,
                    source_type, source_id, created_at)
               VALUES(?, ?, '兑换', ?, ?, 'manual', NULL, ?)""",
            (student_id, -value, happened_on or _today(), note, _today()),
        )
        return int(cur.lastrowid)


def update_redemption(
    redemption_id: int,
    student_id: int,
    points: float,
    happened_on: str,
    note: str = "",
) -> None:
    value = abs(float(points or 0))
    if value <= 0:
        raise ValueError("兑换的积分数要大于 0")
    with _connect() as con:
        con.execute(
            """UPDATE point_transactions
                  SET student_id = ?, change = ?, happened_on = ?, note = ?
                WHERE id = ? AND kind = '兑换' AND source_type = 'manual'""",
            (student_id, -value, happened_on or _today(), note, redemption_id),
        )


def delete_redemption(redemption_id: int) -> None:
    with _connect() as con:
        con.execute(
            "DELETE FROM point_transactions WHERE id = ? AND kind = '兑换' AND source_type = 'manual'",
            (redemption_id,),
        )


def list_redemptions(student_id: int | None = None, limit: int = 200) -> list[dict]:
    sql = """SELECT t.*, s.name AS student_name
               FROM point_transactions t
               JOIN students s ON s.id = t.student_id
              WHERE t.kind = '兑换' AND t.source_type = 'manual'"""
    args: list[Any] = []
    if student_id is not None:
        sql += " AND t.student_id = ?"
        args.append(student_id)
    sql += " ORDER BY t.happened_on DESC, t.id DESC LIMIT ?"
    args.append(limit)
    with _connect() as con:
        rows = con.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def points_balances() -> list[dict]:
    """每个孩子现在的积分（多的排前面）。"""
    with _connect() as con:
        rows = con.execute(
            """SELECT s.id, s.name, s.status, s.grade,
                      COALESCE(SUM(t.change), 0) AS points
                 FROM students s
                 LEFT JOIN point_transactions t ON t.student_id = s.id
                GROUP BY s.id, s.name, s.status, s.grade
                ORDER BY points DESC, s.name"""
        ).fetchall()
    return [dict(r) for r in rows]


def student_recent_lessons(student_id: int, limit: int = 5) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            """SELECT a.attendance, a.discipline, a.performance, a.bonus, a.minutes,
                      a.comment AS attendance_comment,
                      l.id AS lesson_id, l.lesson_date, l.start_time,
                      ct.name AS class_type_name, ct.deduct AS class_type_deduct,
                      lv.subject, lv.name AS level_name
                 FROM attendance a
                 JOIN lessons l ON l.id = a.lesson_id
                 LEFT JOIN class_types ct ON ct.id = l.class_type_id
                 LEFT JOIN levels lv ON lv.id = l.level_id
                WHERE a.student_id = ?
                ORDER BY l.lesson_date DESC, l.id DESC LIMIT ?""",
            (student_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def attendance_names(lesson_ids: list[int]) -> dict[int, list[dict]]:
    """每节课都有谁（列表上用）。"""
    if not lesson_ids:
        return {}
    marks = ",".join("?" * len(lesson_ids))
    with _connect() as con:
        rows = con.execute(
            f"""SELECT a.lesson_id, a.attendance, s.name
                  FROM attendance a
                  JOIN students s ON s.id = a.student_id
                 WHERE a.lesson_id IN ({marks})
                 ORDER BY a.id""",
            lesson_ids,
        ).fetchall()
    out: dict[int, list[dict]] = {}
    for row in rows:
        out.setdefault(int(row["lesson_id"]), []).append(
            {"name": row["name"], "attendance": int(row["attendance"] or 0)}
        )
    return out


# -------------------------------------------------------------------- 待补课


def sync_makeup_for_attendance(attendance_id: int) -> None:
    """请假就自动记一条待补课；改回出勤就把待办撤掉。"""
    a = get_attendance(attendance_id)
    if a is None:
        return
    with _connect() as con:
        pending = con.execute(
            "SELECT id FROM makeups WHERE attendance_id = ? AND status = '待补'",
            (attendance_id,),
        ).fetchone()
        if a["attendance"]:
            if pending:
                con.execute("DELETE FROM makeups WHERE id = ?", (pending["id"],))
            return
        if pending:
            return
        con.execute(
            """INSERT INTO makeups(student_id, lesson_id, attendance_id, status, created_at)
               VALUES(?, ?, ?, '待补', ?)""",
            (a["student_id"], a["lesson_id"], attendance_id, _today()),
        )


_MAKEUP_SELECT = """
    SELECT m.*,
           s.name AS student_name,
           l.lesson_date, l.start_time, l.minutes AS lesson_minutes, l.kind AS lesson_kind,
           ct.name AS class_type_name, lv.subject, lv.name AS level_name,
           ml.lesson_date AS makeup_date, ml.start_time AS makeup_time
      FROM makeups m
      JOIN students s ON s.id = m.student_id
      LEFT JOIN lessons l ON l.id = m.lesson_id
      LEFT JOIN class_types ct ON ct.id = l.class_type_id
      LEFT JOIN levels lv ON lv.id = l.level_id
      LEFT JOIN lessons ml ON ml.id = m.makeup_lesson_id
"""


def get_makeup(makeup_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute(_MAKEUP_SELECT + " WHERE m.id = ?", (makeup_id,)).fetchone()
    return dict(row) if row else None


def get_makeup_by_lesson(lesson_id: int) -> dict | None:
    """这节补课是给谁、补的哪一节。"""
    with _connect() as con:
        row = con.execute(
            _MAKEUP_SELECT + " WHERE m.makeup_lesson_id = ?", (lesson_id,)
        ).fetchone()
    return dict(row) if row else None


def makeups_by_lesson(lesson_ids: list[int]) -> dict[int, dict]:
    if not lesson_ids:
        return {}
    marks = ",".join("?" * len(lesson_ids))
    with _connect() as con:
        rows = con.execute(
            _MAKEUP_SELECT + f" WHERE m.makeup_lesson_id IN ({marks})", lesson_ids
        ).fetchall()
    return {int(r["makeup_lesson_id"]): dict(r) for r in rows}


def list_makeups(status: str = "待补", student_id: int | None = None) -> list[dict]:
    sql = _MAKEUP_SELECT + " WHERE m.status = ?"
    args: list[Any] = [status]
    if student_id is not None:
        sql += " AND m.student_id = ?"
        args.append(student_id)
    sql += " ORDER BY l.lesson_date DESC, m.id DESC"
    with _connect() as con:
        rows = con.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def pending_makeup_count(student_id: int | None = None) -> int:
    sql = "SELECT COUNT(*) AS c FROM makeups WHERE status = '待补'"
    args: list[Any] = []
    if student_id is not None:
        sql += " AND student_id = ?"
        args.append(student_id)
    with _connect() as con:
        row = con.execute(sql, args).fetchone()
    return int(row["c"] or 0)


def students_with_pending_makeups() -> set[int]:
    with _connect() as con:
        rows = con.execute(
            "SELECT DISTINCT student_id FROM makeups WHERE status = '待补'"
        ).fetchall()
    return {int(r["student_id"]) for r in rows}


def arrange_makeup(
    makeup_id: int, lesson_date: str, start_time: str, minutes: float
) -> int:
    """安排补课：新开一节课，把孩子的名字加上去，并关联回原来请假的那节。"""
    makeup = get_makeup(makeup_id)
    if makeup is None:
        raise ValueError("这条待补课不存在")
    origin = get_lesson(makeup["lesson_id"]) if makeup["lesson_id"] else None
    class_type_id = origin["class_type_id"] if origin else None
    if class_type_id is None:
        class_type_id = next(
            (c["id"] for c in list_class_types() if c["name"] == "正课"), None
        )
    level_id = origin["level_id"] if origin else None
    note = f"补课：{makeup['lesson_date']} 请假的那节" if makeup["lesson_date"] else "补课"
    new_lesson = create_lesson(
        lesson_date,
        start_time,
        int(minutes),
        class_type_id,
        level_id,
        comment="",
        note=note,
        kind="补课",
    )
    attendance_id = add_attendance(new_lesson, makeup["student_id"], minutes=minutes)
    with _connect() as con:
        con.execute(
            """UPDATE makeups
                  SET status = '已补', makeup_lesson_id = ?, makeup_attendance_id = ?
                WHERE id = ?""",
            (new_lesson, attendance_id, makeup_id),
        )
    return new_lesson


def cancel_makeup(makeup_id: int, note: str = "") -> None:
    with _connect() as con:
        con.execute(
            "UPDATE makeups SET status = '取消', note = ? WHERE id = ?",
            (note, makeup_id),
        )


# ---------------------------------------------------------------- 固定课表

_TEMPLATE_SELECT = """
    SELECT t.*,
           ct.name AS class_type_name,
           lv.subject AS subject,
           lv.name AS level_name,
           (SELECT COUNT(*) FROM schedule_students ss WHERE ss.template_id = t.id) AS student_count
      FROM schedule_templates t
      LEFT JOIN class_types ct ON ct.id = t.class_type_id
      LEFT JOIN levels lv ON lv.id = t.level_id
"""


def list_templates(weekday: int | None = None, active_only: bool = True) -> list[dict]:
    sql = _TEMPLATE_SELECT + " WHERE 1 = 1"
    args: list[Any] = []
    if active_only:
        sql += " AND t.active = 1"
    if weekday is not None:
        sql += " AND t.weekday = ?"
        args.append(int(weekday))
    sql += " ORDER BY t.weekday, t.start_time, t.id"
    with _connect() as con:
        rows = con.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def get_template(template_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute(_TEMPLATE_SELECT + " WHERE t.id = ?", (template_id,)).fetchone()
    return dict(row) if row else None


def create_template(
    weekday: int,
    start_time: str,
    minutes: int,
    class_type_id: int,
    level_id: int | None,
    note: str = "",
) -> int:
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO schedule_templates
                   (weekday, start_time, minutes, class_type_id, level_id, note, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (
                int(weekday),
                start_time,
                int(minutes),
                class_type_id,
                level_id,
                note,
                _today(),
            ),
        )
        return int(cur.lastrowid)


def update_template(
    template_id: int,
    weekday: int,
    start_time: str,
    minutes: int,
    class_type_id: int,
    level_id: int | None,
    note: str = "",
) -> None:
    with _connect() as con:
        con.execute(
            """UPDATE schedule_templates
                  SET weekday = ?, start_time = ?, minutes = ?, class_type_id = ?,
                      level_id = ?, note = ?
                WHERE id = ?""",
            (
                int(weekday),
                start_time,
                int(minutes),
                class_type_id,
                level_id,
                note,
                template_id,
            ),
        )


def delete_template(template_id: int) -> None:
    with _connect() as con:
        con.execute("DELETE FROM schedule_templates WHERE id = ?", (template_id,))


def template_student_ids(template_id: int) -> list[int]:
    with _connect() as con:
        rows = con.execute(
            "SELECT student_id FROM schedule_students WHERE template_id = ? ORDER BY student_id",
            (template_id,),
        ).fetchall()
    return [int(r["student_id"]) for r in rows]


def set_template_students(template_id: int, student_ids: list[int]) -> None:
    with _connect() as con:
        con.execute(
            "DELETE FROM schedule_students WHERE template_id = ?", (template_id,)
        )
        for sid in dict.fromkeys(student_ids):
            con.execute(
                "INSERT OR IGNORE INTO schedule_students(template_id, student_id) VALUES(?, ?)",
                (template_id, int(sid)),
            )


def lessons_on(lesson_date: str) -> list[dict]:
    """某一天已经排过／上过的课。"""
    with _connect() as con:
        rows = con.execute(
            _LESSON_SELECT + " WHERE l.lesson_date = ? ORDER BY l.start_time, l.id",
            (lesson_date,),
        ).fetchall()
    return [dict(r) for r in rows]


def find_lesson_for_template(template: dict, lesson_date: str) -> dict | None:
    """这天的课是不是已经照这张课表建过了。"""
    for lesson in lessons_on(lesson_date):
        if (
            lesson["start_time"] == template["start_time"]
            and lesson["class_type_id"] == template["class_type_id"]
            and (lesson["level_id"] or None) == (template["level_id"] or None)
        ):
            return lesson
    return None


def create_lesson_from_template(template_id: int, lesson_date: str) -> int:
    """照着固定课表建一节课，孩子一起点上。"""
    template = get_template(template_id)
    if template is None:
        raise ValueError("这张课表不存在")
    existing = find_lesson_for_template(template, lesson_date)
    if existing:
        return int(existing["id"])
    lesson_id = create_lesson(
        lesson_date,
        template["start_time"],
        template["minutes"],
        template["class_type_id"],
        template["level_id"],
    )
    for sid in template_student_ids(template_id):
        add_attendance(lesson_id, sid, minutes=template["minutes"])
    return lesson_id


# ------------------------------------------------------------------ 试听跟进


def create_trial(data: dict) -> int:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("姓名不能为空")
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO trials
                   (name, gender, grade, parent_name, phone, source, status,
                    trial_on, note, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                data.get("gender", ""),
                data.get("grade", ""),
                data.get("parent_name", ""),
                data.get("phone", ""),
                data.get("source", ""),
                data.get("status") or "待试听",
                data.get("trial_on", ""),
                data.get("note", ""),
                _today(),
            ),
        )
        return int(cur.lastrowid)


def update_trial(trial_id: int, data: dict) -> None:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("姓名不能为空")
    with _connect() as con:
        con.execute(
            """UPDATE trials
                  SET name = ?, gender = ?, grade = ?, parent_name = ?, phone = ?,
                      source = ?, status = ?, trial_on = ?, note = ?
                WHERE id = ?""",
            (
                name,
                data.get("gender", ""),
                data.get("grade", ""),
                data.get("parent_name", ""),
                data.get("phone", ""),
                data.get("source", ""),
                data.get("status") or "待试听",
                data.get("trial_on", ""),
                data.get("note", ""),
                trial_id,
            ),
        )


def get_trial(trial_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute("SELECT * FROM trials WHERE id = ?", (trial_id,)).fetchone()
    return dict(row) if row else None


def list_trials(status: str = "", keyword: str = "") -> list[dict]:
    sql = "SELECT * FROM trials WHERE 1 = 1"
    args: list[Any] = []
    if status:
        sql += " AND status = ?"
        args.append(status)
    if keyword:
        like = f"%{keyword}%"
        sql += " AND (name LIKE ? OR phone LIKE ? OR parent_name LIKE ? OR note LIKE ?)"
        args += [like, like, like, like]
    sql += """ ORDER BY CASE status
                            WHEN '待试听' THEN 0
                            WHEN '已试听' THEN 1
                            WHEN '已报名' THEN 2
                            ELSE 3
                        END,
                    trial_on DESC, id DESC"""
    with _connect() as con:
        rows = con.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def trial_counts() -> dict[str, int]:
    counts = {s: 0 for s in TRIAL_STATUS}
    with _connect() as con:
        for row in con.execute(
            "SELECT status, COUNT(*) AS c FROM trials GROUP BY status"
        ):
            counts[row["status"]] = int(row["c"])
    return counts


def delete_trial(trial_id: int) -> None:
    with _connect() as con:
        con.execute("DELETE FROM trials WHERE id = ?", (trial_id,))


def convert_trial_to_student(trial_id: int) -> int:
    """试听转正式：建一份正式学员档案，并把试听记录标成已报名。"""
    trial = get_trial(trial_id)
    if trial is None:
        raise ValueError("这条试听记录不存在")
    if trial["student_id"]:
        return int(trial["student_id"])
    note_bits = []
    if trial["source"]:
        note_bits.append(f"来源：{trial['source']}")
    if trial["parent_name"]:
        note_bits.append(f"家长：{trial['parent_name']}")
    if trial["note"]:
        note_bits.append(trial["note"])
    student_id = create_student(
        {
            "name": trial["name"],
            "gender": trial["gender"],
            "grade": trial["grade"],
            "phone": trial["phone"],
            "note": "；".join(note_bits),
            "status": "在读",
        }
    )
    with _connect() as con:
        con.execute(
            "UPDATE trials SET status = '已报名', student_id = ? WHERE id = ?",
            (student_id, trial_id),
        )
    return student_id


# ---------------------------------------------------------------------- 缴费


def add_file(
    owner_type: str,
    owner_id: int,
    kind: str,
    filename: str,
    stored_name: str,
    size: int,
) -> int:
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO files
                   (owner_type, owner_id, kind, filename, stored_name, size, uploaded_at)
               VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (owner_type, owner_id, kind, filename, stored_name, int(size), _today()),
        )
        return int(cur.lastrowid)


def list_files(owner_type: str, owner_id: int, kind: str | None = None) -> list[dict]:
    sql = "SELECT * FROM files WHERE owner_type = ? AND owner_id = ?"
    args: list[Any] = [owner_type, owner_id]
    if kind:
        sql += " AND kind = ?"
        args.append(kind)
    sql += " ORDER BY id"
    with _connect() as con:
        rows = con.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def files_by_owner(
    owner_type: str, owner_ids: list[int], kind: str | None = None
) -> dict[int, list[dict]]:
    if not owner_ids:
        return {}
    marks = ",".join("?" * len(owner_ids))
    sql = f"SELECT * FROM files WHERE owner_type = ? AND owner_id IN ({marks})"
    args: list[Any] = [owner_type, *owner_ids]
    if kind:
        sql += " AND kind = ?"
        args.append(kind)
    sql += " ORDER BY id"
    with _connect() as con:
        rows = con.execute(sql, args).fetchall()
    out: dict[int, list[dict]] = {}
    for row in rows:
        out.setdefault(int(row["owner_id"]), []).append(dict(row))
    return out


def get_file(file_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    return dict(row) if row else None


def _remove_files(con: sqlite3.Connection, owner_type: str, owner_id: int) -> None:
    rows = con.execute(
        "SELECT stored_name FROM files WHERE owner_type = ? AND owner_id = ?",
        (owner_type, owner_id),
    ).fetchall()
    for row in rows:
        path = UPLOAD_DIR / row["stored_name"]
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    con.execute(
        "DELETE FROM files WHERE owner_type = ? AND owner_id = ?", (owner_type, owner_id)
    )


def delete_file(file_id: int) -> None:
    with _connect() as con:
        row = con.execute(
            "SELECT stored_name FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        if row is None:
            return
        con.execute("DELETE FROM files WHERE id = ?", (file_id,))
        path = UPLOAD_DIR / row["stored_name"]
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def file_url(file_row: dict) -> str:
    # assets 目录就指到 data/files，所以文件直接挂在网站根上
    return f"/{file_row['stored_name']}"


def human_size(size: int) -> str:
    size = int(size or 0)
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


# ---------------------------------------------------------------------- 报表


def hour_alerts() -> list[dict]:
    """剩余课时不够、需要提醒的孩子（只看设置了提醒的账户）。"""
    out = []
    for student in list_students():
        for account in get_accounts(student["id"]):
            if not account["warn"] or account["unlimited"]:
                continue
            if not account["charged"]:
                continue
            if account["balance"] <= WARN_BALANCE:
                out.append(
                    {
                        "student_id": student["id"],
                        "student": student["name"],
                        "grade": student["grade"],
                        "phone": student["phone"],
                        "account": account["name"],
                        "balance": account["balance"],
                    }
                )
    out.sort(key=lambda a: (a["balance"], a["student"]))
    return out


def month_stats(month: str) -> dict:
    """month 传 '2026-09'。"""
    like = f"{month}%"
    with _connect() as con:
        money = con.execute(
            "SELECT COALESCE(SUM(amount), 0) AS s, COUNT(*) AS c FROM payments WHERE paid_on LIKE ?",
            (like,),
        ).fetchone()
        lessons = con.execute(
            "SELECT COUNT(*) AS c FROM lessons WHERE lesson_date LIKE ?", (like,)
        ).fetchone()
        attended = con.execute(
            """SELECT COUNT(*) AS c, COALESCE(SUM(a.minutes), 0) AS m
                 FROM attendance a JOIN lessons l ON l.id = a.lesson_id
                WHERE l.lesson_date LIKE ? AND a.attendance = 1""",
            (like,),
        ).fetchone()
    return {
        "income": float(money["s"] or 0),
        "payments": int(money["c"] or 0),
        "lessons": int(lessons["c"] or 0),
        "attendance": int(attended["c"] or 0),
        "hours": round(float(attended["m"] or 0) / 60, 2),
    }


def month_lesson_counts(month: str) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            """SELECT s.name AS name, COUNT(*) AS times,
                      COALESCE(SUM(a.minutes), 0) AS minutes
                 FROM attendance a
                 JOIN lessons l ON l.id = a.lesson_id
                 JOIN students s ON s.id = a.student_id
                WHERE l.lesson_date LIKE ? AND a.attendance = 1
                GROUP BY s.id, s.name
                ORDER BY times DESC, s.name""",
            (f"{month}%",),
        ).fetchall()
    return [dict(r) for r in rows]


def _level_text(row: dict) -> str:
    subject = (row.get("subject") or "").strip()
    level = (row.get("level_name") or "").strip()
    return f"{subject}-{level}" if subject else level


def export_tables() -> list[tuple[str, list[str], list[list]]]:
    """把所有数据整理成可以写到 Excel 的表。"""
    sheets: list[tuple[str, list[str], list[list]]] = []
    students = list_students()

    sheets.append(
        (
            "学员",
            ["ID", "姓名", "性别", "年级", "电话", "状态", "备注", "建档日期"],
            [
                [s["id"], s["name"], s["gender"], s["grade"], s["phone"], s["status"], s["note"], s["created_at"]]
                for s in students
            ],
        )
    )

    rows = []
    for s in students:
        for e in list_enrollments(s["id"]):
            rows.append(
                [
                    s["name"],
                    _level_text(e),
                    e["class_type_name"],
                    e["minutes"],
                    e["status"],
                    e["note"],
                ]
            )
    sheets.append(("报名课程", ["学员", "等级", "课型", "单次时长(分)", "状态", "备注"], rows))

    rows = []
    for s in students:
        for a in get_accounts(s["id"]):
            if not (a["charged"] or a["used"] or a["unlimited"]):
                continue
            rows.append(
                [
                    s["name"],
                    a["name"],
                    a["charged"],
                    a["paid"],
                    a["manual"],
                    a["used"],
                    a["balance"],
                    "是" if a["unlimited"] else "",
                ]
            )
    sheets.append(
        (
            "课时账户",
            ["学员", "账户", "总课时", "缴费买入", "手工调整", "已用", "剩余", "不限课时"],
            rows,
        )
    )

    lessons = list_lessons(limit=100000)
    sheets.append(
        (
            "上课记录",
            ["日期", "开始时间", "时长(分)", "等级", "课型", "类型", "人数", "课评", "教案"],
            [
                [
                    l["lesson_date"],
                    l["start_time"],
                    l["minutes"],
                    _level_text(l),
                    l["class_type_name"],
                    "补课" if l["kind"] == "补课" else "正常",
                    l["student_count"],
                    l["comment"],
                    l["plan"],
                ]
                for l in lessons
            ],
        )
    )

    rows = []
    for l in lessons:
        for a in list_attendance(l["id"]):
            rows.append(
                [
                    l["lesson_date"],
                    a["student_name"],
                    "到" if a["attendance"] else "请假",
                    "是" if a["discipline"] else "",
                    "是" if a["performance"] else "",
                    a["bonus"],
                    a["minutes"],
                    a["comment"],
                ]
            )
    sheets.append(
        ("点名明细", ["日期", "学员", "出勤", "纪律", "表现", "突出发挥", "时长(分)", "单独点评"], rows)
    )

    hour_rows = []
    point_rows = []
    for s in students:
        for t in list_hour_transactions(s["id"], limit=100000):
            source = t["source_type"] or "manual"
            kind = "缴费" if source.startswith("payment") else ("上课" if source == "lesson" else "手记")
            hour_rows.append(
                [
                    t["happened_on"],
                    s["name"],
                    t["hour_type_name"],
                    t["change"],
                    kind,
                    t["note"],
                ]
            )
        for t in list_point_transactions(s["id"], limit=100000):
            point_rows.append([t["happened_on"], s["name"], t["kind"], t["change"], t["note"]])
    sheets.append(("课时流水", ["日期", "学员", "账户", "变化", "来源", "备注"], hour_rows))
    sheets.append(("积分流水", ["日期", "学员", "类型", "变化", "备注"], point_rows))

    rows = []
    for p in list_payments(limit=100000):
        for item in list_payment_items(p["id"]):
            rows.append(
                [
                    p["paid_on"],
                    p["student_name"],
                    item["hour_type_name"],
                    item["hours"],
                    item["amount"],
                    "赠送" if not item["amount"] else "",
                    p["note"],
                ]
            )
    sheets.append(
        ("缴费记录", ["日期", "学员", "课时类型", "数量", "金额", "赠送", "备注"], rows)
    )

    sheets.append(
        (
            "试听记录",
            ["姓名", "年级", "家长", "电话", "来源", "状态", "试听日期", "备注", "是否转正"],
            [
                [
                    t["name"],
                    t["grade"],
                    t["parent_name"],
                    t["phone"],
                    t["source"],
                    t["status"],
                    t["trial_on"],
                    t["note"],
                    "已转正式" if t["student_id"] else "",
                ]
                for t in list_trials()
            ],
        )
    )

    rows = []
    for t in [*list_makeups("待补"), *list_makeups("已补"), *list_makeups("取消")]:
        rows.append(
            [
                t["student_name"],
                t["lesson_date"],
                t["class_type_name"],
                t["status"],
                t["makeup_date"] or "",
                t["note"],
            ]
        )
    sheets.append(("补课", ["学员", "请假日期", "课型", "状态", "补课日期", "备注"], rows))

    sheets.append(
        (
            "固定课表",
            ["星期", "时间", "时长(分)", "等级", "课型", "人数", "备注"],
            [
                [
                    f"周{'一二三四五六日'[int(t['weekday'])]}",
                    t["start_time"],
                    t["minutes"],
                    _level_text(t),
                    t["class_type_name"],
                    t["student_count"],
                    t["note"],
                ]
                for t in list_templates()
            ],
        )
    )
    return sheets


def create_payment(
    student_id: int,
    paid_on: str,
    items: list[dict],
    note: str = "",
) -> int:
    """一笔缴费：总金额由各行相加，行里 amount=0 就是赠送。"""
    clean = _clean_payment_items(items)
    if not clean:
        raise ValueError("至少要填一行课时")
    total = sum(i["amount"] for i in clean)
    first = clean[0]
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO payments
                   (student_id, paid_on, amount, hour_type_id, hours, note, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (
                student_id,
                paid_on or _today(),
                total,
                first["hour_type_id"],
                first["hours"],
                note,
                _today(),
            ),
        )
        payment_id = int(cur.lastrowid)
        for item in clean:
            con.execute(
                """INSERT INTO payment_items
                       (payment_id, hour_type_id, level_id, hours, amount, created_at)
                   VALUES(?, ?, ?, ?, ?, ?)""",
                (
                    payment_id,
                    item["hour_type_id"],
                    item["level_id"],
                    item["hours"],
                    item["amount"],
                    _today(),
                ),
            )
    sync_payment_hours(payment_id)
    sync_payment_enrollments(payment_id)
    recompute_student(student_id)
    return payment_id


def update_payment(
    payment_id: int,
    student_id: int,
    paid_on: str,
    items: list[dict],
    note: str = "",
) -> None:
    clean = _clean_payment_items(items)
    if not clean:
        raise ValueError("至少要填一行课时")
    total = sum(i["amount"] for i in clean)
    first = clean[0]
    with _connect() as con:
        # 顺序很重要：先清掉老流水，再删老的行
        _clear_payment_hours(con, payment_id)
        con.execute(
            """UPDATE payments
                  SET student_id = ?, paid_on = ?, amount = ?, hour_type_id = ?,
                      hours = ?, note = ?
                WHERE id = ?""",
            (
                student_id,
                paid_on or _today(),
                total,
                first["hour_type_id"],
                first["hours"],
                note,
                payment_id,
            ),
        )
        con.execute("DELETE FROM payment_items WHERE payment_id = ?", (payment_id,))
        for item in clean:
            con.execute(
                """INSERT INTO payment_items
                       (payment_id, hour_type_id, level_id, hours, amount, created_at)
                   VALUES(?, ?, ?, ?, ?, ?)""",
                (
                    payment_id,
                    item["hour_type_id"],
                    item["level_id"],
                    item["hours"],
                    item["amount"],
                    _today(),
                ),
            )
    sync_payment_hours(payment_id)
    sync_payment_enrollments(payment_id)
    recompute_student(student_id)


def _clean_payment_items(items: list[dict]) -> list[dict]:
    out = []
    for raw in items or []:
        hour_type_id = raw.get("hour_type_id")
        hours = float(raw.get("hours") or 0)
        amount = float(raw.get("amount") or 0)
        if not hour_type_id or hours <= 0:
            continue
        out.append(
            {
                "hour_type_id": int(hour_type_id),
                "level_id": int(raw["level_id"]) if raw.get("level_id") else None,
                "hours": hours,
                "amount": amount,
            }
        )
    return out


def _class_type_for_hour_type(con: sqlite3.Connection, hour_type_id: int) -> int | None:
    """课时账户对应哪个课型（社团 ↔ 校内社团）。"""
    row = con.execute(
        "SELECT name FROM hour_types WHERE id = ?", (hour_type_id,)
    ).fetchone()
    name = row["name"] if row else ""
    ct = con.execute("SELECT id FROM class_types WHERE name = ?", (name,)).fetchone()
    if ct is None and name == "社团":
        ct = con.execute(
            "SELECT id FROM class_types WHERE name = '校内社团'"
        ).fetchone()
    return int(ct["id"]) if ct else None


def sync_payment_enrollments(payment_id: int) -> None:
    """缴费里选过等级的课时，顺手把「报名课程」建好。"""
    with _connect() as con:
        payment = con.execute(
            "SELECT * FROM payments WHERE id = ?", (payment_id,)
        ).fetchone()
        if payment is None:
            return
        rows = con.execute(
            """SELECT pi.*, lv.default_minutes
                 FROM payment_items pi
                 LEFT JOIN levels lv ON lv.id = pi.level_id
                WHERE pi.payment_id = ? AND pi.level_id IS NOT NULL""",
            (payment_id,),
        ).fetchall()
        for item in rows:
            class_type_id = _class_type_for_hour_type(con, item["hour_type_id"])
            if class_type_id is None:
                continue
            exists = con.execute(
                """SELECT id FROM enrollments
                    WHERE student_id = ? AND class_type_id = ?
                      AND IFNULL(level_id, 0) = IFNULL(?, 0)""",
                (payment["student_id"], class_type_id, item["level_id"]),
            ).fetchone()
            if exists:
                continue
            con.execute(
                """INSERT INTO enrollments
                       (student_id, level_id, class_type_id, minutes, status, note, created_at)
                   VALUES(?, ?, ?, ?, '在读', '缴费时自动建', ?)""",
                (
                    payment["student_id"],
                    item["level_id"],
                    class_type_id,
                    int(item["default_minutes"] or 90),
                    _today(),
                ),
            )


def list_payment_items(payment_id: int) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            """SELECT pi.*, ht.name AS hour_type_name,
                      lv.subject AS subject, lv.name AS level_name
                 FROM payment_items pi
                 LEFT JOIN hour_types ht ON ht.id = pi.hour_type_id
                 LEFT JOIN levels lv ON lv.id = pi.level_id
                WHERE pi.payment_id = ?
                ORDER BY pi.id""",
            (payment_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def items_by_payment(payment_ids: list[int]) -> dict[int, list[dict]]:
    if not payment_ids:
        return {}
    marks = ",".join("?" * len(payment_ids))
    with _connect() as con:
        rows = con.execute(
            f"""SELECT pi.*, ht.name AS hour_type_name,
                       lv.subject AS subject, lv.name AS level_name
                  FROM payment_items pi
                  LEFT JOIN hour_types ht ON ht.id = pi.hour_type_id
                  LEFT JOIN levels lv ON lv.id = pi.level_id
                 WHERE pi.payment_id IN ({marks})
                 ORDER BY pi.id""",
            payment_ids,
        ).fetchall()
    out: dict[int, list[dict]] = {}
    for row in rows:
        out.setdefault(int(row["payment_id"]), []).append(dict(row))
    return out


def sync_payment_hours(payment_id: int) -> None:
    """缴费对应的课时流水：每一行课时一笔，跟着缴费一起改。"""
    with _connect() as con:
        payment = con.execute(
            "SELECT * FROM payments WHERE id = ?", (payment_id,)
        ).fetchone()
        _clear_payment_hours(con, payment_id)
        if payment is None:
            return
        rows = con.execute(
            "SELECT * FROM payment_items WHERE payment_id = ? ORDER BY id",
            (payment_id,),
        ).fetchall()
        for item in rows:
            if not item["hours"] or not item["hour_type_id"]:
                continue
            if item["amount"]:
                note = f"缴费 {_num(item['amount'])} 元"
            else:
                note = "赠送课时"
            if payment["note"]:
                note += f"（{payment['note']}）"
            con.execute(
                """INSERT INTO hour_transactions
                       (student_id, hour_type_id, change, kind, happened_on, note,
                        source_type, source_id, created_at)
                   VALUES(?, ?, ?, '缴费', ?, ?, 'payment_item', ?, ?)""",
                (
                    payment["student_id"],
                    item["hour_type_id"],
                    float(item["hours"]),
                    payment["paid_on"],
                    note,
                    item["id"],
                    _today(),
                ),
            )


def delete_payment(payment_id: int) -> None:
    with _connect() as con:
        row = con.execute(
            "SELECT student_id FROM payments WHERE id = ?", (payment_id,)
        ).fetchone()
        _clear_payment_hours(con, payment_id)
        con.execute("DELETE FROM payment_items WHERE payment_id = ?", (payment_id,))
        con.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
    if row is not None:
        recompute_student(int(row["student_id"]))


def _clear_payment_hours(con: sqlite3.Connection, payment_id: int) -> None:
    """把这笔缴费（含各行）产生的课时流水清掉。"""
    con.execute(
        """DELETE FROM hour_transactions
            WHERE (source_type = 'payment' AND source_id = ?)
               OR (source_type = 'payment_item' AND source_id IN
                   (SELECT id FROM payment_items WHERE payment_id = ?))""",
        (payment_id, payment_id),
    )


_PAYMENT_SELECT = """
    SELECT p.*, s.name AS student_name, ht.name AS hour_type_name
      FROM payments p
      JOIN students s ON s.id = p.student_id
      LEFT JOIN hour_types ht ON ht.id = p.hour_type_id
"""


def get_payment(payment_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute(_PAYMENT_SELECT + " WHERE p.id = ?", (payment_id,)).fetchone()
    return dict(row) if row else None


def list_payments(student_id: int | None = None, limit: int = 300) -> list[dict]:
    sql = _PAYMENT_SELECT
    args: list[Any] = []
    if student_id is not None:
        sql += " WHERE p.student_id = ?"
        args.append(student_id)
    sql += " ORDER BY p.paid_on DESC, p.id DESC LIMIT ?"
    args.append(limit)
    with _connect() as con:
        rows = con.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def income_total(student_id: int | None = None, month: str | None = None) -> float:
    """month 传 '2026-09' 就是那个月的收入。"""
    sql = "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE 1 = 1"
    args: list[Any] = []
    if student_id is not None:
        sql += " AND student_id = ?"
        args.append(student_id)
    if month:
        sql += " AND paid_on LIKE ?"
        args.append(f"{month}%")
    with _connect() as con:
        row = con.execute(sql, args).fetchone()
    return float(row["total"] or 0)
