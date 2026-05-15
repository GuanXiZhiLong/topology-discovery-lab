# 质量与测试标准

## 测试原则

1. 测试不依赖真实生产设备。
2. 测试不依赖真实生产网段。
3. 测试不使用真实账号密码。
4. 测试优先使用 mock。
5. 核心数据模型必须有测试。
6. 核心解析逻辑必须有测试。
7. 外部连接失败必须有测试。
8. Neo4j 写入逻辑应尽量可 mock。

真实测试网段和测试 Neo4j 的联调策略见 `docs/TESTING.md`。默认 `pytest` 不应依赖真实网络或真实 Neo4j。

## 推荐测试文件

```text
tests/
├── test_config.py
├── test_models.py
├── test_icmp.py
├── test_snmp.py
├── test_ssh.py
├── test_parser.py
└── test_neo4j_repository.py
```

## 测试范围

`test_config.py`：

- 正常配置读取。
- 缺失字段。
- 类型错误。
- 非法网段。
- 敏感配置不被打印。

`test_models.py`：

- `AliveHost`。
- `DeviceNode`。
- `DeviceNode.device_type` 合法值。
- `DeviceNode.endpoint_type` 仅用于终端设备。
- `DeviceNode.deployment_type` 合法值。
- `InterfaceNode`。
- `LinkEdge`。
- `TopologySnapshot`。
- 非法字段校验。

`test_icmp.py`：

- IP 展开。
- 单个 IP 探测。
- 超时处理。
- 不可达处理。
- 并发限制。

`test_snmp.py`：

- SNMP get 结果解析。
- SNMP walk 结果解析。
- 超时处理。
- 认证失败处理。
- OID 缺失处理。

`test_ssh.py`：

- SSH 默认关闭。
- SSH 连接失败。
- SSH 命令执行失败。
- 只读命令校验。
- 禁止危险命令。

`test_parser.py`：

- 设备节点生成。
- 接口节点生成。
- 链路生成。
- 设备去重。
- 接口去重。
- 链路去重。
- 部分失败场景。

`test_neo4j_repository.py`：

- Cypher 使用参数。
- `MERGE` 设备节点。
- `MERGE` 接口节点。
- `MERGE` 关系。
- 连接失败处理。
- 不暴露密码。

## 测试数据原则

允许使用：

```text
192.0.2.1
198.51.100.1
203.0.113.1
example-device
dummy-password
dummy-community
```

不允许使用真实生产 IP、真实生产网段、真实设备名、真实密码、真实 SNMP community 或真实拓扑关系。

## 总体质量原则

1. 正确性优先于性能。
2. 可测试性优先于复杂优化。
3. 清晰结构优先于过度抽象。
4. 可维护性优先于一次性脚本。
5. 安全性优先于开发便利。
6. 可被 Codex 理解优先于炫技式写法。

## 功能正确性指标

| 指标 | 说明 | 目标 |
| --- | --- | --- |
| 配置读取成功率 | 合法配置能否正确读取 | 100% |
| 配置错误识别率 | 非法配置能否明确报错 | 100% |
| 存活探测稳定性 | 单个目标失败是否影响整体 | 不影响 |
| SNMP 采集稳定性 | 单台设备失败是否影响整体 | 不影响 |
| 拓扑模型合法性 | 生成快照是否通过模型校验 | 100% |
| Neo4j 写入幂等性 | 重复写入是否产生重复节点 | 不产生重复 |

## 拓扑质量指标

节点识别率：

```text
成功识别为 DeviceNode 的设备数量 / 存活设备数量
```

初期目标：`>= 60%`

接口识别率：

```text
成功采集接口的设备数量 / SNMP 成功设备数量
```

初期目标：`>= 80%`

链路发现准确率在 LLDP/CDP 实现前不强制；LLDP/CDP 实现后目标为 `>= 90%`。

真实测试网段质量指标应额外记录：

| 指标 | 说明 |
| --- | --- |
| 存活率 | `reachable_hosts / scanned_hosts` |
| SNMP 成功率 | `snmp_successes / reachable_hosts` |
| 设备识别率 | `identified_devices / snmp_successes`，优先用于评估识别规则 |
| unknown 覆盖率 | `unknown_devices / devices` |
| offline unknown 数量 | 用于区分不可达导致的 unknown |
| partial unknown 数量 | 用于区分可达但协议采集失败导致的 unknown |
| 写入覆盖率 | `devices_written / scanned_hosts` |

当 SNMP 成功率较低时，不应简单判定设备识别规则失败，应先区分协议采集失败和识别规则覆盖不足。

## PR 最低合格标准

1. 功能符合任务描述。
2. 测试可以运行。
3. 不破坏已有测试。
4. 不引入安全风险。
5. 不引入暂缓技术栈。
6. 不破坏架构边界。
7. 不降低代码可读性。
8. 不绕过数据模型。
9. 不提交真实凭据。
10. PR 描述清晰。

## PR Review 检查清单

每个 PR 必须检查：

1. 是否符合当前阶段范围。
2. 是否引入暂缓技术栈。
3. 是否符合目录结构。
4. 是否兼容 Python 3.11。
5. 是否存在硬编码密钥。
6. 是否存在真实生产信息。
7. 是否存在没有超时的外部连接。
8. 是否存在裸 `except:`。
9. 是否缺少测试。
10. 是否破坏数据模型。
11. 是否破坏 Neo4j 图模型。
12. 是否把业务逻辑写入错误层级。
13. 是否存在明显重复代码。
14. 是否存在过度抽象。
15. 是否遗漏文档更新。
16. 是否符合 `docs/CODE_STYLE.md` 中的代码风格、接口命名和变量命名规范。
