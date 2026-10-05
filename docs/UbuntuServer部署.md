# 部署到 Ubuntu Server

这个项目本身就是「跑一个小服务 + 浏览器访问」，最适合放在 Ubuntu Server 上常年开着：
电脑、手机、iPad 连上网，浏览器打开同一个地址就能用，不用在每台设备上装东西。

装完的效果：**开机自动启动、关掉终端也不停、崩了自动重启**。

---

## 一、服务器上装运行环境

SSH 进服务器，依次执行（x86_64 和 arm64 都支持，树莓派 / Oracle ARM 一样能用）：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc                # 让 uv 命令立刻生效
uv python install 3.12
```

中文字体——**这一步别省**，不然「做海报」会报找不到中文字体（Ubuntu Server 默认一个中文字体都没有）：

```bash
sudo apt update
sudo apt install -y fonts-noto-cjk
```

顺手装上处理照片的工具（可选，但建议）：iPhone 拍的 HEIC 照片靠它们转成 JPEG，能自动压小。

```bash
sudo apt install -y imagemagick libheif-examples
```

不装也不影响使用：HEIC 照片会原样存下来（不丢，只是不压缩）。

## 二、把项目和数据传上去

### 在 Mac 上打包

在项目目录里：

```bash
./scripts/打包部署包.sh
```

会在项目的上一级目录生成 `flet_pckj-部署包-日期.tar.gz`。
这个包**连 `data/` 一起带走**——数据库、上传的照片、海报都在里面，搬过去就是原样。
（不含 `.venv`，到服务器上重新 `uv sync` 装一份；`.git` 带上了，以后还能 `git pull` 拉更新。）

### 传到服务器

```bash
scp ~/Creeping·Hunger/flet_pckj-部署包-*.tar.gz 你的用户名@服务器IP:~/
```

### 服务器上解开

```bash
cd ~
tar -xzf flet_pckj-部署包-*.tar.gz
cd flet_pckj
```

> ⚠️ **别把部署包解到已经在跑的服务器目录上**——包里的 `data/` 会把线上的数据盖成
> Mac 上那份旧的。要么用在一个空目录（第一次搬），要么照第三节只解 `data/`。

> **放在哪儿**：家目录（`~`）或者 `/opt` 都行，但必须是**服务器本地磁盘**，
> 不要放 NFS / SMB / 挂载的网盘——SQLite 在这种盘上很容易锁表出错。
> 另外，运行服务的那个用户要对这个目录有读写权限（因为数据写在里面）。

> **用 GitHub 的话**：代码走 `git clone`，这个部署包就只用来搬 `data/` 数据——
> 见下一节。

## 三、用 GitHub 托管代码（推荐）

代码放 GitHub 上，服务器就能一条命令更新，不用每次打包上传。

> **关键区别：GitHub 只管代码，`data/` 不在 git 里**（`.gitignore` 里排除了）。
> 所以数据要么按第二节用部署包搬一次，要么单独 `scp` 一次。之后代码随便更新，
> 数据不会被碰。

### 推之前：先把本地的改动提交上（这一步别跳过）

现在的仓库**直接推上去，clone 下来是跑不起来的**：

- `poster.py`、`keywords.py` 从来没提交过，而 `ui/` 里在引用它们（会报 `ModuleNotFoundError`）
- `ui/`、`db.py`、`main.py` 等还有一批改了没提交的改动
- `上课时间表-*.xlsx` 里有学员姓名，**不要**传上去（已经加进 `.gitignore` 了）
- `data/` 里是全部记录和照片，同样不进 git

在 Mac 上提交：

```bash
git add -A
git status                    # 扫一眼，确认没有 data/ 和 Excel
git commit -m "课时记录平台：界面、海报、设置等改动"
```

### 建仓库、推上去

到 GitHub 上建一个 **Private（私有）** 仓库——这是给机构用的业务代码，别开公开仓库。

```bash
git remote add origin git@github.com:你的账号/flet_pckj.git
git branch -M main
git push -u origin main
```

没配 SSH key 的话，用 HTTPS 地址，push 时输用户名和 token 也一样。

### 服务器上：clone 代码，数据搬一次

```bash
cd ~
git clone git@github.com:你的账号/flet_pckj.git
cd flet_pckj
```

数据从部署包里拿（Mac 上 `./scripts/打包部署包.sh` 之后 scp 过来），**只解 data 这一层**：

```bash
tar -xzf ~/flet_pckj-部署包-*.tar.gz --strip-components=1 -C ~/flet_pckj flet_pckj/data
```

> 别把整个包直接解到 clone 出来的目录上——包里的 `.git` 会盖掉刚 clone 的仓库。
> 只解 `data/` 就没这个问题；或者用 `scp -r` 单独传 `data` 目录。

然后照第五节装成服务就行。

### 以后更新代码

```bash
cd ~/flet_pckj
./scripts/更新服务.sh
```

它做三件事：`git pull` → `uv sync` → 重启服务（`git status` 能自动帮你发现服务器上被手改的文件）。

**服务器上不要手改代码**：改了会挡住 `git pull`。要改就在 Mac 上改、提交、推上来。

## 四、先手动跑一次

```bash
uv sync          # 第一次装依赖，要联网
./启动.sh
```

看到「课时记录已经启动」和一串地址，就是成了。
在**另一台电脑**浏览器里打开 `http://服务器IP:8550`，能看到登录页就说明网络也通了。

