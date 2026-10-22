# 从 Windows WSL 迁移到树莓派

目标是把已经在 WSL 里跑起来的课时记录平台，原样迁到树莓派：
代码和 Python 环境在树莓派上新装，只把 `data/` 里的数据库和上传文件搬过去，
最后交给 systemd 常驻运行。

迁移顺序很重要：**先让树莓派跑通，再停 WSL 做最终备份并切换。**
正式数据不要在两台机器上同时修改，否则会形成两份无法自动合并的数据。

---

## 一、运行环境要求

建议树莓派使用 **64 位 Raspberry Pi OS**（Bookworm 或更新版本），并优先使用
Raspberry Pi 4/5。可以先在树莓派上确认：

```bash
uname -m
getconf LONG_BIT
```

正常应看到：

```text
aarch64
64
```

如果看到 `armv7l` 和 `32`，建议重装 64 位系统后再迁移。32 位环境不是这套项目
常用的验证目标，图片处理和依赖安装更容易出问题。

树莓派和 Windows 电脑应在同一个局域网，并且可以从 Windows 通过 SSH 登录树莓派。
下面示例使用用户名 `pi`，请换成你实际创建的用户名；服务不建议直接用 `root` 运行。

## 二、先在树莓派安装代码和依赖

SSH 登录树莓派：

```bash
ssh pi@树莓派IP
```

安装系统软件。中文字体不能用，做海报时会失败；HEIC 工具用于处理 iPhone 照片：

```bash
sudo apt update
sudo apt install -y git curl rsync sqlite3 fonts-noto-cjk imagemagick libheif-examples
```

安装 uv 和项目要求的 Python 3.12：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv python install 3.12
```

拉取代码前，树莓派必须能访问 GitHub。仓库是私有的，推荐给树莓派单独创建一把
只读 SSH 密钥。不要复制 WSL 或 Windows 上的私钥，也不要把私钥发给别人。

先在树莓派生成专用密钥：

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -C "raspberry-pi-class-hours" \
  -f ~/.ssh/github_class_hours -N ""
chmod 600 ~/.ssh/github_class_hours
chmod 644 ~/.ssh/github_class_hours.pub
```

配置 GitHub 使用这把密钥：

```bash
cat >> ~/.ssh/config <<'EOF'
Host github-class-hours
  HostName github.com
  User git
  IdentityFile ~/.ssh/github_class_hours
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
```

显示公钥：

```bash
cat ~/.ssh/github_class_hours.pub
```

复制 `ssh-ed25519` 开头的整行公钥，到 GitHub 私有仓库：
**Settings → Deploy keys → Add deploy key**。标题可以填
`Raspberry Pi - class hours`，公钥粘贴进去；只用来下载代码，所以
**不要勾选 Allow write access**。

测试连接：

```bash
ssh -T git@github-class-hours
```

看到 `successfully authenticated` 就说明密钥配置成功。GitHub 提示不提供 shell
访问是正常现象。

然后拉取代码：

```bash
cd ~
git clone git@github-class-hours:QUANTUM-0412/flet_pckj.git
cd ~/flet_pckj
uv sync
```

如果暂时无法给树莓派配置 GitHub 密钥，也可以在 WSL 里执行
`git archive --format=tar.gz --output=/tmp/flet-pckj-code.tar.gz HEAD`，
用 `scp` 把代码包传到树莓派，在 `~/flet_pckj` 里解压。这样能先完成迁移，
但以后更新代码仍建议补上 Deploy Key；不要把 `.git` 目录和私钥一起随意拷贝。

此时不要在树莓派上启动服务，也暂时不要把 WSL 的整个项目目录直接覆盖过来。
`data/` 不在 Git 仓库里，下一步单独安全地导出。

## 三、在 WSL 做最终备份

先确认旧服务实际用的是哪份数据。项目默认读取 `data/app.db`，但如果安装服务时用了
`--data-dir`，正式数据可能已经放在 `/var/lib/class-hours`：

```bash
cd ~/flet_pckj/flet_pckj
sudo systemctl cat class-hours 2>/dev/null | grep 'Environment=CLASS_HOURS_' || true
```

如果有输出，例如：

