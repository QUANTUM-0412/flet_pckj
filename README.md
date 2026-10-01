```bash
ch
uv init flet_pckj

uv python pin 3.12

```



```bash
uv add flet

```

```python
import flet as ft

def main(page: ft.Page):
    page.title = "Hello Flet"
    page.add(ft.Text("Hello, Flet!"))

ft.run(main)

```

```bash
uv run flet run main.py

```

```bash
uv run flet run --web main.py

```

我需要一个记录课时的平台

他能满足多端访问

填写上课计划 记录课时 和孩子们的积分

- 缴费 孩子们缴费的记录
- 兑换积分的记录
- 上课表现
- 补课记录
- 试听记录

## 代码结构

- `main.py` —— 启动入口（起 Web 服务、打印手机访问地址）
- `app_ui.py` —— 界面组合入口：定义 `ClassHoursApp`，把 `ui/` 里各功能模块拼起来
- `ui/` —— 界面代码，按功能拆分：
  - `common.py` 常量与小工具、`auth.py` 登录、`shell.py` 导航外壳、`widgets.py` 卡片与对话框
  - `students.py` 学员、`schedule.py` 课表、`lessons.py` / `lesson_detail.py` / `lesson_dialogs.py` 上课与点名
  - `payments.py` 缴费、`points.py` 积分、`trials.py` 试听、`hours.py` 课时流水、`enrollment.py` 报名
  - `reports.py` 报表导出、`settings.py` 课程设置
- `db.py` —— 数据层（SQLite）
- `xlsx_writer.py` —— 极简 .xlsx 生成
- `tests/smoke_test.py` —— 自检脚本，跑法：`.venv/bin/python tests/smoke_test.py`
