from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from services.topology_discovery.config import Neo4jConfig
from services.topology_discovery.models import (
    DeviceNode,
    InterfaceNode,
    LinkEdge,
    TopologySnapshot,
)
from services.topology_discovery.neo4j_repository import (
    Driver,
    Neo4jRepositoryError,
    Neo4jTopologyRepository,
)

NOW = datetime(2026, 5, 13, 12, 0, tzinfo=UTC)


def test_save_snapshot_uses_parameterized_merge_queries() -> None:
    driver = FakeDriver()
    repository = Neo4jTopologyRepository(_config(), driver_factory=_factory(driver))
    snapshot = _snapshot()

    repository.save_snapshot(snapshot)

    assert len(driver.session_obj.runs) == 5
    device_query, device_params = driver.session_obj.runs[0]
    second_device_query, _ = driver.session_obj.runs[1]
    interface_query, interface_params = driver.session_obj.runs[2]
    interface_link_query, interface_link_params = driver.session_obj.runs[3]
    device_link_query, device_link_params = driver.session_obj.runs[4]

    assert "MERGE (d:Device {device_id: $device_id})" in device_query
    assert "MERGE (d:Device {device_id: $device_id})" in second_device_query
    assert "MERGE (i:Interface {interface_id: $interface_id})" in interface_query
    assert "MERGE (d)-[:HAS_INTERFACE]->(i)" in interface_query
    assert "MERGE (source)-[r:CONNECTED_TO {link_id: $link_id}]->(target)" in (
        interface_link_query
    )
    assert "MERGE (source)-[r:CONNECTED_TO {link_id: $link_id}]->(target)" in (
        device_link_query
    )
    assert device_params["device_id"] == "device:192.0.2.1"
    assert interface_params["interface_id"] == "interface:device:192.0.2.1:1"
    assert interface_link_params["source_interface_id"] == "interface:device:192.0.2.1:1"
    assert device_link_params["source_device_id"] == "device:192.0.2.1"
    assert "192.0.2.1" not in device_query


def test_save_snapshot_uses_configured_database() -> None:
    driver = FakeDriver()
    repository = Neo4jTopologyRepository(
        _config(database="topology"),
        driver_factory=_factory(driver),
    )

    repository.save_snapshot(TopologySnapshot(snapshot_id="empty", started_at=NOW))

    assert driver.database == "topology"


def test_connect_failure_is_sanitized() -> None:
    repository = Neo4jTopologyRepository(
        _config(password="dummy-password"),
        driver_factory=_factory(FailingDriver()),
    )

    with pytest.raises(Neo4jRepositoryError) as exc_info:
        repository.connect()

    message = str(exc_info.value)
    assert "failed to connect to Neo4j" in message
    assert "dummy-password" not in message


def test_close_closes_driver() -> None:
    driver = FakeDriver()
    repository = Neo4jTopologyRepository(_config(), driver_factory=_factory(driver))

    repository.connect()
    repository.close()

    assert driver.closed is True


def _config(password: str = "dummy-password", database: str = "neo4j") -> Neo4jConfig:
    return Neo4jConfig(
        uri="bolt://localhost:7687",
        username="neo4j",
        password=password,
        database=database,
    )


def _snapshot() -> TopologySnapshot:
    device = DeviceNode(
        device_id="device:192.0.2.1",
        ip="192.0.2.1",
        hostname="example-device",
        device_type="switch",
        status="online",
        last_seen=NOW,
        source="snmp",
    )
    target = DeviceNode(
        device_id="device:198.51.100.1",
        ip="198.51.100.1",
        device_type="router",
        status="online",
        last_seen=NOW,
        source="snmp",
    )
    interface = InterfaceNode(
        interface_id="interface:device:192.0.2.1:1",
        device_id="device:192.0.2.1",
        name="GigabitEthernet0/1",
        if_index=1,
        last_seen=NOW,
    )
    interface_link = LinkEdge(
        link_id="link:interface-a:interface-b",
        source_device_id="device:192.0.2.1",
        target_device_id="device:198.51.100.1",
        source_interface_id="interface:device:192.0.2.1:1",
        target_interface_id="interface:device:198.51.100.1:1",
        discovery_method="lldp",
        confidence=1.0,
        last_seen=NOW,
    )
    device_link = LinkEdge(
        link_id="link:device-a:device-b",
        source_device_id="device:192.0.2.1",
        target_device_id="device:198.51.100.1",
        discovery_method="ip_subnet",
        confidence=0.3,
        last_seen=NOW,
    )
    return TopologySnapshot(
        snapshot_id="snapshot-1",
        started_at=NOW,
        finished_at=NOW,
        devices=[device, target],
        interfaces=[interface],
        links=[interface_link, device_link],
    )


class FakeSession:
    def __init__(self) -> None:
        self.runs: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def run(self, query: str, parameters: dict[str, Any] | None = None) -> Any:
        self.runs.append((query, parameters or {}))
        return None


class FakeDriver:
    def __init__(self) -> None:
        self.session_obj = FakeSession()
        self.database: str | None = None
        self.closed = False

    def session(self, **kwargs: Any) -> FakeSession:
        self.database = kwargs["database"]
        return self.session_obj

    def verify_connectivity(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class FailingDriver(FakeDriver):
    def verify_connectivity(self) -> None:
        raise RuntimeError("authentication failed for dummy-password")


def _factory(driver: FakeDriver) -> Callable[[str, tuple[str, str]], Driver]:
    def create_driver(uri: str, auth: tuple[str, str]) -> Driver:
        return cast(Driver, driver)

    return create_driver
