# 安全设计

## 当前安全目标

1. 不提交真实账号。
2. 不提交真实密码。
3. 不提交真实 Token。
4. 不提交真实私钥。
5. 不提交真实生产设备 IP 清单。
6. 不在日志、异常或测试输出中暴露敏感信息。
7. SSH 只允许执行只读命令。
8. SNMP community 不允许硬编码。
9. Neo4j 密码不允许硬编码。
10. Codex 不允许生成危险设备操作命令。

## 敏感信息定义

以下内容均视为敏感信息：

- 网络设备用户名和密码。
- SNMP community。
- SNMP v3 用户名、认证密码、加密密码。
- SSH 私钥。
- Neo4j 密码。
- API Token。
- 真实生产设备 IP 和真实生产网段。
- 真实拓扑关系。
- 设备序列号。
- 内部主机名和内部机房名称。

## 配置安全

允许提交：

```text
config/config.example.yaml
config/README.md
```

不允许提交：

```text
config/config.yaml
config/prod.yaml
config/real.yaml
config/secrets.yaml
config/*.local.yaml
.env
.env.*
*.pem
*.key
```

`.gitignore` 应包含：

```text
config/config.yaml
config/*.local.yaml
config/*secret*.yaml
.env
.env.*
*.pem
*.key
```

## SNMP 安全

SNMP community 属于敏感信息，不允许硬编码在业务代码中。

不允许：

```python
community = "real-community"
```

允许：

```python
community = config.snmp.community
```

测试中允许使用 `dummy-community` 和 `public`，但不能当作真实生产配置。

错误信息允许：

```text
SNMP authentication failed for target 192.0.2.1
```

错误信息不允许：

```text
SNMP authentication failed with community real-community
```

SNMP v2c 不加密，只适合实验环境、本地测试环境和受控内网环境。后续进入生产级设计时，应优先考虑 SNMP v3、只读账号、限制采集源 IP 和最小权限访问。

## SSH 安全

SSH 默认关闭：

```yaml
ssh:
  enabled: false
```

SSH 模块只允许执行只读命令。

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

SSH 命令必须来自配置文件或受控命令白名单。不允许在代码中随意拼接用户输入为命令。

SSH 错误信息中不允许包含密码、私钥内容、完整连接字符串或可用于攻击的详细认证信息。

## Neo4j 安全

Neo4j 用户名和密码不允许硬编码。

不允许：

```python
GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
```

允许：

```python
GraphDatabase.driver(config.neo4j.uri, auth=(config.neo4j.username, config.neo4j.password))
```

所有 Cypher 查询必须使用参数化查询。

不允许：

```python
query = f"MATCH (d:Device {{ip: '{ip}'}}) RETURN d"
```

允许：

```python
query = "MATCH (d:Device {ip: $ip}) RETURN d"
session.run(query, ip=ip)
```

## 日志安全

当前阶段即使没有正式日志系统，也必须遵守：

1. 不打印密码。
2. 不打印 Token。
3. 不打印 SNMP community。
4. 不打印私钥。
5. 不打印完整配置对象。
6. 不打印真实生产网段。
7. 错误信息应脱敏。

## Codex 安全规则

Codex 开发时必须遵守：

1. 不生成硬编码凭据。
2. 不生成真实生产配置。
3. 不生成危险 SSH 命令。
4. 不把配置样例当作真实配置。
5. 不在测试中连接真实设备。
6. 不在错误信息中暴露敏感字段。
7. 不绕过参数化查询。
8. 不提交 `.env`。
9. 不提交私钥。
10. 不主动引入远程执行能力。
