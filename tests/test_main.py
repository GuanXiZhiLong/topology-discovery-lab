from __future__ import annotations

from typing import Any

import pytest

from services.topology_discovery.config import (
    AppConfig,
    Neo4jConfig,
    ScanConfig,
    SnmpConfig,
    SshConfig,
)
from services.topology_discovery.main import (
    DiscoverySummary,
    LatestTopologyCounts,
    fetch_latest_topology_counts,
    main,
    run_discovery,
)
from services.topology_discovery.models import (
    AliveHost,
    SnmpDeviceInfo,
    SshDeviceInfo,
    TopologySnapshot,
)


def test_run_discovery_saves_snapshot_and_returns_summary() -> None:
    repository = FakeRepository()

    summary = run_discovery(
        _config(),
        scan_hosts=_scan_hosts,
        collect_snmp=_collect_snmp_success,
        collect_ssh=_collect_ssh_success,
        repository_factory=lambda config: repository,
    )

    assert summary == DiscoverySummary(
        scanned_hosts=2,
        reachable_hosts=1,
        snmp_successes=1,
        ssh_successes=0,
        devices=2,
        interfaces=0,
        links=0,
        errors=1,
    )
    assert repository.saved_snapshot is not None
    assert repository.saved_snapshot.scan_targets == ["192.0.2.1"]
    assert repository.closed is True


def test_run_discovery_collects_ssh_when_enabled() -> None:
    calls: list[str] = []

    def collect_ssh(host: AliveHost, config: SshConfig) -> SshDeviceInfo:
        calls.append(host.ip)
        return _collect_ssh_success(host, config)

    summary = run_discovery(
        _config(ssh_enabled=True),
        scan_hosts=_scan_hosts,
        collect_snmp=_collect_snmp_success,
        collect_ssh=collect_ssh,
        repository_factory=lambda config: FakeRepository(),
    )

    assert calls == ["192.0.2.1"]
    assert summary.ssh_successes == 1


def test_run_discovery_records_ssh_failure_in_summary() -> None:
    summary = run_discovery(
        _config(ssh_enabled=True),
        scan_hosts=_scan_hosts,
        collect_snmp=_collect_snmp_success,
        collect_ssh=_collect_ssh_failure,
        repository_factory=lambda config: FakeRepository(),
    )

    assert summary.ssh_successes == 0
    assert summary.errors == 2


def test_run_discovery_saves_partial_snapshot_when_snmp_fails() -> None:
    repository = FakeRepository()

    summary = run_discovery(
        _config(),
        scan_hosts=_scan_hosts,
        collect_snmp=_collect_snmp_failure,
        repository_factory=lambda config: repository,
    )

    assert summary.snmp_successes == 0
    assert summary.devices == 2
    assert summary.errors == 2
    assert repository.saved_snapshot is not None
    assert repository.saved_snapshot.devices[0].status == "partial"


def test_run_discovery_converts_snmp_exception_to_structured_error() -> None:
    repository = FakeRepository()

    summary = run_discovery(
        _config(),
        scan_hosts=_scan_hosts,
        collect_snmp=_raise_snmp_error,
        repository_factory=lambda config: repository,
    )

    assert summary.snmp_successes == 0
    assert summary.errors == 2
    assert repository.saved_snapshot is not None
    assert repository.saved_snapshot.errors[1].message == "RuntimeError"


def test_run_discovery_closes_repository_when_save_fails() -> None:
    repository = FakeRepository(save_error=RuntimeError("write failed"))

    with pytest.raises(RuntimeError):
        run_discovery(
            _config(),
            scan_hosts=_scan_hosts,
            collect_snmp=_collect_snmp_success,
            repository_factory=lambda config: repository,
        )

    assert repository.closed is True


def test_fetch_latest_topology_counts_returns_counts_and_closes_repository() -> None:
    repository = FakeRepository(
        latest_counts={
            "devices": 2,
            "interfaces": 3,
            "active_links": 1,
        }
    )

    counts = fetch_latest_topology_counts(
        _config(),
        repository_factory=lambda config: repository,
    )

    assert counts == LatestTopologyCounts(
        devices=2,
        interfaces=3,
        active_links=1,
    )
    assert repository.saved_snapshot is None
    assert repository.closed is True


def test_fetch_latest_topology_counts_closes_repository_when_query_fails() -> None:
    repository = FakeRepository(query_error=RuntimeError("query failed"))

    with pytest.raises(RuntimeError):
        fetch_latest_topology_counts(
            _config(),
            repository_factory=lambda config: repository,
        )

    assert repository.closed is True


