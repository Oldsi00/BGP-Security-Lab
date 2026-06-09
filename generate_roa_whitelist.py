#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "roa_whitelist.json"
OUT_FILE = BASE_DIR / "configs" / "r200" / "bgpd_roa_whitelist.conf"
SOURCE_CONFIG = BASE_DIR / "configs" / "r200" / "bgpd.conf"


def main() -> None:
    records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    allow_lines = []
    deny_lines = []
    seq = 5
    for item in records:
        prefix = item["prefix"]
        max_length = item["max_length"]
        allow_lines.append(f"ip prefix-list ROA-AUTH-{seq} seq 5 permit {prefix} le {max_length}")
        deny_lines.append(f"ip prefix-list ROA-BLOCK-{seq} seq 5 deny {prefix} le 32")
        deny_lines.append(f"ip prefix-list ROA-BLOCK-{seq} seq 100 permit 0.0.0.0/0 le 32")
        seq += 5

    template = SOURCE_CONFIG.read_text(encoding="utf-8").splitlines()
    header = [
        "hostname bgpd-r200",
        "password zebra",
        "!",
        *allow_lines,
        *deny_lines,
        "!",
    ]

    body = [
        "router bgp 200",
        " bgp router-id 200.0.0.1",
        " no bgp ebgp-requires-policy",
        " neighbor 172.16.12.1 remote-as 100",
        " neighbor 172.16.24.2 remote-as 400",
        " neighbor 172.16.25.2 remote-as 500",
        " neighbor 2001:db8:12::1 remote-as 100",
        " neighbor 2001:db8:24::2 remote-as 400",
        " neighbor 2001:db8:25::2 remote-as 500",
        " neighbor 2001:db8:12::1 update-source 2001:db8:12::2",
        " neighbor 2001:db8:24::2 update-source 2001:db8:24::1",
        " neighbor 2001:db8:25::2 update-source 2001:db8:25::1",
        " !",
        " address-family ipv4 unicast",
        "  neighbor 172.16.12.1 activate",
        "  neighbor 172.16.24.2 activate",
        "  neighbor 172.16.25.2 activate",
        "  neighbor 172.16.25.2 prefix-list ROA-BLOCK-5 in",
        " exit-address-family",
        " !",
        " address-family ipv6 unicast",
        "  neighbor 2001:db8:12::1 activate",
        "  neighbor 2001:db8:24::2 activate",
        "  neighbor 2001:db8:25::2 activate",
        " exit-address-family",
        "!",
        "line vty",
    ]

    OUT_FILE.write_text("\n".join(header + body) + "\n", encoding="utf-8")
    print(f"generated: {OUT_FILE}")


if __name__ == "__main__":
    main()
