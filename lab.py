#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pwd
import grp
import re
import shutil
import time
from pathlib import Path

from mininet.cli import CLI
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Node, OVSBridge
from mininet.topo import Topo

BASE_DIR = Path(__file__).resolve().parent
PROJECT_CONFIG_DIR = BASE_DIR / "configs"
STATE_DIR = Path("/tmp/mininet_bgp_lab_6as_rr")
STATE_CONFIG_DIR = STATE_DIR / "configs"
STATE_RUNTIME_DIR = STATE_DIR / "runtime"
FRR_DIR = Path("/usr/lib/frr")
ROUTERS = ["r100", "r200", "r300", "rr400", "r401", "r402", "r500", "r600"]
LEAK_PREFIXES = [f"10.200.{i}.0/24" for i in range(12)]
LEAK_SAMPLE_PREFIX = LEAK_PREFIXES[-1]


class LinuxRouter(Node):
    """A Mininet node with IPv4/IPv6 forwarding enabled."""

    def config(self, **params):
        super().config(**params)
        self.cmd("sysctl -w net.ipv4.ip_forward=1")
        self.cmd("sysctl -w net.ipv6.conf.all.forwarding=1")
        self.cmd("sysctl -w net.ipv4.conf.all.rp_filter=0")
        self.cmd("sysctl -w net.ipv4.conf.default.rp_filter=0")

    def terminate(self):
        self.cmd("sysctl -w net.ipv4.ip_forward=0")
        self.cmd("sysctl -w net.ipv6.conf.all.forwarding=0")
        super().terminate()


class SixASRRTopo(Topo):
    """6-AS IPv4 topology with an RR-based AS400 core."""

    def build(self):
        hosts = {
            "h100": ("10.100.0.2/24", "via 10.100.0.1", "2001:db8:100::2/64", "via 2001:db8:100::1"),
            "h401": ("10.40.1.2/24", "via 10.40.1.1", "2001:db8:401::2/64", "via 2001:db8:401::1"),
            "h402": ("10.40.2.2/24", "via 10.40.2.1", "2001:db8:402::2/64", "via 2001:db8:402::1"),
            "h500": ("10.50.0.2/24", "via 10.50.0.1", "2001:db8:500::2/64", "via 2001:db8:500::1"),
            "h600": ("10.60.0.2/24", "via 10.60.0.1", "2001:db8:600::2/64", "via 2001:db8:600::1"),
        }
        for name, (ip, default_route, ip6, default_route6) in hosts.items():
            self.addHost(name, ip=ip, defaultRoute=default_route)
            self.nodeInfo(name)["ipv6"] = ip6
            self.nodeInfo(name)["defaultRoute6"] = default_route6

        for switch in ["s100", "s400i", "s401", "s402", "s500", "s600"]:
            self.addSwitch(switch)

        for router in ROUTERS:
            self.addNode(router, cls=LinuxRouter, ip=None)

        self.addLink("h100", "s100")
        self.addLink("s100", "r100", intfName2="r100-eth0")

        self.addLink("r100", "r200", intfName1="r100-eth1", intfName2="r200-eth0")
        self.addLink("r100", "r300", intfName1="r100-eth2", intfName2="r300-eth0")

        self.addLink("r200", "r401", intfName1="r200-eth1", intfName2="r401-eth1")
        self.addLink("r200", "r500", intfName1="r200-eth2", intfName2="r500-eth0")

        self.addLink("r300", "r402", intfName1="r300-eth1", intfName2="r402-eth1")
        self.addLink("r300", "r600", intfName1="r300-eth2", intfName2="r600-eth0")

        self.addLink("rr400", "s400i", intfName1="rr400-eth0")
        self.addLink("r401", "s400i", intfName1="r401-eth0")
        self.addLink("r402", "s400i", intfName1="r402-eth0")

        self.addLink("r401", "s401", intfName1="r401-eth2")
        self.addLink("s401", "h401")
        self.addLink("r402", "s402", intfName1="r402-eth2")
        self.addLink("s402", "h402")
        self.addLink("r500", "s500", intfName1="r500-eth1")
        self.addLink("s500", "h500")
        self.addLink("r600", "s600", intfName1="r600-eth1")
        self.addLink("s600", "h600")


