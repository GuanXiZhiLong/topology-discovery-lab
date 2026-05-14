"""Core topology discovery data models."""

from __future__ import annotations

from datetime import datetime
from ipaddress import ip_address
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DeviceType = Literal["router", "switch", "firewall", "server", "wireless_ap", "unknown"]
DeviceStatus = Literal["online", "offline", "unknown", "partial"]


class DiscoveryBaseModel(BaseModel):
    """Base model configuration shared by discovery models."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*")
    @classmethod
    def validate_timezone_aware_datetime(cls, value: object) -> object:
        if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("datetime values must be timezone-aware")
        return value


class AliveHost(DiscoveryBaseModel):
    """A host discovered by a reachability probe."""

    ip: str
    reachable: bool
    latency_ms: float | None = None
    discovered_by: str
    error: str | None = None

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, value: str) -> str:
        ip_address(value)
        return value

    @field_validator("latency_ms")
    @classmethod
    def validate_latency(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("latency_ms must be greater than or equal to 0")
        return value


class DeviceNode(DiscoveryBaseModel):
    """A network device node in a topology snapshot."""

    device_id: str
    ip: str
    hostname: str | None = None
    device_type: DeviceType
    vendor: str | None = None
    model: str | None = None
    os_version: str | None = None
    sys_descr: str | None = None
    sys_object_id: str | None = None
    status: DeviceStatus
    last_seen: datetime
    source: str

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, value: str) -> str:
        ip_address(value)
        return value


class InterfaceNode(DiscoveryBaseModel):
    """A network interface that belongs to a device."""

    interface_id: str
    device_id: str
    name: str
    description: str | None = None
    mac_address: str | None = None
    if_index: int | None = None
    admin_status: str | None = None
    oper_status: str | None = None
    speed_bps: int | None = None
    last_seen: datetime

    @field_validator("if_index")
    @classmethod
    def validate_if_index(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("if_index must be greater than or equal to 0")
        return value

    @field_validator("speed_bps")
    @classmethod
    def validate_speed(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("speed_bps must be greater than or equal to 0")
        return value


class LinkEdge(DiscoveryBaseModel):
    """A discovered connection between two devices or interfaces."""

    link_id: str
    source_device_id: str
    target_device_id: str
    source_interface_id: str | None = None
    target_interface_id: str | None = None
    discovery_method: str
    confidence: float = Field(ge=0.0, le=1.0)
    last_seen: datetime


class DiscoveryError(DiscoveryBaseModel):
    """A recoverable or fatal error observed during discovery."""

    target: str
    stage: str
    message: str
    recoverable: bool


class TopologySnapshot(DiscoveryBaseModel):
    """A complete topology discovery result."""

    snapshot_id: str
    started_at: datetime
    finished_at: datetime | None = None
    devices: list[DeviceNode] = Field(default_factory=list)
    interfaces: list[InterfaceNode] = Field(default_factory=list)
    links: list[LinkEdge] = Field(default_factory=list)
    errors: list[DiscoveryError] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_finished_at(self) -> TopologySnapshot:
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at must be greater than or equal to started_at")
        return self
