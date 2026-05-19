# Debian Disk Cleanup

Debian 10/11/12 一键磁盘清理脚本，适合 VPS、长期运行的 Debian 服务器、CI/测试机做安全清理。

## 功能

默认执行相对安全的清理：

- 清理 APT 缓存：`apt-get clean`、`autoclean`
- 清理无用包：`apt-get autoremove --purge`
- systemd journal 限制到指定大小，默认 `100M`
- 删除 `/var/log` 下的旧轮转日志：`.gz`、`.1`、`.2`、`.old`、`.log.*`
- 删除 `/var/cache` 下残留的 `.deb` 文件
- 清理旧内核包，保留当前正在运行的内核
- 可选清理 `deborphan` 发现的孤儿包
- 可选清理 disabled snap revisions

高风险清理需要显式参数开启：

- `--clear-login-logs`：清空 `/var/log/btmp` 和 `/var/log/wtmp`
- `--clear-tmp`：清理 `/tmp` 和 `/var/tmp`
- `--clear-user-caches`：清理 `/root/.cache` 和 `/home/*/.cache`
- `--prune-docker`：执行 `docker system prune -a`
- `--prune-volumes`：连 Docker volumes 一起清理

## 快速使用

```bash
curl -fsSL https://raw.githubusercontent.com/brucelau1987cn/debian-disk-cleanup/main/debian-disk-cleanup.sh -o debian-disk-cleanup.sh
chmod +x debian-disk-cleanup.sh
sudo ./debian-disk-cleanup.sh --dry-run
sudo ./debian-disk-cleanup.sh --yes
```

完整清理示例：

```bash
sudo ./debian-disk-cleanup.sh --yes \
  --journal-size 100M \
  --clear-tmp \
  --clear-user-caches \
  --clear-login-logs \
  --prune-docker
```

带 Docker volumes 的强清理：

```bash
sudo ./debian-disk-cleanup.sh --yes --prune-volumes
```

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
  -h, --help                Show this help.
```

## 与原始版本相比的安全修正

- 修复 `journalctl --vacuum-size=100M 2>/dev/null true` 这类语法问题，统一使用 `|| true`。
- 使用 `apt-get`，更适合脚本环境。
- 添加 root 检查和交互确认。
- 添加 `--dry-run` 预览模式。
- Docker prune、用户缓存、登录记录、临时目录清理改为显式开启。
- 修复 `/home/*/.cache/*` 被引号包住导致通配符失效的问题。
- 旧内核清理使用 `dpkg-query`，保留当前 `uname -r` 对应内核。
- 避免默认清空 `auth.log`、`syslog`、`dpkg.log` 等正在使用的主日志文件。
- 对可能不存在的命令和文件做容错处理。

## 验证

本仓库包含基础 CI，会执行：

- `bash -n debian-disk-cleanup.sh`
- ShellCheck 静态检查
- Python 静态规则测试

本地验证：

```bash
bash -n debian-disk-cleanup.sh
shellcheck debian-disk-cleanup.sh
python3 tests/test_static.py
```

## 注意事项

- 请先执行 `--dry-run` 查看将要清理的范围。
- `--prune-volumes` 会删除未使用的 Docker volumes，数据库、对象存储、应用数据有可能放在 volume 中。
- `--clear-login-logs` 会清空登录审计记录，生产环境建议保留。
- `--clear-tmp` 会删除临时目录内容，运行中的程序如果依赖临时文件可能受影响。

## License

MIT
