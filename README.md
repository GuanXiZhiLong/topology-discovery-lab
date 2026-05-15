# topology-discovery-lab

网络拓扑自动发现后端实验项目。

本项目用于验证一条最小可运行链路：读取配置、扫描目标网段、发现存活设备、采集设备与接口信息、生成拓扑快照，并将设备、接口和链路关系写入 Neo4j。

## 项目定位

`topology-discovery-lab` 不是一次性脚本，也不是生产级完整平台。当前阶段重点是建立清晰、可测试、可持续迭代的后端工程骨架。

当前优先闭环：

```text
读取配置
  -> 扫描目标网段
  -> 发现存活设备
  -> 采集设备信息
  -> 解析设备、接口和链路
  -> 生成拓扑快照
  -> 写入 Neo4j
```

## 技术栈

- Python：`>=3.11,<3.12`
- 图数据库：Neo4j
- 配置读取：PyYAML
- 数据模型：Pydantic
- SNMP 采集：pysnmp
- ICMP/ARP 探测：scapy
- SSH 采集：paramiko
- 测试：pytest
- 静态检查：ruff
- 类型检查：mypy

## 当前阶段范围

当前阶段计划实现：

1. 读取 YAML 配置文件。
2. 根据配置扫描指定 IP 或 CIDR 网段。
3. 判断目标设备是否存活。
4. 通过 SNMP 采集设备基础信息。
5. 通过 SNMP 采集接口信息。
6. 通过 SSH 进行只读补充采集。
7. 将采集结果转换为统一拓扑模型。
8. 将设备节点、接口节点和链路关系写入 Neo4j。
9. 提供基础单元测试和核心逻辑测试。

当前阶段暂不实现：

- 前端拓扑图展示
- Kafka、RabbitMQ、Celery
- Prometheus、Loki、Grafana、Elasticsearch
- 分布式任务调度
- 多租户、用户权限、告警系统
- Kubernetes、Helm Chart
- 生产级高可用架构

## 目录结构

当前项目结构：

```text
topology-discovery-lab/
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
│   └── NEXT_TASKS.md
├── services/
│   └── topology_discovery/
└── tests/
```

## 文档导航

- `docs/ARCHITECTURE.md`：项目边界、技术栈、目录结构、模块职责。
- `docs/DESIGN.md`：配置模型、数据模型、协议采集、拓扑解析、Neo4j 图模型。
- `docs/CODE_STYLE.md`：代码风格、接口命名、变量命名、错误处理和测试命名。
- `docs/RELIABILITY.md`：超时、重试、失败隔离、幂等写入。
- `docs/SECURITY.md`：凭据安全、SNMP/SSH/Neo4j 安全、日志脱敏。
- `docs/QUALITY_SCORE.md`：测试策略、质量标准、Review 检查清单。
- `docs/PLANS.md`：开发阶段、里程碑和验收标准。
- `docs/NEXT_TASKS.md`：推荐下一步任务。

## 配置说明

配置样例文件位于：

```text
config/config.example.yaml
```

真实运行时可复制为：

```text
config/config.yaml
```

`config/config.yaml` 不应提交到 Git 仓库。配置中涉及 SNMP community、SSH 密码、Neo4j 密码等敏感信息时，应只保存在本地或安全的密钥管理系统中。

## 本地开发

本项目本地开发默认使用 conda，环境名与项目名一致：

```text
topology-discovery-lab
```

```powershell
conda create -n topology-discovery-lab python=3.11
conda activate topology-discovery-lab
python -c "import sys; print(sys.executable); print(sys.version)"
python -m pip --version
python -m pip install -U pip
```

依赖配置完成后，常用命令：

```powershell
conda run -n topology-discovery-lab python -m pytest
conda run -n topology-discovery-lab python -m ruff check .
conda run -n topology-discovery-lab python -m mypy .
```

## 最小运行方式

真实运行配置不提交到 Git。先复制样例文件到本地配置：

```powershell
Copy-Item config/config.example.yaml config/config.yaml
```

按本地实验环境修改 `config/config.yaml` 中的扫描目标、SNMP、SSH 和 Neo4j 参数后运行：

```powershell
conda run -n topology-discovery-lab python -m services.topology_discovery.main --config config/config.yaml
```

程序只输出聚合统计，不输出完整配置、密码、SNMP community 或 SSH 凭据。

当前阶段 SSH 默认关闭。启用 SSH 前应确认配置中的命令均为只读命令，例如 `show version` 或 `show lldp neighbors detail`。

## 安全提醒

- 不提交真实账号、密码、Token、私钥。
- 不提交真实生产设备 IP、真实生产网段或真实拓扑关系。
- SNMP community 不允许硬编码在业务代码中。
- SSH 默认关闭，只允许执行只读命令。
- Neo4j 查询必须使用参数化 Cypher。
- 日志、异常和测试输出不得暴露敏感信息。
