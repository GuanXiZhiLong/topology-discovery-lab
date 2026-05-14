"""Application orchestration for topology discovery."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from services.topology_discovery.config import (
    AppConfig,
    ConfigError,
    Neo4jConfig,
    ScanConfig,
    SnmpConfig,
    SshConfig,
    load_config,
)
from services.topology_discovery.icmp import scan_alive_hosts
from services.topology_discovery.models import (
    AliveHost,
    SnmpDeviceInfo,
    SshDeviceInfo,
    TopologySnapshot,
)
from services.topology_discovery.neo4j_repository import (
    Neo4jRepositoryError,
    Neo4jTopologyRepository,
)
from services.topology_discovery.parser import build_topology_snapshot
from services.topology_discovery.snmp import collect_snmp_device_info
from services.topology_discovery.ssh import collect_ssh_device_info

DEFAULT_CONFIG_PATH = "config/config.yaml"


class TopologyRepository(Protocol):
    """Repository operations used by the application orchestrator."""

    def save_snapshot(self, snapshot: TopologySnapshot) -> None:
        """Persist a topology snapshot."""

    def close(self) -> None:
        """Close repository resources."""


ScanAliveHosts = Callable[[ScanConfig], list[AliveHost]]
SnmpCollector = Callable[[AliveHost, SnmpConfig], SnmpDeviceInfo]
SshCollector = Callable[[AliveHost, SshConfig], SshDeviceInfo]
RepositoryFactory = Callable[[Neo4jConfig], TopologyRepository]


@dataclass(frozen=True)
class DiscoverySummary:
    """Aggregated discovery run statistics."""

    scanned_hosts: int
    reachable_hosts: int
    snmp_successes: int
    ssh_successes: int
    devices: int
    interfaces: int
    links: int
    errors: int


def run_discovery(
    config: AppConfig,
    scan_hosts: ScanAliveHosts = scan_alive_hosts,
    collect_snmp: SnmpCollector = collect_snmp_device_info,
    collect_ssh: SshCollector = collect_ssh_device_info,
    repository_factory: RepositoryFactory = Neo4jTopologyRepository,
) -> DiscoverySummary:
    """Run a complete discovery pass and persist the resulting snapshot."""

    alive_hosts = scan_hosts(config.scan)
    reachable_hosts = [host for host in alive_hosts if host.reachable]
    snmp_results = [collect_snmp(host, config.snmp) for host in reachable_hosts]
    ssh_results = (
        [collect_ssh(host, config.ssh) for host in reachable_hosts] if config.ssh.enabled else []
    )

    snapshot = build_topology_snapshot(
        alive_hosts=alive_hosts,
        snmp_results=snmp_results,
        ssh_results=ssh_results,
    )
    repository = repository_factory(config.neo4j)
    try:
        repository.save_snapshot(snapshot)
    finally:
        repository.close()

    return DiscoverySummary(
        scanned_hosts=len(alive_hosts),
        reachable_hosts=len(reachable_hosts),
        snmp_successes=sum(result.success for result in snmp_results),
        ssh_successes=sum(result.success for result in ssh_results),
        devices=len(snapshot.devices),
        interfaces=len(snapshot.interfaces),
        links=len(snapshot.links),
        errors=len(snapshot.errors),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Run topology discovery.")
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to YAML configuration file.",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        summary = run_discovery(config)
    except (ConfigError, Neo4jRepositoryError) as exc:
        print(f"discovery failed: {exc}", file=sys.stderr)
        return 1

    print(_format_summary(summary))
    return 0


def _format_summary(summary: DiscoverySummary) -> str:
    return (
        "discovery completed: "
        f"scanned_hosts={summary.scanned_hosts}, "
        f"reachable_hosts={summary.reachable_hosts}, "
        f"snmp_successes={summary.snmp_successes}, "
        f"ssh_successes={summary.ssh_successes}, "
        f"devices={summary.devices}, "
        f"interfaces={summary.interfaces}, "
        f"links={summary.links}, "
        f"errors={summary.errors}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
