# 代码风格与接口规范

## 目标

本文档用于统一项目代码风格、接口命名、变量命名、错误处理、测试命名和文档同步规则。

后续实现、Review 和重构都应优先遵守本文档，避免同类概念出现多套命名和多种接口风格。

## Python 基础规范

- Python 版本：`>=3.11,<3.12`。
- 代码格式和基础质量以 `ruff` 为准。
- 类型检查以 `mypy` 为准。
- 函数名、变量名、模块名使用 `snake_case`。
- 类名使用 `PascalCase`。
- 常量使用 `UPPER_SNAKE_CASE`。
- 私有 helper 使用前导下划线，例如 `_normalize_ip`。
- 避免缩写，除非是通用网络缩写，例如 `ip`、`snmp`、`ssh`、`mac`、`oid`。

## 模块命名

模块文件名必须使用小写 `snake_case`。

推荐模块：

```text
config.py
icmp.py
snmp.py
ssh.py
parser.py
models.py
neo4j_repository.py
main.py
```

不推荐：

```text
snmpCollector.py
neo4jRepo.py
topologyParser.py
utils.py
common.py
```

`utils.py`、`common.py` 这类宽泛模块名应尽量避免。确实需要公共 helper 时，应按领域命名，例如 `ip_utils.py` 或 `time_utils.py`，并先确认是否真的需要新增模块。

## 接口命名规范

### 配置读取

配置读取入口使用：

```python
load_config(path: str) -> AppConfig
```

配置模型使用 `Config` 后缀：

```text
AppConfig
ScanConfig
SnmpConfig
SshConfig
Neo4jConfig
```

### 扫描接口

网络扫描函数使用 `scan_*`：

```python
scan_alive_hosts(config: ScanConfig) -> list[AliveHost]
```

内部单目标探测可以使用：

```python
probe_host(...)
```

不推荐混用：

```text
discover_hosts
ping_all
find_alive_devices
```

除非设计文档明确调整，否则对外接口统一使用 `scan_alive_hosts`。

### 采集接口

协议采集函数使用 `collect_*`：

```python
collect_snmp_device_info(host: AliveHost, config: SnmpConfig) -> SnmpDeviceInfo
collect_ssh_device_info(host: AliveHost, config: SshConfig) -> SshDeviceInfo
```

SNMP get/walk 这类底层 helper 可使用：

```python
snmp_get(...)
snmp_walk(...)
```

### 解析接口

拓扑构建使用 `build_*`：

```python
build_topology_snapshot(...) -> TopologySnapshot
```

字符串或原始协议输出解析可使用 `parse_*`：

```python
parse_lldp_neighbors(...)
parse_interface_table(...)
```

去重 helper 使用 `_deduplicate_*`：

```python
_deduplicate_devices(...)
_deduplicate_interfaces(...)
_deduplicate_links(...)
```

### Repository 接口

持久化对外接口使用 `save_*`：

```python
save_snapshot(snapshot: TopologySnapshot) -> None
```

内部幂等写入 helper 使用 `_upsert_*`：

```python
_upsert_device(...)
_upsert_interface(...)
_upsert_link(...)
```

Repository 不直接读取 YAML，不执行扫描，不解析 SNMP 原始结果。

## 数据模型命名

模型命名应表达领域含义，而不是表达存储细节。

- 节点模型使用 `Node` 后缀：`DeviceNode`、`InterfaceNode`。
- 关系模型使用 `Edge` 后缀：`LinkEdge`。
- 配置模型使用 `Config` 后缀：`ScanConfig`、`SnmpConfig`。
- 采集结果模型使用 `Info` 或 `Result` 后缀：`SnmpDeviceInfo`、`SshDeviceInfo`。
- 错误模型统一使用：`DiscoveryError`。
- 一次完整结果统一使用：`TopologySnapshot`。

不要用过于宽泛的模型名：

```text
Data
Item
Record
Result
Node
Edge
```

除非该名称在局部上下文中非常明确。

## 字段命名规范

核心字段统一如下：

| 含义 | 字段名 |
| --- | --- |
| 管理 IP | `ip` |
| 设备唯一标识 | `device_id` |
| 接口唯一标识 | `interface_id` |
| 链路唯一标识 | `link_id` |
| 主机名 | `hostname` |
| 设备类型 | `device_type` |
| 终端类型 | `endpoint_type` |
| 部署形态 | `deployment_type` |
| 厂商 | `vendor` |
| 型号 | `model` |
| 系统版本 | `os_version` |
| SNMP 系统描述 | `sys_descr` |
| SNMP 系统对象 ID | `sys_object_id` |
| 接口名称 | `name` |
| 接口描述 | `description` |
| MAC 地址 | `mac_address` |
| 接口索引 | `if_index` |
| 管理状态 | `admin_status` |
| 运行状态 | `oper_status` |
| 接口速率 | `speed_bps` |
| 状态 | `status` |
| 数据来源 | `source` |
| 首个来源扫描目标 | `source_target` |
| 所有来源扫描目标 | `source_targets` |
| 扫描目标列表 | `scan_targets` |
| 网段唯一标识 | `segment_id` |
| 扫描目标 | `target` |
| CIDR 网段 | `cidr` |
| 最近发现时间 | `last_seen` |
| 开始时间 | `started_at` |
| 完成时间 | `finished_at` |
| 单个错误 | `error` |
| 错误列表 | `errors` |

