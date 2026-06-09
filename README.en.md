# BGP Security Lab

This repository provides a Mininet, Open vSwitch and FRRouting based BGP security lab. The lab builds a six-AS topology with an internal Route Reflector in AS400.

Verified scenarios include:

- IPv4 baseline routing.
- IPv6 dual-stack baseline routing.
- Same-prefix hijacking and prefix filtering.
- Subprefix hijacking and filtering.
- AS_PATH tampering and AS_PATH filtering.
- Route leak.
- MD5 BGP session protection.
- RTBH blackhole response.
- Lightweight ROA-data-generated prefix whitelist.

Quick start:

```bash
bash run_test.sh
bash run_hijack_test.sh
bash run_defense_test.sh
bash run_subprefix_test.sh
bash run_aspath_test.sh
bash run_leak_test.sh
bash run_roa_whitelist_test.sh
```

The primary README is written in Chinese first, with English content included after the Chinese sections.
