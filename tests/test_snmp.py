from __future__ import annotations

from services.topology_discovery.config import SnmpConfig
from services.topology_discovery.models import AliveHost
from services.topology_discovery.snmp import (
    IF_ADMIN_STATUS_OID,
    IF_DESCR_OID,
    IF_INDEX_OID,
    IF_OPER_STATUS_OID,
    IF_PHYS_ADDRESS_OID,
    IF_SPEED_OID,
    SYS_DESCR_OID,
    SYS_NAME_OID,
    SYS_OBJECT_ID_OID,
    SnmpError,
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
    assert result.error == "snmp request failed"
    assert "dummy-community" not in str(result)


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
    raise SnmpError("snmp request failed")


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
