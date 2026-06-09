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

run_root mn -c || true
run_root pkill -f "/usr/lib/frr/bgpd -d -f /tmp/mininet_bgp_lab_6as_rr/configs" || true
run_root pkill -f "/usr/lib/frr/zebra -d -f /tmp/mininet_bgp_lab_6as_rr/configs" || true
run_root rm -rf /tmp/mininet_bgp_lab_6as_rr
