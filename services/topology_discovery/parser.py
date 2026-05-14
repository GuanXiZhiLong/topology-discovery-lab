"""Build topology snapshots from collected discovery data."""

from __future__ import annotations

from datetime import UTC, datetime
from ipaddress import ip_address, ip_network

from services.topology_discovery.models import (
    AliveHost,
    DeviceNode,
    DeviceType,
    DiscoveryError,
    InterfaceNode,
    NetworkSegmentNode,
    SnmpDeviceInfo,
    SnmpInterfaceInfo,
    SshDeviceInfo,
    TopologySnapshot,
)


def build_topology_snapshot(
    alive_hosts: list[AliveHost],
    snmp_results: list[SnmpDeviceInfo],
    ssh_results: list[SshDeviceInfo] | None = None,
    scan_targets: list[str] | None = None,
) -> TopologySnapshot:
    """Build a topology snapshot from protocol collection results."""

    started_at = datetime.now(UTC)
    resolved_ssh_results = ssh_results or []
    resolved_scan_targets = scan_targets or _scan_targets_from_alive_hosts(alive_hosts)
    devices = _deduplicate_devices(
        [
            *_devices_from_alive_hosts(alive_hosts, started_at),
            *_devices_from_snmp_results(snmp_results, started_at),
        ]
    )
    interfaces = _deduplicate_interfaces(
        [
            interface
            for snmp_result in snmp_results
            if snmp_result.success
            for interface in _interfaces_from_snmp_result(snmp_result, started_at)
        ]
    )
    errors = (
        _errors_from_alive_hosts(alive_hosts)
        + _errors_from_snmp_results(snmp_results)
        + _errors_from_ssh_results(resolved_ssh_results)
    )
    finished_at = datetime.now(UTC)

    return TopologySnapshot(
        snapshot_id=f"snapshot:{started_at.isoformat()}",
        scan_targets=resolved_scan_targets,
        started_at=started_at,
        finished_at=finished_at,
        devices=devices,
        interfaces=interfaces,
        links=[],
        network_segments=_network_segments_from_targets(resolved_scan_targets, started_at),
        errors=errors,
    )


def _devices_from_alive_hosts(
    alive_hosts: list[AliveHost],
    last_seen: datetime,
) -> list[DeviceNode]:
    return [
        DeviceNode(
            device_id=_device_id(host.ip),
            ip=host.ip,
            device_type="unknown",
            status="partial" if host.reachable else "offline",
            last_seen=last_seen,
            source=host.discovered_by,
        )
        for host in alive_hosts
    ]


def _devices_from_snmp_results(
    snmp_results: list[SnmpDeviceInfo],
    last_seen: datetime,
) -> list[DeviceNode]:
    devices: list[DeviceNode] = []
    for result in snmp_results:
        if not result.success:
            continue
        devices.append(
            DeviceNode(
                device_id=_device_id(result.ip),
                ip=result.ip,
                hostname=result.sys_name,
                device_type=_identify_device_type(result.sys_descr),
                vendor=None,
                model=None,
                os_version=None,
                sys_descr=result.sys_descr,
                sys_object_id=result.sys_object_id,
                status="online",
                last_seen=last_seen,
                source="snmp",
            )
        )
    return devices


def _interfaces_from_snmp_result(
    snmp_result: SnmpDeviceInfo,
    last_seen: datetime,
) -> list[InterfaceNode]:
    device_id = _device_id(snmp_result.ip)
    return [
        InterfaceNode(
            interface_id=_interface_id(device_id, interface),
            device_id=device_id,
            name=interface.name or f"ifIndex{interface.if_index}",
            description=interface.name,
            mac_address=interface.mac_address,
            if_index=interface.if_index,
            admin_status=interface.admin_status,
            oper_status=interface.oper_status,
            speed_bps=interface.speed_bps,
            last_seen=last_seen,
        )
        for interface in snmp_result.interfaces
    ]


def _errors_from_alive_hosts(alive_hosts: list[AliveHost]) -> list[DiscoveryError]:
    return [
        DiscoveryError(
            target=host.ip,
            stage="icmp",
            message=host.error,
            recoverable=True,
        )
        for host in alive_hosts
        if host.error
    ]


def _errors_from_snmp_results(snmp_results: list[SnmpDeviceInfo]) -> list[DiscoveryError]:
    return [
        DiscoveryError(
            target=result.ip,
            stage="snmp",
            message=result.error or "snmp collection failed",
            recoverable=True,
        )
        for result in snmp_results
        if not result.success
    ]


def _errors_from_ssh_results(ssh_results: list[SshDeviceInfo]) -> list[DiscoveryError]:
    return [
        DiscoveryError(
            target=result.ip,
            stage="ssh",
            message=result.error or "ssh collection failed",
            recoverable=True,
        )
        for result in ssh_results
        if not result.success
    ]


def _deduplicate_devices(devices: list[DeviceNode]) -> list[DeviceNode]:
    by_device_id: dict[str, DeviceNode] = {}
    for device in devices:
        existing = by_device_id.get(device.device_id)
        if existing is None or _device_priority(device) >= _device_priority(existing):
            by_device_id[device.device_id] = device
    return list(by_device_id.values())


def _deduplicate_interfaces(interfaces: list[InterfaceNode]) -> list[InterfaceNode]:
    by_interface_id: dict[str, InterfaceNode] = {}
    for interface in interfaces:
        by_interface_id.setdefault(interface.interface_id, interface)
    return list(by_interface_id.values())


def _network_segments_from_targets(
    scan_targets: list[str],
    last_seen: datetime,
) -> list[NetworkSegmentNode]:
    segments: list[NetworkSegmentNode] = []
    seen: set[str] = set()
    for target in scan_targets:
        normalized_target = _normalize_target(target)
        if normalized_target in seen:
            continue
        seen.add(normalized_target)
        segments.append(
            NetworkSegmentNode(
                segment_id=f"segment:{normalized_target}",
                target=normalized_target,
                cidr=_target_cidr(normalized_target),
                source="config",
                last_seen=last_seen,
            )
        )
    return segments


def _scan_targets_from_alive_hosts(alive_hosts: list[AliveHost]) -> list[str]:
    scan_targets: list[str] = []
    for host in alive_hosts:
        for target in host.source_targets:
            if target not in scan_targets:
                scan_targets.append(target)
    return scan_targets


def _identify_device_type(sys_descr: str | None) -> DeviceType:
    if not sys_descr:
        return "unknown"

    normalized = sys_descr.casefold()
    if "switch" in normalized:
        return "switch"
    if "router" in normalized:
        return "router"
    if "firewall" in normalized:
        return "firewall"
    if "wireless" in normalized or " ap " in f" {normalized} ":
        return "wireless_ap"
    return "unknown"


def _device_id(ip: str) -> str:
    return f"device:{ip}"


def _interface_id(device_id: str, interface: SnmpInterfaceInfo) -> str:
    return f"interface:{device_id}:{interface.if_index}"


def _device_priority(device: DeviceNode) -> int:
    if device.source == "snmp":
        return 2
    if device.status == "partial":
        return 1
    return 0


def _normalize_target(target: str) -> str:
    try:
        return str(ip_address(target))
    except ValueError:
        return str(ip_network(target, strict=False))


def _target_cidr(target: str) -> str | None:
    try:
        ip_address(target)
        return None
    except ValueError:
        return str(ip_network(target, strict=False))
