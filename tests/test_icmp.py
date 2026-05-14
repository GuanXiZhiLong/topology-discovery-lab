from __future__ import annotations

from typing import Any

import pytest

from services.topology_discovery.config import ScanConfig
from services.topology_discovery.icmp import (
    expand_target_sources,
    expand_targets,
    probe_host,
    scan_alive_hosts,
)
from services.topology_discovery.models import AliveHost


def test_expand_targets_supports_single_ip() -> None:
    assert expand_targets(["192.0.2.1"]) == ["192.0.2.1"]


def test_expand_targets_supports_cidr() -> None:
    assert expand_targets(["192.0.2.0/30"]) == ["192.0.2.1", "192.0.2.2"]


def test_expand_targets_deduplicates_in_order() -> None:
    assert expand_targets(["192.0.2.1", "192.0.2.0/30"]) == ["192.0.2.1", "192.0.2.2"]


def test_expand_target_sources_preserves_overlapping_target_sources() -> None:
    assert expand_target_sources(["192.0.2.1", "192.0.2.0/30"]) == {
        "192.0.2.1": ["192.0.2.1", "192.0.2.0/30"],
        "192.0.2.2": ["192.0.2.0/30"],
    }


def test_scan_alive_hosts_returns_alive_host_results() -> None:
    config = ScanConfig(
        targets=["192.0.2.1"],
        timeout_seconds=2,
        retry_count=0,
        max_concurrency=4,
    )

    results = scan_alive_hosts(config, probe=_successful_probe)

    assert results == [
        AliveHost(
            ip="192.0.2.1",
            reachable=True,
            latency_ms=1.0,
            discovered_by="icmp",
            source_target="192.0.2.1",
            source_targets=["192.0.2.1"],
        )
    ]


def test_scan_alive_hosts_reports_failed_probe_without_stopping() -> None:
    config = ScanConfig(
        targets=["192.0.2.1", "198.51.100.1"],
        timeout_seconds=2,
        retry_count=0,
        max_concurrency=2,
    )

    results = scan_alive_hosts(config, probe=_mixed_probe)

    assert [result.ip for result in results] == ["192.0.2.1", "198.51.100.1"]
    assert results[0].reachable is True
    assert results[0].source_targets == ["192.0.2.1"]
    assert results[1].reachable is False
    assert results[1].source_target == "198.51.100.1"
    assert results[1].error == "timeout"


def test_scan_alive_hosts_records_all_source_targets_for_overlapping_ranges() -> None:
    config = ScanConfig(
        targets=["192.0.2.1", "192.0.2.0/30"],
        timeout_seconds=2,
        retry_count=0,
        max_concurrency=2,
    )

    results = scan_alive_hosts(config, probe=_successful_probe)

    assert results[0].ip == "192.0.2.1"
    assert results[0].source_target == "192.0.2.1"
    assert results[0].source_targets == ["192.0.2.1", "192.0.2.0/30"]
    assert results[1].ip == "192.0.2.2"
    assert results[1].source_targets == ["192.0.2.0/30"]


def test_scan_alive_hosts_retries_until_success() -> None:
    config = ScanConfig(
        targets=["192.0.2.1"],
        timeout_seconds=2,
        retry_count=1,
        max_concurrency=1,
    )
    calls: list[str] = []

    def probe(ip: str, timeout_seconds: float) -> AliveHost:
        calls.append(ip)
        if len(calls) == 1:
            return AliveHost(
                ip=ip,
                reachable=False,
                latency_ms=None,
                discovered_by="icmp",
                error="timeout",
            )
        return _successful_probe(ip, timeout_seconds)

    results = scan_alive_hosts(config, probe=probe)

    assert len(calls) == 2
    assert results[0].reachable is True


def test_scan_alive_hosts_converts_probe_exception_to_failed_result() -> None:
    config = ScanConfig(
        targets=["192.0.2.1"],
        timeout_seconds=2,
        retry_count=0,
        max_concurrency=1,
    )

    results = scan_alive_hosts(config, probe=_raising_probe)

    assert results[0] == AliveHost(
        ip="192.0.2.1",
        reachable=False,
        latency_ms=None,
        discovered_by="icmp",
        source_target="192.0.2.1",
        source_targets=["192.0.2.1"],
        error="RuntimeError",
    )


def test_probe_host_uses_icmp_echo_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.topology_discovery.icmp.sr1", _successful_sr1)

    result = probe_host("192.0.2.1", timeout_seconds=2)

    assert result.ip == "192.0.2.1"
    assert result.reachable is True
    assert result.discovered_by == "icmp"
    assert result.error is None


def test_probe_host_reports_unreachable_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.topology_discovery.icmp.sr1", _timeout_sr1)

    result = probe_host("192.0.2.1", timeout_seconds=2)

    assert result.reachable is False
    assert result.error == "unreachable"


def test_probe_host_converts_os_error_to_failed_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.topology_discovery.icmp.sr1", _raising_sr1)

    result = probe_host("192.0.2.1", timeout_seconds=2)

    assert result.reachable is False
    assert result.error == "PermissionError"


def _successful_probe(ip: str, timeout_seconds: float) -> AliveHost:
    return AliveHost(
        ip=ip,
        reachable=True,
        latency_ms=1.0,
        discovered_by="icmp",
    )


def _mixed_probe(ip: str, timeout_seconds: float) -> AliveHost:
    if ip == "192.0.2.1":
        return _successful_probe(ip, timeout_seconds)
    return AliveHost(
        ip=ip,
        reachable=False,
        latency_ms=None,
        discovered_by="icmp",
        error="timeout",
    )


def _raising_probe(ip: str, timeout_seconds: float) -> AliveHost:
    raise RuntimeError("probe failed")


def _successful_sr1(*args: Any, **kwargs: Any) -> object:
    return object()


def _timeout_sr1(*args: Any, **kwargs: Any) -> None:
    return None


def _raising_sr1(*args: Any, **kwargs: Any) -> None:
    raise PermissionError("raw socket denied")
