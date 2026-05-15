# 详细设计

## 配置设计

配置样例文件：

```text
config/config.example.yaml
```

真实运行配置可复制为：

```text
config/config.yaml
```

`config.yaml` 不应提交到 Git 仓库。

示例结构：

```yaml
scan:
  targets:
    - "192.0.2.0/24"
  timeout_seconds: 2
  retry_count: 1
  max_concurrency: 64

snmp:
  enabled: true
  version: "2c"
  community: "public"
  timeout_seconds: 2
  retry_count: 1
  port: 161

ssh:
  enabled: false
  username: ""
  password: ""
  timeout_seconds: 5
  port: 22
  commands:
    show_version: "show version"
    show_lldp_neighbors: "show lldp neighbors detail"

neo4j:
  uri: "bolt://localhost:7687"
  username: "neo4j"
  password: "change-me"
  database: "neo4j"
```

### 配置模型

`ScanConfig`：

- `targets: list[str]`
- `timeout_seconds: float`
- `retry_count: int`
- `max_concurrency: int`

`SnmpConfig`：

- `enabled: bool`
- `version: str`，初期支持 `2c`
- `community: str`
- `timeout_seconds: float`
- `retry_count: int`
- `port: int`，默认 161

`SshConfig`：

- `enabled: bool`
- `username: str`
- `password: str`
- `timeout_seconds: float`
- `port: int`
- `commands: dict[str, str]`

`Neo4jConfig`：

- `uri: str`
- `username: str`
- `password: str`
- `database: str`

## 数据模型

### `AliveHost`

表示一个被探测为存活的主机。

- `ip: str`
- `reachable: bool`
- `latency_ms: float | None`
- `discovered_by: str`
- `source_target: str | None`
- `source_targets: list[str]`
- `error: str | None`

`source_target` 表示该主机最先由哪个配置目标发现，例如 `192.0.2.0/24`。

`source_targets` 表示该主机匹配到的所有配置目标。多个网段重叠时，同一个 IP 可能同时属于多个 target，解析和写入时应保留这些来源信息。

### `DeviceNode`

表示网络设备节点。

- `device_id: str`
- `ip: str`
- `hostname: str | None`
- `device_type: str`
- `endpoint_type: str | None`
- `deployment_type: str`
- `vendor: str | None`
- `model: str | None`
- `os_version: str | None`
- `sys_descr: str | None`
- `sys_object_id: str | None`
- `status: str`
- `last_seen: datetime`
- `source: str`

`status` 允许值：

| 值 | 含义 |
| --- | --- |
| `online` | 设备可达，且关键采集信息成功获取。 |
| `offline` | 设备当前不可达，通常用于增量更新或离线标记。 |
| `unknown` | 设备状态无法判断，或只有不完整的候选信息。 |
| `partial` | 设备部分可发现，例如 ICMP 可达但 SNMP/SSH 部分失败，仍保留基础节点。 |

`device_type` 表示设备在网络中的主要角色。

`endpoint_type` 仅在 `device_type = "endpoint"` 时使用。非终端设备应设置为 `None`。

`deployment_type` 表示设备部署形态，而不是网络角色。

`device_id` 生成优先级：

1. 稳定设备序列号。
2. SNMP engine ID。
3. hostname + 管理 IP。
4. 管理 IP。

初期可以使用：

```text
device:{ip}
```

### `InterfaceNode`

表示网络设备接口。

- `interface_id: str`
- `device_id: str`
- `name: str`
- `description: str | None`
- `mac_address: str | None`
- `if_index: int | None`
- `admin_status: str | None`
- `oper_status: str | None`
- `speed_bps: int | None`
- `last_seen: datetime`

接口 ID 规则：

```text
interface:{device_id}:{if_index}
interface:{device_id}:{name}
```

### `LinkEdge`

表示设备或接口之间的连接关系。

- `link_id: str`
- `source_device_id: str`
- `target_device_id: str`
- `source_interface_id: str | None`
- `target_interface_id: str | None`
- `discovery_method: str`
- `confidence: float`
- `last_seen: datetime`

链路 ID 应对两端 ID 排序：

```text
link:{min_endpoint}:{max_endpoint}
```

### `TopologySnapshot`

表示一次完整拓扑发现结果。

- `snapshot_id: str`
- `scan_targets: list[str]`
- `started_at: datetime`
- `finished_at: datetime | None`
- `devices: list[DeviceNode]`
- `interfaces: list[InterfaceNode]`
- `links: list[LinkEdge]`
- `errors: list[DiscoveryError]`

`scan_targets` 记录本次扫描配置中的原始 IP 或 CIDR 目标，用于后续审计、统计和图数据库中的网段归属关系。

### `NetworkSegmentNode`

表示一个扫描目标网段或单个扫描目标。

- `segment_id: str`
- `target: str`
- `cidr: str | None`
- `source: str`
- `last_seen: datetime`

`segment_id` 生成规则：

```text
segment:{normalized_target}
```

其中 `normalized_target` 应使用标准化后的 IP 或 CIDR 字符串。示例：