避免同义字段混用：

```text
host_ip
management_ip
mgmt_ip
device_ip
iface_id
intf_id
mac
```

如确实需要表达不同语义，应先更新 `docs/DESIGN.md`。

## 时间字段规范

- 事件时间使用 `*_at`，例如 `started_at`、`finished_at`。
- 状态更新时间使用 `last_seen`。
- 时间值应使用 timezone-aware `datetime`，除非设计文档明确允许 naive datetime。
- 不要用字符串保存内部时间模型；只有序列化、日志或数据库驱动要求时才转换。

## 状态字段规范

设备状态建议使用：

```text
online
offline
unknown
partial
```

接口状态建议使用：

```text
up
down
unknown
```

不要在不同模块中混用：

```text
active
inactive
ok
failed
enabled
disabled
```

如果新增状态值，必须同步更新 `docs/DESIGN.md` 和相关测试。

## 错误处理规范

单设备、单协议失败优先返回结构化错误，不应中断整体流程。

推荐：

```python
DiscoveryError(
    target=target,
    stage="snmp",
    message="SNMP request timed out",
    recoverable=True,
)
```

允许抛异常的场景：

- 配置文件不存在或格式错误。
- 配置字段类型错误。
- 数据模型校验失败。
- Neo4j 整体连接或写入失败。
- 编程错误，例如不可能出现的内部状态。

禁止：

```python
except:
    ...
```

应使用明确异常类型：

```python
except TimeoutError as exc:
    ...
```

错误信息不得包含：

- SNMP community。
- SSH 密码。
- Neo4j 密码。
- Token。
- 私钥内容。
- 真实生产网段或敏感设备名。

## 函数设计规范

- 外部 I/O 函数必须支持 timeout。
- 网络扫描和协议采集函数不能因为单个目标失败中断整体流程。
- 核心解析函数应尽量是纯函数。
- 解析函数不执行网络 I/O。
- Repository 函数不读取 YAML。
- 采集层不写 Neo4j。
- `main.py` 只做流程编排，不堆叠协议细节或复杂 Cypher。
- 函数参数优先使用配置对象和模型对象，避免传入松散的 `dict`。
- 返回值优先使用明确模型，避免返回结构不稳定的 `dict`。

## 日志和输出规范

当前阶段没有正式日志系统时，也应遵守：

- 不打印完整配置对象。
- 不打印密码、Token、community、私钥。
- 不打印真实生产网段。
- 面向用户的统计输出应聚合，不输出敏感明细。
- 错误输出应说明阶段、目标和可恢复性，但必须脱敏。

## 测试命名规范

测试文件命名：

```text
test_<module>.py
```

测试函数命名：

```text
test_<行为>_<场景>
```

示例：

```python
def test_load_config_valid_file() -> None:
    ...

def test_build_topology_snapshot_deduplicates_devices() -> None:
    ...
```

fixture 命名：

```text
sample_*
mock_*
```

示例：

```python
sample_alive_host
sample_snmp_device_info
mock_neo4j_session
```

测试数据只能使用文档允许的示例数据：

```text
192.0.2.1
198.51.100.1
203.0.113.1
example-device
dummy-password
dummy-community
```

测试不得依赖真实网络设备、真实生产网段或真实凭据。

## Cypher 规范

所有 Cypher 必须参数化。

允许：

```python
query = "MATCH (d:Device {ip: $ip}) RETURN d"
session.run(query, ip=ip)
```

禁止：

```python
query = f"MATCH (d:Device {{ip: '{ip}'}}) RETURN d"
```

写入使用 `MERGE` 保证幂等。

内部写入 helper 推荐命名：

```text
_upsert_device
_upsert_interface
_upsert_link
```

## 文档同步规则

- 修改模块职责或目录结构时，同步更新 `docs/ARCHITECTURE.md`。
- 修改配置、模型、接口、图模型时，同步更新 `docs/DESIGN.md`。
- 修改超时、重试、失败隔离、幂等策略时，同步更新 `docs/RELIABILITY.md`。
- 修改凭据、日志、SNMP、SSH、Neo4j 安全行为时，同步更新 `docs/SECURITY.md`。
- 修改测试要求、质量门禁或 Review 标准时，同步更新 `docs/QUALITY_SCORE.md`。
- 修改开发阶段或下一步任务时，同步更新 `docs/PLANS.md` 或 `docs/NEXT_TASKS.md`。

## Review 检查点

Review 时应检查：

1. 命名是否符合本文档。
2. 接口是否符合 `docs/DESIGN.md`。
3. 模块职责是否符合 `docs/ARCHITECTURE.md`。
4. 错误处理是否结构化且脱敏。
5. 外部 I/O 是否有 timeout。
6. 测试命名和测试数据是否符合规范。
7. 是否引入宽泛 helper 模块或过度抽象。
8. 是否需要同步更新文档。