def set_tree_owner(path: Path, user: str, group: str, dir_mode: int, file_mode: int) -> None:
    uid = pwd.getpwnam(user).pw_uid
    gid = grp.getgrnam(group).gr_gid
    for root, dirs, files in os.walk(path):
        os.chown(root, uid, gid)
        os.chmod(root, dir_mode)
        for name in dirs:
            child = Path(root) / name
            os.chown(child, uid, gid)
            os.chmod(child, dir_mode)
        for name in files:
            child = Path(root) / name
            os.chown(child, uid, gid)
            os.chmod(child, file_mode)


def recreate_state_dirs(scenario: str) -> None:
    if STATE_DIR.exists():
        shutil.rmtree(STATE_DIR)

    shutil.copytree(PROJECT_CONFIG_DIR, STATE_CONFIG_DIR)
    if scenario != "baseline":
        for router in ROUTERS:
            scenario_cfg = STATE_CONFIG_DIR / router / f"bgpd_{scenario}.conf"
            if scenario_cfg.exists():
                shutil.copy2(scenario_cfg, STATE_CONFIG_DIR / router / "bgpd.conf")

    for router in ROUTERS:
        (STATE_RUNTIME_DIR / router / "vty").mkdir(parents=True, exist_ok=True)

    set_tree_owner(STATE_CONFIG_DIR, user="frr", group="frr", dir_mode=0o755, file_mode=0o644)
    set_tree_owner(STATE_RUNTIME_DIR, user="frr", group="frr", dir_mode=0o775, file_mode=0o664)


def configure_router_interfaces(net: Mininet) -> None:
    interface_map = {
        "r100": {
            "r100-eth0": ("10.100.0.1/24", "2001:db8:100::1/64", "fe80::100:1/64"),
            "r100-eth1": ("172.16.12.1/30", "2001:db8:12::1/64", "fe80::12:1/64"),
            "r100-eth2": ("172.16.13.1/30", "2001:db8:13::1/64", "fe80::13:1/64"),
        },
        "r200": {
            "r200-eth0": ("172.16.12.2/30", "2001:db8:12::2/64", "fe80::12:2/64"),
            "r200-eth1": ("172.16.24.1/30", "2001:db8:24::1/64", "fe80::24:1/64"),
            "r200-eth2": ("172.16.25.1/30", "2001:db8:25::1/64", "fe80::25:1/64"),
        },
        "r300": {
            "r300-eth0": ("172.16.13.2/30", "2001:db8:13::2/64", "fe80::13:2/64"),
            "r300-eth1": ("172.16.34.1/30", "2001:db8:34::1/64", "fe80::34:1/64"),
            "r300-eth2": ("172.16.36.1/30", "2001:db8:36::1/64", "fe80::36:1/64"),
        },
        "rr400": {
            "rr400-eth0": ("10.40.0.1/24", "2001:db8:40::1/64", "fe80::40:1/64"),
        },
        "r401": {
            "r401-eth0": ("10.40.0.2/24", "2001:db8:40::2/64", "fe80::40:2/64"),
            "r401-eth1": ("172.16.24.2/30", "2001:db8:24::2/64", "fe80::24:2/64"),
            "r401-eth2": ("10.40.1.1/24", "2001:db8:401::1/64", "fe80::401:1/64"),
        },
        "r402": {
            "r402-eth0": ("10.40.0.3/24", "2001:db8:40::3/64", "fe80::40:3/64"),
            "r402-eth1": ("172.16.34.2/30", "2001:db8:34::2/64", "fe80::34:2/64"),
            "r402-eth2": ("10.40.2.1/24", "2001:db8:402::1/64", "fe80::402:1/64"),
        },
        "r500": {
            "r500-eth0": ("172.16.25.2/30", "2001:db8:25::2/64", "fe80::25:2/64"),
            "r500-eth1": ("10.50.0.1/24", "2001:db8:500::1/64", "fe80::500:1/64"),
        },
        "r600": {
            "r600-eth0": ("172.16.36.2/30", "2001:db8:36::2/64", "fe80::36:2/64"),
            "r600-eth1": ("10.60.0.1/24", "2001:db8:600::1/64", "fe80::600:1/64"),
        },
    }

    for node_name, assignments in interface_map.items():
        node = net[node_name]
        for intf, (cidr4, cidr6, ll6) in assignments.items():
            node.cmd(f"ip addr flush dev {intf}")
            node.cmd(f"ip addr add {cidr4} dev {intf}")
            node.cmd(f"ip -6 addr flush dev {intf}")
            node.cmd(f"ip -6 addr add {cidr6} dev {intf} nodad")
            node.cmd(f"ip -6 addr add {ll6} dev {intf} nodad")
            node.cmd(f"ip link set dev {intf} up")

    host_map = {
        "h100": ("2001:db8:100::2/64", "2001:db8:100::1"),
        "h401": ("2001:db8:401::2/64", "2001:db8:401::1"),
        "h402": ("2001:db8:402::2/64", "2001:db8:402::1"),
        "h500": ("2001:db8:500::2/64", "2001:db8:500::1"),
        "h600": ("2001:db8:600::2/64", "2001:db8:600::1"),
    }
    for host_name, (cidr6, gw6) in host_map.items():
        host = net[host_name]
        intf = f"{host_name}-eth0"
        host.cmd(f"ip -6 addr flush dev {intf}")
        host.cmd(f"ip -6 addr add {cidr6} dev {intf} nodad")
        host.cmd(f"ip -6 route replace default via {gw6}")


