from __future__ import annotations

from typing import Any

import paramiko

from services.topology_discovery.config import SshConfig
from services.topology_discovery.models import AliveHost
from services.topology_discovery.ssh import collect_ssh_device_info, is_read_only_ssh_command


def test_collect_ssh_device_info_disabled_returns_failed_result() -> None:
    result = collect_ssh_device_info(_host(), _config(enabled=False), ssh_client_factory=FakeClient)

    assert result.success is False
    assert result.error == "ssh_disabled"


def test_collect_ssh_device_info_unreachable_host_returns_failed_result() -> None:
    result = collect_ssh_device_info(
        AliveHost(ip="192.0.2.1", reachable=False, discovered_by="icmp"),
        _config(),
        ssh_client_factory=FakeClient,
    )

    assert result.success is False
    assert result.error == "host_unreachable"


def test_collect_ssh_device_info_rejects_unsafe_command() -> None:
    config = _config(commands={"reload": "reload"})

    result = collect_ssh_device_info(_host(), config, ssh_client_factory=FakeClient)

    assert result.success is False
    assert result.error == "unsafe_ssh_command:reload"


def test_collect_ssh_device_info_success() -> None:
    client = FakeClient()

    result = collect_ssh_device_info(_host(), _config(), ssh_client_factory=lambda: client)

    assert result.success is True
    assert result.error is None
    assert result.commands[0].name == "show_version"
    assert result.commands[0].output == "Example OS"
    assert client.connect_kwargs["hostname"] == "192.0.2.1"
    assert client.connect_kwargs["timeout"] == 5
    assert client.closed is True


def test_collect_ssh_device_info_command_failure_is_structured() -> None:
    client = FakeClient(exit_status=1, stderr="invalid command")

    result = collect_ssh_device_info(_host(), _config(), ssh_client_factory=lambda: client)

    assert result.success is False
    assert result.error == "ssh_command_failed"
    assert result.commands[0].success is False
    assert result.commands[0].error == "invalid command"


def test_collect_ssh_device_info_timeout_is_sanitized() -> None:
    result = collect_ssh_device_info(_host(), _config(), ssh_client_factory=TimeoutClient)

    assert result.success is False
    assert result.error == "ssh_timeout"
    assert "dummy-password" not in str(result)


def test_collect_ssh_device_info_auth_failure_is_sanitized() -> None:
    result = collect_ssh_device_info(_host(), _config(), ssh_client_factory=AuthFailureClient)

    assert result.success is False
    assert result.error == "ssh_authentication_failed"
    assert "dummy-password" not in str(result)


def test_collect_ssh_device_info_request_failure_is_sanitized() -> None:
    result = collect_ssh_device_info(_host(), _config(), ssh_client_factory=RequestFailureClient)

    assert result.success is False
    assert result.error == "ssh_request_failed"
    assert "dummy-password" not in str(result)


def test_is_read_only_ssh_command_allows_show_commands() -> None:
    assert is_read_only_ssh_command("show version") is True
    assert is_read_only_ssh_command("show lldp neighbors detail") is True
    assert is_read_only_ssh_command("show interfaces") is True


def test_is_read_only_ssh_command_rejects_dangerous_commands() -> None:
    assert is_read_only_ssh_command("reload") is False
    assert is_read_only_ssh_command("configure terminal") is False
    assert is_read_only_ssh_command("shutdown") is False
    assert is_read_only_ssh_command("show version; reload") is False


def _host() -> AliveHost:
    return AliveHost(ip="192.0.2.1", reachable=True, discovered_by="icmp")


def _config(
    enabled: bool = True,
    commands: dict[str, str] | None = None,
) -> SshConfig:
    return SshConfig(
        enabled=enabled,
        username="example-user",
        password="dummy-password",
        timeout_seconds=5,
        port=22,
        commands=commands or {"show_version": "show version"},
    )


class FakeChannel:
    def __init__(self, exit_status: int) -> None:
        self._exit_status = exit_status

    def recv_exit_status(self) -> int:
        return self._exit_status


class FakeStream:
    def __init__(self, output: str, exit_status: int = 0) -> None:
        self._output = output
        self.channel = FakeChannel(exit_status)

    def read(self) -> bytes:
        return self._output.encode()


class FakeClient:
    def __init__(
        self,
        exit_status: int = 0,
        stdout: str = "Example OS",
        stderr: str = "",
    ) -> None:
        self.exit_status = exit_status
        self.stdout = stdout
        self.stderr = stderr
        self.connect_kwargs: dict[str, Any] = {}
        self.closed = False

    def set_missing_host_key_policy(self, policy: Any) -> None:
        return None

    def connect(self, **kwargs: Any) -> None:
        self.connect_kwargs = kwargs

    def exec_command(self, command: str, timeout: float) -> tuple[None, FakeStream, FakeStream]:
        return (
            None,
            FakeStream(self.stdout, self.exit_status),
            FakeStream(self.stderr, self.exit_status),
        )

    def close(self) -> None:
        self.closed = True


class TimeoutClient(FakeClient):
    def connect(self, **kwargs: Any) -> None:
        raise TimeoutError


class AuthFailureClient(FakeClient):
    def connect(self, **kwargs: Any) -> None:
        raise paramiko.AuthenticationException("authentication failed for dummy-password")


class RequestFailureClient(FakeClient):
    def connect(self, **kwargs: Any) -> None:
        raise paramiko.SSHException("ssh failed for dummy-password")
