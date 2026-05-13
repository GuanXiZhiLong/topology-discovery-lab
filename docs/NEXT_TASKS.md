# 下一步任务

## 任务 1：补齐 Python 项目配置

目标：创建可运行的 Python 3.11 项目基础配置。

涉及文件：

```text
pyproject.toml
.python-version
.gitignore
```

要求：

1. Python 版本固定为 3.11。
2. 配置 pytest。
3. 配置 ruff。
4. 配置 mypy。
5. 添加核心依赖。
6. 添加测试命令说明。

验收标准：

1. `pytest` 可运行。
2. `ruff check .` 可运行。
3. `mypy .` 可运行。
4. Python 包路径正确。

## 任务 2：实现数据模型

目标：实现 `models.py`。

涉及文件：

```text
services/topology_discovery/models.py
tests/test_models.py
```

要求：

1. 实现 `AliveHost`。
2. 实现 `DeviceNode`。
3. 实现 `InterfaceNode`。
4. 实现 `LinkEdge`。
5. 实现 `TopologySnapshot`。
6. 实现 `DiscoveryError`。
7. 使用 Pydantic。
8. 编写模型测试。

验收标准：

1. 合法数据可以创建模型。
2. 非法 IP 被拒绝。
3. 非法置信度被拒绝。
4. 缺少必填字段时报错。
5. 测试通过。

## 任务 3：实现配置读取

目标：实现 `config.py`。

涉及文件：

```text
services/topology_discovery/config.py
config/config.example.yaml
tests/test_config.py
```

要求：

1. 读取 YAML。
2. 返回类型化配置。
3. 校验扫描目标。
4. 校验 SNMP 配置。
5. 校验 SSH 配置。
6. 校验 Neo4j 配置。
7. 编写测试。

验收标准：

1. 可以读取 example 配置。
2. 缺少配置时报错。
3. 非法网段时报错。
4. 不打印敏感信息。
5. 测试通过。

## 任务 4：实现 ICMP 扫描骨架

目标：实现 `icmp.py`。

涉及文件：

```text
services/topology_discovery/icmp.py
tests/test_icmp.py
```

要求：

1. 支持 IP 和 CIDR 展开。
2. 支持单个目标探测。
3. 支持超时。
4. 支持失败结果。
5. 支持 mock 测试。
6. 不依赖真实网络。

验收标准：

1. CIDR 可以展开。
2. 单个 IP 可以处理。
3. 失败不会抛出中断整体流程的异常。
4. 返回 `AliveHost`。
5. 测试通过。

## 任务 5：实现 Neo4j Repository 骨架

目标：实现基础 Neo4j 写入层。

涉及文件：

```text
services/topology_discovery/neo4j_repository.py
tests/test_neo4j_repository.py
```

要求：

1. 使用 Neo4j 官方驱动。
2. 使用参数化 Cypher。
3. 使用 `MERGE` 写入设备。
4. 使用 `MERGE` 写入接口。
5. 使用 `MERGE` 写入关系。
6. 不暴露密码。
7. 编写 mock 测试。

验收标准：

1. Cypher 使用参数。
2. 重复写入逻辑幂等。
3. 连接失败有明确错误。
4. 测试通过。
