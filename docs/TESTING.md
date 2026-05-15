# 测试设计

## 目标

本文档定义 `topology-discovery-lab` 的测试分层、真实测试环境准入条件、执行顺序、验收标准和禁止事项。

本项目当前允许接入受控测试网络进行真实联调，但真实配置、真实凭据、真实网段和真实拓扑数据不得提交到 Git。

## 测试分层

### 单元测试

默认测试层级，不连接真实网络，不连接真实 Neo4j。

适用范围：

- 配置读取和校验。
- 数据模型校验。
- ICMP/SNMP/SSH 模块的错误处理和结果转换。
- parser 去重和快照构建。
- Neo4j repository 的 Cypher 生成和参数传递。

要求：

1. 使用 mock、fake adapter 或样例数据。
2. 不依赖真实设备。
3. 不依赖真实网段。
4. 不使用真实账号、密码、community。
5. 默认 `pytest` 只运行单元测试和不依赖外部环境的测试。

### 本地 Neo4j 集成测试

用于验证真实 Neo4j 驱动、Cypher、`MERGE` 幂等和图模型。

准入条件：

1. Neo4j 是本地或受控测试实例。
2. 使用本地 `config/config.yaml` 或环境变量提供连接信息。
3. 连接 URI 必须使用 Bolt 协议，例如 `bolt://<host>:7687`。
4. 测试数据不得包含真实生产拓扑。
5. 测试库必须可清理，或使用独立测试 database。

验证内容：

- `RETURN 1 AS ok` 连通性。
- `Device` 写入。
- `Interface` 写入。
- `NetworkSegment` 写入。
- `HAS_INTERFACE` 关系写入。
- `BELONGS_TO_SEGMENT` 关系写入。
- `CONNECTED_TO` 关系写入。
- 重复执行不重复创建节点或关系。

### 真实测试网段联调

用于验证真实网络环境中的扫描、采集、解析和 Neo4j 写入闭环。

准入条件：

1. 当前网络明确为测试环境。
2. 已确认扫描目标不属于生产或运营商网络。
3. 本地 `config/config.yaml` 已存在，且被 `.gitignore` 忽略。
4. SSH 默认关闭。
5. SNMP 使用只读 community 或只读账号。
6. 所有外部连接必须配置 timeout。
7. 初始并发必须保守。

推荐顺序：

1. Neo4j 连通性测试。
2. Neo4j 假数据写入测试。
3. 单 IP 真实扫描。
4. 单个小网段扫描。
5. 多个小网段扫描。
6. 完整测试网段扫描。
7. 多网段重复扫描和幂等验证。

## Conda 环境检查

本项目本地开发和测试默认使用 conda，环境名固定为：

```text
topology-discovery-lab
```

测试前执行：

```powershell
conda activate topology-discovery-lab
python -c "import sys; print(sys.executable); print(sys.version)"
python -m pip --version
```

验收：

1. Python 版本为 3.11。
2. `python` 和 `python -m pip` 来自同一个 conda 环境。

## 本地配置要求

真实测试配置文件：

```text
config/config.yaml
```

该文件必须被 `.gitignore` 忽略。

真实测试配置可以包含：

- 测试网段。
- SNMP 只读 community。
- 测试 Neo4j Bolt URI。
- 测试 Neo4j 用户名和密码。

禁止提交：

- `config/config.yaml`
- 真实 Neo4j 密码。
- 真实 SNMP community。
- 真实生产网段。
- 真实拓扑数据。

## 真实测试流程

### 阶段 1：Neo4j 连通性

目标：只验证 Neo4j 可连接，不执行扫描。

验证查询：

```cypher
RETURN 1 AS ok
```

验收：

1. 连接成功。
2. 错误信息不包含密码。
3. URI 使用 `bolt://`，不是 `http://`。

### 阶段 2：Neo4j 假数据写入

目标：验证 repository 和图模型，不接真实网络。

测试数据应包含：