```text
Environment=CLASS_HOURS_DB=/var/lib/class-hours/app.db
Environment=CLASS_HOURS_FILES=/var/lib/class-hours/files
```

那么本机正式数据目录就是 `/var/lib/class-hours`；没有这几行时，才是项目里的
`data/`。按实际情况设置一个变量，后面全部以它为准：

```bash
# 按上一步的实际输出二选一
SOURCE_DATA_DIR=/var/lib/class-hours
# SOURCE_DATA_DIR=$PWD/data
```

先停止 WSL 里的旧服务，确保备份期间没有新记录写入。

如果旧服务是用 systemd 安装的：

```bash
cd ~/flet_pckj/flet_pckj
sudo systemctl stop class-hours
```

如果旧服务是用 `wsl-silent-start.sh` 启动的：

```bash
cd ~/flet_pckj/flet_pckj
if [ -f .run.pid ]; then
  kill "$(cat .run.pid)"
fi
```

随后确认 8550 端口已经停止监听：

```bash
curl --max-time 2 -sS http://127.0.0.1:8550 >/dev/null && echo "仍在运行" || echo "已停止"
```

显示“已停止”后，用项目自带备份脚本生成 SQLite 一致性快照。不要直接 `cp app.db`，
数据库正在写入时直接复制可能得到损坏文件：

```bash
CLASS_HOURS_DB="$SOURCE_DATA_DIR/app.db" \
CLASS_HOURS_FILES="$SOURCE_DATA_DIR/files" \
  ./scripts/backup-data.sh /tmp/class-hours-migration --keep 0
```

创建一个只包含 `app.db` 和 `files/` 的传输包：

```bash
MIGRATION_DIR=$(find /tmp/class-hours-migration -maxdepth 1 -type d -name '课时记录-*' | sort | tail -n 1)
test -n "$MIGRATION_DIR"
tar -czf /tmp/class-hours-data.tar.gz -C "$MIGRATION_DIR" app.db files
sha256sum /tmp/class-hours-data.tar.gz | tee /tmp/class-hours-data.sha256
```

检查数据库快照本身是完整的：

```bash
.venv/bin/python - "$MIGRATION_DIR/app.db" <<'PY'
import sqlite3
import sys

con = sqlite3.connect(sys.argv[1])
print(con.execute("PRAGMA integrity_check").fetchone()[0])
con.close()
PY
```

结果必须是 `ok`。如果不是，停止迁移并保留 WSL 里的原始数据。

## 四、把数据传到树莓派

直接从 WSL 使用 `scp` 传到树莓派的临时目录：

```bash
scp /tmp/class-hours-data.tar.gz pi@树莓派IP:~/
scp /tmp/class-hours-data.sha256 pi@树莓派IP:~/
```

在树莓派上校验传输没有损坏：

```bash
cd ~
sha256sum -c class-hours-data.sha256
```

必须看到 `OK` 再继续。

## 五、把数据放进长期目录

推荐把代码和数据分开。数据放到树莓派本地磁盘的 `/var/lib/class-hours`，
以后更新代码或重拉仓库都不会碰它：

```bash
sudo install -d -o "$USER" -g "$USER" -m 750 /var/lib/class-hours
sudo tar -xzf ~/class-hours-data.tar.gz -C /var/lib/class-hours
sudo chown -R "$USER:$USER" /var/lib/class-hours
```

检查导入结果：

```bash
ls -lh /var/lib/class-hours/app.db
find /var/lib/class-hours/files -type f | wc -l
sqlite3 /var/lib/class-hours/app.db 'PRAGMA integrity_check;'
sqlite3 /var/lib/class-hours/app.db 'SELECT COUNT(*) FROM students;'
sqlite3 /var/lib/class-hours/app.db 'SELECT COUNT(*) FROM lessons;'
```

数据必须放在树莓派本地磁盘，不要放到 NFS、SMB 或睡眠频繁的移动硬盘上，
SQLite 在这种存储上容易出现文件锁问题。

## 六、在树莓派手动试跑

进入代码目录，清空数据库/文件目录环境变量，避免把测试目录带进正式服务：

