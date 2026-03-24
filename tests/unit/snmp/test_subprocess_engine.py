"""Unit tests for SubprocessSnmpEngine."""
from __future__ import annotations

import asyncio
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Stub out pysnmp before importing app.snmp.engine
_pysnmp_stub = ModuleType("pysnmp")
_hlapi_stub = ModuleType("pysnmp.hlapi")
_asyncio_stub = ModuleType("pysnmp.hlapi.asyncio")

for _attr in (
    "CommunityData",
    "ContextData",
    "ObjectIdentity",
    "ObjectType",
    "UdpTransportTarget",
    "bulkCmd",
    "getCmd",
):
    setattr(_asyncio_stub, _attr, MagicMock())
_asyncio_stub.SnmpEngine = MagicMock()

for _mod_name, _mod in (
    ("pysnmp", _pysnmp_stub),
    ("pysnmp.hlapi", _hlapi_stub),
    ("pysnmp.hlapi.asyncio", _asyncio_stub),
):
    sys.modules.setdefault(_mod_name, _mod)

from app.snmp.engine import SnmpEngineConfig, SnmpTarget, SnmpTimeoutError  # noqa: E402
from app.snmp.subprocess_engine import (  # noqa: E402
    SubprocessSnmpEngine,
    _parse_snmp_line,
)


@pytest.fixture
def target():
    return SnmpTarget(
        ip="10.0.0.1",
        community="public",
        port=161,
        timeout=3.0,
        retries=1,
    )


@pytest.fixture
def engine():
    return SubprocessSnmpEngine(config=SnmpEngineConfig(
        max_repetitions=25,
        walk_timeout=60.0,
    ))


# ── _parse_snmp_line tests ──────────────────────────────────────


class TestParseSnmpLine:
    def test_integer(self):
        result = _parse_snmp_line(".1.3.6.1.2.1.2.2.1.8.1 = INTEGER: 1")
        assert result == ("1.3.6.1.2.1.2.2.1.8.1", "1")

    def test_string(self):
        result = _parse_snmp_line(
            '.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: "GigabitEthernet0/1"'
        )
        assert result == ("1.3.6.1.2.1.31.1.1.1.1.1", "GigabitEthernet0/1")

    def test_oid_value(self):
        result = _parse_snmp_line(
            ".1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.25506.11.2.2"
        )
        assert result == ("1.3.6.1.2.1.1.2.0", "1.3.6.1.4.1.25506.11.2.2")

    def test_gauge32(self):
        result = _parse_snmp_line(".1.3.6.1.2.1.2.2.1.5.1 = Gauge32: 1000000000")
        assert result == ("1.3.6.1.2.1.2.2.1.5.1", "1000000000")

    def test_counter32(self):
        result = _parse_snmp_line(".1.3.6.1.2.1.2.2.1.10.1 = Counter32: 12345678")
        assert result == ("1.3.6.1.2.1.2.2.1.10.1", "12345678")

    def test_hex_string(self):
        result = _parse_snmp_line(
            ".1.3.6.1.2.1.17.4.3.1.1.0 = Hex-STRING: AA BB CC DD EE FF"
        )
        assert result == ("1.3.6.1.2.1.17.4.3.1.1.0", "AA BB CC DD EE FF")

    def test_timeticks(self):
        result = _parse_snmp_line(
            ".1.3.6.1.2.1.1.3.0 = Timeticks: (123456) 0:20:34.56"
        )
        assert result == ("1.3.6.1.2.1.1.3.0", "(123456) 0:20:34.56")

    def test_no_such_object(self):
        result = _parse_snmp_line(
            ".1.3.6.1.2.1.999.0 = No Such Object available on this agent at this OID"
        )
        assert result is None

    def test_no_such_instance(self):
        result = _parse_snmp_line(
            ".1.3.6.1.2.1.999.0 = No Such Instance currently exists at this OID"
        )
        assert result is None

    def test_no_more_variables(self):
        result = _parse_snmp_line(
            ".1.3.6.1.2.1.999.0 = No more variables left in this MIB View"
        )
        assert result is None

    def test_empty_line(self):
        assert _parse_snmp_line("") is None
        assert _parse_snmp_line("   ") is None

    def test_malformed_line(self):
        assert _parse_snmp_line("no equals sign here") is None

    def test_string_without_quotes(self):
        result = _parse_snmp_line(
            ".1.3.6.1.2.1.31.1.1.1.1.1 = STRING: Ethernet1/1"
        )
        assert result == ("1.3.6.1.2.1.31.1.1.1.1.1", "Ethernet1/1")


