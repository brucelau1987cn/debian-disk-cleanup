#!/usr/bin/env bash
# Debian disk cleanup script.
# Supports Debian 10/11/12. Run as root.

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
  -h, --help                Show this help.

Safe defaults clean APT cache, orphaned APT packages, old rotated logs,
Debian package cache files, old kernels, disabled snap revisions, and systemd
journal retention. Destructive areas require explicit flags.
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

run_shell() {
  local cmd="$1"
  if (( DRY_RUN )); then
    printf '[DRY-RUN] bash -c %q\n' "$cmd"
  else
    bash -c "$cmd"
  fi
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
      --prune-volumes) PRUNE_DOCKER=1; PRUNE_DOCKER_VOLUMES=1; shift ;;
      --clear-login-logs) CLEAR_LOGIN_LOGS=1; shift ;;
      --clear-user-caches) CLEAR_USER_CACHES=1; shift ;;
      --clear-tmp) CLEAR_TMP=1; shift ;;
      -h|--help) usage; exit 0 ;;
      *) print_error "Unknown option: $1"; usage; exit 2 ;;
    esac
  done
}

show_disk() {
  df -h /
}

apt_cleanup() {
  print_info "Cleaning APT cache and unused packages..."
  export DEBIAN_FRONTEND=noninteractive
  run apt-get clean
  run apt-get autoclean
  run apt-get autoremove --purge -y
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
  print_info "Cleaning old rotated logs under /var/log..."

  if (( CLEAR_LOGIN_LOGS )); then
    for logfile in /var/log/btmp /var/log/wtmp; do
      if [[ -f "$logfile" ]]; then
        print_warn "Truncating ${logfile}..."
        run truncate -s 0 "$logfile"
      fi
    done
  fi

  run find /var/log -type f \( \
    -name '*.gz' -o \
    -name '*.1' -o \
    -name '*.2' -o \
    -name '*.old' -o \
    -name '*.log.*' \
  \) -delete
}

cache_cleanup() {
  print_info "Cleaning package cache files under /var/cache..."
  run find /var/cache -type f -name '*.deb' -delete
}

tmp_cleanup() {
  if (( CLEAR_TMP )); then
    print_info "Cleaning temporary directories..."
    run find /tmp /var/tmp -mindepth 1 -xdev -exec rm -rf -- {} +
  else
    print_warn "Skipping /tmp and /var/tmp cleanup. Use --clear-tmp to enable."
  fi
}

kernel_cleanup() {
  print_info "Cleaning old Debian kernel packages..."
  local current_kernel packages
  current_kernel="$(uname -r)"
  packages="$(dpkg-query -W -f='${Package}\n' 'linux-image-[0-9]*' 2>/dev/null | grep -Fv "${current_kernel}" || true)"

  if [[ -z "$packages" ]]; then
    print_info "No old kernel packages found."
    return 0
  fi

  while IFS= read -r kernel; do
    [[ -z "$kernel" ]] && continue
    print_warn "Purging old kernel: ${kernel}"
    run apt-get purge -y "$kernel"
  done <<< "$packages"

  run apt-get autoremove --purge -y
}

orphan_cleanup() {
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
    run_shell 'find /root/.cache /home/*/.cache -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + 2>/dev/null || true'
  else
    print_warn "Skipping user cache cleanup. Use --clear-user-caches to enable."
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
  require_root

  print_info "Disk status before cleanup:"
  show_disk
  echo

  confirm

  apt_cleanup
  journal_cleanup
  log_cleanup
  cache_cleanup
  tmp_cleanup
  kernel_cleanup
  orphan_cleanup
  docker_cleanup
  user_cache_cleanup
  snap_cleanup

  echo
  print_info "Disk status after cleanup:"
  show_disk
  print_info "Disk cleanup finished."
}

main "$@"
