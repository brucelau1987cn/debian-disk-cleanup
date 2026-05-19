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


def test_kernel_cleanup_only_targets_installed_packages():
    assert "${db:Status-Abbrev} ${Package}" in SCRIPT
    assert "awk '$1 ~ /^ii/ {print $2}'" in SCRIPT


def test_dpkg_preflight_exists_before_apt_cleanup_call():
    assert "apt_preflight()" in SCRIPT
    assert "run dpkg --configure -a" in SCRIPT
    assert "--skip-dpkg-repair" in SCRIPT
    assert SCRIPT.index("apt_preflight") < SCRIPT.index("apt_cleanup")
