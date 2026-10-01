"""一个不依赖浏览器的自检脚本：把界面搭起来、把按钮点一遍，看看数据对不对。

运行： .venv/bin/python tests/smoke_test.py
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="class-hours-test-")
os.environ["CLASS_HOURS_DB"] = str(pathlib.Path(TMP) / "test.db")

import flet as ft  # noqa: E402

import db  # noqa: E402
from app_ui import ClassHoursApp  # noqa: E402

# 自检里没有真的页面，控件上的 .update() 直接跳过
ft.BaseControl.update = lambda self: None


class StubPage:
    """冒充 Flet 的 Page，只在内存里搭积木，不开窗口。"""

    def __init__(self, width: int = 1200, height: int = 900):
        self.width = width
        self.height = height
        self.controls: list = []
        self.dialogs: list = []
        self.overlay: list = []
        self.services: list = []
        self.theme_mode = None
        self.bgcolor = None
        self.padding = 0
        self.title = ""
        self.on_resize = None

    def clean(self):
        self.controls.clear()

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        pass

    def show_dialog(self, dlg):
        self.dialogs.append(dlg)

    def pop_dialog(self):
        if self.dialogs:
            self.dialogs.pop()

    def run_task(self, handler, *args):
        pass


def walk(control):
    yield control
    for attr in (
        "controls",
        "content",
        "actions",
        "title",
        "subtitle",
        "label",
        "leading",
        "trailing",
        "icon",
    ):
        value = getattr(control, attr, None)
        if isinstance(value, list):
            for v in value:
                if isinstance(v, ft.BaseControl):
                    yield from walk(v)
        elif isinstance(value, ft.BaseControl):
            yield from walk(value)


def find_field(control, label: str) -> ft.TextField:
    for c in walk(control):
        if isinstance(c, ft.TextField) and (c.label or "") == label:
            return c
    raise AssertionError(f"找不到输入框：{label}")


def find_dropdown(control, label: str) -> ft.Dropdown:
    for c in walk(control):
        if isinstance(c, ft.Dropdown) and (c.label or "") == label:
            return c
    raise AssertionError(f"找不到下拉框：{label}")


def find_button(control, text: str):
    for c in walk(control):
        if isinstance(c, (ft.Button, ft.TextButton)) and c.content == text:
            return c
    raise AssertionError(f"找不到按钮：{text}")


def find_checkbox(control, name_prefix: str) -> ft.Checkbox:
    for c in walk(control):
        if isinstance(c, ft.Checkbox) and str(c.label or "").startswith(name_prefix):
            return c
    raise AssertionError(f"找不到勾选框：{name_prefix}")


def find_text(control, needle: str) -> bool:
    for c in walk(control):
        if isinstance(c, ft.Text) and needle in str(c.value or ""):
            return True
    return False


def click(control, label: str):
    find_button(control, label).on_click(None)


def top_dialog(page: StubPage):
    assert page.dialogs, "没有打开任何对话框"
    return page.dialogs[-1]


checks = 0


def ok(condition, message):
    global checks
    assert condition, f"✗ {message}"
    checks += 1
    print(f"  ✓ {message}")


print("1. 初始化数据库")
db.init_db()
ok(len(db.list_hour_types()) == 5, "五种课时账户建好了")
ok(len(db.list_class_types()) == 7, "七种课型建好了")
ok(len(db.list_levels()) == 7, "七个等级建好了")

rules = {c["name"]: c for c in db.list_class_types()}
ok(rules["竞赛"]["primary_name"] == "竞赛", "竞赛课先扣竞赛课时")
ok(rules["竞赛"]["fallback_name"] == "正课", "竞赛课时不够补扣正课")
ok(rules["考级"]["fallback_name"] == "正课", "考级课时不够补扣正课")
ok(rules["试听"]["deduct"] == 0, "试听不扣课时")
ok(rules["替课"]["deduct"] == 1 and rules["替课"]["primary_name"] == "正课", "老师替课照扣正课课时")

print("2. 搭界面（宽屏 / 手机）")
page = StubPage(width=1200)
app = ClassHoursApp(page)
app.render()
ok(find_text(page.controls[0], "请用账号登录"), "打开先要登录")
find_field(page.controls[0], "用户名").value = "root"
find_field(page.controls[0], "密码").value = "wrong-password"
click(page.controls[0], "登录")
ok(app.user is None, "密码不对进不去")
ok(find_text(page.controls[0], "用户名或密码不对"), "提示用户名或密码不对")
find_field(page.controls[0], "用户名").value = "root"
find_field(page.controls[0], "密码").value = db.DEFAULT_ADMIN_PASSWORD
click(page.controls[0], "登录")
ok(app.user is not None and app.user["role"] == "root", "管理员登录成功")
ok(app.is_admin(), "管理员有全部权限")

ok(find_text(page.controls[0], "还没有学员"), "宽屏：左侧导航 + 空列表")
ok(find_text(page.controls[0], "设置"), "左侧导航有「设置」")
ok(
    any(isinstance(c, ft.Container) and c.width == 96 for c in walk(page.controls[0])),
    "宽屏用左侧竖排导航",
)

phone_page = StubPage(width=390)
phone_app = ClassHoursApp(phone_page)
phone_app.user = app.user
phone_app.render()
ok(
    any(isinstance(c, ft.Container) and c.height == 56 for c in walk(phone_page.controls[0])),
    "手机用底部横排导航",
)
ok(find_text(phone_page.controls[0], "还没有学员"), "手机上也显示学员列表")

app._goto(1)
ok(find_text(page.controls[0], "还没有上课记录"), "点「上课记录」能切过去")
app._goto(2)
ok(find_text(page.controls[0], "还没有缴费记录"), "点「缴费」能切过去")
app._goto(3)
ok(find_text(page.controls[0], "兑换记录"), "点「积分」能切过去")
app._goto(4)
ok(find_text(page.controls[0], "还没有试听记录"), "点「试听」能切过去")
app._goto(5)
ok(find_text(page.controls[0], "课时不够要提醒的"), "点「报表」能切过去")
app._goto(6)
ok(find_text(page.controls[0], "课型与扣课时规则"), "点「课程设置」能切过去")
app._goto(0)
ok(find_text(page.controls[0], "还没有学员"), "点「学员」能切回来")

print("3. 新增学员")
app._open_new_student()
dlg = top_dialog(page)
find_field(dlg, "姓名 *").value = "张晨希"
find_field(dlg, "年级").value = "六年级"
find_field(dlg, "联系电话").value = "13800000000"
find_dropdown(dlg, "性别").value = "女"
click(dlg, "保存")
students = db.list_students()
ok(len(students) == 1 and students[0]["name"] == "张晨希", "学员存进去了")
sid = students[0]["id"]

print("4. 学员详情页")
app.open_student(sid)
tree = page.controls[0]
ok(find_text(tree, "张晨希"), "详情页显示姓名")
ok(find_text(tree, "课时账户"), "详情页有课时账户")
ok(find_text(tree, "报名课程"), "详情页有报名课程")

print("5. 改档案")
save_btn = None
for c in walk(tree):
    if isinstance(c, (ft.Button, ft.TextButton)) and c.content == "保存":
        save_btn = c
find_field(tree, "年级").value = "初一"
save_btn.on_click(None)
ok(db.get_student(sid)["grade"] == "初一", "档案改好了")

print("6. 报名课程")
then = db.list_enrollments(sid)
ok(then == [], "还没报名")
app._open_enrollment_dialog(sid, None)
dlg = top_dialog(page)
levels = db.list_levels()
gpl = next(l for l in levels if db.level_full_name(l) == "GPL-Lvl-03")
find_dropdown(dlg, "科目-等级").value = str(gpl["id"])
find_dropdown(dlg, "课型").value = str(next(c["id"] for c in db.list_class_types() if c["name"] == "正课"))
find_field(dlg, "单次时长（分钟）").value = "90"
click(dlg, "保存")
enrollments = db.list_enrollments(sid)
ok(len(enrollments) == 1, "报名记录建好了")
ok(enrollments[0]["level_name"] == "Lvl-03", "报名绑定了等级")

print("7. 课时充值与剩余")
app._open_hours_dialog(sid, None)
dlg = top_dialog(page)
find_field(dlg, "数量（课时）").value = "24"
find_field(dlg, "备注").value = "缴费 3000"
click(dlg, "保存")
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 24, "正课课时 +24")

app._open_hours_dialog(sid, accounts["正课"]["hour_type_id"])
dlg = top_dialog(page)
find_dropdown(dlg, "类型").value = "扣减"
find_field(dlg, "数量（课时）").value = "22"
click(dlg, "保存")
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 2, "扣完剩 2 课时")
ok(accounts["正课"]["charged"] == 24 and accounts["正课"]["used"] == 22, "总课时／已用分得清")

print("8. 剩余课时不足会提醒")
app.open_student(None)
ok(any(isinstance(c, ft.Icon) and c.icon == ft.Icons.ERROR_OUTLINE for c in walk(page.controls[0])), "列表上出现提醒图标")
ok(find_text(page.controls[0], "正课 2"), "列表显示剩余课时")

print("9. 不限课时开关")
db.set_unlimited(sid, accounts["正课"]["hour_type_id"], True)
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["unlimited"] == 1, "不限课时打开了")
ok(db.hours_text(list(accounts.values())).find("不限") >= 0, "列表上显示不限")
db.set_unlimited(sid, accounts["正课"]["hour_type_id"], False)

print("10. 课程设置")
app.tab = 1
app.render()
app._open_level_dialog(None)
dlg = top_dialog(page)
find_field(dlg, "科目（如 GPL、STEM）").value = "PY"
find_field(dlg, "等级／阶段（如 Lvl-01）").value = "Lvl-02"
find_field(dlg, "默认时长（分钟）").value = "60"
click(dlg, "保存")
ok(any(db.level_full_name(l) == "PY-Lvl-02" for l in db.list_levels()), "新增等级成功")

victim = next(l for l in db.list_levels() if db.level_full_name(l) == "PY-Lvl-02")
app._open_level_dialog(victim)
dlg = top_dialog(page)
find_field(dlg, "默认时长（分钟）").value = "45"
click(dlg, "保存")
ok(any(l["default_minutes"] == 45 for l in db.list_levels() if l["id"] == victim["id"]), "改等级成功")

app._open_class_type_dialog(rules["替课"])
dlg = top_dialog(page)
find_button(dlg, "保存").on_click(None)
ok(len(db.list_class_types()) == 7, "课型规则能保存")

print("11. 上课记录与点名")
zhengke = next(c for c in db.list_class_types() if c["name"] == "正课")
jingsai = next(c for c in db.list_class_types() if c["name"] == "竞赛")
gpl3 = next(l for l in db.list_levels() if db.level_full_name(l) == "GPL-Lvl-03")
zhengke_hour_id = next(a["hour_type_id"] for a in db.get_accounts(sid) if a["name"] == "正课")
db.add_hours(sid, zhengke_hour_id, 22, kind="调整", note="自检：把课时补回 24")
ok({a["name"]: a for a in db.get_accounts(sid)}["正课"]["balance"] == 24, "先凑够 24 课时")

app.tab = 1
app.lesson_id = None
app.render()
ok(find_text(page.controls[0], "还没有上课记录"), "上课记录一开始是空的")

app._open_lesson_dialog()
dlg = top_dialog(page)
find_field(dlg, "日期").value = "2026-09-05"
find_field(dlg, "开始时间").value = "08:30"
find_field(dlg, "时长（分钟）").value = "90"
find_dropdown(dlg, "课型").value = str(zhengke["id"])
find_dropdown(dlg, "等级（可不选）").value = str(gpl3["id"])
find_field(dlg, "课评（一节课一份，全班共用）").value = "今天讲循环"
find_checkbox(dlg, "张晨希").value = True
click(dlg, "保存")

lessons = db.list_lessons()
ok(len(lessons) == 1, "课次建好了")
lesson = lessons[0]
rows = db.list_attendance(lesson["id"])
ok(len(rows) == 1 and rows[0]["minutes"] == 90, "点名记录带上了默认时长")
ok(db.get_lesson(lesson["id"])["comment"] == "今天讲循环", "课评存在课次上")
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 22.5, "出勤自动扣了 1.5 课时")
ok(db.student_points(sid) == 30, "出勤＋纪律＋表现 = 30 分")

app._save_attendance_flag(rows[0]["id"], "attendance", 1, False)
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 24, "改成请假，课时退回来")
ok(db.student_points(sid) == 0, "请假不加分")

app._save_attendance_flag(rows[0]["id"], "attendance", 0, True)
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 22.5, "改回出勤，课时又扣上")
ok(db.student_points(sid) == 10, "请假时清掉的纪律和表现会重新勾，所以先只算 10 分")

app._save_attendance_value(rows[0]["id"], "bonus", 0, "25")
ok(db.student_points(sid) == 35, "突出发挥 25 分算进积分")

app._open_lesson_dialog()
dlg = top_dialog(page)
find_field(dlg, "时长（分钟）").value = "120"
find_dropdown(dlg, "课型").value = str(jingsai["id"])
find_checkbox(dlg, "张晨希").value = True
click(dlg, "保存")
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(
    accounts["竞赛"]["balance"] == 0 and accounts["正课"]["balance"] == 20.5,
    "竞赛课时不够，自动从正课扣了 2 课时",
)
ok(len(db.list_lessons()) == 2, "第二节课也在")

app.open_lesson(lesson["id"])
ok(find_text(page.controls[0], "点名（1 人）"), "课次详情显示点名人数")
ok(find_text(page.controls[0], "今天讲循环"), "课次详情显示课评")

db.delete_lesson(lessons[0]["id"])
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 22, "删掉正课那节，1.5 课时退回来")
ok(db.student_points(sid) == 30, "删掉一节课，积分也退回来")
for l in db.list_lessons():
    db.delete_lesson(l["id"])
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 24 and db.student_points(sid) == 0, "全部删掉后账回到原样")

print("12. 缴费记录")
app.tab = 2
app.render()
app._open_payment_dialog(None, sid)
dlg = top_dialog(page)
find_field(dlg, "金额（元）").value = "3000"
find_field(dlg, "数量（课时）").value = "24"
find_field(dlg, "备注").value = "微信转账"
find_dropdown(dlg, "课时类型").value = str(zhengke_hour_id)
find_dropdown(dlg, "报的等级").value = str(gpl3["id"])
click(dlg, "保存")
payments = db.list_payments(sid)
ok(len(payments) == 1 and payments[0]["amount"] == 3000, "缴费记下来了")
items = db.list_payment_items(payments[0]["id"])
ok(
    len(items) == 1 and items[0]["hour_type_name"] == "正课" and items[0]["hours"] == 24,
    "记的是正课 24 课时",
)
ok(items[0]["level_id"] == gpl3["id"], "缴费行上记着是哪个等级")
ok(
    len(db.list_enrollments(sid)) == 1,
    "这个孩子本来就有这条报名，缴费时选等级不会重复建",
)
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 48, "缴费后正课课时自动加上")
ok(accounts["正课"]["charged"] == 70, "总课时还算得对（24＋22＋24）")
ok(db.income_total(student_id=sid) == 3000, "这个孩子的累计缴费是 3000")
today_month = date.today().strftime("%Y-%m")
ok(db.income_total(month=today_month) == 3000, "本月收入算得对")

pay = payments[0]
app._open_payment_dialog(pay)
dlg = top_dialog(page)
find_field(dlg, "数量（课时）").value = "30"
click(dlg, "保存")
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 54, "改课时数，账户跟着变")

app.tab = 0
app.open_student(sid)
ok(find_text(page.controls[0], "缴费记录（累计 3000 元）"), "学员详情能看到缴费记录")
ok(find_text(page.controls[0], "微信转账"), "学员详情显示备注")

db.delete_payment(pay["id"])
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 24, "删掉缴费，课时一起扣回去")
ok(db.income_total(student_id=sid) == 0, "删掉缴费，收入也不算了")

print("13. 兑换积分")
lesson_id = db.create_lesson("2026-09-12", "10:30", 90, zhengke["id"], gpl3["id"], "讲循环")
db.add_attendance(lesson_id, sid)
ok(db.student_points(sid) == 30, "上课赚了 30 分")

app.tab = 3
app.render()
ok(find_text(page.controls[0], "30 分"), "积分页显示孩子的积分")
app._open_redemption_dialog(None, sid)
dlg = top_dialog(page)
find_field(dlg, "扣多少分").value = "20"
find_field(dlg, "换了什么（可不填）").value = "小玩具"
click(dlg, "保存")
redemptions = db.list_redemptions(sid)
ok(len(redemptions) == 1 and redemptions[0]["change"] == -20, "兑换记下来了")
ok(db.student_points(sid) == 10, "积分扣掉了 20")

app._open_redemption_dialog(redemptions[0])
dlg = top_dialog(page)
find_field(dlg, "扣多少分").value = "5"
click(dlg, "保存")
ok(db.student_points(sid) == 25, "改成扣 5 分，积分跟着改")

app.tab = 0
app.open_student(sid)
ok(find_text(page.controls[0], "积分明细（现在 25 分）"), "学员详情有积分明细")
ok(find_text(page.controls[0], "小玩具"), "积分明细显示了兑换原因")

app.tab = 3
app.render()
ok(find_text(page.controls[0], "小玩具"), "积分页能看到兑换记录")
db.delete_redemption(redemptions[0]["id"])
ok(db.student_points(sid) == 30, "删掉兑换，积分加回来")
db.delete_lesson(lesson_id)
ok(db.student_points(sid) == 0, "删掉那节课，积分也撤了")

print("14. 请假 → 待补课 → 补课")
zhengke_balance = lambda: {a["name"]: a for a in db.get_accounts(sid)}["正课"]["balance"]
lesson_id = db.create_lesson("2026-09-19", "10:30", 90, zhengke["id"], gpl3["id"])
att = db.add_attendance(lesson_id, sid)
ok(zhengke_balance() == 22.5, "出勤先扣了 1.5 课时")
ok(db.pending_makeup_count(sid) == 0, "出勤的时候没有待补课")

app._save_attendance_flag(att, "attendance", 1, False)
ok(zhengke_balance() == 24, "改成请假，课时退回来")
ok(db.pending_makeup_count(sid) == 1, "请假自动生成一条待补课")

app.tab = 1
app.lesson_id = None
app.render()
ok(find_text(page.controls[0], "待补课（1 条）"), "上课记录页顶部显示待补课")

makeup = db.list_makeups("待补", sid)[0]
ok(makeup["student_name"] == "张晨希" and makeup["lesson_date"] == "2026-09-19", "待补课连着原来那节")
app._open_arrange_makeup_dialog(makeup)
dlg = top_dialog(page)
find_field(dlg, "补课日期").value = "2026-09-26"
find_field(dlg, "开始时间").value = "13:00"
find_field(dlg, "时长（分钟）").value = "90"
click(dlg, "保存")
ok(db.pending_makeup_count(sid) == 0, "安排完就不在待补列表里了")
lessons = db.list_lessons()
ok(len(lessons) == 2, "多出来一节补课")
makeup_lesson = next(l for l in lessons if l["kind"] == "补课")
ok(makeup_lesson["lesson_date"] == "2026-09-26", "补课排在 9月26日")
rows = db.list_attendance(makeup_lesson["id"])
ok(len(rows) == 1 and rows[0]["student_id"] == sid, "补课那节点了孩子的名")
ok(zhengke_balance() == 22.5, "补课照扣 1.5 课时")
done = db.get_makeup(makeup["id"])
ok(done["status"] == "已补" and done["makeup_lesson_id"] == makeup_lesson["id"], "待补课关掉并关联回补课那节")

app.tab = 1
app.open_lesson(makeup_lesson["id"])
tree = page.controls[0]
ok(find_text(tree, "这是给「张晨希」补的一节课"), "补课那节写着是给谁补的")
ok(find_text(tree, "补的是 9月19日 周六 10:30 请假的那节"), "补课那节写着补的是哪一节")
try:
    find_button(tree, "看原课")
    linked = True
except AssertionError:
    linked = False
ok(linked, "能从补课点回原来那节")
app.open_lesson(None)
ok(find_text(page.controls[0], "补 张晨希 9月19日 周六 请假的那节"), "课次列表上也写明补的是哪节")

app.tab = 0
app.open_student(sid)
tree = page.controls[0]
ok(find_text(tree, "补课情况"), "学员页有补课情况")
ok(find_text(tree, "现在没有要补的课"), "没欠课的时候也写明")
ok(find_text(tree, "已经补过的：9月19日 周六 → 9月26日 周六"), "学员页能看到补过的那次")

app.tab = 0
app.render()
ok(not find_text(page.controls[0], "待补课\n"), "学员列表上没有待补课标记了")
lesson2 = db.create_lesson("2026-10-10", "10:30", 90, zhengke["id"], gpl3["id"])
att2 = db.add_attendance(lesson2, sid)
app._save_attendance_flag(att2, "attendance", 1, False)
ok(db.pending_makeup_count(sid) == 1, "又请了一次假")
app.tab = 0
app.open_student(sid)
ok(find_text(page.controls[0], "补课情况（有 1 节要补）"), "学员页写明他有一节要补")
try:
    find_button(page.controls[0], "安排补课")
    can_arrange = True
except AssertionError:
    can_arrange = False
ok(can_arrange, "学员页上就能直接安排补课")
app._save_attendance_flag(att2, "attendance", 0, True)
ok(db.pending_makeup_count(sid) == 0, "改回出勤，待补课自动撤掉")
app._save_attendance_flag(att2, "attendance", 1, False)
db.cancel_makeup(db.list_makeups("待补", sid)[0]["id"], "家长不补了")
ok(db.pending_makeup_count(sid) == 0, "标记「不补了」也能关掉")
for l in db.list_lessons():
    db.delete_lesson(l["id"])
ok(zhengke_balance() == 24, "把课次都删掉，课时回到 24")

print("15. 试听跟进")
app.tab = 4
app.trial_filter = ""
app.render()
app._open_trial_dialog()
dlg = top_dialog(page)
find_field(dlg, "孩子姓名 *").value = "徐在贤"
find_field(dlg, "年级").value = "四年级"
find_field(dlg, "家长称呼（妈妈／爸爸）").value = "妈妈"
find_field(dlg, "联系电话").value = "13900000000"
find_field(dlg, "来源").value = "朋友介绍"
find_field(dlg, "试听日期（可不填）").value = "2026-09-30"
find_field(dlg, "备注（孩子情况、家长想法…）").value = "试过核桃，妈妈是老师"
click(dlg, "保存")
trials = db.list_trials()
ok(len(trials) == 1 and trials[0]["name"] == "徐在贤", "试听记录建好了")
ok(trials[0]["status"] == "待试听", "默认是待试听")
ok(db.trial_counts()["待试听"] == 1, "按状态数得出来")
ok(find_text(page.controls[0], "徐在贤"), "试听列表上能看到")
ok(find_text(page.controls[0], "试过核桃，妈妈是老师"), "备注也能看到")

trial = trials[0]
app._set_trial_filter("已报名")
ok(not find_text(page.controls[0], "试过核桃"), "按状态筛选能过滤")
app._set_trial_filter("")

student_count = len(db.list_students())
new_sid = db.convert_trial_to_student(trial["id"])
ok(len(db.list_students()) == student_count + 1, "转正式后多了一份学员档案")
new_student = db.get_student(new_sid)
ok(new_student["name"] == "徐在贤" and new_student["grade"] == "四年级", "档案信息带过去了")
ok("朋友介绍" in new_student["note"] and "妈妈是老师" in new_student["note"], "来源和备注也带过去了")
after = db.get_trial(trial["id"])
ok(after["status"] == "已报名" and after["student_id"] == new_sid, "试听记录标成已报名并连上档案")
ok(db.convert_trial_to_student(trial["id"]) == new_sid, "重复点转正式不会建第二份档案")
app.render()
try:
    find_button(page.controls[0], "看学员")
    has_link = True
except AssertionError:
    has_link = False
ok(has_link, "转过的记录显示「看学员」")
db.delete_trial(trial["id"])
ok(db.list_trials() == [], "试听记录能删掉")
ok(len(db.list_students()) == student_count + 1, "删试听记录不影响正式档案")
db.delete_student(new_sid)

print("16. 教案、照片、附件")


class FakeFile:
    def __init__(self, name, data):
        self.name = name
        self.bytes = data


class FakeEvent:
    def __init__(self, files):
        self.files = files


lesson_file = db.create_lesson(
    "2026-10-17", "10:30", 90, zhengke["id"], gpl3["id"], "讲数组", "先复习循环，再讲数组"
)
db.add_attendance(lesson_file, sid)
ok(db.get_lesson(lesson_file)["plan"] == "先复习循环，再讲数组", "教案存得下")
app.tab = 1
app.open_lesson(lesson_file)
ok(find_text(page.controls[0], "先复习循环，再讲数组"), "课次详情显示教案")
ok(find_text(page.controls[0], "附件（0 个）"), "课次详情有附件区")

rows = db.list_attendance(lesson_file)
att_photo = rows[0]["id"]
app._set_upload_target("attendance", att_photo, "照片")
app._on_files_picked(FakeEvent([FakeFile("课堂.jpg", b"x" * 1234)]))
photos = db.list_files("attendance", att_photo, "照片")
ok(len(photos) == 1 and photos[0]["filename"] == "课堂.jpg", "照片记到数据库里")
photo_path = db.UPLOAD_DIR / photos[0]["stored_name"]
ok(photo_path.exists() and photo_path.stat().st_size == 1234, "照片真的写进磁盘了")
ok(db.file_url(photos[0]).endswith(photos[0]["stored_name"]), "图片地址拼得对")
ok(db.human_size(1234) == "1 KB", "文件大小显示成人话")

app.open_lesson(lesson_file)
ok(
    any(isinstance(c, ft.Image) for c in walk(page.controls[0])),
    "课次详情里能看到照片",
)

app._set_upload_target("lesson", lesson_file, "附件")
app._on_files_picked(FakeEvent([FakeFile("课件.pdf", b"pdf-bytes")]))
files = db.list_files("lesson", lesson_file, "附件")
ok(len(files) == 1 and files[0]["filename"] == "课件.pdf", "附件记上了")
ok(find_text(page.controls[0], "课件.pdf"), "详情页列出来了")

db.delete_file(photos[0]["id"])
ok(not photo_path.exists(), "删照片时磁盘文件一起删了")
db.delete_lesson(lesson_file)
ok(db.list_files("lesson", lesson_file, "附件") == [], "删课次时附件记录一起清掉")
ok(not (db.UPLOAD_DIR / files[0]["stored_name"]).exists(), "磁盘上的附件也删了")

print("17. 排课表")
app.tab = 1
app.lesson_id = None
app.show_schedule = False
app.render()
app.open_schedule(True)
ok(find_text(page.controls[0], "还没有固定课表"), "排课表一开始是空的")

app._open_template_dialog()
dlg = top_dialog(page)
find_dropdown(dlg, "星期几").value = "5"  # 周六
find_field(dlg, "开始时间").value = "10:30"
find_field(dlg, "时长（分钟）").value = "90"
find_dropdown(dlg, "课型").value = str(zhengke["id"])
find_dropdown(dlg, "等级（可不选）").value = str(gpl3["id"])
find_checkbox(dlg, "张晨希").value = True
click(dlg, "保存")
templates = db.list_templates()
ok(len(templates) == 1, "固定课表建好了")
ok(
    templates[0]["start_time"] == "10:30"
    and templates[0]["student_count"] == 1
    and templates[0]["weekday"] == 5,
    "记下了星期几、时间和人数",
)
ok(db.template_student_ids(templates[0]["id"]) == [sid], "记住了固定来的孩子")

app.open_schedule(True)
app.schedule_date = "2026-10-03"  # 周六
app.render()
ok(find_text(page.controls[0], "这天的课"), "排课表能看某一天的课")
try:
    find_button(page.controls[0], "点名")
    has_button = True
except AssertionError:
    has_button = False
ok(has_button, "这天有待点名的课")

app._roll_call(templates[0]["id"])
lessons = db.list_lessons()
ok(len(lessons) == 1 and lessons[0]["lesson_date"] == "2026-10-03", "照课表建出了一节课")
ok(len(db.list_attendance(lessons[0]["id"])) == 1, "孩子自动进了名单")
ok(
    db.create_lesson_from_template(templates[0]["id"], "2026-10-03") == lessons[0]["id"],
    "同一天不会重复建课",
)
app.open_schedule(True)
app.schedule_date = "2026-10-03"
app.render()
try:
    find_button(page.controls[0], "已点名 · 进去看")
    rolled = True
except AssertionError:
    rolled = False
ok(rolled, "建过的课显示已点名")
ok(find_text(page.controls[0], "每周六"), "固定课表里写着每周六")

db.delete_template(templates[0]["id"])
ok(db.list_templates() == [], "课表能删掉")
for l in db.list_lessons():
    db.delete_lesson(l["id"])

print("18. 删除与级联")
db.delete_student(sid)
ok(db.list_students() == [], "学员删掉了")
ok(db.list_enrollments(sid) == [], "报名一起删掉了")
ok(db.list_hour_transactions(sid) == [], "课时流水一起删掉了")
ok(db.list_payments(sid) == [], "缴费记录一起删掉了")
ok(db.list_redemptions(sid) == [], "兑换记录一起删掉了")

print("19. 重名／空名保护")
try:
    db.create_student({"name": "  "})
    raise AssertionError("空名字应该被拦住")
except ValueError:
    checks += 1
    print("  ✓ 空名字被拦住")
a = db.create_student({"name": "萱萱"})
b = db.create_student({"name": "萱萱"})
ok(a != b and len(db.list_students(keyword="萱萱")) == 2, "同名的两个孩子可以各自建档")
ok(db.list_students(status="停课") == [], "按状态筛选能用")

print("20. 课时明细能改能删（输错了能改回来）")
sid2 = db.create_student({"name": "课时测试", "grade": "三年级"})
db.create_enrollment(sid2, gpl3["id"], zhengke["id"], 90)
hour_id = next(a["hour_type_id"] for a in db.get_accounts(sid2) if a["name"] == "正课")
def balance2():
    return {a["name"]: a for a in db.get_accounts(sid2)}["正课"]["balance"]

tx = db.add_hours(sid2, hour_id, 10, kind="充值", note="一开始写错了", source_type="manual")
ok(balance2() == 10, "先记了一笔 10 课时")
app.tab = 0
app.open_student(sid2)
app._open_hour_ledger(sid2, hour_id)
dlg = top_dialog(page)
ok(find_text(dlg, "一开始写错了"), "明细里能看到这一笔")
ok(find_text(dlg, "手记"), "手记的流水有标记")

db.update_hour_transaction(tx, hour_id, 4, "2026-09-01", "其实只买了 4 课时")
ok(balance2() == 4, "改成 4 课时，账户跟着变")
row = db.get_hour_transaction(tx)
ok(row["note"] == "其实只买了 4 课时" and row["happened_on"] == "2026-09-01", "日期和备注也改了")

db.delete_hour_transaction(tx)
ok(balance2() == 0, "删掉这一笔，课时回到 0")

pay_id = db.create_payment(sid2, "2026-09-05", [{"hour_type_id": hour_id, "hours": 24, "amount": 3000}])
ok(balance2() == 24, "缴费后又加上了 24")
pay_tx = [
    t for t in db.list_hour_transactions(sid2) if t["source_type"].startswith("payment")
][0]
try:
    db.delete_hour_transaction(pay_tx["id"])
    blocked = False
except ValueError:
    blocked = True
ok(blocked, "缴费产生的流水不能在这儿随便删")
db.delete_payment(pay_id)
ok(balance2() == 0, "到缴费页删掉，课时也扣回去")

print("21. 一笔缴费买多种课时（买的＋送的）")
kaoji_id = next(a["hour_type_id"] for a in db.get_accounts(sid2) if a["name"] == "考级")
jingsai_id = next(a["hour_type_id"] for a in db.get_accounts(sid2) if a["name"] == "竞赛")
app.tab = 2
app.render()
app._open_payment_dialog(None, sid2)
dlg = top_dialog(page)
find_dropdown(dlg, "课时类型").value = str(hour_id)
find_field(dlg, "数量（课时）").value = "24"
find_field(dlg, "金额（元）").value = "3000"
# 加一行赠送的考级
add_row_btn = find_button(dlg, "+ 加一行")
add_row_btn.on_click(None)
rows = [f for f in walk(dlg) if isinstance(f, ft.Dropdown) and f.label == "课时类型"]
ok(len(rows) == 2, "能加第二行课时")
rows[1].value = str(kaoji_id)
fields = [f for f in walk(dlg) if isinstance(f, ft.TextField) and f.label == "数量（课时）"]
fields[1].value = "1"
amounts = [f for f in walk(dlg) if isinstance(f, ft.TextField) and f.label == "金额（元）"]
amounts[1].value = "0"
click(dlg, "保存")
multi = db.list_payments(sid2)[0]
items = db.list_payment_items(multi["id"])
ok(len(items) == 2, "这笔缴费有两行课时")
ok(
    items[0]["hour_type_name"] == "正课" and items[0]["amount"] == 3000,
    "正课 24 课时 3000 元",
)
ok(
    items[1]["hour_type_name"] == "考级" and items[1]["hours"] == 1 and items[1]["amount"] == 0,
    "考级 1 课时是赠送",
)
ok(multi["amount"] == 3000, "总额只算买的那部分")
accounts2 = {a["name"]: a for a in db.get_accounts(sid2)}
ok(accounts2["正课"]["balance"] == 24 and accounts2["考级"]["balance"] == 1, "两个账户都加上了")
ok(accounts2["正课"]["paid"] == 24 and accounts2["正课"]["manual"] == 0, "正课来源拆得清：缴费 24 ＋ 手工 0")
ok(accounts2["考级"]["paid"] == 1, "考级的 1 课时也算在缴费来源里")
gift_tx = [t for t in db.list_hour_transactions(sid2) if "赠送" in (t["note"] or "")]
ok(len(gift_tx) == 1 and gift_tx[0]["hour_type_name"] == "考级", "流水上标着赠送")
ok(db.income_total(student_id=sid2) == 3000, "收入还是 3000")

app.tab = 2
app.render()
ok(find_text(page.controls[0], "考级 1 课时（送）"), "缴费列表上标了「送」")

db.delete_payment(multi["id"])
accounts2 = {a["name"]: a for a in db.get_accounts(sid2)}
ok(accounts2["正课"]["balance"] == 0 and accounts2["考级"]["balance"] == 0, "删掉缴费，两种课时都扣回去")

print("22. 提醒只管正课")
app.tab = 5 if False else 0
app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
db.set_unlimited(sid2, hour_id, False)
db.add_hours(sid2, hour_id, 2, kind="充值", note="只剩 2 课时", source_type="manual")
db.add_hours(sid2, kaoji_id, 2, kind="充值", note="考级也只剩 2", source_type="manual")
app.tab = 0
app.open_student(None)
list_tree = page.controls[0]
ok(find_text(list_tree, "正课 2"), "列表上显示正课剩 2")
ok(find_text(list_tree, "考级 2"), "列表上也显示考级剩 2")
ok(
    any(isinstance(c, ft.Icon) and c.icon == ft.Icons.ERROR_OUTLINE for c in walk(list_tree)),
    "剩 2 课时会亮提醒",
)

# 正课补足以后，只有考级剩 2（考级不提醒）就不该再亮提醒
db.add_hours(sid2, hour_id, 10, kind="充值", note="补足正课", source_type="manual")
app.open_student(None)
list_tree = page.controls[0]
ok(
    not any(isinstance(c, ft.Icon) and c.icon == ft.Icons.ERROR_OUTLINE for c in walk(list_tree)),
    "考级剩 2 但不提醒，所以列表上不亮提醒",
)

db.set_hour_type_warn(kaoji_id, True)
db.set_hour_type_warn(hour_id, False)
ok(
    not any(
        a["warn"]
        for a in db.get_accounts(sid2)
        if a["name"] == "正课"
    ),
    "设置里能把正课的提醒关掉",
)
ok(
    {a["name"]: a["warn"] for a in db.get_accounts(sid2)}["考级"] == 1,
    "也能改成提醒考级",
)
db.set_hour_type_warn(hour_id, True)
db.set_hour_type_warn(kaoji_id, False)

print("23. 报表和导出 Excel")
import io  # noqa: E402
import zipfile  # noqa: E402

app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
ok(db.hour_alerts() == [], "课时都够的时候没有提醒")

s3 = db.create_student({"name": "报表测试", "grade": "二年级"})
h3 = next(a["hour_type_id"] for a in db.get_accounts(s3) if a["name"] == "正课")
k3 = next(a["hour_type_id"] for a in db.get_accounts(s3) if a["name"] == "考级")
db.add_hours(s3, h3, 2, kind="充值", source_type="manual")
db.add_hours(s3, k3, 2, kind="充值", source_type="manual")
alerts = db.hour_alerts()
ok(
    len(alerts) == 1 and alerts[0]["student"] == "报表测试" and alerts[0]["account"] == "正课",
    "只提醒正课：正课剩 2 会提醒、考级剩 2 不提醒",
)

today = date.today()
month = today.strftime("%Y-%m")
lesson_report = db.create_lesson(today.isoformat(), "10:00", 90, zhengke["id"], gpl3["id"])
db.add_attendance(lesson_report, s3)
db.create_payment(
    s3, today.isoformat(), [{"hour_type_id": h3, "hours": 24, "amount": 3000}], "微信"
)
stats = db.month_stats(month)
ok(stats["lessons"] == 1 and stats["attendance"] == 1, "这个月上了几节课、点名几人数得对")
ok(stats["hours"] == 1.5, "这个月消耗 1.5 课时")
ok(stats["income"] == 3000 and stats["payments"] == 1, "这个月收入对得上")
counts = db.month_lesson_counts(month)
ok(counts and counts[0]["name"] == "报表测试" and counts[0]["times"] == 1, "月度上课次数排得出来")

app.tab = 5
app.render()
ok(find_text(page.controls[0], "报表"), "报表页能打开")
ok(find_text(page.controls[0], "积分榜"), "报表里有积分榜")
app._export_excel()
dlg = top_dialog(page)
ok(find_text(dlg, "导出好了"), "导出完成有提示")

name, data = app._last_export
ok(name.endswith(".xlsx") and len(data) > 1000, "生成了 Excel 文件")
zf = zipfile.ZipFile(io.BytesIO(data))
names = zf.namelist()
ok(
    "[Content_Types].xml" in names and "xl/workbook.xml" in names,
    "xlsx 结构完整",
)
workbook_xml = zf.read("xl/workbook.xml").decode("utf-8")
for sheet_name in ["学员", "课时账户", "上课记录", "点名明细", "课时流水", "缴费记录", "积分流水", "试听记录", "固定课表"]:
    if sheet_name not in workbook_xml:
        raise AssertionError(f"导出里少了表：{sheet_name}")
checks += 1
print("  ✓ 九张表都在（学员、课时账户、上课记录、点名明细、课时流水、缴费记录、积分流水、试听记录、固定课表）")
sheet1 = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
ok("报表测试" in sheet1, "学员表里能查到数据")
ok(len(list(db.EXPORT_DIR.glob("*.xlsx"))) == 1, "电脑上也存了一份")

db.delete_payment(db.list_payments(s3)[0]["id"])
db.delete_lesson(lesson_report)
db.delete_student(s3)

print("24. 老师和权限")
teacher_id = db.create_user("li", "abcd1234", "李老师", db.ROLE_TEACHER)
ok(db.verify_user("li", "abcd1234") is not None, "老师账号能登录")
ok(db.verify_user("li", "错的") is None, "密码不对登不进")
try:
    db.create_user("li", "abcd1234", "李老师二")
    dup = False
except ValueError:
    dup = True
ok(dup, "用户名不能重复")
try:
    db.delete_user(1) if db.get_user(1)["role"] == db.ROLE_ROOT else None
    last_root = False
except ValueError:
    last_root = True
ok(last_root, "最后一个管理员不能删")

app.user = {
    "id": teacher_id,
    "username": "li",
    "display_name": "李老师",
    "role": db.ROLE_TEACHER,
}
ok(not app.is_admin(), "老师不是管理员")
app.tab = 0
app.open_student(sid2)
ok(not find_text(page.controls[0], "删除学员"), "老师看不到删除学员")
ok(find_text(page.controls[0], "明细"), "老师还能看课时明细")
try:
    find_button(page.controls[0], "调整课时")
    has_adjust = True
except AssertionError:
    has_adjust = False
ok(not has_adjust, "老师看不到调整课时")
app.tab = 2
app.render()
try:
    find_button(page.controls[0], "记一笔")
    teacher_can_pay = True
except AssertionError:
    teacher_can_pay = False
ok(not teacher_can_pay, "老师不能自己记缴费")
app.tab = 1
app.lesson_id = None
app.show_schedule = False
app.render()
ok(find_text(page.controls[0], "记一节课"), "老师还能记一节课、点名")

app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
db.delete_user(teacher_id)
ok(len(db.list_users()) == 1, "老师账号能删掉")

print("25. 缴费时顺手把报名课程建好")
app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
s6 = db.create_student({"name": "新缴费学员", "grade": "三年级"})
ok(db.list_enrollments(s6) == [], "新学员还没有报名课程")
app.tab = 2
app.render()
app._open_payment_dialog(None, s6)
dlg = top_dialog(page)
find_dropdown(dlg, "课时类型").value = str(zhengke["id"])
find_dropdown(dlg, "报的等级").value = str(gpl3["id"])
find_field(dlg, "数量（课时）").value = "24"
find_field(dlg, "金额（元）").value = "3000"
click(dlg, "保存")
enrolls = db.list_enrollments(s6)
ok(
    len(enrolls) == 1
    and enrolls[0]["level_name"] == "Lvl-03"
    and enrolls[0]["class_type_name"] == "正课"
    and enrolls[0]["minutes"] == 90,
    "缴费选了等级，报名课程自动建好了（等级、课型、时长都对）",
)
ok(
    {a["name"]: a["balance"] for a in db.get_accounts(s6)}["正课"] == 24,
    "课时也照常加上了",
)
db.delete_payment(db.list_payments(s6)[0]["id"])
ok(len(db.list_enrollments(s6)) == 1, "删掉缴费后报名课程还在（要删自己去学员页删）")
ok({a["name"]: a["balance"] for a in db.get_accounts(s6)}["正课"] == 0, "课时退回去了")
db.delete_student(s6)

print("26. 先上课后缴费，课时要归位（竞赛课扣竞赛）")
s7 = db.create_student({"name": "先上课后缴费", "grade": "五年级"})
jingsai_h = next(a["hour_type_id"] for a in db.get_accounts(s7) if a["name"] == "竞赛")
zhengke_h = next(a["hour_type_id"] for a in db.get_accounts(s7) if a["name"] == "正课")
js_level = next(l["id"] for l in db.list_levels() if db.level_full_name(l) == "GPL-竞赛-小低组")
lesson_js = db.create_lesson("2026-09-15", "16:00", 120, jingsai["id"], js_level)
db.add_attendance(lesson_js, s7)
ok(
    {a["name"]: a["balance"] for a in db.get_accounts(s7)}["正课"] == -2,
    "竞赛账户还没钱时，先按规则记成欠正课 2 课时",
)
db.create_payment(
    s7, "2026-09-15", [{"hour_type_id": jingsai_h, "hours": 8, "amount": 1000}]
)
accounts7 = {a["name"]: a for a in db.get_accounts(s7)}
ok(
    accounts7["竞赛"]["used"] == 2 and accounts7["竞赛"]["balance"] == 6,
    "交上竞赛课时后，那节竞赛课自动改成扣竞赛",
)
ok(accounts7["正课"]["balance"] == 0, "正课不再被误扣，退回来了")
js_tx = [t for t in db.list_hour_transactions(s7) if t["source_type"] == "lesson"]
ok(len(js_tx) == 1 and js_tx[0]["hour_type_name"] == "竞赛", "流水上只剩一笔，扣的是竞赛")

lesson_js2 = db.create_lesson("2026-09-16", "16:00", 120, jingsai["id"], js_level)
db.add_attendance(lesson_js2, s7)
ok(
    {a["name"]: a["balance"] for a in db.get_accounts(s7)}["竞赛"] == 4,
    "再来一节竞赛课，继续扣竞赛",
)
db.delete_lesson(lesson_js2)
ok(
    {a["name"]: a["balance"] for a in db.get_accounts(s7)}["竞赛"] == 6,
    "删掉那节课，课时退回来",
)
db.delete_student(s7)

print("27. 学员页看得到他上过什么课 / 列表看得到谁上的课")
app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
s4 = db.create_student({"name": "上课记录测试", "grade": "一年级"})
h4 = next(a["hour_type_id"] for a in db.get_accounts(s4) if a["name"] == "正课")
db.add_hours(s4, h4, 10, kind="充值", source_type="manual")  # 有课时，但没报名
app.tab = 0
app.open_student(s4)
tree = page.controls[0]
ok(
    find_text(tree, "还没报名课程。上面课时账户里已经有课时了"),
    "只缴费没报名时，会提示去加一条报名课程",
)
ok(find_text(tree, "还没有上过课"), "没上过课时，学员页会说明")

s5 = db.create_student({"name": "同班同学", "grade": "一年级"})
lesson_x = db.create_lesson(today.isoformat(), "09:00", 90, zhengke["id"], gpl3["id"])
a4 = db.add_attendance(lesson_x, s4)
a5 = db.add_attendance(lesson_x, s5)
db.update_attendance(a5, attendance=0, discipline=0, performance=0)

app.tab = 1
app.lesson_id = None
app.show_schedule = False
app.render()
tree = page.controls[0]
ok(
    find_text(tree, "上课记录测试、同班同学（请假）"),
    "上课记录列表上能看到谁上的课，请假的会标出来",
)
ok(find_text(tree, "2 人 · 扣 1.5 课时"), "请假的人不算进扣课时（人数照列，课时只算到场的）")

app.tab = 0
app.open_student(s4)
tree = page.controls[0]
ok(find_text(tree, "上课记录（最近 1 次）"), "学员页多了一块上课记录")
ok(find_text(tree, "扣 1.5 课时"), "学员页能看到这次扣了多少课时")
ok(find_text(tree, "+30 分"), "学员页能看到这次得了多少分")

db.delete_lesson(lesson_x)
db.delete_student(s4)
db.delete_student(s5)

print(f"\n全部通过：{checks} 项检查")
