# BGP安全防御实验平台 / BGP Security Lab

本仓库是一个基于 Mininet、Open vSwitch 和 FRRouting 的 BGP 安全实验平台。项目构建了六个自治系统和 AS400 内部 Route Reflector 结构，用于复现 BGP 正常传播、典型异常路由传播以及多种边界防御策略。

This repository provides a Mininet, Open vSwitch and FRRouting based BGP security lab. It builds a six-AS topology with a Route Reflector inside AS400 to reproduce normal routing, abnormal BGP propagation and several practical edge-defense workflows.

## 项目特点

- 六 AS 拓扑：AS100、AS200、AS300、AS400、AS500、AS600。
- AS400 内部包含 `rr400`、`r401`、`r402`，用于验证 iBGP Route Reflector 传播。
- 支持 IPv4 基线和 IPv6 双栈基线验证。
- 已验证攻击场景包括同前缀劫持、子前缀劫持、AS_PATH 篡改和路由泄露。
- 已验证防御场景包括前缀过滤、AS_PATH 过滤、MD5 会话保护、RTBH 黑洞处置和基于 ROA 数据生成的前缀白名单。
- 支持通过脚本自动清理环境、启动拓扑、执行测试并导出 JSON 告警快照。

## Topology And Roles

- `AS100`: legitimate source AS, with host `h100`.
- `AS200`: upstream provider and main defense edge.
- `AS300`: second upstream provider.
- `AS400`: enterprise AS, with `rr400`, `r401` and `r402`.
- `AS500`: attacker-side stub AS, with host `h500`.
- `AS600`: observer AS, with host `h600`.

## 运行环境

建议在 Linux 虚拟机或实验主机上运行，需安装：

- Mininet
- Open vSwitch
- FRRouting
- Python 3

当前实验主机中的项目路径示例：

```bash
cd /home/toor/Desktop/cherry/mininet_bgp_lab/six_as_rr
```

## 快速运行

每个脚本都会先清理 Mininet 状态，再启动对应场景。

```bash
bash run_test.sh
```

进入交互式 Mininet CLI：

```bash
bash run_cli.sh
```

## 稳定测试脚本

```bash
bash run_test.sh
bash run_test_ipv6.sh
bash run_hijack_test.sh
bash run_defense_test.sh
bash run_subprefix_test.sh
bash run_subprefix_defense_test.sh
bash run_aspath_test.sh
bash run_aspath_defense_test.sh
bash run_leak_test.sh
bash run_md5_test.sh
bash run_rtbh_test.sh
bash run_roa_whitelist_test.sh
```

## 实验场景说明

### 基线路由传播

`run_test.sh` 验证六 AS IPv4 拓扑中的 BGP 邻接关系、合法前缀传播、内核路由安装和端到端连通性。

`run_test_ipv6.sh` 在同一拓扑上验证 IPv6 BGP 邻接关系和 IPv6 主机连通性。

### 同前缀劫持与前缀过滤

`run_hijack_test.sh` 使 AS500 伪造发布 `10.100.0.0/24`，观察 AS200 最优路径偏移以及污染路径进入 AS400 的情况。

`run_defense_test.sh` 在 AS200 对来自 AS500 的伪造前缀进行入向过滤，验证合法路径恢复和污染路径阻断。

### 子前缀劫持与过滤

`run_subprefix_test.sh` 使 AS500 发布更具体的 `10.100.0.0/25`，验证最长前缀匹配对转发路径的影响。

`run_subprefix_defense_test.sh` 通过 AS200 入向前缀过滤阻断更具体攻击前缀，并验证业务可达性恢复。

### AS_PATH 篡改与过滤

`run_aspath_test.sh` 通过 AS500 注入伪造 AS 序列，模拟路径属性异常传播。

`run_aspath_defense_test.sh` 在 AS200 使用 AS_PATH 过滤策略阻断异常路径。

### 路由泄露

`run_leak_test.sh` 使 AS500 批量发布 `10.200.x.0/24` 前缀，观察异常前缀集合进入 AS200 并继续传播到 AS400 的过程。

### MD5 会话保护

`run_md5_test.sh` 为 AS200 与 AS500 之间的关键 eBGP 会话配置匹配的 MD5 密码，用于验证会话级认证保护。

### RTBH 黑洞处置

`run_rtbh_test.sh` 在 AS200 安装针对 `10.100.0.0/24` 的黑洞路由，用于模拟攻击后的快速流量处置。

### ROA 白名单

`run_roa_whitelist_test.sh` 根据 `data/roa_whitelist.json` 生成入向前缀白名单配置，模拟轻量级路由起源授权校验。

## 告警快照

可以为指定场景导出结构化告警结果：

```bash
bash run_alert_snapshot.sh hijack
```

输出文件会写入 `outputs/` 目录，内容包括场景名称、告警等级和判断依据。

## English Quick Start

Run the baseline test:

```bash
bash run_test.sh
```

Run selected security scenarios:

```bash
bash run_hijack_test.sh
bash run_defense_test.sh
bash run_subprefix_test.sh
bash run_aspath_test.sh
bash run_leak_test.sh
bash run_roa_whitelist_test.sh
```

The verified scope includes same-prefix hijacking, subprefix hijacking, AS_PATH tampering, route leak, prefix filtering, AS_PATH filtering, MD5 session protection, RTBH and a lightweight ROA whitelist workflow.

## 说明

本仓库公开的是稳定验证范围内的项目代码。完整 RPKI 验证器、TCP-AO、BMP/MRT 采集、Ryu 控制器主线集成和最大前缀路由泄露防御不作为当前稳定功能声明。
