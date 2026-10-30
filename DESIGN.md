---
name: 课时记录
description: 面向培训机构的日常教学与运营工作台
colors:
  action-blue: "#1976D2"
  action-blue-deep: "#1565C0"
  action-blue-soft: "#E3F2FD"
  canvas: "#F5F5F5"
  surface: "#FFFFFF"
  surface-muted: "#FAFAFA"
  line: "#E0E0E0"
  line-soft: "#EEEEEE"
  text: "#000000"
  text-secondary: "#757575"
  text-muted: "#9E9E9E"
  success: "#388E3C"
  warning: "#F57C00"
  danger: "#E53935"
typography:
  headline:
    fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.3
  title:
    fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: 1.3
rounded:
  sm: "6px"
  md: "10px"
  lg: "12px"
  nav: "16px"
  pill: "18px"
spacing:
  xs: "4px"
  sm: "6px"
  md: "8px"
  lg: "12px"
  xl: "14px"
  xxl: "20px"
components:
  button-primary:
    backgroundColor: "{colors.action-blue-soft}"
    textColor: "{colors.action-blue}"
    rounded: "{rounded.pill}"
    padding: "10px 16px"
    height: "44px"
  button-ghost:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.action-blue}"
    rounded: "{rounded.pill}"
    padding: "8px 12px"
  input-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "10px 12px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
    padding: "14px"
  navigation-active:
    backgroundColor: "{colors.action-blue-soft}"
    textColor: "{colors.action-blue-deep}"
    rounded: "{rounded.nav}"
    height: "56px"
---

# Design System: 课时记录

## Overview

**Creative North Star: "Daily Operations Ledger"**

这套系统像一本每天持续更新的机构工作台账：页面安静、信息密集但分组明确，重要状态用少量蓝色、橙色和绿色提示。它不追求营销页式的强情绪，而是让老师在点名、收费和查找学员时相信眼前的数据。

界面以浅灰画布、白色内容面和细边界构成。桌面端使用左侧导航保留完整业务目录，手机端只保留当天最常用的入口。登录后的第一屏以“今天”为中心，先回答要上什么课、谁需要点名、还有什么需要跟进。

**Key Characteristics:**

- 中文业务语言直接、克制。
- 平坦表面与一像素边界优先于阴影。
- 蓝色负责导航和主要动作，橙色负责待处理，红色只用于明确风险。
- 卡片内部通过间距和浅灰分组建立层级，不堆叠装饰。

## Colors

调色策略是浅色中性底上的单一蓝色强调，辅以有限的语义状态色。

### Primary

