"""从课评里挑出这节课学的东西（知识点／作品名），放在海报上给家长看。

不联网、不用大模型：拿一份常见词表去课评里找，再从引号里捞老师特意强调的词。
找不到就返回空，海报上那行自动不显示。
"""

from __future__ import annotations

import re

# 一份「课评里常写」的词表：建模／打印／机械电子／编程／竞赛
TERMS: tuple[str, ...] = (
    # 三维建模、设计
    "草图",
    "约束",
    "尺寸",
    "基准面",
    "基准轴",
    "参考面",
    "拉伸切除",
    "拉伸凸台",
    "拉伸",
    "切除",
    "旋转",
    "扫描",
    "放样",
    "抽壳",
    "倒角",
    "圆角",
    "镜像",
    "阵列",
    "拔模",
    "成型到面",
    "引导线",
    "曲面",
    "实体",
    "特征",
    "装配",
    "配合",
    "干涉",
    "工程图",
    "三视图",
    "剖视",
    "螺纹",
    "建模",
    "模型",
    "图纸",
    "标注",
    # 打印
    "3D打印",
    "切片",
    "支撑",
    "填充",
    "层高",
    "热床",
    "喷头",
    "耗材",
    "PLA",
    "建模软件",
    # 结构、机械、电子
    "底座",
    "支架",
    "车架",
    "齿轮",
    "齿条",
    "连杆",
    "轴承",
    "传动",
    "结构",
    "螺丝",
    "螺母",
    "电机",
    "马达",
    "舵机",
    "履带",
    "轮子",
    "轮胎",
    "主板",
    "电池",
    "电路",
    "引脚",
    "传感器",
    "超声波",
    "红外",
    "循迹",
    "陀螺仪",
    "加速度计",
    "蜂鸣器",
    "显示屏",
    "电位器",
    "按钮",
    "灯带",
    "RGB",
    # 编程
    "变量",
    "循环",
    "条件",
    "判断",
    "函数",
    "参数",
    "返回值",
    "列表",
    "数组",
    "字典",
    "字符串",
    "布尔",
    "递归",
    "算法",
    "排序",
    "查找",
    "遍历",
    "嵌套",
    "事件",
    "广播",
    "克隆",
    "角色",
    "舞台",
    "造型",
    "积木",
    "坐标",
    "随机数",
    "计时器",
    "调试",
    "报错",
    "输入输出",
    "串口",
    "波特率",
    "PWM",
    "蓝牙",
    "WiFi",
    "物联网",
    "语音识别",
    "图像识别",
    "人脸识别",
    "避障",
    "遥控",
    "自动化",
    # 语言、工具
    "Scratch",
    "Python",
    "海龟",
    "绘图",
    "turtle",
    "pygame",
    "Arduino",
    "Mixly",
    "Mind+",
    "KC",
    "程序",
    "代码",
    "脚本",
    "模块",
    # 竞赛、任务
    "巡线",
    "抓取",
    "搬运",
    "任务",
    "挑战",
    "计时",
    "得分",
    "规则",
    "比赛",
    "作品",
)

_SORTED_TERMS = sorted(TERMS, key=len, reverse=True)
_QUOTE_PATTERN = re.compile(r"[「『“\"']([^「『」』“”\"'。！？，、；：\n]{2,14})[」』”\"']")


def extract_keywords(text: str, limit: int = 4) -> list[str]:
    """按在课评里出现的先后，挑出最多 limit 个词。"""
    body = (text or "").strip()
    if not body:
        return []

    found: list[tuple[int, str]] = []
    lowered = body.lower()
    for term in _SORTED_TERMS:
        index = lowered.find(term.lower())
        if index >= 0:
            found.append((index, term))
    # 老师特意加引号的词（比如「成型到面」）优先当成知识点
    for match in _QUOTE_PATTERN.finditer(body):
        found.append((match.start(), match.group(1).strip()))

    found.sort(key=lambda item: (item[0], -len(item[1])))
    picked: list[str] = []
    for _, term in found:
        if any(term in kept or kept in term for kept in picked):
            continue  # 「拉伸」和「拉伸切除」只留长的那个
        picked.append(term)
        if len(picked) >= limit:
            break
    return picked
