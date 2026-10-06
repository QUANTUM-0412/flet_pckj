"""课时记录平台 —— 数据层。

所有数据存在 data/app.db 这一个文件里，备份的时候直接拷这个文件就行。
"""

from __future__ import annotations

import calendar
import hashlib
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
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

STUDENT_STATUS = ["在读", "停课"]
GENDER_OPTIONS = ["男", "女"]
GRADE_OPTIONS = ["一年级", "二年级", "三年级", "四年级", "五年级", "六年级", "初一", "初二", "初三"]
WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
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
    school      TEXT    NOT NULL DEFAULT '',
    phone       TEXT    NOT NULL DEFAULT '',
    note        TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT '在读',
    owner_teacher_id INTEGER REFERENCES users(id),
    created_at  TEXT    NOT NULL DEFAULT ''
);

-- 学校字典：下拉框里能挑的学校名（学员档案上填过的也会一起算进来）
CREATE TABLE IF NOT EXISTS schools (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT    NOT NULL UNIQUE
);

-- 一些内部标记（比如"默认字典已经初始化过了"）
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
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
    default_teacher_id INTEGER REFERENCES users(id),
    active          INTEGER NOT NULL DEFAULT 1,
    sort            INTEGER NOT NULL DEFAULT 0,
    UNIQUE(subject, name)
);

-- 报名：一个孩子报的一门课
CREATE TABLE IF NOT EXISTS enrollments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    level_id      INTEGER REFERENCES levels(id),
    class_type_id INTEGER NOT NULL REFERENCES class_types(id),
    class_id      INTEGER REFERENCES schedule_templates(id) ON DELETE SET NULL,
    minutes       INTEGER NOT NULL DEFAULT 90,
    status        TEXT    NOT NULL DEFAULT '在读',
    owner_teacher_id INTEGER REFERENCES users(id),
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
    teacher_id    INTEGER REFERENCES users(id),
    template_id   INTEGER REFERENCES schedule_templates(id) ON DELETE SET NULL,
    rolled        INTEGER NOT NULL DEFAULT 1,
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
    owner_teacher_id INTEGER REFERENCES users(id),
    created_at    TEXT    NOT NULL DEFAULT ''
);

-- 缴费：一笔钱买了哪种课时
-- 代金券：缴费正课送的一批券（一次 10 张，面额 = 正课金额 ÷ 10，24 个月有效），
-- 以后每次缴费最多用掉 1 张。放在 payments 前面建，好让外键指得着。
CREATE TABLE IF NOT EXISTS vouchers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    payment_id INTEGER REFERENCES payments(id) ON DELETE SET NULL,
    face       REAL    NOT NULL DEFAULT 0,
    count      INTEGER NOT NULL DEFAULT 0,
    issued_on  TEXT    NOT NULL DEFAULT '',
    expires_on TEXT    NOT NULL DEFAULT '',
    note       TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id   INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    paid_on      TEXT    NOT NULL,
    amount       REAL    NOT NULL DEFAULT 0,
    hour_type_id INTEGER REFERENCES hour_types(id),
    hours        REAL    NOT NULL DEFAULT 0,
    note         TEXT    NOT NULL DEFAULT '',
    voucher_id   INTEGER REFERENCES vouchers(id),
    voucher_amount REAL  NOT NULL DEFAULT 0,
    teacher_id   INTEGER REFERENCES users(id),
    created_at   TEXT    NOT NULL DEFAULT ''
);

-- 缴费里的每一行课时（正课 24 ＋ 赠送考级 1 ＋ 赠送竞赛 1 这种）
CREATE TABLE IF NOT EXISTS payment_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id   INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
    hour_type_id INTEGER REFERENCES hour_types(id),
    level_id     INTEGER REFERENCES levels(id),
    enrollment_id INTEGER REFERENCES enrollments(id) ON DELETE SET NULL,
    hours        REAL    NOT NULL DEFAULT 0,
    amount       REAL    NOT NULL DEFAULT 0,
    owner_teacher_id INTEGER REFERENCES users(id),
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
    school      TEXT    NOT NULL DEFAULT '',
    parent_name TEXT    NOT NULL DEFAULT '',
    phone       TEXT    NOT NULL DEFAULT '',
    source      TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT '待试听',
    trial_on    TEXT    NOT NULL DEFAULT '',
    note        TEXT    NOT NULL DEFAULT '',
    student_id  INTEGER REFERENCES students(id) ON DELETE SET NULL,
    owner_teacher_id INTEGER REFERENCES users(id),
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
    phone         TEXT    NOT NULL DEFAULT '',
    is_teacher    INTEGER NOT NULL DEFAULT 1,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS schedule_templates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL DEFAULT '',
    weekday       INTEGER NOT NULL DEFAULT 0,
    start_time    TEXT    NOT NULL DEFAULT '',
    minutes       INTEGER NOT NULL DEFAULT 90,
    class_type_id INTEGER NOT NULL REFERENCES class_types(id),
    level_id      INTEGER REFERENCES levels(id),
    teacher_id    INTEGER REFERENCES users(id),
    note          TEXT    NOT NULL DEFAULT '',
    active        INTEGER NOT NULL DEFAULT 1,
    start_date    TEXT    NOT NULL DEFAULT '',
    end_date      TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS schedule_students (
    template_id INTEGER NOT NULL REFERENCES schedule_templates(id) ON DELETE CASCADE,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    PRIMARY KEY (template_id, student_id)
);

-- 课程临时取消的日子（节假日、那天不上）：这几天不再出现在课表上
CREATE TABLE IF NOT EXISTS course_skips (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL REFERENCES schedule_templates(id) ON DELETE CASCADE,
    skip_date   TEXT    NOT NULL,
    note        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT '',
    UNIQUE(template_id, skip_date)
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
CREATE INDEX IF NOT EXISTS idx_course_skips ON course_skips(skip_date);
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
    # 课次是从哪张固定课表排出来的，以及"点过名没有"
    # （批量排出来的课先不点名，等真上课了再点，免得提前扣课时）
    if "template_id" not in lesson_columns:
        con.execute("ALTER TABLE lessons ADD COLUMN template_id INTEGER REFERENCES schedule_templates(id)")
    if "rolled" not in lesson_columns:
        con.execute("ALTER TABLE lessons ADD COLUMN rolled INTEGER NOT NULL DEFAULT 1")
    hour_columns = {r["name"] for r in con.execute("PRAGMA table_info(hour_types)")}
    template_columns = {r["name"] for r in con.execute("PRAGMA table_info(schedule_templates)")}
    if "start_date" not in template_columns:
        con.execute("ALTER TABLE schedule_templates ADD COLUMN start_date TEXT NOT NULL DEFAULT ''")
    if "end_date" not in template_columns:
        con.execute("ALTER TABLE schedule_templates ADD COLUMN end_date TEXT NOT NULL DEFAULT ''")
    pay_columns = {r["name"] for r in con.execute("PRAGMA table_info(payments)")}
    if "voucher_id" not in pay_columns:
        con.execute("ALTER TABLE payments ADD COLUMN voucher_id INTEGER REFERENCES vouchers(id)")
    if "voucher_amount" not in pay_columns:
        con.execute("ALTER TABLE payments ADD COLUMN voucher_amount REAL NOT NULL DEFAULT 0")
    if "warn" not in hour_columns:
        con.execute("ALTER TABLE hour_types ADD COLUMN warn INTEGER NOT NULL DEFAULT 0")
        # 默认只有正课提醒
        con.execute("UPDATE hour_types SET warn = 1 WHERE name = '正课'")
    # 学员档案加上"哪所小学"，试听记录也加一份，转正式的时候带过去
    for table in ("students", "trials"):
        table_columns = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        if "school" not in table_columns:
            con.execute(f"ALTER TABLE {table} ADD COLUMN school TEXT NOT NULL DEFAULT ''")
    # 老数据里年级写的是 "1"、"2"，统一成"一年级"这种写法
    for digit, han in zip("123456", "一二三四五六"):
        con.execute("UPDATE students SET grade = ? WHERE grade = ?", (f"{han}年级", digit))
        con.execute("UPDATE trials SET grade = ? WHERE grade = ?", (f"{han}年级", digit))
    # 学员档案不再有"结课"（容易和课程的结课混淆）：老数据归回"在读"
    con.execute("UPDATE students SET status = '在读' WHERE status = '结课'")
    # 监护人姓名
    _ensure_column(con, "students", "guardian", "TEXT NOT NULL DEFAULT ''")
    # 归属老师是不是手动钉住的（钉住以后不再跟着缴费自动变）
    _ensure_column(con, "students", "owner_manual", "INTEGER NOT NULL DEFAULT 0")
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
    # ---- 老师与归属：老库补字段（新库在 SCHEMA 里已经有了）
    _ensure_column(con, "users", "phone", "TEXT NOT NULL DEFAULT ''")
    if _ensure_column(con, "users", "is_teacher", "INTEGER NOT NULL DEFAULT 1"):
        # 老库里的管理员不一定是上课老师，先不列进"归属老师"下拉，需要的话在设置里勾上
        con.execute("UPDATE users SET is_teacher = 0 WHERE role = 'root'")
    _ensure_column(con, "students", "owner_teacher_id", "INTEGER REFERENCES users(id)")
    _ensure_column(con, "levels", "default_teacher_id", "INTEGER REFERENCES users(id)")
    _ensure_column(con, "enrollments", "owner_teacher_id", "INTEGER REFERENCES users(id)")
    _ensure_column(con, "lessons", "teacher_id", "INTEGER REFERENCES users(id)")
    _ensure_column(con, "attendance", "owner_teacher_id", "INTEGER REFERENCES users(id)")
    _ensure_column(con, "payments", "teacher_id", "INTEGER REFERENCES users(id)")
    _ensure_column(con, "payment_items", "owner_teacher_id", "INTEGER REFERENCES users(id)")
    _ensure_column(con, "trials", "owner_teacher_id", "INTEGER REFERENCES users(id)")
    _ensure_column(con, "schedule_templates", "teacher_id", "INTEGER REFERENCES users(id)")
    # ---- 班级：固定课表升级成正式班级，报名挂到班级上
    _ensure_column(con, "schedule_templates", "name", "TEXT NOT NULL DEFAULT ''")
    # 等级可以"停用"：不再出现在新建课程／报名／缴费的下拉里，老记录照旧
    _ensure_column(con, "levels", "active", "INTEGER NOT NULL DEFAULT 1")
    # 课程名的规范字段：年份-学期-等级-Cls-序号
    _ensure_column(con, "schedule_templates", "year", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(con, "schedule_templates", "term", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(con, "schedule_templates", "seq", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "enrollments", "class_id", "INTEGER REFERENCES schedule_templates(id)")
    _ensure_column(
        con, "payment_items", "enrollment_id", "INTEGER REFERENCES enrollments(id)"
    )
    _ensure_column(
        con, "enrollments", "auto_finished", "INTEGER NOT NULL DEFAULT 0"
    )
    # 索引要等字段补好再建（老库里这些列刚加上）
    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_enroll_owner ON enrollments(owner_teacher_id)",
        "CREATE INDEX IF NOT EXISTS idx_enroll_class ON enrollments(class_id)",
        "CREATE INDEX IF NOT EXISTS idx_lesson_teacher ON lessons(teacher_id)",
        "CREATE INDEX IF NOT EXISTS idx_att_owner ON attendance(owner_teacher_id)",
        "CREATE INDEX IF NOT EXISTS idx_pay_teacher ON payments(teacher_id)",
        "CREATE INDEX IF NOT EXISTS idx_payitem_owner ON payment_items(owner_teacher_id)",
        "CREATE INDEX IF NOT EXISTS idx_payitem_enroll ON payment_items(enrollment_id)",
        "CREATE INDEX IF NOT EXISTS idx_trials_owner ON trials(owner_teacher_id)",
    ):
        con.execute(statement)
    # 课程名唯一（空名字的老课程不算，等管理员起名）
    try:
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_course_name "
            "ON schedule_templates(name) WHERE name <> ''"
        )
    except sqlite3.IntegrityError:
        # 老数据里有重名，先跳过；到设置里改名时会挡重名
        pass
    _backfill_course_name_parts(con)
    backfill_teacher_attribution(con)
    backfill_enrollment_classes(con)
    # 学员的总体状态跟着课程走（有在读就是在读）
    for row in con.execute("SELECT DISTINCT student_id FROM enrollments").fetchall():
        refresh_student(int(row["student_id"]), con)
    # 过了结课日的课程，报名自动结课
    sync_course_statuses(con)


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}


def _ensure_column(con: sqlite3.Connection, table: str, column: str, decl: str) -> bool:
    """表里没有这一列就加上；返回是不是这次新加的。"""
    if column in _columns(con, table):
        return False
    con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    return True