- **Operational Blue** (`action-blue`, #1976D2): 当前导航、文字按钮、主要动作和链接。
- **Deep Operational Blue** (`action-blue-deep`, #1565C0): 激活导航文字和需要更高对比度的强调。
- **Quiet Blue Surface** (`action-blue-soft`, #E3F2FD): 当前导航背景、轻量主按钮、今日课程高亮和合计区域。

### Neutral

- **Work Canvas** (`canvas`, #F5F5F5): 应用背景，让白色内容面彼此分开。
- **Record Surface** (`surface`, #FFFFFF): 卡片、弹窗和底部导航。
- **Muted Surface** (`surface-muted`, #FAFAFA): 列表行、表单分组和次要内容底。
- **Rule Line** (`line`, #E0E0E0): 卡片边界和主要分隔。
- **Soft Rule** (`line-soft`, #EEEEEE): 表格线、卡片内部分隔。
- **Primary Ink** (`text`, #000000): 标题和关键数据。
- **Secondary Ink** (`text-secondary`, #757575): 说明、元信息和辅助标签。
- **Quiet Ink** (`text-muted`, #9E9E9E): 非关键占位和空状态图标。

### Semantic

- **Confirmed Green** (`success`, #388E3C): 已完成、正常、已点名。
- **Action Orange** (`warning`, #F57C00): 待点名、待补课和课时预警。
- **Risk Red** (`danger`, #E53935): 删除、失败和负向账目。

**The Scarce Accent Rule.** Blue identifies navigation and action, not decoration; do not wash entire page sections in the accent.

## Typography

**Display Font:** System UI

**Body Font:** System UI

**Character:** 使用设备原生中文无衬线字体，追求熟悉的浏览器体验和稳定的小字号阅读，不引入具有品牌表演性的展示字体。

### Hierarchy

- **Headline** (700, 20px, 1.3): 页面名称和弹窗标题。
- **Title** (600, 15px, 1.35): 分区名称、班级名和主要列表标题。
- **Body** (400, 12px, 1.45): 档案、课程、金额说明和业务记录。
- **Label** (600, 11–12px, 1.3): 状态、导航、字段标签和紧凑元信息。

**The Information Before Ornament Rule.** Type hierarchy comes from size, weight, and spacing; decorative lettering is not used for operational data.

## Layout

应用外壳在 820px 及以上使用 96px 宽的左侧导航，窄屏使用 56px 高的底部导航。主要内容区使用 14px 水平内边距和 12px 的卡片间距。手机后台只保留“今天、学员、课程、更多”，低频模块进入底部面板。

工作台遵循单列优先：今日课程在上，待补课、课时不足和试听跟进在下。桌面端将三个待处理分组排成三列，手机端恢复纵向堆叠。课程页在窄屏先把标题和操作拆成两行，再显示搜索和课表。

表单与弹窗宽度以 300px 为常用基准，在手机上随可用宽度收敛。筛选使用底部面板，长表单内部滚动，操作按钮保持在可见区域。

## Elevation & Depth

系统以平坦表面为主，通过白色内容面、灰色画布、一像素边界和局部背景色分层。卡片默认没有投影；弹窗和弹出面板使用平台的 Material 浮层机制。

**The Flat-By-Default Rule.** Static records stay flat. Elevation is reserved for overlays and temporary interaction surfaces.

## Shapes

- 内容卡片使用柔和圆角（12px）。
- 列表行和表单分组使用较小圆角（10px）。
- 输入框和标签使用紧凑圆角（6px）。
- 按钮、账号条和主要操作使用胶囊形圆角。
- 边界统一为一像素实线，不使用装饰性粗边。

## Components

### Buttons

- **Shape:** 胶囊形；触控动作至少 44px 高。
- **Primary:** 浅蓝背景配 Operational Blue 文本，用于当前任务的主要下一步。
- **Hover / Focus:** 保持蓝色文字并显示平台焦点；不以颜色单独表达可用性。
- **Secondary / Ghost:** 白底或透明底配蓝色文字，用于查看、清空和次级导航。

### Chips

- **Style:** 6px 圆角的小型实色标签，白字。
- **State:** 绿色表示完成，橙色表示待处理，灰色表示中性或已结束，红色只用于风险。

### Cards / Containers

- **Corner Style:** 12px。
- **Background:** 白色主体；内部列表使用 `surface-muted`。
- **Shadow Strategy:** 静态卡片无阴影。
- **Border:** 1px `line`。
- **Internal Padding:** 10–14px，相关字段使用 6–8px 间距。

### Inputs / Fields

- **Style:** 白底、细边界、浮动标签和紧凑高度。
- **Focus:** 以平台蓝色边框或焦点状态确认当前字段。
- **Error / Disabled:** 错误文字放在字段附近；禁用字段保持可读，不通过降低到不可辨认来暗示权限。

### Navigation

- **Desktop:** 96px 白色左侧栏，图标与文字同时出现；当前项使用浅蓝背景和深蓝文字。
- **Mobile:** 56px 白色底栏，最多四项；“更多”面板展开其余业务模块。

### Daily Workbench

今日课程行把时间、状态、班级、老师和人数放在同一阅读单元，右侧只保留一个与当前状态匹配的动作。待处理事项采用紧凑列表，数量直接写入分组标题。

### Payment Summary

缴费弹窗先呈现学员、日期、缴费方式和课时明细，再用浅蓝汇总块显示本笔实收。规则说明和低频提示默认折叠。

## Do's and Don'ts

### Do:

- **Do** 让主要动作在每个页面只有一个视觉中心。
- **Do** 在手机端保持至少 44px 的触控高度和清晰的文字标签。
- **Do** 用橙色文字或标签同时说明“待点名、待补课、课时不足”等状态。
- **Do** 把长规则说明放进上下文提示或折叠区。
- **Do** 保留稳定的导航页签编号和既有业务数据关系。

### Don't:

- **Don't** 在手机底栏同时塞入全部后台模块。
- **Don't** 用长课程编码压过班级名称、剩余课时和待处理状态。
- **Don't** 让相同业务动作在不同页面使用不同名称。
- **Don't** 在静态列表卡片上添加装饰性阴影或粗色边。
- **Don't** 用颜色或图标单独承载错误、成功或权限含义。