# ── Helper to build mock process ────────────────────────────────


def _make_mock_proc(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Create a mock asyncio.Process."""
    proc = AsyncMock()
    proc.communicate = AsyncMock(
        return_value=(stdout.encode(), stderr.encode())
    )
    proc.returncode = returncode
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    return proc


# ── GET tests ────────────────────────────────────────────────────


class TestGet:
    @pytest.mark.asyncio
    async def test_get_success(self, engine, target):
        stdout = (
            ".1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.25506.11.2.2\n"
            ".1.3.6.1.2.1.1.5.0 = STRING: \"switch-01\"\n"
        )
        proc = _make_mock_proc(stdout=stdout, returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await engine.get(
                target,
                "1.3.6.1.2.1.1.2.0",
                "1.3.6.1.2.1.1.5.0",
            )

        assert result == {
            "1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.25506.11.2.2",
            "1.3.6.1.2.1.1.5.0": "switch-01",
        }

    @pytest.mark.asyncio
    async def test_get_empty_oids(self, engine, target):
        result = await engine.get(target)
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_timeout_exit_code_2(self, engine, target):
        proc = _make_mock_proc(
            stderr="Timeout: No Response from 10.0.0.1",
            returncode=2,
        )

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(SnmpTimeoutError, match="timeout"):
                await engine.get(target, "1.3.6.1.2.1.1.2.0")

    @pytest.mark.asyncio
    async def test_get_timeout_process_hang(self, engine, target):
        """Process hangs beyond deadline → kill → SnmpTimeoutError."""
        proc = AsyncMock()
        proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        proc.kill = MagicMock()
        proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                with pytest.raises(SnmpTimeoutError, match="deadline"):
                    await engine.get(target, "1.3.6.1.2.1.1.2.0")

    @pytest.mark.asyncio
    async def test_get_no_such_object_skipped(self, engine, target):
        stdout = (
            ".1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.25506.11.2.2\n"
            ".1.3.6.1.2.1.999.0 = No Such Object available on this agent at this OID\n"
        )
        proc = _make_mock_proc(stdout=stdout, returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await engine.get(
                target,
                "1.3.6.1.2.1.1.2.0",
                "1.3.6.1.2.1.999.0",
            )

        assert len(result) == 1
        assert "1.3.6.1.2.1.1.2.0" in result

    @pytest.mark.asyncio
    async def test_get_command_not_found(self, engine, target):
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("snmpget"),
        ):
            with pytest.raises(Exception, match="not found"):
                await engine.get(target, "1.3.6.1.2.1.1.2.0")

    @pytest.mark.asyncio
    async def test_get_community_with_vlan(self, engine):
        """Cisco per-VLAN community string: community@vlan."""
        target = SnmpTarget(
            ip="10.0.0.1",
            community="public@100",
            port=161,
            timeout=3.0,
            retries=1,
        )
        stdout = ".1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.9.1.1\n"
        proc = _make_mock_proc(stdout=stdout, returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await engine.get(target, "1.3.6.1.2.1.1.2.0")

        # Verify community@vlan is passed correctly
        call_args = mock_exec.call_args[0]
        assert "public@100" in call_args


# ── WALK tests ───────────────────────────────────────────────────


class TestWalk:
    @pytest.mark.asyncio
    async def test_walk_success(self, engine, target):
        stdout = (
            ".1.3.6.1.2.1.31.1.1.1.1.1 = STRING: GigabitEthernet0/1\n"
            ".1.3.6.1.2.1.31.1.1.1.1.2 = STRING: GigabitEthernet0/2\n"
            ".1.3.6.1.2.1.31.1.1.1.1.3 = STRING: GigabitEthernet0/3\n"
        )
        proc = _make_mock_proc(stdout=stdout, returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            results = await engine.walk(target, "1.3.6.1.2.1.31.1.1.1.1")

        assert len(results) == 3
        assert results[0] == ("1.3.6.1.2.1.31.1.1.1.1.1", "GigabitEthernet0/1")
        assert results[2] == ("1.3.6.1.2.1.31.1.1.1.1.3", "GigabitEthernet0/3")

    @pytest.mark.asyncio
    async def test_walk_timeout_exit_code_2(self, engine, target):
        proc = _make_mock_proc(
            stderr="Timeout: No Response from 10.0.0.1",
            returncode=2,
        )

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(SnmpTimeoutError, match="timeout"):
                await engine.walk(target, "1.3.6.1.2.1.31.1.1.1.1")

    @pytest.mark.asyncio
    async def test_walk_out_of_scope_oid_stops(self, engine, target):
        """Walk stops when OIDs go outside the requested prefix."""
        stdout = (
            ".1.3.6.1.2.1.31.1.1.1.1.1 = STRING: Eth0/1\n"
            ".1.3.6.1.2.1.31.1.1.1.1.2 = STRING: Eth0/2\n"
            ".1.3.6.1.2.1.31.1.1.1.2.1 = STRING: Eth0/1\n"  # out of scope
        )
        proc = _make_mock_proc(stdout=stdout, returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            results = await engine.walk(target, "1.3.6.1.2.1.31.1.1.1.1")

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_walk_exit_code_1_with_output(self, engine, target):
        """Exit code 1 with output = end of MIB, treated as success."""
        stdout = ".1.3.6.1.2.1.31.1.1.1.1.1 = STRING: Eth0/1\n"
        proc = _make_mock_proc(stdout=stdout, returncode=1)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            results = await engine.walk(target, "1.3.6.1.2.1.31.1.1.1.1")

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_walk_max_repetitions_in_command(self, engine, target):
        """Verify -Cr<max_rep> is passed to snmpbulkwalk."""
        proc = _make_mock_proc(stdout="", returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await engine.walk(target, "1.3.6.1.2.1.31.1.1.1.1")

        call_args = mock_exec.call_args[0]
        assert "-Cr25" in call_args

    @pytest.mark.asyncio
    async def test_walk_empty_result(self, engine, target):
        proc = _make_mock_proc(stdout="", returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            results = await engine.walk(target, "1.3.6.1.2.1.31.1.1.1.1")

        assert results == []


# ── Process timeout (kill) tests ─────────────────────────────────


class TestProcessKill:
    @pytest.mark.asyncio
    async def test_get_kills_hung_process(self, engine, target):
        """Hung process is killed and cleaned up."""
        proc = AsyncMock()
        proc.kill = MagicMock()
        proc.wait = AsyncMock()

        async def _hang():
            await asyncio.sleep(999)

        proc.communicate = _hang

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(SnmpTimeoutError):
                await engine.get(target, "1.3.6.1.2.1.1.2.0")

        # Verify kill was called
        proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_walk_kills_hung_process(self, engine, target):
        """Hung walk process is killed and cleaned up."""
        proc = AsyncMock()
        proc.kill = MagicMock()
        proc.wait = AsyncMock()

        async def _hang():
            await asyncio.sleep(999)

        proc.communicate = _hang

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with pytest.raises(SnmpTimeoutError):
                await engine.walk(target, "1.3.6.1.2.1.31.1.1.1.1")

        proc.kill.assert_called_once()
