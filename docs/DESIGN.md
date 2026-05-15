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

### 识别数据源优先级

设备识别不应长期只依赖 SNMP `sysDescr`。真实测试发现，当 ICMP 可达但 SNMP 失败时，设备会大量停留在 `unknown`。

推荐识别数据源优先级：

1. 显式人工标注或配置覆盖。
2. SNMP `sysObjectID` 厂商和设备类型映射。
3. SNMP `sysDescr`、`sysName`。
4. LLDP/CDP 邻居信息。
5. SSH `show version`、`show lldp neighbors detail`、`show cdp neighbors detail`。
6. MAC OUI。
7. 接口数量、接口描述和接口速率特征。
8. hostname 命名规则。
9. 保守回退为 `unknown`。

识别规则必须保守：低置信度数据只能辅助判断，不应覆盖更高优先级来源。

### `sysObjectID` 映射表设计

后续应引入受控映射表，用于提升 SNMP 成功设备的识别精度。

推荐映射内容：

```text
sys_object_id_prefix
vendor
device_type
deployment_type
model_family
confidence
```

示例规则：

```text
1.3.6.1.4.1.8072 -> vendor=net-snmp, device_type=server, deployment_type=unknown
```

映射表应作为代码内受控数据或配置样例维护，不应包含真实生产设备序列号或内部资产信息。

### LLDP/CDP 识别增强

LLDP/CDP 不只用于链路发现，也可用于提升设备识别精度。

可使用的信息：

1. 本端接口和远端接口。
2. 远端系统名称。
3. 远端系统描述。
4. 远端 capabilities。
5. 远端 chassis ID。
6. 远端 management address。

识别用途：

1. `capabilities` 包含 bridge 时，可辅助识别为 `switch`。
2. `capabilities` 包含 router 时，可辅助识别为 `router`。
3. LLDP/CDP 邻居存在物理接口互联时，可辅助判断 `deployment_type = physical`，但不能单独作为强制判断依据。
4. LLDP/CDP 可帮助发现只在邻居表中出现、但 SNMP 直接采集失败的设备候选。

当前阶段可以先实现 SNMP LLDP/CDP OID 采集设计，SSH LLDP/CDP 作为补充。

### SNMP 失败分类设计

SNMP 失败不应只记录泛化的 `snmp request failed`。

建议错误类型：

```text
snmp_timeout
snmp_auth_failed
snmp_transport_unreachable
snmp_oid_unsupported
snmp_parse_error
snmp_unknown_error
```

错误信息必须脱敏，不得包含 community。

### SNMP 凭据策略

真实测试发现 SNMP 成功率可能显著低于 ICMP 可达率。后续设计应支持更灵活的 SNMP 参数策略。

推荐演进方向：

1. 当前阶段保留单一 `snmp.community`。
2. 下一阶段支持多个只读 community 或 SNMP credential profile。
3. 支持按 target 或网段选择不同 SNMP profile。
4. 支持记录每个 profile 的成功/失败统计，但不记录明文凭据。

配置设计可演进为：

```yaml
snmp:
  enabled: true
  profiles:
    - name: "default"
      version: "2c"
      community: "from-local-config"
      timeout_seconds: 2
      retry_count: 1
      port: 161
```

在实现 profile 前，不应破坏现有 `snmp.community` 配置。

### UDP/161 可达性探测

为了区分“ICMP 可达但 SNMP 不可用”和“SNMP 请求超时”，后续可增加 UDP/161 可达性或 SNMP 预探测。

该探测只能作为诊断辅助，不应替代正式 SNMP 采集结果。

### unknown 写入策略

真实测试中大量 `unknown` 来自不可达或 SNMP 失败，不一定是识别规则不足。

当前阶段策略：

1. 继续保留扫描目标生成的 `DeviceNode`，以表达扫描覆盖范围。
2. 不可达目标写入 `status = offline`、`device_type = unknown`。
3. ICMP 可达但 SNMP/SSH 失败写入 `status = partial`、`device_type = unknown`。
4. 设备识别率统计不应以全部 `scanned_hosts` 为唯一分母。

统计口径：

1. 扫描覆盖率：`scanned_hosts`。
2. 存活率：`reachable_hosts / scanned_hosts`。
3. SNMP 成功率：`snmp_successes / reachable_hosts`。
4. 设备识别率：优先使用 `identified_devices / snmp_successes`。
5. 拓扑写入覆盖率：`devices_written / scanned_hosts`。

