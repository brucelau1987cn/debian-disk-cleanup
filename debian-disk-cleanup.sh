#!/usr/bin/env bash
# Debian disk cleanup script.
# Supports Debian 10/11/12/13. Run as root.

set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_NAME="$(basename "$0")"
JOURNAL_LIMIT="${JOURNAL_LIMIT:-100M}"
ASSUME_YES=0
DRY_RUN=0
PRUNE_DOCKER=0
PRUNE_DOCKER_VOLUMES=0
CLEAR_LOGIN_LOGS=0
CLEAR_USER_CACHES=0
CLEAR_TMP=0
REPAIR_DPKG=0
CLEAR_APT_LISTS=0
REMOVE_UNUSED_SWAP=0
CLEAR_OLD_LOGS=0
CLEAR_PYTHON_CACHES=0
CLEAR_PLAYWRIGHT_BROWSERS=0
PURGE_DEBORPHANS=0
AUTOREMOVE_PACKAGES=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
print_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

usage() {
  cat <<'USAGE'
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

Safe defaults clean APT cache, Debian package cache indexes, disabled snap
revisions, and systemd journal retention. Destructive and
development-tool caches require explicit flags.
USAGE
}

run() {
  if (( DRY_RUN )); then
    printf '[DRY-RUN]'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

safe_delete_tree_contents() {
  local root mount_path mount_output
  local -a roots=()
  local -a find_args=()

  if ! command -v findmnt >/dev/null 2>&1; then
    print_warn "findmnt not found; skipping directory cleanup to avoid crossing mount points."
    return 0
  fi

  for root in "$@"; do
    [[ -d "$root" ]] && roots+=("$root")
  done
  (( ${#roots[@]} > 0 )) || return 0

  find_args=(find "${roots[@]}" -xdev -depth -mindepth 1)
  for root in "${roots[@]}"; do
    if ! mount_output="$(findmnt -ln -R -o TARGET --target "$root" 2>/dev/null)"; then
      print_warn "Unable to inspect mounts below ${root}; skipping directory cleanup."
      return 0
    fi
    while IFS= read -r mount_path; do
      [[ -n "$mount_path" ]] || continue
      [[ "$mount_path" == "$root" ]] && continue
      [[ "$mount_path" == "$root/"* ]] || continue
      print_warn "Preserving mounted path ${mount_path}."
      find_args+=( ! -path "$mount_path" ! -path "$mount_path/*" )
    done <<< "$mount_output"
  done
  find_args+=(-delete)

  run "${find_args[@]}" || \
    print_warn "Some paths were skipped because they are mounted, protected, or in use."
}

require_root() {
  if [[ "${EUID}" -ne 0 && "${DEBIAN_DISK_CLEANUP_TEST_ALLOW_NON_ROOT:-0}" != "1" ]]; then
    print_error "Please run as root: sudo ./${SCRIPT_NAME}"
    exit 1
  fi
}

confirm() {
  (( ASSUME_YES || DRY_RUN )) && return 0
  echo "This will clean system caches and removable logs on this Debian host."
  read -r -p "Continue? [y/N] " answer
  case "${answer}" in
    y|Y|yes|YES) return 0 ;;
    *) print_warn "Cancelled."; exit 0 ;;
  esac
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -y|--yes) ASSUME_YES=1; shift ;;
      -n|--dry-run) DRY_RUN=1; shift ;;
      --journal-size)
        [[ $# -ge 2 ]] || { print_error "--journal-size requires a value"; exit 2; }
        JOURNAL_LIMIT="$2"; shift 2 ;;
      --prune-docker) PRUNE_DOCKER=1; shift ;;
      --prune-volumes) PRUNE_DOCKER_VOLUMES=1; shift ;;
      --clear-login-logs) CLEAR_LOGIN_LOGS=1; shift ;;
      --clear-user-caches) CLEAR_USER_CACHES=1; shift ;;
      --clear-tmp) CLEAR_TMP=1; shift ;;
      --clear-apt-lists) CLEAR_APT_LISTS=1; shift ;;
      --remove-unused-swap) REMOVE_UNUSED_SWAP=1; shift ;;
      --clear-old-logs) CLEAR_OLD_LOGS=1; shift ;;
      --clear-python-caches) CLEAR_PYTHON_CACHES=1; shift ;;
      --clear-playwright-browsers) CLEAR_PLAYWRIGHT_BROWSERS=1; shift ;;
      --purge-deborphans) PURGE_DEBORPHANS=1; shift ;;
      --autoremove) AUTOREMOVE_PACKAGES=1; shift ;;
      --repair-dpkg) REPAIR_DPKG=1; shift ;;
      --skip-dpkg-repair) REPAIR_DPKG=0; shift ;;
      -h|--help) usage; exit 0 ;;
      *) print_error "Unknown option: $1"; usage; exit 2 ;;
    esac
  done
}

