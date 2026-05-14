"""Neo4j persistence layer for topology snapshots."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from ipaddress import ip_address, ip_network
from typing import Any, Protocol, cast

from neo4j import GraphDatabase

from services.topology_discovery.config import Neo4jConfig
from services.topology_discovery.models import (
    DeviceNode,
    InterfaceNode,
    LinkEdge,
    NetworkSegmentNode,
    TopologySnapshot,
)


class Neo4jRepositoryError(RuntimeError):
    """Raised when Neo4j operations fail."""


class Session(Protocol):
    """Minimal Neo4j session protocol used by the repository."""

    def __enter__(self) -> Session:
        """Enter the session context."""

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Exit the session context."""

    def run(self, query: str, parameters: Mapping[str, Any] | None = None) -> Any:
        """Run a Cypher query."""


class Driver(Protocol):
    """Minimal Neo4j driver protocol used by the repository."""

    def session(self, **kwargs: Any) -> Session:
        """Create a database session."""

    def verify_connectivity(self) -> None:
        """Verify the driver can connect."""

    def close(self) -> None:
        """Close the driver."""


DriverFactory = Callable[[str, tuple[str, str]], Driver]


class Neo4jTopologyRepository:
    """Persist topology snapshots to Neo4j using idempotent Cypher."""

    def __init__(
        self,
        config: Neo4jConfig,
        driver_factory: DriverFactory | None = None,
    ) -> None:
        self._config = config
        self._driver_factory = driver_factory or _create_driver
        self._driver: Driver | None = None

    def connect(self) -> None:
        """Create a driver and verify connectivity."""

        try:
            self._driver = self._driver_factory(
                self._config.uri,
                (self._config.username, self._config.password),
            )
            self._driver.verify_connectivity()
        except Exception as exc:  # noqa: BLE001
            self._driver = None
            raise Neo4jRepositoryError("failed to connect to Neo4j") from exc

    def close(self) -> None:
        """Close the underlying driver if it has been opened."""

        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def save_snapshot(self, snapshot: TopologySnapshot) -> None:
        """Persist all devices, interfaces, and links from a snapshot."""

        driver = self._require_driver()
        try:
            with driver.session(database=self._config.database) as session:
                for device in snapshot.devices:
                    self._upsert_device(session, device)
                for segment in snapshot.network_segments:
                    self._upsert_network_segment(session, segment)
                for device in snapshot.devices:
                    for segment in snapshot.network_segments:
                        if _device_belongs_to_segment(device, segment):
                            self._upsert_device_segment_relationship(session, device, segment)
                for interface in snapshot.interfaces:
                    self._upsert_interface(session, interface)
                for link in snapshot.links:
                    self._upsert_link(session, link)
        except Exception as exc:  # noqa: BLE001
            raise Neo4jRepositoryError("failed to save topology snapshot") from exc

    def _require_driver(self) -> Driver:
        if self._driver is None:
            self.connect()
        if self._driver is None:
            raise Neo4jRepositoryError("failed to initialize Neo4j driver")
        return self._driver

    def _upsert_device(self, session: Session, device: DeviceNode) -> None:
        session.run(
            """
            MERGE (d:Device {device_id: $device_id})
            SET d.ip = $ip,
                d.hostname = $hostname,
                d.device_type = $device_type,
                d.vendor = $vendor,
                d.model = $model,
                d.os_version = $os_version,
                d.status = $status,
                d.sys_descr = $sys_descr,
                d.sys_object_id = $sys_object_id,
                d.last_seen = $last_seen,
                d.source = $source
            """,
            _device_parameters(device),
        )

    def _upsert_interface(self, session: Session, interface: InterfaceNode) -> None:
        session.run(
            """
            MERGE (i:Interface {interface_id: $interface_id})
            SET i.device_id = $device_id,
                i.name = $name,
                i.description = $description,
                i.mac_address = $mac_address,
                i.if_index = $if_index,
                i.admin_status = $admin_status,
                i.oper_status = $oper_status,
                i.speed_bps = $speed_bps,
                i.last_seen = $last_seen
            WITH i
            MATCH (d:Device {device_id: $device_id})
            MERGE (d)-[:HAS_INTERFACE]->(i)
            """,
            _interface_parameters(interface),
        )

    def _upsert_network_segment(self, session: Session, segment: NetworkSegmentNode) -> None:
        session.run(
            """
            MERGE (s:NetworkSegment {segment_id: $segment_id})
            SET s.target = $target,
                s.cidr = $cidr,
                s.source = $source,
                s.last_seen = $last_seen
            """,
            _network_segment_parameters(segment),
        )

    def _upsert_device_segment_relationship(
        self,
        session: Session,
        device: DeviceNode,
        segment: NetworkSegmentNode,
    ) -> None:
        session.run(
            """
            MATCH (d:Device {device_id: $device_id})
            MATCH (s:NetworkSegment {segment_id: $segment_id})
            MERGE (d)-[:BELONGS_TO_SEGMENT]->(s)
            """,
            {
                "device_id": device.device_id,
                "segment_id": segment.segment_id,
            },
        )

    def _upsert_link(self, session: Session, link: LinkEdge) -> None:
        if link.source_interface_id and link.target_interface_id:
            session.run(
                """
                MATCH (source:Interface {interface_id: $source_interface_id})
                MATCH (target:Interface {interface_id: $target_interface_id})
                MERGE (source)-[r:CONNECTED_TO {link_id: $link_id}]->(target)
                SET r.discovery_method = $discovery_method,
                r.confidence = $confidence,
                r.last_seen = $last_seen
                """,
                _normalized_link_parameters(link),
            )
            return

        session.run(
            """
            MATCH (source:Device {device_id: $source_device_id})
            MATCH (target:Device {device_id: $target_device_id})
            MERGE (source)-[r:CONNECTED_TO {link_id: $link_id}]->(target)
            SET r.discovery_method = $discovery_method,
                r.confidence = $confidence,
                r.last_seen = $last_seen
            """,
            _normalized_link_parameters(link),
        )