确认没问题后，按 `Ctrl+C` 停掉，接着做第五步——让它常驻。

## 五、装成开机自启的服务（推荐）

```bash
sudo ./scripts/安装服务.sh
```

这个脚本会把 `deploy/class-hours.service` 填好路径和用户名，装到
`/etc/systemd/system/class-hours.service`，然后设成开机自启并立刻启动。

之后常用命令：

```bash
systemctl status class-hours            # 看状态（running 就是好的）
journalctl -u class-hours -f            # 实时看日志，里面会打印访问地址
sudo systemctl restart class-hours      # 重启
sudo systemctl stop class-hours         # 停止
```

服务器重启、或者程序崩了，都会自动起来（`Restart=always`）。

**改了代码之后**，让它生效：

```bash
uv sync                    # 如果依赖变了才需要
sudo systemctl restart class-hours
```

**想换端口 / 换数据目录**：改 `/etc/systemd/system/class-hours.service` 里的
`Environment=` 那几行，然后 `sudo systemctl daemon-reload && sudo systemctl restart class-hours`。

## 六、让别人（手机）能连上

### 服务器自己的防火墙

如果开了 ufw：

```bash
sudo ufw allow 8550/tcp
sudo ufw status
```

### 云服务器还要放行安全组

阿里云 / 腾讯云 / AWS / Oracle 这类，要去控制台的「安全组」「防火墙」里
放行 TCP **8550** 端口——ufw 放行了但安全组没放，手机照样连不上。

### 手机、iPad 上打开

和服务器在同一个局域网（同一个 WiFi）时：

```
http://服务器IP:8550
```

服务器 IP 用 `hostname -I` 看（取第一个地址）。程序启动时打印的那几行地址，
随便挑一个在手机浏览器里试，能打开的那个就是对的。

### 不在同一个网络？

那就需要公网 IP，或者用内网穿透 / VPN。**强烈建议不要直接把 8550 裸奔在公网上**——原因见下一节。
比较省心的做法是装个 Tailscale（服务器和手机都装、登同一个账号），
然后用 `http://服务器的Tailscale地址:8550` 访问，等于自建了一条加密专线。

## 七、安全提醒（重要）

这套系统里有学员信息、缴费记录，管理员账号能改一切。所以：

- **默认管理员账号是 `root`，密码是 `1234`**，装好后第一件事就是在「设置 → 老师账号」里改掉。
- 只想在店里局域网用的话，就**不要**在路由器上做端口映射，也不用放开公网安全组。
- 想从外面访问，推荐 Tailscale / WireGuard 这类 VPN，或者用 Nginx 反代 + HTTPS（顺便还能挂个域名）。
  直接暴露 8550 到公网，至少也要有强密码，并且别用默认端口。
- 老师账号的权限要按需给：管理员能删记录、改课时，老师不能。

## 八、数据会涨多大、放哪儿、怎么备份

### 数据长什么样

| 路径（默认在项目里的 `data/`） | 是什么 | 会长多大 |
|---|---|---|
| `app.db` | 全部记录（学员、课时、缴费、积分、试听……） | 很小，纯文字。现在 13 个学员、33 节课是 260 KB，涨到几万条也就是几十 MB |
| `files/` | 上传的照片、做的海报 | **这才是增长的大头**。照片自动压到 800 KB 以内，实际一张 200–400 KB；一天传 10 张，一年大约 1 GB |
| `files/exports/` | 导出 Excel 时顺手留的一份 | 很小（每个几十 KB） |

所以：**不用换数据库**。SQLite 扛这个量级绰绰有余，几个老师同时用也没问题
（程序自带 5 秒的写锁等待）。真正要盯的是照片占的磁盘。

### 建议：把数据放到项目外面

默认数据在项目目录里的 `data/`。长期在服务器上跑，更推荐把**代码**和**数据**分开：

```
~/flet_pckj/              ← git 克隆的代码，可以随便 pull、重装
/var/lib/class-hours/     ← 数据（app.db + files），git 永远碰不到
```

