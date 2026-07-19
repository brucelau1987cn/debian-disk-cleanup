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


def run_script(args, tmp_path, commands=None, input_text=None, env_overrides=None):
    commands = commands or {}
    fakebin, log = make_fakebin(tmp_path, commands)
    env = os.environ.copy()
    env["PATH"] = f"{fakebin}:{env['PATH']}"
    env["COMMAND_LOG"] = str(log)
    env["DEBIAN_DISK_CLEANUP_TEST_ALLOW_NON_ROOT"] = "1"
    if env_overrides:
        env.update(env_overrides)
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
    "dpkg": """
        #!/usr/bin/env bash
        echo "dpkg DEBIAN_FRONTEND=${DEBIAN_FRONTEND:-} $*" >> "$COMMAND_LOG"
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
    "findmnt": """
        #!/usr/bin/env bash
        echo "findmnt $*" >> "$COMMAND_LOG"
        exit 0
    """,
    "rm": """
        #!/usr/bin/env bash
        echo "rm $*" >> "$COMMAND_LOG"
        exit 0
    """,
    "swapon": """
        #!/usr/bin/env bash
        echo "swapon $*" >> "$COMMAND_LOG"
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
    "uv": """
        #!/usr/bin/env bash
        echo "uv $*" >> "$COMMAND_LOG"
        exit 0
    """,
    "python3": """
        #!/usr/bin/env bash
        echo "python3 $*" >> "$COMMAND_LOG"
        exit 0
    """,
    "playwright": """
        #!/usr/bin/env bash
        echo "playwright $*" >> "$COMMAND_LOG"
        exit 0
    """,
}


def test_dry_run_safe_defaults_do_not_execute_destructive_commands(tmp_path):
    result, log = run_script(["--dry-run"], tmp_path, BASE_COMMANDS)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "[DRY-RUN] apt-get clean" in result.stdout
    assert "dpkg --configure -a" not in result.stdout
    assert "apt-get purge -y linux-image" not in result.stdout
    assert "apt-get purge -y orphan-lib" not in result.stdout
    assert "apt-get autoremove" not in result.stdout
    assert "uv cache" not in result.stdout
    assert "playwright uninstall" not in result.stdout
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
            "--clear-apt-lists",
            "--remove-unused-swap",
            "--prune-docker",
            "--prune-volumes",
            "--clear-python-caches",
            "--clear-playwright-browsers",
            "--purge-deborphans",
            "--autoremove",
        ],
        tmp_path,
        BASE_COMMANDS,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "find /tmp /var/tmp" in result.stdout
    assert "/root/.cache" in result.stdout
    assert "find /var/lib/apt/lists" in result.stdout
    assert "mkdir -p /var/lib/apt/lists/partial" in result.stdout
    assert "docker system prune -a --volumes -f" in result.stdout
    assert "uv cache prune" in result.stdout
    assert "python3 -m pip cache purge" in result.stdout
    assert "playwright uninstall --all" in result.stdout
    assert "apt-get purge -y orphan-lib" in result.stdout
    assert "apt-get autoremove --purge -y" in result.stdout


def test_prune_volumes_requires_prune_docker(tmp_path):
    result, _ = run_script(["--dry-run", "--prune-volumes"], tmp_path, BASE_COMMANDS)
    assert result.returncode == 2
    assert "requires --prune-docker" in result.stderr


def test_apt_binary_caches_are_safe_default_cleanup(tmp_path):
    result, _ = run_script(["--dry-run"], tmp_path, BASE_COMMANDS)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "rm -f /var/cache/apt/pkgcache.bin" in result.stdout
    assert "rm -f /var/cache/apt/srcpkgcache.bin" in result.stdout
    assert "find /var/cache" not in result.stdout
    assert "/var/lib/apt/lists" not in result.stdout


def test_clear_apt_lists_requires_explicit_flag(tmp_path):
    result, _ = run_script(["--dry-run", "--clear-apt-lists"], tmp_path, BASE_COMMANDS)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "/var/lib/apt/lists" in result.stdout


