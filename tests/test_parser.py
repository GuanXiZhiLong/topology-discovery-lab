from __future__ import annotations

from services.topology_discovery.models import (
    AliveHost,
    SnmpDeviceInfo,
    SnmpInterfaceInfo,
    SshDeviceInfo,
)
from services.topology_discovery.parser import build_topology_snapshot


def test_build_topology_snapshot_creates_device_from_alive_host() -> None:
    snapshot = build_topology_snapshot(
        alive_hosts=[AliveHost(ip="192.0.2.1", reachable=True, discovered_by="icmp")],
        snmp_results=[],
    )

    assert len(snapshot.devices) == 1
    assert snapshot.devices[0].device_id == "device:192.0.2.1"
    assert snapshot.devices[0].status == "partial"
    assert snapshot.links == []


def test_build_topology_snapshot_creates_device_and_interface_from_snmp() -> None:
    snapshot = build_topology_snapshot(
        alive_hosts=[AliveHost(ip="192.0.2.1", reachable=True, discovered_by="icmp")],
        snmp_results=[_snmp_result()],
    )

    assert len(snapshot.devices) == 1
    assert snapshot.devices[0].hostname == "example-device"
    assert snapshot.devices[0].device_type == "switch"
    assert snapshot.devices[0].status == "online"
    assert len(snapshot.interfaces) == 1
    assert snapshot.interfaces[0].interface_id == "interface:device:192.0.2.1:1"
    assert snapshot.interfaces[0].admin_status == "up"


def test_build_topology_snapshot_deduplicates_devices_preferring_snmp() -> None:
    snapshot = build_topology_snapshot(
        alive_hosts=[
            AliveHost(ip="192.0.2.1", reachable=True, discovered_by="icmp"),
            AliveHost(ip="192.0.2.1", reachable=True, discovered_by="icmp"),
        ],
        snmp_results=[_snmp_result()],
    )

    assert len(snapshot.devices) == 1
    assert snapshot.devices[0].source == "snmp"


def test_build_topology_snapshot_deduplicates_interfaces() -> None:
    snmp_result = _snmp_result(
        interfaces=[
            _snmp_interface(if_index=1, name="GigabitEthernet0/1"),
            _snmp_interface(if_index=1, name="Duplicate"),
        ]
    )

    snapshot = build_topology_snapshot(
        alive_hosts=[],
        snmp_results=[snmp_result],
    )

    assert len(snapshot.interfaces) == 1
    assert snapshot.interfaces[0].name == "GigabitEthernet0/1"


def test_build_topology_snapshot_records_snmp_failure_without_dropping_device() -> None:
    snapshot = build_topology_snapshot(
        alive_hosts=[AliveHost(ip="192.0.2.1", reachable=True, discovered_by="icmp")],
        snmp_results=[
            SnmpDeviceInfo(ip="192.0.2.1", success=False, error="snmp_timeout"),
        ],
    )

    assert len(snapshot.devices) == 1
    assert snapshot.devices[0].status == "partial"
    assert snapshot.errors[0].stage == "snmp"
    assert snapshot.errors[0].message == "snmp_timeout"


def test_build_topology_snapshot_records_icmp_error() -> None:
    snapshot = build_topology_snapshot(
        alive_hosts=[
            AliveHost(
                ip="192.0.2.1",
                reachable=False,
                discovered_by="icmp",
                error="unreachable",
            )
        ],
        snmp_results=[],
    )

    assert snapshot.devices[0].status == "offline"
    assert snapshot.errors[0].stage == "icmp"
    assert snapshot.errors[0].message == "unreachable"


def test_build_topology_snapshot_records_ssh_failure() -> None:
    snapshot = build_topology_snapshot(
        alive_hosts=[AliveHost(ip="192.0.2.1", reachable=True, discovered_by="icmp")],
        snmp_results=[],
        ssh_results=[SshDeviceInfo(ip="192.0.2.1", success=False, error="ssh_timeout")],
    )

    assert snapshot.errors[0].stage == "ssh"
    assert snapshot.errors[0].message == "ssh_timeout"


def test_build_topology_snapshot_identifies_device_types() -> None:
    descriptions = {
        "Example Switch": "switch",
        "Example Router": "router",
        "Example Firewall": "firewall",
        "Example Wireless AP": "wireless_ap",
        "Example Appliance": "unknown",
    }

    for description, expected_type in descriptions.items():
        snapshot = build_topology_snapshot(
            alive_hosts=[],
            snmp_results=[_snmp_result(ip="192.0.2.1", sys_descr=description)],
        )

        assert snapshot.devices[0].device_type == expected_type


def test_build_topology_snapshot_uses_timezone_aware_timestamps() -> None:
    snapshot = build_topology_snapshot(
        alive_hosts=[],
        snmp_results=[],
    )

    assert snapshot.started_at.tzinfo is not None
    assert snapshot.finished_at is not None
    assert snapshot.finished_at.tzinfo is not None


def test_build_topology_snapshot_records_scan_targets_and_segments() -> None:
    snapshot = build_topology_snapshot(
        alive_hosts=[],
        snmp_results=[],
        scan_targets=["192.0.2.1", "192.0.2.0/30"],
    )

    assert snapshot.scan_targets == ["192.0.2.1", "192.0.2.0/30"]
    assert [segment.segment_id for segment in snapshot.network_segments] == [
        "segment:192.0.2.1",
        "segment:192.0.2.0/30",
    ]
    assert snapshot.network_segments[0].cidr is None
    assert snapshot.network_segments[1].cidr == "192.0.2.0/30"


def test_build_topology_snapshot_derives_scan_targets_from_alive_hosts() -> None:
    snapshot = build_topology_snapshot(
        alive_hosts=[
            AliveHost(
                ip="192.0.2.1",
                reachable=True,
                discovered_by="icmp",
                source_targets=["192.0.2.1", "192.0.2.0/30"],
            )
        ],
        snmp_results=[],
    )

    assert snapshot.scan_targets == ["192.0.2.1", "192.0.2.0/30"]


def _snmp_result(
    ip: str = "192.0.2.1",
    sys_descr: str = "Example Switch",
    interfaces: list[SnmpInterfaceInfo] | None = None,
) -> SnmpDeviceInfo:
    return SnmpDeviceInfo(
        ip=ip,
        success=True,
        sys_name="example-device",
        sys_descr=sys_descr,
        sys_object_id="1.3.6.1.4.1.999",
        interfaces=interfaces or [_snmp_interface()],
    )


def _snmp_interface(
    if_index: int = 1,
    name: str = "GigabitEthernet0/1",
) -> SnmpInterfaceInfo:
    return SnmpInterfaceInfo(
        if_index=if_index,
        name=name,
        mac_address="00:11:22:33:44:55",
        admin_status="up",
        oper_status="up",
        speed_bps=1_000_000_000,
    )
