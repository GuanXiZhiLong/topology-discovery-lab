# 架构设计

## 项目定位

`topology-discovery-lab` 是一个网络拓扑自动发现后端实验项目。

项目目标是通过 Python 后端服务自动扫描指定网络范围，发现存活设备，采集设备信息、接口信息和链路信息，并将最终拓扑结构写入 Neo4j 图数据库。

当前优先实现核心闭环：

```text
读取配置
  -> 扫描目标网段
  -> 发现存活设备
  -> 采集设备信息
  -> 解析设备、接口和链路
  -> 生成拓扑快照
  -> 写入 Neo4j
  -> 支持后续查询和可视化扩展
```

## 技术栈

- 后端语言：Python 3.11
- Python 版本约束：`>=3.11,<3.12`
- 本地开发环境：conda，环境名固定为 `topology-discovery-lab`
- 图数据库：Neo4j
- 配置读取：`pyyaml`
- 数据模型校验：`pydantic`
- ICMP/ARP 探测：`scapy`
- SNMP 采集：`pysnmp`
- SSH 采集：`paramiko`
- 测试框架：`pytest`
- 静态检查：`ruff`
- 类型检查：`mypy`

除非用户明确要求，当前阶段不主动引入 FastAPI、Celery、Kafka、RabbitMQ、Prometheus、Elasticsearch、Redis、SQLAlchemy、前端框架或 Kubernetes 相关依赖。

## 当前实际目录

当前仓库已存在基础目录：

```text
topology-discovery-lab/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .python-version
├── .gitignore
├── .github/
│   └── pull_request_template.md
├── config/
│   └── config.example.yaml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DESIGN.md
│   ├── PLANS.md
│   ├── QUALITY_SCORE.md
│   ├── RELIABILITY.md
│   ├── SECURITY.md
│   ├── CODEX_WORKFLOW.md
│   └── NEXT_TASKS.md
├── services/
│   └── topology_discovery/
└── tests/
```

设计文档中的推荐代码结构可以后续逐步补齐。除非任务明确要求，不应为了对齐目录而做大规模移动。

## 推荐模块结构

推荐 Python 包内模块：

```text
services/topology_discovery/
├── __init__.py
├── main.py
├── config.py
├── icmp.py
├── snmp.py
├── ssh.py
├── parser.py
├── models.py
└── neo4j_repository.py
```

## 系统分层

系统分为：

1. 配置层。
2. 协议采集层。
3. 数据解析层。
4. 拓扑模型层。
5. 数据存储层。
6. 程序编排层。

总体调用方向：

```text
main.py
  -> config.py
  -> icmp.py / snmp.py / ssh.py
  -> parser.py
  -> models.py
  -> neo4j_repository.py
  -> Neo4j
```

## 模块职责

### `config.py`

负责读取 YAML、校验配置结构、提供类型化配置对象、处理默认值和配置错误提示。

禁止执行网络扫描、连接 Neo4j、解析拓扑关系或写数据库。

### `icmp.py`、`snmp.py`、`ssh.py`

负责从网络设备获取原始信息，返回结构化采集结果，处理协议级异常。

禁止直接生成最终拓扑图或写 Neo4j。

### `parser.py`

负责将 ICMP、SNMP、SSH 结果合并为设备节点、接口节点、链路关系和统一拓扑快照。

禁止执行协议采集、连接 Neo4j 或读取 YAML 配置。

### `models.py`

负责定义统一数据模型，校验节点、接口、链路和错误数据。

禁止连接外部设备、连接 Neo4j 或承担业务流程编排。

### `neo4j_repository.py`

负责 Neo4j 连接管理、设备写入、接口写入、关系写入、查询当前拓扑和增量更新。

必须使用参数化 Cypher 和 `MERGE` 保证幂等。

### `main.py`

负责加载配置、调用扫描和采集模块、生成快照、写入 Neo4j、输出统计结果。

禁止堆叠大量协议细节、复杂 Cypher 或核心数据模型定义。

## 依赖方向

允许：

- `main.py` 可以调用所有模块。
- `parser.py` 可以依赖 `models.py`。
- `neo4j_repository.py` 可以依赖 `models.py`。
- `icmp.py`、`snmp.py`、`ssh.py` 可以依赖 `models.py` 中的采集结果模型。
- `models.py` 不依赖其他业务模块。
- `config.py` 不依赖协议采集模块。

禁止：

```text
models.py -> parser.py
models.py -> neo4j_repository.py
parser.py -> neo4j_repository.py
icmp.py -> neo4j_repository.py
snmp.py -> neo4j_repository.py
ssh.py -> neo4j_repository.py
config.py -> main.py
```
