# 真实测试网段联调结果评估

## 背景

- 日期：2026-05-15
- 分支：`feature/codex-ssh-basic`
- 目的：验证真实测试网络中的扫描、采集、解析和 Neo4j 写入闭环，并为设计侧评估设备类型识别效果提供依据。
- 说明：本文档不记录真实地址、真实凭据、SNMP community、Neo4j 密码或具体设备 IP。

## 执行范围

本次联调使用本地未提交配置文件：

```text
config/config.yaml
```

配置文件已被 `.gitignore` 忽略，未提交到 Git。

执行内容：

1. Conda 环境检查。
2. Neo4j 连通性验证。
3. Neo4j 假数据重复写入验证。
4. 真实测试网段完整扫描。
5. 设备类型识别结果统计。
6. 单 IP 冒烟测试。

## 前置验证

质量门禁已通过：

```text
ruff check .        通过
pytest              83 passed
mypy .              通过
```

Conda 环境：

```text
Python 3.11.15
环境名：topology-discovery-lab
```

## Neo4j 连通性结果

结果：

```text
Neo4j 可连接
默认 database 下 RETURN 1 成功
```

发现的问题：

```text
当前测试 Neo4j/Bolt 协议不支持显式 database selection
```

处理结果：

```text
repository 已增加兼容逻辑：
优先使用配置中的 database；
如果服务端不支持 database selection，则回退到默认 database session。
```

## Neo4j 假数据写入验证

使用文档保留地址段构造假数据，重复写入两次。

验证结果：

```text
Device              2
Interface           2
NetworkSegment      1
BELONGS_TO_SEGMENT  2
CONNECTED_TO        1
```

结论：

```text
Device、Interface、NetworkSegment 和关系写入可用；
MERGE 幂等行为符合预期。
```

## 真实测试网段完整扫描结果

执行结果：

```text
scanned_hosts     508
reachable_hosts   126
snmp_successes     19
ssh_successes       0
devices           508
interfaces        130
links               0
errors            489
```

说明：

- SSH 当前关闭，`ssh_successes = 0` 符合预期。
- 当前阶段尚未实现 LLDP/CDP 链路发现，`links = 0` 符合预期。
- `errors` 主要来自不可达目标和协议采集失败。

## Neo4j 聚合结果

扫描后 Neo4j 聚合统计：

```text
Device                  510
Interface               133
NetworkSegment            3
BELONGS_TO_SEGMENT      510
```

说明：

- `Device` 和 `Interface` 包含早前 Neo4j 假数据写入测试留下的示例节点。
- `NetworkSegment` 和 `BELONGS_TO_SEGMENT` 写入正常。

## 设备类型识别结果

设备类型分布：

```text
unknown  489
server    19
router     1
switch     1
```

部署形态分布：

```text
unknown  508
None       2
```

终端类型分布：

```text
无 endpoint_type 非空记录
```

说明：

- `router` 和 `switch` 主要来自早前假数据写入验证中的示例节点。
- 真实扫描中可识别出的设备主要为 `server`。
- 真实扫描中没有可确认的 endpoint 识别结果。

## unknown 原因拆解

`unknown` 设备状态分布：

```text
offline + icmp   382
partial + icmp   107
```

结论：

```text
大多数 unknown 不是设备识别规则未覆盖导致，
而是没有获得可用于识别的数据。
```

原因：

1. `offline + icmp` 表示目标不可达，没有 SNMP 数据。
2. `partial + icmp` 表示 ICMP 可达，但 SNMP 采集失败。
3. 当前设备识别主要依赖 SNMP `sysDescr`。
4. 没有 `sysDescr/sysObjectID` 时，系统按保守策略设置为 `unknown`。

## SNMP 成功样本

当前获取到 `sysDescr` 的真实设备主要呈现为 Linux 服务器：

```text
sysObjectID: 1.3.6.1.4.1.8072.3.2.10
sysDescr: Linux ...
```

这些设备已被识别为：

```text
device_type = server
deployment_type = unknown
endpoint_type = None
```

## SNMP 失败样本

对一个 `partial + unknown` 设备重新采样：

```text
sample_snmp_success = False
sample_snmp_error   = snmp request failed
```

说明：

```text
该类设备 ICMP 可达，但 SNMP 未成功返回可识别信息。
```

## 单 IP 冒烟测试

从真实配置派生单 IP 临时配置：

```text
tmp/one-host-config.yaml
```

该文件在 ignored 的 `tmp/` 目录下，未提交。

执行结果：

```text
scanned_hosts    1
reachable_hosts  1
snmp_successes   0
ssh_successes    0
devices          1
interfaces       0
links            0
errors           1
stderr           空
```

说明：

- 单 IP 流程可跑通。
- Scapy MAC broadcast warning 已被抑制。

## 已修复的问题

1. Neo4j 旧 Bolt 协议不支持 database selection。
   - 已增加默认 database fallback。
2. 真实网段 SNMP 顺序采集导致整体耗时过长。
   - 已将 SNMP/SSH 采集按 `scan.max_concurrency` 并发执行。
3. Scapy 广播警告输出过多。
   - 已抑制 `scapy.runtime` warning。
4. 设备识别字段缺失。
   - 已增加 `endpoint_type` 和 `deployment_type`。
   - Neo4j 写入已同步新增字段。

## 需要设计侧评估的问题

### 1. unknown 是否应写入 Neo4j

当前行为：

```text
所有扫描目标都会生成 DeviceNode。
不可达目标写入为 offline + unknown。
ICMP 可达但 SNMP 失败写入为 partial + unknown。
```

待评估：

1. 是否应写入不可达目标。
2. 是否应只写入 reachable 设备。
3. 是否需要区分 `HostCandidate` 与 `Device`。
4. 是否需要对 ICMP-only 节点使用不同标签或属性。

### 2. SNMP 成功率低的处理策略

当前现象：

```text
reachable_hosts = 126
snmp_successes  = 19
```

待评估：

1. 是否需要配置多个 SNMP community 或凭据组。
2. 是否需要区分 timeout、认证失败、OID 不支持等错误类型。
3. 是否需要先做 UDP/161 可达性探测。
4. 是否需要为不同网段配置不同 SNMP 参数。

### 3. 设备类型识别数据源优先级

当前主要依据：

```text
SNMP sysDescr
```

待评估是否增加：

1. `sysObjectID` 厂商和设备类型映射。
2. SSH `show version` 输出识别。
3. LLDP/CDP 邻居信息识别。
4. MAC OUI 识别。
5. 接口数量和接口描述识别。

### 4. deployment_type 识别策略

当前行为：

```text
无法确认物理或虚拟时设置为 unknown。
```

待评估：

1. Linux server 是否默认保持 `unknown`。
2. 是否根据 VMware/KVM/QEMU/Hyper-V 等关键词设置 `virtual`。
3. 是否根据 sysObjectID 或 vendor/model 推断 `physical`。

### 5. 真实联调验收指标

建议设计侧明确：

1. 节点写入是否应包含 offline 目标。
2. 设备识别率统计是否以 scanned_hosts、reachable_hosts 还是 SNMP-success hosts 为分母。
3. SNMP 成功率最低期望值。
4. 完整测试网段扫描的最大允许耗时。
5. 是否需要清理或隔离集成测试假数据。

## 建议下一步

1. 设计侧先确认 `unknown/offline/partial` 的图模型策略。
2. 根据真实测试环境补充 SNMP 参数策略。
3. 增加 `sysObjectID` 映射表设计。
4. 决定是否将 SSH `show version` 纳入设备识别。
5. 决定是否需要 Neo4j 清理脚本或测试 database 隔离。
