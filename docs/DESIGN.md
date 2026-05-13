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
- `error: str | None`

### `DeviceNode`

表示网络设备节点。

- `device_id: str`
- `ip: str`
- `hostname: str | None`
- `device_type: str`
- `vendor: str | None`
- `model: str | None`
- `os_version: str | None`
- `sys_descr: str | None`
- `sys_object_id: str | None`
- `status: str`
- `last_seen: datetime`
- `source: str`

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
- `started_at: datetime`
- `finished_at: datetime | None`
- `devices: list[DeviceNode]`
- `interfaces: list[InterfaceNode]`
- `links: list[LinkEdge]`
- `errors: list[DiscoveryError]`

### `DiscoveryError`

表示发现过程中的错误。

- `target: str`
- `stage: str`
- `message: str`
- `recoverable: bool`

错误阶段建议：`config`、`icmp`、`snmp`、`ssh`、`parse`、`neo4j`、`main`。

## 设备类型识别

初期设备类型：

- `router`
- `switch`
- `firewall`
- `server`
- `wireless_ap`
- `unknown`

初期识别规则：

- `sysDescr` 包含 `Switch` -> `switch`
- `sysDescr` 包含 `Router` -> `router`
- `sysDescr` 包含 `Firewall` -> `firewall`
- `sysDescr` 包含 `AP` 或 `Wireless` -> `wireless_ap`
- 其他 -> `unknown`

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

设备写入必须使用：

```cypher
MERGE (d:Device {device_id: $device_id})
SET d.ip = $ip,
    d.hostname = $hostname,
    d.device_type = $device_type,
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

## 最小可运行流程

`main.py` 初期流程：

1. 读取 `config/config.yaml`。
2. 扫描存活主机。
3. 对存活主机执行 SNMP 采集。
4. 如果 SSH 启用，对设备执行 SSH 补充采集。
5. 构建 `TopologySnapshot`。
6. 写入 Neo4j。
7. 输出统计结果。