未来如需更严格地区分候选主机和确认设备，可引入 `HostCandidate` 标签或模型，但当前阶段先不引入，避免扩大范围。

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

### LLDP/CDP 邻居采集

当前阶段 SNMP 采集结果可以包含邻居表信息：

```text
SnmpDeviceInfo.neighbors: list[SnmpNeighborInfo]
SnmpDeviceInfo.collection_errors: list[str]
```

`SnmpNeighborInfo` 字段：

- `protocol: str`，当前允许 `lldp`、`cdp`
- `local_interface_index: int | None`
- `local_interface_name: str | None`
- `remote_chassis_id: str | None`
- `remote_port_id: str | None`
- `remote_system_name: str | None`
- `remote_system_description: str | None`
- `remote_management_address: str | None`
- `capabilities: str | None`

解析链路时必须保持保守：

1. 远端管理 IP 命中已发现设备时，可以生成链路。
2. 或远端系统名精确命中已发现设备 hostname 时，可以生成链路。
3. 不仅凭不完整邻居字段创建新的确认设备节点。
4. LLDP/CDP 采集失败只记录 `collection_errors`，不影响基础 SNMP 设备和接口结果。
5. LLDP 生成链路时 `discovery_method = "lldp"`，`confidence = 1.0`。
6. CDP 生成链路时 `discovery_method = "cdp"`，`confidence = 0.95`。

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

### 分层发现策略

网络自动发现应采用分层递进策略，先保证基础发现闭环，再对无法识别或信息不足的设备启用更高级的数据源。

发现层级：

1. 基础发现层。
2. 标准采集层。
3. 补充识别层。
4. 高级拓扑发现层。

基础发现层：

- 目标展开：单 IP、CIDR、多网段。
- 存活探测：ICMP/ARP。
- 结果：生成 `AliveHost`，记录可达性、延迟、来源 target。

标准采集层：

- SNMP 基础信息：`sysDescr`、`sysObjectID`、`sysName`。
- SNMP 接口信息：接口名称、状态、MAC、速率。
- 结果：生成 `DeviceNode` 和 `InterfaceNode`。

补充识别层：

- SSH 只读命令，例如 `show version`。
- `sysObjectID` 映射表。
- MAC OUI。
- hostname 规则。
- 接口数量、接口描述、接口速率特征。
- 触发条件：基础发现可达但 SNMP 失败、SNMP 数据不足、`device_type = unknown`、`deployment_type = unknown`。

高级拓扑发现层：

- LLDP。
- CDP。
- 路由表。
- ARP 表。
- MAC 地址表。
- 触发条件：设备已确认可达，但链路为 0、邻居关系不足、设备类型无法确认、需要跨网段拓扑关系。

原则：

1. 不应直接依赖高级发现替代基础发现。
2. 高级发现只用于补充识别精度、链路发现和邻居推断。
3. 高级发现失败不能影响基础发现结果写入。
4. 每一层都必须有 timeout、错误隔离和脱敏错误记录。
5. SSH 仍默认关闭；启用前必须确认命令只读。
6. 真实测试报告必须记录本次启用了哪些发现层级。

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

### 路由表、ARP 表和 MAC 表增强

当 LLDP/CDP 不可用或覆盖不足时，可以使用路由表、ARP 表和 MAC 地址表进行补充发现。

使用原则：

1. 路由表用于发现三层邻接关系、下一跳和跨网段路径线索。
2. ARP 表用于发现本地二层网段内的 IP/MAC 候选主机。
3. MAC 地址表用于发现交换机端口上的二层终端或下联设备。
4. 这些数据属于推断来源，置信度低于 LLDP/CDP。
5. 推断链路必须标记 `discovery_method`，例如 `route_table`、`arp_table`、`mac_table`。
6. 推断链路不得覆盖 LLDP/CDP 发现的高置信度链路。
7. 推断出的未知主机可以进入候选设备流程，但应保守设置为 `device_type = unknown`，直到有更多证据。

当前阶段优先级：

1. 先实现基础发现和 SNMP 采集。
2. 再实现 LLDP/CDP。
3. 再考虑路由表、ARP 表、MAC 表推断。

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