def backfill_teacher_attribution(con: sqlite3.Connection | None = None) -> int:
    """把还没指定归属老师的老记录，按「报名 → 学员默认 → 课程默认」补上。

    只补空的，不动已经指定过的（历史归属一旦定了就不重算）。
    返回补了多少条。设置页的「按课程默认值补全归属」按钮也调它。
    """

    def run(c: sqlite3.Connection) -> int:
        changed = 0
        # 报名：先看课程默认老师，再看学员默认老师
        rows = c.execute(
            """SELECT e.id, s.owner_teacher_id AS student_owner,
                      l.default_teacher_id AS level_owner
                 FROM enrollments e
                 JOIN students s ON s.id = e.student_id
                 LEFT JOIN levels l ON l.id = e.level_id
                WHERE e.owner_teacher_id IS NULL"""
        ).fetchall()
        for r in rows:
            owner = r["level_owner"] or r["student_owner"]
            if owner:
                c.execute(
                    "UPDATE enrollments SET owner_teacher_id = ? WHERE id = ?", (owner, r["id"])
                )
                changed += 1
        # 点名：报名归属 → 学员默认
        rows = c.execute(
            """SELECT a.id,
                      (SELECT e.owner_teacher_id FROM enrollments e
                        WHERE e.id = a.enrollment_id) AS enroll_owner,
                      (SELECT l.default_teacher_id FROM levels l
                        WHERE l.id = (SELECT e2.level_id FROM enrollments e2
                                       WHERE e2.id = a.enrollment_id)) AS level_owner,
                      (SELECT s.owner_teacher_id FROM students s
                        WHERE s.id = a.student_id) AS student_owner
                 FROM attendance a
                WHERE a.owner_teacher_id IS NULL"""
        ).fetchall()
        for r in rows:
            owner = r["enroll_owner"] or r["level_owner"] or r["student_owner"]
            if owner:
                c.execute(
                    "UPDATE attendance SET owner_teacher_id = ? WHERE id = ?", (owner, r["id"])
                )
                changed += 1
        # 缴费行：同级别的报名归属 → 学员默认 → 课程默认
        rows = c.execute(
            """SELECT pi.id, pi.level_id, p.student_id,
                      (SELECT s.owner_teacher_id FROM students s
                        WHERE s.id = p.student_id) AS student_owner,
                      (SELECT l.default_teacher_id FROM levels l
                        WHERE l.id = pi.level_id) AS level_owner
                 FROM payment_items pi
                 JOIN payments p ON p.id = pi.payment_id
                WHERE pi.owner_teacher_id IS NULL"""
        ).fetchall()
        for r in rows:
            enroll = c.execute(
                """SELECT owner_teacher_id FROM enrollments
                    WHERE student_id = ? AND IFNULL(level_id, 0) = IFNULL(?, 0)
                      AND owner_teacher_id IS NOT NULL
                    LIMIT 1""",
                (r["student_id"], r["level_id"]),
            ).fetchone()
            owner = (
                (enroll["owner_teacher_id"] if enroll else None)
                or r["level_owner"]
                or r["student_owner"]
            )
            if owner:
                c.execute(
                    "UPDATE payment_items SET owner_teacher_id = ? WHERE id = ?",
                    (owner, r["id"]),
                )
                changed += 1
        # 缴费主表：一整笔都是同一个老师就写上；跨老师（混合）就留空
        for p in c.execute("SELECT id FROM payments").fetchall():
            owners = {
                row["owner_teacher_id"]
                for row in c.execute(
                    """SELECT owner_teacher_id FROM payment_items
                        WHERE payment_id = ? AND owner_teacher_id IS NOT NULL""",
                    (p["id"],),
                )
            }
            value = owners.pop() if len(owners) == 1 else None
            c.execute("UPDATE payments SET teacher_id = ? WHERE id = ?", (value, p["id"]))
        return changed

    if con is not None:
        return run(con)
    with _connect() as c:
        return run(c)


def backfill_lesson_teachers() -> int:
    """给还没填「上课老师」的老课次补上（只补空的，不动已经填过的）。

    这是算**课时费**的老师，不是"谁的客户"。优先按：
    这节课所属课程的老师 → 这门等级的默认老师 → 最后才看学生归属。
    返回补了几节课。
    """
    changed = 0
    with _connect() as con:
        lessons = con.execute(
            """SELECT l.id, l.level_id,
                      (SELECT lv.default_teacher_id FROM levels lv
                        WHERE lv.id = l.level_id) AS level_teacher,
                      (SELECT t.teacher_id FROM schedule_templates t
                        WHERE t.id = l.template_id) AS course_teacher
                 FROM lessons l
                WHERE l.teacher_id IS NULL"""
        ).fetchall()
        for lesson in lessons:
            teacher = lesson["course_teacher"] or lesson["level_teacher"]
            if not teacher:
                owners = [
                    row["owner_teacher_id"]
                    for row in con.execute(
                        """SELECT DISTINCT owner_teacher_id FROM attendance
                            WHERE lesson_id = ? AND owner_teacher_id IS NOT NULL""",
                        (lesson["id"],),
                    )
                ]
                teacher = owners[0] if len(owners) == 1 else None
            if teacher:
                con.execute(
                    "UPDATE lessons SET teacher_id = ? WHERE id = ?",
                    (teacher, lesson["id"]),
                )
                changed += 1
    return changed


_COURSE_NAME_RE = re.compile(r"^\s*(\d{4})\s*-\s*(\d+)\s*-(.*?)-\s*Cls\s*-?\s*(\d+)\s*$")
_COURSE_PREFIX_RE = re.compile(r"^\s*(\d{4})\s*-\s*(\d+)\s*-")


def parse_course_name(name: str) -> dict:
    """把 2026-2-STEM-Lvl-02-Cls-01 拆成 年份／学期／等级／序号。"""
    m = _COURSE_NAME_RE.match(name or "")
    if not m:
        return {}
    return {
        "year": m.group(1),
        "term": m.group(2),
        "level_text": (m.group(3) or "").strip(),
        "seq": int(m.group(4)),
    }


def make_course_name(year: str, term: str, level_text: str, seq: int) -> str:
    """课程名的规范写法：2026-2-STEM-Lvl-02-Cls-01。"""
    return (
        f"{(year or '').strip()}-{(term or '').strip()}-"
        f"{(level_text or '').strip()}-Cls-{int(seq or 1):02d}"
    )


def _backfill_course_name_parts(con: sqlite3.Connection) -> int:
    """从老课程名里把 年份／学期／序号 拆出来存好；没有序号的按顺序补。"""
    rows = con.execute(
        """SELECT id, name, year, term, seq, level_id FROM schedule_templates
            ORDER BY id"""
    ).fetchall()
    parsed: list[tuple[sqlite3.Row, str, str, int]] = []
    for row in rows:
        info = parse_course_name(row["name"] or "")
        prefix = _COURSE_PREFIX_RE.match(row["name"] or "")
        year = (row["year"] or info.get("year") or (prefix.group(1) if prefix else "")).strip()
        term = (row["term"] or info.get("term") or (prefix.group(2) if prefix else "")).strip()
        seq = int(row["seq"] or 0) or int(info.get("seq") or 0)
        parsed.append((row, year, term, seq))
    used: dict[tuple[str, str, object], set[int]] = {}
    for row, year, term, seq in parsed:
        if seq:
            used.setdefault((year, term, row["level_id"]), set()).add(seq)
    changed = 0
    for row, year, term, seq in parsed:
        key = (year, term, row["level_id"])
        if not seq:
            seq = 1
            while seq in used.get(key, set()):
                seq += 1
            used.setdefault(key, set()).add(seq)
        if (row["year"], row["term"], int(row["seq"] or 0)) != (year, term, seq):
            con.execute(
                "UPDATE schedule_templates SET year = ?, term = ?, seq = ? WHERE id = ?",
                (year, term, seq, row["id"]),
            )
            changed += 1
    return changed


def next_course_seq(
    year: str, term: str, level_id: int | None, exclude_id: int | None = None
) -> int:
    """同一个 年份＋学期＋等级 里，下一个班级序号（Cls-01、Cls-02…）。"""
    with _connect() as con:
        row = con.execute(
            """SELECT COALESCE(MAX(seq), 0) AS m FROM schedule_templates
                WHERE year = ? AND term = ?
                  AND IFNULL(level_id, 0) = IFNULL(?, 0)
                  AND id <> ?""",
            (
                (year or "").strip(),
                (term or "").strip(),
                level_id,
                int(exclude_id or 0),
            ),
        ).fetchone()
    return int(row["m"] or 0) + 1


def normalize_course_names() -> int:
    """把现有课程名统一成 年份-学期-等级-Cls-序号。返回改了几门。"""
    changed = 0
    with _connect() as con:
        _backfill_course_name_parts(con)
        rows = con.execute(
            """SELECT t.*, l.subject, l.name AS level_name
                 FROM schedule_templates t
                 LEFT JOIN levels l ON l.id = t.level_id
                ORDER BY t.id"""
        ).fetchall()
        taken = {
            r["name"]
            for r in con.execute(
                "SELECT name FROM schedule_templates WHERE name <> ''"
            )
        }
        for row in rows:
            subject = (row["subject"] or "").strip()
            level_name = (row["level_name"] or "").strip()
            level_text = f"{subject}-{level_name}" if subject else level_name
            if not (row["year"] and row["term"] and level_text and row["seq"]):
                continue
            seq = int(row["seq"])
            new_name = make_course_name(row["year"], row["term"], level_text, seq)
            while new_name in taken and new_name != row["name"]:
                seq += 1
                new_name = make_course_name(row["year"], row["term"], level_text, seq)
            if new_name == row["name"] and seq == int(row["seq"]):
                continue
            con.execute(
                "UPDATE schedule_templates SET name = ?, seq = ? WHERE id = ?",
                (new_name, seq, row["id"]),
            )
            taken.discard(row["name"])
            taken.add(new_name)
            changed += 1
    return changed


def weekday_text(weekday) -> str:
    """星期几的文字：0-6 是周一到周日，-1（或空的）是"时间不定"。"""
    try:
        w = int(weekday)
    except (TypeError, ValueError):
        return "时间不定"
    if 0 <= w <= 6:
        return f"每{WEEKDAY_NAMES[w]}"
    return "时间不定"


def class_label(row: dict | sqlite3.Row) -> str:
    """班级的显示名：起了名字用名字，没起就用"周几 时间 等级"拼一个。"""
    data = dict(row)
    name = (data.get("name") or "").strip()
    if name:
        return name
    bits = []
    weekday = data.get("weekday")
    if weekday is not None and 0 <= int(weekday) <= 6:
        bits.append(WEEKDAY_NAMES[int(weekday)])
    if (data.get("start_time") or "").strip():
        bits.append(data["start_time"].strip())
    subject = (data.get("subject") or "").strip()
    level = (data.get("level_name") or "").strip()
    if subject or level:
        bits.append(f"{subject}-{level}" if subject else level)
    return " ".join(bits) or (f"班级 {data.get('id')}" if data.get("id") else "")


def backfill_enrollment_classes(con: sqlite3.Connection | None = None) -> int:
    """老报名按"这个孩子在哪个班"补上班级链接。

    同一个等级／课型要是命中好几个班（或者一个都没命中），就不乱猜，留着让管理员自己选。
    """

    def run(c: sqlite3.Connection) -> int:
        changed = 0
        rows = c.execute(
            """SELECT id, student_id, level_id, class_type_id, owner_teacher_id
                 FROM enrollments WHERE class_id IS NULL"""
        ).fetchall()
        for e in rows:
            matches = c.execute(
                """SELECT t.id, t.teacher_id
                     FROM schedule_students ss
                     JOIN schedule_templates t ON t.id = ss.template_id
                    WHERE ss.student_id = ?
                      AND IFNULL(t.level_id, 0) = IFNULL(?, 0)
                      AND t.class_type_id = ?
                    ORDER BY t.active DESC, t.id""",
                (e["student_id"], e["level_id"], e["class_type_id"]),
            ).fetchall()
            if len(matches) != 1:
                continue
            match = matches[0]
            c.execute(
                "UPDATE enrollments SET class_id = ? WHERE id = ?", (match["id"], e["id"])
            )
            if match["teacher_id"] and not e["owner_teacher_id"]:
                c.execute(
                    "UPDATE enrollments SET owner_teacher_id = ? WHERE id = ?",
                    (match["teacher_id"], e["id"]),
                )
            changed += 1
        return changed

    if con is not None:
        return run(con)
    with _connect() as c:
        return run(c)


def enrollment_class_label(enrollment: dict) -> str:
    """一条报名挂在哪个班上（没挂班就返回空）。"""
    if not enrollment.get("class_id"):
        return ""
    return class_label(
        {
            "name": enrollment.get("class_name"),
            "weekday": enrollment.get("class_weekday"),
            "start_time": enrollment.get("class_start_time"),
            "subject": enrollment.get("subject"),
            "level_name": enrollment.get("level_name"),
            "id": enrollment.get("class_id"),
        }
    )


def course_status(row: dict | sqlite3.Row) -> str:
    """课程的状态：还没到开课日=未开课；过了结课日=已结课；中间=在读。"""
    data = dict(row)
    today = _today()
    start = (data.get("start_date") or "").strip()
    end = (data.get("end_date") or "").strip()
    if end and end < today:
        return "已结课"
    if start and start > today:
        return "未开课"
    return "在读"