def configure_scenario_routes(net: Mininet, scenario: str) -> None:
    if scenario in {"hijack", "defense", "aspath", "aspath_defense"}:
        net["r500"].cmd("ip route replace blackhole 10.100.0.0/24")
    if scenario == "rtbh":
        net["r500"].cmd("ip route replace blackhole 10.100.0.0/24")
        net["r200"].cmd("ip route replace blackhole 10.100.0.0/24 metric 5")
    if scenario in {"subprefix", "subprefix_defense"}:
        net["r500"].cmd("ip route replace blackhole 10.100.0.0/25")
    if scenario == "leak":
        for prefix in LEAK_PREFIXES:
            net["r500"].cmd(f"ip route replace blackhole {prefix}")



def start_frr(node: Node, name: str) -> None:
    runtime = STATE_RUNTIME_DIR / name
    config = STATE_CONFIG_DIR / name
    vty_dir = runtime / "vty"
    node.cmd(f"rm -f {runtime}/*.pid {runtime}/*.api {runtime}/*.log {vty_dir}/*.vty")

    zebra_cmd = (
        f"{FRR_DIR / 'zebra'} -d -f {config / 'zebra.conf'} "
        f"-i {runtime / 'zebra.pid'} -z {runtime / 'zserv.api'} "
        f"--vty_socket {vty_dir} -A 127.0.0.1 "
        f"--log file:{runtime / 'zebra.log'}"
    )
    bgpd_cmd = (
        f"{FRR_DIR / 'bgpd'} -d -f {config / 'bgpd.conf'} "
        f"-i {runtime / 'bgpd.pid'} -z {runtime / 'zserv.api'} "
        f"--vty_socket {vty_dir} -A 127.0.0.1 "
        f"--log file:{runtime / 'bgpd.log'}"
    )

    info(f"*** Starting FRR on {name}\n")
    node.cmd(zebra_cmd)
    time.sleep(0.6)
    node.cmd(bgpd_cmd)


def stop_frr(node: Node, name: str) -> None:
    runtime = STATE_RUNTIME_DIR / name
    node.cmd(f"pkill -F {runtime / 'bgpd.pid'} || true")
    node.cmd(f"pkill -F {runtime / 'zebra.pid'} || true")


def vtysh_cmd(node: Node, router: str, command: str) -> str:
    vty_dir = STATE_RUNTIME_DIR / router / "vty"
    return node.cmd(f'vtysh --vty_socket {vty_dir} -c "{command}" 2>/dev/null || true')


