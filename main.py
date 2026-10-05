"""课时记录平台 —— 启动文件。

用法：在店里那台电脑上运行 python main.py。
电脑会自动打开浏览器；手机连上同一个 WiFi，用终端里显示的地址打开就行。
"""

from __future__ import annotations

import os
import socket

import flet as ft

import db
from app_ui import ClassHoursApp

PORT = int(os.environ.get("CLASS_HOURS_PORT", "8550"))


def lan_ips() -> list[str]:
    """列出本机可能能用的局域网地址，手机上挑打得开的那个。"""
    ips: list[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    try:  # 服务器上常常不止一张网卡，多列几个省得猜
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


def main(page: ft.Page) -> None:
    db.init_db()
    ClassHoursApp(page).render()


if __name__ == "__main__":
    db.init_db()
    print("课时记录已经启动。")
    print(f"  这台电脑上打开：http://127.0.0.1:{PORT}")
    for ip in lan_ips():
        print(f"  手机上打开：    http://{ip}:{PORT}")
    print("（手机要和这台电脑连同一个 WiFi；关掉这个窗口就停止了）")
    print("（要装在 Ubuntu Server 上常驻，见 docs/UbuntuServer部署.md）")
    ft.run(
        main,
        view=ft.AppView.WEB_BROWSER,
        host="0.0.0.0",
        port=PORT,
        assets_dir=str(db.UPLOAD_DIR),  # 上传的照片/附件也放在 data 里，一起备份
    )
