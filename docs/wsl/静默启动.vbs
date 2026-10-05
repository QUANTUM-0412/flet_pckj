' 静默启动 WSL 里的课时记录平台：双击即可，不会弹出任何窗口。
'
' 想让 Windows 登录时自动跑：
'   1. 按 Win+R，输入 shell:startup，回车
'   2. 把本文件（或它的快捷方式）拖进去
'
' 注意：下面的 Ubuntu 是 WSL 发行版名字，用 wsl -l -v 看实际叫什么。
'       ~/flet_pckj 换成项目实际路径。
Set sh = CreateObject("WScript.Shell")
sh.Run "wsl.exe -d Ubuntu -- bash -lc ""cd ~/flet_pckj && ./scripts/wsl-静默启动.sh""", 0, False