def wait_for_bgp(net: Mininet, timeout: int = 35) -> bool:
    expected = {
        "r100": ["172.16.12.2", "172.16.13.2"],
        "r200": ["172.16.12.1", "172.16.24.2", "172.16.25.2"],
        "r300": ["172.16.13.1", "172.16.34.2", "172.16.36.2"],
        "rr400": ["10.40.0.2", "10.40.0.3"],
        "r401": ["10.40.0.1", "172.16.24.1"],
        "r402": ["10.40.0.1", "172.16.34.1"],
        "r500": ["172.16.25.1"],
        "r600": ["172.16.36.1"],
    }

    for _ in range(timeout):
        ok = True
        for router, peers in expected.items():
            output = net[router].cmd("ss -tn state established '( sport = :179 or dport = :179 )' || true")
            if not all(peer in output for peer in peers):
                ok = False
                break
        if ok:
            return True
        time.sleep(1)
    return False


def wait_for_bgp_ipv6(net: Mininet, timeout: int = 35) -> bool:
    expected = {
        "r100": ["2001:db8:12::2", "2001:db8:13::2"],
        "r200": ["2001:db8:12::1", "2001:db8:24::2", "2001:db8:25::2"],
        "r300": ["2001:db8:13::1", "2001:db8:34::2", "2001:db8:36::2"],
        "rr400": ["2001:db8:40::2", "2001:db8:40::3"],
        "r401": ["2001:db8:40::1", "2001:db8:24::1"],
        "r402": ["2001:db8:40::1", "2001:db8:34::1"],
        "r500": ["2001:db8:25::1"],
        "r600": ["2001:db8:36::1"],
    }

    bad_states = ("Idle", "Active", "Connect", "OpenSent", "OpenConfirm")
    for _ in range(timeout):
        ok = True
        for router, peers in expected.items():
            output = vtysh_cmd(net[router], router, "show bgp ipv6 unicast summary")
            for peer in peers:
                line = next((ln for ln in output.splitlines() if peer in ln), "")
                if not line or any(state in line for state in bad_states):
                    ok = False
                    break
            if not ok:
                break
        if ok:
            return True
        time.sleep(1)
    return False


def prefix_view(net: Mininet, router: str, prefix: str) -> str:
    return vtysh_cmd(net[router], router, f"show ip bgp {prefix}")


def kernel_route(net: Mininet, router: str, prefix: str) -> str:
    return net[router].cmd(f"ip route show {prefix}")


def leak_prefix_count(net: Mininet, router: str) -> int:
    output = vtysh_cmd(net[router], router, "show ip bgp")
    return len(set(re.findall(r"10\.200\.\d+\.0/24", output)))


def bgp_summary(net: Mininet, router: str) -> str:
    return vtysh_cmd(net[router], router, "show ip bgp summary")