def test_remove_unused_swap_requires_explicit_flag_and_safety_checks(tmp_path):
    swap_file = tmp_path / "swap"
    swap_file.write_bytes(b"0")
    result, _ = run_script(
        ["--dry-run", "--remove-unused-swap"],
        tmp_path,
        BASE_COMMANDS,
        env_overrides={"DEBIAN_DISK_CLEANUP_TEST_SWAP_FILE": str(swap_file)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"[DRY-RUN] rm -f {swap_file}" in result.stdout


def test_active_swap_file_is_not_removed(tmp_path):
    commands = dict(BASE_COMMANDS)
    swap_file = tmp_path / "swap"
    swap_file.write_bytes(b"0")
    commands["swapon"] = """
        #!/usr/bin/env bash
        echo "swapon $*" >> "$COMMAND_LOG"
        echo "$DEBIAN_DISK_CLEANUP_TEST_SWAP_FILE"
        exit 0
    """
    result, _ = run_script(
        ["--dry-run", "--remove-unused-swap"],
        tmp_path,
        commands,
        env_overrides={"DEBIAN_DISK_CLEANUP_TEST_SWAP_FILE": str(swap_file)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"[DRY-RUN] rm -f {swap_file}" not in result.stdout
    assert "is active. Skipping removal" in result.stdout


def test_fstab_swap_file_is_not_removed(tmp_path):
    swap_file = tmp_path / "swap"
    swap_file.write_bytes(b"0")
    fstab = tmp_path / "fstab"
    fstab.write_text(f"{swap_file} none swap sw 0 0\n")
    result, _ = run_script(
        ["--dry-run", "--remove-unused-swap"],
        tmp_path,
        BASE_COMMANDS,
        env_overrides={
            "DEBIAN_DISK_CLEANUP_TEST_SWAP_FILE": str(swap_file),
            "DEBIAN_DISK_CLEANUP_TEST_FSTAB": str(fstab),
        },
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"[DRY-RUN] rm -f {swap_file}" not in result.stdout
    assert "referenced in" in result.stdout


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


def test_default_never_manually_purges_kernel_packages(tmp_path):
    commands = dict(BASE_COMMANDS)
    commands["dpkg-query"] = """
        #!/usr/bin/env bash
        echo "rc  linux-image-6.1.0-18-cloud-amd64-unsigned"
        echo "ii  linux-image-6.1.0-18-cloud-amd64"
        echo "ii  linux-image-6.1.0-current-amd64"
    """
    result, _ = run_script(["--dry-run"], tmp_path, commands)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "apt-get purge -y linux-image" not in result.stdout


def test_explicit_dpkg_repair_runs_before_apt_cleanup(tmp_path):
    result, log = run_script(["--yes", "--repair-dpkg"], tmp_path, BASE_COMMANDS)
    assert result.returncode == 0, result.stderr + result.stdout
    dpkg_index = log.index("dpkg DEBIAN_FRONTEND=noninteractive --configure -a")
    apt_index = log.index("apt-get clean")
    assert dpkg_index < apt_index


def test_dpkg_repair_is_skipped_by_default(tmp_path):
    result, log = run_script(["--yes"], tmp_path, BASE_COMMANDS)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "dpkg --configure -a" not in log
    assert "Skipping dpkg repair" in result.stdout


def test_python_cache_cleanup_executes_only_when_requested(tmp_path):
    result, log = run_script(["--yes", "--clear-python-caches"], tmp_path, BASE_COMMANDS)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "uv cache prune" in log
    assert "python3 -m pip cache purge" in log


def test_playwright_cleanup_executes_only_when_requested(tmp_path):
    result, log = run_script(["--yes", "--clear-playwright-browsers"], tmp_path, BASE_COMMANDS)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "playwright uninstall --all" in log


def test_tmp_cleanup_skips_deletion_when_mount_inspection_fails(tmp_path):
    commands = dict(BASE_COMMANDS)
    commands["findmnt"] = """
        #!/usr/bin/env bash
        echo "findmnt $*" >> "$COMMAND_LOG"
        exit 1
    """
    result, log = run_script(["--yes", "--clear-tmp"], tmp_path, commands)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Unable to inspect mounts below /tmp" in result.stdout
    assert "find /tmp /var/tmp" not in log


def test_tmp_cleanup_excludes_mount_paths_with_spaces(tmp_path):
    commands = dict(BASE_COMMANDS)
    commands["findmnt"] = """
        #!/usr/bin/env bash
        echo "findmnt $*" >> "$COMMAND_LOG"
        case "$*" in
          *"--target /tmp"*)
            echo "/tmp"
            echo "/tmp/mounted space"
            ;;
          *"--target /var/tmp"*) echo "/var/tmp" ;;
        esac
        exit 0
    """
    result, log = run_script(["--yes", "--clear-tmp"], tmp_path, commands)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Preserving mounted path /tmp/mounted space" in result.stdout
    assert "! -path /tmp/mounted space ! -path /tmp/mounted space/*" in log