def test_main_returns_success_and_prints_summary(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    monkeypatch.setattr("services.topology_discovery.main.load_config", lambda path: _config())
    monkeypatch.setattr(
        "services.topology_discovery.main.run_discovery",
        lambda config: DiscoverySummary(
            scanned_hosts=1,
            reachable_hosts=1,
            snmp_successes=1,
            ssh_successes=0,
            devices=1,
            interfaces=0,
            links=0,
            errors=0,
        ),
    )

    exit_code = main(["--config", "config/config.example.yaml"])

    assert exit_code == 0
    assert "discovery completed" in capsys.readouterr().out


def test_main_returns_success_and_prints_latest_counts(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    monkeypatch.setattr("services.topology_discovery.main.load_config", lambda path: _config())
    monkeypatch.setattr(
        "services.topology_discovery.main.fetch_latest_topology_counts",
        lambda config: LatestTopologyCounts(
            devices=2,
            interfaces=3,
            active_links=1,
        ),
    )

    exit_code = main(["--config", "config/config.example.yaml", "--latest-counts"])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == (
        "latest topology counts: devices=2, interfaces=3, active_links=1"
    )


def test_main_returns_failure_for_config_error(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    monkeypatch.setattr(
        "services.topology_discovery.main.load_config",
        _raise_config_error,
    )

    exit_code = main(["--config", "config/config.yaml"])

    assert exit_code == 1
    assert "dummy-password" not in capsys.readouterr().err


def test_main_returns_failure_for_latest_counts_repository_error(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    monkeypatch.setattr("services.topology_discovery.main.load_config", lambda path: _config())
    monkeypatch.setattr(
        "services.topology_discovery.main.fetch_latest_topology_counts",
        _raise_latest_counts_error,
    )

    exit_code = main(["--latest-counts"])

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "failed to fetch latest topology counts" in stderr
    assert "dummy-password" not in stderr


def _config(ssh_enabled: bool = False) -> AppConfig:
    return AppConfig(
        scan=ScanConfig(
            targets=["192.0.2.1"],
            timeout_seconds=2,
            retry_count=1,
            max_concurrency=1,
        ),
        snmp=SnmpConfig(
            enabled=True,
            version="2c",
            community="dummy-community",
            timeout_seconds=2,
            retry_count=1,
            port=161,
        ),
        ssh=SshConfig(
            enabled=ssh_enabled,
            username="example-user",
            password="dummy-password",
            timeout_seconds=5,
            port=22,
            commands={"show_version": "show version"},
        ),
        neo4j=Neo4jConfig(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="dummy-password",
            database="neo4j",
        ),
    )


def _scan_hosts(config: ScanConfig) -> list[AliveHost]:
    return [
        AliveHost(ip="192.0.2.1", reachable=True, discovered_by="icmp"),
        AliveHost(
            ip="198.51.100.1",
            reachable=False,
            discovered_by="icmp",
            error="unreachable",
        ),
    ]


def _collect_snmp_success(host: AliveHost, config: SnmpConfig) -> SnmpDeviceInfo:
    return SnmpDeviceInfo(ip=host.ip, success=True, sys_name="example-device")


def _collect_snmp_failure(host: AliveHost, config: SnmpConfig) -> SnmpDeviceInfo:
    return SnmpDeviceInfo(ip=host.ip, success=False, error="snmp_timeout")


def _raise_snmp_error(host: AliveHost, config: SnmpConfig) -> SnmpDeviceInfo:
    raise RuntimeError("snmp failed with dummy-community")


def _collect_ssh_success(host: AliveHost, config: SshConfig) -> SshDeviceInfo:
    return SshDeviceInfo(ip=host.ip, success=True)


def _collect_ssh_failure(host: AliveHost, config: SshConfig) -> SshDeviceInfo:
    return SshDeviceInfo(ip=host.ip, success=False, error="ssh_timeout")


def _raise_config_error(path: str) -> None:
    from services.topology_discovery.config import ConfigError

    raise ConfigError("invalid config fields: neo4j.password")


def _raise_latest_counts_error(config: AppConfig) -> None:
    from services.topology_discovery.neo4j_repository import Neo4jRepositoryError

    raise Neo4jRepositoryError("failed to fetch latest topology counts")


class FakeRepository:
    def __init__(
        self,
        save_error: Exception | None = None,
        query_error: Exception | None = None,
        latest_counts: dict[str, int] | None = None,
    ) -> None:
        self.save_error = save_error
        self.query_error = query_error
        self.latest_counts = latest_counts or {
            "devices": 0,
            "interfaces": 0,
            "active_links": 0,
        }
        self.saved_snapshot: TopologySnapshot | None = None
        self.closed = False

    def save_snapshot(self, snapshot: TopologySnapshot) -> None:
        if self.save_error is not None:
            raise self.save_error
        self.saved_snapshot = snapshot

    def fetch_latest_topology_counts(self) -> dict[str, int]:
        if self.query_error is not None:
            raise self.query_error
        return self.latest_counts

    def close(self) -> None:
        self.closed = True