validate_args() {
  if (( PRUNE_DOCKER_VOLUMES && ! PRUNE_DOCKER )); then
    print_error "--prune-volumes requires --prune-docker"
    exit 2
  fi
}

show_disk() {
  df -h /
}

apt_preflight() {
  if ! (( REPAIR_DPKG )); then
    print_warn "Skipping dpkg repair. Use --repair-dpkg after freeing space if package configuration is incomplete."
    return 0
  fi

  print_info "Checking dpkg package database state..."
  export DEBIAN_FRONTEND=noninteractive
  run dpkg --configure -a
}

apt_cleanup() {
  print_info "Cleaning APT cache and unused packages..."
  export DEBIAN_FRONTEND=noninteractive
  run apt-get clean
  run apt-get autoclean
  if (( AUTOREMOVE_PACKAGES )); then
    run apt-get autoremove --purge -y
  else
    print_warn "Skipping APT autoremove. Use --autoremove to enable."
  fi
}

journal_cleanup() {
  if command -v journalctl >/dev/null 2>&1; then
    print_info "Vacuuming systemd journal to ${JOURNAL_LIMIT}..."
    run journalctl "--vacuum-size=${JOURNAL_LIMIT}" || true
  else
    print_warn "journalctl not found, skipping journal cleanup."
  fi
}

log_cleanup() {
  local mount_path mount_output
  local -a log_find_args=()

  if (( CLEAR_LOGIN_LOGS )); then
    for logfile in /var/log/btmp /var/log/wtmp; do
      if [[ -f "$logfile" ]]; then
        print_warn "Truncating ${logfile}..."
        run truncate -s 0 "$logfile"
      fi
    done
  fi

  if (( CLEAR_OLD_LOGS )); then
    if ! command -v findmnt >/dev/null 2>&1; then
      print_warn "findmnt not found; skipping rotated log cleanup to avoid crossing mount points."
      return 0
    fi
    if ! mount_output="$(findmnt -ln -R -o TARGET --target /var/log 2>/dev/null)"; then
      print_warn "Unable to inspect mounts below /var/log; skipping rotated log cleanup."
      return 0
    fi

    print_warn "Cleaning non-audit rotated logs older than 7 days under /var/log..."
    log_find_args=(find /var/log -xdev -type f -mtime +7 \( \
      -name '*.gz' -o \
      -name '*.xz' -o \
      -name '*.zst' -o \
      -regex '.*\.[0-9]+' \
    \) ! -path '/var/log/audit/*' ! -name 'wtmp*' ! -name 'btmp*')
    while IFS= read -r mount_path; do
      [[ -n "$mount_path" ]] || continue
      [[ "$mount_path" == "/var/log" ]] && continue
      [[ "$mount_path" == "/var/log/"* ]] || continue
      print_warn "Preserving mounted log path ${mount_path}."
      log_find_args+=( ! -path "$mount_path" ! -path "$mount_path/*" )
    done <<< "$mount_output"
    log_find_args+=(-delete)
    run "${log_find_args[@]}"
  else
    print_warn "Skipping rotated log cleanup. Use --clear-old-logs to enable."
  fi
}

cache_cleanup() {
  print_info "Cleaning APT binary cache indexes..."
  for cache_file in /var/cache/apt/pkgcache.bin /var/cache/apt/srcpkgcache.bin; do
    if [[ -f "$cache_file" ]]; then
      run rm -f "$cache_file"
    fi
  done

  if (( CLEAR_APT_LISTS )); then
    print_warn "Cleaning APT package indexes under /var/lib/apt/lists. Run apt-get update before installing packages later."
    safe_delete_tree_contents /var/lib/apt/lists
    run mkdir -p /var/lib/apt/lists/partial
  fi
}

unused_swap_cleanup() {
  if ! (( REMOVE_UNUSED_SWAP )); then
    return 0
  fi

  local swap_file="/swap"
  local fstab_file="/etc/fstab"
  if [[ "${DEBIAN_DISK_CLEANUP_TEST_ALLOW_NON_ROOT:-0}" == "1" ]]; then
    swap_file="${DEBIAN_DISK_CLEANUP_TEST_SWAP_FILE:-$swap_file}"
    fstab_file="${DEBIAN_DISK_CLEANUP_TEST_FSTAB:-$fstab_file}"
  fi
  if [[ ! -f "$swap_file" ]]; then
    print_info "No ${swap_file} file found."
    return 0
  fi

  if swapon --show=NAME --noheadings 2>/dev/null | grep -Fxq "$swap_file"; then
    print_warn "${swap_file} is active. Skipping removal."
    return 0
  fi

  if awk -v target="$swap_file" '
    /^[[:space:]]*#/ { next }
    NF >= 3 && $1 == target && $3 == "swap" { found=1 }
    END { exit !found }
  ' "$fstab_file" 2>/dev/null; then
    print_warn "${swap_file} is referenced in ${fstab_file}. Skipping removal."
    return 0
  fi

  print_warn "Removing inactive ${swap_file} file..."
  run rm -f "$swap_file"
}

