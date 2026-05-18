# 真实测试网段联调结果评估

## 背景

- 日期：2026-05-18
- 分支：`feature/codex-latest-counts-cli`
- 目的：验证 0 网段和 2 网段多网段真实扫描、SNMP 采集、拓扑快照写入和 latest 聚合查询。
- 脱敏说明：本报告不记录完整网段、真实设备 IP、账号、密码、SNMP community、Neo4j 密码或可还原真实拓扑关系的设备明细。

## 执行范围

- 使用配置：`config/config.yaml`，该文件已被 `.gitignore` 忽略。
- 执行阶段：多网段真实扫描。
- 扫描范围说明：2 个受控测试 `/24` 网段，脱敏标识为 0 网段和 2 网段。
- 并发设置：`max_concurrency=8`。
- SNMP：启用。
- SSH：关闭。

## 前置验证

- conda 环境：使用当前项目 Python 3.11 环境执行。
- `pytest`：通过，114 passed。
- `ruff check .`：通过。
- `mypy .`：通过，17 个 source files 无类型错误。

## Neo4j 连通性结果

- 结果：`--latest-counts` 查询成功。
- 扫描前 latest 聚合结果：
  - devices：0
  - interfaces：0
  - active_links：0
- 发现的问题：当前 Neo4j Bolt 协议不支持显式 database selection。
- 处理结果：Repository 的 database fallback 路径可用，真实扫描和 latest 查询均可继续使用默认 database session。

## Neo4j 假数据写入验证

- 输入数据说明：本次未单独执行假数据写入；依赖默认单元测试中的 repository mock 测试覆盖事务、幂等 Cypher、fallback 和错误脱敏。
- 聚合结果：不适用。
- 幂等验证：本次未重复执行完整真实扫描。
- 结论：默认质量门禁通过；真实 Neo4j 后续可补充独立假数据幂等联调。

## 真实测试网段完整扫描结果

- scanned_hosts：508
- reachable_hosts：142
- snmp_successes：18
- ssh_successes：0
- devices：508
- interfaces：81
- links：0
- errors：491
- 总耗时：约 640 秒

## Neo4j 聚合结果

latest DiscoveryRun 聚合结果：

- Device：508
- Interface：81
- CONNECTED_TO active：0
- error_count：491

全库脱敏聚合结果：

- Device：510
- Interface：133
- NetworkSegment：4
- HAS_INTERFACE：133
- BELONGS_TO_SEGMENT：511
- CONNECTED_TO：1

说明：全库聚合包含历史测试残留，因此与本次 latest DiscoveryRun 计数不同。当前对外最新状态应以 `DiscoveryRun {is_latest: true}` 的聚合计数为准。

## 设备识别结果

device_type 分布：

- unknown：490
- server：18
- router：1
- switch：1

deployment_type 分布：

- unknown：508
- 未设置：2

unknown 原因拆解：

- offline unknown：366，主要来自扫描覆盖但当前不可达的地址。
- partial unknown：124，主要来自 ICMP 可达但 SNMP 未成功或信息不足的地址。
- online unknown：未单独查询到聚合值，后续可增加查询脚本细分。

## 协议采集结果

- SNMP 成功样本特征：SNMP 成功 18 个，生成接口 81 个。
- SNMP 失败类型分布：本次未落库细分错误类型，仅 latest error_count 记录为 491。
- SSH 是否启用：否。
- LLDP/CDP 是否启用：SNMP 采集层已支持邻居采集，但本次未生成链路。
- 路由表/ARP 表/MAC 表是否启用：否，SSH 关闭。
- 各发现层级启用情况：
  - 基础发现层：启用。
  - SNMP 标准采集层：启用。
  - SSH 补充识别层：未启用。
  - ARP/MAC/路由表推断：未启用。

## 单 IP 冒烟测试

- 输入：本次未单独执行单 IP 冒烟测试，直接执行 0/2 两个受控测试 `/24` 网段。
- 输出统计：见完整扫描结果。
- stderr：未记录到需要脱敏输出的错误。
- 结论：多网段扫描闭环成功，SNMP 成功率偏低，需要结合真实设备 SNMP 配置和 ACL 继续分析。

## 已修复的问题

1. 无本次测试中即时修复的问题。

## 需要设计侧评估的问题

1. 是否需要持久化结构化 `DiscoveryError`，用于后续统计 SNMP 失败类型，而不是仅保存 `DiscoveryRun.error_count`。
2. 是否需要新增受控真实联调脚本，自动输出脱敏 Neo4j 聚合、设备状态分布和设备类型分布。
3. 是否需要为真实测试增加重复扫描步骤，专门验证 latest、offline、stale 和事务写入在真实 Neo4j 中的幂等表现。
4. 如果目标是从单台交换机扩展发现更多网络，应先由 Design Codex 设计 seed 设备递归发现、路由表解析和扫描范围保护策略。

## 建议下一步

1. 在 Design Codex 确认后，增加结构化错误落库或测试报告查询能力。
2. 对 SNMP 成功和失败样本做脱敏分类，区分超时、认证失败、OID 不支持和网络不可达。
3. 选择 1 台确认开启 LLDP/CDP 的测试交换机做单设备链路发现验证。
4. 如果需要发现跨网段拓扑，先设计路由表、ARP 表、MAC 表的只读采集和递归范围限制。
