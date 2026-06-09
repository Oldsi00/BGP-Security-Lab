#!/usr/bin/env bash
set -euo pipefail
SUDO_PASSWORD="${SUDO_PASSWORD:-toor}"

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    printf '%s\n' "$SUDO_PASSWORD" | sudo -S "$@"
  fi
}

cd "$(dirname "$0")"
run_root mn -c >/dev/null 2>&1 || true
run_root rm -rf /tmp/mininet_bgp_lab_6as_rr || true
run_root python3 lab.py --test --scenario defense