def _apply_course_dates(con: sqlite3.Connection, course_id: int) -> int:
    """按课程的起止日期，把挂在它下面的报名状态同步一下。

    过了结课日 → 这些报名自动变「结课」（记 auto_finished=1）；
    结课日改回未来／清空 → 把系统自动结课的改回「在读」，手动结课的不动。
    """
    course = con.execute(
        "SELECT * FROM schedule_templates WHERE id = ?", (course_id,)
    ).fetchone()
    if course is None:
        return 0
    end = (course["end_date"] or "").strip()
    today = _today()
    changed = 0
    if end and end < today:
        cur = con.execute(
            """UPDATE enrollments SET status = '结课', auto_finished = 1
                WHERE class_id = ? AND status <> '结课'""",
            (course_id,),
        )
        changed += int(cur.rowcount or 0)
    else:
        cur = con.execute(
            """UPDATE enrollments SET status = '在读', auto_finished = 0
                WHERE class_id = ? AND auto_finished = 1""",
            (course_id,),
        )
        changed += int(cur.rowcount or 0)
    if changed:
        for row in con.execute(
            "SELECT DISTINCT student_id FROM enrollments WHERE class_id = ?", (course_id,)
        ):
            refresh_student(int(row["student_id"]), con)
    return changed


def sync_course_statuses(con: sqlite3.Connection | None = None) -> int:
    """把所有课程的起止日期过一遍，到期就自动结课。"""

    def run(c: sqlite3.Connection) -> int:
        changed = 0
        for row in c.execute("SELECT id FROM schedule_templates").fetchall():
            changed += _apply_course_dates(c, int(row["id"]))
        return changed

    if con is not None:
        return run(con)
    with _connect() as c:
        return run(c)


def lesson_class_label(lesson: dict) -> str:
    """这节课属于哪个班（不是从班里排出来的课就返回空）。"""
    if not lesson.get("template_id"):
        return ""
    return class_label(
        {
            "name": lesson.get("class_name"),
            "weekday": lesson.get("class_weekday"),
            "start_time": lesson.get("class_start_time"),
            "subject": lesson.get("subject"),
            "level_name": lesson.get("level_name"),
            "id": lesson.get("template_id"),
        }
    )