def _create_driver(uri: str, auth: tuple[str, str]) -> Driver:
    return cast(Driver, GraphDatabase.driver(uri, auth=auth))


def _device_parameters(device: DeviceNode) -> dict[str, Any]:
    return {
        "device_id": device.device_id,
        "ip": device.ip,
        "hostname": device.hostname,
        "device_type": device.device_type,
        "vendor": device.vendor,
        "model": device.model,
        "os_version": device.os_version,
        "status": device.status,
        "sys_descr": device.sys_descr,
        "sys_object_id": device.sys_object_id,
        "last_seen": _to_neo4j_datetime(device.last_seen),
        "source": device.source,
    }


def _interface_parameters(interface: InterfaceNode) -> dict[str, Any]:
    return {
        "interface_id": interface.interface_id,
        "device_id": interface.device_id,
        "name": interface.name,
        "description": interface.description,
        "mac_address": interface.mac_address,
        "if_index": interface.if_index,
        "admin_status": interface.admin_status,
        "oper_status": interface.oper_status,
        "speed_bps": interface.speed_bps,
        "last_seen": _to_neo4j_datetime(interface.last_seen),
    }


def _network_segment_parameters(segment: NetworkSegmentNode) -> dict[str, Any]:
    return {
        "segment_id": segment.segment_id,
        "target": segment.target,
        "cidr": segment.cidr,
        "source": segment.source,
        "last_seen": _to_neo4j_datetime(segment.last_seen),
    }


def _normalized_link_parameters(link: LinkEdge) -> dict[str, Any]:
    source_device_id = link.source_device_id
    target_device_id = link.target_device_id
    source_interface_id = link.source_interface_id
    target_interface_id = link.target_interface_id

    if source_interface_id and target_interface_id:
        if source_interface_id > target_interface_id:
            source_interface_id, target_interface_id = target_interface_id, source_interface_id
            source_device_id, target_device_id = target_device_id, source_device_id
    elif source_device_id > target_device_id:
        source_device_id, target_device_id = target_device_id, source_device_id

    return {
        "link_id": link.link_id,
        "source_device_id": source_device_id,
        "target_device_id": target_device_id,
        "source_interface_id": source_interface_id,
        "target_interface_id": target_interface_id,
        "discovery_method": link.discovery_method,
        "confidence": link.confidence,
        "last_seen": _to_neo4j_datetime(link.last_seen),
    }


def _to_neo4j_datetime(value: datetime) -> str:
    return value.isoformat()


def _device_belongs_to_segment(device: DeviceNode, segment: NetworkSegmentNode) -> bool:
    device_ip = ip_address(device.ip)
    if segment.cidr is None:
        return device_ip == ip_address(segment.target)
    return device_ip in ip_network(segment.cidr, strict=False)
