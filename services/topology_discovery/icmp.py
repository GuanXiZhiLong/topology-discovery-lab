"""Reachability scanning helpers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from ipaddress import ip_address, ip_network
from time import perf_counter
from typing import Protocol

from scapy.layers.inet import ICMP, IP
from scapy.sendrecv import sr1

from services.topology_discovery.config import ScanConfig
from services.topology_discovery.models import AliveHost


class Probe(Protocol):
    """Callable used to probe a single IP address."""

    def __call__(self, ip: str, timeout_seconds: float) -> AliveHost:
        """Probe a single IP address."""


def expand_targets(targets: list[str]) -> list[str]:
    """Expand IP and CIDR scan targets into a de-duplicated IP list."""

    expanded: list[str] = []
    seen: set[str] = set()
    for target in targets:
        for ip in _expand_target(target):
            if ip not in seen:
                expanded.append(ip)
                seen.add(ip)
    return expanded


def probe_host(ip: str, timeout_seconds: float) -> AliveHost:
    """Probe a single host with ICMP echo and return a reachability result."""

    start = perf_counter()
    try:
        response = _send_icmp_echo(ip, timeout_seconds)
    except OSError as exc:
        return AliveHost(
            ip=ip,
            reachable=False,
            latency_ms=None,
            discovered_by="icmp",
            error=exc.__class__.__name__,
        )

    reachable = response is not None
    latency_ms = (perf_counter() - start) * 1000
    return AliveHost(
        ip=ip,
        reachable=reachable,
        latency_ms=latency_ms if reachable else None,
        discovered_by="icmp",
        error=None if reachable else "unreachable",
    )


def scan_alive_hosts(config: ScanConfig, probe: Probe = probe_host) -> list[AliveHost]:
    """Scan configured targets and return reachability results for each IP."""

    ips = expand_targets(config.targets)
    results_by_ip: dict[str, AliveHost] = {}
    max_workers = min(config.max_concurrency, len(ips)) or 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _probe_with_retries,
                ip,
                config.timeout_seconds,
                config.retry_count,
                probe,
            ): ip
            for ip in ips
        }
        for future in as_completed(futures):
            ip = futures[future]
            try:
                results_by_ip[ip] = future.result()
            except Exception as exc:  # noqa: BLE001
                results_by_ip[ip] = AliveHost(
                    ip=ip,
                    reachable=False,
                    latency_ms=None,
                    discovered_by="icmp",
                    error=exc.__class__.__name__,
                )

    return [results_by_ip[ip] for ip in ips]


def _expand_target(target: str) -> list[str]:
    try:
        return [str(ip_address(target))]
    except ValueError:
        network = ip_network(target, strict=False)
        return [str(ip) for ip in network.hosts()]


def _probe_with_retries(
    ip: str,
    timeout_seconds: float,
    retry_count: int,
    probe: Probe,
) -> AliveHost:
    attempts = retry_count + 1
    last_result: AliveHost | None = None

    for _ in range(attempts):
        last_result = probe(ip, timeout_seconds)
        if last_result.reachable:
            return last_result

    if last_result is None:
        return AliveHost(
            ip=ip,
            reachable=False,
            latency_ms=None,
            discovered_by="icmp",
            error="not_probed",
        )
    return last_result


def _send_icmp_echo(ip: str, timeout_seconds: float) -> object | None:
    return sr1(
        IP(dst=ip) / ICMP(),
        timeout=timeout_seconds,
        verbose=False,
    )
