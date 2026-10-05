# 在 WSL 里静默运行（不出窗口、开机自己起）

目标：Windows 上装好 WSL，课时记录**在后台一直跑**——看不到终端窗口、不会弹浏览器，
开机登录后自己起来，用的时候在 Windows 浏览器打开 `http://localhost:8550` 就行。

> 前提：项目已经在 WSL 里装好（`uv sync` 跑过，`./启动.sh` 能手动启动）。
> 下面命令都在 **WSL 终端**里执行。

---

## 一、先看 WSL 支不支持 systemd

```bash
wsl --version          # 在 Windows 的 PowerShell 里跑，看版本
```

WSL 2.0 以上就支持 systemd（Windows 11，或者应用商店里更新的 WSL）。

## 二、方案一：用 systemd 常驻（推荐）

和 Ubuntu Server 上是同一套东西，仓库里现成的脚本就能用。

**1. 打开 systemd**（只需一次）：编辑 `/etc/wsl.conf`：

```ini
[boot]
systemd=true
```

```bash
sudo nano /etc/wsl.conf     # 没这个文件就新建
```

然后在 **Windows PowerShell** 里重启 WSL：

```powershell
wsl --shutdown
```

再进 WSL，确认 `systemctl` 能用：

```bash
systemctl is-system-running      # 不是 "offline" 就对了
```

**2. 装成服务**

```bash
cd ~/flet_pckj
sudo ./scripts/安装服务.sh
```

想顺便把数据放到项目外面（推荐，git 碰不到数据）：

```bash
sudo mkdir -p /var/lib/class-hours
sudo rsync -a ~/flet_pckj/data/ /var/lib/class-hours/
sudo chown -R $USER:$USER /var/lib/class-hours
sudo ./scripts/安装服务.sh --data-dir /var/lib/class-hours
```

**3. 确认**

```bash
systemctl status class-hours       # running 就是好的
curl -I http://127.0.0.1:8550      # 返回 200 就对了
```

之后 WSL 一启动，服务就自己起来；崩溃了 systemd 会拉起来（`Restart=always`）。

## 三、方案二：不开 systemd，直接后台跑

不想改 `/etc/wsl.conf` 的话用这个，效果一样，只是崩了不会自动重启：

```bash
cd ~/flet_pckj
./scripts/wsl-静默启动.sh
```

它会检查是不是已经在跑（在跑就不动），然后 `nohup` 丢到后台，日志写到
项目里的 `运行日志.log`。脚本里带了 `FLET_FORCE_WEB_SERVER=1`，所以不会去找浏览器。

停止：

```bash
kill "$(cat ~/flet_pckj/.run.pid)"
```

## 四、让 Windows 登录后自动、无窗口启动

用仓库里的 [docs/wsl/静默启动.vbs](../docs/wsl/静默启动.vbs)：双击它不会出现任何窗口，
它只是把 WSL 叫醒、再跑一遍上面的静默启动脚本（已经在跑就什么都不做）。

**要开机自动跑**，两种办法任选：

- **最简单**：按 `Win+R` → 输入 `shell:startup` → 回车，把 `静默启动.vbs`
  的快捷方式丢进去。
- **更可控**：任务计划程序 → 创建任务 →
  触发器「登录时」→ 操作「启动程序」，程序填 `wscript.exe`，
  参数填 `"C:\路径\静默启动.vbs"`，并勾上「隐藏」。

> 打开 `静默启动.vbs` 改两个地方：`-d Ubuntu` 里的发行版名字
> （用 `wsl -l -v` 看实际叫什么）、以及 `~/flet_pckj` 这个路径。

## 五、用起来

- Windows 上打开：`http://localhost:8550` —— WSL2 会把端口自动转发给 Windows，不用配
- **不会弹浏览器是故意的**：静默运行就是要它别弹，自己开浏览器输地址
- 看日志（systemd 方案）：`journalctl -u class-hours -f`
- 看日志（nohup 方案）：`tail -f ~/flet_pckj/运行日志.log`
- 停掉整个 WSL：`wsl --shutdown`（服务也会停；下次 WSL 起来会自动恢复）

## 六、手机访问要额外配一下

WSL2 默认是 NAT 网络，脚本打印的 `172.x.x.x` 手机连不上。两个办法：

**推荐：镜像网络**（Windows 11 22H2+）。`C:\Users\<你>\.wslconfig`：

```ini
[wsl2]
networkingMode=mirrored
```

`wsl --shutdown` 重进，然后**管理员 PowerShell** 放行端口：

```powershell
New-NetFirewallRule -DisplayName "课时记录 8550" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8550
New-NetFirewallHyperVRule -Name "课时记录 8550" -DisplayName "课时记录 8550" -VMCreatorId "{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}" -Direction Inbound -Protocol TCP -LocalPorts 8550
```

**或者：端口转发**（每次 WSL 重启后要重跑第一行）：

```powershell
$wslIp = (wsl hostname -I).Trim().Split()[0]
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8550 connectaddress=$wslIp connectport=8550
New-NetFirewallRule -DisplayName "课时记录 8550" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8550
```

手机打开 `http://<Windows 的局域网 IP>:8550`（`ipconfig` 看 WLAN 那节的 IPv4）。

## 七、常见问题

| 现象 | 怎么办 |
|---|---|
| `systemctl` 提示 offline/不能用 | `/etc/wsl.conf` 里没写 `[boot] systemd=true`，写完要 `wsl --shutdown` 重进 |
| 装了服务但 `localhost:8550` 打不开 | `journalctl -u class-hours -n 50` 看报错；确认 WSL 窗口不是刚 `--shutdown` 过 |
| 开机后没自动跑 | 看 `shell:startup` 里的快捷方式在不在；WSL 得先被唤醒，服务才会起来 |
| 双击 vbs 没反应 | 发行版名字不对（`wsl -l -v`），或项目路径不是 `~/flet_pckj` |
| 不想让它开机跑 | 删掉 `shell:startup` 里的快捷方式；再 `sudo systemctl disable class-hours` |
| 重启电脑后数据还在吗 | 在。数据在 WSL 的文件系统里（`~/flet_pckj/data` 或 `/var/lib/class-hours`），不受重启影响 |

> 提醒：WSL 里的数据是**另一份文件系统**，和 Windows 的 C 盘不是一套。
> 备份要么用 `./scripts/备份数据.sh` 备到 `/mnt/c/...`，
> 要么在 Windows 这边 `\\wsl.localhost\Ubuntu\home\<用户>\flet_pckj` 里拷出来。