```bash
cd ~/flet_pckj
env -u CLASS_HOURS_DB -u CLASS_HOURS_FILES \
  CLASS_HOURS_DB=/var/lib/class-hours/app.db \
  CLASS_HOURS_FILES=/var/lib/class-hours/files \
  CLASS_HOURS_NO_BROWSER=1 \
  .venv/bin/python main.py
```

保持这个终端运行，在树莓派另开一个 SSH 会话检查：

```bash
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8550
```

返回 `200` 后，再用 Windows 或手机浏览器打开：

```text
http://树莓派IP:8550
```

重点确认：

- 默认管理员能登录，学员和课时记录数量与迁移前一致；
- 上传的照片、附件和海报能打开；
- 新建测试记录后重启服务，数据仍然存在。

确认后回到运行服务的终端按 `Ctrl+C` 停止，再安装正式服务。

## 七、安装为开机自启服务

必须确保当前普通用户已经执行过 `uv sync`，并且 `.venv/bin/python` 存在：

```bash
cd ~/flet_pckj
sudo ./scripts/install-service.sh --data-dir /var/lib/class-hours
```

检查状态并测试自动重启：

```bash
systemctl status class-hours
journalctl -u class-hours -n 100 --no-pager
sudo systemctl restart class-hours
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8550
```

如果开启了防火墙：

```bash
sudo ufw allow 8550/tcp
sudo ufw status
```

然后在 Windows 和手机上都用 `http://树莓派IP:8550` 打开一次。
树莓派重启后也应能在不登录终端的情况下继续访问。

## 八、完成切换

树莓派确认可用并保留一份备份后，再停用 WSL 的旧实例，避免两边同时产生业务数据：

```bash
# 在 WSL
sudo systemctl disable --now class-hours
```

如果 WSL 原本用 `wsl-silent-start.sh` 开机启动，还要删除或停用 Windows
`shell:startup` 里的 `silent-start.vbs` 快捷方式。

WSL 的原始 `data/` 至少保留到树莓派稳定运行一段时间。旧实例不要再打开并录入数据；
以后如需回滚，应停掉树莓派服务，再把树莓派数据完整备份后导入 WSL，不能只复制一半文件。

## 九、建议立即设置的自动备份

先手动验证一次备份：

```bash
cd ~/flet_pckj
CLASS_HOURS_DB=/var/lib/class-hours/app.db \
CLASS_HOURS_FILES=/var/lib/class-hours/files \
  ./scripts/backup-data.sh /var/lib/class-hours/backups --keep 7
```

编辑 cron：

```bash
crontab -e
```

加入下面一行，并把用户名和路径改成实际值：

```cron
30 22 * * * cd /home/pi/flet_pckj && CLASS_HOURS_DB=/var/lib/class-hours/app.db CLASS_HOURS_FILES=/var/lib/class-hours/files ./scripts/backup-data.sh /var/lib/class-hours/backups --keep 7 >> /home/pi/class-hours-backup.log 2>&1
```

同一块盘上的备份只能防误删，不能防 SD 卡或硬盘损坏。建议每周再把
`/var/lib/class-hours/backups/` 同步到另一台电脑、移动硬盘或私有网盘。

## 十、常见问题

| 现象 | 处理 |
|---|---|
| `uv: command not found` | 执行 `source ~/.bashrc`，或重开 SSH；uv 通常位于 `~/.local/bin` |
| `uv sync` 在树莓派安装依赖失败 | 确认 `uname -m` 是 `aarch64`、系统时间和网络正常，再重试 |
| 服务启动失败 | 看 `journalctl -u class-hours -n 100 --no-pager`，最常见是数据目录权限或 `.venv` 不存在 |
| 图片或海报打不开 | 检查 `/var/lib/class-hours/files` 是否存在及权限是否正确 |
| 做海报提示找不到中文字体 | 确认已安装 `fonts-noto-cjk`，再 `sudo systemctl restart class-hours` |
| Windows 能连、手机不能连 | 确认手机在同一 WiFi、路由器未开启客户端隔离、树莓派 ufw 已放行 8550 |
| WSL 和树莓派数据不一致 | 不要猜哪份新；停两边服务，分别备份，再人工确认后选一份作为正式数据 |

