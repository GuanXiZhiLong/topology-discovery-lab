from __future__ import annotations

from services.topology_discovery.config import SnmpConfig
from services.topology_discovery.models import AliveHost
from services.topology_discovery.snmp import (
    CDP_CACHE_ADDRESS_OID,
    CDP_CACHE_DEVICE_ID_OID,
    CDP_CACHE_DEVICE_PORT_OID,
    IF_ADMIN_STATUS_OID,
    IF_DESCR_OID,
    IF_INDEX_OID,
    IF_OPER_STATUS_OID,
    IF_PHYS_ADDRESS_OID,
    IF_SPEED_OID,
    LLDP_REM_CHASSIS_ID_OID,
    LLDP_REM_PORT_ID_OID,
    LLDP_REM_SYS_NAME_OID,
    SYS_DESCR_OID,
    SYS_NAME_OID,
    SYS_OBJECT_ID_OID,
    SnmpError,
    _raise_for_snmp_error,
    collect_snmp_device_info,
)


def test_collect_snmp_device_info_success() -> None:
    result = collect_snmp_device_info(
        _host(),
        _config(),
        snmp_get_func=_mock_get,
        snmp_walk_func=_mock_walk,
    )

    assert result.success is True
    assert result.sys_name == "example-device"
    assert result.sys_descr == "Example Switch"
    assert result.sys_object_id == "1.3.6.1.4.1.999"
    assert len(result.interfaces) == 1
    assert result.interfaces[0].name == "GigabitEthernet0/1"
    assert result.interfaces[0].admin_status == "up"
    assert result.interfaces[0].oper_status == "down"


def test_collect_snmp_device_info_collects_lldp_and_cdp_neighbors() -> None:
    result = collect_snmp_device_info(
        _host(),
        _config(),
        snmp_get_func=_mock_get,
        snmp_walk_func=_mock_walk_with_neighbors,
    )

    assert result.success is True
    assert [neighbor.protocol for neighbor in result.neighbors] == ["lldp", "cdp"]
    assert result.neighbors[0].local_interface_index == 1
    assert result.neighbors[0].remote_system_name == "example-neighbor"
    assert result.neighbors[1].remote_management_address == "198.51.100.1"


def test_collect_snmp_device_info_keeps_base_data_when_neighbor_collection_fails() -> None:
    result = collect_snmp_device_info(
        _host(),
        _config(),
        snmp_get_func=_mock_get,
        snmp_walk_func=_neighbor_failure_walk,
    )

    assert result.success is True
    assert len(result.interfaces) == 1
    assert result.neighbors == []
    assert result.collection_errors == ["lldp_collection_failed", "cdp_collection_failed"]


def test_collect_snmp_device_info_disabled_returns_failed_result() -> None:
    config = _config(enabled=False)

    result = collect_snmp_device_info(
        _host(),
        config,
        snmp_get_func=_mock_get,
        snmp_walk_func=_mock_walk,
    )

    assert result.success is False
    assert result.error == "snmp_disabled"


def test_collect_snmp_device_info_unreachable_host_returns_failed_result() -> None:
    result = collect_snmp_device_info(
        AliveHost(ip="192.0.2.1", reachable=False, discovered_by="icmp"),
        _config(),
        snmp_get_func=_mock_get,
        snmp_walk_func=_mock_walk,
    )

    assert result.success is False
    assert result.error == "host_unreachable"


def test_collect_snmp_device_info_timeout_is_structured_and_sanitized() -> None:
    result = collect_snmp_device_info(
        _host(),
        _config(),
        snmp_get_func=_timeout_get,
        snmp_walk_func=_mock_walk,
    )

    assert result.success is False
    assert result.error == "snmp_timeout"
    assert "dummy-community" not in str(result)


def test_collect_snmp_device_info_auth_failure_is_sanitized() -> None:
    result = collect_snmp_device_info(
        _host(),
        _config(),
        snmp_get_func=_auth_failure_get,
        snmp_walk_func=_mock_walk,
    )

    assert result.success is False
    assert result.error == "snmp_auth_failed"
    assert "dummy-community" not in str(result)


def test_collect_snmp_device_info_transport_failure_is_classified() -> None:
    result = collect_snmp_device_info(
        _host(),
        _config(),
        snmp_get_func=_transport_failure_get,
        snmp_walk_func=_mock_walk,
    )

    assert result.success is False
    assert result.error == "snmp_transport_unreachable"


def test_collect_snmp_device_info_unsupported_oid_is_classified() -> None:
    result = collect_snmp_device_info(
        _host(),
        _config(),
        snmp_get_func=_unsupported_oid_get,
        snmp_walk_func=_mock_walk,
    )

    assert result.success is False
    assert result.error == "snmp_oid_unsupported"