```text
segment:192.0.2.0/24
segment:192.0.2.1
```

对于单个 IP，`cidr` 可以为 `None`，`target` 保留原始配置值或标准化后的 IP。

### `DiscoveryError`

表示发现过程中的错误。

- `target: str`
- `stage: str`
- `message: str`
- `recoverable: bool`

错误阶段建议：`config`、`icmp`、`snmp`、`ssh`、`parse`、`neo4j`、`main`。

## 设备识别设计

设备识别拆分为三个维度：

1. `device_type`：设备在网络中的主要角色。
2. `endpoint_type`：终端设备的细分类别。
3. `deployment_type`：设备是物理、虚拟还是未知部署形态。

不允许将这些维度组合成单个枚举，例如 `physical_switch`、`virtual_firewall`、`mobile_phone`。

### 设备角色 `device_type`

当前阶段推荐设备角色：

- `router`
- `switch`
- `firewall`
- `wireless_ap`
- `server`
- `endpoint`
- `printer`
- `storage`
- `camera`
- `iot`
- `unknown`

初期最小实现可以只覆盖：

```text
router
switch
firewall
wireless_ap
server
endpoint
unknown
```

`device_type` 识别依据：

1. SNMP `sysDescr`。
2. SNMP `sysObjectID`。
3. hostname 命名规则。
4. MAC OUI。
5. 接口数量和接口类型。
6. LLDP/CDP 邻居信息。
7. SSH `show version` 输出。

初期简单规则：

- `sysDescr` 包含 `Switch` -> `switch`
- `sysDescr` 包含 `Router` -> `router`
- `sysDescr` 包含 `Firewall` -> `firewall`
- `sysDescr` 包含 `AP` 或 `Wireless` -> `wireless_ap`
- `sysDescr` 包含 `Server`、`Linux`、`Windows Server` -> `server`
- `sysDescr` 包含 `Windows`、`macOS`、`Android`、`iOS` -> `endpoint`
- 其他 -> `unknown`

### 终端类型 `endpoint_type`

`endpoint_type` 仅用于 `device_type = "endpoint"` 的设备。

推荐值：

- `pc`
- `laptop`
- `workstation`
- `phone`
- `tablet`
- `unknown`

非终端设备应设置为 `None`。

示例：

```text
device_type = endpoint
endpoint_type = pc
deployment_type = physical
```

```text
device_type = firewall
endpoint_type = None
deployment_type = virtual
```

### 部署形态 `deployment_type`

推荐值：

- `physical`
- `virtual`
- `unknown`

默认值：

```text
deployment_type = unknown
```

`deployment_type` 识别依据：

1. `sysDescr` 包含 `VMware`、`Virtual`、`KVM`、`QEMU`、`Hyper-V`、`VirtualBox`。
2. `sysObjectID` 属于已知虚拟化厂商或虚拟设备。
3. MAC OUI 属于虚拟化厂商。
4. `vendor`、`model` 明确显示虚拟设备。
5. 接口描述包含虚拟网卡特征。

可推断为 `physical` 的依据：

1. SNMP 返回明确硬件型号。
2. `sysObjectID` 匹配实体网络设备厂商。
3. LLDP/CDP 能发现物理邻居。
4. 接口形态符合物理交换机、路由器或防火墙。

无法可靠判断时必须使用 `unknown`，不应强行猜测。

## SNMP 采集设计

初期采集 OID：

| 信息 | OID | 说明 |
| --- | --- | --- |
| sysDescr | `1.3.6.1.2.1.1.1.0` | 系统描述 |
| sysObjectID | `1.3.6.1.2.1.1.2.0` | 系统对象 ID |
| sysName | `1.3.6.1.2.1.1.5.0` | 系统名称 |
| ifIndex | `1.3.6.1.2.1.2.2.1.1` | 接口索引 |
| ifDescr | `1.3.6.1.2.1.2.2.1.2` | 接口描述 |
| ifSpeed | `1.3.6.1.2.1.2.2.1.5` | 接口速率 |
| ifPhysAddress | `1.3.6.1.2.1.2.2.1.6` | 接口 MAC |
| ifAdminStatus | `1.3.6.1.2.1.2.2.1.7` | 管理状态 |
| ifOperStatus | `1.3.6.1.2.1.2.2.1.8` | 运行状态 |

SNMP 失败时返回包含错误信息的结果，不影响其他设备采集，不在错误中暴露 community。

## SSH 采集设计

SSH 只作为补充采集方式，默认关闭，只允许执行只读命令。

允许示例：

- `show version`
- `show interfaces`
- `show lldp neighbors detail`
- `show cdp neighbors detail`
- `show ip arp`
- `show mac address-table`

禁止示例：

- `configure terminal`
- `reload`
- `write erase`
- `delete`
- `copy running-config startup-config`
- `shutdown`
- `no shutdown`
- `interface`
- `vlan`
- `ip route`

## 拓扑解析设计

### 多网段扫描规则

`ScanConfig.targets` 支持多个目标，每个目标可以是单个 IP 或 CIDR。

扫描展开规则：

