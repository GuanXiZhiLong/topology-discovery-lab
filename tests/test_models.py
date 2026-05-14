from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from services.topology_discovery.models import (
    AliveHost,
    DeviceNode,
    DiscoveryError,
    InterfaceNode,
    LinkEdge,
    TopologySnapshot,
)

NOW = datetime(2026, 5, 13, 12, 0, tzinfo=UTC)


def test_alive_host_accepts_valid_data() -> None:
    host = AliveHost(
        ip="192.0.2.1",
        reachable=True,
        latency_ms=1.5,
        discovered_by="icmp",
    )

    assert host.ip == "192.0.2.1"
    assert host.reachable is True


def test_alive_host_rejects_invalid_ip() -> None:
    with pytest.raises(ValidationError):
        AliveHost(
            ip="not-an-ip",
            reachable=False,
            discovered_by="icmp",
            error="timeout",
        )


def test_device_node_accepts_valid_data() -> None:
    device = DeviceNode(
        device_id="device:192.0.2.1",
        ip="192.0.2.1",
        hostname="example-device",
        device_type="switch",
        status="online",
        last_seen=NOW,
        source="snmp",
    )

    assert device.device_id == "device:192.0.2.1"
    assert device.device_type == "switch"


def test_device_node_accepts_partial_status() -> None:
    device = DeviceNode(
        device_id="device:192.0.2.1",
        ip="192.0.2.1",
        device_type="unknown",
        status="partial",
        last_seen=NOW,
        source="icmp",
    )

    assert device.status == "partial"


def test_device_node_rejects_missing_required_field() -> None:
    data: dict[str, Any] = {
        "device_id": "device:192.0.2.1",
        "ip": "192.0.2.1",
        "device_type": "switch",
        "status": "online",
        "last_seen": NOW,
    }

    with pytest.raises(ValidationError):
        DeviceNode(**data)


def test_device_node_rejects_naive_last_seen() -> None:
    with pytest.raises(ValidationError):
        DeviceNode(
            device_id="device:192.0.2.1",
            ip="192.0.2.1",
            device_type="unknown",
            status="partial",
            last_seen=datetime(2026, 5, 13, 12, 0),
            source="icmp",
        )


def test_interface_node_accepts_valid_data() -> None:
    interface = InterfaceNode(
        interface_id="interface:device:192.0.2.1:1",
        device_id="device:192.0.2.1",
        name="GigabitEthernet0/1",
        if_index=1,
        admin_status="up",
        oper_status="up",
        speed_bps=1_000_000_000,
        last_seen=NOW,
    )

    assert interface.if_index == 1
    assert interface.speed_bps == 1_000_000_000


def test_link_edge_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        LinkEdge(
            link_id="link:a:b",
            source_device_id="device:192.0.2.1",
            target_device_id="device:198.51.100.1",
            discovery_method="lldp",
            confidence=1.1,
            last_seen=NOW,
        )


def test_link_edge_rejects_naive_last_seen() -> None:
    with pytest.raises(ValidationError):
        LinkEdge(
            link_id="link:a:b",
            source_device_id="device:192.0.2.1",
            target_device_id="device:198.51.100.1",
            discovery_method="lldp",
            confidence=1.0,
            last_seen=datetime(2026, 5, 13, 12, 0),
        )


def test_topology_snapshot_accepts_nested_models() -> None:
    snapshot = TopologySnapshot(
        snapshot_id="snapshot-1",
        started_at=NOW,
        finished_at=NOW,
        devices=[
            DeviceNode(
                device_id="device:192.0.2.1",
                ip="192.0.2.1",
                device_type="unknown",
                status="online",
                last_seen=NOW,
                source="icmp",
            )
        ],
        interfaces=[],
        links=[],
        errors=[
            DiscoveryError(
                target="198.51.100.1",
                stage="snmp",
                message="timeout",
                recoverable=True,
            )
        ],
    )

    assert snapshot.devices[0].ip == "192.0.2.1"
    assert snapshot.errors[0].recoverable is True


def test_topology_snapshot_rejects_finished_before_started() -> None:
    with pytest.raises(ValidationError):
        TopologySnapshot(
            snapshot_id="snapshot-1",
            started_at=datetime(2026, 5, 13, 12, 1, tzinfo=UTC),
            finished_at=NOW,
        )


def test_topology_snapshot_rejects_naive_started_at() -> None:
    with pytest.raises(ValidationError):
        TopologySnapshot(
            snapshot_id="snapshot-1",
            started_at=datetime(2026, 5, 13, 12, 0),
        )
