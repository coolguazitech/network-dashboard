"""
Comprehensive unit tests for UplinkIndicator, VersionIndicator, and PortChannelIndicator.

Tests cover:
- evaluate() with healthy data (all pass), failure data, missing data, edge cases
- get_metadata() returns correct structure
- Helper methods and normalisation logic (PortChannelIndicator)
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.indicators.uplink import UplinkIndicator
from app.indicators.version import VersionIndicator
from app.indicators.port_channel import PortChannelIndicator


# =====================================================================
# Shared constants
# =====================================================================

MAINTENANCE_ID = "MAINT-TEST-001"


# =====================================================================
# Mock record factories
# =====================================================================

def _make_neighbor_record(
    switch_hostname: str = "SW-01",
    local_interface: str = "GigabitEthernet1/0/49",
    remote_hostname: str = "CORE-SW-01",
    remote_interface: str = "GigabitEthernet1/0/1",
    collected_at: datetime | None = None,
) -> MagicMock:
    """Create a mock NeighborRecord."""
    record = MagicMock()
    record.switch_hostname = switch_hostname
    record.local_interface = local_interface
    record.remote_hostname = remote_hostname
    record.remote_interface = remote_interface
    record.collected_at = collected_at or datetime(2026, 1, 15, 12, 0, 0)
    return record


def _make_version_record(
    switch_hostname: str = "SW-01",
    version: str = "17.6.3",
    collected_at: datetime | None = None,
) -> MagicMock:
    """Create a mock VersionRecord."""
    record = MagicMock()
    record.switch_hostname = switch_hostname
    record.version = version
    record.collected_at = collected_at or datetime(2026, 1, 15, 12, 0, 0)
    return record


def _make_pc_record(
    switch_hostname: str = "SW-01",
    interface_name: str = "Port-channel1",
    status: str = "up",
    members: list[str] | None = None,
    member_status: dict[str, str] | None = None,
    collected_at: datetime | None = None,
) -> MagicMock:
    """Create a mock PortChannelRecord."""
    record = MagicMock()
    record.switch_hostname = switch_hostname
    record.interface_name = interface_name
    record.status = status
    record.members = members or ["GigabitEthernet1/0/1", "GigabitEthernet1/0/2"]
    record.member_status = member_status or {
        "GigabitEthernet1/0/1": "up",
        "GigabitEthernet1/0/2": "up",
    }
    record.collected_at = collected_at or datetime(2026, 1, 15, 12, 0, 0)
    return record


def _make_pc_expectation(
    hostname: str = "SW-01",
    port_channel: str = "Port-channel1",
    member_interfaces: str = "GigabitEthernet1/0/1;GigabitEthernet1/0/2",
) -> MagicMock:
    """Create a mock PortChannelExpectation."""
    exp = MagicMock()
    exp.hostname = hostname
    exp.port_channel = port_channel
    exp.member_interfaces = member_interfaces
    return exp


def _make_uplink_expectation(
    hostname: str = "SW-01",
    expected_neighbor: str = "CORE-SW-01",
) -> MagicMock:
    """Create a mock UplinkExpectation."""
    exp = MagicMock()
    exp.hostname = hostname
    exp.expected_neighbor = expected_neighbor
    return exp


def _make_version_expectation(
    hostname: str = "SW-01",
    expected_versions: str = "17.6.3",
) -> MagicMock:
    """Create a mock VersionExpectation."""
    exp = MagicMock()
    exp.hostname = hostname
    exp.expected_versions = expected_versions
    return exp


# =====================================================================
#  UPLINK INDICATOR TESTS
# =====================================================================


class TestUplinkIndicatorMetadata:
    """UplinkIndicator.get_metadata() verification."""

    def test_metadata_fields(self):
        indicator = UplinkIndicator()
        meta = indicator.get_metadata()

        assert meta.name == "uplink"
        assert meta.title == "Uplink 連接監控"
        assert meta.object_type == "switch"
        assert meta.data_type == "boolean"
        assert len(meta.observed_fields) == 1
        assert meta.observed_fields[0].name == "neighbor_connected"
        assert meta.display_config.chart_type == "table"
        assert meta.display_config.refresh_interval_seconds == 600

    def test_metadata_description(self):
        indicator = UplinkIndicator()
        meta = indicator.get_metadata()
        assert "Uplink" in meta.description


@pytest.mark.asyncio
class TestUplinkEvaluateAllPass:
    """All expected neighbors found -> all pass."""

    async def test_all_neighbors_found(self):
        indicator = UplinkIndicator()
        session = AsyncMock()

        neighbor_records = [
            _make_neighbor_record("SW-01", remote_hostname="CORE-SW-01"),
            _make_neighbor_record("SW-01", remote_hostname="CORE-SW-02"),
            _make_neighbor_record("SW-02", remote_hostname="CORE-SW-01"),
        ]

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value={
                    "SW-01": ["CORE-SW-01", "CORE-SW-02"],
                    "SW-02": ["CORE-SW-01"],
                },
            ),
            patch.object(
                indicator, "_get_latest_all_protocols",
                new_callable=AsyncMock,
                return_value=neighbor_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.indicator_type == "uplink"
        assert result.maintenance_id == MAINTENANCE_ID
        assert result.total_count == 3
        assert result.pass_count == 3
        assert result.fail_count == 0
        assert result.failures is None
        assert result.passes is not None
        assert len(result.passes) == 3
        assert result.pass_rates["uplink_topology"] == 100.0
        assert "3/3" in result.summary


@pytest.mark.asyncio
class TestUplinkEvaluateSomeFail:
    """Some expected neighbors missing -> partial failure."""

    async def test_missing_neighbor(self):
        indicator = UplinkIndicator()
        session = AsyncMock()

        neighbor_records = [
            _make_neighbor_record("SW-01", remote_hostname="CORE-SW-01"),
            # SW-01 expected CORE-SW-02 but it's not present
        ]

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value={
                    "SW-01": ["CORE-SW-01", "CORE-SW-02"],
                },
            ),
            patch.object(
                indicator, "_get_latest_all_protocols",
                new_callable=AsyncMock,
                return_value=neighbor_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 2
        assert result.pass_count == 1
        assert result.fail_count == 1
        assert result.failures is not None
        assert len(result.failures) == 1
        assert result.failures[0]["device"] == "SW-01"
        assert result.failures[0]["expected_neighbor"] == "CORE-SW-02"
        assert "未找到" in result.failures[0]["reason"]
        assert result.pass_rates["uplink_topology"] == pytest.approx(50.0)


@pytest.mark.asyncio
class TestUplinkEvaluateNoCollectedData:
    """Device has expectations but no neighbor records collected."""

    async def test_no_collected_data_for_device(self):
        indicator = UplinkIndicator()
        session = AsyncMock()

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value={
                    "SW-01": ["CORE-SW-01", "CORE-SW-02"],
                },
            ),
            patch.object(
                indicator, "_get_latest_all_protocols",
                new_callable=AsyncMock,
                return_value=[],  # no records at all
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 2
        assert result.pass_count == 0
        assert result.fail_count == 2
        assert result.failures is not None
        assert len(result.failures) == 2
        for failure in result.failures:
            assert failure["device"] == "SW-01"
            assert failure["reason"] == "無採集數據"


@pytest.mark.asyncio
class TestUplinkEvaluateNoExpectations:
    """No uplink expectations at all -> zero total."""

    async def test_no_expectations(self):
        indicator = UplinkIndicator()
        session = AsyncMock()

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch.object(
                indicator, "_get_latest_all_protocols",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 0
        assert result.pass_count == 0
        assert result.fail_count == 0
        assert result.pass_rates == {"uplink_topology": 0}
        assert result.summary == "無 Uplink 數據"


@pytest.mark.asyncio
class TestUplinkEvaluateEmptyExpectedNeighborList:
    """Device in expectations but its neighbor list is empty -> skip."""

    async def test_empty_neighbor_list_skipped(self):
        indicator = UplinkIndicator()
        session = AsyncMock()

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value={
                    "SW-01": [],  # empty list, should be skipped
                },
            ),
            patch.object(
                indicator, "_get_latest_all_protocols",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 0
        assert result.pass_count == 0
        assert result.fail_count == 0


@pytest.mark.asyncio
class TestUplinkEvaluateMultipleDevices:
    """Multiple devices with mixed pass/fail results."""

    async def test_mixed_results(self):
        indicator = UplinkIndicator()
        session = AsyncMock()

        neighbor_records = [
            _make_neighbor_record("SW-01", remote_hostname="CORE-SW-01"),
            _make_neighbor_record("SW-01", remote_hostname="CORE-SW-02"),
            # SW-02 has CORE-SW-01 but not CORE-SW-03
            _make_neighbor_record("SW-02", remote_hostname="CORE-SW-01"),
        ]

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value={
                    "SW-01": ["CORE-SW-01", "CORE-SW-02"],
                    "SW-02": ["CORE-SW-01", "CORE-SW-03"],
                },
            ),
            patch.object(
                indicator, "_get_latest_all_protocols",
                new_callable=AsyncMock,
                return_value=neighbor_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 4
        assert result.pass_count == 3
        assert result.fail_count == 1
        assert result.pass_rates["uplink_topology"] == pytest.approx(75.0)


@pytest.mark.asyncio
class TestUplinkPassesCappedAtTen:
    """passes list should not exceed 10 items."""

    async def test_passes_capped(self):
        indicator = UplinkIndicator()
        session = AsyncMock()

        # 15 expectations, all passing
        expectations = {
            f"SW-{i:02d}": [f"CORE-{i:02d}"]
            for i in range(1, 16)
        }
        neighbor_records = [
            _make_neighbor_record(f"SW-{i:02d}", remote_hostname=f"CORE-{i:02d}")
            for i in range(1, 16)
        ]

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value=expectations,
            ),
            patch.object(
                indicator, "_get_latest_all_protocols",
                new_callable=AsyncMock,
                return_value=neighbor_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.pass_count == 15
        assert result.passes is not None
        assert len(result.passes) <= 10


# =====================================================================
#  VERSION INDICATOR TESTS
# =====================================================================


class TestVersionIndicatorMetadata:
    """VersionIndicator.get_metadata() verification."""

    def test_metadata_fields(self):
        indicator = VersionIndicator()
        meta = indicator.get_metadata()

        assert meta.name == "version"
        assert meta.title == "韌體版本監控"
        assert meta.object_type == "switch"
        assert meta.data_type == "string"
        assert len(meta.observed_fields) == 1
        assert meta.observed_fields[0].name == "version"
        assert meta.display_config.chart_type == "gauge"
        assert meta.display_config.refresh_interval_seconds == 3600

    def test_metadata_description(self):
        indicator = VersionIndicator()
        meta = indicator.get_metadata()
        assert "版本" in meta.description


@pytest.mark.asyncio
class TestVersionEvaluateAllPass:
    """All devices running the expected version -> all pass."""

    async def test_all_versions_match(self):
        indicator = VersionIndicator()
        session = AsyncMock()

        version_records = [
            _make_version_record("SW-01", version="17.6.3"),
            _make_version_record("SW-02", version="17.6.3"),
        ]

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value={
                    "SW-01": ["17.6.3"],
                    "SW-02": ["17.6.3"],
                },
            ),
            patch(
                "app.indicators.version.VersionRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=version_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.indicator_type == "version"
        assert result.maintenance_id == MAINTENANCE_ID
        assert result.total_count == 2
        assert result.pass_count == 2
        assert result.fail_count == 0
        assert result.failures is None
        assert result.passes is not None
        assert len(result.passes) == 2
        assert result.pass_rates["version_match"] == 100.0
        assert "2/2" in result.summary


@pytest.mark.asyncio
class TestVersionEvaluateVersionMismatch:
    """Device running wrong version -> failure."""

    async def test_wrong_version(self):
        indicator = VersionIndicator()
        session = AsyncMock()

        version_records = [
            _make_version_record("SW-01", version="17.3.1"),
        ]

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value={
                    "SW-01": ["17.6.3"],
                },
            ),
            patch(
                "app.indicators.version.VersionRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=version_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert len(result.failures) == 1
        assert result.failures[0]["device"] == "SW-01"
        assert result.failures[0]["reason"] == "版本不符"
        assert result.failures[0]["expected"] == "17.6.3"
        assert result.failures[0]["actual"] == "17.3.1"


@pytest.mark.asyncio
class TestVersionEvaluateMultipleExpectedVersions:
    """Multiple acceptable versions (semicolon-separated) -> pass if any match."""

    async def test_one_of_multiple_versions_matches(self):
        indicator = VersionIndicator()
        session = AsyncMock()

        version_records = [
            _make_version_record("SW-01", version="17.6.4"),
        ]

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value={
                    "SW-01": ["17.6.3", "17.6.4"],  # either is acceptable
                },
            ),
            patch(
                "app.indicators.version.VersionRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=version_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 1
        assert result.pass_count == 1
        assert result.fail_count == 0


@pytest.mark.asyncio
class TestVersionEvaluateNoCollectedData:
    """Expected device but no version record collected -> failure."""

    async def test_no_collected_version(self):
        indicator = VersionIndicator()
        session = AsyncMock()

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value={
                    "SW-01": ["17.6.3"],
                },
            ),
            patch(
                "app.indicators.version.VersionRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=[],  # no records
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert result.failures[0]["device"] == "SW-01"
        assert result.failures[0]["reason"] == "尚未採集"
        assert result.failures[0]["actual"] is None


@pytest.mark.asyncio
class TestVersionEvaluateNoExpectations:
    """No version expectations configured -> early return with zero counts."""

    async def test_no_expectations(self):
        indicator = VersionIndicator()
        session = AsyncMock()

        with patch.object(
            indicator, "_load_expectations",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 0
        assert result.pass_count == 0
        assert result.fail_count == 0
        assert result.pass_rates == {"version_match": 0}
        assert result.summary == "無版本期望設定"
        assert result.failures is None


@pytest.mark.asyncio
class TestVersionEvaluateNullActualVersion:
    """Actual version is None (or empty) -> failure."""

    async def test_null_version(self):
        indicator = VersionIndicator()
        session = AsyncMock()

        null_version_record = _make_version_record("SW-01", version=None)

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value={
                    "SW-01": ["17.6.3"],
                },
            ),
            patch(
                "app.indicators.version.VersionRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=[null_version_record],
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert result.failures[0]["reason"] == "版本不符"
        assert result.failures[0]["actual"] is None


@pytest.mark.asyncio
class TestVersionEvaluateMixedResults:
    """Multiple devices with mixed pass/fail results."""

    async def test_mixed_results(self):
        indicator = VersionIndicator()
        session = AsyncMock()

        version_records = [
            _make_version_record("SW-01", version="17.6.3"),
            _make_version_record("SW-02", version="17.3.1"),
            _make_version_record("SW-03", version="17.6.3"),
        ]

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value={
                    "SW-01": ["17.6.3"],
                    "SW-02": ["17.6.3"],
                    "SW-03": ["17.6.3"],
                },
            ),
            patch(
                "app.indicators.version.VersionRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=version_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 3
        assert result.pass_count == 2
        assert result.fail_count == 1
        assert result.pass_rates["version_match"] == pytest.approx(66.6667, abs=0.01)


@pytest.mark.asyncio
class TestVersionEvaluatePassesCappedAtTen:
    """passes list should not exceed 10 items."""

    async def test_passes_capped(self):
        indicator = VersionIndicator()
        session = AsyncMock()

        expectations = {
            f"SW-{i:02d}": ["17.6.3"]
            for i in range(1, 16)
        }
        version_records = [
            _make_version_record(f"SW-{i:02d}", version="17.6.3")
            for i in range(1, 16)
        ]

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value=expectations,
            ),
            patch(
                "app.indicators.version.VersionRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=version_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.pass_count == 15
        assert result.passes is not None
        assert len(result.passes) <= 10


@pytest.mark.asyncio
class TestVersionEvaluateSummaryFormat:
    """Verify the summary string format."""

    async def test_summary_format(self):
        indicator = VersionIndicator()
        session = AsyncMock()

        version_records = [
            _make_version_record("SW-01", version="17.6.3"),
            _make_version_record("SW-02", version="17.3.1"),
        ]

        with (
            patch.object(
                indicator, "_load_expectations",
                new_callable=AsyncMock,
                return_value={
                    "SW-01": ["17.6.3"],
                    "SW-02": ["17.6.3"],
                },
            ),
            patch(
                "app.indicators.version.VersionRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=version_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.summary == "版本驗收: 1/2 通過 (50.0%)"


# =====================================================================
#  PORT-CHANNEL INDICATOR TESTS
# =====================================================================


class TestPortChannelIndicatorMetadata:
    """PortChannelIndicator.get_metadata() verification."""

    def test_metadata_fields(self):
        indicator = PortChannelIndicator()
        meta = indicator.get_metadata()

        assert meta.name == "port_channel"
        assert meta.title == "Port-Channel 監控"
        assert meta.object_type == "switch"
        assert meta.data_type == "string"
        assert len(meta.observed_fields) == 1
        assert meta.observed_fields[0].name == "pc_status"
        assert meta.display_config.chart_type == "table"
        assert meta.display_config.refresh_interval_seconds == 600

    def test_metadata_description(self):
        indicator = PortChannelIndicator()
        meta = indicator.get_metadata()
        assert "Port-Channel" in meta.description


@pytest.mark.asyncio
class TestPortChannelEvaluateAllPass:
    """All port-channels UP, correct members, all members UP -> all pass."""

    async def test_all_port_channels_healthy(self):
        indicator = PortChannelIndicator()
        session = AsyncMock()

        pc_records = [
            _make_pc_record(
                "SW-01", "Port-channel1",
                status="up",
                members=["GigabitEthernet1/0/1", "GigabitEthernet1/0/2"],
                member_status={
                    "GigabitEthernet1/0/1": "up",
                    "GigabitEthernet1/0/2": "up",
                },
            ),
        ]
        exp_map = {
            "SW-01": {
                "Port-channel1": _make_pc_expectation(
                    "SW-01", "Port-channel1",
                    "GigabitEthernet1/0/1;GigabitEthernet1/0/2",
                ),
            },
        }

        with (
            patch.object(
                indicator, "_build_expectation_map",
                new_callable=AsyncMock,
                return_value=exp_map,
            ),
            patch(
                "app.indicators.port_channel.PortChannelRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=pc_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.indicator_type == "port_channel"
        assert result.maintenance_id == MAINTENANCE_ID
        assert result.total_count == 1
        assert result.pass_count == 1
        assert result.fail_count == 0
        assert result.failures is None
        assert result.passes is not None
        assert len(result.passes) == 1
        assert result.pass_rates["status_ok"] == 100.0


@pytest.mark.asyncio
class TestPortChannelEvaluateStatusDown:
    """Port-Channel status is DOWN -> failure."""

    async def test_port_channel_down(self):
        indicator = PortChannelIndicator()
        session = AsyncMock()

        pc_records = [
            _make_pc_record(
                "SW-01", "Port-channel1",
                status="down",
                members=["GigabitEthernet1/0/1", "GigabitEthernet1/0/2"],
            ),
        ]
        exp_map = {
            "SW-01": {
                "Port-channel1": _make_pc_expectation(
                    "SW-01", "Port-channel1",
                    "GigabitEthernet1/0/1;GigabitEthernet1/0/2",
                ),
            },
        }

        with (
            patch.object(
                indicator, "_build_expectation_map",
                new_callable=AsyncMock,
                return_value=exp_map,
            ),
            patch(
                "app.indicators.port_channel.PortChannelRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=pc_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert "狀態異常" in result.failures[0]["reason"]
        assert result.failures[0]["data"]["status"] == "down"


@pytest.mark.asyncio
class TestPortChannelEvaluateMissingMembers:
    """Expected member interfaces not all present -> failure."""

    async def test_missing_member(self):
        indicator = PortChannelIndicator()
        session = AsyncMock()

        pc_records = [
            _make_pc_record(
                "SW-01", "Port-channel1",
                status="up",
                members=["GigabitEthernet1/0/1"],  # missing Gi1/0/2
                member_status={"GigabitEthernet1/0/1": "up"},
            ),
        ]
        exp_map = {
            "SW-01": {
                "Port-channel1": _make_pc_expectation(
                    "SW-01", "Port-channel1",
                    "GigabitEthernet1/0/1;GigabitEthernet1/0/2",
                ),
            },
        }

        with (
            patch.object(
                indicator, "_build_expectation_map",
                new_callable=AsyncMock,
                return_value=exp_map,
            ),
            patch(
                "app.indicators.port_channel.PortChannelRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=pc_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert "成員缺失" in result.failures[0]["reason"]
        assert "GigabitEthernet1/0/2" in result.failures[0]["reason"]


@pytest.mark.asyncio
class TestPortChannelEvaluateUnhealthyMember:
    """All members present but one member status is down -> failure."""

    async def test_member_down(self):
        indicator = PortChannelIndicator()
        session = AsyncMock()

        pc_records = [
            _make_pc_record(
                "SW-01", "Port-channel1",
                status="up",
                members=["GigabitEthernet1/0/1", "GigabitEthernet1/0/2"],
                member_status={
                    "GigabitEthernet1/0/1": "up",
                    "GigabitEthernet1/0/2": "down",
                },
            ),
        ]
        exp_map = {
            "SW-01": {
                "Port-channel1": _make_pc_expectation(
                    "SW-01", "Port-channel1",
                    "GigabitEthernet1/0/1;GigabitEthernet1/0/2",
                ),
            },
        }

        with (
            patch.object(
                indicator, "_build_expectation_map",
                new_callable=AsyncMock,
                return_value=exp_map,
            ),
            patch(
                "app.indicators.port_channel.PortChannelRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=pc_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert "成員狀態異常" in result.failures[0]["reason"]
        assert "GigabitEthernet1/0/2" in result.failures[0]["reason"]


@pytest.mark.asyncio
class TestPortChannelEvaluateNoCollectedData:
    """No records collected for device -> all expected PCs fail."""

    async def test_no_collected_data(self):
        indicator = PortChannelIndicator()
        session = AsyncMock()

        exp_map = {
            "SW-01": {
                "Port-channel1": _make_pc_expectation(
                    "SW-01", "Port-channel1",
                    "GigabitEthernet1/0/1;GigabitEthernet1/0/2",
                ),
                "Port-channel2": _make_pc_expectation(
                    "SW-01", "Port-channel2",
                    "GigabitEthernet1/0/3;GigabitEthernet1/0/4",
                ),
            },
        }

        with (
            patch.object(
                indicator, "_build_expectation_map",
                new_callable=AsyncMock,
                return_value=exp_map,
            ),
            patch(
                "app.indicators.port_channel.PortChannelRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=[],  # no records
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 2
        assert result.pass_count == 0
        assert result.fail_count == 2
        assert result.failures is not None
        assert len(result.failures) == 2
        for failure in result.failures:
            assert failure["reason"] == "無採集數據"
            assert failure["data"] is None


@pytest.mark.asyncio
class TestPortChannelEvaluateNoExpectations:
    """No expectations -> zero counts."""

    async def test_no_expectations(self):
        indicator = PortChannelIndicator()
        session = AsyncMock()

        with (
            patch.object(
                indicator, "_build_expectation_map",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "app.indicators.port_channel.PortChannelRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 0
        assert result.pass_count == 0
        assert result.fail_count == 0
        assert result.pass_rates["status_ok"] == 0.0
        assert result.summary == "Port-Channel: 0/0 通過"


@pytest.mark.asyncio
class TestPortChannelEvaluatePortChannelNotExist:
    """Expected port-channel not found in actual records -> failure."""

    async def test_pc_not_exist(self):
        indicator = PortChannelIndicator()
        session = AsyncMock()

        # Actual has Port-channel2 but expectation is for Port-channel1
        pc_records = [
            _make_pc_record(
                "SW-01", "Port-channel2",
                status="up",
            ),
        ]
        exp_map = {
            "SW-01": {
                "Port-channel1": _make_pc_expectation(
                    "SW-01", "Port-channel1",
                    "GigabitEthernet1/0/1;GigabitEthernet1/0/2",
                ),
            },
        }

        with (
            patch.object(
                indicator, "_build_expectation_map",
                new_callable=AsyncMock,
                return_value=exp_map,
            ),
            patch(
                "app.indicators.port_channel.PortChannelRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=pc_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert result.failures[0]["reason"] == "Port-Channel 不存在"


@pytest.mark.asyncio
class TestPortChannelEvaluateMultipleDevicesMixed:
    """Multiple devices, mixed pass/fail results."""

    async def test_mixed_results(self):
        indicator = PortChannelIndicator()
        session = AsyncMock()

        pc_records = [
            # SW-01 PC1 healthy
            _make_pc_record(
                "SW-01", "Port-channel1",
                status="up",
                members=["Gi1/0/1", "Gi1/0/2"],
                member_status={"Gi1/0/1": "up", "Gi1/0/2": "up"},
            ),
            # SW-02 PC1 status down
            _make_pc_record(
                "SW-02", "Port-channel1",
                status="down",
                members=["Gi1/0/1"],
                member_status={"Gi1/0/1": "down"},
            ),
        ]
        exp_map = {
            "SW-01": {
                "Port-channel1": _make_pc_expectation(
                    "SW-01", "Port-channel1", "Gi1/0/1;Gi1/0/2",
                ),
            },
            "SW-02": {
                "Port-channel1": _make_pc_expectation(
                    "SW-02", "Port-channel1", "Gi1/0/1",
                ),
            },
        }

        with (
            patch.object(
                indicator, "_build_expectation_map",
                new_callable=AsyncMock,
                return_value=exp_map,
            ),
            patch(
                "app.indicators.port_channel.PortChannelRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=pc_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 2
        assert result.pass_count == 1
        assert result.fail_count == 1
        assert result.pass_rates["status_ok"] == pytest.approx(50.0)


@pytest.mark.asyncio
class TestPortChannelEvaluateNullStatus:
    """Port-channel with None/null status -> failure."""

    async def test_null_status(self):
        indicator = PortChannelIndicator()
        session = AsyncMock()

        pc_records = [
            _make_pc_record(
                "SW-01", "Port-channel1",
                status=None,
                members=["GigabitEthernet1/0/1"],
                member_status={"GigabitEthernet1/0/1": "up"},
            ),
        ]
        exp_map = {
            "SW-01": {
                "Port-channel1": _make_pc_expectation(
                    "SW-01", "Port-channel1",
                    "GigabitEthernet1/0/1",
                ),
            },
        }

        with (
            patch.object(
                indicator, "_build_expectation_map",
                new_callable=AsyncMock,
                return_value=exp_map,
            ),
            patch(
                "app.indicators.port_channel.PortChannelRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=pc_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert "狀態異常" in result.failures[0]["reason"]


@pytest.mark.asyncio
class TestPortChannelEvaluateMemberStatusNone:
    """member_status is None -> no unhealthy member issues (passes member check)."""

    async def test_member_status_none_passes(self):
        indicator = PortChannelIndicator()
        session = AsyncMock()

        pc_records = [
            _make_pc_record(
                "SW-01", "Port-channel1",
                status="up",
                members=["GigabitEthernet1/0/1"],
                member_status=None,
            ),
        ]
        exp_map = {
            "SW-01": {
                "Port-channel1": _make_pc_expectation(
                    "SW-01", "Port-channel1",
                    "GigabitEthernet1/0/1",
                ),
            },
        }

        with (
            patch.object(
                indicator, "_build_expectation_map",
                new_callable=AsyncMock,
                return_value=exp_map,
            ),
            patch(
                "app.indicators.port_channel.PortChannelRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=pc_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        # member_status is None -> _unhealthy_members returns [] -> passes
        assert result.total_count == 1
        assert result.pass_count == 1
        assert result.fail_count == 0


# =====================================================================
#  PORT-CHANNEL HELPER METHOD TESTS
# =====================================================================


class TestPortChannelNormalizeName:
    """Tests for _normalize_name."""

    def test_port_channel_to_po(self):
        indicator = PortChannelIndicator()
        assert indicator._normalize_name("Port-channel1") == "po1"

    def test_bridge_aggregation_to_bagg(self):
        indicator = PortChannelIndicator()
        assert indicator._normalize_name("Bridge-Aggregation1") == "bagg1"

    def test_already_lowercase(self):
        indicator = PortChannelIndicator()
        assert indicator._normalize_name("po1") == "po1"

    def test_mixed_case(self):
        indicator = PortChannelIndicator()
        assert indicator._normalize_name("PORT-CHANNEL10") == "po10"


class TestPortChannelCalcPercent:
    """Tests for _calc_percent."""

    def test_normal(self):
        assert PortChannelIndicator._calc_percent(3, 5) == pytest.approx(60.0)

    def test_all_pass(self):
        assert PortChannelIndicator._calc_percent(10, 10) == pytest.approx(100.0)

    def test_none_pass(self):
        assert PortChannelIndicator._calc_percent(0, 10) == pytest.approx(0.0)

    def test_zero_total(self):
        assert PortChannelIndicator._calc_percent(0, 0) == 0.0


class TestPortChannelBuildDevicePCMap:
    """Tests for _build_device_pc_map."""

    def test_groups_by_hostname_and_interface(self):
        records = [
            _make_pc_record("SW-01", "Port-channel1"),
            _make_pc_record("SW-01", "Port-channel2"),
            _make_pc_record("SW-02", "Port-channel1"),
        ]
        result = PortChannelIndicator._build_device_pc_map(records)

        assert "SW-01" in result
        assert "SW-02" in result
        assert "Port-channel1" in result["SW-01"]
        assert "Port-channel2" in result["SW-01"]
        assert "Port-channel1" in result["SW-02"]

    def test_empty_records(self):
        result = PortChannelIndicator._build_device_pc_map([])
        assert result == {}


class TestPortChannelMissingMembers:
    """Tests for _missing_members."""

    def test_no_missing(self):
        exp = _make_pc_expectation(
            member_interfaces="Gi1/0/1;Gi1/0/2",
        )
        actual = _make_pc_record(
            members=["Gi1/0/1", "Gi1/0/2", "Gi1/0/3"],
        )
        result = PortChannelIndicator._missing_members(exp, actual)
        assert result == set()

    def test_some_missing(self):
        exp = _make_pc_expectation(
            member_interfaces="Gi1/0/1;Gi1/0/2;Gi1/0/3",
        )
        actual = _make_pc_record(
            members=["Gi1/0/1"],
        )
        result = PortChannelIndicator._missing_members(exp, actual)
        assert result == {"Gi1/0/2", "Gi1/0/3"}

    def test_actual_members_none(self):
        exp = _make_pc_expectation(
            member_interfaces="Gi1/0/1;Gi1/0/2",
        )
        actual = _make_pc_record(members=None)
        actual.members = None
        result = PortChannelIndicator._missing_members(exp, actual)
        assert result == {"Gi1/0/1", "Gi1/0/2"}

    def test_empty_expected(self):
        exp = _make_pc_expectation(
            member_interfaces="",
        )
        actual = _make_pc_record(
            members=["Gi1/0/1"],
        )
        result = PortChannelIndicator._missing_members(exp, actual)
        assert result == set()


class TestPortChannelUnhealthyMembers:
    """Tests for _unhealthy_members."""

    def test_all_up(self):
        record = _make_pc_record(
            member_status={
                "Gi1/0/1": "up",
                "Gi1/0/2": "up",
            },
        )
        result = PortChannelIndicator._unhealthy_members(record)
        assert result == []

    def test_some_down(self):
        record = _make_pc_record(
            member_status={
                "Gi1/0/1": "up",
                "Gi1/0/2": "down",
                "Gi1/0/3": "suspended",
            },
        )
        result = PortChannelIndicator._unhealthy_members(record)
        assert len(result) == 2
        assert any("Gi1/0/2" in item for item in result)
        assert any("Gi1/0/3" in item for item in result)

    def test_member_status_none(self):
        record = _make_pc_record()
        record.member_status = None
        result = PortChannelIndicator._unhealthy_members(record)
        assert result == []

    def test_member_status_with_none_value(self):
        """Member status value is None -> treated as unknown, which is not UP."""
        record = _make_pc_record(
            member_status={
                "Gi1/0/1": "up",
                "Gi1/0/2": None,
            },
        )
        result = PortChannelIndicator._unhealthy_members(record)
        assert len(result) == 1
        assert "Gi1/0/2" in result[0]
        assert "unknown" in result[0]


class TestPortChannelFindActualRecord:
    """Tests for _find_actual_record with normalised name fallback."""

    def test_exact_match(self):
        indicator = PortChannelIndicator()
        record = _make_pc_record(interface_name="Port-channel1")
        actual_pcs = {"Port-channel1": record}
        result = indicator._find_actual_record("Port-channel1", actual_pcs)
        assert result is record

    def test_normalised_match(self):
        """Lookup 'Po1' against record named 'Port-channel1' via normalisation."""
        indicator = PortChannelIndicator()
        record = _make_pc_record(interface_name="Port-channel1")
        actual_pcs = {"Port-channel1": record}
        result = indicator._find_actual_record("Po1", actual_pcs)
        assert result is record

    def test_not_found(self):
        indicator = PortChannelIndicator()
        record = _make_pc_record(interface_name="Port-channel2")
        actual_pcs = {"Port-channel2": record}
        result = indicator._find_actual_record("Port-channel99", actual_pcs)
        assert result is None


@pytest.mark.asyncio
class TestPortChannelEvaluateNormalizedNameMatch:
    """Port-channel found via normalized name fallback -> should pass."""

    async def test_normalized_name_match(self):
        indicator = PortChannelIndicator()
        session = AsyncMock()

        # Actual record uses full name "Port-channel1"
        pc_records = [
            _make_pc_record(
                "SW-01", "Port-channel1",
                status="up",
                members=["Gi1/0/1"],
                member_status={"Gi1/0/1": "up"},
            ),
        ]
        # Expectation uses short name "Po1"
        exp_map = {
            "SW-01": {
                "Po1": _make_pc_expectation(
                    "SW-01", "Po1",
                    "Gi1/0/1",
                ),
            },
        }

        with (
            patch.object(
                indicator, "_build_expectation_map",
                new_callable=AsyncMock,
                return_value=exp_map,
            ),
            patch(
                "app.indicators.port_channel.PortChannelRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=pc_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.total_count == 1
        assert result.pass_count == 1
        assert result.fail_count == 0


@pytest.mark.asyncio
class TestPortChannelPassesCappedAtTen:
    """passes list should not exceed 10 items across devices."""

    async def test_passes_capped(self):
        indicator = PortChannelIndicator()
        session = AsyncMock()

        # 15 expected PCs across multiple devices, all passing
        exp_map = {}
        pc_records = []
        for i in range(1, 16):
            hostname = f"SW-{i:02d}"
            pc_name = "Port-channel1"
            exp_map[hostname] = {
                pc_name: _make_pc_expectation(
                    hostname, pc_name, "Gi1/0/1",
                ),
            }
            pc_records.append(
                _make_pc_record(
                    hostname, pc_name,
                    status="up",
                    members=["Gi1/0/1"],
                    member_status={"Gi1/0/1": "up"},
                )
            )

        with (
            patch.object(
                indicator, "_build_expectation_map",
                new_callable=AsyncMock,
                return_value=exp_map,
            ),
            patch(
                "app.indicators.port_channel.PortChannelRecordRepo.get_latest_per_device",
                new_callable=AsyncMock,
                return_value=pc_records,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, session)

        assert result.pass_count == 15
        assert result.passes is not None
        assert len(result.passes) <= 10


class TestPortChannelFailureHelper:
    """Tests for the _failure static-like method."""

    def test_failure_without_actual(self):
        result = PortChannelIndicator._failure("SW-01", "Po1", "some reason")
        assert result["device"] == "SW-01"
        assert result["interface"] == "Po1"
        assert result["reason"] == "some reason"
        assert result["data"] is None

    def test_failure_with_actual(self):
        actual = _make_pc_record(
            interface_name="Port-channel1",
            status="down",
            members=["Gi1/0/1"],
            member_status={"Gi1/0/1": "down"},
        )
        result = PortChannelIndicator._failure(
            "SW-01", "Port-channel1", "status down", actual,
        )
        assert result["data"] is not None
        assert result["data"]["interface_name"] == "Port-channel1"
        assert result["data"]["status"] == "down"
        assert result["data"]["members"] == ["Gi1/0/1"]


class TestPortChannelRecordToData:
    """Tests for _record_to_data."""

    def test_serialises_key_fields(self):
        record = _make_pc_record(
            interface_name="Port-channel1",
            status="up",
            members=["Gi1/0/1", "Gi1/0/2"],
            member_status={"Gi1/0/1": "up", "Gi1/0/2": "up"},
        )
        data = PortChannelIndicator._record_to_data(record)
        assert data["interface_name"] == "Port-channel1"
        assert data["status"] == "up"
        assert data["members"] == ["Gi1/0/1", "Gi1/0/2"]
        assert data["member_status"] == {"Gi1/0/1": "up", "Gi1/0/2": "up"}


# =====================================================================
#  INDICATOR TYPE ATTRIBUTE TESTS
# =====================================================================


class TestIndicatorTypeAttributes:
    """Verify indicator_type class attribute is set correctly."""

    def test_uplink_indicator_type(self):
        assert UplinkIndicator.indicator_type == "uplink"

    def test_version_indicator_type(self):
        assert VersionIndicator.indicator_type == "version"

    def test_port_channel_indicator_type(self):
        assert PortChannelIndicator.indicator_type == "port_channel"
