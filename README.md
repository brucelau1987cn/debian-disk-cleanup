# Debian Disk Cleanup

Debian/Ubuntu VPS 磁盘清理脚本。默认只做相对安全的清理；会删日志审计、临时目录、APT lists、Docker 数据的操作都需要你显式加参数。

适合：
- 5G/10G 小硬盘 VPS 抢空间
- 长期运行的 Debian/Ubuntu 服务器
- CI、测试机、临时机器的定期清理

支持：Debian 10/11/12/13，Ubuntu 系列理论兼容。

## 快速使用

先预览，看看会清理什么：

```bash
curl -fsSL https://raw.githubusercontent.com/brucelau1987cn/debian-disk-cleanup/main/debian-disk-cleanup.sh -o debian-disk-cleanup.sh
chmod +x debian-disk-cleanup.sh
sudo ./debian-disk-cleanup.sh --dry-run
```

确认后执行默认安全清理：

```bash
sudo ./debian-disk-cleanup.sh --yes
```

小盘 VPS 强清理：

```bash
sudo ./debian-disk-cleanup.sh --yes \
  --journal-size 50M \
  --clear-login-logs \
  --clear-tmp \
  --clear-apt-lists \
  --remove-unused-swap
```

执行 `--clear-apt-lists` 后，后续安装软件前先运行：

```bash
sudo apt-get update
```

## 一行命令

默认安全清理：

```bash
curl -fsSL https://raw.githubusercontent.com/brucelau1987cn/debian-disk-cleanup/main/debian-disk-cleanup.sh -o debian-disk-cleanup.sh && chmod +x debian-disk-cleanup.sh && sudo ./debian-disk-cleanup.sh --yes
```

预览模式：

```bash
curl -fsSL https://raw.githubusercontent.com/brucelau1987cn/debian-disk-cleanup/main/debian-disk-cleanup.sh -o debian-disk-cleanup.sh && chmod +x debian-disk-cleanup.sh && sudo ./debian-disk-cleanup.sh --dry-run
```

小盘 VPS 强清理：

```bash
curl -fsSL https://raw.githubusercontent.com/brucelau1987cn/debian-disk-cleanup/main/debian-disk-cleanup.sh -o debian-disk-cleanup.sh && chmod +x debian-disk-cleanup.sh && sudo ./debian-disk-cleanup.sh --yes --journal-size 50M --clear-login-logs --clear-tmp --clear-apt-lists --remove-unused-swap
```

## 默认会清理什么

默认模式偏保守，适合直接用于生产 VPS：

- APT 缓存：`apt-get clean`、`autoclean`
- 无用包：`apt-get autoremove --purge`
- systemd journal，默认保留到 `100M`
- `/var/log` 下的旧轮转日志：`.gz`、`.1`、`.2`、`.old`、`.log.*`
- `/var/cache` 下残留的 `.deb` 文件
- APT 二进制缓存：`pkgcache.bin`、`srcpkgcache.bin`
- 旧内核包，保留当前正在运行的内核
- `deborphan` 发现的孤儿包，系统已安装 `deborphan` 时才会执行
- disabled snap revisions，系统已安装 `snap` 时才会执行

默认会保留正在使用的主日志，例如 `auth.log`、`syslog`、`kern.log`、`dpkg.log`。

## 需要显式开启的清理

这些选项更激进，适合磁盘空间非常紧张时使用：

- `--clear-login-logs`：清空 `/var/log/btmp` 和 `/var/log/wtmp`
- `--clear-tmp`：清理 `/tmp` 和 `/var/tmp`
- `--clear-user-caches`：清理 `/root/.cache` 和 `/home/*/.cache`
- `--clear-apt-lists`：清理 `/var/lib/apt/lists` 软件包索引
- `--remove-unused-swap`：删除未启用、未写入 `/etc/fstab` 的 `/swap` 普通文件
- `--prune-docker`：执行 `docker system prune -a`
- `--prune-volumes`：配合 `--prune-docker` 删除未使用的 Docker volumes

`--prune-volumes` 风险最高。数据库、对象存储、应用持久化数据经常放在 Docker volume 里。

## 参数

```text
Usage: sudo ./debian-disk-cleanup.sh [options]

Options:
  -y, --yes                 Skip interactive confirmation.
  -n, --dry-run             Show what would be cleaned without deleting files.
      --journal-size SIZE   Keep systemd journal under SIZE. Default: 100M.
      --prune-docker        Run docker system prune -a.
      --prune-volumes       Include Docker volumes. Requires --prune-docker.
      --clear-login-logs    Truncate /var/log/btmp and /var/log/wtmp.
      --clear-user-caches   Delete /root/.cache and /home/*/.cache contents.
      --clear-tmp           Delete files under /tmp and /var/tmp.
      --clear-apt-lists     Delete /var/lib/apt/lists package indexes.
      --remove-unused-swap  Delete /swap when it is a plain file, inactive, and absent from /etc/fstab.
      --skip-dpkg-repair    Skip automatic 'dpkg --configure -a' preflight repair.
  -h, --help                Show this help.
```

## 常用组合

默认安全清理：

```bash
sudo ./debian-disk-cleanup.sh --yes
```

压缩 journal 到 50M：

```bash
sudo ./debian-disk-cleanup.sh --yes --journal-size 50M
```

清理 Docker 镜像和构建缓存：

```bash
sudo ./debian-disk-cleanup.sh --yes --prune-docker
```

连未使用的 Docker volumes 一起清理：

```bash
sudo ./debian-disk-cleanup.sh --yes --prune-docker --prune-volumes
```

完整激进清理：

```bash
sudo ./debian-disk-cleanup.sh --yes \
  --journal-size 50M \
  --clear-tmp \
  --clear-user-caches \
  --clear-login-logs \
  --clear-apt-lists \
  --remove-unused-swap \
  --prune-docker
```

## 安全设计

脚本内置了几层保护：

- `--dry-run` 预览模式
- root 检查和交互确认
- APT 前置执行 `dpkg --configure -a`，减少上次安装中断带来的报错
- 旧内核清理只处理 `ii` 状态包，并保留当前 `uname -r` 对应内核
- Docker、临时目录、用户缓存、登录记录、APT lists 都由显式参数控制
- `/swap` 只在普通文件、未启用、未写入 `/etc/fstab` 时删除
- 对可能缺失的命令和文件做容错处理

## 本地验证

```bash
bash -n debian-disk-cleanup.sh
shellcheck debian-disk-cleanup.sh
python3 tests/test_static.py
python3 tests/test_behavior.py
```

CI 会运行 Bash 语法检查、ShellCheck 和 Python 测试。

## 注意事项

- 建议先跑 `--dry-run`。
- 生产环境谨慎使用 `--clear-login-logs`，它会清空登录审计记录。
- `--clear-tmp` 会清理临时目录，运行中的程序可能正在使用临时文件。
- `--clear-apt-lists` 会删除软件包索引，后续安装软件前需要执行 `apt-get update`。
- `--prune-volumes` 会删除未使用的 Docker volumes，先确认数据没有放在 volume 里。
- `--remove-unused-swap` 会自动跳过正在使用或写入 `/etc/fstab` 的 swap。

## License

MIT
