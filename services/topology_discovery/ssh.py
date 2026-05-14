"""SSH supplemental collection helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast

import paramiko

from services.topology_discovery.config import SshConfig
from services.topology_discovery.models import AliveHost, SshCommandResult, SshDeviceInfo

READ_ONLY_PREFIXES = ("show ",)
DANGEROUS_COMMAND_PREFIXES = (
    "configure",
    "configure terminal",
    "reload",
    "write erase",
    "delete",
    "copy running-config startup-config",
    "shutdown",
    "no shutdown",
    "interface",
    "vlan",
    "ip route",
)
COMMAND_SEPARATORS = (";", "&&", "||", "|", ">", "<", "`", "$(", "\n", "\r")


class SshClient(Protocol):
    """Minimal SSH client protocol used by the collector."""

    def set_missing_host_key_policy(self, policy: Any) -> None:
        """Set the host key policy."""

    def connect(self, **kwargs: Any) -> None:
        """Connect to an SSH server."""

    def exec_command(self, command: str, timeout: float) -> tuple[Any, Any, Any]:
        """Execute a command and return stdin, stdout, stderr streams."""

    def close(self) -> None:
        """Close the SSH connection."""


SshClientFactory = Callable[[], SshClient]


def collect_ssh_device_info(
    host: AliveHost,
    config: SshConfig,
    ssh_client_factory: SshClientFactory | None = None,
) -> SshDeviceInfo:
    """Collect supplemental device information over SSH."""

    if not config.enabled:
        return _failed_result(host.ip, "ssh_disabled")
    if not host.reachable:
        return _failed_result(host.ip, "host_unreachable")

    unsafe_command = _first_unsafe_command(config.commands)
    if unsafe_command is not None:
        return _failed_result(host.ip, f"unsafe_ssh_command:{unsafe_command}")

    client = _create_ssh_client() if ssh_client_factory is None else ssh_client_factory()
    try:
        _connect(client, host, config)
        command_results = [
            _execute_command(client, name, command, config.timeout_seconds)
            for name, command in config.commands.items()
        ]
    except TimeoutError:
        return _failed_result(host.ip, "ssh_timeout")
    except paramiko.AuthenticationException:
        return _failed_result(host.ip, "ssh_authentication_failed")
    except paramiko.SSHException:
        return _failed_result(host.ip, "ssh_request_failed")
    except OSError as exc:
        return _failed_result(host.ip, exc.__class__.__name__)
    finally:
        client.close()

    success = all(result.success for result in command_results)
    return SshDeviceInfo(
        ip=host.ip,
        success=success,
        commands=command_results,
        error=None if success else "ssh_command_failed",
    )


def is_read_only_ssh_command(command: str) -> bool:
    """Return whether a configured SSH command is allowed for read-only collection."""

    normalized = _normalize_command(command)
    if not normalized:
        return False
    if any(separator in command for separator in COMMAND_SEPARATORS):
        return False
    if not normalized.startswith(READ_ONLY_PREFIXES):
        return False
    return not any(
        normalized == prefix or normalized.startswith(f"{prefix} ")
        for prefix in DANGEROUS_COMMAND_PREFIXES
    )


def _first_unsafe_command(commands: dict[str, str]) -> str | None:
    for name, command in commands.items():
        if not is_read_only_ssh_command(command):
            return name
    return None


def _connect(client: SshClient, host: AliveHost, config: SshConfig) -> None:
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host.ip,
        port=config.port,
        username=config.username,
        password=config.password,
        timeout=config.timeout_seconds,
        banner_timeout=config.timeout_seconds,
        auth_timeout=config.timeout_seconds,
        look_for_keys=False,
        allow_agent=False,
    )


def _execute_command(
    client: SshClient,
    name: str,
    command: str,
    timeout_seconds: float,
) -> SshCommandResult:
    _stdin, stdout, stderr = client.exec_command(command, timeout=timeout_seconds)
    exit_status = _exit_status(stdout)
    output = _read_stream(stdout)
    error_output = _read_stream(stderr)
    return SshCommandResult(
        name=name,
        command=command,
        success=exit_status == 0,
        output=output,
        error=None if exit_status == 0 else error_output or "ssh_command_failed",
    )


def _exit_status(stdout: Any) -> int:
    channel = getattr(stdout, "channel", None)
    if channel is None:
        return 0
    return cast(int, channel.recv_exit_status())


def _read_stream(stream: Any) -> str:
    raw_output = stream.read()
    if isinstance(raw_output, bytes):
        return raw_output.decode(errors="replace").strip()
    return str(raw_output).strip()


def _failed_result(ip: str, error: str) -> SshDeviceInfo:
    return SshDeviceInfo(ip=ip, success=False, error=error)


def _create_ssh_client() -> SshClient:
    return cast(SshClient, paramiko.SSHClient())


def _normalize_command(command: str) -> str:
    return " ".join(command.casefold().strip().split())