装服务时一个参数就搞定（数据要先搬过去，脚本会告诉你确切命令）：

```bash
sudo mkdir -p /var/lib/class-hours
sudo rsync -a ~/flet_pckj/data/ /var/lib/class-hours/
sudo chown -R $USER:$USER /var/lib/class-hours
sudo ./scripts/安装服务.sh --data-dir /var/lib/class-hours
```

好处：代码怎么折腾都动不到数据；以后数据大了可以整个目录挪到更大的盘；
备份就是备这一个目录。想看会生成什么，先跑 `./scripts/安装服务.sh --dry-run --data-dir /var/lib/class-hours`。

### 备份

**不要**直接 `cp` 正在使用的 `app.db`——程序在写的时候可能拷到一半，拷出来的文件是坏的。
用仓库里带的脚本，它走 SQLite 的备份接口，做出来的一定是一致的：

```bash
./scripts/备份数据.sh                                    # 备到 <数据目录>/backups，保留最近 7 份
./scripts/备份数据.sh /media/你的U盘名/课时记录             # 备到 U 盘 / 移动硬盘
./scripts/备份数据.sh /mnt/backup/课时记录 --keep 30       # 留 30 份
```

每次备出来的是 `课时记录-年月日_时分秒/`，里面是 `app.db` + `files/`。
超出的旧备份会自动删掉（只删名字是 `课时记录-*` 的，别的不碰）。

> 注意：**保留份数 × 数据大小 = 占的盘**。数据到 1 GB 时，留 7 份就是 7 GB。
> 数据涨起来以后把 `--keep` 调小，或者备到别的盘上。

每天自动备一份，`crontab -e` 加一行（`crontab` 里的路径要写全）：

```cron
# 每天 22:30 备份到 /mnt/backup（换成你自己的盘）
30 22 * * * /home/你的用户名/flet_pckj/scripts/备份数据.sh /mnt/backup/课时记录 --keep 7 >> /home/你的用户名/backup.log 2>&1
```

> 备份和原始数据在同一块盘上，挡不住硬盘坏。隔段时间往移动硬盘、另一台机器
> 或者网盘再挪一份。

### 恢复

停掉服务，把备份里的 `app.db` 和 `files/` 覆盖回数据目录，再启动：

```bash
sudo systemctl stop class-hours
sudo rsync -a 备份目录/课时记录-xxxx/ /var/lib/class-hours/
sudo chown -R $USER:$USER /var/lib/class-hours
sudo systemctl start class-hours
```

## 九、常见问题

| 现象 | 怎么办 |
|---|---|
| `uv: command not found` | `source ~/.bashrc`，或者重开终端；uv 装在 `~/.local/bin` |
| 做海报报「找不到中文字体」 | `sudo apt install fonts-noto-cjk`，然后重启服务 |
| `systemctl status` 显示失败 | `journalctl -u class-hours -n 100` 看真正的报错 |
| 端口被占用 | 改 `CLASS_HOURS_PORT`（service 文件里），或者 `fuser -k 8550/tcp` 查是谁占着 |
| 电脑上能开、手机打不开 | ufw 放行了吗？云服务器安全组放行了吗？是不是同一个 WiFi？ |
| 换了服务器/重装系统 | 代码 `git clone` 再 `uv sync`，数据把备份（或 `data/` 目录）拷过去，重装一次服务 |
| 想同时开两个实例 | 用 `CLASS_HOURS_PORT` 分开端口，**数据目录也要分开**（`CLASS_HOURS_DB`），否则会抢同一个 SQLite 文件 |
| `git push` 报 Permission denied | SSH key 没配（`ssh-keygen` + 把公钥加到 GitHub），或者改用 HTTPS 地址 + token |
| `git pull` 说本地有改动 | 服务器上被手改过。先看清楚是什么：`git status`、`git diff`；确认不要了再 `git checkout -- <文件>`（会丢改动） |
| 数据会不会被 git 覆盖 | 不会。`data/` 在 `.gitignore` 里，git 从不跟踪它，`git pull` 只动代码 |
| 那数据怎么丢的 | 三种情况：① 把整个部署包解到服务器目录（包里的 `data/` 会盖掉线上的）；② 手滑跑 `git clean -xfd`（它专删被 ignore 的文件，也就是 data）；③ 硬盘坏又没备份 |

## 十、想在 Mac 上继续开发

改代码在 Mac 上做，改完再同步到服务器，两边共用一份 `data/` 拷来拷去容易乱，
简单点就是：**服务器上跑正式数据，Mac 上跑测试数据**（默认的 `data/app.db` 就是本机的）。

Mac 上启动：

```bash
uv sync
./启动.command
```