def write_alert_snapshot(net: Mininet, scenario: str, out_path: str) -> None:
    snapshot = {
        "scenario": scenario,
        "alerts": [],
    }

    def add_alert(severity: str, title: str, evidence: str) -> None:
        snapshot["alerts"].append({"severity": severity, "title": title, "evidence": evidence})

    if scenario in {"hijack", "aspath", "rtbh"}:
        r200_route = kernel_route(net, "r200", "10.100.0.0/24").strip()
        r401_view = prefix_view(net, "r401", "10.100.0.0/24")
        if "172.16.25.2" in r200_route:
            add_alert("critical", "边界节点选路异常", r200_route)
        if "200 500" in r401_view or "65099 65098" in r401_view:
            add_alert("high", "AS400内部出现污染路径", "r401/AS400 observed polluted route")
    if scenario in {"defense", "aspath_defense", "subprefix_defense", "rtbh"}:
        add_alert("info", "防御场景已执行", "Defense workflow completed")
    if scenario == "leak":
        add_alert("high", "检测到批量路由泄露", f"r200 leak count={leak_prefix_count(net, 'r200')}")
    if scenario == "subprefix":
        add_alert("critical", "更具体前缀劫持生效", kernel_route(net, 'r600', '10.100.0.0/25').strip())
    if scenario == "subprefix_defense":
        add_alert("info", "更具体前缀已阻断", prefix_view(net, 'r600', '10.100.0.0/25').strip())
    if scenario == "rtbh":
        add_alert("warning", "RTBH黑洞处置生效", kernel_route(net, 'r200', '10.100.0.0/24').strip())

    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def show_state(net: Mininet, scenario: str) -> None:
    info("\n*** r100 BGP summary\n")
    info(vtysh_cmd(net["r100"], "r100", "show ip bgp summary"))
    info("\n*** rr400 BGP summary\n")
    info(vtysh_cmd(net["rr400"], "rr400", "show ip bgp summary"))
    info("\n*** r402 BGP summary\n")
    info(vtysh_cmd(net["r402"], "r402", "show ip bgp summary"))
    info("\n*** r600 BGP summary\n")
    info(vtysh_cmd(net["r600"], "r600", "show ip bgp summary"))
    info("\n*** r600 IPv6 BGP summary\n")
    info(vtysh_cmd(net["r600"], "r600", "show bgp ipv6 unicast summary"))
    info("\n*** r600 kernel routes\n")
    info(net["r600"].cmd("ip route"))
    info("\n*** r300 kernel routes\n")
    info(net["r300"].cmd("ip route"))
    info("\n*** rr400 bgpd log tail\n")
    info(net["rr400"].cmd(f"tail -n 20 {STATE_RUNTIME_DIR / 'rr400' / 'bgpd.log'} || true"))

    if scenario in {"hijack", "defense", "aspath", "aspath_defense", "rtbh"}:
        info(f"\n*** {scenario.title()} views for 10.100.0.0/24\n")
        for router in ["r200", "r401", "rr400", "r600"]:
            info(f"\n--- {router} BGP view ---\n")
            info(prefix_view(net, router, "10.100.0.0/24"))
            info(f"\n--- {router} kernel route ---\n")
            info(kernel_route(net, router, "10.100.0.0/24"))
    if scenario in {"subprefix", "subprefix_defense"}:
        info(f"\n*** {scenario.title()} views for 10.100.0.0/25\n")
        for router in ["r200", "r401", "rr400", "r600"]:
            info(f"\n--- {router} BGP view ---\n")
            info(prefix_view(net, router, "10.100.0.0/25"))
            info(f"\n--- {router} kernel route ---\n")
            info(kernel_route(net, router, "10.100.0.0/25"))
    if scenario == "leak":
        info(f"\n*** {scenario.title()} sample views for {LEAK_SAMPLE_PREFIX}\n")
        for router in ["r200", "r401", "rr400"]:
            info(f"\n--- {router} BGP view ---\n")
            info(prefix_view(net, router, LEAK_SAMPLE_PREFIX))
            info(f"\n--- {router} leak prefix count ---\n")
            info(str(leak_prefix_count(net, router)) + "\n")


def ping_check(net: Mininet, src: str, dst: str, label: str) -> bool:
    info(f"\n*** {label}\n")
    result = net[src].cmd(f"ping -c 3 {dst}")
    info(result)
    return ", 0% packet loss" in result


def ping6_check(net: Mininet, src: str, dst: str, label: str) -> bool:
    info(f"\n*** {label}\n")
    result = net[src].cmd(f"ping -6 -c 3 {dst}")
    info(result)
    return ", 0% packet loss" in result


def ping_expect_fail(net: Mininet, src: str, dst: str, label: str) -> bool:
    info(f"\n*** {label}\n")
    result = net[src].cmd(f"ping -c 3 {dst}")
    info(result)
    return "100% packet loss" in result