def recompute_student_status(
    student_id: int, con: sqlite3.Connection | None = None
) -> None:
    """学员的总体状态跟着报名课程走：有在读就是在读，全结课才是结课。

    这样"一门课结课、另一门还在读"的孩子，列表里还是"在读"，
    具体哪门结课了看他的报名课程。没填过报名的孩子，手填的状态不动。
    """

    def run(c: sqlite3.Connection) -> None:
        row = c.execute(
            "SELECT status FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        if row is None:
            return
        statuses = [
            r["status"]
            for r in c.execute(
                "SELECT status FROM enrollments WHERE student_id = ?", (student_id,)
            )
        ]
        if not statuses:
            return
        if "在读" in statuses:
            new_status = "在读"
        elif "停课" in statuses:
            new_status = "停课"
        else:
            # 所有课程都结课了也不改学员状态（"结课"只在课程上，避免混淆）
            return
        if new_status != row["status"]:
            c.execute(
                "UPDATE students SET status = ? WHERE id = ?", (new_status, student_id)
            )

    if con is not None:
        run(con)
        return
    with _connect() as c:
        run(c)


_OWNER_FROM_PAYMENT = "缴费"
_OWNER_FROM_COURSE = "课程"


def _student_owner_rows(con: sqlite3.Connection, student_id: int) -> list[sqlite3.Row]:
    """这个学员的归属老师是哪几位，按来源排。

    首选**缴费的归属**（谁收的这笔钱，这个客户就归谁；最近交的排前面）；
    还没交过费，就退回看报名／课程的归属。
    """
    rows = con.execute(
        """SELECT pi.owner_teacher_id AS tid, MAX(p.paid_on) AS last_on
             FROM payment_items pi
             JOIN payments p ON p.id = pi.payment_id
            WHERE p.student_id = ? AND pi.owner_teacher_id IS NOT NULL
            GROUP BY pi.owner_teacher_id
            ORDER BY last_on DESC, tid""",
        (student_id,),
    ).fetchall()
    if rows:
        return rows
    return con.execute(
        """SELECT owner_teacher_id AS tid, MAX(COALESCE(created_at, '')) AS last_on
             FROM enrollments
            WHERE student_id = ? AND owner_teacher_id IS NOT NULL
            GROUP BY owner_teacher_id
            ORDER BY last_on DESC, tid""",
        (student_id,),
    ).fetchall()


def student_owners(student_id: int) -> list[dict]:
    """学员的归属老师（谁的客户），带上是按缴费还是按课程算的。"""
    with _connect() as con:
        me = con.execute(
            "SELECT owner_teacher_id, owner_manual FROM students WHERE id = ?",
            (student_id,),
        ).fetchone()
        if me is not None and int(me["owner_manual"] or 0):
            if not me["owner_teacher_id"]:
                return []
            info = con.execute(
                "SELECT id, display_name, username FROM users WHERE id = ?",
                (me["owner_teacher_id"],),
            ).fetchone()
            return [
                {
                    "teacher_id": int(me["owner_teacher_id"]),
                    "name": (info["display_name"] or info["username"]) if info else "",
                    "source": "手动",
                    "last_on": "",
                }
            ]
        rows = _student_owner_rows(con, student_id)
        from_payment = bool(
            con.execute(
                """SELECT 1 FROM payment_items pi
                    JOIN payments p ON p.id = pi.payment_id
                   WHERE p.student_id = ? AND pi.owner_teacher_id IS NOT NULL
                   LIMIT 1""",
                (student_id,),
            ).fetchone()
        )
        names = {
            int(r["id"]): (r["display_name"] or r["username"] or "")
            for r in con.execute("SELECT id, display_name, username FROM users")
        }
    return [
        {
            "teacher_id": int(r["tid"]),
            "name": names.get(int(r["tid"]), ""),
            "source": _OWNER_FROM_PAYMENT if from_payment else _OWNER_FROM_COURSE,
            "last_on": r["last_on"] or "",
        }
        for r in rows
    ]


def sync_student_owner(
    student_id: int, con: sqlite3.Connection | None = None
) -> None:
    """学员档案上的归属老师：跟着缴费的归属走（还没交过费就看课程）。

    一节课是谁上的，记在上课老师上（那个老师拿课时费），跟这个归属是两回事。
    """

    def run(c: sqlite3.Connection) -> None:
        # 手动钉住的归属老师不动它
        student = c.execute(
            "SELECT owner_manual FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        if student is not None and int(student["owner_manual"] or 0):
            return
        rows = _student_owner_rows(c, student_id)
        if rows:
            c.execute(
                "UPDATE students SET owner_teacher_id = ? WHERE id = ?",
                (int(rows[0]["tid"]), student_id),
            )

    if con is not None:
        run(con)
        return
    with _connect() as c:
        run(c)
def refresh_student(
    student_id: int, con: sqlite3.Connection | None = None
) -> None:
    """报名／课程变过以后，把学员的总体状态和归属老师重算一遍。"""
    recompute_student_status(student_id, con)
    sync_student_owner(student_id, con)


def _seed(con: sqlite3.Connection) -> None:
    # 默认的课时账户／课型／等级只在**第一次建库**时写一次。
    # 以前每次启动都补一遍，导致删掉的默认等级一重启又长回来。
    if con.execute("SELECT 1 FROM meta WHERE key = 'seeded'").fetchone() is not None:
        return
    has_data = any(
        int(con.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"] or 0)
        for table in ("hour_types", "class_types", "levels")
    )
    if has_data:
        # 老库本来就有数据，说明早就初始化过了：直接打个标记，不再补默认值
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('seeded', '1')")
        return
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
    con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('seeded', '1')")


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
                   (username, password_hash, salt, display_name, role, is_teacher, created_at)
               VALUES(?, ?, ?, ?, 'root', 0, ?)""",
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


def list_teachers(active_only: bool = True) -> list[dict]:
    """能当「归属老师／上课老师」的人：账号里勾了"上课老师"的。

    查询历史记录时要显示已经停用的老师，所以留了 active_only=False。
    """
    sql = "SELECT * FROM users WHERE is_teacher = 1"
    if active_only:
        sql += " AND active = 1"
    sql += " ORDER BY CASE role WHEN 'teacher' THEN 0 ELSE 1 END, id"
    with _connect() as con:
        rows = con.execute(sql).fetchall()
    return [dict(r) for r in rows]


def teacher_name_map() -> dict[int, str]:
    """id → 老师显示名（含已停用的，用来显示老记录上的名字）。"""
    with _connect() as con:
        rows = con.execute("SELECT id, display_name, username FROM users").fetchall()
    return {int(r["id"]): (r["display_name"] or r["username"] or "") for r in rows}


def create_user(
    username: str,
    password: str,
    display_name: str = "",
    role: str = ROLE_TEACHER,
    phone: str = "",
    is_teacher: bool | None = None,
) -> int:
    username = (username or "").strip()
    if not username:
        raise ValueError("用户名不能为空")
    if not password:
        raise ValueError("密码不能为空")
    role = role if role in ROLE_NAMES else ROLE_TEACHER
    if is_teacher is None:
        is_teacher = role == ROLE_TEACHER
    salt = secrets.token_hex(8)
    with _connect() as con:
        exists = con.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if exists:
            raise ValueError("这个用户名已经有了")
        cur = con.execute(
            """INSERT INTO users
                   (username, password_hash, salt, display_name, role, phone,
                    is_teacher, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                username,
                _hash_password(password, salt),
                salt,
                display_name or username,
                role,
                (phone or "").strip(),
                1 if is_teacher else 0,
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


def update_user(
    user_id: int,
    display_name: str,
    role: str,
    active: bool,
    phone: str = "",
    is_teacher: bool | None = None,
) -> None:
    role = role if role in ROLE_NAMES else ROLE_TEACHER
    with _connect() as con:
        current = con.execute(
            "SELECT is_teacher FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if is_teacher is None:
            is_teacher = bool(current["is_teacher"]) if current else True
        if role != ROLE_ROOT or not active:
            roots = con.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = 'root' AND active = 1 AND id != ?",
                (user_id,),
            ).fetchone()
            if int(roots["c"] or 0) == 0:
                raise ValueError("至少要留一个能用的管理员")
        con.execute(
            """UPDATE users
                  SET display_name = ?, role = ?, active = ?, phone = ?, is_teacher = ?
                WHERE id = ?""",
            (
                display_name,
                role,
                1 if active else 0,
                (phone or "").strip(),
                1 if is_teacher else 0,
                user_id,
            ),
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
        # 有记录的老师不能删（报名／缴费／课次都指着他），改成停用就行
        used = 0
        for table, column in (
            ("enrollments", "owner_teacher_id"),
            ("attendance", "owner_teacher_id"),
            ("lessons", "teacher_id"),
            ("payments", "teacher_id"),
            ("payment_items", "owner_teacher_id"),
            ("trials", "owner_teacher_id"),
            ("schedule_templates", "teacher_id"),
            ("students", "owner_teacher_id"),
            ("levels", "default_teacher_id"),
        ):
            count = con.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE {column} = ?", (user_id,)
            ).fetchone()
            used += int(count["c"] or 0)
        if used:
            raise ValueError(
                f"这位老师名下有 {used} 条记录（报名、缴费、课次等），不能删。"
                "把他「停用」就不会再出现在新的下拉里，以前的记录还留着。"
            )
        con.execute("DELETE FROM users WHERE id = ?", (user_id,))


def list_students(
    keyword: str = "",
    status: str = "",
    grade: str = "",
    school: str = "",
    owner: str = "",
) -> list[sqlite3.Row]:
    # keyword 是全字段模糊搜；grade／school／owner 是下拉筛选项。
    # owner 传 "" 是全部、"__none__" 是还没定归属、其它是老师 id。
    sql = "SELECT * FROM students WHERE 1 = 1"
    args: list[Any] = []
    if keyword:
        like = f"%{keyword}%"
        sql += " AND (name LIKE ? OR grade LIKE ? OR school LIKE ? OR phone LIKE ? OR note LIKE ?)"
        args += [like, like, like, like, like]
    if (grade or "").strip():
        sql += " AND grade = ?"
        args.append(grade.strip())
    if (school or "").strip():
        sql += " AND school = ?"
        args.append(school.strip())
    owner = (owner or "").strip()
    if owner == "__none__":
        sql += " AND owner_teacher_id IS NULL"
    elif owner:
        sql += " AND owner_teacher_id = ?"
        args.append(int(owner))
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY CASE status WHEN '在读' THEN 0 ELSE 1 END, name"
    with _connect() as con:
        return list(con.execute(sql, args))


def list_schools() -> list[str]:
    """学校下拉里的候选：学校字典 ＋ 学员／试听记录上填过的名字。"""
    with _connect() as con:
        rows = con.execute(
            """SELECT name FROM schools WHERE name <> ''
               UNION SELECT school FROM students WHERE school <> ''
               UNION SELECT school FROM trials WHERE school <> ''
               ORDER BY 1"""
        ).fetchall()
    return [r["name"] for r in rows]


def school_rows() -> list[dict]:
    """设置页用：每个学校叫什么、有几个学员／试听记录在用。

    `id` 只有字典里有的才有；学员档案上填过、没进字典的名字 id 是 None。
    """
    with _connect() as con:
        ids = {r["name"]: int(r["id"]) for r in con.execute("SELECT id, name FROM schools")}
        used: dict[str, int] = {}
        for table in ("students", "trials"):
            for row in con.execute(
                f"SELECT school, COUNT(*) AS c FROM {table} WHERE school <> '' GROUP BY school"
            ):
                used[row["school"]] = used.get(row["school"], 0) + int(row["c"])
    names = sorted(set(ids) | set(used))
    return [{"id": ids.get(n), "name": n, "used": used.get(n, 0)} for n in names]


def add_school(name: str) -> None:
    """往学校字典里加一个（已经有的就跳过）。"""
    text = (name or "").strip()
    if not text:
        raise ValueError("学校名不能为空")
    with _connect() as con:
        con.execute("INSERT OR IGNORE INTO schools(name) VALUES(?)", (text,))


def delete_school(school_id: int) -> None:
    with _connect() as con:
        con.execute("DELETE FROM schools WHERE id = ?", (school_id,))


def list_students_with_summary(
    keyword: str = "",
    status: str = "",
    grade: str = "",
    school: str = "",
    owner: str = "",
) -> list[dict]:
    out = []
    for row in list_students(
        keyword=keyword,
        status=status,
        grade=grade,
        school=school,
        owner=owner,
    ):
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
    owner = data.get("owner_teacher_id")
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO students
                   (name, gender, grade, school, phone, guardian, note, status,
                    owner_teacher_id, owner_manual, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                data.get("gender", ""),
                data.get("grade", ""),
                data.get("school", ""),
                data.get("phone", ""),
                data.get("guardian", ""),
                data.get("note", ""),
                data.get("status") or "在读",
                int(owner) if owner else None,
                1 if data.get("owner_manual") else 0,
                _today(),
            ),
        )
        return int(cur.lastrowid)


def update_student(student_id: int, data: dict) -> None:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("姓名不能为空")
    with _connect() as con:
        # 归属老师现在是跟着课程算的，表单里不再填；没传就别动它
        if "owner_teacher_id" in data:
            owner = data.get("owner_teacher_id")
            manual = 1 if data.get("owner_manual") else 0
        else:
            current = con.execute(
                "SELECT owner_teacher_id, owner_manual FROM students WHERE id = ?",
                (student_id,),
            ).fetchone()
            owner = current["owner_teacher_id"] if current is not None else None
            manual = int(current["owner_manual"] or 0) if current is not None else 0
        con.execute(
            """UPDATE students
                  SET name = ?, gender = ?, grade = ?, school = ?, phone = ?,
                      guardian = ?, note = ?, status = ?, owner_teacher_id = ?,
                      owner_manual = ?
                WHERE id = ?""",
            (
                name,
                data.get("gender", ""),
                data.get("grade", ""),
                data.get("school", ""),
                data.get("phone", ""),
                data.get("guardian", ""),
                data.get("note", ""),
                data.get("status") or "在读",
                int(owner) if owner else None,
                manual,
                student_id,
            ),
        )
    if "owner_teacher_id" in data and not manual:
        # 选回"跟缴费走（自动）"：立刻按缴费重新算一次
        sync_student_owner(student_id)


def delete_student(student_id: int) -> None:
    with _connect() as con:
        con.execute("DELETE FROM students WHERE id = ?", (student_id,))


# ------------------------------------------------------------------ 等级／课型


def list_levels(active_only: bool = False) -> list[sqlite3.Row]:
    """等级列表。选课／报名／缴费的下拉传 active_only=True，只列没停用的。"""
    with _connect() as con:
        return list(
            con.execute(
                """SELECT l.*, u.display_name AS default_teacher_name
                     FROM levels l
                     LEFT JOIN users u ON u.id = l.default_teacher_id
                    WHERE (? = 0 OR l.active = 1)
                    ORDER BY l.sort, l.subject, l.name"""
                ,
                (1 if active_only else 0,),
            )
        )


def set_level_active(level_id: int, active: bool) -> None:
    """停用／启用一个等级。停用后新建课程、报名、缴费的下拉里就不出现了。"""
    with _connect() as con:
        con.execute(
            "UPDATE levels SET active = ? WHERE id = ?",
            (1 if active else 0, level_id),
        )


def levels_for_selection(include_ids: list[int] | None = None) -> list[sqlite3.Row]:
    """下拉里能选的等级：没停用的 ＋ 正在编辑的那条记录本来用的等级。

    这样编辑一条老记录时，就算它的等级已经停用了，也不会显示成空白。
    """
    rows = list(list_levels(active_only=True))
    want = {int(i) for i in (include_ids or []) if i}
    if want:
        have = {int(r["id"]) for r in rows}
        rows += [
            r for r in list_levels() if int(r["id"]) in want and int(r["id"]) not in have
        ]
    return rows

def level_full_name(row: sqlite3.Row | dict) -> str:
    subject = (row["subject"] or "").strip()
    name = (row["name"] or "").strip()
    return f"{subject}-{name}" if subject else name


def create_level(
    subject: str, name: str, minutes: int, default_teacher_id: int | None = None
) -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("等级名称不能为空")
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO levels(subject, name, default_minutes, default_teacher_id, sort)
               VALUES(?, ?, ?, ?, 100)""",
            (
                (subject or "").strip(),
                name,
                int(minutes),
                int(default_teacher_id) if default_teacher_id else None,
            ),
        )
        return int(cur.lastrowid)


def update_level(
    level_id: int,
    subject: str,
    name: str,
    minutes: int,
    default_teacher_id: int | None = None,
) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("等级名称不能为空")
    with _connect() as con:
        con.execute(
            """UPDATE levels
                  SET subject = ?, name = ?, default_minutes = ?, default_teacher_id = ?
                WHERE id = ?""",
            (
                (subject or "").strip(),
                name,
                int(minutes),
                int(default_teacher_id) if default_teacher_id else None,
                level_id,
            ),
        )


def level_usage(level_id: int) -> dict[str, int]:
    """这个等级还在哪些地方被用：学员报名、课程、缴费行、课次。"""
    with _connect() as con:
        return {
            key: int(
                con.execute(
                    f"SELECT COUNT(*) AS c FROM {table} WHERE level_id = ?",
                    (level_id,),
                ).fetchone()["c"]
                or 0
            )
            for key, table in (
                ("enrollments", "enrollments"),
                ("courses", "schedule_templates"),
                ("payments", "payment_items"),
                ("lessons", "lessons"),
            )
        }


def count_level_usage(level_id: int) -> int:
    """这个等级还有没有在用（只要有一处用了就算）。"""
    return sum(level_usage(level_id).values())


def level_usage_text(level_id: int) -> str:
    """给界面看的一句话：这个等级被哪些记录用着。"""
    usage = level_usage(level_id)
    labels = (
        ("enrollments", "个学员报名"),
        ("courses", "门课程"),
        ("payments", "条缴费"),
        ("lessons", "节课"),
    )
    parts = [f"{usage[key]} {label}" for key, label in labels if usage[key]]
    return "、".join(parts)


def delete_level(level_id: int, force: bool = False) -> None:
    """删等级。

    有记录在用时，force=True 会把那些记录上的等级清空，再把等级删掉
    （课程、缴费、课次、报名这些记录本身都不删，只是不再指向这个等级）。
    """
    used = level_usage_text(level_id)
    if used and not force:
        raise ValueError(f"这个等级还有记录在用它（{used}）。")
    with _connect() as con:
        if used:
            con.execute("UPDATE lessons SET level_id = NULL WHERE level_id = ?", (level_id,))
            con.execute(
                "UPDATE payment_items SET level_id = NULL WHERE level_id = ?", (level_id,)
            )
            con.execute(
                "UPDATE schedule_templates SET level_id = NULL WHERE level_id = ?",
                (level_id,),
            )
            con.execute(
                "UPDATE enrollments SET level_id = NULL WHERE level_id = ?", (level_id,)
            )
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
                      l.default_teacher_id AS level_teacher_id,
                      ct.name AS class_type_name,
                      u.display_name AS owner_teacher_name,
                      t.name AS class_name, t.weekday AS class_weekday,
                      t.start_time AS class_start_time,
                      t.teacher_id AS class_teacher_id,
                      tu.display_name AS class_teacher_name
                 FROM enrollments e
                 LEFT JOIN levels l ON l.id = e.level_id
                 LEFT JOIN class_types ct ON ct.id = e.class_type_id
                 LEFT JOIN users u ON u.id = e.owner_teacher_id
                 LEFT JOIN schedule_templates t ON t.id = e.class_id
                 LEFT JOIN users tu ON tu.id = t.teacher_id
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
    owner_teacher_id: int | None = None,
    class_id: int | None = None,
) -> int:
    with _connect() as con:
        if class_id:
            cls = con.execute(
                "SELECT * FROM schedule_templates WHERE id = ?", (class_id,)
            ).fetchone()
            if cls is not None:
                level_id = level_id or cls["level_id"]
                class_type_id = class_type_id or cls["class_type_id"]
                if not owner_teacher_id and cls["teacher_id"]:
                    owner_teacher_id = cls["teacher_id"]
        owner = int(owner_teacher_id) if owner_teacher_id else None
        if not owner and level_id:
            lv = con.execute(
                "SELECT default_teacher_id FROM levels WHERE id = ?", (level_id,)
            ).fetchone()
            owner = int(lv["default_teacher_id"]) if lv and lv["default_teacher_id"] else None
        if not owner:
            st = con.execute(
                "SELECT owner_teacher_id FROM students WHERE id = ?", (student_id,)
            ).fetchone()
            owner = int(st["owner_teacher_id"]) if st and st["owner_teacher_id"] else None
        cur = con.execute(
            """INSERT INTO enrollments
                   (student_id, level_id, class_type_id, class_id, minutes, status,
                    owner_teacher_id, note, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                student_id,
                level_id,
                class_type_id,
                int(class_id) if class_id else None,
                int(minutes),
                status,
                owner,
                note,
                _today(),
            ),
        )
        new_id = int(cur.lastrowid)
        if class_id:
            # 这门课程已经过了结课日的话，新报名直接算结课
            _apply_course_dates(con, int(class_id))
    refresh_student(student_id)
    return new_id


def update_enrollment(
    enrollment_id: int,
    level_id: int | None,
    class_type_id: int,
    minutes: int,
    status: str,
    note: str,
    owner_teacher_id: int | None = None,
    class_id: int | None = None,
) -> None:
    with _connect() as con:
        con.execute(
            """UPDATE enrollments
                  SET level_id = ?, class_type_id = ?, class_id = ?, minutes = ?, status = ?,
                      owner_teacher_id = ?, note = ?
                WHERE id = ?""",
            (
                level_id,
                class_type_id,
                int(class_id) if class_id else None,
                int(minutes),
                status,
                int(owner_teacher_id) if owner_teacher_id else None,
                note,
                enrollment_id,
            ),
        )
        row = con.execute(
            "SELECT student_id FROM enrollments WHERE id = ?", (enrollment_id,)
        ).fetchone()
    if row is not None:
        refresh_student(int(row["student_id"]))


def delete_enrollment(enrollment_id: int) -> None:
    with _connect() as con:
        row = con.execute(
            "SELECT student_id FROM enrollments WHERE id = ?", (enrollment_id,)
        ).fetchone()
        con.execute("DELETE FROM enrollments WHERE id = ?", (enrollment_id,))
    if row is not None:
        refresh_student(int(row["student_id"]))


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


# ---------------------------------------------------------------- 杂项设置


def get_meta(key: str, default: str = "") -> str:
    """读一条杂项设置（比如海报上的机构名）。"""
    with _connect() as con:
        row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row is not None else default


def set_meta(key: str, value: str) -> None:
    with _connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (key, value or "")
        )


def next_lesson_for(student_id: int, day: str, start_time: str = "") -> dict | None:
    """这个孩子下一节要上的课（海报上写给家长看）。"""
    if not student_id:
        return None
    with _connect() as con:
        row = con.execute(
            """SELECT l.id, l.lesson_date, l.start_time, l.kind
                 FROM attendance a
                 JOIN lessons l ON l.id = a.lesson_id
                WHERE a.student_id = ?
                  AND (l.lesson_date > ? OR (l.lesson_date = ? AND l.start_time > ?))
                ORDER BY l.lesson_date, l.start_time, l.id
                LIMIT 1""",
            (int(student_id), day or "", day or "", start_time or ""),
        ).fetchone()
    return dict(row) if row else None


def month_attendance_summary(
    student_id: int, month: str, upto_day: str = ""
) -> tuple[int, int]:
    """这个孩子在某个月出勤了几次／一共几次（只算到 upto_day 那天为止）。

    month 是 'YYYY-MM'。海报上写成「本月出勤 3/3 次」用。
    """
    if not student_id or not month:
        return 0, 0
    sql = """SELECT COUNT(*) AS total,
                    COALESCE(SUM(CASE WHEN a.attendance THEN 1 ELSE 0 END), 0) AS present
               FROM attendance a
               JOIN lessons l ON l.id = a.lesson_id
              WHERE a.student_id = ? AND substr(l.lesson_date, 1, 7) = ?"""
    args: list[Any] = [int(student_id), month]
    if upto_day:
        sql += " AND l.lesson_date <= ?"
        args.append(upto_day)
    with _connect() as con:
        row = con.execute(sql, args).fetchone()
    return int(row["present"] or 0), int(row["total"] or 0)


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
    teacher_id: int | None = None,
    template_id: int | None = None,
    rolled: int = 1,
) -> int:
    """新建一节课。

    ``rolled=1``（默认）表示这节课当场就算数（扣课时、加积分）；
    传 ``rolled=0`` 就是**先排上、还没点名**：名单在，等上完课点「点名」才算数。
    """
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO lessons
                   (lesson_date, start_time, minutes, class_type_id, level_id,
                    comment, plan, note, kind, teacher_id, template_id, rolled, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                int(teacher_id) if teacher_id else None,
                int(template_id) if template_id else None,
                0 if rolled is not None and int(rolled) == 0 else 1,
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
    teacher_id: int | None = None,
    template_id: int | None = None,
) -> None:
    with _connect() as con:
        con.execute(
            """UPDATE lessons
                  SET lesson_date = ?, start_time = ?, minutes = ?, class_type_id = ?,
                      level_id = ?, comment = ?, plan = ?, note = ?, teacher_id = ?,
                      template_id = ?
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
                int(teacher_id) if teacher_id else None,
                int(template_id) if template_id else None,
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
           t.name AS class_name, t.weekday AS class_weekday,
           t.start_time AS class_start_time,
           u.display_name AS teacher_name,
           (SELECT GROUP_CONCAT(DISTINCT COALESCE(u2.display_name, u2.username))
              FROM attendance a2
              LEFT JOIN users u2 ON u2.id = a2.owner_teacher_id
             WHERE a2.lesson_id = l.id AND a2.owner_teacher_id IS NOT NULL) AS owner_names,
           (SELECT COUNT(*) FROM attendance a WHERE a.lesson_id = l.id) AS student_count,
           (SELECT COALESCE(SUM(CASE WHEN a.attendance = 1 THEN a.minutes ELSE 0 END), 0)
              FROM attendance a WHERE a.lesson_id = l.id) AS attended_minutes,
           (SELECT COUNT(*) FROM attendance a
             WHERE a.lesson_id = l.id AND a.attendance = 1) AS attended_count,
           (SELECT COALESCE(SUM((a.attendance + a.discipline + a.performance) * 10 + a.bonus), 0)
              FROM attendance a WHERE a.lesson_id = l.id) AS points
      FROM lessons l
      LEFT JOIN class_types ct ON ct.id = l.class_type_id
      LEFT JOIN levels lv ON lv.id = l.level_id
      LEFT JOIN schedule_templates t ON t.id = l.template_id
      LEFT JOIN users u ON u.id = l.teacher_id
"""


def get_lesson(lesson_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute(_LESSON_SELECT + " WHERE l.id = ?", (lesson_id,)).fetchone()
    return dict(row) if row else None


def list_lessons(
    limit: int = 200,
    keyword: str = "",
    start: str = "",
    end: str = "",
) -> list[dict]:
    """课次列表。keyword 会搜：孩子名字、课型、等级、日期、课评、教案、正常／补课。

    start／end 传日期就是只看这一段（按周展示用）。
    """
    sql = _LESSON_SELECT
    args: list[Any] = []
    where: list[str] = []
    text = (keyword or "").strip()
    if text:
        like = f"%{text}%"
        # 界面上日期是"9月26日"这种写法，库里存的是 2026-09-26，
        # 所以顺手把"9月26日""9-26"这种输入转成 -09-26 一起配一下
        date_hit = re.match(r"^(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*日?$", text)
        where.append(
            f"""(
              l.lesson_date LIKE ? OR ct.name LIKE ? OR lv.subject LIKE ? OR lv.name LIKE ?
              OR l.kind LIKE ? OR l.comment LIKE ? OR l.plan LIKE ?
              {"OR l.lesson_date LIKE ?" if date_hit else ""}
              OR EXISTS (SELECT 1 FROM attendance a
                           JOIN students s ON s.id = a.student_id
                          WHERE a.lesson_id = l.id AND s.name LIKE ?)
          )"""
        )
        args += [like] * 7
        if date_hit:
            args.append(f"%-{int(date_hit.group(1)):02d}-{int(date_hit.group(2)):02d}")
        args.append(like)  # 最后那个是孩子名字
    if (start or "").strip():
        where.append("l.lesson_date >= ?")
        args.append(start.strip())
    if (end or "").strip():
        where.append("l.lesson_date <= ?")
        args.append(end.strip())
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY l.lesson_date DESC, l.start_time DESC, l.id DESC LIMIT ?"
    args.append(limit)
    with _connect() as con:
        rows = con.execute(sql, args).fetchall()
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
                      lv.name AS level_name,
                      u.display_name AS owner_teacher_name
                 FROM attendance a
                 JOIN students s ON s.id = a.student_id
                 LEFT JOIN enrollments e ON e.id = a.enrollment_id
                 LEFT JOIN levels lv ON lv.id = e.level_id
                 LEFT JOIN users u ON u.id = a.owner_teacher_id
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


def find_enrollment(
    student_id: int,
    level_id: int | None = None,
    class_id: int | None = None,
    teacher_id: int | None = None,
) -> dict | None:
    """这节课该记到孩子的哪条报名上。

    优先顺序：同班级 → 同等级＋同归属老师 → 同等级 → 任何在读。
    （一个孩子同一等级报了两个班时，靠班级／老师区分。）
    """
    all_rows = list_enrollments(student_id)
    active = [e for e in all_rows if e["status"] == "在读"]
    rows = active or all_rows
    if class_id:
        for e in [*rows, *all_rows]:
            if e["class_id"] == class_id:
                return e
    if level_id and teacher_id:
        for e in rows:
            if e["level_id"] == level_id and e["owner_teacher_id"] == teacher_id:
                return e
    if level_id:
        for e in rows:
            if e["level_id"] == level_id:
                return e
    return rows[0] if rows else None


def get_enrollment(enrollment_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute(
            """SELECT e.*, l.subject, l.name AS level_name,
                      l.default_teacher_id AS level_teacher_id,
                      l.default_minutes,
                      u.display_name AS owner_teacher_name,
                      t.name AS class_name, t.teacher_id AS class_teacher_id,
                      t.weekday AS class_weekday, t.start_time AS class_start_time
                 FROM enrollments e
                 LEFT JOIN levels l ON l.id = e.level_id
                 LEFT JOIN users u ON u.id = e.owner_teacher_id
                 LEFT JOIN schedule_templates t ON t.id = e.class_id
                WHERE e.id = ?""",
            (enrollment_id,),
        ).fetchone()
    return dict(row) if row else None


def _owner_teacher_for(
    con: sqlite3.Connection, student_id: int, enrollment: dict | None
) -> int | None:
    """这条点名算谁的客户：缴费归属 → 报名／课程归属 → 课程默认老师 → 学员默认。

    注意：这里记的是"谁的客户"；这节课谁上的（拿课时费）记在课程的
    「上课老师」上，两回事。
    """
    paid = con.execute(
        """SELECT pi.owner_teacher_id AS tid FROM payment_items pi
             JOIN payments p ON p.id = pi.payment_id
            WHERE p.student_id = ? AND pi.owner_teacher_id IS NOT NULL
            ORDER BY p.paid_on DESC, p.id DESC
            LIMIT 1""",
        (student_id,),
    ).fetchone()
    if paid is not None:
        return int(paid["tid"])
    if enrollment and enrollment.get("owner_teacher_id"):
        return int(enrollment["owner_teacher_id"])
    if enrollment and enrollment.get("class_teacher_id"):
        return int(enrollment["class_teacher_id"])
    level_id = enrollment.get("level_id") if enrollment else None
    if level_id:
        lv = con.execute(
            "SELECT default_teacher_id FROM levels WHERE id = ?", (level_id,)
        ).fetchone()
        if lv is not None and lv["default_teacher_id"]:
            return int(lv["default_teacher_id"])
    row = con.execute(
        "SELECT owner_teacher_id FROM students WHERE id = ?", (student_id,)
    ).fetchone()
    if row is not None and row["owner_teacher_id"]:
        return int(row["owner_teacher_id"])
    return None


def default_owner_teacher(student_id: int | None, level_id: int | None = None) -> int | None:
    """新报名／新缴费行默认归谁：这个孩子的报名 → 课程默认老师 → 学员默认。

    同一个等级报了两个班（两个老师）时，不猜，返回 None 让人自己选。
    """
    if student_id:
        rows = [
            e
            for e in list_enrollments(student_id)
            if e["status"] == "在读" and e["owner_teacher_id"]
        ]
        if level_id:
            owners = {int(e["owner_teacher_id"]) for e in rows if e["level_id"] == level_id}
            if len(owners) == 1:
                return owners.pop()
            if len(owners) > 1:
                return None
        elif rows:
            return int(rows[0]["owner_teacher_id"])
    if level_id:
        with _connect() as con:
            row = con.execute(
                "SELECT default_teacher_id FROM levels WHERE id = ?", (level_id,)
            ).fetchone()
        if row is not None and row["default_teacher_id"]:
            return int(row["default_teacher_id"])
    if student_id:
        with _connect() as con:
            row = con.execute(
                "SELECT owner_teacher_id FROM students WHERE id = ?", (student_id,)
            ).fetchone()
        if row is not None and row["owner_teacher_id"]:
            return int(row["owner_teacher_id"])
    return None


def add_attendance(
    lesson_id: int,
    student_id: int,
    enrollment_id: int | None = None,
    minutes: float | None = None,
) -> int:
    lesson = get_lesson(lesson_id)
    if lesson is None:
        raise ValueError("这节课不存在")
    enrollment = get_enrollment(enrollment_id) if enrollment_id else None
    if enrollment is None:
        enrollment = find_enrollment(
            student_id,
            lesson["level_id"],
            class_id=lesson.get("template_id"),
            teacher_id=lesson.get("teacher_id"),
        )
        enrollment_id = enrollment["id"] if enrollment else None
    if minutes is None:
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
        owner = _owner_teacher_for(con, student_id, enrollment)
        cur = con.execute(
            """INSERT INTO attendance
                   (lesson_id, student_id, enrollment_id, minutes,
                    owner_teacher_id, created_at)
               VALUES(?, ?, ?, ?, ?, ?)""",
            (lesson_id, student_id, enrollment_id, float(minutes), owner, _today()),
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
    if not lesson.get("rolled"):
        # 还没点名：这节课先不记分、不扣课时
        with _connect() as con:
            con.execute(
                "DELETE FROM point_transactions WHERE source_type = 'lesson' AND source_id = ?",
                (lesson_id,),
            )
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
                WHERE a.student_id = ? AND l.rolled = 1
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
           l.teacher_id AS origin_teacher_id,
           u.display_name AS origin_teacher_name,
           ct.name AS class_type_name, lv.subject, lv.name AS level_name,
           ml.lesson_date AS makeup_date, ml.start_time AS makeup_time
      FROM makeups m
      JOIN students s ON s.id = m.student_id
      LEFT JOIN lessons l ON l.id = m.lesson_id
      LEFT JOIN users u ON u.id = l.teacher_id
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
    makeup_id: int,
    lesson_date: str,
    start_time: str,
    minutes: float,
    teacher_id: int | None = None,
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
    if teacher_id is None and origin is not None:
        teacher_id = origin["teacher_id"]
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
        teacher_id=int(teacher_id) if teacher_id else None,
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
           u.display_name AS teacher_name,
           (SELECT COUNT(*) FROM schedule_students ss WHERE ss.template_id = t.id) AS student_count
      FROM schedule_templates t
      LEFT JOIN class_types ct ON ct.id = t.class_type_id
      LEFT JOIN levels lv ON lv.id = t.level_id
      LEFT JOIN users u ON u.id = t.teacher_id
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
    start_date: str = "",
    end_date: str = "",
    teacher_id: int | None = None,
    name: str = "",
    year: str = "",
    term: str = "",
    seq: int | None = None,
) -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("课程名不能为空")
    with _connect() as con:
        exists = con.execute(
            "SELECT id FROM schedule_templates WHERE name = ?", (name,)
        ).fetchone()
        if exists is not None:
            raise ValueError(f"已经有叫「{name}」的课程了，换个名字")
        cur = con.execute(
            """INSERT INTO schedule_templates
                   (name, year, term, seq, weekday, start_time, minutes,
                    class_type_id, level_id, note,
                    start_date, end_date, teacher_id, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                (year or "").strip(),
                (term or "").strip(),
                int(seq or 0),
                int(weekday),
                start_time,
                int(minutes),
                class_type_id,
                level_id,
                note,
                (start_date or "").strip(),
                (end_date or "").strip(),
                int(teacher_id) if teacher_id else None,
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
    start_date: str = "",
    end_date: str = "",
    teacher_id: int | None = None,
    name: str = "",
    year: str = "",
    term: str = "",
    seq: int | None = None,
) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("课程名不能为空")
    with _connect() as con:
        exists = con.execute(
            "SELECT id FROM schedule_templates WHERE name = ? AND id <> ?",
            (name, template_id),
        ).fetchone()
        if exists is not None:
            raise ValueError(f"已经有叫「{name}」的课程了，换个名字")
        con.execute(
            """UPDATE schedule_templates
                  SET name = ?, year = ?, term = ?, seq = ?, weekday = ?,
                      start_time = ?, minutes = ?, class_type_id = ?,
                      level_id = ?, note = ?, start_date = ?, end_date = ?, teacher_id = ?
                WHERE id = ?""",
            (
                name,
                (year or "").strip(),
                (term or "").strip(),
                int(seq or 0),
                int(weekday),
                start_time,
                int(minutes),
                class_type_id,
                level_id,
                note,
                (start_date or "").strip(),
                (end_date or "").strip(),
                int(teacher_id) if teacher_id else None,
                template_id,
            ),
        )
        # 给班定了／换了老师，挂在这个班上的报名归属跟着走
        # （历史点名和缴费是冻结的，不受影响）
        if teacher_id:
            con.execute(
                "UPDATE enrollments SET owner_teacher_id = ? WHERE class_id = ?",
                (int(teacher_id), template_id),
            )
        # 起止日期变了，跟着同步"是不是已经结课"
        _apply_course_dates(con, template_id)
        # 换了课程老师，学员档案上的归属也跟着更新
        for row in con.execute(
            "SELECT DISTINCT student_id FROM enrollments WHERE class_id = ?",
            (template_id,),
        ):
            refresh_student(int(row["student_id"]), con)


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
        # 刚加进这个班的孩子：要是他这门课还没挂过班，就顺手挂上，
        # 归属跟着班级老师走（一个等级命中好几条报名时不动，免得挂错）
        template = con.execute(
            "SELECT * FROM schedule_templates WHERE id = ?", (template_id,)
        ).fetchone()
        if template is None:
            return
        for sid in dict.fromkeys(student_ids):
            rows = con.execute(
                """SELECT id, owner_teacher_id FROM enrollments
                    WHERE student_id = ? AND IFNULL(level_id, 0) = IFNULL(?, 0)
                      AND class_type_id = ? AND class_id IS NULL""",
                (int(sid), template["level_id"], template["class_type_id"]),
            ).fetchall()
            if len(rows) != 1:
                continue
            owner = template["teacher_id"] or rows[0]["owner_teacher_id"]
            con.execute(
                "UPDATE enrollments SET class_id = ?, owner_teacher_id = ? WHERE id = ?",
                (template_id, owner, rows[0]["id"]),
            )
        # 新加进来的孩子，要是这个课程已经结课了，报名也跟着结课
        _apply_course_dates(con, template_id)
        for sid in dict.fromkeys(student_ids):
            refresh_student(int(sid), con)


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
        if int(lesson["template_id"] or 0) == int(template["id"]):
            return lesson
        # 早年建的课次没记来源，就按"时间 + 课型 + 等级"认一下
        if (
            lesson["template_id"] is None
            and lesson["start_time"] == template["start_time"]
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
    if not course_covers(template, lesson_date):
        raise ValueError("这天不在这个课程的开班～结课范围内，不能排课")
    if is_course_skipped(template_id, lesson_date):
        raise ValueError("这天已经标了「不上课」，要上的话先去课程里把那天的取消恢复")
    existing = find_lesson_for_template(template, lesson_date)
    if existing:
        return int(existing["id"])
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO lessons
                   (lesson_date, start_time, minutes, class_type_id, level_id,
                    kind, teacher_id, template_id, rolled, created_at)
               VALUES(?, ?, ?, ?, ?, '正常', ?, ?, 0, ?)""",
            (
                lesson_date,
                template["start_time"],
                int(template["minutes"]),
                template["class_type_id"],
                template["level_id"],
                int(template["teacher_id"]) if template["teacher_id"] else None,
                template_id,
                _today(),
            ),
        )
        lesson_id = int(cur.lastrowid)
    for sid in template_student_ids(template_id):
        add_attendance(lesson_id, sid, minutes=template["minutes"])
    return lesson_id


def course_covers(course: dict | sqlite3.Row, day: str) -> bool:
    """这门课程这一天在不在开课范围内（开班日 ≤ 这天 ≤ 结课日；空的一边不限）。"""
    text = (day or "").strip()
    if not text:
        return False
    data = dict(course)
    start = (data.get("start_date") or "").strip()
    end = (data.get("end_date") or "").strip()
    if start and text < start:
        return False
    if end and text > end:
        return False
    return True


def templates_on(day: str) -> list[dict]:
    """某一天该上的课程：周几对上，而且这天在开班～结课之间。"""
    text = (day or "").strip()
    try:
        weekday = date.fromisoformat(text).weekday()
    except ValueError:
        return []
    with _connect() as con:
        skipped = {
            int(r["template_id"])
            for r in con.execute(
                "SELECT template_id FROM course_skips WHERE skip_date = ?", (text,)
            )
        }
    return [
        t
        for t in list_templates(weekday=weekday)
        if course_covers(t, text) and int(t["id"]) not in skipped
    ]


def skip_course_day(template_id: int, day: str, note: str = "") -> None:
    """把这门课某一天标成"不上"：那天不再出现在课表上，也不给点名。"""
    text = (day or "").strip()
    if not text:
        raise ValueError("要指定日期")
    with _connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO course_skips
                   (template_id, skip_date, note, created_at)
               VALUES(?, ?, ?, ?)""",
            (int(template_id), text, note or "", _today()),
        )


def unskip_course_day(template_id: int, day: str) -> None:
    """恢复某一天上课。"""
    with _connect() as con:
        con.execute(
            "DELETE FROM course_skips WHERE template_id = ? AND skip_date = ?",
            (int(template_id), (day or "").strip()),
        )


def course_skips(template_id: int) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            """SELECT * FROM course_skips WHERE template_id = ?
                ORDER BY skip_date""",
            (int(template_id),),
        ).fetchall()
    return [dict(r) for r in rows]


def is_course_skipped(template_id: int, day: str) -> bool:
    with _connect() as con:
        row = con.execute(
            "SELECT 1 FROM course_skips WHERE template_id = ? AND skip_date = ?",
            (int(template_id), (day or "").strip()),
        ).fetchone()
    return row is not None


def template_dates(template: dict, start: str | None = None, end: str | None = None) -> list[str]:
    """课表区间里，逢"周几"的那些日子。"""
    first = (start if start is not None else template.get("start_date") or "").strip()
    last = (end if end is not None else template.get("end_date") or "").strip()
    if not first or not last:
        return []
    try:
        weekday = int(template["weekday"])
    except (KeyError, TypeError, ValueError):
        return []
    if not (0 <= weekday <= 6):
        # 没定星期几的课程，算不出每周的日期
        return []
    try:
        day = date.fromisoformat(first)
        stop = date.fromisoformat(last)
    except ValueError:
        return []
    if stop < day:
        return []
    step = (weekday - day.weekday()) % 7
    day += timedelta(days=step)
    out = []
    while day <= stop:
        out.append(day.isoformat())
        day += timedelta(days=7)
    return out


def template_lessons(template_id: int) -> list[dict]:
    """这张课表排出来的所有课次。"""
    with _connect() as con:
        rows = con.execute(
            _LESSON_SELECT + " WHERE l.template_id = ? ORDER BY l.lesson_date, l.start_time",
            (template_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def generate_template_lessons(template_id: int) -> dict:
    """照着课表把整学期的课一次排出来。

    排出来的课是"还没点名"的：名单在，但**不扣课时、不加积分**，
    等真的上完课进去点名了才算数。
    """
    template = get_template(template_id)
    if template is None:
        raise ValueError("这张课表不存在")
    dates = template_dates(template)
    if not dates:
        try:
            weekday = int(template["weekday"])
        except (TypeError, ValueError):
            weekday = -1
        if not (0 <= weekday <= 6):
            raise ValueError(
                "这门课程没定星期几（时间不定），不能用「排整学期」；用「记一节课」一次一次记"
            )
        raise ValueError("先填上课表的起止日期")
    made, skipped = [], []
    for day in dates:
        if is_course_skipped(template_id, day):
            skipped.append(day)
            continue
        if find_lesson_for_template(template, day):
            skipped.append(day)
            continue
        create_lesson_from_template(template_id, day)
        made.append(day)
    return {"made": made, "skipped": skipped, "dates": dates}


def roll_call(lesson_id: int) -> None:
    """这节课点过名了：从现在起才真的扣课时、加积分。"""
    with _connect() as con:
        row = con.execute("SELECT rolled FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        if row is None or row["rolled"]:
            return
        con.execute("UPDATE lessons SET rolled = 1 WHERE id = ?", (lesson_id,))
    recompute_lesson(lesson_id)


def unroll_lesson(lesson_id: int) -> None:
    """撤销点名：把课改回「待点名」，这节课扣的课时、加的积分都退回来。

    名单、课评、教案、照片都不动，以后还能再点一次名。
    """
    with _connect() as con:
        row = con.execute("SELECT rolled FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        if row is None or not row["rolled"]:
            return
        con.execute("UPDATE lessons SET rolled = 0 WHERE id = ?", (lesson_id,))
    recompute_lesson(lesson_id)  # rolled=0：先清掉这节课的积分
    for a in list_attendance(lesson_id):
        recompute_student(int(a["student_id"]))  # 课时也按"没上这节课"重算


def unrolled_lessons(limit: int = 200) -> list[dict]:
    """排好了但还没点名的课（按时间从早到晚）。"""
    with _connect() as con:
        rows = con.execute(
            _LESSON_SELECT
            + " WHERE l.rolled = 0 AND l.kind = '正常' ORDER BY l.lesson_date, l.start_time LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ 试听跟进


def create_trial(data: dict) -> int:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("姓名不能为空")
    owner = data.get("owner_teacher_id")
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO trials
                   (name, gender, grade, school, parent_name, phone, source, status,
                    trial_on, note, owner_teacher_id, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                data.get("gender", ""),
                data.get("grade", ""),
                data.get("school", ""),
                data.get("parent_name", ""),
                data.get("phone", ""),
                data.get("source", ""),
                data.get("status") or "待试听",
                data.get("trial_on", ""),
                data.get("note", ""),
                int(owner) if owner else None,
                _today(),
            ),
        )
        return int(cur.lastrowid)


def update_trial(trial_id: int, data: dict) -> None:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("姓名不能为空")
    owner = data.get("owner_teacher_id")
    with _connect() as con:
        con.execute(
            """UPDATE trials
                  SET name = ?, gender = ?, grade = ?, school = ?, parent_name = ?, phone = ?,
                      source = ?, status = ?, trial_on = ?, note = ?, owner_teacher_id = ?
                WHERE id = ?""",
            (
                name,
                data.get("gender", ""),
                data.get("grade", ""),
                data.get("school", ""),
                data.get("parent_name", ""),
                data.get("phone", ""),
                data.get("source", ""),
                data.get("status") or "待试听",
                data.get("trial_on", ""),
                data.get("note", ""),
                int(owner) if owner else None,
                trial_id,
            ),
        )


def get_trial(trial_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute(
            """SELECT t.*, u.display_name AS owner_teacher_name
                 FROM trials t
                 LEFT JOIN users u ON u.id = t.owner_teacher_id
                WHERE t.id = ?""",
            (trial_id,),
        ).fetchone()
    return dict(row) if row else None


def list_trials(status: str = "", keyword: str = "") -> list[dict]:
    sql = """SELECT t.*, u.display_name AS owner_teacher_name
               FROM trials t
               LEFT JOIN users u ON u.id = t.owner_teacher_id
              WHERE 1 = 1"""
    args: list[Any] = []
    if status:
        sql += " AND t.status = ?"
        args.append(status)
    if keyword:
        like = f"%{keyword}%"
        sql += (" AND (t.name LIKE ? OR t.grade LIKE ? OR t.school LIKE ? OR t.phone LIKE ?"
                " OR t.parent_name LIKE ? OR t.note LIKE ?)")
        args += [like, like, like, like, like, like]
    sql += """ ORDER BY CASE t.status
                            WHEN '待试听' THEN 0
                            WHEN '已试听' THEN 1
                            WHEN '已报名' THEN 2
                            ELSE 3
                        END,
                    t.trial_on DESC, t.id DESC"""
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
            "school": trial["school"],
            "phone": trial["phone"],
            "guardian": trial["parent_name"],
            "note": "；".join(note_bits),
            "status": "在读",
            "owner_teacher_id": trial["owner_teacher_id"] if "owner_teacher_id" in trial.keys() else None,
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
    like = f"{month}%" if month else "%"
    with _connect() as con:
        money = con.execute(
            """SELECT COALESCE(SUM(amount), 0) AS s, COUNT(*) AS c,
                      COALESCE(SUM(voucher_amount), 0) AS v
                 FROM payments WHERE paid_on LIKE ?""",
            (like,),
        ).fetchone()
        lessons = con.execute(
            "SELECT COUNT(*) AS c FROM lessons WHERE lesson_date LIKE ? AND rolled = 1", (like,)
        ).fetchone()
        attended = con.execute(
            """SELECT COUNT(*) AS c, COALESCE(SUM(a.minutes), 0) AS m
                 FROM attendance a JOIN lessons l ON l.id = a.lesson_id
                WHERE l.lesson_date LIKE ? AND a.attendance = 1 AND l.rolled = 1""",
            (like,),
        ).fetchone()
    return {
        "income": float(money["s"] or 0),
        "voucher_used": float(money["v"] or 0),
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
                WHERE l.lesson_date LIKE ? AND a.attendance = 1 AND l.rolled = 1
                GROUP BY s.id, s.name
                ORDER BY times DESC, s.name""",
            (f"{month}%",),
        ).fetchall()
    return [dict(r) for r in rows]


def teacher_report(month: str) -> list[dict]:
    """按老师汇总：归属缴费（实收）、上课节数与课时、在读学生、跟进中的试听。

    「归属缴费」按缴费明细行的归属老师算；一笔钱如果用了券，
    就按各行的名义金额比例把实收现金摊到各个老师头上。
    「上课」按这节课实际上课的老师算（谁上的课给谁）。
    """
    like = f"{month}%" if month else "%"
    names = teacher_name_map()

    def blank(key: int | None) -> dict:
        return {
            "teacher_id": key,
            "name": names.get(key, "") if key else "（未指定）",
            "phone": "",
            "income": 0.0,
            "lessons": 0,
            "hours": 0.0,
            "students": 0,
            "trials_open": 0,
        }

    info: dict[int | None, dict] = {}
    with _connect() as con:
        for r in con.execute(
            """SELECT id, display_name, username, phone FROM users
                WHERE is_teacher = 1 AND active = 1"""
        ):
            key = int(r["id"])
            info[key] = blank(key)
            info[key]["name"] = r["display_name"] or r["username"] or ""
            info[key]["phone"] = r["phone"] or ""

        # 归属缴费：把实收现金按行摊到各行归属老师
        rows = con.execute(
            """SELECT p.id AS payment_id, p.amount AS paid, pi.amount AS item_amount,
                      pi.owner_teacher_id AS owner
                 FROM payments p
                 JOIN payment_items pi ON pi.payment_id = p.id
                WHERE p.paid_on LIKE ?""",
            (like,),
        ).fetchall()
        by_payment: dict[int, list[sqlite3.Row]] = {}
        for r in rows:
            by_payment.setdefault(int(r["payment_id"]), []).append(r)
        for items in by_payment.values():
            nominal = sum(float(i["item_amount"] or 0) for i in items)
            cash = float(items[0]["paid"] or 0)
            for i in items:
                amount = float(i["item_amount"] or 0)
                share = cash * (amount / nominal) if nominal > 0 else 0.0
                key = int(i["owner"]) if i["owner"] else None
                info.setdefault(key, blank(key))["income"] += share

        # 上课：按实际上课老师
        for r in con.execute(
            """SELECT teacher_id, COUNT(*) AS c FROM lessons
                WHERE lesson_date LIKE ? AND rolled = 1
                GROUP BY teacher_id""",
            (like,),
        ):
            key = int(r["teacher_id"]) if r["teacher_id"] else None
            info.setdefault(key, blank(key))["lessons"] += int(r["c"] or 0)
        for r in con.execute(
            """SELECT l.teacher_id AS teacher_id, COALESCE(SUM(a.minutes), 0) AS m
                 FROM attendance a
                 JOIN lessons l ON l.id = a.lesson_id
                WHERE l.lesson_date LIKE ? AND a.attendance = 1 AND l.rolled = 1
                GROUP BY l.teacher_id""",
            (like,),
        ):
            key = int(r["teacher_id"]) if r["teacher_id"] else None
            info.setdefault(key, blank(key))["hours"] += float(r["m"] or 0) / 60

        # 在读学生：按报名归属
        for r in con.execute(
            """SELECT owner_teacher_id AS o, COUNT(DISTINCT student_id) AS c
                 FROM enrollments
                WHERE status = '在读' AND owner_teacher_id IS NOT NULL
                GROUP BY owner_teacher_id"""
        ):
            key = int(r["o"])
            info.setdefault(key, blank(key))["students"] += int(r["c"] or 0)

        # 跟进中的试听：谁的客户线索
        for r in con.execute(
            """SELECT owner_teacher_id AS o, COUNT(*) AS c FROM trials
                WHERE status IN ('待试听', '已试听') AND owner_teacher_id IS NOT NULL
                GROUP BY owner_teacher_id"""
        ):
            key = int(r["o"])
            info.setdefault(key, blank(key))["trials_open"] += int(r["c"] or 0)

    for row in info.values():
        row["income"] = round(row["income"], 2)
        row["hours"] = round(row["hours"], 2)
    # 有名字的老师排前面，「还没指定老师」那一桶放最后
    return sorted(
        info.values(), key=lambda r: (r["teacher_id"] is None, -r["income"], r["name"])
    )


def _level_text(row: dict) -> str:
    subject = (row.get("subject") or "").strip()
    level = (row.get("level_name") or "").strip()
    return f"{subject}-{level}" if subject else level


def export_tables() -> list[tuple[str, list[str], list[list]]]:
    """把所有数据整理成可以写到 Excel 的表。"""
    sheets: list[tuple[str, list[str], list[list]]] = []
    students = list_students()
    tnames = teacher_name_map()

    sheets.append(
        (
            "学员",
            ["ID", "姓名", "性别", "年级", "学校", "电话", "监护人", "状态", "归属老师", "备注", "建档日期"],
            [
                [
                    s["id"],
                    s["name"],
                    s["gender"],
                    s["grade"],
                    s["school"],
                    s["phone"],
                    s["guardian"],
                    s["status"],
                    tnames.get(s["owner_teacher_id"], "") if s["owner_teacher_id"] else "",
                    s["note"],
                    s["created_at"],
                ]
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
                    e["owner_teacher_name"] or "",
                    e["note"],
                ]
            )
    sheets.append(
        ("报名课程", ["学员", "等级", "课型", "单次时长(分)", "状态", "归属老师", "备注"], rows)
    )

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
            ["日期", "开始时间", "时长(分)", "等级", "课型", "上课老师", "类型", "人数", "课评", "教案"],
            [
                [
                    l["lesson_date"],
                    l["start_time"],
                    l["minutes"],
                    _level_text(l),
                    l["class_type_name"],
                    l["teacher_name"] or "",
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
                    a["owner_teacher_name"] or "",
                    "到" if a["attendance"] else "请假",
                    "是" if a["discipline"] else "",
                    "是" if a["performance"] else "",
                    a["bonus"],
                    a["minutes"],
                    a["comment"],
                ]
            )
    sheets.append(
        (
            "点名明细",
            ["日期", "学员", "归属老师", "出勤", "纪律", "表现", "突出发挥", "时长(分)", "单独点评"],
            rows,
        )
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
                    item["owner_teacher_name"] or "",
                    item["hour_type_name"],
                    item["hours"],
                    item["amount"],
                    "赠送" if not item["amount"] else "",
                    p["note"],
                ]
            )
    sheets.append(
        (
            "缴费记录",
            ["日期", "学员", "归属老师", "课时类型", "数量", "金额", "赠送", "备注"],
            rows,
        )
    )

    sheets.append(
        (
            "试听记录",
            ["姓名", "年级", "学校", "家长", "电话", "来源", "跟进老师", "状态", "试听日期", "备注", "是否转正"],
            [
                [
                    t["name"],
                    t["grade"],
                    t["school"],
                    t["parent_name"],
                    t["phone"],
                    t["source"],
                    t["owner_teacher_name"] or "",
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
            "课程",
            ["课程", "状态", "开班日", "结课日", "星期", "时间", "时长(分)", "等级", "课型", "上课老师", "人数", "备注"],
            [
                [
                    class_label(t),
                    course_status(t),
                    t["start_date"],
                    t["end_date"],
                    weekday_text(t["weekday"]),
                    t["start_time"],
                    t["minutes"],
                    _level_text(t),
                    t["class_type_name"],
                    t["teacher_name"] or "",
                    t["student_count"],
                    t["note"],
                ]
                for t in list_templates()
            ],
        )
    )

    sheets.append(
        (
            "老师",
            ["老师", "电话", "在读学生", "归属实收(全部)", "上课节数(全部)", "上课课时(全部)", "跟进中试听"],
            [
                [
                    r["name"],
                    r["phone"],
                    r["students"],
                    r["income"],
                    r["lessons"],
                    r["hours"],
                    r["trials_open"],
                ]
                for r in teacher_report("")
            ],
        )
    )
    return sheets


def create_payment(
    student_id: int,
    paid_on: str,
    items: list[dict],
    note: str = "",
    voucher_id: int | None = None,
) -> int:
    """一笔缴费：总金额由各行相加，行里 amount=0 就是赠送。

    用代金券的话：amount 记实收现金，券抵的那部分记在 voucher_amount 里。
    只有本笔含正课才送券（面额 = 正课金额 ÷ 10，一次 10 张）。
    """
    clean = _clean_payment_items(items)
    if not clean:
        raise ValueError("至少要填一行课时")
    paid_on = paid_on or _today()
    nominal = sum(i["amount"] for i in clean)
    used_amount, used_id = _pick_voucher(student_id, voucher_id, paid_on)
    total = max(0.0, nominal - used_amount)
    first = clean[0]
    with _connect() as con:
        clean = _fill_item_owners(con, student_id, clean)
        owner_id = _single_owner(clean)
        cur = con.execute(
            """INSERT INTO payments
                   (student_id, paid_on, amount, hour_type_id, hours, note,
                    voucher_id, voucher_amount, teacher_id, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                student_id,
                paid_on,
                total,
                first["hour_type_id"],
                first["hours"],
                note,
                used_id,
                used_amount,
                owner_id,
                _today(),
            ),
        )
        payment_id = int(cur.lastrowid)
        for item in clean:
            con.execute(
                """INSERT INTO payment_items
                       (payment_id, hour_type_id, level_id, enrollment_id, hours, amount,
                        owner_teacher_id, created_at)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    payment_id,
                    item["hour_type_id"],
                    item["level_id"],
                    item["enrollment_id"],
                    item["hours"],
                    item["amount"],
                    item["owner_teacher_id"],
                    _today(),
                ),
            )
    sync_payment_hours(payment_id)
    sync_payment_enrollments(payment_id)
    issue_vouchers(student_id, payment_id, voucher_base(clean), paid_on)
    recompute_student(student_id)
    refresh_student(student_id)  # 客户归谁跟着这笔缴费的归属走
    return payment_id


def update_payment(
    payment_id: int,
    student_id: int,
    paid_on: str,
    items: list[dict],
    note: str = "",
    voucher_id: int | None = None,
) -> None:
    clean = _clean_payment_items(items)
    if not clean:
        raise ValueError("至少要填一行课时")
    paid_on = paid_on or _today()
    nominal = sum(i["amount"] for i in clean)
    used_amount, used_id = _pick_voucher(student_id, voucher_id, paid_on, payment_id)
    total = max(0.0, nominal - used_amount)
    first = clean[0]
    with _connect() as con:
        clean = _fill_item_owners(con, student_id, clean)
        owner_id = _single_owner(clean)
        # 顺序很重要：先清掉老流水，再删老的行
        _clear_payment_hours(con, payment_id)
        # 这笔原来送的券，只要一张都没用出去就收回，按新的金额重发
        _drop_unused_vouchers(con, payment_id)
        con.execute(
            """UPDATE payments
                  SET student_id = ?, paid_on = ?, amount = ?, hour_type_id = ?,
                      hours = ?, note = ?, voucher_id = ?, voucher_amount = ?, teacher_id = ?
                WHERE id = ?""",
            (
                student_id,
                paid_on,
                total,
                first["hour_type_id"],
                first["hours"],
                note,
                used_id,
                used_amount,
                owner_id,
                payment_id,
            ),
        )
        con.execute("DELETE FROM payment_items WHERE payment_id = ?", (payment_id,))
        for item in clean:
            con.execute(
                """INSERT INTO payment_items
                       (payment_id, hour_type_id, level_id, enrollment_id, hours, amount,
                        owner_teacher_id, created_at)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    payment_id,
                    item["hour_type_id"],
                    item["level_id"],
                    item["enrollment_id"],
                    item["hours"],
                    item["amount"],
                    item["owner_teacher_id"],
                    _today(),
                ),
            )
    sync_payment_hours(payment_id)
    sync_payment_enrollments(payment_id)
    issue_vouchers(student_id, payment_id, voucher_base(clean), paid_on)
    recompute_student(student_id)
    refresh_student(student_id)


def _clean_payment_items(items: list[dict]) -> list[dict]:
    out = []
    for raw in items or []:
        hour_type_id = raw.get("hour_type_id")
        hours = float(raw.get("hours") or 0)
        amount = float(raw.get("amount") or 0)
        if not hour_type_id or hours <= 0:
            continue
        owner = raw.get("owner_teacher_id")
        enroll = raw.get("enrollment_id")
        out.append(
            {
                "hour_type_id": int(hour_type_id),
                "level_id": int(raw["level_id"]) if raw.get("level_id") else None,
                "enrollment_id": int(enroll) if enroll else None,
                "hours": hours,
                "amount": amount,
                "owner_teacher_id": int(owner) if owner else None,
            }
        )
    return out


def _single_owner(clean: list[dict]) -> int | None:
    """一笔缴费里所有行都是同一个老师就返回他；跨老师（混合）返回 None。"""
    owners = {i["owner_teacher_id"] for i in clean if i.get("owner_teacher_id")}
    return owners.pop() if len(owners) == 1 else None


def _fill_item_owners(
    con: sqlite3.Connection, student_id: int, clean: list[dict]
) -> list[dict]:
    """缴费行没写归属老师的，按「指定的报名 → 学员钉住的归属 → 同等级报名 → 课程默认」补。

    同一等级要是报了两个班（两个老师），不猜，留空让人在缴费行上自己选。
    """
    student = con.execute(
        "SELECT owner_teacher_id, owner_manual FROM students WHERE id = ?",
        (student_id,),
    ).fetchone()
    student_owner = student["owner_teacher_id"] if student is not None else None
    for item in clean:
        if item.get("owner_teacher_id"):
            continue
        owner = None
        ambiguous = False
        # 这一行指定了是哪条报名（哪个班），归属直接跟它走
        if item.get("enrollment_id"):
            row = con.execute(
                """SELECT e.level_id AS level_id, e.owner_teacher_id AS owner,
                          t.teacher_id AS class_teacher
                     FROM enrollments e
                     LEFT JOIN schedule_templates t ON t.id = e.class_id
                    WHERE e.id = ?""",
                (item["enrollment_id"],),
            ).fetchone()
            if row is not None:
                item["level_id"] = item["level_id"] or row["level_id"]
                owner = row["owner"] or row["class_teacher"]
        # 学员档案里手动钉了归属老师，就按那个走（以后新缴费默认也归他）
        if (
            not owner
            and student is not None
            and int(student["owner_manual"] or 0)
            and student["owner_teacher_id"]
        ):
            owner = student["owner_teacher_id"]
        if not owner and item.get("level_id"):
            owners = {
                r["owner_teacher_id"]
                for r in con.execute(
                    """SELECT owner_teacher_id FROM enrollments
                        WHERE student_id = ? AND IFNULL(level_id, 0) = IFNULL(?, 0)
                          AND owner_teacher_id IS NOT NULL
                        GROUP BY owner_teacher_id""",
                    (student_id, item["level_id"]),
                )
            }
            if len(owners) == 1:
                owner = owners.pop()
            elif len(owners) > 1:
                ambiguous = True
        if not owner and not ambiguous and item.get("level_id"):
            level = con.execute(
                "SELECT default_teacher_id FROM levels WHERE id = ?",
                (item["level_id"],),
            ).fetchone()
            if level is not None:
                owner = level["default_teacher_id"]
        if not owner and not ambiguous:
            owner = student_owner
        item["owner_teacher_id"] = int(owner) if owner else None
    return clean


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
    """缴费里选过等级（或指定了哪条报名）的课时，顺手把「报名课程」建好。"""
    with _connect() as con:
        payment = con.execute(
            "SELECT * FROM payments WHERE id = ?", (payment_id,)
        ).fetchone()
        if payment is None:
            return
        rows = con.execute(
            """SELECT pi.*, lv.default_minutes,
                      lv.default_teacher_id AS level_teacher,
                      t.teacher_id AS class_teacher
                 FROM payment_items pi
                 LEFT JOIN levels lv ON lv.id = pi.level_id
                 LEFT JOIN enrollments e ON e.id = pi.enrollment_id
                 LEFT JOIN schedule_templates t ON t.id = e.class_id
                WHERE pi.payment_id = ?
                  AND (pi.level_id IS NOT NULL OR pi.enrollment_id IS NOT NULL)""",
            (payment_id,),
        ).fetchall()
        student_owner = con.execute(
            "SELECT owner_teacher_id FROM students WHERE id = ?",
            (payment["student_id"],),
        ).fetchone()
        fallback_owner = (
            student_owner["owner_teacher_id"] if student_owner is not None else None
        )
        for item in rows:
            class_type_id = _class_type_for_hour_type(con, item["hour_type_id"])
            if class_type_id is None:
                continue
            # 已经指定了是哪条报名（哪个班）：把空的归属补上就行，不再另建
            if item["enrollment_id"]:
                owner = item["owner_teacher_id"] or item["class_teacher"]
                if owner:
                    con.execute(
                        """UPDATE enrollments
                              SET owner_teacher_id = COALESCE(owner_teacher_id, ?)
                            WHERE id = ?""",
                        (owner, item["enrollment_id"]),
                    )
                    con.execute(
                        """UPDATE payment_items
                              SET owner_teacher_id = COALESCE(owner_teacher_id, ?)
                            WHERE id = ?""",
                        (owner, item["id"]),
                    )
                continue
            owner = (
                item["owner_teacher_id"]
                or item["class_teacher"]
                or item["level_teacher"]
                or fallback_owner
            )
            exists = con.execute(
                """SELECT id, owner_teacher_id FROM enrollments
                    WHERE student_id = ? AND class_type_id = ?
                      AND IFNULL(level_id, 0) = IFNULL(?, 0)
                      AND (? IS NULL OR IFNULL(owner_teacher_id, 0) = ?)
                    ORDER BY id
                    LIMIT 1""",
                (
                    payment["student_id"],
                    class_type_id,
                    item["level_id"],
                    owner,
                    owner,
                ),
            ).fetchone()
            if exists:
                if owner and not exists["owner_teacher_id"]:
                    con.execute(
                        "UPDATE enrollments SET owner_teacher_id = ? WHERE id = ?",
                        (owner, exists["id"]),
                    )
                continue
            con.execute(
                """INSERT INTO enrollments
                       (student_id, level_id, class_type_id, minutes, status,
                        owner_teacher_id, note, created_at)
                   VALUES(?, ?, ?, ?, '在读', ?, '缴费时自动建', ?)""",
                (
                    payment["student_id"],
                    item["level_id"],
                    class_type_id,
                    int(item["default_minutes"] or 90),
                    owner,
                    _today(),
                ),
            )


# ------------------------------------------------------------------ 代金券

VOUCHER_COUNT = 10   # 一次送几张
VOUCHER_MONTHS = 24  # 有效期多少个月


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def voucher_plan(base: float) -> tuple[float, int]:
    """这笔正课钱送多少券：面额 = 正课金额 ÷ 10，一次 10 张。"""
    money = float(base or 0)
    if money <= 0:
        return 0.0, 0
    return round(money / VOUCHER_COUNT, 2), VOUCHER_COUNT


def voucher_base(items: list[dict]) -> float:
    """本笔缴费里"正课"那部分的钱 —— 只有正课才送代金券。"""
    with _connect() as con:
        row = con.execute("SELECT id FROM hour_types WHERE name = '正课'").fetchone()
    if row is None:
        return 0.0
    zhengke = int(row["id"])
    return sum(float(i.get("amount") or 0) for i in items if int(i["hour_type_id"]) == zhengke)


def list_vouchers(student_id: int | None = None, today: str = "") -> list[dict]:
    """代金券批次，带"还剩几张"和"过没过期"。"""
    sql = """
        SELECT v.*, s.name AS student_name,
               v.count - (SELECT COUNT(*) FROM payments p WHERE p.voucher_id = v.id) AS remain
          FROM vouchers v
          JOIN students s ON s.id = v.student_id
         WHERE 1 = 1
    """
    args: list[Any] = []
    if student_id is not None:
        sql += " AND v.student_id = ?"
        args.append(student_id)
    sql += " ORDER BY v.issued_on, v.id"
    day = today or date.today().isoformat()
    with _connect() as con:
        rows = [dict(r) for r in con.execute(sql, args).fetchall()]
    for row in rows:
        row["remain"] = max(0, int(row["remain"] or 0))
        row["expired"] = bool(row["expires_on"]) and row["expires_on"] < day
        row["usable"] = row["remain"] > 0 and not row["expired"]
    return rows


def available_vouchers(student_id: int, today: str = "") -> list[dict]:
    """这个孩子现在能用的券。"""
    return [v for v in list_vouchers(student_id, today) if v["usable"]]


def voucher_uses(voucher_id: int) -> list[dict]:
    """这张券在哪几笔缴费里用掉了。"""
    with _connect() as con:
        rows = con.execute(
            """SELECT p.id, p.paid_on, p.voucher_amount, s.name AS student_name
                 FROM payments p JOIN students s ON s.id = p.student_id
                WHERE p.voucher_id = ? ORDER BY p.paid_on, p.id""",
            (voucher_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def issue_vouchers(
    student_id: int, payment_id: int, base: float, issued_on: str
) -> int | None:
    """缴费送券。base 是正课那部分的钱；没正课或金额为 0 就不送。"""
    face, count = voucher_plan(base)
    if face <= 0 or count <= 0:
        return None
    try:
        day = date.fromisoformat(issued_on) if issued_on else date.today()
    except ValueError:
        day = date.today()
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO vouchers
                   (student_id, payment_id, face, count, issued_on, expires_on, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (
                student_id,
                payment_id,
                face,
                count,
                day.isoformat(),
                _add_months(day, VOUCHER_MONTHS).isoformat(),
                _today(),
            ),
        )
        return int(cur.lastrowid)


def _drop_unused_vouchers(con: sqlite3.Connection, payment_id: int) -> None:
    """这笔缴费送的券，一张都还没用出去就收回（改错了能撤干净）。"""
    for row in con.execute(
        "SELECT id FROM vouchers WHERE payment_id = ?", (payment_id,)
    ).fetchall():
        used = con.execute(
            "SELECT COUNT(*) AS c FROM payments WHERE voucher_id = ?", (row["id"],)
        ).fetchone()
        if not int(used["c"] or 0):
            con.execute("DELETE FROM vouchers WHERE id = ?", (row["id"],))


def _pick_voucher(
    student_id: int,
    voucher_id: int | None,
    used_on: str,
    current_payment_id: int | None = None,
) -> tuple[float, int | None]:
    """检查这张券能不能用：得是这个孩子的、还有剩、没过期。"""
    if not voucher_id:
        return 0.0, None
    match = next(
        (v for v in list_vouchers(student_id, used_on) if int(v["id"]) == int(voucher_id)),
        None,
    )
    if match is None:
        raise ValueError("找不到这张代金券")
    if match["usable"]:
        return float(match["face"]), int(match["id"])
    # 改一笔缴费时，它自己用掉的那张要允许保留（可能已经是最后一张/已经过期）
    if current_payment_id:
        with _connect() as con:
            row = con.execute(
                "SELECT voucher_id FROM payments WHERE id = ?", (current_payment_id,)
            ).fetchone()
        if row is not None and int(row["voucher_id"] or 0) == int(voucher_id):
            return float(match["face"]), int(match["id"])
    raise ValueError("这张代金券用不了（已经用完或者过期了）")


def list_payment_items(payment_id: int) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            """SELECT pi.*, ht.name AS hour_type_name,
                      lv.subject AS subject, lv.name AS level_name,
                      u.display_name AS owner_teacher_name,
                      e.class_id AS class_id,
                      t.name AS class_name, t.weekday AS class_weekday,
                      t.start_time AS class_start_time
                 FROM payment_items pi
                 LEFT JOIN hour_types ht ON ht.id = pi.hour_type_id
                 LEFT JOIN levels lv ON lv.id = pi.level_id
                 LEFT JOIN users u ON u.id = pi.owner_teacher_id
                 LEFT JOIN enrollments e ON e.id = pi.enrollment_id
                 LEFT JOIN schedule_templates t ON t.id = e.class_id
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
                       lv.subject AS subject, lv.name AS level_name,
                       u.display_name AS owner_teacher_name,
                       e.class_id AS class_id,
                       t.name AS class_name, t.weekday AS class_weekday,
                       t.start_time AS class_start_time
                  FROM payment_items pi
                  LEFT JOIN hour_types ht ON ht.id = pi.hour_type_id
                  LEFT JOIN levels lv ON lv.id = pi.level_id
                  LEFT JOIN users u ON u.id = pi.owner_teacher_id
                  LEFT JOIN enrollments e ON e.id = pi.enrollment_id
                  LEFT JOIN schedule_templates t ON t.id = e.class_id
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
        # 这笔送出去的券，还没用就一起收回；用掉的就留着（券已经给家长了）
        _drop_unused_vouchers(con, payment_id)
        con.execute("DELETE FROM payment_items WHERE payment_id = ?", (payment_id,))
        con.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
    if row is not None:
        recompute_student(int(row["student_id"]))
        refresh_student(int(row["student_id"]))


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
    SELECT p.*, s.name AS student_name, ht.name AS hour_type_name,
           u.display_name AS teacher_name
      FROM payments p
      JOIN students s ON s.id = p.student_id
      LEFT JOIN hour_types ht ON ht.id = p.hour_type_id
      LEFT JOIN users u ON u.id = p.teacher_id
"""


def get_payment(payment_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute(_PAYMENT_SELECT + " WHERE p.id = ?", (payment_id,)).fetchone()
    return dict(row) if row else None


def list_payments(
    student_id: int | None = None, limit: int = 300, month: str | None = None
) -> list[dict]:
    sql = _PAYMENT_SELECT
    args: list[Any] = []
    where: list[str] = []
    if student_id is not None:
        where.append("p.student_id = ?")
        args.append(student_id)
    if month:
        where.append("p.paid_on LIKE ?")
        args.append(f"{month}%")
    if where:
        sql += " WHERE " + " AND ".join(where)
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
