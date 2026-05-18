"""Build topology snapshots from collected discovery data."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from ipaddress import ip_address, ip_network
from typing import TypedDict

from services.topology_discovery.models import (
    AliveHost,
    DeploymentType,
    DeviceNode,
    DeviceType,
    DiscoveryError,
    EndpointType,
    InterfaceNode,
    LinkEdge,
    NetworkSegmentNode,
    SnmpDeviceInfo,
    SnmpInterfaceInfo,
    SnmpNeighborInfo,
    SshCommandResult,
    SshDeviceInfo,
    TopologySnapshot,
)


class SysObjectIdMapping(TypedDict):
    prefix: str
    vendor: str
    device_type: DeviceType
    deployment_type: DeploymentType
    model_family: str


SYS_OBJECT_ID_MAPPINGS: tuple[SysObjectIdMapping, ...] = (
    {
        "prefix": "1.3.6.1.4.1.8072",
        "vendor": "net-snmp",
        "device_type": "server",
        "deployment_type": "unknown",
        "model_family": "net-snmp",
    },
)
IP_TOKEN_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
MAC_TOKEN_PATTERN = re.compile(
    r"\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b"
    r"|\b[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\b"
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
    links = _deduplicate_links(
        [
            *_links_from_snmp_neighbors(snmp_results, devices, interfaces, started_at),
            *_links_from_ssh_tables(resolved_ssh_results, devices, interfaces, started_at),
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
        links=links,
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
        object_id_mapping = _sys_object_id_mapping(result.sys_object_id)
        devices.append(
            DeviceNode(
                device_id=_device_id(result.ip),
                ip=result.ip,
                hostname=result.sys_name,
                device_type=_identify_device_type(result.sys_descr, result.sys_object_id),
                endpoint_type=_identify_endpoint_type(result.sys_descr, result.sys_object_id),
                deployment_type=_identify_deployment_type(result.sys_descr, result.sys_object_id),
                vendor=object_id_mapping.get("vendor") if object_id_mapping else None,
                model=object_id_mapping.get("model_family") if object_id_mapping else None,
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
    errors = [
        DiscoveryError(
            target=result.ip,
            stage="snmp",
            message=result.error or "snmp collection failed",
            recoverable=True,
        )
        for result in snmp_results
        if not result.success
    ]
    for result in snmp_results:
        errors.extend(
            DiscoveryError(
                target=result.ip,
                stage="snmp",
                message=error,
                recoverable=True,
            )
            for error in result.collection_errors
        )
    return errors


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


def _deduplicate_links(links: list[LinkEdge]) -> list[LinkEdge]:
    by_link_id: dict[str, LinkEdge] = {}
    for link in links:
        existing = by_link_id.get(link.link_id)
        if existing is None or link.confidence > existing.confidence:
            by_link_id[link.link_id] = link
    return list(by_link_id.values())


def _links_from_snmp_neighbors(
    snmp_results: list[SnmpDeviceInfo],
    devices: list[DeviceNode],
    interfaces: list[InterfaceNode],
    last_seen: datetime,
) -> list[LinkEdge]:
    devices_by_ip = {device.ip: device for device in devices}
    devices_by_hostname = {
        device.hostname.casefold(): device for device in devices if device.hostname is not None
    }
    interfaces_by_device_and_index = {
        (interface.device_id, interface.if_index): interface
        for interface in interfaces
        if interface.if_index is not None
    }
    interfaces_by_device_and_name = {
        (interface.device_id, _normalize_interface_name(interface.name)): interface
        for interface in interfaces
    }

    links: list[LinkEdge] = []
    for result in snmp_results:
        if not result.success:
            continue
        source_device = devices_by_ip.get(result.ip)
        if source_device is None:
            continue
        for neighbor in result.neighbors:
            target_device = _target_device_from_neighbor(
                neighbor,
                devices_by_ip,
                devices_by_hostname,
            )
            if target_device is None or target_device.device_id == source_device.device_id:
                continue
            source_interface = (
                interfaces_by_device_and_index.get(
                    (source_device.device_id, neighbor.local_interface_index)
                )
                if neighbor.local_interface_index is not None
                else None
            )
            target_interface = _target_interface_from_neighbor(
                target_device,
                neighbor,
                interfaces_by_device_and_name,
            )
            links.append(
                LinkEdge(
                    link_id=_link_id(
                        source_device,
                        target_device,
                        source_interface,
                        target_interface,
                    ),
                    source_device_id=source_device.device_id,
                    target_device_id=target_device.device_id,
                    source_interface_id=(
                        source_interface.interface_id if source_interface is not None else None
                    ),
                    target_interface_id=(
                        target_interface.interface_id if target_interface is not None else None
                    ),
                    discovery_method=neighbor.protocol,
                    confidence=_neighbor_confidence(neighbor),
                    last_seen=last_seen,
                )
            )
    return links


def _links_from_ssh_tables(
    ssh_results: list[SshDeviceInfo],
    devices: list[DeviceNode],
    interfaces: list[InterfaceNode],
    last_seen: datetime,
) -> list[LinkEdge]:
    devices_by_ip = {device.ip: device for device in devices}
    devices_by_id = {device.device_id: device for device in devices}
    interfaces_by_mac = {
        normalized_mac: interface
        for interface in interfaces
        if interface.mac_address is not None
        for normalized_mac in [_normalize_mac_address(interface.mac_address)]
        if normalized_mac is not None
    }
    interfaces_by_device_and_name = {
        (interface.device_id, _normalize_interface_name(interface.name)): interface
        for interface in interfaces
    }

    links: list[LinkEdge] = []
    for result in ssh_results:
        if not result.success:
            continue
        source_device = devices_by_ip.get(result.ip)
        if source_device is None:
            continue
        for command in result.commands:
            if not command.success or not command.output:
                continue
            command_text = f"{command.name} {command.command}".casefold()
            if "arp" in command_text:
                links.extend(
                    _links_from_arp_table(
                        command,
                        source_device,
                        devices_by_id,
                        interfaces_by_mac,
                        last_seen,
                    )
                )
            if "mac" in command_text:
                links.extend(
                    _links_from_mac_table(
                        command,
                        source_device,
                        devices_by_id,
                        interfaces_by_mac,
                        interfaces_by_device_and_name,
                        last_seen,
                    )
                )
    return links


def _links_from_arp_table(
    command: SshCommandResult,
    source_device: DeviceNode,
    devices_by_id: dict[str, DeviceNode],
    interfaces_by_mac: dict[str, InterfaceNode],
    last_seen: datetime,
) -> list[LinkEdge]:
    links: list[LinkEdge] = []
    if command.output is None:
        return links
    for line in command.output.splitlines():
        ip_match = IP_TOKEN_PATTERN.search(line)
        mac_address = _first_mac_address(line)
        if ip_match is None or mac_address is None:
            continue
        target_interface = interfaces_by_mac.get(mac_address)
        if target_interface is None:
            continue
        target_device = devices_by_id.get(target_interface.device_id)
        if target_device is None or target_device.device_id == source_device.device_id:
            continue
        links.append(
            LinkEdge(
                link_id=_link_id(source_device, target_device, None, target_interface),
                source_device_id=source_device.device_id,
                target_device_id=target_device.device_id,
                target_interface_id=target_interface.interface_id,
                discovery_method="arp_table",
                confidence=0.6,
                last_seen=last_seen,
            )
        )
    return links


def _links_from_mac_table(
    command: SshCommandResult,
    source_device: DeviceNode,
    devices_by_id: dict[str, DeviceNode],
    interfaces_by_mac: dict[str, InterfaceNode],
    interfaces_by_device_and_name: dict[tuple[str, str], InterfaceNode],
    last_seen: datetime,
) -> list[LinkEdge]:
    links: list[LinkEdge] = []
    if command.output is None:
        return links
    for line in command.output.splitlines():
        mac_address = _first_mac_address(line)
        if mac_address is None:
            continue
        target_interface = interfaces_by_mac.get(mac_address)
        if target_interface is None:
            continue
        target_device = devices_by_id.get(target_interface.device_id)
        if target_device is None or target_device.device_id == source_device.device_id:
            continue
        source_interface = _source_interface_from_mac_table_line(
            line,
            source_device,
            interfaces_by_device_and_name,
        )
        links.append(
            LinkEdge(
                link_id=_link_id(source_device, target_device, source_interface, target_interface),
                source_device_id=source_device.device_id,
                target_device_id=target_device.device_id,
                source_interface_id=(
                    source_interface.interface_id if source_interface is not None else None
                ),
                target_interface_id=target_interface.interface_id,
                discovery_method="mac_table",
                confidence=0.7,
                last_seen=last_seen,
            )
        )
    return links


def _target_device_from_neighbor(
    neighbor: SnmpNeighborInfo,
    devices_by_ip: dict[str, DeviceNode],
    devices_by_hostname: dict[str, DeviceNode],
) -> DeviceNode | None:
    if neighbor.remote_management_address is not None:
        target_device = devices_by_ip.get(neighbor.remote_management_address)
        if target_device is not None:
            return target_device
    if neighbor.remote_system_name is None:
        return None
    return devices_by_hostname.get(neighbor.remote_system_name.casefold())


def _target_interface_from_neighbor(
    target_device: DeviceNode,
    neighbor: SnmpNeighborInfo,
    interfaces_by_device_and_name: dict[tuple[str, str], InterfaceNode],
) -> InterfaceNode | None:
    if neighbor.remote_port_id is None:
        return None
    return interfaces_by_device_and_name.get(
        (target_device.device_id, _normalize_interface_name(neighbor.remote_port_id))
    )


def _link_id(
    source_device: DeviceNode,
    target_device: DeviceNode,
    source_interface: InterfaceNode | None,
    target_interface: InterfaceNode | None,
) -> str:
    if source_interface is not None and target_interface is not None:
        endpoints = sorted([source_interface.interface_id, target_interface.interface_id])
        return f"link:{endpoints[0]}:{endpoints[1]}"
    endpoints = sorted([source_device.device_id, target_device.device_id])
    return f"link:{endpoints[0]}:{endpoints[1]}"


def _normalize_interface_name(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def _first_mac_address(value: str) -> str | None:
    match = MAC_TOKEN_PATTERN.search(value)
    if match is None:
        return None
    return _normalize_mac_address(match.group(0))


def _normalize_mac_address(value: str) -> str | None:
    normalized = "".join(character for character in value.casefold() if character.isalnum())
    if len(normalized) != 12 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        return None
    return normalized


def _source_interface_from_mac_table_line(
    line: str,
    source_device: DeviceNode,
    interfaces_by_device_and_name: dict[tuple[str, str], InterfaceNode],
) -> InterfaceNode | None:
    columns = line.split()
    for raw_column in reversed(columns):
        interface = interfaces_by_device_and_name.get(
            (source_device.device_id, _normalize_interface_name(raw_column))
        )
        if interface is not None:
            return interface
    return None


def _neighbor_confidence(neighbor: SnmpNeighborInfo) -> float:
    if neighbor.protocol == "lldp":
        return 1.0
    return 0.95


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


def _identify_device_type(
    sys_descr: str | None,
    sys_object_id: str | None = None,
) -> DeviceType:
    object_id_mapping = _sys_object_id_mapping(sys_object_id)
    if object_id_mapping is not None:
        return object_id_mapping["device_type"]

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
    if "windows server" in normalized or "server" in normalized or "linux" in normalized:
        return "server"
    if any(marker in normalized for marker in ("windows", "macos", "android", "ios")):
        return "endpoint"
    return "unknown"


def _identify_endpoint_type(
    sys_descr: str | None,
    sys_object_id: str | None = None,
) -> EndpointType | None:
    if _identify_device_type(sys_descr, sys_object_id) != "endpoint":
        return None
    if not sys_descr:
        return "unknown"

    normalized = sys_descr.casefold()
    if "android" in normalized or "ios" in normalized:
        return "phone"
    if "tablet" in normalized or "ipad" in normalized:
        return "tablet"
    if "workstation" in normalized:
        return "workstation"
    if "laptop" in normalized or "notebook" in normalized:
        return "laptop"
    if "windows" in normalized or "macos" in normalized:
        return "pc"
    return "unknown"


def _identify_deployment_type(
    sys_descr: str | None,
    sys_object_id: str | None = None,
) -> DeploymentType:
    object_id_mapping = _sys_object_id_mapping(sys_object_id)
    if object_id_mapping is not None:
        return object_id_mapping["deployment_type"]

    if not sys_descr:
        return "unknown"

    normalized = sys_descr.casefold()
    if any(
        marker in normalized
        for marker in ("vmware", "virtual", "kvm", "qemu", "hyper-v", "virtualbox")
    ):
        return "virtual"
    return "unknown"


def _sys_object_id_mapping(sys_object_id: str | None) -> SysObjectIdMapping | None:
    if not sys_object_id:
        return None
    matches = [
        mapping
        for mapping in SYS_OBJECT_ID_MAPPINGS
        if sys_object_id == mapping["prefix"] or sys_object_id.startswith(f"{mapping['prefix']}.")
    ]
    if not matches:
        return None
    return max(matches, key=lambda mapping: len(mapping["prefix"]))


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
