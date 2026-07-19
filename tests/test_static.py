import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "debian-disk-cleanup.sh").read_text()


def test_has_strict_mode_and_root_guard():
    assert "set -Eeuo pipefail" in SCRIPT
    assert "require_root" in SCRIPT
    assert "${EUID}" in SCRIPT
    assert "DEBIAN_DISK_CLEANUP_TEST_ALLOW_NON_ROOT" in SCRIPT


def test_destructive_operations_require_flags():
    assert "PRUNE_DOCKER=0" in SCRIPT
    assert "CLEAR_LOGIN_LOGS=0" in SCRIPT
    assert "CLEAR_USER_CACHES=0" in SCRIPT
    assert "CLEAR_TMP=0" in SCRIPT
    assert "--prune-docker" in SCRIPT
    assert "--clear-login-logs" in SCRIPT
    assert "--clear-user-caches" in SCRIPT
    assert "--clear-tmp" in SCRIPT
    assert "CLEAR_APT_LISTS=0" in SCRIPT
    assert "REMOVE_UNUSED_SWAP=0" in SCRIPT
    assert "--clear-apt-lists" in SCRIPT
    assert "--remove-unused-swap" in SCRIPT
    assert "CLEAR_PYTHON_CACHES=0" in SCRIPT
    assert "CLEAR_PLAYWRIGHT_BROWSERS=0" in SCRIPT
    assert "PURGE_DEBORPHANS=0" in SCRIPT
    assert "--clear-python-caches" in SCRIPT
    assert "--clear-playwright-browsers" in SCRIPT
    assert "--purge-deborphans" in SCRIPT
    assert "AUTOREMOVE_PACKAGES=0" in SCRIPT
    assert "--autoremove" in SCRIPT


def test_no_broken_true_syntax_from_original_script():
    assert "2>/dev/null  true" not in SCRIPT
    assert "2>/dev/null true" not in SCRIPT


def test_home_cache_glob_is_not_single_quoted_in_rm_rf():
    assert 'rm -rf "$user_home/.cache/*"' not in SCRIPT


def test_docker_volumes_are_separate_flag():
    prune_without_volumes = re.search(r"docker system prune -a -f", SCRIPT)
    prune_with_volumes = re.search(r"docker system prune -a --volumes -f", SCRIPT)
    assert prune_without_volumes
    assert prune_with_volumes


def test_default_does_not_truncate_active_main_logs():
    forbidden = [
        'truncate -s 0 /var/log/syslog',
        'truncate -s 0 /var/log/auth.log',
        'truncate -s 0 /var/log/kern.log',
        'truncate -s 0 /var/log/dpkg.log',
    ]
    for text in forbidden:
        assert text not in SCRIPT


def test_snap_pipeline_is_tolerant_under_pipefail():
    assert "snap list --all 2>/dev/null | awk '/disabled/{print $1, $3}' || true" in SCRIPT


def test_default_does_not_manually_purge_kernel_packages():
    assert "kernel_cleanup()" not in SCRIPT
    assert "apt-get purge -y \"$kernel\"" not in SCRIPT


def test_dpkg_preflight_exists_before_apt_cleanup_call():
    assert "apt_preflight()" in SCRIPT
    assert "run dpkg --configure -a" in SCRIPT
    assert "REPAIR_DPKG=0" in SCRIPT
    assert "--repair-dpkg" in SCRIPT
    assert "--skip-dpkg-repair" in SCRIPT
    assert SCRIPT.index("apt_preflight") < SCRIPT.index("apt_cleanup")


def test_unused_swap_cleanup_has_safety_guards():
    assert "unused_swap_cleanup()" in SCRIPT
    assert 'local swap_file="/swap"' in SCRIPT
    assert "swapon --show=NAME --noheadings" in SCRIPT
    assert "grep -Fxq \"$swap_file\"" in SCRIPT
    assert '$1 == target && $3 == "swap"' in SCRIPT


def test_directory_cleanup_uses_mount_aware_helper():
    assert "safe_delete_tree_contents()" in SCRIPT
    assert "findmnt -ln -R -o TARGET" in SCRIPT
    assert "safe_delete_tree_contents /tmp /var/tmp" in SCRIPT
    assert 'safe_delete_tree_contents "${cache_dirs[@]}"' in SCRIPT
    assert "-exec rm -rf" not in SCRIPT


def test_default_log_cleanup_requires_an_explicit_flag():
    assert "--clear-old-logs" in SCRIPT
    assert "CLEAR_OLD_LOGS=0" in SCRIPT
    assert "-mtime" in SCRIPT
    assert "*.log.*" not in SCRIPT
    assert "Preserving mounted log path" in SCRIPT
    assert "Unable to inspect mounts below /var/log" in SCRIPT


def test_apt_list_cleanup_warns_to_run_update_later():
    assert "safe_delete_tree_contents /var/lib/apt/lists" in SCRIPT
    assert "run mkdir -p /var/lib/apt/lists/partial" in SCRIPT
    assert "rm -rf /var/lib/apt/lists" not in SCRIPT
    assert "Run apt-get update before installing packages later" in SCRIPT
