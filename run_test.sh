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

run_root mn -c >/dev/null 2>&1 || true
run_root rm -rf /tmp/mininet_bgp_lab_6as_rr || true
run_root python3 /home/toor/Desktop/cherry/mininet_bgp_lab/six_as_rr/lab.py --test
