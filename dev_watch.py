"""开发时用：盯着项目里的 .py 文件，保存后自动重启 main.py。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IGNORE_DIRS = {".venv", "data", "__pycache__", ".git"}


def snapshot() -> dict[str, int]:
    out: dict[str, int] = {}
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if any(part in IGNORE_DIRS for part in relative.parts):
            continue
        try:
            out[str(path)] = path.stat().st_mtime_ns
        except OSError:
            pass
    return out


def start() -> subprocess.Popen:
    env = dict(os.environ)
    env["CLASS_HOURS_NO_BROWSER"] = "1"
    return subprocess.Popen(
        [sys.executable, str(ROOT / "main.py")],
        cwd=ROOT,
        env=env,
    )


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def main() -> int:
    proc = start()
    print("开发模式：改完 .py 文件保存后会自动重启；按 Ctrl+C 停止。")
    last = snapshot()
    try:
        while True:
            time.sleep(0.6)
            if proc.poll() is not None:
                print(f"服务退出了（退出码 {proc.returncode}），热重启监听也停下。")
                return proc.returncode or 1
            current = snapshot()
            if current != last:
                last = current
                print("检测到代码改动，正在重启…")
                stop(proc)
                proc = start()
    except KeyboardInterrupt:
        return 0
    finally:
        stop(proc)


if __name__ == "__main__":
    raise SystemExit(main())