tmp_cleanup() {
  if (( CLEAR_TMP )); then
    print_info "Cleaning temporary directories..."
    safe_delete_tree_contents /tmp /var/tmp
  else
    print_warn "Skipping /tmp and /var/tmp cleanup. Use --clear-tmp to enable."
  fi
}

orphan_cleanup() {
  if ! (( PURGE_DEBORPHANS )); then
    print_warn "Skipping deborphan purge. Use --purge-deborphans to enable."
    return 0
  fi

  if command -v deborphan >/dev/null 2>&1; then
    print_info "Cleaning orphan packages reported by deborphan..."
    local orphans
    orphans="$(deborphan 2>/dev/null || true)"
    if [[ -n "$orphans" ]]; then
      while IFS= read -r pkg; do
        [[ -z "$pkg" ]] && continue
        run apt-get purge -y "$pkg"
      done <<< "$orphans"
    else
      print_info "No orphan packages found."
    fi
  else
    print_warn "deborphan not installed, skipping orphan package cleanup."
  fi
}

docker_cleanup() {
  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi

  if (( PRUNE_DOCKER )); then
    print_warn "Pruning Docker unused data..."
    if (( PRUNE_DOCKER_VOLUMES )); then
      run docker system prune -a --volumes -f
    else
      run docker system prune -a -f
    fi
  else
    print_warn "Docker detected. Skipping prune. Use --prune-docker to enable."
  fi
}

user_cache_cleanup() {
  if (( CLEAR_USER_CACHES )); then
    print_info "Cleaning user cache directories..."
    local -a cache_dirs=()
    local cache_dir
    [[ -d /root/.cache ]] && cache_dirs+=(/root/.cache)
    for cache_dir in /home/*/.cache; do
      [[ -d "$cache_dir" ]] && cache_dirs+=("$cache_dir")
    done
    (( ${#cache_dirs[@]} > 0 )) && safe_delete_tree_contents "${cache_dirs[@]}"
  else
    print_warn "Skipping user cache cleanup. Use --clear-user-caches to enable."
  fi
}

python_cache_cleanup() {
  if ! (( CLEAR_PYTHON_CACHES )); then
    return 0
  fi

  print_warn "Cleaning Python package caches for the current user..."
  if command -v uv >/dev/null 2>&1; then
    run uv cache prune || print_warn "uv cache prune failed, continuing."
  else
    print_warn "uv not found, skipping uv cache cleanup."
  fi

  if command -v python3 >/dev/null 2>&1; then
    run python3 -m pip cache purge || print_warn "pip cache purge failed or pip is unavailable, continuing."
  fi
}

playwright_cache_cleanup() {
  if ! (( CLEAR_PLAYWRIGHT_BROWSERS )); then
    return 0
  fi

  if command -v playwright >/dev/null 2>&1; then
    print_warn "Uninstalling Playwright browsers tracked for the current user..."
    run playwright uninstall --all || print_warn "Playwright browser cleanup failed, continuing."
  else
    print_warn "playwright not found, skipping browser cleanup."
  fi
}

snap_cleanup() {
  if command -v snap >/dev/null 2>&1; then
    print_info "Cleaning disabled snap revisions..."
    local disabled_revisions
    disabled_revisions="$(snap list --all 2>/dev/null | awk '/disabled/{print $1, $3}' || true)"
    if [[ -z "$disabled_revisions" ]]; then
      print_info "No disabled snap revisions found."
      return 0
    fi
    while read -r snapname revision; do
      [[ -n "$snapname" && -n "$revision" ]] || continue
      run snap remove "$snapname" "--revision=${revision}" || true
    done <<< "$disabled_revisions"
  fi
}

main() {
  parse_args "$@"
  validate_args
  require_root

  print_info "Disk status before cleanup:"
  show_disk
  echo

  confirm

  apt_preflight
  apt_cleanup
  journal_cleanup
  log_cleanup
  cache_cleanup
  tmp_cleanup
  unused_swap_cleanup
  orphan_cleanup
  docker_cleanup
  user_cache_cleanup
  python_cache_cleanup
  playwright_cache_cleanup
  snap_cleanup

  echo
  print_info "Disk status after cleanup:"
  show_disk
  print_info "Disk cleanup finished."
}

main "$@"
