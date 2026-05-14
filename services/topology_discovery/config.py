"""Configuration loading and validation."""

from __future__ import annotations

from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class ConfigError(ValueError):
    """Raised when application configuration cannot be loaded or validated."""


class ConfigBaseModel(BaseModel):
    """Base model configuration shared by config models."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ScanConfig(ConfigBaseModel):
    """Scan target and reachability settings."""

    targets: list[str] = Field(min_length=1)
    timeout_seconds: float = Field(gt=0)
    retry_count: int = Field(ge=0)
    max_concurrency: int = Field(gt=0)

    @field_validator("targets")
    @classmethod
    def validate_targets(cls, values: list[str]) -> list[str]:
        for value in values:
            _validate_ip_or_network(value)
        return values


class SnmpConfig(ConfigBaseModel):
    """SNMP collection settings."""

    enabled: bool
    version: Literal["2c"]
    community: str
    timeout_seconds: float = Field(gt=0)
    retry_count: int = Field(ge=0)
    port: int = Field(default=161, ge=1, le=65535)

    @model_validator(mode="after")
    def validate_enabled_settings(self) -> SnmpConfig:
        if self.enabled and not self.community:
            raise ValueError("snmp community is required when snmp is enabled")
        return self


class SshConfig(ConfigBaseModel):
    """SSH supplemental collection settings."""

    enabled: bool
    username: str
    password: str
    timeout_seconds: float = Field(gt=0)
    port: int = Field(default=22, ge=1, le=65535)
    commands: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_enabled_settings(self) -> SshConfig:
        if self.enabled and not self.username:
            raise ValueError("ssh username is required when ssh is enabled")
        if self.enabled and not self.commands:
            raise ValueError("ssh commands are required when ssh is enabled")
        return self


class Neo4jConfig(ConfigBaseModel):
    """Neo4j connection settings."""

    uri: str = Field(min_length=1)
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    database: str = Field(min_length=1)


class AppConfig(ConfigBaseModel):
    """Top-level application configuration."""

    scan: ScanConfig
    snmp: SnmpConfig
    ssh: SshConfig
    neo4j: Neo4jConfig


def load_config(path: str) -> AppConfig:
    """Load and validate application configuration from a YAML file."""

    config_path = Path(path)
    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"failed to read config file: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"failed to parse config file: {config_path}") from exc

    if not isinstance(raw_config, dict):
        raise ConfigError("config file must contain a mapping at the top level")

    try:
        return AppConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigError(_sanitize_validation_error(exc)) from exc


def _validate_ip_or_network(value: str) -> None:
    try:
        ip_address(value)
        return
    except ValueError:
        pass

    try:
        ip_network(value, strict=False)
    except ValueError as exc:
        raise ValueError("target must be a valid IP address or CIDR network") from exc


def _sanitize_validation_error(exc: ValidationError) -> str:
    locations = sorted(_format_location(error.get("loc", ())) for error in exc.errors())
    return "invalid config fields: " + ", ".join(locations)


def _format_location(location: Any) -> str:
    if isinstance(location, tuple):
        return ".".join(str(part) for part in location)
    return str(location)