def build_net() -> Mininet:
    topo = SixASRRTopo()
    return Mininet(topo=topo, switch=OVSBridge, controller=None, autoSetMacs=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="6-AS Mininet + FRR lab with Route Reflector")
    parser.add_argument("--test", action="store_true", help="Run checks and exit")
    parser.add_argument("--test-ipv6", action="store_true", help="Run IPv6 checks and exit")
    parser.add_argument("--alerts-out", help="Write alert snapshot JSON to the given path")
    parser.add_argument(
        "--scenario",
        choices=["baseline", "hijack", "defense", "leak", "aspath", "aspath_defense", "subprefix", "subprefix_defense", "md5", "rtbh", "roa_whitelist"],
        default="baseline",
        help="Select the lab scenario",
    )
    args = parser.parse_args()

    recreate_state_dirs(args.scenario)
    net = build_net()
    net.start()
    configure_router_interfaces(net)
    configure_scenario_routes(net, args.scenario)

    try:
        for router in ROUTERS:
            start_frr(net[router], router)
        time.sleep(4)
        established = wait_for_bgp(net)
        established_v6 = wait_for_bgp_ipv6(net) if args.test_ipv6 else True
        show_state(net, args.scenario)

        if args.test or args.test_ipv6:
            if not established:
                raise SystemExit("BGP sessions did not establish within timeout")
            if args.test_ipv6 and not established_v6:
                raise SystemExit("IPv6 BGP sessions did not establish within timeout")
            if args.test:
                tests = [
                    ("h100", "10.60.0.2", "Ping h100 -> h600"),
                    ("h600", "10.40.1.2", "Ping h600 -> h401 (via RR path)"),
                    ("h500", "10.40.2.2", "Ping h500 -> h402"),
                ]
                if args.scenario == "subprefix":
                    tests = [
                        ("h600", "10.40.1.2", "Ping h600 -> h401 (via RR path)"),
                        ("h500", "10.40.2.2", "Ping h500 -> h402"),
                    ]
                if args.scenario == "subprefix_defense":
                    tests = [
                        ("h100", "10.60.0.2", "Ping h100 -> h600"),
                        ("h600", "10.40.1.2", "Ping h600 -> h401 (via RR path)"),
                        ("h500", "10.40.2.2", "Ping h500 -> h402"),
                    ]
                for src, dst, label in tests:
                    if not ping_check(net, src, dst, label):
                        raise SystemExit(f"Connectivity test failed: {label}")
            if args.test_ipv6:
                tests_v6 = [
                    ("h100", "2001:db8:600::2", "Ping6 h100 -> h600"),
                    ("h600", "2001:db8:401::2", "Ping6 h600 -> h401"),
                    ("h500", "2001:db8:402::2", "Ping6 h500 -> h402"),
                ]
                for src, dst, label in tests_v6:
                    if not ping6_check(net, src, dst, label):
                        raise SystemExit(f"IPv6 connectivity test failed: {label}")
            if args.scenario == "hijack" and args.test:
                r200_route = kernel_route(net, "r200", "10.100.0.0/24")
                r401_view = prefix_view(net, "r401", "10.100.0.0/24")
                if "172.16.25.2" not in r200_route:
                    raise SystemExit("Hijack scenario did not steer r200 toward AS500 for 10.100.0.0/24")
                if "200 500" not in r401_view:
                    raise SystemExit("Hijack scenario did not propagate the poisoned AS-PATH into AS400")
                info("\n*** Hijack scenario confirmed on r200 and observed inside AS400\n")
            if args.scenario == "defense" and args.test:
                r200_route = kernel_route(net, "r200", "10.100.0.0/24")
                r401_view = prefix_view(net, "r401", "10.100.0.0/24")
                if "172.16.25.2" in r200_route:
                    raise SystemExit("Defense scenario still allowed r200 to prefer the attacker route")
                if "200 500" in r401_view:
                    raise SystemExit("Defense scenario still propagated the poisoned AS-PATH into AS400")
                if "172.16.12.1" not in r200_route:
                    raise SystemExit("Defense scenario did not restore the legitimate path on r200")
                info("\n*** Defense scenario confirmed: attacker prefix blocked at AS200 and not propagated into AS400\n")
            if args.scenario == "roa_whitelist" and args.test:
                r200_route = kernel_route(net, "r200", "10.100.0.0/24")
                r401_view = prefix_view(net, "r401", "10.100.0.0/24")
                if "172.16.25.2" in r200_route:
                    raise SystemExit("ROA whitelist scenario still allowed the unauthorized attacker path")
                if "200 500" in r401_view:
                    raise SystemExit("ROA whitelist scenario still propagated the unauthorized origin into AS400")
                if "172.16.12.1" not in r200_route:
                    raise SystemExit("ROA whitelist scenario did not keep the authorized legitimate path on r200")
                info("\n*** ROA whitelist defense confirmed: unauthorized origin blocked by generated prefix whitelist\n")
            if args.scenario == "aspath" and args.test:
                r200_route = kernel_route(net, "r200", "10.100.0.0/24")
                r401_view = prefix_view(net, "r401", "10.100.0.0/24")
                if "172.16.25.2" not in r200_route:
                    raise SystemExit("AS-PATH tamper scenario did not steer r200 toward AS500")
                if "65099 65098" not in r401_view:
                    raise SystemExit("AS-PATH tamper scenario did not propagate the injected AS sequence")
                info("\n*** AS-PATH tamper scenario confirmed: injected AS sequence observed inside AS400\n")
            if args.scenario == "aspath_defense" and args.test:
                r200_route = kernel_route(net, "r200", "10.100.0.0/24")
                r401_view = prefix_view(net, "r401", "10.100.0.0/24")
                if "65099 65098" in r401_view:
                    raise SystemExit("AS-PATH defense scenario still allowed the tampered AS sequence into AS400")
                if "172.16.12.1" not in r200_route:
                    raise SystemExit("AS-PATH defense scenario did not restore the legitimate path on r200")
                info("\n*** AS-PATH defense confirmed: tampered path blocked and legitimate path restored\n")
            if args.scenario == "rtbh" and args.test:
                r200_route = kernel_route(net, "r200", "10.100.0.0/24")
                if "blackhole 10.100.0.0/24" not in r200_route:
                    raise SystemExit("RTBH scenario did not install a blackhole route on r200")
                if not ping_expect_fail(net, "h401", "10.100.0.2", "Ping h401 -> h100 under RTBH"):
                    raise SystemExit("RTBH scenario did not blackhole traffic toward the victim prefix")
                info("\n*** RTBH scenario confirmed: traffic toward the victim prefix was blackholed at AS200\n")
            if args.scenario == "subprefix" and args.test:
                r600_view = prefix_view(net, "r600", "10.100.0.0/25")
                if "10.100.0.0/25" not in r600_view:
                    raise SystemExit("Subprefix scenario did not propagate the more specific prefix to AS600")
                if not ping_expect_fail(net, "h600", "10.100.0.2", "Ping h600 -> h100 during subprefix hijack"):
                    raise SystemExit("Subprefix scenario did not divert traffic away from the legitimate host")
                info("\n*** Subprefix hijack confirmed: more specific route propagated and victim traffic was disrupted\n")
            if args.scenario == "subprefix_defense" and args.test:
                r600_view = prefix_view(net, "r600", "10.100.0.0/25")
                if "10.100.0.0/25" in r600_view and "Network not in table" not in r600_view:
                    raise SystemExit("Subprefix defense scenario still allowed the more specific attacker prefix")
                if not ping_check(net, "h600", "10.100.0.2", "Ping h600 -> h100 after subprefix defense"):
                    raise SystemExit("Subprefix defense scenario did not restore reachability to the legitimate host")
                info("\n*** Subprefix defense confirmed: more specific attacker prefix blocked and reachability restored\n")
            if args.scenario == "leak" and args.test:
                r200_count = leak_prefix_count(net, "r200")
                rr400_count = leak_prefix_count(net, "rr400")
                if r200_count < len(LEAK_PREFIXES):
                    raise SystemExit("Leak scenario did not import the expected leaked prefixes into AS200")
                if rr400_count < len(LEAK_PREFIXES):
                    raise SystemExit("Leak scenario did not propagate leaked prefixes into AS400")
                info("\n*** Leak scenario confirmed: leaked prefixes imported by AS200 and propagated into AS400\n")
            if args.alerts_out:
                write_alert_snapshot(net, args.scenario, args.alerts_out)
            info("\n*** 6-AS RR test completed successfully\n")
        else:
            info("\n*** Entering Mininet CLI. Use exit or Ctrl-D to stop the lab.\n")
            CLI(net)
    finally:
        for router in reversed(ROUTERS):
            stop_frr(net[router], router)
        net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    main()
