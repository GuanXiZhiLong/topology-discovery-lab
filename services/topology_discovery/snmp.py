"""SNMP collection helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from ipaddress import ip_address
from typing import Any

from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
    walk_cmd,
)

from services.topology_discovery.config import SnmpConfig
from services.topology_discovery.models import (
    AliveHost,
    SnmpDeviceInfo,
    SnmpInterfaceInfo,
    SnmpNeighborInfo,
)

SYS_DESCR_OID = "1.3.6.1.2.1.1.1.0"
SYS_OBJECT_ID_OID = "1.3.6.1.2.1.1.2.0"
SYS_NAME_OID = "1.3.6.1.2.1.1.5.0"
IF_INDEX_OID = "1.3.6.1.2.1.2.2.1.1"
IF_DESCR_OID = "1.3.6.1.2.1.2.2.1.2"
IF_SPEED_OID = "1.3.6.1.2.1.2.2.1.5"
IF_PHYS_ADDRESS_OID = "1.3.6.1.2.1.2.2.1.6"
IF_ADMIN_STATUS_OID = "1.3.6.1.2.1.2.2.1.7"
IF_OPER_STATUS_OID = "1.3.6.1.2.1.2.2.1.8"
LLDP_REM_CHASSIS_ID_OID = "1.0.8802.1.1.2.1.4.1.1.5"
LLDP_REM_PORT_ID_OID = "1.0.8802.1.1.2.1.4.1.1.7"
LLDP_REM_SYS_NAME_OID = "1.0.8802.1.1.2.1.4.1.1.9"
LLDP_REM_SYS_DESC_OID = "1.0.8802.1.1.2.1.4.1.1.10"
LLDP_REM_SYS_CAP_ENABLED_OID = "1.0.8802.1.1.2.1.4.1.1.12"
CDP_CACHE_ADDRESS_OID = "1.3.6.1.4.1.9.9.23.1.2.1.1.4"
CDP_CACHE_DEVICE_ID_OID = "1.3.6.1.4.1.9.9.23.1.2.1.1.6"
CDP_CACHE_DEVICE_PORT_OID = "1.3.6.1.4.1.9.9.23.1.2.1.1.7"
CDP_CACHE_PLATFORM_OID = "1.3.6.1.4.1.9.9.23.1.2.1.1.8"
CDP_CACHE_CAPABILITIES_OID = "1.3.6.1.4.1.9.9.23.1.2.1.1.9"

SnmpGet = Callable[[str, SnmpConfig, str], str | None]
SnmpWalk = Callable[[str, SnmpConfig, str], dict[str, str]]


class SnmpError(RuntimeError):
    """Raised when a low-level SNMP operation fails."""


def collect_snmp_device_info(
    host: AliveHost,
    config: SnmpConfig,
    snmp_get_func: SnmpGet | None = None,
    snmp_walk_func: SnmpWalk | None = None,
) -> SnmpDeviceInfo:
    """Collect base device and interface information over SNMP."""

    get_func = snmp_get if snmp_get_func is None else snmp_get_func
    walk_func = snmp_walk if snmp_walk_func is None else snmp_walk_func

    if not config.enabled:
        return _failed_result(host.ip, "snmp_disabled")
    if not host.reachable:
        return _failed_result(host.ip, "host_unreachable")

    try:
        sys_descr = get_func(host.ip, config, SYS_DESCR_OID)
        sys_object_id = get_func(host.ip, config, SYS_OBJECT_ID_OID)
        sys_name = get_func(host.ip, config, SYS_NAME_OID)
        interfaces = _collect_interfaces(host.ip, config, walk_func)
        neighbors, collection_errors = _collect_neighbors(host.ip, config, walk_func)
    except SnmpError as exc:
        return _failed_result(host.ip, _sanitize_error(exc))
    except TimeoutError:
        return _failed_result(host.ip, "snmp_timeout")
    except OSError as exc:
        return _failed_result(host.ip, exc.__class__.__name__)

    return SnmpDeviceInfo(
        ip=host.ip,
        success=True,
        sys_name=sys_name,
        sys_descr=sys_descr,
        sys_object_id=sys_object_id,
        interfaces=interfaces,
        neighbors=neighbors,
        collection_errors=collection_errors,
    )


def snmp_get(ip: str, config: SnmpConfig, oid: str) -> str | None:
    """Run a single SNMP get request."""

    return asyncio.run(_snmp_get_async(ip, config, oid))


def snmp_walk(ip: str, config: SnmpConfig, oid: str) -> dict[str, str]:
    """Run an SNMP walk request."""

    return asyncio.run(_snmp_walk_async(ip, config, oid))


def _collect_interfaces(
    ip: str,
    config: SnmpConfig,
    walk_func: SnmpWalk,
) -> list[SnmpInterfaceInfo]:
    indexes = walk_func(ip, config, IF_INDEX_OID)
    names = walk_func(ip, config, IF_DESCR_OID)
    speeds = walk_func(ip, config, IF_SPEED_OID)
    mac_addresses = walk_func(ip, config, IF_PHYS_ADDRESS_OID)
    admin_statuses = walk_func(ip, config, IF_ADMIN_STATUS_OID)
    oper_statuses = walk_func(ip, config, IF_OPER_STATUS_OID)

    interfaces: list[SnmpInterfaceInfo] = []
    for oid, raw_index in sorted(indexes.items(), key=lambda item: _sortable_oid_suffix(item[0])):
        suffix = _oid_suffix(oid)
        if suffix is None:
            continue
        if_index = _parse_int(raw_index)
        if if_index is None:
            continue
        interfaces.append(
            SnmpInterfaceInfo(
                if_index=if_index,
                name=names.get(f"{IF_DESCR_OID}.{suffix}"),
                mac_address=mac_addresses.get(f"{IF_PHYS_ADDRESS_OID}.{suffix}"),
                admin_status=_normalize_interface_status(
                    admin_statuses.get(f"{IF_ADMIN_STATUS_OID}.{suffix}")
                ),
                oper_status=_normalize_interface_status(
                    oper_statuses.get(f"{IF_OPER_STATUS_OID}.{suffix}")
                ),
                speed_bps=_parse_int(speeds.get(f"{IF_SPEED_OID}.{suffix}")),
            )
        )
    return interfaces


def _collect_neighbors(
    ip: str,
    config: SnmpConfig,
    walk_func: SnmpWalk,
) -> tuple[list[SnmpNeighborInfo], list[str]]:
    neighbors: list[SnmpNeighborInfo] = []
    errors: list[str] = []

    for collect_func, error_name in (
        (_collect_lldp_neighbors, "lldp_collection_failed"),
        (_collect_cdp_neighbors, "cdp_collection_failed"),
    ):
        try:
            neighbors.extend(collect_func(ip, config, walk_func))
        except (SnmpError, TimeoutError, OSError, ValueError):
            errors.append(error_name)

    return neighbors, errors


def _collect_lldp_neighbors(
    ip: str,
    config: SnmpConfig,
    walk_func: SnmpWalk,
) -> list[SnmpNeighborInfo]:
    chassis_ids = walk_func(ip, config, LLDP_REM_CHASSIS_ID_OID)
    port_ids = walk_func(ip, config, LLDP_REM_PORT_ID_OID)
    system_names = walk_func(ip, config, LLDP_REM_SYS_NAME_OID)
    system_descriptions = walk_func(ip, config, LLDP_REM_SYS_DESC_OID)
    capabilities = walk_func(ip, config, LLDP_REM_SYS_CAP_ENABLED_OID)

    neighbors: list[SnmpNeighborInfo] = []
    for oid, remote_name in sorted(system_names.items()):
        suffix = _table_suffix(oid, LLDP_REM_SYS_NAME_OID)
        if suffix is None:
            continue
        neighbors.append(
            SnmpNeighborInfo(
                protocol="lldp",
                remote_chassis_id=chassis_ids.get(f"{LLDP_REM_CHASSIS_ID_OID}.{suffix}"),
                remote_port_id=port_ids.get(f"{LLDP_REM_PORT_ID_OID}.{suffix}"),
                remote_system_name=remote_name,
                remote_system_description=system_descriptions.get(
                    f"{LLDP_REM_SYS_DESC_OID}.{suffix}"
                ),
                capabilities=capabilities.get(f"{LLDP_REM_SYS_CAP_ENABLED_OID}.{suffix}"),
            )
        )
    return neighbors


def _collect_cdp_neighbors(
    ip: str,
    config: SnmpConfig,
    walk_func: SnmpWalk,
) -> list[SnmpNeighborInfo]:
    addresses = walk_func(ip, config, CDP_CACHE_ADDRESS_OID)
    device_ids = walk_func(ip, config, CDP_CACHE_DEVICE_ID_OID)
    ports = walk_func(ip, config, CDP_CACHE_DEVICE_PORT_OID)
    platforms = walk_func(ip, config, CDP_CACHE_PLATFORM_OID)
    capabilities = walk_func(ip, config, CDP_CACHE_CAPABILITIES_OID)

    neighbors: list[SnmpNeighborInfo] = []
    for oid, remote_name in sorted(device_ids.items()):
        suffix = _table_suffix(oid, CDP_CACHE_DEVICE_ID_OID)
        if suffix is None:
            continue
        neighbors.append(
            SnmpNeighborInfo(
                protocol="cdp",
                local_interface_index=_cdp_local_interface_from_suffix(suffix),
                remote_port_id=ports.get(f"{CDP_CACHE_DEVICE_PORT_OID}.{suffix}"),
                remote_system_name=remote_name,
                remote_system_description=platforms.get(f"{CDP_CACHE_PLATFORM_OID}.{suffix}"),
                remote_management_address=_normalize_ip_address(
                    addresses.get(f"{CDP_CACHE_ADDRESS_OID}.{suffix}")
                ),
                capabilities=capabilities.get(f"{CDP_CACHE_CAPABILITIES_OID}.{suffix}"),
            )
        )
    return neighbors


async def _snmp_get_async(ip: str, config: SnmpConfig, oid: str) -> str | None:
    transport = await UdpTransportTarget.create(
        (ip, config.port),
        timeout=config.timeout_seconds,
        retries=config.retry_count,
    )
    error_indication, error_status, _error_index, var_binds = await get_cmd(
        SnmpEngine(),
        CommunityData(config.community, mpModel=1),
        transport,
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
    )
    _raise_for_snmp_error(error_indication, error_status)
    if not var_binds:
        return None
    return str(var_binds[0][1])


async def _snmp_walk_async(ip: str, config: SnmpConfig, oid: str) -> dict[str, str]:
    transport = await UdpTransportTarget.create(
        (ip, config.port),
        timeout=config.timeout_seconds,
        retries=config.retry_count,
    )
    result: dict[str, str] = {}
    async for error_indication, error_status, _error_index, var_binds in walk_cmd(
        SnmpEngine(),
        CommunityData(config.community, mpModel=1),
        transport,
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
        lexicographicMode=False,
    ):
        _raise_for_snmp_error(error_indication, error_status)
        for name, value in var_binds:
            result[str(name)] = str(value)
    return result


def _raise_for_snmp_error(error_indication: Any, error_status: Any) -> None:
    if error_indication:
        raise SnmpError(_classify_snmp_error(str(error_indication)))
    if error_status:
        raise SnmpError(_classify_snmp_error(str(error_status)))


def _failed_result(ip: str, error: str) -> SnmpDeviceInfo:
    return SnmpDeviceInfo(ip=ip, success=False, error=error)


def _sanitize_error(exc: Exception) -> str:
    if isinstance(exc, SnmpError):
        return str(exc)
    return exc.__class__.__name__


def _classify_snmp_error(message: str) -> str:
    normalized = message.casefold()
    if "timeout" in normalized or "timed out" in normalized or "no response" in normalized:
        return "snmp_timeout"
    if "auth" in normalized or "authorization" in normalized or "community" in normalized:
        return "snmp_auth_failed"
    if (
        "unreachable" in normalized
        or "network is unreachable" in normalized
        or "connection refused" in normalized
        or "host down" in normalized
    ):
        return "snmp_transport_unreachable"
    if "no such" in normalized or "nosuch" in normalized or "unknown object" in normalized:
        return "snmp_oid_unsupported"
    if "parse" in normalized or "decode" in normalized:
        return "snmp_parse_error"
    return "snmp_unknown_error"


def _oid_suffix(oid: str) -> int | None:
    try:
        return int(oid.rsplit(".", maxsplit=1)[1])
    except (IndexError, ValueError):
        return None


def _sortable_oid_suffix(oid: str) -> int:
    return _oid_suffix(oid) or 0


def _table_suffix(oid: str, base_oid: str) -> str | None:
    prefix = f"{base_oid}."
    if not oid.startswith(prefix):
        return None
    suffix = oid.removeprefix(prefix)
    return suffix or None


def _cdp_local_interface_from_suffix(suffix: str) -> int | None:
    parts = suffix.split(".")
    if not parts:
        return None
    return _parse_int(parts[0])


def _normalize_ip_address(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return str(ip_address(value))
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _normalize_interface_status(value: str | None) -> str | None:
    if value == "1":
        return "up"
    if value == "2":
        return "down"
    if value is None:
        return None
    return "unknown"