1. 按配置顺序展开每个 target。
2. 对展开后的 IP 进行去重，避免重叠网段导致同一 IP 被重复探测。
3. 如果同一 IP 属于多个 target，`AliveHost.source_targets` 应记录所有来源 target。
4. `AliveHost.source_target` 保留第一个命中的 target，作为兼容字段和简化显示字段。
5. `TopologySnapshot.scan_targets` 保留本次扫描使用的原始 target 列表。
6. 单个 target 格式非法时应作为配置错误处理，不应进入扫描阶段。

多网段场景中，设备去重不应依赖网段归属，而应依赖 `device_id`、管理 IP 或后续更稳定的设备标识。

设备去重优先级：

1. `device_id`
2. 管理 IP
3. hostname + vendor
4. sysObjectID + sysName

接口去重优先级：

1. `interface_id`
2. `device_id + if_index`
3. `device_id + name`

链路去重优先级：

1. 排序后的两个接口 ID。
2. 排序后的两个设备 ID。
3. discovery method + endpoints。

链路置信度：

| 发现方式 | 置信度 |
| --- | --- |
| LLDP | 1.0 |
| CDP | 0.95 |
| 手动配置 | 0.9 |
| MAC 表推断 | 0.7 |
| ARP 推断 | 0.6 |
| IP 网段推断 | 0.3 |

当前阶段若没有 LLDP/CDP，可以先只写入设备节点和接口节点，链路功能后续扩展。

## Neo4j 图模型

节点标签：

- `Device`
- `Interface`
- `DiscoveryRun`
- `NetworkSegment`

关系类型：

- `HAS_INTERFACE`
- `CONNECTED_TO`
- `DISCOVERED_IN`
- `BELONGS_TO_SEGMENT`

### `NetworkSegment` 节点属性

| 属性 | 说明 |
| --- | --- |
| `segment_id` | 唯一 ID |
| `target` | 配置中的扫描目标或标准化后的目标 |
| `cidr` | CIDR 网段，单个 IP 时可以为空 |
| `source` | 数据来源，例如 `config` |
| `last_seen` | 最近一次扫描时间 |

网段写入 Cypher 示例：

```cypher
MERGE (s:NetworkSegment {segment_id: $segment_id})
SET s.target = $target,
    s.cidr = $cidr,
    s.source = $source,
    s.last_seen = $last_seen
```

### `BELONGS_TO_SEGMENT` 关系

结构：

```cypher
(:Device)-[:BELONGS_TO_SEGMENT]->(:NetworkSegment)
```

含义：

1. 一个设备可以属于多个扫描目标。
2. 多个重叠网段命中同一设备时，不重复创建设备节点，但可以建立多个网段归属关系。
3. 重复扫描同一 target 不应重复创建关系。
4. 网段归属用于查询和统计，不应作为设备唯一身份判断依据。

设备写入必须使用：

```cypher
MERGE (d:Device {device_id: $device_id})
SET d.ip = $ip,
    d.hostname = $hostname,
    d.device_type = $device_type,
    d.endpoint_type = $endpoint_type,
    d.deployment_type = $deployment_type,
    d.vendor = $vendor,
    d.model = $model,
    d.os_version = $os_version,
    d.status = $status,
    d.sys_descr = $sys_descr,
    d.sys_object_id = $sys_object_id,
    d.last_seen = $last_seen,
    d.source = $source
```

接口关系：

```cypher
(:Device)-[:HAS_INTERFACE]->(:Interface)
```

推荐最终链路：

```cypher
(:Interface)-[:CONNECTED_TO]->(:Interface)
```

初期可简化为：

```cypher
(:Device)-[:CONNECTED_TO]->(:Device)
```

## 核心接口

```python
def load_config(path: str) -> AppConfig:
    ...

def scan_alive_hosts(config: ScanConfig) -> list[AliveHost]:
    ...

def collect_snmp_device_info(host: AliveHost, config: SnmpConfig) -> SnmpDeviceInfo:
    ...

def collect_ssh_device_info(host: AliveHost, config: SshConfig) -> SshDeviceInfo:
    ...

def build_topology_snapshot(
    alive_hosts: list[AliveHost],
    snmp_results: list[SnmpDeviceInfo],
    ssh_results: list[SshDeviceInfo],
) -> TopologySnapshot:
    ...

class Neo4jTopologyRepository:
    def save_snapshot(self, snapshot: TopologySnapshot) -> None:
        ...
```

`save_snapshot` 还应负责写入本次扫描涉及的 `NetworkSegment` 节点，并根据 `AliveHost.source_targets`、`TopologySnapshot.scan_targets` 或解析阶段保留的归属信息建立 `BELONGS_TO_SEGMENT` 关系。

## 最小可运行流程

`main.py` 初期流程：

1. 读取 `config/config.yaml`。
2. 扫描存活主机。
3. 对存活主机执行 SNMP 采集。
4. 如果 SSH 启用，对设备执行 SSH 补充采集。
5. 构建 `TopologySnapshot`。
6. 写入 Neo4j。
7. 输出统计结果。