- 1 个 `Device`
- 2 个 `Interface`
- 1 个 `NetworkSegment`
- `HAS_INTERFACE`
- `BELONGS_TO_SEGMENT`
- 可选 `CONNECTED_TO`

重复执行两次。

验收：

1. `Device` 不重复。
2. `Interface` 不重复。
3. `NetworkSegment` 不重复。
4. 关系不重复。
5. `last_seen` 可以更新。

### 阶段 3：单 IP 真实扫描

目标：验证单台设备从扫描到写入的最小闭环。

建议：

1. 每个目标网段先选 1 台确认存在的测试设备。
2. `max_concurrency` 设置为 `1`。
3. SSH 保持关闭。

验收：

1. 返回 `AliveHost`。
2. SNMP 成功或失败均结构化记录。
3. 可生成 `DeviceNode`。
4. SNMP 成功时可生成 `InterfaceNode`。
5. 可写入 Neo4j。
6. 重复执行不产生重复节点。

### 阶段 4：小网段真实扫描

目标：验证失败隔离、并发控制和多设备写入。

建议：

1. 使用小 CIDR 或少量单 IP 列表。
2. `max_concurrency` 从 `4` 开始。
3. 保持 `timeout_seconds` 较短。
4. SSH 保持关闭。

验收：

1. 单个 IP 失败不影响整体。
2. SNMP 失败不影响其他设备。
3. Neo4j 写入成功。
4. 重复执行不重复创建节点或关系。
5. 错误列表可读且脱敏。

### 阶段 5：完整测试网段扫描

目标：验证真实测试网络规模下的稳定性。

建议：

1. 同时配置多个测试网段。
2. `max_concurrency` 先使用 `8`。
3. 稳定后再考虑提高到 `16`。
4. SSH 仍默认关闭。

验收：

1. 扫描总耗时可接受。
2. 错误率可解释。
3. 设备、接口、网段归属关系正确。
4. 重复扫描后节点和关系数量不异常增长。
5. `TopologySnapshot.scan_targets` 能记录原始扫描目标。
6. `NetworkSegment` 能表达每个扫描目标。
7. `BELONGS_TO_SEGMENT` 能表达设备和网段归属。

### 阶段 5.5：分层发现策略验证

目标：验证系统先完成基础发现，再对信息不足的设备启用补充或高级发现方式。

验证顺序：

1. 仅启用基础发现和 SNMP，记录 `unknown`、`offline`、`partial` 分布。
2. 对 `partial + unknown` 样本启用补充识别方式，例如 SSH 只读 `show version` 或 `sysObjectID` 映射。
3. 对链路为 0 或邻居不足的设备启用 LLDP/CDP。
4. 当 LLDP/CDP 不可用时，再评估路由表、ARP 表、MAC 地址表推断。

验收：

1. 基础发现结果不会因为高级发现失败而丢失。
2. 补充识别只提升设备类型、部署形态或接口/邻居信息，不覆盖更高置信度来源。
3. LLDP/CDP 发现的链路置信度高于路由表、ARP 表、MAC 表推断。
4. 路由表、ARP 表、MAC 表推断结果必须标记发现方式。
5. 测试报告必须记录每个阶段启用了哪些发现层级。

## 测试结果报告归档

每次真实测试网段联调后，必须输出固定结构的 Markdown 报告。

报告目录：

```text
reports/real-world-testing/
```

推荐文件名：

```text
YYYY-MM-DD-<short-scenario>-assessment.md
```

示例：

```text
2026-05-15-discovery-assessment.md
```

报告必须脱敏，不允许记录真实设备 IP、真实账号、真实密码、SNMP community、Neo4j 密码或可还原真实拓扑关系的设备明细。

允许记录聚合统计、脱敏错误类型、分支名、执行阶段、测试是否通过、设计侧需要评估的问题。

### 报告固定结构

每份真实测试报告应使用以下结构：

