"""一个不依赖浏览器的自检脚本：把界面搭起来、把按钮点一遍，看看数据对不对。

运行： .venv/bin/python tests/smoke_test.py
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sqlite3
import sys
import tempfile
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="class-hours-test-")
os.environ["CLASS_HOURS_DB"] = str(pathlib.Path(TMP) / "test.db")

import flet as ft  # noqa: E402

import db  # noqa: E402
from app_ui import ClassHoursApp  # noqa: E402
from ui.shell import TAB_DASHBOARD  # noqa: E402
from ui.tools import (  # noqa: E402
    calculate_3d_print_points,
    format_print_duration,
    parse_print_duration,
    print_half_hour_units,
)

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
        "columns",
        "rows",
        "cells",
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


def find_key(control, key: str):
    for c in walk(control):
        if c.key == key:
            return c
    raise AssertionError(f"找不到控件：{key}")


def find_checkbox(control, name_prefix: str) -> ft.Checkbox:
    for c in walk(control):
        if isinstance(c, ft.Checkbox) and str(c.label or "").startswith(name_prefix):
            return c
    raise AssertionError(f"找不到勾选框：{name_prefix}")


def find_text(control, needle: str) -> bool:
    for c in walk(control):
        if isinstance(c, ft.Text) and needle in str(c.value or ""):
            return True
        if isinstance(c, ft.Markdown) and needle in str(c.value or ""):
            return True
        if isinstance(c, ft.TextField) and needle in str(c.value or ""):
            return True
    return False


def find_search(control):
    """页面上的搜索框（按放大镜图标找）。"""
    for c in walk(control):
        if isinstance(c, ft.TextField) and c.prefix_icon == ft.Icons.SEARCH:
            return c
    raise AssertionError("找不到搜索框")


def holder_of(control, target):
    """找到直接装着 target 的那个容器（用来判断整块内容显示没显示）。"""
    for c in walk(control):
        if isinstance(c, ft.Column) and target in (c.controls or []):
            return c
    raise AssertionError("找不到装着这个控件的容器")


class Evt:
    """冒充 Flet 的事件对象：处理函数要用 e.control。"""

    def __init__(self, control):
        self.control = control
        self.data = None


def type_school(control, name: str):
    """手打学校名（学校就是个普通输入框）。"""
    field = find_field(control, "学校")
    field.value = name
    return field


def pick_school(control, name: str):
    """从"选填过的"下拉里挑一个学校，像真客户端那样把选中事件也走一遍。"""
    dd = find_dropdown(control, "选填过的")
    dd.value = name
    dd.on_select(Evt(dd))
    return dd


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
ok(len(db.list_hour_types()) == 6, "六种课时账户建好了")
ok(len(db.list_class_types()) == 8, "八种课型建好了")
ok(len(db.list_levels()) == 7, "七个等级建好了")

rules = {c["name"]: c for c in db.list_class_types()}
ok(rules["竞赛"]["primary_name"] == "竞赛", "竞赛课先扣竞赛课时")
ok(rules["竞赛"]["fallback_name"] == "正课", "竞赛课时不够补扣正课")
ok(rules["考级"]["fallback_name"] == "正课", "考级课时不够补扣正课")
ok(
    rules["全年"]["deduct"] == 1 and rules["全年"]["primary_name"] == "全年",
    "全年课型默认扣全年课时",
)
ok(rules["试听"]["deduct"] == 0, "试听不扣课时")
ok(rules["替课"]["deduct"] == 1 and rules["替课"]["primary_name"] == "正课", "老师替课照扣正课课时")
ok(
    "社团" in rules and "校内社团" not in rules,
    "社团课型统一显示为「社团」",
)
uav_level = next(l for l in db.list_levels() if l["level_type"] == "社团")
ok(
    db.class_type_id_for_level(uav_level["id"]) == rules["社团"]["id"],
    "社团等级会自动匹配社团课型",
)

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
ok(
    app.tab == TAB_DASHBOARD and find_text(page.controls[0], "今天"),
    "管理员登录后先进入今日工作台",
)
ok(find_text(page.controls[0], "今天没有排课"), "没有排课时工作台给出清楚的空状态")

app._goto(0)
ok(find_text(page.controls[0], "还没有学员"), "宽屏：左侧导航 + 空列表")
status_default = find_dropdown(page.controls[0], "状态")
ok(
    app.status_filter == "在读" and status_default.value == "在读",
    "学员列表默认只显示在读学员",
)
ok(find_text(page.controls[0], "设置"), "左侧导航有「设置」")
ok(
    find_text(page.controls[0], "全部数据与权限"),
    "管理员登录后明确显示当前角色和数据范围",
)
ok(
    any(isinstance(c, ft.Container) and c.width == 96 for c in walk(page.controls[0])),
    "宽屏用左侧竖排导航",
)

phone_page = StubPage(width=390)
phone_app = ClassHoursApp(phone_page)
phone_app.user = app.user
phone_app.tab = TAB_DASHBOARD
phone_app.render()
ok(
    any(isinstance(c, ft.Container) and c.height == 56 for c in walk(phone_page.controls[0])),
    "手机用底部横排导航",
)
ok(find_text(phone_page.controls[0], "今天"), "手机上也从今日工作台开始")
ok(
    phone_app._mobile_primary_indices() == [TAB_DASHBOARD, 0, 1]
    and phone_app._mobile_more_indices() == [2, 3, 4, 8, 5, 6, 7],
    "手机后台保留今天、学员、课程，其余收进「更多」",
)
ok(find_text(phone_page.controls[0], "更多"), "手机后台有「更多」入口")
phone_app._goto(0)
ok(find_text(phone_page.controls[0], "还没有学员"), "手机学员页仍显示完整名册")
phone_filter_button = next(
    control
    for control in walk(phone_page.controls[0])
    if isinstance(control, (ft.Button, ft.TextButton))
    and str(control.content or "").startswith("筛选")
)
ok(phone_filter_button.height == 48, "手机筛选按钮有足够大的触控高度")
phone_filter_button.on_click(None)
filter_sheet = top_dialog(phone_page)
ok(isinstance(filter_sheet, ft.BottomSheet), "手机筛选用底部面板展开")
ok(
    find_dropdown(filter_sheet, "年级") is not None
    and find_dropdown(filter_sheet, "学校") is not None
    and find_dropdown(filter_sheet, "归属老师") is not None,
    "手机筛选面板里有完整的筛选条件",
)
phone_page.pop_dialog()

app._goto(1)
ok(find_text(page.controls[0], "课程排课"), "点「课程」能切过去")
app._goto(2)
ok(find_text(page.controls[0], "还没有试听记录"), "点「试听」能切过去")
app._goto(3)
ok(find_text(page.controls[0], "还没有缴费记录"), "点「缴费」能切过去")
app._goto(4)
ok(find_text(page.controls[0], "论坛悬赏"), "点「论坛」能切过去")
app._goto(5)
ok(find_text(page.controls[0], "课时不够要提醒的"), "点「报表」能切过去")
app._goto(6)
ok(find_text(page.controls[0], "竞技与考级"), "点「竞技」能切过去")
app._goto(7)
ok(find_text(page.controls[0], "课型与扣课时规则"), "点「课程设置」能切过去")
app._goto(8)
ok(find_text(page.controls[0], "工具栏"), "点「工具」能切过去")
app._goto(0)
ok(find_text(page.controls[0], "还没有学员"), "点「学员」能切回来")

menus = [label for _ic, _sic, label in app._nav_items()]
ok(
    menus == [
        "今天",
        "学员",
        "课程",
        "试听",
        "缴费",
        "论坛",
        "工具",
        "报表",
        "竞技",
        "设置",
    ],
    f"菜单是 {menus}",
)
ok("上课记录" not in menus, "「上课记录」栏目并入「课程」了")
ok("积分" not in menus, "积分不再单占一个菜单（挪进学员页和报表页了）")

print("2b. 3D 打印积分工具")
ok(print_half_hour_units(1) == 1, "不足半小时按 1 档")
ok(print_half_hour_units(30) == 1, "正好半小时按 1 档")
ok(print_half_hour_units(31) == 2, "超过半小时按 2 档")
ok(print_half_hour_units(60) == 2, "1 小时按 2 档")
ok(print_half_hour_units(61) == 3, "超过 1 小时按 3 档")
ok(calculate_3d_print_points(10, 30) == 100, "10 克打印半小时消耗 100 积分")
ok(calculate_3d_print_points(10, 61) == 300, "10 克打印 61 分钟消耗 300 积分")
ok(format_print_duration(180) == "3 小时", "180 分钟显示成 3 小时")
ok(format_print_duration(90) == "1 小时 30 分钟", "90 分钟显示成 1 小时 30 分钟")
ok(parse_print_duration("3:00") == 180, "时长 3:00 能解析成 180 分钟")
ok(parse_print_duration("1:30") == 90, "时长 1:30 能解析成 90 分钟")
ok(parse_print_duration("1：01") == 61, "中文冒号也能识别")
try:
    calculate_3d_print_points(10, 0)
    zero_duration_allowed = True
except ValueError:
    zero_duration_allowed = False
ok(not zero_duration_allowed, "打印时长必须大于 0")

app._goto(8)
page.width = 1600
app.render()
ok(
    any(isinstance(c, ft.ResponsiveRow) for c in walk(page.controls[0])),
    "工具页会利用宽屏空间，输入和结果分区展示",
)
page.width = 1200
app.render()
ok(find_text(page.controls[0], "等待计算"), "还没填写时结果是清楚的等待状态")
find_field(page.controls[0], "耗材重量（克）").value = "12.5"
find_field(page.controls[0], "打印时长（小时:分钟）").value = "1:01"
click(page.controls[0], "计算积分")
ok(
    find_text(page.controls[0], "375 积分")
    and find_text(page.controls[0], "1 小时 1 分钟（61 分钟）")
    and find_text(page.controls[0], "12.5g × 10 × 3 档"),
    "用 1:01 输入，也能正确按半小时档数算积分",
)
find_field(page.controls[0], "打印时长（小时:分钟）").value = "3:00"
click(page.controls[0], "计算积分")
ok(
    find_text(page.controls[0], "750 积分")
    and find_text(page.controls[0], "3 小时（180 分钟）"),
    "打印 3 小时不用自己换算分钟",
)

print("2c. 网站工具")
ok(
    db.normalize_web_tool_url("scratch.mit.edu") == "https://scratch.mit.edu",
    "网址省略 https:// 时自动补全",
)
try:
    db.normalize_web_tool_url("javascript:alert(1)")
    unsafe_url_allowed = True
except ValueError:
    unsafe_url_allowed = False
ok(not unsafe_url_allowed, "网站工具不允许脚本地址")

root_id = app._my_user_id() or 0
try:
    db.create_web_tool(999, "无权添加", "example.com")
    non_root_created_tool = True
except PermissionError:
    non_root_created_tool = False
ok(not non_root_created_tool, "只有 root 能在数据层添加网站工具")

app._goto(8)
ok(find_text(page.controls[0], "网站工具（0）"), "工具栏有网站工具区域")
click(page.controls[0], "添加网站")
dlg = top_dialog(page)
find_field(dlg, "网站名称 *").value = "Scratch 官网"
find_field(dlg, "网址 *").value = "scratch.mit.edu"
click(dlg, "添加网站")
app._close()
web_tools = db.list_web_tools()
ok(
    len(web_tools) == 1
    and web_tools[0]["title"] == "Scratch 官网"
    and web_tools[0]["url"] == "https://scratch.mit.edu",
    "root 添加的网站会成为一个独立工具",
)
ok(
    find_text(page.controls[0], "Scratch 官网")
    and any(
        isinstance(c, ft.IconButton) and c.tooltip == "编辑网站工具"
        for c in walk(page.controls[0])
    ),
    "root 能看到网站工具和编辑入口",
)

app._open_web_tool_dialog(web_tools[0])
dlg = top_dialog(page)
find_field(dlg, "网站名称 *").value = "Scratch 编程"
click(dlg, "保存修改")
app._close()
ok(db.list_web_tools()[0]["title"] == "Scratch 编程", "root 能编辑网站工具")

class FakeBookmarkLauncher:
    def __init__(self):
        self.opened = []

    async def launch_url(self, url, web_only_window_name=None):
        self.opened.append((url, web_only_window_name))


original_launcher = app.launcher
app.launcher = FakeBookmarkLauncher()
asyncio.run(app._open_web_tool("https://scratch.mit.edu"))
ok(
    app.launcher.opened == [("https://scratch.mit.edu", "_blank")],
    "打开网站工具会交给默认浏览器的新窗口",
)
app.launcher = original_launcher

root_user = dict(app.user)
app.user = {
    "id": 999,
    "username": "student-viewer",
    "display_name": "学生",
    "role": db.ROLE_STUDENT,
}
app.tab = 3
app.render()
ok(
    find_text(page.controls[0], "Scratch 编程")
    and not any(
        isinstance(c, ft.IconButton)
        and c.tooltip in {"编辑网站工具", "删除网站工具"}
        for c in walk(page.controls[0])
    ),
    "普通账号能打开网站工具，但看不到添加、编辑、删除入口",
)
try:
    find_button(page.controls[0], "添加网站")
    non_root_saw_add = True
except AssertionError:
    non_root_saw_add = False
ok(not non_root_saw_add, "普通账号看不到添加网站按钮")
app.user = root_user
db.delete_web_tool(web_tools[0]["id"], root_id)
app._goto(0)

app._goto(1)
ok(
    find_text(page.controls[0], "课程排课") and find_text(page.controls[0], "这一周的课"),
    "「课程」栏目里有排课表",
)
ok(find_search(page.controls[0]) is not None, "「课程」里有搜课次的搜索框")
app._goto(0)

# 一个学员都还没建档的时候，缴费框应该直接让人填新学员，而不是把人挡回去
app.tab = 3
app.render()
app._open_payment_dialog()
dlg = top_dialog(page)
dd = find_dropdown(dlg, "孩子")
new_key = next((o.key for o in dd.options if "新建" in o.text), None)
ok(new_key is not None and dd.value == new_key, "「孩子」默认就是「＋ 新建学员…」")
ok(find_field(dlg, "姓名 *") is not None, "里面直接给了填新学员的地方")
ok(holder_of(dlg, find_field(dlg, "姓名 *")).visible, "没有学员时，填名字那块是展开的")
ok(not find_text(dlg, "先添加学员"), "不再弹「先添加学员」把人挡回去")
ok(find_text(dlg, "本笔合计"), "缴费框把本笔合计单独汇总")
ok(
    any(
        isinstance(c, ft.ExpansionTile) and c.title == "填写说明"
        for c in walk(dlg)
    ),
    "缴费填写说明默认收进可展开区域",
)
app._close()
app._goto(0)  # 看完缴费页记得回来，后面接着测学员

print("3. 新增学员")
app._open_new_student()
dlg = top_dialog(page)
ok(find_field(dlg, "出生日期") is not None, "新增学员可以填出生日期")
ok(
    not any(
        isinstance(c, ft.Switch)
        and "自动计算年级" in str(c.label or "")
        for c in walk(dlg)
    ),
    "出生日期绑定后不再提供可选开关",
)
find_field(dlg, "姓名 *").value = "张晨希"
find_dropdown(dlg, "年级").value = "六年级"
find_field(dlg, "出生日期").value = "2014-10-10"
type_school(dlg, "实验小学")
find_field(dlg, "联系电话").value = "13800000000"
find_dropdown(dlg, "性别").value = "女"
click(dlg, "保存")
students = db.list_students()
ok(len(students) == 1 and students[0]["name"] == "张晨希", "学员存进去了")
ok(students[0]["grade"] == "六年级", "年级存的是「六年级」这种写法，不是光秃秃的 6")
ok(students[0]["school"] == "实验小学", "学校也存进去了")
sid = students[0]["id"]
auto_account = db.get_student_user(sid)
ok(
    auto_account is not None
    and auto_account["role"] == db.ROLE_STUDENT
    and auto_account["student_id"] == sid,
    "新建正式学员后自动生成学生账号",
)
credentials_dlg = top_dialog(page)
ok(find_text(credentials_dlg, "学生账号已生成"), "创建后显示学生初始账号密码")
ok(find_text(credentials_dlg, "用户名：zhangchenxi"), "学生用户名使用姓名拼音")
password_line = next(
    c.value
    for c in walk(credentials_dlg)
    if isinstance(c, ft.Text) and str(c.value or "").startswith("初始密码：")
)
initial_password = str(password_line).split("：", 1)[1]
ok(
    len(initial_password) == 8 and initial_password.isdigit(),
    "没有出生日期时生成 8 位随机数字密码",
)
ok(
    db.verify_user("zhangchenxi", initial_password) is not None,
    "自动生成的拼音用户名和初始密码能登录",
)
app._close()

print("4. 学员详情页")
app.open_student(sid)
tree = page.controls[0]
ok(find_text(tree, "张晨希"), "详情页显示姓名")
ok(any(isinstance(c, ft.ResponsiveRow) for c in walk(tree)), "基本档案默认用横向信息卡显示")
try:
    find_field(tree, "姓名 *")
    profile_form_by_default = True
except AssertionError:
    profile_form_by_default = False
ok(not profile_form_by_default, "不编辑时不显示整排输入框")
ok(find_text(tree, "课时账户"), "详情页有课时账户")
ok(find_text(tree, "报名课程"), "详情页有报名课程")
click(tree, "重设密码")
dlg = top_dialog(page)
find_field(dlg, "新密码").value = "kid-new-pass"
find_field(dlg, "再输一遍新密码").value = "kid-new-pass"
click(dlg, "保存")
ok(
    db.verify_user("zhangchenxi", "kid-new-pass") is not None,
    "从学员档案里能修改学生登录密码",
)

print("4b. 学员列表上年级和学校都看得见")
app.open_student(None)
app.tab = 0
app.render()
ok(find_text(page.controls[0], "六年级"), "列表卡片上有年级")
ok(find_text(page.controls[0], "实验小学"), "列表卡片上有哪所小学")

print("5. 改档案")
app.open_student(sid)
tree = page.controls[0]
find_button(tree, "编辑").on_click(None)
tree = page.controls[0]
save_btn = None
for c in walk(tree):
    if isinstance(c, (ft.Button, ft.TextButton)) and c.content == "保存":
        save_btn = c
find_dropdown(tree, "年级").value = "初一"
find_field(tree, "出生日期").value = "2013-10-10"
type_school(tree, "育才小学")
save_btn.on_click(None)
ok(db.get_student(sid)["grade"] == "初一", "档案改好了（年级）")
ok(db.get_student(sid)["school"] == "育才小学", "档案改好了（学校）")

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
accounts = {a["name"]: a for a in db.get_accounts(sid)}
db.add_hours(
    sid,
    accounts["正课"]["hour_type_id"],
    24,
    kind="充值",
    note="测试准备课时",
    source_type="manual",
)
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 24, "正课课时 +24")

db.add_hours(
    sid,
    accounts["正课"]["hour_type_id"],
    -22,
    kind="扣减",
    note="测试准备已用课时",
    source_type="manual",
)
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
ok(len(db.list_class_types()) == 8, "课型规则能保存")

ok(
    find_button(app._class_types_card(), "新增课型") is not None,
    "课程设置里有新增课型入口",
)
app._open_class_type_dialog()
dlg = top_dialog(page)
find_field(dlg, "课型名称 *").value = "晚间课"
find_dropdown(dlg, "主扣账户").value = str(
    next(h["id"] for h in db.list_hour_types() if h["name"] == "正课")
)
click(dlg, "保存")
created_class_type = next(
    c for c in db.list_class_types() if c["name"] == "晚间课"
)
ok(
    created_class_type["deduct"] == 1
    and created_class_type["primary_name"] == "正课",
    "设置里可以新增课型并指定扣课时账户",
)
app._open_class_type_dialog(created_class_type)
dlg = top_dialog(page)
find_field(dlg, "课型名称 *").value = "晚间班"
click(dlg, "保存")
ok(
    any(
        c["id"] == created_class_type["id"] and c["name"] == "晚间班"
        for c in db.list_class_types()
    ),
    "设置里可以编辑课型名称",
)

print("10b. 学校字典（设置里加，填学员时直接挑）")
app.tab = 7
app.render()
tree = page.controls[0]
ok(
    find_text(tree, "老师账号")
    and not find_text(tree, "用户名 zhangchenxi"),
    "老师账号列表不混入学生账号",
)
ok(find_text(tree, "育才小学"), "已经在用的学校也列在这儿")
ok(find_button(tree, "新增学校") is not None, "学校默认只显示列表，新增时才打开输入框")
find_button(tree, "新增学校").on_click(None)
dlg = top_dialog(page)
find_field(dlg, "新学校名").value = "云山道小学"
click(dlg, "保存")
ok("云山道小学" in db.list_schools(), "学校加进字典了")
ok(find_text(page.controls[0], "还没有孩子填这个学校"), "卡片上注明还没人用")

app._open_new_student()
dlg = top_dialog(page)
ok(
    any(o.key == "云山道小学" for o in find_dropdown(dlg, "选填过的").options),
    "填学员档案时，字典里的学校能直接挑",
)
pick_school(dlg, "云山道小学")
ok(find_field(dlg, "学校").value == "云山道小学", "挑一下自动填进输入框")
app._close()

row = next(r for r in db.school_rows() if r["name"] == "云山道小学")
db.delete_school(row["id"])
ok("云山道小学" not in db.list_schools(), "也能从下拉候选里去掉")

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
ok(find_text(page.controls[0], "课程排课"), "课程栏目能打开（上课记录并进来了）")

app._open_lesson_dialog()
dlg = top_dialog(page)
find_field(dlg, "日期").value = "2026-09-05"
find_field(dlg, "开始时间").value = "08:30"
find_field(dlg, "时长（分钟）").value = "90"
find_dropdown(dlg, "课型").value = str(zhengke["id"])
find_dropdown(dlg, "等级（可不选）").value = str(gpl3["id"])
find_checkbox(dlg, "张晨希").value = True
click(dlg, "保存")

lessons = db.list_lessons()
ok(len(lessons) == 1, "课次建好了")
lesson = lessons[0]
db.set_lesson_comment(lesson["id"], "今天讲循环")
rows = db.list_attendance(lesson["id"])
ok(len(rows) == 1 and rows[0]["minutes"] == 90, "点名记录带上了默认时长")
ok(db.get_lesson(lesson["id"])["comment"] == "今天讲循环", "课评存在课次上")
ok(db.get_lesson(lesson["id"])["rolled"] == 0, "记一节课默认先挂着「待点名」")
app._open_lesson_dialog(db.get_lesson(lesson["id"]))
_edit_dlg = top_dialog(page)
ok(
    not any(
        isinstance(c, ft.TextField)
        and c.label
        and ("课评" in c.label or "教案" in c.label)
        for c in walk(_edit_dlg)
    ),
    "编辑课次里不再重复放课评和教案",
)
app._close()
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 24, "还没点名，课时先不扣")
ok(db.student_points(sid) == 0, "还没点名，积分也先不加")
db.roll_call(lesson["id"])
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 22.5, "出勤自动扣了 1.5 课时")
ok(db.student_points(sid) == 30, "出勤＋纪律＋学习 = 30 分")

app._save_attendance_flag(rows[0]["id"], "attendance", False)
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 24, "改成请假，课时退回来")
ok(db.student_points(sid) == 0, "请假不加分")

app._save_attendance_flag(rows[0]["id"], "attendance", True)
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(accounts["正课"]["balance"] == 22.5, "改回出勤，课时又扣上")
ok(db.student_points(sid) == 10, "纪律和学习不好时先按默认 0 分计算")

app.open_lesson(lesson["id"])
ok(find_checkbox(page.controls[0], "纪律").label == "纪律", "标题就是「纪律」")
ok(find_checkbox(page.controls[0], "学习").label == "学习", "标题就是「学习」")
performance_score = find_field(page.controls[0], "学习分（-10 < x < 10）")
ok(performance_score.visible, "学习不好时显示老师填分框")
performance_score.value = "10"
performance_score.on_blur(Evt(performance_score))
ok(
    performance_score.error == "学习分必须大于 -10 且小于 10"
    and float(db.get_attendance(rows[0]["id"])["performance_score"]) == 0,
    "学习分等于 10 时拒绝保存",
)
performance_score.value = "-3.2"
performance_score.on_blur(Evt(performance_score))
ok(
    abs(float(db.get_attendance(rows[0]["id"])["performance_score"]) + 3.2) < 1e-6,
    "老师填写的学习分 -3.2 存下来了",
)
ok(abs(db.student_points(sid) - 6.8) < 1e-6, "学习分 -3.2 参与积分计算")

discipline_score = find_field(page.controls[0], "纪律分（-10 < x < 10）")
ok(discipline_score.visible, "纪律不好时显示老师填分框")
discipline_score.value = "10"
discipline_score.on_blur(Evt(discipline_score))
ok(
    discipline_score.error == "纪律分必须大于 -10 且小于 10"
    and float(db.get_attendance(rows[0]["id"])["discipline_score"]) == 0,
    "纪律分等于 10 时拒绝保存",
)
discipline_score.value = "-2.5"
discipline_score.on_blur(Evt(discipline_score))
ok(
    abs(float(db.get_attendance(rows[0]["id"])["discipline_score"]) + 2.5) < 1e-6,
    "老师填写的纪律分 -2.5 存下来了",
)
ok(abs(db.student_points(sid) - 4.3) < 1e-6, "纪律分也参与本次积分计算")
for field, title in (
    ("discipline_score", "纪律分"),
    ("performance_score", "学习分"),
):
    for invalid_score in (-10, 10):
        try:
            db.update_attendance(
                rows[0]["id"], **{field: invalid_score}
            )
            rejected = False
        except ValueError:
            rejected = True
        ok(rejected, f"{title} {invalid_score} 不允许保存")

poor_discipline_reason = find_field(page.controls[0], "纪律不好原因")
ok(poor_discipline_reason.visible, "纪律不好时显示原因输入框")
poor_discipline_reason.value = "多次打断课堂，影响其他同学"
poor_discipline_reason.on_blur(Evt(poor_discipline_reason))
ok(
    db.get_attendance(rows[0]["id"])["poor_discipline_reason"]
    == "多次打断课堂，影响其他同学",
    "纪律不好的原因存下来了",
)

poor_reason = find_field(page.controls[0], "学习不好原因")
ok(poor_reason.visible, "学习不好时显示原因输入框")
poor_reason.value = "多次离座，没有按步骤完成"
poor_reason.on_blur(Evt(poor_reason))
ok(
    db.get_attendance(rows[0]["id"])["poor_performance_reason"]
    == "多次离座，没有按步骤完成",
    "学习不好的原因存下来了",
)
ok(
    "纪律不好（得分 -2.5）：多次打断课堂，影响其他同学"
    in db.list_point_transactions(sid)[0]["note"],
    "纪律不好的原因也写进积分明细",
)
ok(
    "学习不好（得分 -3.2）：多次离座，没有按步骤完成"
    in db.list_point_transactions(sid)[0]["note"],
    "学习不好的原因也写进积分明细",
)

discipline_box = find_checkbox(page.controls[0], "纪律")
discipline_box.value = True
discipline_box.on_change(Evt(discipline_box))
ok(
    abs(db.student_points(sid) - 16.8) < 1e-6,
    "重新勾上纪律时恢复满分 10 分",
)
ok(
    not find_field(page.controls[0], "纪律分（-10 < x < 10）").visible
    and not find_field(page.controls[0], "纪律不好原因").visible,
    "勾上纪律后，纪律分和原因框立即隐藏",
)
discipline_row = db.get_attendance(rows[0]["id"])
ok(
    float(discipline_row["discipline_score"]) == -2.5
    and discipline_row["poor_discipline_reason"] == "多次打断课堂，影响其他同学",
    "重新勾上后，纪律填分和原因仍保留",
)
discipline_box.value = False
discipline_box.on_change(Evt(discipline_box))
ok(
    abs(db.student_points(sid) - 4.3) < 1e-6,
    "再次取消纪律时，恢复使用原来的纪律分",
)
learning_box = find_checkbox(page.controls[0], "学习")
learning_box.value = True
learning_box.on_change(Evt(learning_box))
ok(
    abs(db.student_points(sid) - 17.5) < 1e-6,
    "重新勾上学习时也恢复满分 10 分",
)
ok(
    not find_field(page.controls[0], "学习分（-10 < x < 10）").visible
    and not find_field(page.controls[0], "学习不好原因").visible,
    "勾上学习后，学习分和原因框立即隐藏",
)
learning_box.value = False
learning_box.on_change(Evt(learning_box))
ok(
    abs(db.student_points(sid) - 4.3) < 1e-6,
    "再次取消学习时，恢复使用原来的学习分",
)
lesson_points = [
    t
    for t in db.list_point_transactions(sid)
    if t["source_type"] == "lesson" and t["source_id"] == lesson["id"]
]
ok(len(lesson_points) == 1, "反复切换纪律和学习不会重复生成积分")

app._save_attendance_value(rows[0]["id"], "bonus", 0, "25")
ok(
    abs(db.student_points(sid) - 29.3) < 1e-6,
    "突出发挥 25 分在纪律分和学习分之后继续累加",
)
bonus_reason = find_field(page.controls[0], "突出发挥原因")
ok(bonus_reason.visible, "突出发挥时显示原因输入框")
bonus_reason.value = "主动帮助同学检查线路"
bonus_reason.on_blur(Evt(bonus_reason))
ok(
    db.get_attendance(rows[0]["id"])["bonus_reason"] == "主动帮助同学检查线路",
    "突出发挥的原因存下来了",
)
ok(
    "突出发挥：主动帮助同学检查线路" in db.list_point_transactions(sid)[0]["note"],
    "突出发挥的原因也写进积分明细",
)

app._open_lesson_dialog()
dlg = top_dialog(page)
find_field(dlg, "时长（分钟）").value = "120"
find_dropdown(dlg, "课型").value = str(jingsai["id"])
find_checkbox(dlg, "张晨希").value = True
find_checkbox(dlg, "现在就点名").value = True  # 当场算数的特殊路子
click(dlg, "保存")
accounts = {a["name"]: a for a in db.get_accounts(sid)}
ok(
    accounts["竞赛"]["balance"] == 0 and accounts["正课"]["balance"] == 20.5,
    "竞赛课时不够，自动从正课扣了 2 课时",
)
ok(len(db.list_lessons()) == 2, "第二节课也在")

print("11b. 添加孩子时只列本级别的")
py_level = next(l for l in db.list_levels() if db.level_full_name(l) == "PY-Lvl-02")
other_sid = db.create_student({"name": "别的级别娃", "grade": "三年级"})
db.create_enrollment(other_sid, py_level["id"], zhengke["id"], 60)
app.open_lesson(lesson["id"])
app._open_add_students_dialog(db.get_lesson(lesson["id"]))
dlg = top_dialog(page)
ok(find_text(dlg, "只列这个级别的孩子"), "对话框上写明这节课是哪个级别")


def listed_in(dialog, name_prefix) -> bool:
    try:
        find_checkbox(dialog, name_prefix)
        return True
    except AssertionError:
        return False


ok(not listed_in(dlg, "别的级别娃"), "别的级别的孩子不列出来")
show_all = find_checkbox(dlg, "也显示别的级别的孩子")
show_all.value = True
show_all.on_change(None)
ok(listed_in(dlg, "别的级别娃"), "打开开关，别的级别的孩子才出来")
app._close()

# 「记一节课」里选完等级，候选名单也该跟着筛
app._open_lesson_dialog()
dlg = top_dialog(page)
level_dd = find_dropdown(dlg, "等级（可不选）")
level_dd.value = str(gpl3["id"])
level_dd.on_select(None)
ok(listed_in(dlg, "张晨希"), "记一节课：选了等级，本级别的孩子还在名单里")
ok(not listed_in(dlg, "别的级别娃"), "记一节课：别的级别的孩子被筛掉")
find_checkbox(dlg, "也显示别的级别的孩子").value = True
find_checkbox(dlg, "也显示别的级别的孩子").on_change(None)
ok(listed_in(dlg, "别的级别娃"), "记一节课：勾上开关，别的级别又出来了")
app._close()
db.delete_student(other_sid)

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

print("11c. 上课记录能搜")
search_kid = db.create_student({"name": "搜索娃", "grade": "三年级"})
lesson_a = db.create_lesson(
    "2026-08-01", "10:00", 90, zhengke["id"], gpl3["id"], "这节课课评很特别"
)
lesson_b = db.create_lesson("2026-08-02", "11:00", 90, zhengke["id"], None)
db.add_attendance(lesson_a, search_kid)

app.tab = 1
app.lesson_id = None
app.lesson_keyword = ""
app.render()
ok(find_text(page.controls[0], "课程排课"), "课程栏目里也能搜课次")

box = find_search(page.controls[0])
box.value = "搜索娃"
box.on_submit(Evt(box))
ok(find_text(page.controls[0], "共 1 节课"), "在搜索框里搜孩子名字，能筛出来")

for word, expected, why in [
    ("很特别", 1, "课评"),
    ("Lvl-03", 1, "等级"),
    ("2026-08-02", 1, "日期"),
    ("8月2日", 1, "中文日期（界面上就是这么显示的）"),
    ("8-1", 1, "简写日期"),
    ("正课", 2, "课型"),
]:
    app.lesson_keyword = word
    app.render()
    ok(find_text(page.controls[0], f"共 {expected} 节课"), f"搜{why}也能搜到")

app.lesson_keyword = "根本就没有这个"
app.render()
ok(find_text(page.controls[0], "没有符合条件的课"), "搜不到就提示没有符合条件的课")

app.lesson_keyword = ""
app.render()
ok(find_text(page.controls[0], "这一周的课"), "清掉搜索就回到课表")
db.delete_student(search_kid)
for l in db.list_lessons():
    db.delete_lesson(l["id"])

print("12. 缴费记录")
app.tab = 3
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

print("12b. 交钱的人还没档案，缴费时顺手建一个")
before_count = len(db.list_students())
app.tab = 3
app.render()
app._open_payment_dialog()
dlg = top_dialog(page)
dd = find_dropdown(dlg, "孩子")
new_key = next(o.key for o in dd.options if "新建" in o.text)
ok(dd.on_select is not None, "「孩子」下拉接的是 on_select（Flet 1.0 的 Dropdown 没有 on_change）")
ok(getattr(dd, "on_change", None) is None, "没人把事件错接在 on_change 上")
# 先在「老学员」和「新学员」之间来回切一下，确认填名字那块是跟着出来的
dd.value = str(sid)
dd.on_select(None)
ok(not holder_of(dlg, find_field(dlg, "姓名 *")).visible, "选了老学员，填名字那块先收起来")
dd.value = new_key
dd.on_select(None)
ok(holder_of(dlg, find_field(dlg, "姓名 *")).visible, "切到「＋ 新建学员…」，填名字的地方就出来了")
find_field(dlg, "姓名 *").value = "刚交钱的娃"
find_dropdown(dlg, "年级").value = "三年级"
find_field(dlg, "出生日期").value = "2017-10-10"
# 学校是手打的
type_school(dlg, "实验小学")
find_field(dlg, "联系电话").value = "13700000000"
find_field(dlg, "数量（课时）").value = "12"
find_field(dlg, "金额（元）").value = "1200"
click(dlg, "保存")
students_now = db.list_students()
ok(len(students_now) == before_count + 1, "缴费时把学员档案一起建好了")
fresh = next(s for s in students_now if s["name"] == "刚交钱的娃")
ok(fresh["grade"] == "三年级", "建档时年级记上了")
ok(fresh["school"] == "实验小学", "手打进去的学校也存下来了")
ok("实验小学" in db.list_schools(), "存过的学校进了候选名单")
ok(
    db.get_student_user(fresh["id"]) is not None,
    "缴费时顺手新建的正式学员也会自动生成账号",
)
ok(find_text(top_dialog(page), "学生账号已生成"), "缴费建档后显示初始账号")
app._close()

# 下次再打开：填过的学校应该出现在下拉里，挑一下就能填进输入框
app._open_new_student()
dlg2 = top_dialog(page)
ok(find_dropdown(dlg2, "选填过的") is not None, "填过学校之后，旁边多了「选填过的」下拉")
ok(any(o.key == "实验小学" for o in find_dropdown(dlg2, "选填过的").options), "实验小学在下拉里")
ok(find_field(dlg2, "学校").value in ("", None), "还没挑，输入框是空的")
pick_school(dlg2, "实验小学")
ok(find_field(dlg2, "学校").value == "实验小学", "从下拉里挑一下，学校就填进输入框了")
app._close()

app.tab = 0
app.open_student(fresh["id"])
find_button(page.controls[0], "编辑").on_click(None)
ok(find_field(page.controls[0], "学校").value == "实验小学", "学员档案里回显着学校")
app.open_student(None)
fresh_accounts = {a["name"]: a for a in db.get_accounts(fresh["id"])}
ok(fresh_accounts["正课"]["balance"] == 12, "课时挂到这个新学员名下")
ok(len(db.list_payments(student_id=fresh["id"])) == 1, "缴费记录也是他的")
db.delete_payment(db.list_payments(student_id=fresh["id"])[0]["id"])
db.delete_student(fresh["id"])
ok(len(db.list_students()) == before_count, "清干净了")

print("12c. 固定课包与代金券")
vou_kid = db.create_student({"name": "券娃", "grade": "二年级"})
zk_hour = next(h["id"] for h in db.list_hour_types() if h["name"] == "正课")
js_hour = next(h["id"] for h in db.list_hour_types() if h["name"] == "竞赛")
default_package = next(
    p for p in db.list_course_packages() if p["name"] == "3000 元固定课包"
)
package_hours = {
    item["hour_type_name"]: item["hours"] for item in default_package["items"]
}
ok(
    default_package["price"] == 3000
    and package_hours == {"正课": 24.0, "考级": 1.0, "竞赛": 1.0},
    "预置课包是 3000 元：正课24＋考级1＋竞赛1",
)
ok(db.voucher_plan(3000) == (0.0, 0), "普通 3000 元缴费不送券")
ok(
    db.voucher_plan(3000, package_selected=True) == (300.0, 10),
    "满 3000 元的固定课包送 10 张 300 元券",
)
ok(
    db.voucher_plan(5200, package_selected=True) == (520.0, 10),
    "5200 元固定课包送 10 张 520 元券",
)
ok(db.voucher_plan(720, package_selected=True) == (0.0, 0), "不满 3000 元不送券")
ok(db.voucher_plan(0) == (0.0, 0), "没花钱就不送")

small_kid = db.create_student({"name": "720 元学员", "grade": "二年级"})
db.create_payment(
    small_kid,
    "2026-10-01",
    [{"hour_type_id": zk_hour, "level_id": None, "hours": 6, "amount": 720}],
)
ok(db.list_vouchers(small_kid) == [], "普通 720 元缴费不再送代金券")
for p in db.list_payments(student_id=small_kid):
    db.delete_payment(p["id"])
db.delete_student(small_kid)

manual_3000 = db.create_payment(
    vou_kid,
    "2026-10-01",
    [{"hour_type_id": zk_hour, "level_id": None, "hours": 24, "amount": 3000}],
)
ok(db.list_vouchers(vou_kid) == [], "没有选择固定课包，即使 3000 元也不送券")
db.delete_payment(manual_3000)


def package_items(package: dict) -> list[dict]:
    return [
        {
            "hour_type_id": item["hour_type_id"],
            "level_id": None,
            "hours": item["hours"],
            "amount": package["price"] if index == 0 else 0,
            "package_item": True,
        }
        for index, item in enumerate(package["items"])
    ]


full_year_hour = next(
    h["id"] for h in db.list_hour_types() if h["name"] == "全年"
)
full_year_package_id = db.save_course_package(
    None,
    "全年 3000 元课包",
    3000,
    [{"hour_type_id": full_year_hour, "hours": 24}],
)
full_year_package = db.get_course_package(full_year_package_id)
ok(
    db.voucher_plan(3000, package_selected=True, has_regular=False) == (0.0, 0),
    "不含正课的固定课包即使满 3000 元也不送券",
)
ok(
    not find_text(app._course_packages_card(), "不送券（课包不含正课）"),
    "固定课包列表不显示“不送券”文字",
)
full_year_kid = db.create_student({"name": "全年券测试", "grade": "二年级"})
db.create_payment(
    full_year_kid,
    "2026-10-01",
    package_items(full_year_package),
    package_id=full_year_package["id"],
)
ok(
    db.list_vouchers(full_year_kid) == [],
    "全年课包实际缴费不会生成代金券",
)
for p in db.list_payments(student_id=full_year_kid):
    db.delete_payment(p["id"])
db.delete_student(full_year_kid)
db.delete_course_package(full_year_package_id)


v_first = db.create_payment(
    vou_kid,
    "2026-10-01",
    package_items(default_package),
    package_id=default_package["id"],
)
batches = db.list_vouchers(vou_kid)
ok(
    len(batches) == 1
    and batches[0]["count"] == 10
    and batches[0]["face"] == 300,
    "选择 3000 元固定课包才送 10 张 300 元券",
)
ok(batches[0]["expires_on"] == "2028-10-01", "有效期 24 个月")
ok(batches[0]["remain"] == 10, "刚发下来 10 张都能用")
ok(db.get_payment(v_first)["amount"] == 3000, "送券不影响这一笔的实收")

db.create_payment(
    vou_kid, "2026-10-02", [{"hour_type_id": js_hour, "level_id": None, "hours": 2, "amount": 5200}]
)
ok(len(db.list_vouchers(vou_kid)) == 1, "只交竞赛不送代金券")

the_voucher = db.available_vouchers(vou_kid)[0]
v_second = db.create_payment(
    vou_kid,
    "2026-11-01",
    [{"hour_type_id": zk_hour, "level_id": None, "hours": 10, "amount": 1500}],
    "用券交的",
    voucher_id=the_voucher["id"],
)
second = db.get_payment(v_second)
ok(second["amount"] == 1200 and second["voucher_amount"] == 300, "用券抵 300：名义 1500、实收 1200")
left = next(v for v in db.list_vouchers(vou_kid) if v["id"] == the_voucher["id"])
ok(left["remain"] == 9, "券本上从 10 张变 9 张")
ok(len(db.voucher_uses(the_voucher["id"])) == 1, "留下了使用记录")
ok(
    db.income_total(student_id=vou_kid) == 3000 + 5200 + 1200,
    "收入算实收现金（券抵的不算现金）",
)
ok(db.month_stats("2026-11")["voucher_used"] == 300, "报表里能看到这个月用券抵了 300")

# 一笔只用一张：同一张券不能再抵到另一笔上超过它的张数
for i in range(9):
    db.create_payment(
        vou_kid,
        "2026-11-02",
        [{"hour_type_id": zk_hour, "level_id": None, "hours": 1, "amount": 300}],
        "",
        voucher_id=the_voucher["id"],
    )
spent = next(v for v in db.list_vouchers(vou_kid) if v["id"] == the_voucher["id"])
ok(spent["remain"] == 0, "10 张券用满 10 笔之后就用完了")
try:
    db.create_payment(
        vou_kid,
        "2026-11-03",
        [{"hour_type_id": zk_hour, "level_id": None, "hours": 1, "amount": 300}],
        "",
        voucher_id=the_voucher["id"],
    )
    used_up_ok = False
except ValueError:
    used_up_ok = True
ok(used_up_ok, "用完了就不让再抵了")

# 界面上：缴费框里有代金券，学员页能看到券本
app.tab = 3
app.render()
app._open_payment_dialog(None, vou_kid)
dlg = top_dialog(page)
ok(find_dropdown(dlg, "用代金券") is not None, "缴费框里有「用代金券」")
ok(find_text(dlg, "本笔合计"), "缴费框把本笔合计单独汇总")
package_dd = find_dropdown(dlg, "缴费方式")
package_dd.value = str(default_package["id"])
package_dd.on_select(Evt(package_dd))
ok(find_text(dlg, "送 10 张 300 元的代金券"), "选固定课包后当场显示送券")
ok(any(isinstance(c, ft.DataTable) for c in walk(dlg)), "固定课包用简洁表格展示")
try:
    find_field(dlg, "数量（课时）")
    has_package_input_rows = True
except AssertionError:
    has_package_input_rows = False
ok(not has_package_input_rows, "固定课包不再显示不可编辑的整排输入框")
ok(
    find_button(dlg, "额外赠送考级／比赛课时") is not None,
    "固定课包仍可额外添加赠送课时",
)
find_button(dlg, "额外赠送考级／比赛课时").on_click(None)
gift_type = find_dropdown(dlg, "赠送课时类型")
ok(
    all(str(hour_id) != str(zk_hour) for hour_id in [o.key for o in gift_type.options]),
    "额外赠送里不能选择正课",
)
gift_type.value = str(js_hour)
find_field(dlg, "赠送数量").value = "1"
click(dlg, "保存")
ok(
    find_field(top_dialog(page), "备注").error == "赠送课时必须写明原因",
    "课包额外赠送也要先写备注原因",
)
find_field(top_dialog(page), "备注").value = "老师额外赠送比赛 1 课时"
click(top_dialog(page), "保存")
package_gift_payment = next(
    p
    for p in db.list_payments(vou_kid)
    if p["note"] == "老师额外赠送比赛 1 课时"
)
ok(
    package_gift_payment["amount"] == 3000
    and any(
        item["hour_type_name"] == "竞赛" and item["hours"] == 1
        for item in db.list_payment_items(package_gift_payment["id"])
    ),
    "带备注的课包额外赠送可以保存",
)

app.tab = 7
app.render()
ok(find_text(page.controls[0], "固定课包"), "设置里能管理固定课包")
ok(find_button(page.controls[0], "新增课包") is not None, "设置里有新增课包按钮")
app._open_course_package_dialog(default_package)
dlg = top_dialog(page)
ok(find_field(dlg, "课包名称").value == "3000 元固定课包", "课包设置能打开编辑")
ok(find_field(dlg, "课包价格（元）").value == "3000", "课包价格回显正确")
app._close()

app.tab = 0
app.open_student(vou_kid)
ok(find_text(page.controls[0], "代金券"), "学员页有代金券卡片")
ok(find_text(page.controls[0], "已用完"), "用完的批次标着已用完")
app.open_student(None)

# 删掉那笔缴费，券要跟着回滚
db.delete_payment(v_second)
back = next(v for v in db.list_vouchers(vou_kid) if v["id"] == the_voucher["id"])
ok(back["remain"] == 1, "删掉那笔缴费，抵掉的券退回来了")
db.delete_payment(v_first)
ok(
    [v for v in db.list_vouchers(vou_kid) if v["id"] == the_voucher["id"]],
    "送券的那笔删了，但券已经用出去过，券本留着",
)

# 竞赛缴费：能用券，但不发券
p_new = db.create_payment(
    vou_kid,
    "2026-12-01",
    package_items(default_package),
    package_id=default_package["id"],
)
fresh_batch = next(v for v in db.list_vouchers(vou_kid) if v["payment_id"] == p_new)
ok(
    fresh_batch["face"] == 300 and fresh_batch["count"] == 10,
    "固定课包再次缴费仍送 10 张 300 元券",
)
race_pay = db.create_payment(
    vou_kid,
    "2026-12-05",
    [{"hour_type_id": js_hour, "level_id": None, "hours": 2, "amount": 520}],
    "竞赛用券交的",
    voucher_id=fresh_batch["id"],
)
race = db.get_payment(race_pay)
ok(
    race["amount"] == 220 and race["voucher_amount"] == 300,
    "竞赛缴费也能用 300 元固定课包券",
)
ok(
    [v for v in db.list_vouchers(vou_kid) if v["payment_id"] == race_pay] == [],
    "竞赛缴费本身不送券",
)
ok(
    next(v for v in db.list_vouchers(vou_kid) if v["id"] == fresh_batch["id"])["remain"] == 9,
    "竞赛用掉的那张从券本上减掉了",
)

for p in db.list_payments(student_id=vou_kid):
    db.delete_payment(p["id"])
db.delete_student(vou_kid)

print("13. 兑换积分")
lesson_id = db.create_lesson("2026-09-12", "10:30", 90, zhengke["id"], gpl3["id"], "讲循环")
db.add_attendance(lesson_id, sid)
ok(db.student_points(sid) == 30, "上课赚了 30 分")

app.tab = 5
app.render()
ok(find_text(page.controls[0], "30 分"), "报表页显示孩子的积分")
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

app.tab = 5
app.render()
ok(find_text(page.controls[0], "小玩具"), "报表页能看到兑换记录")
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

app._save_attendance_flag(att, "attendance", False)
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
app.lesson_keyword = "张晨希"  # 用搜索找到那节补课
app.render()
ok(find_text(page.controls[0], "补 张晨希 9月19日 周六 请假的那节"), "课次列表上也写明补的是哪节")
app.lesson_keyword = ""
app.render()

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
app._save_attendance_flag(att2, "attendance", False)
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
app._save_attendance_flag(att2, "attendance", True)
ok(db.pending_makeup_count(sid) == 0, "改回出勤，待补课自动撤掉")
app._save_attendance_flag(att2, "attendance", False)
db.cancel_makeup(db.list_makeups("待补", sid)[0]["id"], "家长不补了")
ok(db.pending_makeup_count(sid) == 0, "标记「不补了」也能关掉")
for l in db.list_lessons():
    db.delete_lesson(l["id"])
ok(zhengke_balance() == 24, "把课次都删掉，课时回到 24")

print("15. 试听跟进")
app.tab = 2
app.trial_filter = ""
app.render()
app._open_trial_dialog()
dlg = top_dialog(page)
find_field(dlg, "孩子姓名 *").value = "徐在贤"
find_dropdown(dlg, "年级").value = "四年级"
type_school(dlg, "育才小学")  # 手打，试一下试听记录这条也能存
find_field(dlg, "家长称呼（妈妈／爸爸）").value = "妈妈"
find_field(dlg, "联系电话").value = "13900000000"
find_field(dlg, "来源").value = "朋友介绍"
find_field(dlg, "试听日期（可不填）").value = "2026-09-30"
find_field(dlg, "备注（孩子情况、家长想法…）").value = "试过核桃，妈妈是老师"
click(dlg, "保存")
trials = db.list_trials()
ok(
    db.list_students(keyword="徐在贤") == [],
    "纯试听记录不会生成正式学员或学生账号",
)
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
new_sid = app._convert_trial_with_account(trial)
app.render()
ok(len(db.list_students()) == student_count + 1, "转正式后多了一份学员档案")
new_student = db.get_student(new_sid)
ok(new_student["name"] == "徐在贤" and new_student["grade"] == "四年级", "档案信息带过去了")
ok(db.get_student_user(new_sid) is not None, "试听转正式后自动生成学生账号")
ok(find_text(top_dialog(page), "学生账号已生成"), "试听转正式后显示初始账号")
app._close()
ok(new_student["school"] == "育才小学", "学校也从试听记录带过去了")
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
ok(
    photos[0]["stored_name"].startswith(f"photo_a{att_photo}_")
    and photos[0]["stored_name"].isascii()
    and " " not in photos[0]["stored_name"],
    "照片存成带归属的 ASCII 文件名，以后迁移不怕中文和重名",
)
photo_path = db.UPLOAD_DIR / photos[0]["stored_name"]
ok(photo_path.exists() and photo_path.stat().st_size == 1234, "照片真的写进磁盘了")
ok(db.file_url(photos[0]).endswith(photos[0]["stored_name"]), "图片地址拼得对")
ok(db.human_size(1234) == "1 KB", "文件大小显示成人话")

# 全班合影挂在课次上：传一次，所有孩子都能用
class_photo_button = find_button(page.controls[0], "加课堂照片")
class_photo_button.on_click(Evt(class_photo_button))
ok(
    app._upload_target == ("lesson", lesson_file, "照片"),
    "点课堂照片按钮会立即记下上传目标",
)
app._on_files_picked(FakeEvent([FakeFile("全班合影.jpg", b"c" * 777)]))
class_photos = db.list_files("lesson", lesson_file, "照片")
ok(
    len(class_photos) == 1 and class_photos[0]["filename"] == "全班合影.jpg",
    "全班照片挂在课次上",
)
ok(
    class_photos[0]["stored_name"].startswith(f"photo_l{lesson_file}_")
    and class_photos[0]["stored_name"].isascii(),
    "课堂照片的文件名带上课次编号",
)
app.open_lesson(lesson_file)
ok(find_text(page.controls[0], "课堂内容"), "课次详情里有课堂内容区")
ok(find_text(page.controls[0], "课堂照片（1 张）"), "课堂照片并在课堂内容里")
ok(find_button(page.controls[0], "加课堂照片") is not None, "能直接上传课堂照片")

# 教案：Markdown 渲染 + 本地图片自动改链接
_md_text, _md_pending, _md_missing = app._prepare_markdown_upload(
    [
        FakeFile("第一课.md", "# 第一课\n\n![步骤](images/step1.png)\n".encode("utf-8")),
        FakeFile("step1.png", b"png-bytes"),
    ]
)
ok("![步骤](/" in _md_text and "images/step1.png" not in _md_text, "本地图片链接改成了站内地址")
ok(len(_md_pending) == 1 and not _md_missing, "引用的图片进入待上传列表")
ok(
    _md_pending[0]["stored_name"].startswith("planimg_")
    and _md_pending[0]["stored_name"].isascii(),
    "Markdown 图片也用安全的文件名",
)
_md_bad_text, _md_bad_pending, _md_bad_missing = app._prepare_markdown_upload(
    [FakeFile("缺图.md", "![步骤](images/none.png)".encode("utf-8"))]
)
ok(_md_bad_missing == ["none.png"] and not _md_bad_pending, "缺图片时能说清缺哪张")
db.set_lesson_plan(lesson_file, _md_text)
app._save_plan_uploads(lesson_file, _md_pending)
app.open_lesson(lesson_file)
ok(
    any(isinstance(c, ft.Markdown) for c in walk(page.controls[0])),
    "教案用 Markdown 控件显示",
)
ok(find_button(page.controls[0], "上传 Markdown") is not None, "详情页能上传 Markdown")

# 手机原图自动压小：长边 1600、几百 KB，给家长看还看得清
try:
    from PIL import Image as _Image
    from PIL import ImageDraw as _ImageDraw
except ImportError:
    _Image = None
if _Image is not None:
    import io as _io

    _raw_buf = _io.BytesIO()
    _Image.effect_noise((3000, 2000), 40).convert("RGB").save(
        _raw_buf, "JPEG", quality=95, optimize=True
    )
    _raw = _raw_buf.getvalue()
    app._set_upload_target("attendance", att_photo, "照片")
    app._on_files_picked(FakeEvent([FakeFile("大照片.jpg", _raw)]))
    _big = [
        f for f in db.list_files("attendance", att_photo, "照片") if f["filename"] == "大照片.jpg"
    ][0]
    _big_path = db.UPLOAD_DIR / _big["stored_name"]
    _shrunk = _Image.open(_big_path)
    ok(_big["stored_name"].endswith(".jpg"), "压过的照片还是 jpg")
    ok(_big_path.stat().st_size < len(_raw), f"4 MB 的大照片压小了（{db.human_size(_big['size'])}）")
    ok(_big["size"] == _big_path.stat().st_size, "数据库里的大小和磁盘上的对得上")
    ok(max(_shrunk.size) <= 1600, "照片长边压到 1600 像素以内")
    ok(
        abs(_shrunk.size[0] / _shrunk.size[1] - 1.5) < 0.05,
        "照片没被拉变形（长宽比还是原来的 3:2）",
    )

    # 做海报：孩子的照片 + 课评 + 老师点评，拼成一张图
    import poster as _poster_mod

    ok(_poster_mod.teacher_label("李昂") == "李老师", "海报上老师只写姓＋老师")
    ok(_poster_mod.teacher_label("欧阳娜娜") == "欧阳老师", "复姓也认得出来")
    db.set_meta("poster_brand", "拾光机器人")
    db.set_meta("poster_contact", "微信 138-0000-0000")
    ok(db.get_meta("poster_brand") == "拾光机器人", "海报署名存得住")
    _qr_buf = _io.BytesIO()
    _qr_image = _Image.new("RGB", (360, 360), "white")
    _qr_draw = _ImageDraw.Draw(_qr_image)
    for _qy in range(8):
        for _qx in range(8):
            if (_qx * 3 + _qy * 5) % 4 in (0, 1):
                _qr_draw.rectangle(
                    (18 + _qx * 40, 18 + _qy * 40, 50 + _qx * 40, 50 + _qy * 40),
                    fill="black",
                )
    _qr_image.save(_qr_buf, "PNG")
    app.tab = 7
    app.render()
    ok(find_text(page.controls[0], "机构名"), "海报署名默认用摘要表格")
    try:
        find_field(page.controls[0], "机构名（海报上角）")
        poster_form_by_default = True
    except AssertionError:
        poster_form_by_default = False
    ok(not poster_form_by_default, "海报署名不编辑时不显示输入框")
    click(page.controls[0], "编辑")
    click(page.controls[0], "上传二维码")
    app._on_files_picked(FakeEvent([FakeFile("联系二维码.png", _qr_buf.getvalue())]))
    _qr_stored = db.get_meta("poster_qr")
    ok(
        _qr_stored.startswith("poster_qr_")
        and (db.UPLOAD_DIR / _qr_stored).is_file(),
        "设置里能上传并保存海报二维码",
    )
    click(page.controls[0], "上传 Logo")
    app._on_files_picked(FakeEvent([FakeFile("机构Logo.png", _qr_buf.getvalue())]))
    _logo_stored = db.get_meta("poster_logo")
    ok(
        _logo_stored.startswith("poster_logo_")
        and (db.UPLOAD_DIR / _logo_stored).is_file(),
        "设置里能上传并保存机构 Logo",
    )
    app.tab = 1
    db.update_attendance(
        att_photo,
        attendance=1,
        discipline=1,
        performance=1,
        bonus=10,
        comment="今天很投入，主动帮同桌检查了一遍。",
    )
    db.update_lesson(
        lesson_file,
        "2026-10-17",
        "10:30",
        90,
        zhengke["id"],
        gpl3["id"],
        "今天讲数组：先复习循环，再让孩子自己搭。",
        "先复习循环，再讲数组",
    )
    app.open_lesson(lesson_file)
    ok(find_button(page.controls[0], "做海报") is not None, "每个孩子的点名里有「做海报」按钮")
    _comment_field = next(
        (
            c
            for c in walk(page.controls[0])
            if isinstance(c, ft.TextField) and "课评" in str(c.hint_text or "")
        ),
        None,
    )
    ok(_comment_field is not None, "课评可以直接在课堂内容里写")
    _comment_field.value = "直接写的课评，复习了循环"
    _comment_field.on_blur(type("Event", (), {"control": _comment_field})())
    ok(
        db.get_lesson(lesson_file)["comment"] == "直接写的课评，复习了循环",
        "离开课评输入框就自动保存",
    )
    click(page.controls[0], "编辑教案")
    _plan_editor = next(
        (
            c
            for c in walk(page.controls[0])
            if isinstance(c, ft.TextField) and "Markdown" in str(c.hint_text or "")
        ),
        None,
    )
    ok(_plan_editor is not None, "教案能在课堂内容里直接编辑")
    _plan_editor.value = "# 直接改的教案\n\n不用再进编辑课次。"
    click(page.controls[0], "保存教案")
    ok(
        db.get_lesson(lesson_file)["plan"] == "# 直接改的教案\n\n不用再进编辑课次。",
        "教案在课堂内容里保存成功",
    )
    _poster_buttons = [
        c
        for c in walk(page.controls[0])
        if isinstance(c, ft.Button) and c.content == "做海报"
    ]
    ok(len(_poster_buttons) >= 2, "课堂内容的照片旁也有「做海报」按钮")
    app._make_class_poster_for_lesson(db.get_lesson(lesson_file))
    _class_lesson_poster = top_dialog(page)
    ok(find_text(_class_lesson_poster, "班级课堂海报"), "课堂内容能直接做班级海报")
    app._close()
    app._open_poster_for(att_photo, lesson_file)
    _choose = top_dialog(page)
    ok(find_text(_choose, "选照片做海报"), "多张照片时先弹出选照片")
    _boxes = [c for c in walk(_choose) if isinstance(c, ft.Checkbox)]
    ok(len(_boxes) == 3, "三张照片都能选")
    _main_photo_dd = find_dropdown(_choose, "主照片（铺满大图）")
    ok(
        len(_main_photo_dd.options) == 3 and _main_photo_dd.value,
        "做海报前能明确指定哪张是主照片",
    )
    for b in _boxes:
        b.value = False
    _boxes[0].value = True
    click(_choose, "做海报")
    _dlg = top_dialog(page)
    _poster_img = next(
        (c for c in walk(_dlg) if isinstance(c, ft.Image) and str(c.src).startswith("/posters/")),
        None,
    )
    ok(_poster_img is not None, "海报弹窗里显示这张图")
    ok(
        not any(
            isinstance(c, (ft.Button, ft.TextButton)) and c.content == "下载图片"
            for c in walk(_dlg)
        ),
        "海报弹窗不再显示无法使用的下载按钮",
    )
    _poster_files = sorted((db.UPLOAD_DIR / "posters").glob("poster_s*.jpg"))
    ok(len(_poster_files) == 1, "海报存到 data/files/posters 里")
    _poster = _Image.open(_poster_files[0])
    ok(_poster.width == 1080 and _poster.height > 900, "海报是 1080 宽的长图")
    ok(_poster_files[0].stat().st_size > 30 * 1024, "海报画质够看（不是几十 KB 的糊图）")

    _att = db.get_attendance(att_photo)
    _lesson = db.get_lesson(lesson_file)
    _poster_data = app._poster_data(_att, _lesson, [])
    ok(_poster_data.subject == "GPL", "海报带上了科目（背景按科目配色）")
    ok(_poster_data.student_name == "", "海报画面不出现孩子名字")
    ok(
        {mark.label for mark in _poster_data.point_marks if mark.earned}
        == {"出勤", "纪律", "学习", "突出"},
        "海报积分拆成不同类别的星星",
    )
    ok(
        _poster_data.qr_code
        and _poster_data.qr_code == (db.UPLOAD_DIR / _qr_stored).read_bytes(),
        "海报数据带上二维码",
    )
    ok(
        _poster_data.logo
        and _poster_data.logo == (db.UPLOAD_DIR / _logo_stored).read_bytes(),
        "海报数据带上机构 Logo",
    )
    _all_poster_photos = db.list_files("attendance", att_photo, "照片") + class_photos
    _chosen_main = _all_poster_photos[1]
    _main_raw, _work_raws = app._poster_photo_parts(
        _all_poster_photos, _chosen_main["id"]
    )
    ok(
        _main_raw
        == (db.UPLOAD_DIR / _chosen_main["stored_name"]).read_bytes()
        and len(_work_raws) == 2,
        "明确指定的照片作为主图，其余照片进入作品叠层",
    )

    def _poster_photo(color):
        buf = _io.BytesIO()
        _Image.new("RGB", (700, 900), color).save(buf, "JPEG", quality=90)
        return buf.getvalue()

    _portrait_blob = _poster_photo((190, 225, 245))
    _work_blob = _poster_photo((255, 178, 86))
    _portrait_only = _poster_mod.build_poster(
        _poster_mod.PosterData(
            student_name="",
            date_line="2026-10-17 10:30",
            subject="GPL",
            portrait_photo=_portrait_blob,
            seed="portrait-only",
        )
    )
    _with_work_and_points = _poster_mod.build_poster(
        _poster_mod.PosterData(
            student_name="",
            date_line="2026-10-17 10:30",
            subject="GPL",
            portrait_photo=_portrait_blob,
            work_photos=(_work_blob,),
            points_text="本次积分 +40",
            seed="portrait-only",
        )
    )
    ok(
        _Image.open(_io.BytesIO(_portrait_only)).width
        == _Image.open(_io.BytesIO(_with_work_and_points)).width,
        "作品照放在海报左下角，海报仍是 1080 宽长图",
    )
    ok(_portrait_only != _with_work_and_points, "作品和积分确实画进了孩子海报")

    # 海报背景跟着科目走：科创／图形化／无人机……不能张张一样
    _theme_keys = {
        _s: _poster_mod.theme_for(_s).key
        for _s in ("STEM", "GPL-竞赛-Zecode", "UAV-社团", "PY", "MCU", "Ev3", "")
    }
    ok(_theme_keys["STEM"] == "stem", "科创课的海报走蓝图纸背景")
    ok(_theme_keys["GPL-竞赛-Zecode"] == "scratch", "图形化编程课的海报走积木背景")
    ok(_theme_keys["UAV-社团"] == "uav", "无人机课的海报走航线背景")
    ok(
        _theme_keys["PY"] == "python" and _theme_keys["MCU"] == "hardware",
        "Python／单片机各走一套背景",
    )
    ok(_theme_keys[""] == "stem", "没填科目的课退到科创背景")
    ok(len(set(_theme_keys.values())) >= 4, "不同科目至少 4 套背景")

    def _demo_poster(subject: str, seed: str) -> bytes:
        return _poster_mod.build_poster(
            _poster_mod.PosterData(
                student_name="测试同学",
                date_line="2026-10-17 10:30",
                class_line="Lvl-03 · 90 分钟",
                subject=subject,
                lesson_comment="今天讲数组，复习了循环。",
                student_comment="很投入。",
                keywords=("循环",),
                seed=seed,
            )
        )

    _blobs = [
        _demo_poster(_s, "2026-10-17|10:30|1")
        for _s in ("STEM", "GPL", "UAV-社团", "PY", "MCU")
    ]
    ok(len({hash(_b) for _b in _blobs}) == 5, "五门课的海报背景各不相同")
    ok(
        _demo_poster("GPL", "2026-10-17|10:30|1") == _demo_poster("GPL", "2026-10-17|10:30|1"),
        "同一节课做的海报每次都一样",
    )
    ok(
        _demo_poster("GPL", "2026-10-17|10:30|1") != _demo_poster("GPL", "2026-10-24|10:30|1"),
        "同一门课换个课次，花纹也会挪一挪",
    )
    for _b in _blobs:
        _img = _Image.open(_io.BytesIO(_b))
        ok(_img.width == 1080 and _img.height > 500, "换了背景以后海报还是 1080 宽的长图")

    _named = app._poster_data(_att, dict(_lesson, teacher_name="高正元"), [])
    ok(_named.teacher_name == "高老师", "海报页脚：高正元 → 高老师，不直呼全名")
    _tags = _poster_data.tags
    ok(any(t.startswith("本次积分") for t in _tags), "海报上写着这次的积分")
    ok(
        all(not t.startswith(("出勤", "纪律", "学习", "时长")) for t in _tags),
        "每节都一样的出勤/纪律/学习/时长不再占地方",
    )
    _absent = app._poster_data(dict(_att, attendance=0), _lesson, [])
    ok("请假" in _absent.tags, "请假那节课的海报上标「请假」")
    ok(any(t.startswith("本月出勤") for t in _tags), "海报上写着本月出勤次数")
    ok("循环" in _poster_data.keywords, "海报从课评里认出了「循环」这个知识点")

    import keywords as _keywords

    ok(
        _keywords.extract_keywords("今天做的是底座。抽壳第一次接触，倒角跟圆角分得清。", limit=3)
        == ["底座", "抽壳", "倒角"],
        "知识点提取：按课评里出现的先后取词",
    )
    ok(
        _keywords.extract_keywords("今天没干什么，就是复习。") == [],
        "课评里没有知识点就不硬凑",
    )

    # 本月出勤：只数这个月已经上过的课，请假算总数不算出勤
    _before = db.month_attendance_summary(sid, "2026-10", "2026-10-17")
    _m1 = db.create_lesson("2026-10-10", "10:30", 90, zhengke["id"], gpl3["id"])
    _m2 = db.create_lesson("2026-10-20", "10:30", 90, zhengke["id"], gpl3["id"])
    _m3 = db.create_lesson("2026-10-12", "10:30", 90, zhengke["id"], gpl3["id"])
    _a1 = db.add_attendance(_m1, sid)
    db.update_attendance(_a1, attendance=1)
    _a2 = db.add_attendance(_m2, sid)
    db.update_attendance(_a2, attendance=1)
    _a3 = db.add_attendance(_m3, sid)
    db.update_attendance(_a3, attendance=0)
    _after = db.month_attendance_summary(sid, "2026-10", "2026-10-17")
    ok(_after[1] == _before[1] + 2, "本月出勤：后面的课不算进来，请假算进总数")
    ok(_after[0] == _before[0] + 1, "本月出勤：请假那节不算「出勤」")
    _next = db.create_lesson("2026-10-24", "10:30", 90, zhengke["id"], gpl3["id"])
    db.add_attendance(_next, sid)
    ok(
        any(t.startswith("下次课") for t in app._poster_data(_att, _lesson, []).tags),
        "海报上写着下次课的时间",
    )
    db.delete_lesson(_next)
    for _lid in (_m1, _m2, _m3):
        db.delete_lesson(_lid)
    app._close()
    for _p in _poster_files:
        _p.unlink()
    db.delete_file(_big["id"])

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
ok(find_text(page.controls[0], "还没有课程"), "排课表一开始是空的")

# 造一个别的级别的孩子，用来验证固定课表的候选名单也会筛
py_level_t = next(l for l in db.list_levels() if db.level_full_name(l) == "PY-Lvl-02")
bystander = db.create_student({"name": "别的级别娃", "grade": "三年级"})
db.create_enrollment(bystander, py_level_t["id"], zhengke["id"], 60)

app._open_template_dialog()
dlg = top_dialog(page)
_weekday_tile = next(c for c in walk(dlg) if isinstance(c, ft.ExpansionTile))
ok(not _weekday_tile.expanded, "上课日平时折叠，不占大块空间")
name_field = find_field(dlg, "课程名（自动生成，也可自己改）")
name_field.value = "自检班"
find_checkbox(dlg, "周六").value = True
find_checkbox(dlg, "周日").value = True
find_field(dlg, "周六时间").value = "10:30"
find_field(dlg, "周日时间").value = "09:00"
find_field(dlg, "时长（分钟）").value = "90"
level_dd = find_dropdown(dlg, "等级 *")
try:
    find_dropdown(dlg, "课型")
    course_type_visible = True
except AssertionError:
    course_type_visible = False
ok(not course_type_visible, "新增课程不显示课型，直接按等级判断")
click(dlg, "保存")
ok(
    level_dd.error == "请选择等级" and db.list_templates() == [],
    "新增课程必须选择等级",
)
level_dd.value = str(gpl3["id"])
level_dd.on_select(None)
_form_order = list(walk(dlg))
ok(
    _form_order.index(name_field)
    < _form_order.index(level_dd)
    < _form_order.index(_weekday_tile),
    "课程名、必选等级在前，然后才是上课时间",
)
ok(listed_in(dlg, "张晨希"), "排课表：选了等级，本级别的孩子还在")
ok(not listed_in(dlg, "别的级别娃"), "排课表：别的级别的孩子被筛掉")
find_checkbox(dlg, "也显示别的级别的孩子").value = True
find_checkbox(dlg, "也显示别的级别的孩子").on_change(None)
ok(listed_in(dlg, "别的级别娃"), "排课表：勾上开关，别的级别又出来了")
find_checkbox(dlg, "也显示别的级别的孩子").value = False
find_checkbox(dlg, "也显示别的级别的孩子").on_change(None)
find_checkbox(dlg, "张晨希").value = True
click(dlg, "保存")
templates = db.list_templates()
ok(len(templates) == 1, "固定课表建好了")
ok(
    templates[0]["start_time"] == "10:30"
    and templates[0]["class_type_name"] == "正课"
    and templates[0]["student_count"] == 1
    and templates[0]["weekday"] == 5
    and templates[0]["weekdays"] == "5,6"
    and db.template_day_times(templates[0]) == {5: "10:30", 6: "09:00"},
    "记下了多个上课日、时间和人数",
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
ok(db.get_lesson(lessons[0]["id"])["rolled"] == 0, "照课表建出来的课先挂着「待点名」")
ok(
    db.create_lesson_from_template(templates[0]["id"], "2026-10-03") == lessons[0]["id"],
    "同一天不会重复建课",
)
app.open_schedule(True)
app.schedule_date = "2026-10-03"
app.render()
try:
    find_button(page.controls[0], "去点名")
    rolled = True
except AssertionError:
    rolled = False
ok(rolled, "排好的课显示「去点名」")
ok(
    find_text(page.controls[0], "周六 10:30")
    and find_text(page.controls[0], "周日 09:00"),
    "固定课表里逐天写着各自时间",
)

db.delete_template(templates[0]["id"])
ok(db.list_templates() == [], "课表能删掉")
for l in db.list_lessons():
    db.delete_lesson(l["id"])
db.delete_student(bystander)

print("17b. 学期课：一次排一学期，上完再点名")
sem_kid = db.create_student({"name": "学期娃", "grade": "二年级"})
db.create_enrollment(sem_kid, gpl3["id"], zhengke["id"], 90)
sem_hour_id = next(a["hour_type_id"] for a in db.get_accounts(sem_kid) if a["name"] == "正课")
db.add_hours(sem_kid, sem_hour_id, 20, note="缴费 20 课时")

sem_tid = db.create_template(
    5,
    "09:00",
    90,
    zhengke["id"],
    gpl3["id"],
    "秋季学期班",
    "2026-09-01",
    "2026-10-31",
    name="秋季班",
)
db.set_template_students(sem_tid, [sem_kid])
dates = db.template_dates(db.get_template(sem_tid))
ok(len(dates) == 9 and dates[0] == "2026-09-05", "每周六的日期算得对（9 次）")

result = db.generate_template_lessons(sem_tid)
ok(len(result["made"]) == 9, "一次把整学期的课都排上了")
ok(
    {a["name"]: a["balance"] for a in db.get_accounts(sem_kid)}["正课"] == 20,
    "刚排完课，课时一分没扣",
)
ok(db.student_points(sem_kid) == 0, "刚排完课，积分也没加")
sem_lessons = db.template_lessons(sem_tid)
ok(all(l["rolled"] == 0 for l in sem_lessons), "排出来的课都是「待点名」")

db.roll_call(sem_lessons[0]["id"])
ok(
    {a["name"]: a["balance"] for a in db.get_accounts(sem_kid)}["正课"] == 18.5,
    "点完名才扣 1.5 课时",
)
ok(db.student_points(sem_kid) == 30, "点完名才加积分")

again = db.generate_template_lessons(sem_tid)
ok(not again["made"] and len(again["skipped"]) == 9, "再排一次不会重复建课")

after = db.template_lessons(sem_tid)
ok(after[0]["lesson_date"] == "2026-09-05" and after[0]["rolled"] == 1, "点过名那节还在原地")
ok(
    after[1]["lesson_date"] == "2026-09-12" and after[1]["rolled"] == 0,
    "没点名的第二节还挂着「待点名」",
)

app.open_schedule(True)
app.schedule_date = "2026-09-12"
app.render()
ok(find_text(page.controls[0], "这一周的课"), "排课表里有周视图")
ok(find_text(page.controls[0], "周六"), "周视图里有周六这一列")
ok(find_text(page.controls[0], "待点名"), "周视图上标着还没点名的课")
open_lesson = find_button(page.controls[0], "去点名")
open_lesson.on_click(None)
ok(app.lesson_id == after[1]["id"], "点「去点名」能进那节课")
app.open_schedule(False)

db.set_lesson_comment(after[1]["id"], "这周讲了变量和循环")
app.open_schedule(True)
app.schedule_date = "2026-09-12"
app.render()
try:
    find_button(page.controls[0], "做海报")
    course_has_poster = True
except AssertionError:
    course_has_poster = False
ok(not course_has_poster, "课程列表不再显示「做海报」")

db.delete_template(sem_tid)
sem_enrollments = db.list_enrollments(sem_kid)
ok(
    len(sem_enrollments) == 1 and sem_enrollments[0]["class_id"] is None,
    "删班级后报名还在，只是不再挂在这个班下面",
)
remaining_lessons = db.list_lessons()
ok(
    len(remaining_lessons) == 9
    and all(l["template_id"] is None for l in remaining_lessons),
    "删班级后已排的课还在，班名链接自动解除（老库也不会再报外键）",
)
for l in db.list_lessons():
    db.delete_lesson(l["id"])
db.delete_student(sem_kid)

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

print("20. 课时明细只读，课时统一走缴费")
sid2 = db.create_student({"name": "课时测试", "grade": "三年级"})
db.create_enrollment(sid2, gpl3["id"], zhengke["id"], 90)
hour_id = next(a["hour_type_id"] for a in db.get_accounts(sid2) if a["name"] == "正课")
def balance2():
    return {a["name"]: a for a in db.get_accounts(sid2)}["正课"]["balance"]

tx = db.add_hours(sid2, hour_id, 10, kind="充值", note="历史手记课时", source_type="manual")
ok(balance2() == 10, "历史手记课时仍然能正常显示")
app.tab = 0
app.open_student(sid2)
try:
    find_button(page.controls[0], "调整课时")
    has_adjust = True
except AssertionError:
    has_adjust = False
ok(not has_adjust, "学员账户不再显示调整课时")
app._open_hour_ledger(sid2, hour_id)
dlg = top_dialog(page)
ok(find_text(dlg, "历史手记课时"), "明细里能看到历史手记")
ok(find_text(dlg, "手记"), "手记的流水有标记")
try:
    find_button(dlg, "记一笔")
    ledger_can_add = True
except AssertionError:
    ledger_can_add = False
ok(not ledger_can_add, "课时明细里不再提供手记入口")
ok(
    not any(
        isinstance(c, ft.IconButton)
        and c.tooltip in ("改这一笔", "删这一笔")
        for c in walk(dlg)
    ),
    "历史手记流水也不能在这里改删",
)
db.delete_hour_transaction(tx)
ok(balance2() == 0, "测试历史流水清理完成")

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
app.tab = 3
app.render()
app._open_payment_dialog(None, sid2)
dlg = top_dialog(page)
find_dropdown(dlg, "课时类型").value = str(hour_id)
find_field(dlg, "数量（课时）").value = "24"
find_field(dlg, "金额（元）").value = "3000"
# 加一行赠送的考级
add_row_btn = find_button(dlg, "加一行")
add_row_btn.on_click(None)
rows = [f for f in walk(dlg) if isinstance(f, ft.Dropdown) and f.label == "课时类型"]
ok(len(rows) == 2, "能加第二行课时")
rows[1].value = str(kaoji_id)
fields = [f for f in walk(dlg) if isinstance(f, ft.TextField) and f.label == "数量（课时）"]
fields[1].value = "1"
amounts = [f for f in walk(dlg) if isinstance(f, ft.TextField) and f.label == "金额（元）"]
amounts[1].value = "0"
click(dlg, "保存")
ok(
    find_field(top_dialog(page), "备注").error == "赠送课时必须写明原因",
    "手动赠送考级课时没填备注时不予添加",
)
find_field(top_dialog(page), "备注").value = "老师赠送考级 1 课时"
click(top_dialog(page), "保存")
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
gift_tx = [
    t
    for t in db.list_hour_transactions(sid2, limit=100000)
    if t["source_type"] == "payment_item"
    and (t["note"] or "").startswith("赠送课时")
]
ok(len(gift_tx) == 1 and gift_tx[0]["hour_type_name"] == "考级", "流水上标着赠送")
ok(db.income_total(student_id=sid2) == 3000, "收入还是 3000")
try:
    db.create_payment(
        sid2,
        "2026-09-06",
        [{"hour_type_id": hour_id, "hours": 1, "amount": 0}],
        "想赠送一节正课",
    )
    free_regular_allowed = True
except ValueError:
    free_regular_allowed = False
ok(not free_regular_allowed, "正课不能作为赠送课时手动添加")

app.tab = 3
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
for sheet_name in ["学员", "报名课程", "课时账户", "上课记录", "点名明细", "课时流水", "缴费记录", "积分流水", "试听记录", "课程", "老师"]:
    if sheet_name not in workbook_xml:
        raise AssertionError(f"导出里少了表：{sheet_name}")
checks += 1
print("  ✓ 十一张表都在（学员、报名课程、课时账户、上课记录、点名明细、课时流水、缴费记录、积分流水、试听记录、课程、老师）")
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

teacher2_id = db.create_user(
    "wang_perm", "pw123456", "王老师（权限测试）", db.ROLE_TEACHER
)
other_level_id = db.create_level(
    "权限测试", "别人等级", 30, default_teacher_id=teacher2_id
)
app.tab = 7
app.render()
ok(
    find_text(page.controls[0], "可编辑本人负责的记录"),
    "老师登录后明确显示自己的权限范围",
)
ok(find_text(page.controls[0], "我的等级"), "普通老师能看到自己的等级入口")
ok(find_button(page.controls[0], "新增等级"), "普通老师可以新增自己的等级")
app._open_level_dialog(None)
dlg = top_dialog(page)
level_teacher = find_dropdown(dlg, "默认老师（报名时自动带出）")
ok(
    level_teacher.disabled and level_teacher.value == str(teacher_id),
    "普通老师新建等级时，归属固定为自己",
)
find_field(dlg, "科目（如 GPL、STEM）").value = "权限测试"
find_field(dlg, "等级／阶段（如 Lvl-01）").value = "我的等级"
find_field(dlg, "默认时长（分钟）").value = "45"
click(dlg, "保存")
own_level = next(
    l for l in db.list_levels() if db.level_full_name(l) == "权限测试-我的等级"
)
other_level = next(
    l for l in db.list_levels() if l["id"] == other_level_id
)
ok(
    own_level["default_teacher_id"] == teacher_id,
    "普通老师新建的等级归自己",
)
ok(
    app._can_manage_level(own_level)
    and not app._can_manage_level(other_level),
    "自己的等级能管理，别人的等级只读",
)

own_course = db.create_template(
    5,
    "08:00",
    90,
    zhengke["id"],
    gpl3["id"],
    name="老师自己的课程",
    teacher_id=teacher_id,
)
other_course = db.create_template(
    6,
    "09:00",
    90,
    zhengke["id"],
    gpl3["id"],
    name="其他老师的课程",
    teacher_id=teacher2_id,
)
own_course_row = db.get_template(own_course)
other_course_row = db.get_template(other_course)
ok(
    app._can_manage_course(own_course_row)
    and not app._can_manage_course(other_course_row),
    "自己的课程能管理，别人的课程只读",
)

# 工作台必须按当前老师收窄，而不是只隐藏操作按钮。
today_iso = date.today().isoformat()
dash_own_course = db.create_template(
    date.today().weekday(),
    "07:10",
    45,
    zhengke["id"],
    gpl3["id"],
    start_date=today_iso,
    end_date=today_iso,
    teacher_id=teacher_id,
    name="工作台本人课程",
)
dash_other_course = db.create_template(
    date.today().weekday(),
    "07:20",
    45,
    zhengke["id"],
    gpl3["id"],
    start_date=today_iso,
    end_date=today_iso,
    teacher_id=teacher2_id,
    name="工作台他人课程",
)
dash_own_trial = db.create_trial(
    {
        "name": "工作台本人试听",
        "status": "待试听",
        "owner_teacher_id": teacher_id,
    }
)
dash_other_trial = db.create_trial(
    {
        "name": "工作台他人试听",
        "status": "待试听",
        "owner_teacher_id": teacher2_id,
    }
)
dash_own_student = db.create_student(
    {
        "name": "工作台本人低课时",
        "owner_teacher_id": teacher_id,
        "owner_manual": True,
    }
)
dash_other_student = db.create_student(
    {
        "name": "工作台他人低课时",
        "owner_teacher_id": teacher2_id,
        "owner_manual": True,
    }
)
for student_id, owner_id in (
    (dash_own_student, teacher_id),
    (dash_other_student, teacher2_id),
):
    db.create_payment(
        student_id,
        today_iso,
        [
            {
                "hour_type_id": zhengke["id"],
                "level_id": gpl3["id"],
                "hours": 2,
                "amount": 200,
                "owner_teacher_id": owner_id,
            }
        ],
        "工作台权限测试",
    )
app.tab = TAB_DASHBOARD
app.render()
ok(
    find_text(page.controls[0], "工作台本人课程")
    and not find_text(page.controls[0], "工作台他人课程"),
    "老师工作台只显示自己的今日课程",
)
ok(
    find_text(page.controls[0], "工作台本人试听")
    and not find_text(page.controls[0], "工作台他人试听"),
    "老师工作台只显示自己的试听跟进",
)
ok(
    find_text(page.controls[0], "工作台本人低课时")
    and not find_text(page.controls[0], "工作台他人低课时"),
    "老师工作台只显示自己学员的课时预警",
)
app.filter_owner = None
app._apply_user_defaults()
app.tab = 0
app.student_id = None
app.render()
ok(
    app.filter_owner == str(teacher_id)
    and find_text(page.controls[0], "我的学员")
    and find_text(page.controls[0], "工作台本人低课时")
    and not find_text(page.controls[0], "工作台他人低课时"),
    "老师进入学员页默认只显示自己名下学员",
)
app.filter_owner = ""
app.render()
ok(
    find_text(page.controls[0], "工作台本人低课时")
    and find_text(page.controls[0], "工作台他人低课时"),
    "老师仍可主动切换到全部学员",
)
for trial_id in (dash_own_trial, dash_other_trial):
    db.delete_trial(trial_id)
for student_id in (dash_own_student, dash_other_student):
    db.delete_student(student_id)
db.delete_template(dash_own_course)
db.delete_template(dash_other_course)
app.tab = 7
app.render()

app._open_template_dialog(own_course_row)
dlg = top_dialog(page)
course_teacher = find_dropdown(dlg, "课程老师（这门课归谁）")
ok(
    course_teacher.disabled and course_teacher.value == str(teacher_id),
    "普通老师只能把课程建在自己名下",
)
app._close()

own_student = db.create_student(
    {
        "name": "李老师的学员",
        "grade": "三年级",
        "owner_teacher_id": teacher_id,
        "owner_manual": True,
    }
)
other_student = db.create_student(
    {
        "name": "王老师的学员",
        "grade": "三年级",
        "owner_teacher_id": teacher2_id,
        "owner_manual": True,
    }
)
ok(
    app._can_manage_student(own_student)
    and not app._can_manage_student(other_student),
    "自己的学员能编辑，别人的学员只读",
)
own_perm_lesson = db.create_lesson(
    "2026-10-20",
    "16:00",
    90,
    zhengke["id"],
    gpl3["id"],
    teacher_id=teacher_id,
    template_id=own_course,
    rolled=0,
)
db.add_attendance(own_perm_lesson, own_student)
other_perm_lesson = db.create_lesson(
    "2026-10-20",
    "18:00",
    90,
    zhengke["id"],
    gpl3["id"],
    teacher_id=teacher2_id,
    template_id=other_course,
    rolled=0,
)
other_attendance_id = db.add_attendance(other_perm_lesson, other_student)
makeup_own_lesson = db.create_lesson(
    "2026-10-21",
    "16:00",
    90,
    zhengke["id"],
    gpl3["id"],
    kind="补课",
    teacher_id=teacher_id,
    template_id=other_course,
    rolled=0,
)
db.add_attendance(makeup_own_lesson, own_student)
app.tab = 1
app.open_lesson(own_perm_lesson)
ok(
    find_button(page.controls[0], "点名") is not None
    and find_button(page.controls[0], "编辑课次") is not None
    and find_button(page.controls[0], "添加孩子") is not None,
    "自己的课可以点名学生、编辑和添加孩子",
)
own_comment = next(
    c
    for c in walk(page.controls[0])
    if isinstance(c, ft.TextField) and "课评" in str(c.hint_text or "")
)
ok(not own_comment.read_only, "自己的课可以编辑课评")
app.open_lesson(other_perm_lesson)
other_lesson_tree = page.controls[0]
for label in ("点名", "编辑课次", "添加孩子"):
    try:
        find_button(other_lesson_tree, label)
        visible = True
    except AssertionError:
        visible = False
    ok(not visible, f"其他老师的课不显示「{label}」")
ok(find_text(other_lesson_tree, "只读"), "其他老师的课明确标为只读")
other_comment = next(
    c
    for c in walk(other_lesson_tree)
    if isinstance(c, ft.TextField) and "课评" in str(c.hint_text or "")
)
ok(other_comment.read_only, "其他老师的课评只读")
app._save_lesson_comment(other_perm_lesson, "越权修改")
app._save_attendance_flag(other_attendance_id, "attendance", False)
ok(
    (db.get_lesson(other_perm_lesson)["comment"] or "") == ""
    and db.get_attendance(other_attendance_id)["attendance"] == 1,
    "即使绕过界面调用，也不能改其他老师的课评和点名",
)
app._set_upload_target("lesson", other_perm_lesson, "照片")
app._on_files_picked(
    FakeEvent([FakeFile("越权班级照片.jpg", b"not-allowed")])
)
ok(
    db.list_files("lesson", other_perm_lesson, "照片") == [],
    "其他老师选完照片后仍会被权限校验拦住",
)
app.open_lesson(makeup_own_lesson)
ok(
    find_button(page.controls[0], "编辑课次") is not None
    and find_button(page.controls[0], "点名") is not None,
    "补课由实际上课老师编辑，不受原课程归属限制",
)
app.tab = 0
app.lesson_id = None
app.open_student(own_student)
ok(find_text(page.controls[0], "基本档案"), "自己的学员档案默认表格展示")
ok(find_button(page.controls[0], "编辑") is not None, "老师能进入自己学员的档案编辑")
find_button(page.controls[0], "编辑").on_click(None)
ok(not find_field(page.controls[0], "姓名 *").disabled, "老师能编辑自己的学员档案")
ok(find_button(page.controls[0], "新增报名") is not None, "老师能给自己的学员新增报名")
ok(find_button(page.controls[0], "记一笔") is not None, "老师能给自己学员新增缴费")
app.open_student(other_student)
other_student_tree = page.controls[0]
try:
    find_button(other_student_tree, "编辑")
    other_profile_editable = True
except AssertionError:
    other_profile_editable = False
ok(not other_profile_editable, "其他老师的学员档案没有编辑入口")
try:
    find_field(other_student_tree, "姓名 *")
    other_profile_form = True
except AssertionError:
    other_profile_form = False
ok(not other_profile_form, "其他老师的学员档案只读表格")
try:
    find_button(other_student_tree, "新增报名")
    other_enroll_editable = True
except AssertionError:
    other_enroll_editable = False
ok(not other_enroll_editable, "不能替其他老师的学员新增报名")
try:
    find_button(other_student_tree, "调整课时")
    other_hours_editable = True
except AssertionError:
    other_hours_editable = False
ok(not other_hours_editable, "不能调整其他老师的学员课时")
try:
    find_button(other_student_tree, "记一笔")
    other_payable = True
except AssertionError:
    other_payable = False
ok(not other_payable, "不能替其他老师的学员新增缴费")

app._open_new_student()
dlg = top_dialog(page)
new_student_owner = find_dropdown(dlg, "归属老师（新学员归你）")
ok(
    new_student_owner.disabled and new_student_owner.value == str(teacher_id),
    "普通老师新建学员自动归自己",
)
app._close()

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
app.tab = 3
app.render()
ok(find_button(page.controls[0], "记一笔") is not None, "普通老师可以新增缴费")
app._open_payment_dialog(None, own_student)
dlg = top_dialog(page)
student_choices = find_dropdown(dlg, "孩子")
ok(
    str(other_student) not in {str(o.key) for o in student_choices.options},
    "缴费时不能选择其他老师的学员",
)
owner_field = find_dropdown(dlg, "归属老师（算谁的客户）")
ok(
    owner_field.disabled and owner_field.value == str(teacher_id),
    "普通老师新增缴费时归属固定为自己",
)
find_dropdown(dlg, "课时类型").value = str(zhengke["id"])
find_dropdown(dlg, "报的等级").value = str(gpl3["id"])
find_field(dlg, "数量（课时）").value = "12"
find_field(dlg, "金额（元）").value = "1200"
click(dlg, "保存")
teacher_payments = db.list_payments(own_student)
ok(len(teacher_payments) == 1, "普通老师给自己学员记的缴费保存成功")
teacher_payment_items = db.list_payment_items(teacher_payments[0]["id"])
ok(
    teacher_payment_items[0]["owner_teacher_id"] == teacher_id,
    "新增缴费归属自动记在当前老师名下",
)
ok(
    {a["name"]: a["balance"] for a in db.get_accounts(own_student)}["正课"] == 12,
    "普通老师新增缴费后课时正常加上了",
)
app.tab = 0
app.open_student(own_student)
try:
    find_button(page.controls[0], "调整课时")
    own_adjust_visible = True
except AssertionError:
    own_adjust_visible = False
ok(not own_adjust_visible, "自己学员的账户里也没有调整课时入口")
ok(
    find_text(page.controls[0], "常规课时统一走缴费")
    and find_text(page.controls[0], "转学生自带的课时"),
    "学员账户明确区分缴费和转入课时",
)
app._open_hour_ledger(own_student, zhengke_hour_id)
dlg = top_dialog(page)
try:
    find_button(dlg, "记一笔")
    own_ledger_add_visible = True
except AssertionError:
    own_ledger_add_visible = False
ok(not own_ledger_add_visible, "课时明细里也没有手记入口")
app._close()
app.tab = 1
app.lesson_id = None
app.show_schedule = False
app.render()
ok(find_button(page.controls[0], "记一节课") is not None, "老师还能在「课程」里记一节课、点名")

app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
db.delete_payment(db.list_payments(own_student)[0]["id"])
db.delete_lesson(makeup_own_lesson)
db.delete_lesson(other_perm_lesson)
db.delete_lesson(own_perm_lesson)
db.delete_student(own_student)
db.delete_student(other_student)
db.delete_template(own_course)
db.delete_template(other_course)
db.delete_level(own_level["id"], force=True)
db.delete_level(other_level_id, force=True)
db.delete_user(teacher2_id)
db.delete_user(teacher_id)
ok(len(db.list_users()) == 1, "老师账号能删掉")

print("25. 缴费时顺手把报名课程建好")
app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
s6 = db.create_student({"name": "新缴费学员", "grade": "三年级"})
ok(db.list_enrollments(s6) == [], "新学员还没有报名课程")
app.tab = 3
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
app.schedule_date = today.isoformat()
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
ok(find_text(tree, "上课记录（最近 1 次"), "学员页多了一块上课记录")
ok(find_text(tree, "扣 1.5 课时"), "学员页能看到这次扣了多少课时")
ok(find_text(tree, "+30 分"), "学员页能看到这次得了多少分")

db.delete_lesson(lesson_x)
db.delete_student(s4)
db.delete_student(s5)

print("28. 老师和归属（一个孩子两个老师 / 谁上的课给谁）")
app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
t_a = db.create_user("wang", "pw123456", "王老师", db.ROLE_TEACHER, "13800000001")
t_b = db.create_user("li", "pw123456", "李老师", db.ROLE_TEACHER, "13800000002")
ok(
    {t["id"] for t in db.list_teachers()} == {t_a, t_b},
    "两个上课老师列出来了（管理员默认不算上课老师）",
)
ok(
    db.get_user(t_a)["phone"] == "13800000001",
    "老师档案上有电话",
)

mcu_level = next(l for l in db.list_levels() if db.level_full_name(l) == "MCU-Lvl-02")
db.update_level(gpl3["id"], gpl3["subject"], gpl3["name"], gpl3["default_minutes"], t_a)
db.update_level(
    mcu_level["id"],
    mcu_level["subject"],
    mcu_level["name"],
    mcu_level["default_minutes"],
    t_b,
)
level_teachers = {db.level_full_name(l): l["default_teacher_name"] for l in db.list_levels()}
ok(
    level_teachers.get("GPL-Lvl-03") == "王老师"
    and level_teachers.get("MCU-Lvl-02") == "李老师",
    "课程默认老师设好了（GPL→王老师，MCU→李老师）",
)

kid2 = db.create_student({"name": "归属娃", "grade": "三年级"})
db.create_enrollment(kid2, gpl3["id"], zhengke["id"], 90)
db.create_enrollment(kid2, mcu_level["id"], zhengke["id"], 120)
owners = {e["level_name"]: e["owner_teacher_name"] for e in db.list_enrollments(kid2)}
ok(
    owners.get("Lvl-03") == "王老师" and owners.get("Lvl-02") == "李老师",
    "一个孩子的两门课分属两个老师（报名定归属）",
)

lesson_t = db.create_lesson(
    "2026-10-04", "10:00", 90, zhengke["id"], gpl3["id"], teacher_id=t_b
)
db.add_attendance(lesson_t, kid2)
att_t = db.list_attendance(lesson_t)[0]
ok(att_t["owner_teacher_id"] == t_a, "点名上的归属还是报名的王老师")
ok(db.get_lesson(lesson_t)["teacher_id"] == t_b, "这节课的「上课老师」是代课的李老师")

# 原课老师即使不是学员归属老师，也应当能安排自己课上的补课。
cross_makeup_student = db.create_student(
    {
        "name": "跨归属补课测试",
        "grade": "三年级",
        "owner_teacher_id": t_a,
        "owner_manual": True,
    }
)
cross_makeup_lesson = db.create_lesson(
    "2026-10-05",
    "11:00",
    90,
    zhengke["id"],
    gpl3["id"],
    teacher_id=t_b,
)
cross_attendance = db.add_attendance(cross_makeup_lesson, cross_makeup_student)
db.update_attendance(cross_attendance, attendance=0)
db.sync_makeup_for_attendance(cross_attendance)
cross_makeup = db.list_makeups("待补", cross_makeup_student)[0]
app.user = {
    "id": t_b,
    "username": "li",
    "display_name": "李老师",
    "role": db.ROLE_TEACHER,
}
app.tab = 0
app.student_id = None
app.open_student(cross_makeup_student)
ok(
    find_button(page.controls[0], "安排补课"),
    "原课老师能安排补课，即使学员归属是另一位老师",
)
find_button(page.controls[0], "安排补课").on_click(None)
ok(
    find_field(top_dialog(page), "补课日期") is not None,
    "原课老师点击安排补课能打开表单",
)
app._close()
db.delete_student(cross_makeup_student)
db.delete_lesson(cross_makeup_lesson)
app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}

h_zk = next(h for h in db.list_hour_types() if h["name"] == "正课")
h_js = next(h for h in db.list_hour_types() if h["name"] == "竞赛")
pay_mix = db.create_payment(
    kid2,
    "2026-10-04",
    [
        {
            "hour_type_id": h_zk["id"],
            "level_id": gpl3["id"],
            "hours": 24,
            "amount": 3000,
            "owner_teacher_id": t_a,
        },
        {
            "hour_type_id": h_js["id"],
            "level_id": mcu_level["id"],
            "hours": 10,
            "amount": 1000,
            "owner_teacher_id": t_b,
        },
    ],
)
ok(db.get_payment(pay_mix)["teacher_id"] is None, "跨两个老师的缴费，主表标成混合")
ok(
    {i["owner_teacher_name"] for i in db.list_payment_items(pay_mix)}
    == {"王老师", "李老师"},
    "缴费明细行各归各的老师",
)

pay_one = db.create_payment(
    kid2,
    "2026-10-04",
    [{"hour_type_id": h_zk["id"], "level_id": gpl3["id"], "hours": 1, "amount": 500}],
)
ok(
    db.get_payment(pay_one)["teacher_id"] == t_a,
    "缴费行没写归属时，按课程默认老师自动归到王老师",
)

report = {r["teacher_id"]: r for r in db.teacher_report("2026-10")}
ok(abs(report[t_a]["income"] - 3500) < 0.01, "按老师算归属实收：王老师 3500 元")
ok(abs(report[t_b]["income"] - 1000) < 0.01, "按老师算归属实收：李老师 1000 元")
ok(
    report[t_b]["lessons"] == 1 and report[t_b]["hours"] == 1.5,
    "谁上的课给谁：李老师上了 1 节、1.5 课时",
)
ok(report[t_a]["lessons"] == 0, "王老师没上这节课，不算他上课课时")
ok(
    report[t_a]["students"] == 1 and report[t_b]["students"] == 1,
    "在读学生按报名归属各算一个",
)

trial_t = db.create_trial(
    {"name": "线索娃", "status": "已试听", "owner_teacher_id": t_b}
)
conv = db.convert_trial_to_student(trial_t)
ok(
    db.get_student(conv)["owner_teacher_id"] == t_b,
    "试听转正后，跟进老师变成学员默认归属",
)

# 老数据补全：把归属清掉，再一键按课程默认老师补回来
db.update_enrollment(db.list_enrollments(kid2)[0]["id"], gpl3["id"], zhengke["id"], 90, "在读", "", None)
ok(db.list_enrollments(kid2)[0]["owner_teacher_id"] is None, "先把这条报名的归属清掉")
db.backfill_teacher_attribution()
ok(
    db.list_enrollments(kid2)[0]["owner_teacher_id"] == t_a,
    "一键补全：没指定归属的报名按课程默认老师补上",
)

# 老课次没填上课老师的，也能一键补（按学生归属／课程默认老师）
db.update_lesson(
    lesson_t,
    "2026-10-04",
    "10:00",
   90,
    zhengke["id"],
    gpl3["id"],
    "",
    "",
    "",
    None,
)
ok(db.get_lesson(lesson_t)["teacher_id"] is None, "先把这节课的上课老师清掉")
db.backfill_lesson_teachers()
ok(
    db.get_lesson(lesson_t)["teacher_id"] == t_a,
    "按学生归属给没填的老课次补上上课老师",
)

db.init_db()
ok(len(db.list_teachers()) == 2, "重复初始化数据库也不会丢老师")

# 名下有记录的老师不能删（否则老记录会变成孤儿），只能停用
try:
    db.delete_user(t_a)
    blocked = False
except ValueError:
    blocked = True
ok(blocked and db.get_user(t_a) is not None, "名下有记录的老师不能删，改成停用")

# 界面上：报名 / 记一节课 / 缴费 / 试听 / 固定课表 都有老师下拉
app.tab = 0
app.open_student(None)
app.render()
ok(
    find_text(page.controls[0], "归属老师：王老师、李老师"),
    "学员列表上能看到归属老师",
)

app._open_enrollment_dialog(kid2, None)
dlg = top_dialog(page)
ok(find_dropdown(dlg, "归属老师（算谁的客户）") is not None, "报名框里有归属老师")
app._close()

app.tab = 1
app.lesson_id = None
app.show_schedule = False
app.render()
app._open_lesson_dialog()
dlg = top_dialog(page)
ok(find_dropdown(dlg, "上课老师（谁上的课给谁）") is not None, "记一节课有上课老师")
app._close()

# 老师登录时，新记录的默认上课老师是他自己
app.user = {"id": t_a, "username": "wang", "display_name": "王老师", "role": db.ROLE_TEACHER}
app._open_lesson_dialog()
dlg = top_dialog(page)
ok(
    find_dropdown(dlg, "上课老师（谁上的课给谁）").value == str(t_a),
    "老师自己登录记课，默认上课老师是他自己",
)
app._close()
app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}

app.tab = 3
app.render()
app._open_payment_dialog(None, kid2)
dlg = top_dialog(page)
ok(find_dropdown(dlg, "归属老师（算谁的客户）") is not None, "缴费每一行都有归属老师")
app._close()

app.tab = 2
app.render()
app._open_trial_dialog()
dlg = top_dialog(page)
ok(find_dropdown(dlg, "跟进老师（算谁的客户）") is not None, "试听有跟进老师")
app._close()

app.tab = 1
app.show_schedule = True
app.render()
app._open_template_dialog()
dlg = top_dialog(page)
ok(find_dropdown(dlg, "课程老师（这门课归谁）") is not None, "新增课程能选课程老师")
app._close()
app.show_schedule = False

app.tab = 7
app.render()
ok(find_text(page.controls[0], "老师账号"), "设置页有老师账号")
ok(find_text(page.controls[0], "默认老师 王老师"), "课程设置里能看到默认老师")

app.tab = 5
app.render()
ok(find_text(page.controls[0], "按老师"), "报表里有「按老师」一栏")
app.tab = 0

print("29. 上课记录按周看 / 缴费按月看")
app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
this_monday = today - timedelta(days=today.weekday())
last_monday = this_monday - timedelta(days=7)

week_kid = db.create_student({"name": "本周娃"})
old_kid = db.create_student({"name": "上周娃"})
l_this_week = db.create_lesson(
    this_monday.isoformat(), "10:00", 90, zhengke["id"], gpl3["id"]
)
db.add_attendance(l_this_week, week_kid)
l_last_week = db.create_lesson(
    last_monday.isoformat(), "10:00", 90, zhengke["id"], gpl3["id"]
)
db.add_attendance(l_last_week, old_kid)

app.tab = 1
app.lesson_id = None
app.lesson_keyword = ""
app.schedule_date = this_monday.isoformat()
app.render()
ok(find_text(page.controls[0], "这天的课"), "课程页有「这天的课」")
ok(find_text(page.controls[0], "本周娃"), "本周的课看得到")
ok(not find_text(page.controls[0], "上周娃"), "不在这一天的课就不列出来")

app.schedule_date = last_monday.isoformat()
app.render()
ok(find_text(page.controls[0], "上周娃"), "翻到上一周，看到上周那节课")
app._shift_day(1)
ok(app.schedule_date == (last_monday + timedelta(days=1)).isoformat(), "「后一天」能翻")
app._goto_today()
ok(app.schedule_date == today.isoformat(), "点「今天」回到今天")

# 搜索还是全时间段找
box = find_search(page.controls[0])
box.value = "上周娃"
box.on_submit(Evt(box))
ok(find_text(page.controls[0], "共 1 节课") and find_text(page.controls[0], "上周娃"), "搜索是全时间段的")
app.lesson_keyword = ""
app.render()

pay_kid = db.create_student({"name": "按月娃"})
this_month = today.strftime("%Y-%m")
last_month_day = (today.replace(day=1) - timedelta(days=1)).isoformat()
db.create_payment(
    pay_kid,
    today.isoformat(),
    [{"hour_type_id": h_zk["id"], "level_id": gpl3["id"], "hours": 1, "amount": 777}],
    "本月的钱",
)
db.create_payment(
    pay_kid,
    last_month_day,
    [{"hour_type_id": h_zk["id"], "level_id": gpl3["id"], "hours": 1, "amount": 333}],
    "上月的钱",
)

app.tab = 3
app.payment_month = ""
app.render()
ok(find_text(page.controls[0], "（本月）"), "缴费默认停在本月")
ok(find_text(page.controls[0], "777 元"), "本月的缴费看得到")
ok(not find_text(page.controls[0], "333 元"), "别的月份的缴费不在这一屏")
ok(
    find_text(page.controls[0], f"{today.year} 年 {int(today.month)} 月收入"),
    "上面写着这个月收了多少",
)

app._shift_payment_month(-1)
ok(find_text(page.controls[0], "333 元"), "翻到上个月，看到上月那笔")
ok(not find_text(page.controls[0], "777 元"), "上个月这一屏里没有本月的钱")
app._shift_payment_month(1)
app._this_payment_month()
ok(app.payment_month == "" and find_text(page.controls[0], "（本月）"), "点「本月」回到本月")
ok(find_text(page.controls[0], "缴费记录"), "缴费页还在")

print("30. 班级：同一门课两个班、两个老师")
app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}

cls_a = db.create_template(
    0, "10:00", 90, zhengke["id"], gpl3["id"], teacher_id=t_a, name="GPL-03 周一班"
)
cls_b = db.create_template(
    3, "10:00", 90, zhengke["id"], gpl3["id"], teacher_id=t_b, name="GPL-03 周四班"
)
dual_kid = db.create_student({"name": "两班娃", "grade": "四年级"})
db.set_template_students(cls_a, [dual_kid])
db.set_template_students(cls_b, [dual_kid])
ok(db.class_label(db.get_template(cls_a)) == "GPL-03 周一班", "班级能起名字")
ok(
    db.class_label({"weekday": 2, "start_time": "15:00", "subject": "PY", "level_name": "Lvl-01"})
    == "周三 15:00 PY-Lvl-01",
    "没起名字的班也能自动拼一个看得懂的名字",
)

e_a = db.create_enrollment(dual_kid, gpl3["id"], zhengke["id"], 90, class_id=cls_a)
e_b = db.create_enrollment(dual_kid, gpl3["id"], zhengke["id"], 90, class_id=cls_b)
dual_rows = db.list_enrollments(dual_kid)
ok(len(dual_rows) == 2, "同一个孩子、同一门课，能报两个班")
ok(
    {db.enrollment_class_label(e) for e in dual_rows}
    == {"GPL-03 周一班", "GPL-03 周四班"},
    "两条报名各自挂着班级",
)
ok(
    {e["owner_teacher_name"] for e in dual_rows} == {"王老师", "李老师"},
    "两个班各归各的老师",
)

lesson_a = db.create_lesson_from_template(cls_a, "2026-10-05")
lesson_b = db.create_lesson_from_template(cls_b, "2026-10-08")
db.add_attendance(lesson_a, dual_kid)
db.add_attendance(lesson_b, dual_kid)


def _owner_of(lesson_id: int, student_id: int) -> str:
    """这节课里这个孩子的归属老师。

    别图省事拿 list_attendance(...)[0]：同一天同一时间可能已经有别的课次
    （第 29 节按「今天」建的课就可能撞上），第一条点名未必是这个孩子。
    """
    return next(
        a["owner_teacher_name"]
        for a in db.list_attendance(lesson_id)
        if a["student_id"] == student_id
    )


ok(
    _owner_of(lesson_a, dual_kid) == "王老师",
    "周一班那节课，归属是王老师",
)
ok(
    _owner_of(lesson_b, dual_kid) == "李老师",
    "周四班那节课，归属是李老师",
)

pay_a = db.create_payment(
    dual_kid,
    "2026-10-05",
    [
        {
            "hour_type_id": h_zk["id"],
            "level_id": gpl3["id"],
            "hours": 2,
            "amount": 600,
            "enrollment_id": e_a,
        }
    ],
)
pay_b = db.create_payment(
    dual_kid,
    "2026-10-05",
    [
        {
            "hour_type_id": h_zk["id"],
            "level_id": gpl3["id"],
            "hours": 1,
            "amount": 400,
            "enrollment_id": e_b,
        }
    ],
)
ok(db.get_payment(pay_a)["teacher_id"] == t_a, "交周一班那笔，算王老师的")
ok(db.get_payment(pay_b)["teacher_id"] == t_b, "交周四班那笔，算李老师的")

# 同一门课两个老师、又没指定哪个班时，不瞎猜
pay_mix2 = db.create_payment(
    dual_kid,
    "2026-10-05",
    [{"hour_type_id": h_zk["id"], "level_id": gpl3["id"], "hours": 1, "amount": 100}],
)
ok(
    db.list_payment_items(pay_mix2)[0]["owner_teacher_id"] is None,
    "没指定班级时，两个老师不猜，留空让人自己选",
)

# 结课是按课程走的
db.update_enrollment(e_a, gpl3["id"], zhengke["id"], 90, "结课", "", t_a, cls_a)
ok(
    db.get_student(dual_kid)["status"] == "在读",
    "一门课结课、另一门还在读，学员还是「在读」",
)
db.update_enrollment(e_b, gpl3["id"], zhengke["id"], 90, "结课", "", t_b, cls_b)
ok(
    db.get_student(dual_kid)["status"] == "在读",
    "课程都结课了，学员档案也不再写「结课」（结课只在课程上看）",
)
db.update_enrollment(e_a, gpl3["id"], zhengke["id"], 90, "在读", "", t_a, cls_a)
ok(db.get_student(dual_kid)["status"] == "在读", "改回在读就恢复")

# 界面上：课程名、课程下拉、缴费选哪门课
app.tab = 0
app.open_student(None)
app.render()
ok(find_text(page.controls[0], "GPL-03 周一班"), "学员列表上能看到课程名")

app._open_enrollment_dialog(dual_kid, None)
dlg = top_dialog(page)
ok(find_dropdown(dlg, "课程（可选）") is not None, "报名框里能选课程")
app._close()

app.tab = 1
app.lesson_id = None
app.render()
app._open_lesson_dialog()
dlg = top_dialog(page)
ok(find_dropdown(dlg, "课程（可选，用来定归属）") is not None, "记一节课能挂课程")
app._close()

app._open_template_dialog()
dlg = top_dialog(page)
ok(find_field(dlg, "课程名（自动生成，也可自己改）") is not None, "新增课程能起名字")
app._close()

app.tab = 3
app.render()
app._open_payment_dialog(None, dual_kid)
dlg = top_dialog(page)
ok(find_dropdown(dlg, "哪门课程（报名）") is not None, "缴费每一行能选是哪门课程")
app._close()
ok(
    find_text(page.controls[0], "GPL-03 周一班"),
    "缴费记录上写着这笔是哪个班的",
)

# 把没挂班的孩子加进班里，报名自动挂上班、归属跟着班老师
auto_kid = db.create_student({"name": "自动挂班娃"})
db.create_enrollment(auto_kid, gpl3["id"], zhengke["id"], 90)
ok(db.list_enrollments(auto_kid)[0]["class_id"] is None, "先是一条没挂班的报名")
db.set_template_students(cls_b, [auto_kid])
auto_row = db.list_enrollments(auto_kid)[0]
ok(
    auto_row["class_id"] == cls_b and auto_row["owner_teacher_name"] == "李老师",
    "加进周四班后，报名自动挂班、归属变成李老师",
)
db.update_template(
    cls_b, 3, "10:00", 90, zhengke["id"], gpl3["id"], teacher_id=t_a, name="GPL-03 周四班"
)
ok(
    db.list_enrollments(auto_kid)[0]["owner_teacher_name"] == "王老师",
    "给班换了老师，挂在班上的报名归属跟着换",
)
db.update_template(
    cls_b, 3, "10:00", 90, zhengke["id"], gpl3["id"], teacher_id=t_b, name="GPL-03 周四班"
)

sheets = {name: rows for name, _head, rows in db.export_tables()}
ok(len(sheets.get("课程", [])) >= 2, "导出里有课程表")
ok(
    any("GPL-03 周一班" in str(row[0]) for row in sheets["课程"]),
    "导出里带着课程名字",
)

# 课程起止日期：到期自动结课
old_cls = db.create_template(
    2,
    "10:00",
    90,
    zhengke["id"],
    gpl3["id"],
    teacher_id=t_a,
    name="春季班",
    start_date="2026-01-01",
    end_date="2026-03-31",
)
old_kid = db.create_student({"name": "结课娃"})
db.set_template_students(old_cls, [old_kid])
db.create_enrollment(old_kid, gpl3["id"], zhengke["id"], 90, class_id=old_cls)
ok(
    db.list_enrollments(old_kid)[0]["status"] == "结课",
    "报进一门已经过了结课日的课程，报名直接算结课",
)
ok(
    db.get_student(old_kid)["status"] == "在读",
    "学员档案状态不受课程结课影响（避免混淆）",
)
ok(db.course_status(db.get_template(old_cls)) == "已结课", "课程本身显示「已结课」")

db.update_template(
    old_cls,
    2,
    "10:00",
    90,
    zhengke["id"],
    gpl3["id"],
    start_date="2026-01-01",
    end_date="2026-12-31",
    teacher_id=t_a,
    name="春季班",
)
ok(
    db.list_enrollments(old_kid)[0]["status"] == "在读",
    "把结课日改到以后，自动结课的报名又回到在读",
)
ok(db.get_student(old_kid)["status"] == "在读", "学生状态也跟着回来")

future_cls = db.create_template(
    4,
    "10:00",
    90,
    zhengke["id"],
    gpl3["id"],
    name="下学期班",
    start_date="2099-01-01",
    end_date="2099-06-30",
)
ok(db.course_status(db.get_template(future_cls)) == "未开课", "还没到开班日 → 未开课")

app.tab = 1
app.show_schedule = True
app.render()
ok(find_text(page.controls[0], "已结课") or find_text(page.controls[0], "在读"), "课程列表上有状态")
app.show_schedule = False
app.tab = 0

print("31. 学员状态不带结课 / 监护人 / 上课记录点进详情")
app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
ok(
    db.STUDENT_STATUS == ["在读", "停课", "离校"],
    "学员档案区分在读、暂时停课和已经离校",
)

app.tab = 0
app.student_id = None
app.render()
status_dd = find_dropdown(page.controls[0], "状态")
ok(
    [o.key for o in status_dd.options] == ["全部", "在读", "停课", "离校"],
    "学员列表可以筛选在读、停课和离校",
)

g_kid = db.create_student({"name": "监护娃", "grade": "二年级", "guardian": "张爸爸"})
ok(db.get_student(g_kid)["guardian"] == "张爸爸", "学员档案能存监护人姓名")
app.open_student(g_kid)
tree = page.controls[0]
find_button(tree, "编辑").on_click(None)
tree = page.controls[0]
ok(find_field(tree, "监护人姓名").value == "张爸爸", "学员档案上能看到监护人")
profile_status = find_dropdown(tree, "状态")
ok(
    [o.text for o in profile_status.options] == ["在读", "停课", "离校"],
    "学员基本档案能明确选择离校",
)

away_kid = db.create_student(
    {"name": "已离校测试", "grade": "三年级", "status": "离校"}
)
away_enrollment = db.create_enrollment(
    away_kid,
    gpl3["id"],
    zhengke["id"],
    90,
    owner_teacher_id=t_a,
)
db.refresh_student(away_kid)
ok(
    db.get_student(away_kid)["status"] == "离校"
    and db.list_students(status="离校")[0]["id"] == away_kid,
    "离校状态不会被仍然在读的旧报名自动改回来",
)
db.delete_enrollment(away_enrollment)
db.delete_student(away_kid)

stopped_alert_kid = db.create_student(
    {"name": "停课但要提醒", "grade": "三年级", "status": "停课"}
)
left_alert_kid = db.create_student(
    {"name": "离校不要提醒", "grade": "三年级", "status": "离校"}
)
warn_hour_id = next(
    account["hour_type_id"]
    for account in db.get_accounts(stopped_alert_kid)
    if account["name"] == "正课"
)
for kid in (stopped_alert_kid, left_alert_kid):
    db.add_hours(
        kid,
        warn_hour_id,
        2,
        kind="充值",
        source_type="manual",
    )
alert_names = {row["student"] for row in db.hour_alerts()}
dashboard_alert_names = {
    row["title"] for row in app._dashboard_shortages()
}
ok(
    "停课但要提醒" in alert_names
    and "停课但要提醒" in dashboard_alert_names
    and "离校不要提醒" not in alert_names
    and "离校不要提醒" not in dashboard_alert_names,
    "课时不足统计保留停课，但排除离校",
)
db.delete_student(stopped_alert_kid)
db.delete_student(left_alert_kid)

g_lesson = db.create_lesson(today.isoformat(), "10:00", 90, zhengke["id"], gpl3["id"])
db.add_attendance(g_lesson, g_kid)
app.open_student(g_kid)
tree = page.controls[0]
ok(find_text(tree, "点一条看详情"), "学员页的上课记录写着可以点开")
day_text = f"{today.month}月{today.day}日 周{'一二三四五六日'[today.weekday()]}"
row = None
for control in walk(tree):
    if (
        isinstance(control, ft.Container)
        and control.on_click is not None
        and find_text(control, day_text)
    ):
        row = control
        break
ok(row is not None, "上课记录每条都是能点的")
row.on_click(None)
ok(app.lesson_id == g_lesson, "点一条就进了那节课的详情")
ok(find_text(page.controls[0], "点名（1 人）"), "课次详情打开的是这一节")
app.open_lesson(None)
ok(find_text(page.controls[0], "监护娃"), "返回又回到这个学员的档案")

db.delete_lesson(g_lesson)
db.delete_student(g_kid)

print("32. 还没交费时归属先按课程走 / 上课老师默认是归属老师")
app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
one_cls = db.create_template(
    1, "10:00", 90, zhengke["id"], gpl3["id"], teacher_id=t_a, name="单课班"
)
one_kid = db.create_student({"name": "单课娃", "grade": "三年级"})
db.set_template_students(one_cls, [one_kid])
db.create_enrollment(one_kid, gpl3["id"], zhengke["id"], 90, class_id=one_cls)
ok(
    db.get_student(one_kid)["owner_teacher_id"] == t_a,
    "报名以后，学员档案上的归属老师＝课程老师",
)

app.tab = 0
app.open_student(one_kid)
ok(find_text(page.controls[0], "王老师"), "档案里显示的归属是王老师")
app.open_student(None)
app.render()
ok(find_text(page.controls[0], "归属老师：王老师"), "列表上显示的也是王老师（不再对不上）")

db.update_template(
    one_cls, 1, "10:00", 90, zhengke["id"], gpl3["id"], teacher_id=t_b, name="单课班"
)
ok(
    db.get_student(one_kid)["owner_teacher_id"] == t_b,
    "课程换了老师，学员档案上的归属跟着换",
)
app.open_student(one_kid)
ok(find_text(page.controls[0], "李老师"), "档案里也跟着变成李老师")

app.tab = 1
app.lesson_id = None
app.render()
app._open_lesson_dialog()
dlg = top_dialog(page)
course_dd = find_dropdown(dlg, "课程（可选，用来定归属）")
course_dd.value = str(one_cls)
course_dd.on_select(None)
ok(
    find_dropdown(dlg, "上课老师（谁上的课给谁）").value == str(t_b),
    "选了课程，上课老师默认就是课程老师（归属老师）",
)
app._close()

print("33. 客户归属跟缴费走 / 课时费跟上课老师走")
owners_mix = db.student_owners(kid2)
ok(
    owners_mix and owners_mix[0]["source"] == "缴费",
    "交过费的学员，归属是按缴费算的",
)

# 单课娃：课程老师是李，但钱是王老师收的 → 客户归王老师
month_now = today.strftime("%Y-%m")
report_before = {r["teacher_id"]: r for r in db.teacher_report(month_now)}
db.create_payment(
    one_kid,
    today.isoformat(),
    [
        {
            "hour_type_id": h_zk["id"],
            "level_id": gpl3["id"],
            "hours": 1,
            "amount": 800,
            "owner_teacher_id": t_a,
        }
    ],
)
ok(
    db.get_student(one_kid)["owner_teacher_id"] == t_a,
    "钱是王老师收的，这个学员就归王老师",
)
ok(db.student_owners(one_kid)[0]["source"] == "缴费", "归属来源标成「缴费」")

# 这节课是李老师上的 → 李老师拿课时费；但客户还是王老师的
teach_lesson = db.create_lesson(
    today.isoformat(), "14:00", 90, zhengke["id"], gpl3["id"], teacher_id=t_b
)
db.add_attendance(teach_lesson, one_kid)
ok(db.get_lesson(teach_lesson)["teacher_id"] == t_b, "上课老师是李老师（课时费算他）")
ok(
    db.list_attendance(teach_lesson)[0]["owner_teacher_id"] == t_a,
    "点名上的归属（谁的客户）还是收钱的王老师",
)

report_now = {r["teacher_id"]: r for r in db.teacher_report(month_now)}
ok(
    abs(
        report_now[t_a]["income"]
        - report_before.get(t_a, {"income": 0})["income"]
        - 800
    )
    < 0.01,
    "多收的这 800 算进王老师的「归属实收」",
)
ok(
    report_now[t_b]["lessons"]
    == report_before.get(t_b, {"lessons": 0})["lessons"] + 1,
    "多上的这节课算进李老师的「上课节数」（课时费）",
)
ok(
    report_now[t_a]["lessons"] - report_before.get(t_a, {"lessons": 0})["lessons"] == 0,
    "王老师只收了钱、没上这节课，上课节数不动——两笔账分开",
)

app.tab = 0
app.open_student(one_kid)
ok(
    find_text(page.controls[0], "王老师")
    and find_text(page.controls[0], "按缴费"),
    "学员档案上写明归属是按缴费算的",
)
app.open_lesson(teach_lesson)
ok(find_text(page.controls[0], "归属 王老师"), "课次详情里学员归属是王老师")
ok(find_text(page.controls[0], "上课老师：李老师"), "课次详情里上课老师是李老师")
app.open_lesson(None)
app.tab = 0

print("34. 学员档案里的归属老师可以看、可以改")
app.tab = 0
app.open_student(one_kid)
tree = page.controls[0]
find_button(tree, "编辑").on_click(None)
tree = page.controls[0]
owner_dd = find_dropdown(tree, "归属老师（可改）")
ok(owner_dd.value == "auto", "默认是「跟缴费走（自动）」")
ok(
    find_text(tree, "王老师") and find_text(tree, "按缴费"),
    "档案上看得到现在算谁的",
)

owner_dd.value = str(t_b)
for control in walk(tree):
    if isinstance(control, (ft.Button, ft.TextButton)) and control.content == "保存":
        control.on_click(None)
        break
ok(db.get_student(one_kid)["owner_manual"] == 1, "手动改了归属，就钉住不再自动变")
ok(db.get_student(one_kid)["owner_teacher_id"] == t_b, "钉成了李老师")

app.open_student(one_kid)
ok(
    find_text(page.controls[0], "李老师")
    and find_text(page.controls[0], "手动指定"),
    "档案上显示手动指定的李老师",
)
app.open_student(None)
app.render()
ok(find_text(page.controls[0], "归属老师：李老师"), "学员列表上也跟着显示李老师")

app.open_student(one_kid)
tree = page.controls[0]
find_button(tree, "编辑").on_click(None)
tree = page.controls[0]
find_dropdown(tree, "归属老师（可改）").value = "auto"
for control in walk(tree):
    if isinstance(control, (ft.Button, ft.TextButton)) and control.content == "保存":
        control.on_click(None)
        break
ok(db.get_student(one_kid)["owner_manual"] == 0, "选回「跟缴费走」，钉住取消")
ok(
    find_text(page.controls[0], "王老师")
    and find_text(page.controls[0], "按缴费"),
    "又回到按缴费算（王老师）",
)

print("35. 课程名唯一 / 周视图显示课程名")
conn = sqlite3.connect(db.DB_PATH)
pk_cols = [r[1] for r in conn.execute("PRAGMA table_info(schedule_templates)") if r[5]]
conn.close()
ok(pk_cols == ["id"], "课程表有主键 id")
ok(db.get_template(one_cls)["id"] == one_cls, "课程按 id 能唯一找到")

try:
    db.create_template(2, "10:00", 90, zhengke["id"], gpl3["id"], name="单课班")
    name_dup = False
except ValueError:
    name_dup = True
ok(name_dup, "课程重名不让建")

try:
    db.create_template(2, "10:00", 90, zhengke["id"], gpl3["id"])
    name_empty = False
except ValueError:
    name_empty = True
ok(name_empty, "课程名不能空")

try:
    db.update_template(
        one_cls, 1, "10:00", 90, zhengke["id"], gpl3["id"], name="GPL-03 周一班"
    )
    rename_dup = False
except ValueError:
    rename_dup = True
ok(rename_dup, "改课程名也不能跟别人重名")

# 新建课程对话框：名字不填不给存
app.tab = 1
app.lesson_id = None
app.render()
app._open_template_dialog()
dlg = top_dialog(page)
click(dlg, "保存")
ok(
    bool(find_field(dlg, "课程名（自动生成，也可自己改）").error),
    "新建课程时课程名没填会拦住",
)
app._close()

# 周视图 / 这天的课上显示课程名
app.schedule_date = "2026-10-05"  # 周一，正好是"GPL-03 周一班"的上课日
app.render()
ok(find_text(page.controls[0], "GPL-03 周一班"), "课程表上显示课程名称")
ok(find_text(page.controls[0], "老师：王老师"), "课程卡片上也带着老师")

print("36. 课程名按规范生成（年份-学期-等级-类别-Cls-序号）")
ok(
    db.make_course_name("2026", "2", "STEM-Lvl-02-正课", 1)
    == "2026-2-STEM-Lvl-02-正课-Cls-01",
    "课程名能按「年份-学期-等级-类别-Cls-序号」拼出来",
)
parsed_name = db.parse_course_name("2026-2-STEM-Lvl-02-正课-Cls-03")
ok(
    parsed_name.get("year") == "2026"
    and parsed_name.get("term") == "2"
    and parsed_name.get("level_text") == "STEM-Lvl-02-正课"
    and parsed_name.get("seq") == 3,
    "规范课程名能拆回年份／学期／序号",
)
parsed_jingsai = db.parse_course_name("2026-2-GPL-竞赛-Zecode-小低组-竞赛-Cls-03")
ok(
    parsed_jingsai.get("level_text") == "GPL-竞赛-Zecode-小低组-竞赛"
    and parsed_jingsai.get("seq") == 3,
    "等级里带横杠（竞赛）的名字也能拆对",
)
ok(
    db.make_course_name("2026", "2", "GPL-竞赛-小低组-竞赛", 1)
    == "2026-2-GPL-竞赛-小低组-竞赛-Cls-01",
    "竞赛课的课程名按同样规则生成",
)
ok(
    db.next_course_seq("2099", "1", gpl3["id"]) == 1,
    "新的「年份＋学期＋等级」从 Cls-01 开始",
)
db.create_template(
    0,
    "10:00",
    90,
    zhengke["id"],
    gpl3["id"],
    name=db.make_course_name("2099", "1", db.level_display_name(gpl3), 1),
    year="2099",
    term="1",
    seq=1,
)
ok(
    db.next_course_seq("2099", "1", gpl3["id"]) == 2,
    "同一个年份＋学期＋等级，下一个自动是 Cls-02",
)

old_style = db.create_template(
    2,
    "11:00",
    90,
    zhengke["id"],
    gpl3["id"],
    name="2027-1-GPL-Lvl1-Cls7",
    year="2027",
    term="1",
    seq=7,
)
db.normalize_course_names()
ok(
    db.get_template(old_style)["name"]
    == db.make_course_name("2027", "1", db.level_display_name(gpl3), 7),
    "老写法的课程名能规范成标准写法",
)

app.tab = 1
app.lesson_id = None
app.render()
app._open_template_dialog()
dlg = top_dialog(page)
find_field(dlg, "年份").value = "2098"
find_dropdown(dlg, "学期").value = "2"
level_dd_g = find_dropdown(dlg, "等级 *")
level_dd_g.value = str(gpl3["id"])
level_dd_g.on_select(None)
ok(find_field(dlg, "班级序号").value == "01", "选了年份／学期／等级，序号自动填 01")
click(dlg, "生成课程名")
ok(
    find_field(dlg, "课程名（自动生成，也可自己改）").value
    == db.make_course_name("2098", "2", db.level_display_name(gpl3), 1),
    "点「生成课程名」按规范生成课程名",
)
app._close()

print("37. 课程名自动填 / 排课不能超出开班～结课")
app.tab = 1
app.lesson_id = None
app.render()
app._open_template_dialog()
dlg = top_dialog(page)
find_field(dlg, "年份").value = "2097"
find_dropdown(dlg, "学期").value = "2"
level_dd_auto = find_dropdown(dlg, "等级 *")
level_dd_auto.value = str(gpl3["id"])
level_dd_auto.on_select(None)
ok(
    find_field(dlg, "课程名（自动生成，也可自己改）").value
    == db.make_course_name("2097", "2", db.level_display_name(gpl3), 1),
    "选完等级，课程名自动填好，不用再点按钮",
)
app._close()

rng_cls = db.create_template(
    0,
    "09:00",
    90,
    zhengke["id"],
    gpl3["id"],
    name="2026-2-范围测试班",
    year="2026",
    term="2",
    seq=99,
    start_date="2026-10-01",
    end_date="2026-10-31",
)
ok(db.course_covers(db.get_template(rng_cls), "2026-10-05"), "开班范围内的日子算在课内")
ok(
    not db.course_covers(db.get_template(rng_cls), "2026-09-28"),
    "开班之前不算在课内",
)
ok(
    not db.course_covers(db.get_template(rng_cls), "2026-11-02"),
    "结课之后不算在课内",
)
ok(
    rng_cls in {t["id"] for t in db.templates_on("2026-10-05")},
    "周一对上、又在范围内的课程，排得出来",
)
ok(
    rng_cls not in {t["id"] for t in db.templates_on("2026-09-28")},
    "开班之前的那个周一，不排这个课",
)
ok(
    rng_cls not in {t["id"] for t in db.templates_on("2026-11-02")},
    "结课之后的那个周一，不排这个课",
)
try:
    db.create_lesson_from_template(rng_cls, "2026-11-02")
    out_of_range = False
except ValueError:
    out_of_range = True
ok(out_of_range, "超出结课日不给建课")

app.schedule_date = "2026-10-05"
app.render()
ok(
    find_text(page.controls[0], "这天的课（10月5日 周一）")
    and find_text(page.controls[0], "范围测试班"),
    "开班内的那天，「这天的课」里有这个课程",
)

print("38. 星期几可以多选，也可以选填（时间不定）")
jingsai_ct = next(c for c in db.list_class_types() if c["name"] == "竞赛")
js_level = next(l for l in db.list_levels() if db.level_full_name(l) == "GPL-竞赛-小低组")
free_cls = db.create_template(
    -1,
    "18:00",
    90,
    jingsai_ct["id"],
    js_level["id"],
    name="2026-2-GPL-竞赛-小低组-Cls-01",
    year="2026",
    term="2",
    seq=1,
    teacher_id=t_a,
    start_date="2026-09-01",
    end_date="2026-12-31",
)
ok(db.get_template(free_cls)["weekday"] == -1, "星期几可以不填")
ok(db.weekday_text(-1) == "时间不定", "不填就显示「时间不定」")
ok(
    free_cls not in {t["id"] for t in db.templates_on("2026-10-05")},
    "不定时的课不会自动排到某一天",
)
ok(db.template_dates(db.get_template(free_cls)) == [], "不定时的课算不出每周日期")
try:
    db.generate_template_lessons(free_cls)
    block_semester = False
except ValueError as err:
    block_semester = "时间不定" in str(err)
ok(block_semester, "不定时的课不能「排整学期」，会提示用「记一节课」")

multi_cls = db.create_template(
    (0, 2),
    "17:30",
    90,
    jingsai_ct["id"],
    js_level["id"],
    name="2026-2-GPL-多日班-Cls-01",
    year="2026",
    term="2",
    seq=1,
    teacher_id=t_a,
    start_date="2026-09-01",
    end_date="2026-09-14",
    weekday_times={0: "17:30", 2: "19:00"},
)
multi = db.get_template(multi_cls)
ok(
    db.template_weekdays(multi) == (0, 2)
    and db.weekday_text(multi) == "每周一、周三",
    "课程能同时保存周一和周三",
)
ok(
    db.template_day_times(multi) == {0: "17:30", 2: "19:00"}
    and db.weekday_time_text(multi) == "周一 17:30、周三 19:00",
    "同一课程不同上课日能保存不同时间",
)
ok(
    db.template_dates(multi) == ["2026-09-02", "2026-09-07", "2026-09-09", "2026-09-14"],
    "排整学期会合并两天的日期",
)
ok(
    multi_cls in {t["id"] for t in db.templates_on("2026-09-07")}
    and multi_cls in {t["id"] for t in db.templates_on("2026-09-09")},
    "多日课程在周一周三的课表里都会出现",
)
ok(
    next(t for t in db.templates_on("2026-09-07") if t["id"] == multi_cls)["start_time"]
    == "17:30"
    and next(t for t in db.templates_on("2026-09-09") if t["id"] == multi_cls)[
        "start_time"
    ]
    == "19:00",
    "课表按当天所属星期显示对应时间",
)
_mon_lesson = db.create_lesson_from_template(multi_cls, "2026-09-07")
_wed_lesson = db.create_lesson_from_template(multi_cls, "2026-09-09")
ok(
    db.get_lesson(_mon_lesson)["start_time"] == "17:30"
    and db.get_lesson(_wed_lesson)["start_time"] == "19:00",
    "自动建课次也使用当天自己的时间",
)

free_lesson = db.create_lesson(
    "2026-10-06",
    "18:00",
    90,
    jingsai_ct["id"],
    js_level["id"],
    teacher_id=t_a,
    template_id=free_cls,
)
ok(
    db.get_lesson(free_lesson)["template_id"] == free_cls,
    "不定时的课可以一次一次记，挂在课程上",
)

app.tab = 1
app.lesson_id = None
app.render()
app._open_template_dialog()
dlg = top_dialog(page)
find_checkbox(dlg, "周六").value = False
find_checkbox(dlg, "不指定").value = True
find_field(dlg, "课程名（自动生成，也可自己改）").value = "2026-2-不定时界面班"
find_dropdown(dlg, "等级 *").value = str(gpl3["id"])
click(dlg, "保存")
ui_free = [t for t in db.list_templates(active_only=False) if t["name"] == "2026-2-不定时界面班"]
ok(
    ui_free and ui_free[0]["weekday"] == -1 and ui_free[0]["weekdays"] == "",
    "界面上选「不指定」，存下来就是时间不定",
)
app.schedule_date = "2026-10-05"
app.render()
ok(find_text(page.controls[0], "时间不定"), "课程列表上写着「时间不定」")

print("39. 当天的课都算在「这天的课」里")
db.create_lesson(
    "2026-10-05", "16:00", 90, zhengke["id"], gpl3["id"], teacher_id=t_a
)
app.tab = 1
app.lesson_id = None
app.schedule_date = "2026-10-05"
app.render()
ok(find_text(page.controls[0], "这天的课（10月5日 周一）"), "有「这天的课」这一块")
ok(
    any(
        isinstance(control, ft.Container)
        and isinstance(control.content, ft.Column)
        and any(
            isinstance(child, ft.Text) and child.value == "10月5日 周一"
            for child in walk(control.content)
        )
        and any(
            isinstance(child, ft.Text)
            and child.value == "这天的课（10月5日 周一）"
            for child in walk(control.content)
        )
        for control in walk(page.controls[0])
    ),
    "日期切换和当天的课在同一张卡片里",
)
ok(not find_text(page.controls[0], "这天另外记的课"), "不再单开「这天另外记的课」")
ok(find_text(page.controls[0], "GPL-03 周一班"), "课程的那一节在「这天的课」里")
ok(find_text(page.controls[0], "16:00"), "临时加的那一节也在同一块里")
ok(find_text(page.controls[0], "临时"), "临时加的课有个「临时」小标")

print("40. 时间不定的课程，当天的课跟别的课程一样显示")
app.tab = 1
app.lesson_id = None
app.schedule_date = "2026-10-06"  # free_lesson 那天
app.render()
tree40 = page.controls[0]
ok(find_text(tree40, "这天的课（10月6日 周二）"), "这天的课那一块在")
ok(
    find_text(tree40, "2026-2-GPL-竞赛-小低组-Cls-01"),
    "不定时课程的那节课显示的是课程名",
)
ok(
    find_text(tree40, "已点名"),
    "不定时课程的那节课也走课程行（显示「已点名」），不再是灰底的临时行",
)

print("41. 记一节课默认用「你正在看的那天」")
app.tab = 1
app.lesson_id = None
app.schedule_date = "2026-09-19"
app.render()
app._open_lesson_dialog()
dlg = top_dialog(page)
ok(
    find_field(dlg, "日期").value == "2026-09-19",
    "在课程页翻到 9月19日，记一节课的日期就是 9月19日",
)
click(dlg, "今天")
ok(
    find_field(dlg, "日期").value == date.today().isoformat(),
    "点「今天」就切回今天",
)
app._close()

print("42. 某天的课不上，可以从课表上去掉")
skip_day = "2026-10-12"  # 周一，cls_a（GPL-03 周一班）本来有课
ok(cls_a in {t["id"] for t in db.templates_on(skip_day)}, "这天课表上本来有这门课")
app.tab = 1
app.lesson_id = None
app.schedule_date = skip_day
app.render()
try:
    find_button(page.controls[0], "这天不上")
    has_skip_btn = True
except AssertionError:
    has_skip_btn = False
ok(has_skip_btn, "待点名的课程旁边有「这天不上」")

# 点进点名后先生成一节待点名课次；返回课表时，“不上课”入口不能丢。
app._roll_call(cls_a)
pending_skip_id = app.lesson_id
app.open_schedule(True)
try:
    find_button(page.controls[0], "去点名")
    find_button(page.controls[0], "这天不上")
    pending_actions_visible = True
except AssertionError:
    pending_actions_visible = False
ok(pending_actions_visible, "进入点名后回到课表，「这天不上」仍然在")
app._skip_course_day(cls_a, skip_day)
dlg = top_dialog(page)
click(dlg, "确定")
ok(db.is_course_skipped(cls_a, skip_day), "标成这天不上了")
ok(
    db.get_lesson(pending_skip_id) is None,
    "标成不上课时，那天的待点名课次一起清掉了",
)
ok(
    cls_a not in {t["id"] for t in db.templates_on(skip_day)},
    "这天的课表上就没有这门课了",
)
try:
    db.create_lesson_from_template(cls_a, skip_day)
    blocked = False
except ValueError:
    blocked = True
ok(blocked, "标了不上的那天，不给点名建课")

db.unskip_course_day(cls_a, skip_day)
ok(
    cls_a in {t["id"] for t in db.templates_on(skip_day)},
    "恢复以后这天的课又回来了",
)

# 已经正式点过名，也允许在明确退回课时／积分后取消这一天的课。
rolled_skip_day = "2026-10-13"
rolled_skip_cls = db.create_template(
    1,
    "11:00",
    60,
    zhengke["id"],
    gpl3["id"],
    name="取消已点名课程-测试",
    teacher_id=t_a,
    start_date="2026-09-01",
    end_date="2026-10-31",
)
rolled_skip_id = db.create_lesson_from_template(rolled_skip_cls, rolled_skip_day)
db.roll_call(rolled_skip_id)
app.tab = 1
app.lesson_id = None
app.schedule_date = rolled_skip_day
app.render()
try:
    find_button(page.controls[0], "这天不上")
    rolled_skip_visible = find_text(page.controls[0], "已点名")
except AssertionError:
    rolled_skip_visible = False
ok(rolled_skip_visible, "已点名的课程也保留「这天不上」入口")
try:
    db.skip_course_day(rolled_skip_cls, rolled_skip_day)
    direct_rolled_skip = False
except ValueError:
    direct_rolled_skip = True
ok(direct_rolled_skip, "数据层不会悄悄取消已点名的课")
app._skip_course_day(rolled_skip_cls, rolled_skip_day)
dlg = top_dialog(page)
click(dlg, "确定")
ok(
    db.get_lesson(rolled_skip_id) is None
    and db.is_course_skipped(rolled_skip_cls, rolled_skip_day),
    "确认后可取消已点名课次并标成不上课",
)
db.delete_template(rolled_skip_cls)

db.skip_course_day(rng_cls, "2026-10-05")
result42 = db.generate_template_lessons(rng_cls)
ok("2026-10-05" not in result42["made"], "排整学期会跳过标了「不上」的那天")
for lesson in db.template_lessons(rng_cls):
    db.delete_lesson(lesson["id"])
db.unskip_course_day(rng_cls, "2026-10-05")

print("43. 周课表按时间排序，课程列表按月／状态／老师／科目筛选")
sort_day = "2026-10-19"
sort_early = db.create_template(
    0,
    "09:00",
    60,
    zhengke["id"],
    gpl3["id"],
    name="时间排序-早课",
    teacher_id=t_a,
    start_date="2026-10-01",
    end_date="2026-10-31",
)
sort_late = db.create_template(
    0,
    "10:00",
    60,
    zhengke["id"],
    gpl3["id"],
    name="时间排序-晚课",
    teacher_id=t_a,
    start_date="2026-10-01",
    end_date="2026-10-31",
)
sort_late_lesson = db.create_lesson_from_template(sort_late, sort_day)
app.tab = 1
app.lesson_id = None
app.schedule_date = sort_day
app.render()
visible_texts = [
    str(c.value or "") for c in walk(page.controls[0]) if isinstance(c, ft.Text)
]
early_pos = next(
    i for i, value in enumerate(visible_texts) if "时间排序-早课" in value
)
late_pos = next(
    i for i, value in enumerate(visible_texts) if "时间排序-晚课" in value
)
ok(early_pos < late_pos, "同一天的待点名课程和已生成课次按开始时间排列")

filter_own = db.create_template(
    0,
    "13:00",
    60,
    zhengke["id"],
    gpl3["id"],
    name="筛选-王老师-在读",
    teacher_id=t_a,
    start_date="2026-10-01",
    end_date="2026-10-31",
)
filter_ended = db.create_template(
    0,
    "14:00",
    60,
    zhengke["id"],
    gpl3["id"],
    name="筛选-王老师-已结课",
    teacher_id=t_a,
    start_date="2026-09-01",
    end_date="2026-10-05",
)
filter_other = db.create_template(
    0,
    "15:00",
    60,
    zhengke["id"],
    mcu_level["id"],
    name="筛选-李老师-MCU",
    teacher_id=t_b,
    start_date="2026-10-01",
    end_date="2026-10-31",
)
filter_comp_level = next(
    level
    for level in db.list_levels()
    if db.level_full_name(level) == "GPL-竞赛-小低组"
)
filter_comp = db.create_template(
    0,
    "16:00",
    60,
    rules["竞赛"]["id"],
    filter_comp_level["id"],
    name="筛选-王老师-竞赛",
    teacher_id=t_a,
    start_date="2026-10-01",
    end_date="2026-10-31",
)
ok(
    app.course_month == date.today().strftime("%Y-%m")
    and app.course_status_filter == "unclosed",
    "课程筛选默认显示本月且隐藏已结课",
)
ok(
    db.course_in_month(db.get_template(filter_own), "2026-10")
    and not db.course_in_month(db.get_template(filter_own), "2026-11"),
    "月份按课程实际排课区间判断",
)
app.course_month = "2026-10"
app.course_status_filter = "unclosed"
app.course_teacher_filter = str(t_a)
app.course_subject_filter = ""
app.render()
ok(
    any(
        isinstance(control, ft.Container)
        and isinstance(control.content, ft.Column)
        and find_text(control.content, "课程筛选")
        and find_text(control.content, "课程（")
        for control in walk(page.controls[0])
    ),
    "课程筛选和课程列表放在同一张卡片里",
)
def course_list_text() -> str:
    controls = list(walk(page.controls[0]))
    title_index = next(
        i
        for i, control in enumerate(controls)
        if isinstance(control, ft.Text)
        and str(control.value or "").startswith("课程（")
    )
    return "\n".join(
        str(control.value or "")
        for control in controls[title_index:]
        if isinstance(control, ft.Text)
    )


ok("筛选-王老师-在读" in course_list_text(), "老师自己的在读课程仍然显示")
ok(
    "筛选-王老师-已结课" not in course_list_text(),
    "已结课课程默认隐藏",
)
ok(
    "筛选-李老师-MCU" not in course_list_text(),
    "其他老师的课程不在当前老师筛选里",
)
ok(
    find_dropdown(page.controls[0], "课程状态").value == "unclosed"
    and find_dropdown(page.controls[0], "上课老师").value == str(t_a)
    and find_dropdown(page.controls[0], "类别").value == ""
    and find_dropdown(page.controls[0], "科目").value == "",
    "筛选控件显示默认条件",
)
app.course_teacher_filter = "all"
app.render()
ok(
    "筛选-王老师-在读" in course_list_text()
    and "筛选-李老师-MCU" in course_list_text()
    and "筛选-王老师-已结课" not in course_list_text(),
    "切到全部老师后，只隐藏已结课",
)
app.course_status_filter = "已结课"
app.render()
ok(
    "筛选-王老师-已结课" in course_list_text()
    and "筛选-王老师-在读" not in course_list_text(),
    "选择已结课后只看已结课课程",
)
app.course_status_filter = "all"
app.course_category_filter = "竞赛"
app.render()
ok(
    "筛选-王老师-竞赛" in course_list_text()
    and "筛选-王老师-在读" not in course_list_text(),
    "类别筛选只保留对应类别的课程",
)
app.course_category_filter = ""
app.course_subject_filter = "MCU"
app.render()
ok(
    "筛选-李老师-MCU" in course_list_text()
    and "筛选-王老师-在读" not in course_list_text(),
    "科目筛选只保留对应科目",
)
app.course_month = "2026-09"
app.course_subject_filter = ""
app.render()
ok(
    "筛选-王老师-已结课" in course_list_text()
    and "筛选-王老师-在读" not in course_list_text(),
    "切到上个月后只显示当月有排课的课程",
)
for lesson in db.template_lessons(sort_late):
    db.delete_lesson(lesson["id"])
for template_id in (
    sort_early,
    sort_late,
    filter_own,
    filter_ended,
    filter_other,
    filter_comp,
):
    db.delete_template(template_id)
app._reset_course_filters()

print("44. 学员按姓名／电话／年级／学校／归属老师筛选")
f1 = db.create_student(
    {
        "name": "筛选甲",
        "phone": "13900001111",
        "grade": "三年级",
        "school": "筛选小学甲",
        "status": "在读",
    }
)
f2 = db.create_student(
    {
        "name": "筛选乙",
        "phone": "13800002222",
        "grade": "四年级",
        "school": "筛选小学乙",
        "status": "在读",
    }
)
db.update_student(
    f1,
    {
        "name": "筛选甲",
        "phone": "13900001111",
        "grade": "三年级",
        "school": "筛选小学甲",
        "status": "在读",
        "owner_teacher_id": t_a,
        "owner_manual": True,
    },
)
db.update_student(
    f2,
    {
        "name": "筛选乙",
        "phone": "13800002222",
        "grade": "四年级",
        "school": "筛选小学乙",
        "status": "在读",
        "owner_teacher_id": t_b,
        "owner_manual": True,
    },
)

names = [s["name"] for s in db.list_students(keyword="筛选甲")]
ok(names == ["筛选甲"], "按姓名筛")
names = [s["name"] for s in db.list_students(keyword="2222")]
ok("筛选乙" in names and "筛选甲" not in names, "按电话筛")
names = [s["name"] for s in db.list_students(grade="三年级")]
ok("筛选甲" in names and "筛选乙" not in names, "按年级筛")
names = [s["name"] for s in db.list_students(school="筛选小学甲")]
ok(names == ["筛选甲"], "按学校筛")
names = [s["name"] for s in db.list_students(owner=str(t_a))]
ok("筛选甲" in names and "筛选乙" not in names, "按归属老师筛")
names = [s["name"] for s in db.list_students(owner="__none__")]
ok("筛选甲" not in names and "筛选乙" not in names, "「未指定归属」只列还没定归属的")
names = [s["name"] for s in db.list_students(keyword="筛选", grade="三年级")]
ok(names == ["筛选甲"], "多个条件一起筛")

app.tab = 0
app.student_id = None
app.render()
tree = page.controls[0]
ok(find_dropdown(tree, "年级") is not None, "学员列表上有「年级」筛选")
ok(find_dropdown(tree, "归属老师") is not None, "学员列表上有「归属老师」筛选")
ok(find_search(tree) is not None, "学员列表上有搜索框（姓名/电话/年级/学校都能敲）")
box44 = find_search(tree)
box44.value = "筛选甲"
box44.on_submit(Evt(box44))
ok(
    find_text(page.controls[0], "筛选甲")
    and not find_text(page.controls[0], "筛选乙"),
    "搜索框里敲姓名，只剩他一个",
)
click(page.controls[0], "清空筛选")
ok(
    find_text(page.controls[0], "筛选甲") and find_text(page.controls[0], "筛选乙"),
    "清空筛选以后都回来了",
)

print("45. 「顺延一周」已经去掉")
post_cls = db.create_template(
    0,
    "08:00",
    90,
    zhengke["id"],
    gpl3["id"],
    name="2026-2-排课测试班",
    year="2026",
    term="2",
    seq=98,
    teacher_id=t_a,
    start_date="2026-10-05",
    end_date="2026-10-31",
)
db.set_template_students(post_cls, [one_kid])
db.generate_template_lessons(post_cls)
ok(len(db.template_lessons(post_cls)) == 4, "先排出 4 节待点名的课")

app.tab = 1
app.lesson_id = None
app.schedule_date = "2026-10-05"
app.render()

def _has_button(root, label: str) -> bool:
    return any(
        isinstance(c, (ft.Button, ft.TextButton)) and c.content == label
        for c in walk(root)
    )


ok(not _has_button(page.controls[0], "顺延一周"), "页面上没有「顺延一周」了")
ok(not hasattr(db, "postpone_template"), "后台也没有顺延功能了")
for lesson in db.template_lessons(post_cls):
    db.delete_lesson(lesson["id"])
db.delete_template(post_cls)

print("46. 删等级：在用的会先说清影响，确认后连记录上的等级一起清掉")
used_level = gpl3
ok(sum(db.level_usage(used_level["id"]).values()) > 0, "这个等级确实在用")
try:
    db.delete_level(used_level["id"])  # 不确认（force=False）先拦住
    level_blocked = False
except ValueError as err:
    level_blocked = "还有记录在用它" in str(err)
ok(level_blocked, "没确认时先拦住，并说清在用")
ok(
    any(l["id"] == used_level["id"] for l in db.list_levels()),
    "拦住以后等级还在",
)
ok(
    "个学员报名" in db.level_usage_text(used_level["id"])
    or "门课程" in db.level_usage_text(used_level["id"]),
    "能说清是哪些记录在用",
)

# 确认删除：等级没了，用它的记录还在，只是等级被清空
course_using = db.list_templates(active_only=False)
course_using = next(t for t in course_using if t["level_id"] == used_level["id"])
db.delete_level(used_level["id"], force=True)
ok(
    not any(l["id"] == used_level["id"] for l in db.list_levels()),
    "确认以后等级真的删掉了",
)
ok(
    db.get_template(course_using["id"])["level_id"] is None,
    "用它的课程还在，只是等级清空了",
)

free_level = db.create_level("自检", "可删等级", 60)
db.delete_level(free_level)
ok(
    not any(l["id"] == free_level for l in db.list_levels()),
    "没人用的等级能正常删掉",
)

app.tab = 7
app.render()
tree46 = page.controls[0]
ok(find_text(tree46, "在用（删了会清空这些记录上的等级）"), "设置里写明删了会影响什么")
ok(find_text(tree46, "还没人用"), "没人用的等级写着还没人用")

print("47. 删掉的默认等级，重启不会再长回来")
default_lv = next(
    (l for l in db.list_levels() if db.level_full_name(l) == "PY-Lvl-01"), None
)
ok(default_lv is not None, "默认等级 PY-Lvl-01 在")
db.delete_level(default_lv["id"], force=True)
ok(
    not any(db.level_full_name(l) == "PY-Lvl-01" for l in db.list_levels()),
    "删掉了",
)
db.init_db()  # 模拟重启
db.init_db()
ok(
    not any(db.level_full_name(l) == "PY-Lvl-01" for l in db.list_levels()),
    "重启两次也不会把删掉的默认等级补回来",
)
ok(bool(db.list_levels()), "别的等级还在")

print("48. 每年 9 月自动升年级")
grade_kids = {
    "一年级": db.create_student({"name": "自动升级一", "grade": "一年级"}),
    "五年级": db.create_student({"name": "自动升级五", "grade": "五年级"}),
    "六年级": db.create_student({"name": "自动升级六", "grade": "六年级"}),
    "初三": db.create_student({"name": "自动升级初三", "grade": "初三"}),
}
db.advance_student_grades("2027-09-01")
ok(db.get_student(grade_kids["一年级"])["grade"] == "二年级", "一年级升二年级")
ok(db.get_student(grade_kids["五年级"])["grade"] == "六年级", "五年级升六年级")
ok(db.get_student(grade_kids["六年级"])["grade"] == "初一", "六年级升初一")
ok(db.get_student(grade_kids["初三"])["grade"] == "初三", "初三毕业后保持初三")
ok(db.advance_student_grades("2027-09-01") == 0, "同一学年不会重复升级")
db.advance_student_grades("2028-09-01")
ok(db.get_student(grade_kids["六年级"])["grade"] == "初二", "初一升初二")

auto_birth = db.create_student(
    {
        "name": "生日自动年级",
        "grade": "一年级",
        "birth_date": "2020-05-18",
    }
)
ok(db.grade_from_birth_date("2020-05-18", "2026-09-01") == "一年级", "按生日推算当前年级")
db.advance_student_grades("2027-09-01")
ok(db.get_student(auto_birth)["grade"] == "二年级", "生日绑定的年级随后一学年升级")

manual_grade = db.create_student({"name": "手动改年级", "grade": "四年级"})
db.update_student(
    manual_grade,
    {
        "name": "手动改年级",
        "grade": "三年级",
        "gender": "",
        "school": "",
        "phone": "",
        "guardian": "",
        "note": "",
        "status": "在读",
    },
)
db.advance_student_grades("2027-09-01")
ok(
    db.get_student(manual_grade)["grade"] == "四年级",
    "手动改年级后，从新年级重新按学年升",
)
for kid in [*grade_kids.values(), auto_birth, manual_grade]:
    db.delete_student(kid)

print("49. 学生账号、学生门户和论坛悬赏")
portal_teacher = db.create_user(
    "portal_teacher", "pw123456", "门户老师", db.ROLE_TEACHER
)
portal_student = db.create_student(
    {
        "name": "学生门户娃",
        "grade": "四年级",
        "school": "门户小学",
        "owner_teacher_id": portal_teacher,
        "owner_manual": True,
    }
)
portal_level = next(l for l in db.list_levels(active_only=True))
portal_enrollment = db.create_enrollment(
    portal_student,
    portal_level["id"],
    zhengke["id"],
    90,
    owner_teacher_id=portal_teacher,
)
portal_lesson = db.create_lesson(
    "2026-10-20",
    "16:00",
    90,
    zhengke["id"],
    portal_level["id"],
    "这节课学习循环嵌套",
)
db.set_lesson_plan(portal_lesson, "先复习循环，再完成嵌套练习")
db.add_attendance(portal_lesson, portal_student)
upcoming_day = (date.today() + timedelta(days=2)).isoformat()
portal_upcoming_lesson = db.create_lesson(
    upcoming_day,
    "16:00",
    90,
    zhengke["id"],
    portal_level["id"],
    teacher_id=portal_teacher,
    rolled=0,
)
db.add_attendance(portal_upcoming_lesson, portal_student)

future_history_student = db.create_student(
    {
        "name": "未来课程过滤测试",
        "grade": "四年级",
        "owner_teacher_id": portal_teacher,
        "owner_manual": True,
    }
)
past_history_lesson = db.create_lesson(
    (date.today() - timedelta(days=1)).isoformat(),
    "17:00",
    90,
    zhengke["id"],
    portal_level["id"],
    "已经上过的课",
    teacher_id=portal_teacher,
)
future_history_lesson = db.create_lesson(
    (date.today() + timedelta(days=90)).isoformat(),
    "17:00",
    90,
    zhengke["id"],
    portal_level["id"],
    "未来已经点名的课",
    teacher_id=portal_teacher,
)
for history_lesson in (past_history_lesson, future_history_lesson):
    db.add_attendance(history_lesson, future_history_student)
ok(
    [row["lesson_id"] for row in db.student_recent_lessons(future_history_student, 10)]
    == [past_history_lesson],
    "最近上课记录不包含未来课程",
)
ok(
    [row["lesson_id"] for row in db.student_course_lessons(future_history_student)]
    == [past_history_lesson],
    "学生课程历史不包含未来课程",
)
db.delete_lesson(past_history_lesson)
db.delete_lesson(future_history_lesson)
db.delete_student(future_history_student)

app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
app.tab = 0
app.open_student(portal_student)
ok(find_text(page.controls[0], "学生账号"), "管理员能在学员页管理学生账号")
app._open_student_account_dialog(db.get_student(portal_student))
dlg = top_dialog(page)
find_field(dlg, "登录用户名 *").value = "student_portal"
find_field(dlg, "初始密码 *").value = "kid12345"
click(dlg, "保存")
student_user = db.get_student_user(portal_student)
ok(
    student_user is not None
    and student_user["role"] == db.ROLE_STUDENT
    and student_user["student_id"] == portal_student,
    "学生账号与学员档案一对一绑定",
)
student_nickname = student_user["forum_nickname"]
ok(
    student_nickname and student_nickname != "学生门户娃",
    "学生账号自动获得不暴露姓名的论坛昵称",
)

student_login = db.verify_user("student_portal", "kid12345")
ok(student_login is not None, "学生账号能正常登录")
app.user = {
    "id": student_login["id"],
    "username": student_login["username"],
    "display_name": student_login["display_name"],
    "role": student_login["role"],
    "student_id": student_login["student_id"],
}
menus = [label for _icon, _selected, label in app._nav_items()]
ok(
    menus == ["我的", "课程", "论坛", "工具"],
    "学生登录后只有我的、课程、论坛和工具",
)
app.tab = 3
app.render()
ok(find_text(page.controls[0], "3D 打印积分"), "学生也能使用工具栏")
app.tab = 0
app.render()
ok(find_text(page.controls[0], "学生门户娃"), "学生能看到自己的信息")
ok(find_text(page.controls[0], "当前积分"), "学生能看到自己的积分")
ok(
    find_text(page.controls[0], "积分流水")
    and find_text(page.controls[0], "上课"),
    "学生能在我的页面查询积分获得流水",
)
ok(
    find_text(page.controls[0], "未来 7 天要上的课（1）"),
    "学生首页提醒未来一周要上的课",
)
ok(
    not find_text(page.controls[0], "缴费记录")
    and not find_text(page.controls[0], "课时账户")
    and not find_text(page.controls[0], "代金券"),
    "学生页面不展示课时余额、缴费或代金券",
)
app.tab = 1
app.render()
ok(
    not find_text(page.controls[0], "未来 7 天要上的课"),
    "未来一周提醒只放在我的首页，不在课程页重复",
)
ok(
    not find_text(page.controls[0], "这节课学习循环嵌套")
    and find_button(page.controls[0], "查看课评 / 教案") is not None,
    "我的课程默认只显示简单信息，课评收进详情",
)
click(page.controls[0], "查看课评 / 教案")
dlg = top_dialog(page)
ok(find_text(dlg, "这节课学习循环嵌套"), "学生能在详情里查看课评")
ok(find_text(dlg, "先复习循环，再完成嵌套练习"), "学生能在详情里查看教案")
app._close()
ok(not find_text(page.controls[0], "缴费"), "学生课程页不展示费用")

app.tab = 2
app.render()
try:
    db.create_forum_bounty(student_login["id"], "负数", "测试", -1)
    negative_bounty_allowed = True
except ValueError:
    negative_bounty_allowed = False
ok(not negative_bounty_allowed, "悬赏积分不能小于 0")
try:
    db.create_forum_bounty(student_login["id"], "超额", "测试", 31)
    over_balance_allowed = True
except ValueError:
    over_balance_allowed = False
ok(not over_balance_allowed, "悬赏积分不能超过自己的积分")

app._open_forum_post_dialog()
dlg = top_dialog(page)
find_field(dlg, "悬赏标题 *").value = "循环题不会做"
find_field(dlg, "问题内容 *").value = "嵌套循环的第二步看不懂。"
find_field(dlg, "悬赏积分 *").value = "12"
_forum_order = list(walk(dlg))
ok(
    _forum_order.index(find_field(dlg, "问题内容 *"))
    < _forum_order.index(find_button(dlg, "添加内容图片"))
    < _forum_order.index(find_field(dlg, "悬赏积分 *")),
    "内容图片入口紧跟在问题内容下面",
)
ok(
    app._files_callback is not None,
    "发布框打开时图片回调已经准备好",
)
app._on_files_picked(FakeEvent([]))
ok(
    app._files_callback is not None,
    "取消系统文件选择后仍可重新添加图片",
)
find_button(dlg, "添加内容图片").on_click(None)
ok(
    app._files_callback is not None,
    "打开论坛发布框时已准备好接图片，不依赖点击后的数据库往返",
)
app._files_callback(
    [
        FakeFile("题目截图.png", _qr_buf.getvalue()),
        FakeFile("多余图片.png", _qr_buf.getvalue()),
    ]
)
forum_previews = [
    c
    for c in walk(dlg)
    if isinstance(c, ft.Image)
    and str(c.src or "").startswith("data:image/")
]
ok(
    len(forum_previews) == 1
    and forum_previews[0].fit == ft.BoxFit.CONTAIN
    and find_key(dlg, "forum-selected-image-holder").visible,
    "论坛选图后显示缩略图，并只保留一张",
)
preview_surface = find_key(dlg, "forum-selected-image-preview")
remove_image_button = find_key(dlg, "forum-selected-image-delete")
ok(
    preview_surface.on_click is not None
    and isinstance(remove_image_button, ft.IconButton)
    and remove_image_button.tooltip == "删除图片",
    "缩略图本身可以点开，右上角有删除图标，没有多余文字按钮",
)
preview_surface.on_click(None)
full_preview = top_dialog(page)
full_preview_image = next(
    c
    for c in walk(full_preview)
    if isinstance(c, ft.Image) and str(c.src or "").startswith("data:image/")
)
ok(
    find_text(full_preview, "查看图片")
    and full_preview_image.fit == ft.BoxFit.CONTAIN
    and full_preview_image.height is not None,
    "发布前可以查看选中图片的全貌",
)
app._close()
remove_image_button.on_click(None)
ok(
    not find_key(dlg, "forum-selected-image-holder").visible
    and find_text(dlg, "未选择图片（只能上传 1 张）"),
    "发布前可以删除已选图片",
)
app._files_callback(
    [FakeFile("题目截图.png", _qr_buf.getvalue())]
)
ok(
    find_key(dlg, "forum-selected-image-holder").visible,
    "删除图片后可以重新选择并继续发布",
)
click(dlg, "发布")
ok(app._files_callback is None, "发布完成后清理临时图片回调")
bounties = db.list_forum_bounties()
ok(
    len(bounties) == 1
    and bounties[0]["status"] == "待解决"
    and bounties[0]["target_user_id"] is None,
    "学生能发布公开悬赏",
)
forum_images = db.list_files("forum_bounty", bounties[0]["id"], "图片")
ok(
    len(forum_images) == 1
    and (db.UPLOAD_DIR / forum_images[0]["stored_name"]).is_file(),
    "悬赏只能附带上传 1 张图片",
)
ok(
    db.student_points(portal_student) == 18,
    "发布悬赏后立即冻结 12 积分",
)
app.tab = 2
app.render()
ok(find_text(page.controls[0], "循环题不会做"), "论坛里能看到公开发布的悬赏")
ok(find_text(page.controls[0], "12 积分"), "悬赏积分用醒目徽章单独显示")
ok(
    any(
        isinstance(c, ft.Image)
        and c.visible
        and str(c.src or "") == db.file_url(forum_images[0])
        for c in walk(page.controls[0])
    ),
    "论坛帖子中显示上传图片的缩略图",
)
ok(
    find_text(page.controls[0], student_nickname)
    and not find_text(page.controls[0], "学生门户娃"),
    "学生端只看到发布者昵称，看不到真名",
)
teacher_nickname = db.get_user(portal_teacher)["forum_nickname"]
app._open_forum_post_dialog()
dlg = top_dialog(page)
student_targets = find_dropdown(dlg, "指定交易对象（可选）")
ok(
    student_targets.editable
    and any(teacher_nickname in o.text for o in student_targets.options)
    and not any(
        "门户老师" in o.text or "老师" in o.text or "学生" in o.text
        for o in student_targets.options
        if o.key
    ),
    "学生选择交易对象时只看到昵称，不显示身份",
)
app._close()

app.user = {
    "id": portal_teacher,
    "username": "portal_teacher",
    "display_name": "门户老师",
    "role": db.ROLE_TEACHER,
}
app.tab = 4
app.render()
ok(
    find_text(page.controls[0], "学生门户娃")
    and find_text(page.controls[0], student_nickname),
    "老师端能看到学生真名和昵称",
)
app._open_forum_answer_dialog(bounties[0])
dlg = top_dialog(page)
find_field(dlg, "我的回答 *").value = "先看外层，再看内层。"
click(dlg, "发布回答")
answers = db.list_forum_answers(bounties[0]["id"])
ok(len(answers) == 1, "老师能回答学生的悬赏")

app.user = {
    "id": student_login["id"],
    "username": student_login["username"],
    "display_name": student_login["display_name"],
    "role": student_login["role"],
    "student_id": student_login["student_id"],
}
app.tab = 2
app.render()
accept_button = find_button(page.controls[0], "采纳这个答案")
accept_button.on_click(None)
dlg = top_dialog(page)
click(dlg, "采纳")
ok(
    db.list_forum_bounties()[0]["status"] == "已完成"
    and db.forum_points_balance(portal_teacher) == 12,
    "学生采纳后，悬赏积分转给老师",
)

app.user = {
    "id": portal_teacher,
    "username": "portal_teacher",
    "display_name": "门户老师",
    "role": db.ROLE_TEACHER,
}
app.tab = 4
app.render()
app._open_forum_post_dialog()
dlg = top_dialog(page)
find_field(dlg, "悬赏标题 *").value = "请教循环顺序"
find_field(dlg, "问题内容 *").value = "想确认循环执行顺序。"
find_field(dlg, "悬赏积分 *").value = "5"
target_dd = find_dropdown(dlg, "指定交易对象（可选）")
ok(
    target_dd.enable_search
    and target_dd.enable_filter
    and target_dd.editable
    and "1" not in {str(o.key) for o in target_dd.options},
    "指定对象可搜索且不包含管理员",
)
ok(
    any(
        student_nickname in o.text and "学生门户娃" in o.text
        for o in target_dd.options
    ),
    "老师指定交易对象时显示学生真名和昵称",
)
target_dd.value = str(student_login["id"])
click(dlg, "发布")
targeted = next(b for b in db.list_forum_bounties() if b["title"] == "请教循环顺序")
ok(
    targeted["target_user_id"] == student_login["id"]
    and db.forum_points_balance(portal_teacher) == 7,
    "老师能用自己的论坛积分发布指定悬赏",
)

try:
    db.add_forum_answer(targeted["id"], 1, "管理员不能抢答")
    outsider_allowed = True
except ValueError:
    outsider_allowed = False
ok(not outsider_allowed, "指定悬赏不允许其他人回答")

app.user = {
    "id": student_login["id"],
    "username": student_login["username"],
    "display_name": student_login["display_name"],
    "role": student_login["role"],
    "student_id": student_login["student_id"],
}
app.tab = 2
app.render()
ok(
    find_text(page.controls[0], f"指定给 {student_nickname}"),
    "学生端只看到指定对象的昵称",
)
app._open_forum_answer_dialog(targeted)
dlg = top_dialog(page)
find_field(dlg, "我的回答 *").value = "按从上到下、从内到外执行。"
click(dlg, "发布回答")
targeted_answers = db.list_forum_answers(targeted["id"])
ok(len(targeted_answers) == 1, "被指定的学生可以回答老师悬赏")

app.user = {
    "id": portal_teacher,
    "username": "portal_teacher",
    "display_name": "门户老师",
    "role": db.ROLE_TEACHER,
}
app.tab = 4
app.render()
app._confirm(
    "采纳答案",
    "测试采纳",
    lambda: db.accept_forum_answer(
        targeted["id"], targeted_answers[0]["id"], portal_teacher
    ),
    ok_text="采纳",
)
click(top_dialog(page), "采纳")
ok(
    db.student_points(portal_student) == 23
    and db.forum_points_balance(portal_teacher) == 7,
    "老师采纳后，悬赏积分转给学生",
)
app.tab = 4
app.render()
click(page.controls[0], "积分流水")
history_dlg = top_dialog(page)
ok(
    find_text(history_dlg, "悬赏收入")
    and find_text(history_dlg, "悬赏支出"),
    "老师能在论坛查看自己的积分流水",
)
app._close()

try:
    db.deduct_forum_bounty_points(
        bounties[0]["id"], portal_teacher, 1, "老师没有扣分权限"
    )
    teacher_can_deduct = True
except ValueError:
    teacher_can_deduct = False
ok(not teacher_can_deduct, "普通老师不能手动扣除论坛积分")

app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
app.tab = 4
app.render()
ok(
    find_button(page.controls[0], "管理员扣分") is not None,
    "管理员能看到论坛扣分入口",
)
public_bounty = next(
    row for row in db.list_forum_bounties() if row["title"] == "循环题不会做"
)
app._open_forum_penalty_dialog(public_bounty)
dlg = top_dialog(page)
find_field(dlg, "扣除积分 *").value = "3"
find_field(dlg, "扣分原因 *").value = "发布内容包含不当言论"
click(dlg, "确认扣分")
penalized = next(
    row for row in db.list_forum_bounties()
    if row["title"] == "循环题不会做"
)
ok(
    db.student_points(portal_student) == 20
    and penalized["penalty_points"] == 3
    and penalized["moderation_note"] == "发布内容包含不当言论",
    "管理员扣分后学生积分和悬赏记录同步更新",
)
db.add_redemption(
    portal_student,
    5,
    date.today().isoformat(),
    "兑换小奖品",
)
previous_month_day = (
    date.today().replace(day=1) - timedelta(days=1)
).isoformat()
db.add_redemption(
    portal_student,
    2,
    previous_month_day,
    "上月兑换",
)
app.user = {
    "id": student_login["id"],
    "username": student_login["username"],
    "display_name": student_login["display_name"],
    "role": student_login["role"],
    "student_id": student_login["student_id"],
}
app.tab = 0
app.render()
ok(
    find_text(page.controls[0], "兑换")
    and find_text(page.controls[0], "兑换小奖品")
    and not find_text(page.controls[0], "上月兑换"),
    "学生首页积分流水只显示本月兑换记录",
)
click(page.controls[0], "查看全部")
history_dialog = top_dialog(page)
ok(
    find_text(history_dialog, "上课")
    and find_text(history_dialog, "兑换小奖品")
    and find_button(history_dialog, "下月 →").disabled,
    "完整积分流水默认显示本月，并停在最新月份",
)
click(history_dialog, "← 上月")
ok(
    find_text(history_dialog, "上月兑换")
    and not find_text(history_dialog, "兑换小奖品"),
    "积分流水可以像银行账单一样切换到上月",
)
click(history_dialog, "本月")
ok(find_text(history_dialog, "兑换小奖品"), "积分流水可以切回本月")
app._close()
app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
try:
    db.mute_forum_user(
        portal_student, portal_teacher, "2099-12-31 23:59", "老师不能禁言"
    )
    teacher_can_mute = True
except ValueError:
    teacher_can_mute = False
ok(not teacher_can_mute, "普通老师不能执行论坛禁言")

app._open_forum_mute_dialog(public_bounty)
dlg = top_dialog(page)
find_field(dlg, "禁言至 *").value = "2099-12-31 23:59"
find_field(dlg, "禁言原因 *").value = "多次发布不友善言论"
click(dlg, "确认禁言")
mute_state = db.forum_mute_state(student_login["id"])
ok(
    mute_state["active"] and mute_state["reason"] == "多次发布不友善言论",
    "管理员可以指定截止时间禁言并记录原因",
)

app.user = {
    "id": student_login["id"],
    "username": student_login["username"],
    "display_name": student_login["display_name"],
    "role": student_login["role"],
    "student_id": student_login["student_id"],
}
app.tab = 2
app.render()
ok(find_text(page.controls[0], "你已被禁言至"), "被禁言学生能看到禁言提示")
ok(find_button(page.controls[0], "发布悬赏").disabled, "禁言期间发布按钮不可用")
open_bounty = db.create_forum_bounty(
    portal_teacher, "禁言测试", "这个问题需要回答", 0
)
try:
    db.add_forum_answer(open_bounty, student_login["id"], "尝试回答")
    muted_can_answer = True
except ValueError:
    muted_can_answer = False
ok(not muted_can_answer, "禁言期间不能回答悬赏")

app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
app.tab = 4
app.render()
click(page.controls[0], "解除禁言")
ok(not db.forum_mute_state(student_login["id"])["active"], "管理员可以提前解除禁言")

app.user = {
    "id": student_login["id"],
    "username": student_login["username"],
    "display_name": student_login["display_name"],
    "role": student_login["role"],
    "student_id": student_login["student_id"],
}
app.tab = 2
app.render()
click(page.controls[0], "修改昵称")
dlg = top_dialog(page)
find_field(dlg, "论坛昵称").value = "快乐小侦探"
click(dlg, "保存")
ok(
    db.get_user(student_login["id"])["forum_nickname"] == "快乐小侦探",
    "学生可以修改自己的论坛昵称",
)
for invalid_nickname, why in (
    ("学生门户娃", "真实姓名"),
    ("student_portal", "登录账号"),
    ("垃圾用户", "不文明用语"),
    ("13800000000", "联系方式"),
    (teacher_nickname, "重复昵称"),
):
    try:
        db.update_forum_nickname(
            student_login["id"], invalid_nickname, student_login["id"]
        )
        rejected = False
    except ValueError:
        rejected = True
    ok(rejected, f"昵称不能包含{why}")

app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
app.tab = 0
app.open_student(portal_student)
click(page.controls[0], "修改昵称")
dlg = top_dialog(page)
find_field(dlg, "论坛昵称").value = "老师设置的新昵称"
click(dlg, "保存")
ok(
    db.get_user(student_login["id"])["forum_nickname"] == "老师设置的新昵称",
    "管理员可以从学员档案修改学生昵称",
)

app._open_level_dialog(None)
dlg = top_dialog(page)
find_field(dlg, "科目（如 GPL、STEM）").value = "徽章测试"
find_field(dlg, "等级／阶段（如 Lvl-01）").value = "三级考级"
find_field(dlg, "默认时长（分钟）").value = "60"
ok(
    find_dropdown(dlg, "类别").value == "正课"
    and not find_dropdown(dlg, "考级级别").visible,
    "新等级默认类型是正课，不自动关联徽章",
)
level_dialog_order = list(walk(dlg))
ok(
    level_dialog_order.index(find_field(dlg, "科目（如 GPL、STEM）"))
    < level_dialog_order.index(find_dropdown(dlg, "类别"))
    < level_dialog_order.index(find_field(dlg, "等级／阶段（如 Lvl-01）")),
    "类别紧跟在科目下面",
)
level_category = find_dropdown(dlg, "类别")
level_category.value = "考级"
level_category.on_select(Evt(level_category))
find_dropdown(dlg, "考级级别").value = "3级"
click(dlg, "保存")
configured_badge_level = next(
    level
    for level in db.list_levels()
    if db.level_full_name(level) == "徽章测试-三级考级"
)
ok(
    configured_badge_level["badge_category"] == "考级"
    and configured_badge_level["badge_exam_level"] == "3级"
    and configured_badge_level["level_type"] == "考级"
    and db.level_display_name(configured_badge_level)
    == "徽章测试-三级考级-考级",
    "等级设置里可以配置考级徽章和 1～4 级，显示名称带类别",
)

app._open_badge_dialog(student_id=portal_student)
dlg = top_dialog(page)
find_field(dlg, "比赛／考级名称 *").value = "机器人创意赛"
find_field(dlg, "竞赛组别").value = "小低组"
find_field(dlg, "日期").value = "2026-08-15"
click(dlg, "保存")
app._open_badge_dialog(student_id=portal_student)
dlg = top_dialog(page)
exam_category = find_dropdown(dlg, "徽章类别")
exam_category.value = "考级"
exam_category.on_select(Evt(exam_category))
find_field(dlg, "比赛／考级名称 *").value = "机器人技术等级考试"
linked_level = find_dropdown(dlg, "关联等级（可选）")
linked_level.value = str(configured_badge_level["id"])
linked_level.on_select(Evt(linked_level))
ok(
    find_dropdown(dlg, "考级级别").value == "3级",
    "选择关联考级等级后自动带出 3级",
)
find_dropdown(dlg, "结果").value = "优秀"
find_field(dlg, "日期").value = "2026-09-20"
click(dlg, "保存")
badges = db.list_student_badges(portal_student)
ok(
    len(badges) == 2
    and any(
        badge["category"] == "竞赛"
        and badge["result"] == "一等奖"
        and badge["level_name"] == "小低组"
        for badge in badges
    )
    and any(
        badge["category"] == "考级"
        and badge["result"] == "优秀"
        and badge["level_name"] == "3级"
        and badge["level_id"] == configured_badge_level["id"]
        for badge in badges
    ),
    "学员可以记录竞赛奖项和 1～4 级考级徽章",
)
ok(
    "参与" not in db.COMPETITION_RESULTS
    and db.COMPETITION_RESULTS == ["一等奖", "二等奖", "三等奖"],
    "竞赛只有一二三等奖，没有参与奖",
)
try:
    db.save_student_badge(
        portal_student,
        "竞赛",
        "不应成功",
        "",
        "参与",
        "2026-10-01",
    )
    participation_badge_allowed = True
except ValueError:
    participation_badge_allowed = False
ok(not participation_badge_allowed, "不能添加参与奖徽章")
try:
    db.save_student_badge(
        portal_student,
        "考级",
        "不应成功",
        "5级",
        "通过",
        "2026-10-01",
    )
    invalid_exam_level_allowed = True
except ValueError:
    invalid_exam_level_allowed = False
ok(not invalid_exam_level_allowed, "考级级别只能是 1～4 级")

app.user = {
    "id": student_login["id"],
    "username": student_login["username"],
    "display_name": student_login["display_name"],
    "role": student_login["role"],
    "student_id": student_login["student_id"],
}
app.tab = 0
app.render()
ok(
    find_text(page.controls[0], "机器人创意赛")
    and find_text(page.controls[0], "机器人技术等级考试")
    and find_text(page.controls[0], "3级"),
    "学生能在我的页面看到自己的竞赛和考级徽章",
)

award_course = db.create_template(
    2,
    "16:00",
    60,
    zhengke["id"],
    configured_badge_level["id"],
    name="考级颁发权限课-李老师",
    teacher_id=portal_teacher,
)
db.create_enrollment(
    portal_student,
    configured_badge_level["id"],
    zhengke["id"],
    60,
    owner_teacher_id=portal_teacher,
    class_id=award_course,
)
award_other_teacher = db.create_user(
    "award_other", "pw123456", "其他颁发老师", db.ROLE_TEACHER
)
award_other_student = db.create_student(
    {
        "name": "别的课学员",
        "grade": "四年级",
        "owner_teacher_id": award_other_teacher,
        "owner_manual": True,
    }
)
award_other_course = db.create_template(
    3,
    "16:00",
    60,
    zhengke["id"],
    configured_badge_level["id"],
    name="考级颁发权限课-王老师",
    teacher_id=award_other_teacher,
)
db.create_enrollment(
    award_other_student,
    configured_badge_level["id"],
    zhengke["id"],
    60,
    owner_teacher_id=award_other_teacher,
    class_id=award_other_course,
)
app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
app.tab = 6
app.render()
ok(
    find_text(page.controls[0], "竞技与考级")
    and find_text(page.controls[0], "考级目录（1）")
    and find_text(page.controls[0], "徽章测试-三级考级")
    and find_text(page.controls[0], "学生门户娃"),
    "竞技考级目录会列出关联级别和已关联学员",
)
portal_teacher_row = db.get_user(portal_teacher)
app.user = {
    "id": portal_teacher,
    "username": portal_teacher_row["username"],
    "display_name": portal_teacher_row["display_name"],
    "role": portal_teacher_row["role"],
}
app.tab = 6
app.render()
app._open_level_award_dialog(configured_badge_level)
dlg = top_dialog(page)
ok(
    find_checkbox(dlg, "学生门户娃") is not None,
    "课程老师可以给本课学员颁发",
)
try:
    find_checkbox(dlg, "别的课学员")
    other_course_award_visible = True
except AssertionError:
    other_course_award_visible = False
ok(not other_course_award_visible, "其他课程老师不能给别人课上的学员颁发")
app._close()

app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}
app._open_level_award_dialog(configured_badge_level)
dlg = top_dialog(page)
find_field(dlg, "比赛／考级名称 *").value = "2026 机器人技术等级考试"
find_field(dlg, "日期 *").value = "2026-10-22"
student_award = find_checkbox(dlg, "学生门户娃")
student_award.value = True
award_result = find_dropdown(dlg, "学生门户娃的结果")
award_result.value = "良好"
click(dlg, "确认颁发")
level_awards = [
    badge
    for badge in db.list_student_badges(portal_student)
    if badge["title"] == "2026 机器人技术等级考试"
]
ok(
    len(level_awards) == 1
    and level_awards[0]["category"] == "考级"
    and level_awards[0]["level_name"] == "3级"
    and level_awards[0]["result"] == "良好",
    "目录里可以一次为本场关联学员颁发结果",
)
participant_teachers = {
    row["id"]: row["teacher_ids"]
    for row in db.list_badge_level_participants(configured_badge_level["id"])
}
award_teachers = {
    row["student_id"]: row["teacher_ids"]
    for row in db.list_level_badges(configured_badge_level["id"])
}
ok(
    participant_teachers[portal_student] == [portal_teacher]
    and participant_teachers[award_other_student] == [award_other_teacher]
    and award_teachers[portal_student] == [portal_teacher],
    "竞技考级关联和颁发记录都归对应课程老师",
)
db.save_badge_awards_for_level(
    configured_badge_level["id"],
    "2026 机器人技术等级考试",
    {portal_student: "通过"},
    "2026-10-22",
)
level_awards = [
    badge
    for badge in db.list_student_badges(portal_student)
    if badge["title"] == "2026 机器人技术等级考试"
]
ok(
    len(level_awards) == 1 and level_awards[0]["result"] == "通过",
    "同一场结果重复提交会更新，不会生成两枚重复徽章",
)
unlinked_student = db.create_student({"name": "未关联学员", "grade": "三年级"})
try:
    db.save_badge_awards_for_level(
        configured_badge_level["id"],
        "不应颁发",
        {unlinked_student: "通过"},
        "2026-10-22",
    )
    unlinked_award_allowed = True
except ValueError:
    unlinked_award_allowed = False
ok(not unlinked_award_allowed, "没有关联该级别的学员不能从目录批量颁发")
db.delete_student(unlinked_student)

db.delete_lesson(portal_lesson)
db.delete_lesson(portal_upcoming_lesson)
db.delete_template(award_other_course)
db.delete_template(award_course)
db.delete_student(award_other_student)
db.delete_user(award_other_teacher)
db.delete_user(student_login["id"])
db.delete_student(portal_student)
db.delete_level(configured_badge_level["id"], force=True)
db.delete_user(portal_teacher)
app.user = {"id": 1, "username": "root", "display_name": "管理员", "role": db.ROLE_ROOT}

print("50. 批量生成学生账号")
batch_birth = db.create_student(
    {
        "name": "拼音测试",
        "grade": "三年级",
        "birth_date": "2015-01-02",
    }
)
batch_random = db.create_student({"name": "随机密码", "grade": "三年级"})
batch_dup1 = db.create_student({"name": "重复名字", "grade": "三年级"})
batch_dup2 = db.create_student({"name": "重复名字", "grade": "三年级"})
created_accounts = db.create_missing_student_accounts()
by_student = {item["student_id"]: item for item in created_accounts}
ok(
    by_student[batch_birth]["username"] == "pinyinceshi"
    and by_student[batch_birth]["password"] == "20150102",
    "有生日时用姓名拼音和 YYYYMMDD 生日作初始密码",
)
ok(
    by_student[batch_random]["username"] == "suijimima"
    and len(by_student[batch_random]["password"]) == 8
    and by_student[batch_random]["password"].isdigit(),
    "没生日时用姓名拼音和 8 位随机数字密码",
)
ok(
    {
        by_student[batch_dup1]["username"],
        by_student[batch_dup2]["username"],
    }
    == {"zhongfumingzi", "zhongfumingzi2"},
    "同名学生的拼音用户名自动加序号",
)
ok(
    all(db.get_student_user(kid) is not None for kid in (batch_birth, batch_random, batch_dup1, batch_dup2)),
    "批量补建后每个正式学员都有账号",
)
for kid in (batch_birth, batch_random, batch_dup1, batch_dup2):
    db.delete_student(kid)

print("51. root 转入转学生自带课时")
transfer_teacher = db.create_user(
    "transfer_teacher",
    "pw123456",
    "转入测试老师",
    db.ROLE_TEACHER,
)
transfer_student = db.create_student(
    {
        "name": "转学生课时测试",
        "grade": "三年级",
        "owner_teacher_id": transfer_teacher,
        "owner_manual": True,
    }
)
transfer_root = db.get_user(1)
try:
    db.add_hour_transfer(
        transfer_teacher,
        transfer_student,
        today.isoformat(),
        "原机构转入",
        "",
        [{"hour_type_id": zhengke["id"], "hours": 1}],
    )
    teacher_transfer_allowed = True
except ValueError:
    teacher_transfer_allowed = False
ok(not teacher_transfer_allowed, "老师不能通过数据接口转入课时")

app.user = {
    "id": transfer_teacher,
    "username": "transfer_teacher",
    "display_name": "转入测试老师",
    "role": db.ROLE_TEACHER,
}
app.tab = 0
app.student_id = None
app.open_student(transfer_student)
try:
    find_button(page.controls[0], "转入已有课时")
    teacher_transfer_visible = True
except AssertionError:
    teacher_transfer_visible = False
ok(not teacher_transfer_visible, "老师界面看不到转入课时入口")

app.user = {
    "id": transfer_root["id"],
    "username": transfer_root["username"],
    "display_name": transfer_root["display_name"],
    "role": transfer_root["role"],
}
app.tab = 0
app.open_student(transfer_student)
ok(find_button(page.controls[0], "转入已有课时"), "root 能看到转入课时入口")
click(page.controls[0], "转入已有课时")
dlg = top_dialog(page)
find_field(dlg, "转入日期").value = today.isoformat()
find_field(dlg, "转入来源 *").value = "原机构转入"
find_dropdown(dlg, "课时类型 *").value = str(zhengke["id"])
find_field(dlg, "转入数量 *").value = "10"
find_button(dlg, "加一种课时").on_click(None)
transfer_types = [
    control
    for control in walk(dlg)
    if isinstance(control, ft.Dropdown) and control.label == "课时类型 *"
]
transfer_hours = [
    control
    for control in walk(dlg)
    if isinstance(control, ft.TextField) and control.label == "转入数量 *"
]
transfer_types[1].value = str(jingsai["id"])
transfer_hours[1].value = "2"
find_field(dlg, "备注").value = "原系统剩余课时"
click(dlg, "确认转入")

transfer_accounts = {a["name"]: a for a in db.get_accounts(transfer_student)}
ok(
    transfer_accounts["正课"]["transferred"] == 10
    and transfer_accounts["竞赛"]["transferred"] == 2,
    "一次转入可以记录多种课时",
)
ok(
    db.list_payments(transfer_student) == []
    and db.income_total(student_id=transfer_student) == 0,
    "转入课时不生成缴费记录，也不计入收入",
)
transfer_txs = [
    t
    for t in db.list_hour_transactions(transfer_student)
    if t["source_type"] == "hour_transfer"
]
ok(
    len(transfer_txs) == 2
    and all(t["transfer_origin"] == "原机构转入" for t in transfer_txs)
    and all(t["transfer_created_by_name"] == "管理员" for t in transfer_txs),
    "转入流水保留来源和 root 经办人",
)
app._open_hour_ledger(transfer_student, zhengke["id"])
ledger = top_dialog(page)
ok(
    find_text(ledger, "转入")
    and find_text(ledger, "原机构转入")
    and find_text(ledger, "经办 管理员"),
    "课时明细能区分转入、来源和经办人",
)
app._close()
_account_name, account_headers, account_rows = next(
    sheet for sheet in db.export_tables() if sheet[0] == "课时账户"
)
ok(
    "转入课时" in account_headers
    and any(row[0] == "转学生课时测试" and row[5] == 10 for row in account_rows),
    "导出时能看到转入课时",
)
db.delete_student(transfer_student)
ok(
    db.list_hour_transactions(transfer_student) == [],
    "删除学员时转入流水一起清理",
)
db.delete_user(transfer_teacher)

print(f"\n全部通过：{checks} 项检查")
