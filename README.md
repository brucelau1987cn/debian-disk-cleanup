# Debian Disk Cleanup

Debian/Ubuntu VPS 磁盘清理脚本。默认只做相对安全的清理；旧日志、临时目录、开发工具缓存、APT lists、Docker 数据等操作都需要显式加参数。

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

5G/10G 小盘 VPS 空间不足时：

```bash
sudo ./debian-disk-cleanup.sh --yes \
  --journal-size 50M \
  --clear-old-logs \
  --clear-tmp \
  --clear-apt-lists \
  --clear-python-caches
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

小盘 VPS 空间不足：

```bash
curl -fsSL https://raw.githubusercontent.com/brucelau1987cn/debian-disk-cleanup/main/debian-disk-cleanup.sh -o debian-disk-cleanup.sh && chmod +x debian-disk-cleanup.sh && sudo ./debian-disk-cleanup.sh --yes --journal-size 50M --clear-old-logs --clear-tmp --clear-apt-lists --clear-python-caches
```

## 默认会清理什么

默认模式偏保守，适合直接用于生产 VPS：

- APT 缓存：`apt-get clean`、`autoclean`
- systemd journal，默认保留到 `100M`
- APT 二进制缓存：`pkgcache.bin`、`srcpkgcache.bin`
- disabled snap revisions，系统已安装 `snap` 时才会执行

默认会保留正在使用的主日志，例如 `auth.log`、`syslog`、`kern.log`、`dpkg.log`。

## 需要显式开启的清理

这些选项更激进，适合磁盘空间非常紧张时使用：

- `--clear-login-logs`：清空 `/var/log/btmp` 和 `/var/log/wtmp`
- `--clear-tmp`：清理 `/tmp` 和 `/var/tmp`
- `--clear-user-caches`：清理 `/root/.cache` 和 `/home/*/.cache`
- `--clear-apt-lists`：清理 `/var/lib/apt/lists` 软件包索引
- `--remove-unused-swap`：删除未启用、未写入 `/etc/fstab` 的 `/swap` 普通文件
- `--clear-old-logs`：清理 7 天前的非审计轮转日志，保留 audit、wtmp 和 btmp
- `--clear-python-caches`：为运行脚本的 root 当前环境执行 `uv cache prune` 和 `python3 -m pip cache purge`
- `--clear-playwright-browsers`：执行 `playwright uninstall --all`，清除 root 当前环境登记的 Playwright 浏览器
- `--purge-deborphans`：清理 `deborphan` 报告的孤儿包
- `--autoremove`：执行 `apt-get autoremove --purge -y`
- `--prune-docker`：执行 `docker system prune -a`
- `--prune-volumes`：配合 `--prune-docker` 删除未使用的 Docker volumes

`--prune-volumes` 风险最高。数据库、对象存储、应用持久化数据经常放在 Docker volume 里。

`--clear-playwright-browsers` 清理后，现有自动化项目可能需要重新执行 `playwright install chromium`。`--purge-deborphans` 可能影响依赖声明不完整的手工部署程序，生产机应谨慎使用。

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
      --clear-old-logs      Delete non-audit rotated logs older than 7 days.
      --clear-python-caches Prune uv cache and purge pip cache.
      --clear-playwright-browsers
                            Uninstall browsers tracked by all Playwright installations for the current user.
      --purge-deborphans    Purge packages reported by deborphan.
      --autoremove          Run 'apt-get autoremove --purge -y'.
      --repair-dpkg         Run 'dpkg --configure -a' before APT cleanup.
      --skip-dpkg-repair    Deprecated compatibility option; repair is skipped by default.
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

小盘 VPS 推荐清理：

```bash
sudo ./debian-disk-cleanup.sh --yes \
  --journal-size 50M \
  --clear-tmp \
  --clear-old-logs \
  --clear-apt-lists \
  --clear-python-caches
```

若 Playwright 浏览器缓存占用很大，并且可以接受后续重新下载浏览器，再单独运行：

```bash
sudo ./debian-disk-cleanup.sh --yes --clear-playwright-browsers
```

725M-1G 内存的小 VPS 建议保留 swap。`swapoff -a && swapon -a` 和 `vm.drop_caches=3` 不释放磁盘空间，本工具不会执行这两项操作。

如果清完缓存后空间仍不足，可先预览 APT 自动移除范围：

```bash
sudo ./debian-disk-cleanup.sh --dry-run --autoremove
```

确认候选包可以删除后，再改用 `--yes --autoremove` 执行。

## 安全设计

脚本内置了几层保护：

- `--dry-run` 预览模式
- root 检查和交互确认
- 空间不足时默认先释放缓存；只有显式使用 `--repair-dpkg` 才在 APT 清理前运行 `dpkg --configure -a`
- 默认不删除软件包或内核；只有显式使用 `--autoremove` 才执行 APT 自动移除
- Docker、旧日志、临时目录、用户缓存、开发工具缓存、登录记录、APT lists 都由显式参数控制
- `/tmp`、`/var/tmp` 和用户缓存清理不跨越文件系统挂载点
- `/swap` 只在普通文件、未启用、未写入 `/etc/fstab` 时删除；低内存 VPS 不建议删除
- 对可能缺失的命令和文件做容错处理

## 本地验证

```bash
bash -n debian-disk-cleanup.sh
shellcheck debian-disk-cleanup.sh
python3 -m pytest -q
```

CI 会运行 Bash 语法检查、ShellCheck 和 Python 测试。

## 注意事项

- 建议先跑 `--dry-run`。
- 生产环境谨慎使用 `--clear-login-logs`，它会清空登录审计记录。
- `--clear-tmp` 会清理临时目录，运行中的程序可能正在使用临时文件。
- `--clear-apt-lists` 会删除软件包索引，后续安装软件前需要执行 `apt-get update`。
- `--prune-volumes` 会删除未使用的 Docker volumes，先确认数据没有放在 volume 里。
- `--remove-unused-swap` 会自动跳过正在使用或写入 `/etc/fstab` 的 swap。
- `--clear-python-caches` 会让后续 Python 包安装重新下载或构建依赖。
- `--clear-playwright-browsers` 会让后续 Playwright 任务重新安装所需浏览器。

## License

MIT