```markdown
# 真实测试网段联调结果评估

## 背景

- 日期：
- 分支：
- 目的：
- 脱敏说明：

## 执行范围

- 使用配置：
- 执行阶段：
- 扫描范围说明：

## 前置验证

- conda 环境：
- pytest：
- ruff：
- mypy：

## Neo4j 连通性结果

- 结果：
- 发现的问题：
- 处理结果：

## Neo4j 假数据写入验证

- 输入数据说明：
- 聚合结果：
- 幂等验证：
- 结论：

## 真实测试网段完整扫描结果

- scanned_hosts：
- reachable_hosts：
- snmp_successes：
- ssh_successes：
- devices：
- interfaces：
- links：
- errors：
- 总耗时：

## Neo4j 聚合结果

- Device：
- Interface：
- NetworkSegment：
- HAS_INTERFACE：
- BELONGS_TO_SEGMENT：
- CONNECTED_TO：

## 设备识别结果

- device_type 分布：
- deployment_type 分布：
- endpoint_type 分布：
- unknown 原因拆解：

## 协议采集结果

- SNMP 成功样本特征：
- SNMP 失败类型分布：
- SSH 是否启用：
- LLDP/CDP 是否启用：
- 路由表/ARP 表/MAC 表是否启用：
- 各发现层级启用情况：

## 单 IP 冒烟测试

- 输入：
- 输出统计：
- stderr：
- 结论：

## 已修复的问题

1.

## 需要设计侧评估的问题

1.

## 建议下一步

1.
```

### 报告验收标准

1. 报告必须包含前置验证结果。
2. 报告必须包含 Neo4j 连通性和写入幂等结果。
3. 报告必须包含真实扫描聚合统计。
4. 报告必须包含 `unknown` 原因拆解。
5. 报告必须列出需要设计侧评估的问题。
6. 报告不得包含敏感信息。

### 阶段 6：多网段和重叠网段测试

目标：验证多网段设计。

测试重点：

1. 多个 target 展开后 IP 去重。
2. 同一 IP 属于多个 target 时，保留 `source_targets`。
3. 同一设备不重复生成 `Device`。
4. 同一设备可关联多个 `NetworkSegment`。
5. 重复扫描不重复创建 `BELONGS_TO_SEGMENT`。

验收 Cypher 示例：

```cypher
MATCH (d:Device)-[:BELONGS_TO_SEGMENT]->(s:NetworkSegment)
RETURN d.device_id, collect(s.segment_id) AS segments
```

## 设备识别测试

设备识别必须覆盖三个维度：

- `device_type`
- `endpoint_type`
- `deployment_type`

测试要求：

1. 路由器、交换机、防火墙、无线 AP、服务器、终端设备可按规则识别。
2. PC、手机、平板等终端设备应使用 `device_type = "endpoint"`，并设置 `endpoint_type`。
3. 非终端设备的 `endpoint_type` 应为 `None`。
4. 虚拟设备应设置 `deployment_type = "virtual"`。
5. 无法判断物理或虚拟时，应使用 `deployment_type = "unknown"`。
6. 不允许强行猜测。

## 默认测试命令

默认质量门禁：

```powershell
pytest
ruff check .
mypy .
```

默认命令不得依赖真实网络或真实 Neo4j。

真实网络和真实 Neo4j 测试应通过明确命令、marker 或单独脚本触发，不能混入默认 `pytest`。

## 禁止事项

1. 不提交真实配置。
2. 不提交真实凭据。
3. 不提交真实测试网段细节。
4. 不提交真实拓扑数据。
5. 不默认开启 SSH。
6. 不高并发直接扫描完整网段。
7. 不把集成测试混进默认单元测试。
8. 不在日志、异常或测试输出中打印密码、Token、community。

## 扩展建议

后续可以增加：

1. `pytest` marker：`unit`、`integration`、`network`。
2. `tests/integration/`：Neo4j 集成测试。
3. `tests/network/`：真实测试网段联调测试。
4. `scripts/`：受控测试脚本，例如 Neo4j 连通性检查、单 IP 扫描、小网段扫描。
5. `scan.exclude_targets`：排除测试网中的 Neo4j 服务器、管理机或不应扫描的地址。
