import os
import pathlib
import subprocess
import textwrap

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "debian-disk-cleanup.sh"


def make_fakebin(tmp_path, commands):
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    log = tmp_path / "commands.log"
    for name, body in commands.items():
        path = fakebin / name
        path.write_text(textwrap.dedent(body).lstrip())
        path.chmod(0o755)
    return fakebin, log


def run_script(args, tmp_path, commands=None, input_text=None):
    commands = commands or {}
    fakebin, log = make_fakebin(tmp_path, commands)
    env = os.environ.copy()
    env["PATH"] = f"{fakebin}:{env['PATH']}"
    env["COMMAND_LOG"] = str(log)
    env["DEBIAN_DISK_CLEANUP_TEST_ALLOW_NON_ROOT"] = "1"
    result = subprocess.run(
        ["bash", str(SCRIPT), *args],
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=20,
    )
    return result, log.read_text() if log.exists() else ""


BASE_COMMANDS = {
    "df": """
        #!/usr/bin/env bash
        echo "df $*" >> "$COMMAND_LOG"
        echo "Filesystem Size Used Avail Use% Mounted on"
        echo "/dev/fake 10G 5G 5G 50% /"
    """,
    "apt-get": """
        #!/usr/bin/env bash
        echo "apt-get $*" >> "$COMMAND_LOG"
        exit 0
    """,
    "journalctl": """
        #!/usr/bin/env bash
        echo "journalctl $*" >> "$COMMAND_LOG"
        exit 0
    """,
    "find": """
        #!/usr/bin/env bash
        echo "find $*" >> "$COMMAND_LOG"
        exit 0
    """,
    "uname": """
        #!/usr/bin/env bash
        if [[ "$1" == "-r" ]]; then echo "6.1.0-current-amd64"; else /usr/bin/uname "$@"; fi
    """,
    "dpkg-query": """
        #!/usr/bin/env bash
        echo "ii  linux-image-6.1.0-old-amd64"
        echo "ii  linux-image-6.1.0-current-amd64"
    """,
    "deborphan": """
        #!/usr/bin/env bash
        echo "orphan-lib"
    """,
    "docker": """
        #!/usr/bin/env bash
        echo "docker $*" >> "$COMMAND_LOG"
        exit 0
    """,
    "snap": """
        #!/usr/bin/env bash
        echo "snap $*" >> "$COMMAND_LOG"
        if [[ "$1" == "list" ]]; then
          echo "Name Version Rev Tracking Publisher Notes"
          echo "core 1.0 1 latest/stable canonical disabled"
        fi
        exit 0
    """,
}


def test_dry_run_safe_defaults_do_not_execute_destructive_commands(tmp_path):
    result, log = run_script(["--dry-run"], tmp_path, BASE_COMMANDS)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "[DRY-RUN] apt-get clean" in result.stdout
    assert "[DRY-RUN] apt-get purge -y linux-image-6.1.0-old-amd64" in result.stdout
    assert "[DRY-RUN] apt-get purge -y linux-image-6.1.0-current-amd64" not in result.stdout
    assert "docker system prune" not in result.stdout
    assert "Skipping /tmp and /var/tmp cleanup" in result.stdout
    assert "Skipping user cache cleanup" in result.stdout
    assert "apt-get clean" not in log
    assert "find /tmp /var/tmp" not in log


def test_explicit_destructive_flags_are_visible_in_dry_run(tmp_path):
    result, _ = run_script(
        [
            "--dry-run",
            "--clear-tmp",
            "--clear-user-caches",
            "--clear-login-logs",
            "--prune-volumes",
        ],
        tmp_path,
        BASE_COMMANDS,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "find /tmp /var/tmp" in result.stdout
    assert "bash -c" in result.stdout and "/root/.cache" in result.stdout
    assert "docker system prune -a --volumes -f" in result.stdout


def test_cancel_confirmation_exits_before_cleanup(tmp_path):
    result, log = run_script([], tmp_path, BASE_COMMANDS, input_text="n\n")
    assert result.returncode == 0
    assert "Cancelled" in result.stdout
    assert "apt-get" not in log


def test_unknown_argument_returns_error(tmp_path):
    result, _ = run_script(["--bad-option"], tmp_path, BASE_COMMANDS)
    assert result.returncode == 2
    assert "Unknown option" in result.stderr


def test_snap_list_failure_does_not_abort_cleanup(tmp_path):
    commands = dict(BASE_COMMANDS)
    commands["snap"] = """
        #!/usr/bin/env bash
        echo "snap $*" >> "$COMMAND_LOG"
        exit 1
    """
    result, _ = run_script(["--dry-run"], tmp_path, commands)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Disk cleanup finished" in result.stdout


def test_kernel_cleanup_ignores_removed_config_only_packages(tmp_path):
    commands = dict(BASE_COMMANDS)
    commands["dpkg-query"] = """
        #!/usr/bin/env bash
        echo "rc  linux-image-6.1.0-18-cloud-amd64-unsigned"
        echo "ii  linux-image-6.1.0-18-cloud-amd64"
        echo "ii  linux-image-6.1.0-current-amd64"
    """
    result, _ = run_script(["--dry-run"], tmp_path, commands)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "[DRY-RUN] apt-get purge -y linux-image-6.1.0-18-cloud-amd64" in result.stdout
    assert "[DRY-RUN] apt-get purge -y linux-image-6.1.0-18-cloud-amd64-unsigned" not in result.stdout
