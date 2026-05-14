from __future__ import annotations

from pathlib import Path

import pytest

from services.topology_discovery.config import ConfigError, load_config


def test_load_config_reads_example_config() -> None:
    config = load_config("config/config.example.yaml")

    assert config.scan.targets == ["192.0.2.0/24"]
    assert config.snmp.version == "2c"
    assert config.ssh.enabled is False
    assert config.neo4j.database == "neo4j"


def test_load_config_rejects_missing_required_section(tmp_path: Path) -> None:
    config_file = tmp_path / "missing.yaml"
    config_file.write_text(
        """
scan:
  targets:
    - "192.0.2.1"
  timeout_seconds: 2
  retry_count: 1
  max_concurrency: 1
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError) as exc_info:
        load_config(str(config_file))

    assert "snmp" in str(exc_info.value)
    assert "dummy-password" not in str(exc_info.value)
    assert "dummy-community" not in str(exc_info.value)


def test_load_config_rejects_invalid_scan_target(tmp_path: Path) -> None:
    config_file = tmp_path / "invalid-target.yaml"
    config_file.write_text(
        """
scan:
  targets:
    - "not-a-network"
  timeout_seconds: 2
  retry_count: 1
  max_concurrency: 64
snmp:
  enabled: true
  version: "2c"
  community: "dummy-community"
  timeout_seconds: 2
  retry_count: 1
  port: 161
ssh:
  enabled: false
  username: ""
  password: ""
  timeout_seconds: 5
  port: 22
  commands: {}
neo4j:
  uri: "bolt://localhost:7687"
  username: "neo4j"
  password: "dummy-password"
  database: "neo4j"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError) as exc_info:
        load_config(str(config_file))

    assert "scan.targets" in str(exc_info.value)
    assert "not-a-network" not in str(exc_info.value)
    assert "dummy-community" not in str(exc_info.value)


def test_load_config_rejects_unsupported_snmp_version(tmp_path: Path) -> None:
    config_file = tmp_path / "invalid-snmp.yaml"
    config_file.write_text(
        """
scan:
  targets:
    - "192.0.2.1"
  timeout_seconds: 2
  retry_count: 1
  max_concurrency: 64
snmp:
  enabled: true
  version: "3"
  community: "dummy-community"
  timeout_seconds: 2
  retry_count: 1
  port: 161
ssh:
  enabled: false
  username: ""
  password: ""
  timeout_seconds: 5
  port: 22
  commands: {}
neo4j:
  uri: "bolt://localhost:7687"
  username: "neo4j"
  password: "dummy-password"
  database: "neo4j"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError) as exc_info:
        load_config(str(config_file))

    assert "snmp.version" in str(exc_info.value)
    assert "dummy-community" not in str(exc_info.value)


def test_load_config_rejects_enabled_ssh_without_username(tmp_path: Path) -> None:
    config_file = tmp_path / "invalid-ssh.yaml"
    config_file.write_text(
        """
scan:
  targets:
    - "192.0.2.1"
  timeout_seconds: 2
  retry_count: 1
  max_concurrency: 64
snmp:
  enabled: true
  version: "2c"
  community: "dummy-community"
  timeout_seconds: 2
  retry_count: 1
  port: 161
ssh:
  enabled: true
  username: ""
  password: "dummy-password"
  timeout_seconds: 5
  port: 22
  commands:
    show_version: "show version"
neo4j:
  uri: "bolt://localhost:7687"
  username: "neo4j"
  password: "dummy-password"
  database: "neo4j"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError) as exc_info:
        load_config(str(config_file))

    assert "ssh" in str(exc_info.value)
    assert "dummy-password" not in str(exc_info.value)