def test_raise_for_snmp_error_classifies_low_level_errors() -> None:
    cases = {
        "No response received before timeout": "snmp_timeout",
        "authorization error": "snmp_auth_failed",
        "network is unreachable": "snmp_transport_unreachable",
        "No Such Object": "snmp_oid_unsupported",
        "failed to decode response": "snmp_parse_error",
        "unexpected failure": "snmp_unknown_error",
    }

    for message, expected in cases.items():
        try:
            _raise_for_snmp_error(message, None)
        except SnmpError as exc:
            assert str(exc) == expected


def test_collect_snmp_device_info_missing_oid_keeps_partial_raw_data() -> None:
    result = collect_snmp_device_info(
        _host(),
        _config(),
        snmp_get_func=_missing_oid_get,
        snmp_walk_func=_mock_walk,
    )

    assert result.success is True
    assert result.sys_name is None
    assert result.interfaces[0].if_index == 1


def _host() -> AliveHost:
    return AliveHost(ip="192.0.2.1", reachable=True, discovered_by="icmp")


def _config(enabled: bool = True) -> SnmpConfig:
    return SnmpConfig(
        enabled=enabled,
        version="2c",
        community="dummy-community",
        timeout_seconds=2,
        retry_count=1,
        port=161,
    )


def _mock_get(ip: str, config: SnmpConfig, oid: str) -> str | None:
    values = {
        SYS_DESCR_OID: "Example Switch",
        SYS_OBJECT_ID_OID: "1.3.6.1.4.1.999",
        SYS_NAME_OID: "example-device",
    }
    return values.get(oid)


def _missing_oid_get(ip: str, config: SnmpConfig, oid: str) -> str | None:
    if oid == SYS_NAME_OID:
        return None
    return _mock_get(ip, config, oid)


def _timeout_get(ip: str, config: SnmpConfig, oid: str) -> str | None:
    raise TimeoutError


def _auth_failure_get(ip: str, config: SnmpConfig, oid: str) -> str | None:
    raise SnmpError("snmp_auth_failed")


def _transport_failure_get(ip: str, config: SnmpConfig, oid: str) -> str | None:
    raise SnmpError("snmp_transport_unreachable")


def _unsupported_oid_get(ip: str, config: SnmpConfig, oid: str) -> str | None:
    raise SnmpError("snmp_oid_unsupported")


def _mock_walk(ip: str, config: SnmpConfig, oid: str) -> dict[str, str]:
    values_by_oid = {
        IF_INDEX_OID: {f"{IF_INDEX_OID}.1": "1"},
        IF_DESCR_OID: {f"{IF_DESCR_OID}.1": "GigabitEthernet0/1"},
        IF_SPEED_OID: {f"{IF_SPEED_OID}.1": "1000000000"},
        IF_PHYS_ADDRESS_OID: {f"{IF_PHYS_ADDRESS_OID}.1": "00:11:22:33:44:55"},
        IF_ADMIN_STATUS_OID: {f"{IF_ADMIN_STATUS_OID}.1": "1"},
        IF_OPER_STATUS_OID: {f"{IF_OPER_STATUS_OID}.1": "2"},
    }
    return values_by_oid.get(oid, {})


def _mock_walk_with_neighbors(ip: str, config: SnmpConfig, oid: str) -> dict[str, str]:
    values = _mock_walk(ip, config, oid)
    if values:
        return values

    lldp_suffix = "0.1.1"
    cdp_suffix = "1.1"
    values_by_oid = {
        LLDP_REM_CHASSIS_ID_OID: {f"{LLDP_REM_CHASSIS_ID_OID}.{lldp_suffix}": "chassis-1"},
        LLDP_REM_PORT_ID_OID: {f"{LLDP_REM_PORT_ID_OID}.{lldp_suffix}": "GigabitEthernet0/2"},
        LLDP_REM_SYS_NAME_OID: {f"{LLDP_REM_SYS_NAME_OID}.{lldp_suffix}": "example-neighbor"},
        CDP_CACHE_ADDRESS_OID: {f"{CDP_CACHE_ADDRESS_OID}.{cdp_suffix}": "198.51.100.1"},
        CDP_CACHE_DEVICE_ID_OID: {f"{CDP_CACHE_DEVICE_ID_OID}.{cdp_suffix}": "example-router"},
        CDP_CACHE_DEVICE_PORT_OID: {
            f"{CDP_CACHE_DEVICE_PORT_OID}.{cdp_suffix}": "GigabitEthernet0/2"
        },
    }
    return values_by_oid.get(oid, {})


def _neighbor_failure_walk(ip: str, config: SnmpConfig, oid: str) -> dict[str, str]:
    values = _mock_walk(ip, config, oid)
    if values:
        return values
    raise SnmpError("snmp_oid_unsupported")
