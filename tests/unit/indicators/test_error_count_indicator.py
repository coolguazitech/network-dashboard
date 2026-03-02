"""
Unit tests for ErrorCountIndicator.evaluate() — device-level evaluation.

Mocking strategy:
- indicator._get_active_device_hostnames  -> returns list of hostnames
- InterfaceErrorRecordRepo.get_latest_per_device -> returns list of mock records
- ErrorCountIndicator._get_previous_batches -> returns dict
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.indicators.error_count import ErrorCountIndicator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAINTENANCE_ID = "maint-001"


def _make_record(
    hostname: str,
    interface: str,
    crc_errors: int,
    batch_id: int = 100,
    collected_at: datetime | None = None,
) -> MagicMock:
    """Create a mock InterfaceErrorRecord with the required attributes."""
    rec = MagicMock()
    rec.switch_hostname = hostname
    rec.interface_name = interface
    rec.crc_errors = crc_errors
    rec.batch_id = batch_id
    rec.collected_at = collected_at or datetime(2026, 1, 1, 12, 0, 0)
    return rec


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestErrorCountEvaluate:
    """Tests for ErrorCountIndicator.evaluate() — device-level."""

    @pytest.fixture()
    def indicator(self) -> ErrorCountIndicator:
        return ErrorCountIndicator()

    @pytest.fixture()
    def mock_session(self) -> AsyncMock:
        return AsyncMock()

    # 1. Delta positive → device failure --------------------------------------

    async def test_delta_positive_is_failure(
        self, indicator: ErrorCountIndicator, mock_session: AsyncMock,
    ) -> None:
        """CRC errors grew on an interface -> device fails."""
        current = [_make_record("switch-A", "Gi1/0/1", crc_errors=15, batch_id=200)]
        prev = {"switch-A": {"Gi1/0/1": {"crc_errors": 10}}}

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["switch-A"],
            ),
            patch(
                "app.indicators.error_count.InterfaceErrorRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=current,
            ),
            patch.object(
                indicator, "_get_previous_batches",
                new_callable=AsyncMock, return_value=prev,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert len(result.failures) == 1

        failure = result.failures[0]
        assert failure["device"] == "switch-A"
        assert "CRC 增長" in failure["reason"]
        # Verify growing_interfaces detail
        growing = failure["data"]["growing_interfaces"]
        assert len(growing) == 1
        assert growing[0]["interface"] == "Gi1/0/1"
        assert growing[0]["delta"] == 5
        assert growing[0]["prev_crc_errors"] == 10
        assert growing[0]["crc_errors"] == 15

    # 2. Delta zero → device pass ---------------------------------------------

    async def test_delta_zero_is_pass(
        self, indicator: ErrorCountIndicator, mock_session: AsyncMock,
    ) -> None:
        """CRC errors unchanged -> device passes with '計數器未增長'."""
        current = [_make_record("switch-A", "Gi1/0/1", crc_errors=10, batch_id=200)]
        prev = {"switch-A": {"Gi1/0/1": {"crc_errors": 10}}}

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["switch-A"],
            ),
            patch(
                "app.indicators.error_count.InterfaceErrorRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=current,
            ),
            patch.object(
                indicator, "_get_previous_batches",
                new_callable=AsyncMock, return_value=prev,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 1
        assert result.fail_count == 0
        assert result.passes is not None
        assert result.passes[0]["reason"] == "計數器未增長"

    # 3. Delta negative → device pass (counter reset) -------------------------

    async def test_delta_negative_is_pass(
        self, indicator: ErrorCountIndicator, mock_session: AsyncMock,
    ) -> None:
        """CRC errors decreased (counter reset) -> device passes."""
        current = [_make_record("switch-A", "Gi1/0/1", crc_errors=3, batch_id=200)]
        prev = {"switch-A": {"Gi1/0/1": {"crc_errors": 50}}}

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["switch-A"],
            ),
            patch(
                "app.indicators.error_count.InterfaceErrorRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=current,
            ),
            patch.object(
                indicator, "_get_previous_batches",
                new_callable=AsyncMock, return_value=prev,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 1
        assert result.fail_count == 0
        assert result.passes is not None
        assert result.passes[0]["reason"] == "計數器未增長"

    # 4. First collection, no previous batch ----------------------------------

    async def test_first_collection_no_previous(
        self, indicator: ErrorCountIndicator, mock_session: AsyncMock,
    ) -> None:
        """No previous batch data -> device passes with '首次採集'."""
        current = [_make_record("switch-A", "Gi1/0/1", crc_errors=5, batch_id=200)]
        prev: dict = {}  # no previous batches at all

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["switch-A"],
            ),
            patch(
                "app.indicators.error_count.InterfaceErrorRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=current,
            ),
            patch.object(
                indicator, "_get_previous_batches",
                new_callable=AsyncMock, return_value=prev,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 1
        assert result.pass_count == 1
        assert result.fail_count == 0
        assert result.passes is not None
        assert "首次採集" in result.passes[0]["reason"]

    # 5. Non-active devices are filtered out ----------------------------------

    async def test_non_active_devices_filtered(
        self, indicator: ErrorCountIndicator, mock_session: AsyncMock,
    ) -> None:
        """Records from inactive devices should not be counted."""
        # "switch-B" is in the records but NOT in active device list
        current = [
            _make_record("switch-A", "Gi1/0/1", crc_errors=10, batch_id=200),
            _make_record("switch-B", "Gi1/0/1", crc_errors=99, batch_id=201),
        ]
        prev: dict = {}

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["switch-A"],
            ),
            patch(
                "app.indicators.error_count.InterfaceErrorRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=current,
            ),
            patch.object(
                indicator, "_get_previous_batches",
                new_callable=AsyncMock, return_value=prev,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        # Only switch-A counted (1 device)
        assert result.total_count == 1
        assert result.pass_count == 1
        assert result.fail_count == 0
        # Verify switch-B is nowhere in passes or failures
        all_devices = set()
        if result.passes:
            all_devices.update(p["device"] for p in result.passes)
        if result.failures:
            all_devices.update(f["device"] for f in result.failures)
        assert "switch-B" not in all_devices

    # 6. Empty device list ----------------------------------------------------

    async def test_empty_device_list(
        self, indicator: ErrorCountIndicator, mock_session: AsyncMock,
    ) -> None:
        """No active devices -> total_count=0, summary '無設備資料'."""
        with patch.object(
            indicator, "_get_active_device_hostnames",
            new_callable=AsyncMock, return_value=[],
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 0
        assert result.pass_count == 0
        assert result.fail_count == 0
        assert result.summary == "無設備資料"
        assert result.pass_rates == {"error_no_growth": 0}

    # 7. Multiple interfaces per device — device-level aggregation ------------

    async def test_multiple_interfaces_one_growth_device_fails(
        self, indicator: ErrorCountIndicator, mock_session: AsyncMock,
    ) -> None:
        """Device with 3 interfaces, 1 has growth -> device fails (total=1, fail=1)."""
        current = [
            _make_record("switch-A", "Gi1/0/1", crc_errors=10, batch_id=200),
            _make_record("switch-A", "Gi1/0/2", crc_errors=20, batch_id=200),
            _make_record("switch-A", "Gi1/0/3", crc_errors=30, batch_id=200),
        ]
        prev = {
            "switch-A": {
                "Gi1/0/1": {"crc_errors": 10},   # delta=0  -> ok
                "Gi1/0/2": {"crc_errors": 15},   # delta=+5 -> growth!
                "Gi1/0/3": {"crc_errors": 30},   # delta=0  -> ok
            },
        }

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["switch-A"],
            ),
            patch(
                "app.indicators.error_count.InterfaceErrorRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=current,
            ),
            patch.object(
                indicator, "_get_previous_batches",
                new_callable=AsyncMock, return_value=prev,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        # Device level: 1 device, it fails
        assert result.total_count == 1
        assert result.pass_count == 0
        assert result.fail_count == 1
        assert result.failures is not None
        assert len(result.failures) == 1
        assert result.failures[0]["device"] == "switch-A"
        # Only Gi1/0/2 should be in the growing list
        growing = result.failures[0]["data"]["growing_interfaces"]
        assert len(growing) == 1
        assert growing[0]["interface"] == "Gi1/0/2"
        assert growing[0]["delta"] == 5

    # 8. Mixed devices — each evaluated independently -------------------------

    async def test_mixed_devices(
        self, indicator: ErrorCountIndicator, mock_session: AsyncMock,
    ) -> None:
        """Two devices, both have growth on one interface -> both fail."""
        current = [
            # switch-A: two interfaces
            _make_record("switch-A", "Gi1/0/1", crc_errors=10, batch_id=200),
            _make_record("switch-A", "Gi1/0/2", crc_errors=50, batch_id=200),
            # switch-B: two interfaces
            _make_record("switch-B", "Gi1/0/1", crc_errors=0, batch_id=201),
            _make_record("switch-B", "Gi1/0/2", crc_errors=100, batch_id=201),
        ]
        prev = {
            "switch-A": {
                "Gi1/0/1": {"crc_errors": 10},   # delta=0  -> ok
                "Gi1/0/2": {"crc_errors": 30},   # delta=+20 -> growth
            },
            "switch-B": {
                "Gi1/0/1": {"crc_errors": 5},    # delta=-5 -> reset
                "Gi1/0/2": {"crc_errors": 80},   # delta=+20 -> growth
            },
        }

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["switch-A", "switch-B"],
            ),
            patch(
                "app.indicators.error_count.InterfaceErrorRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=current,
            ),
            patch.object(
                indicator, "_get_previous_batches",
                new_callable=AsyncMock, return_value=prev,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        # Device level: 2 devices, both fail
        assert result.total_count == 2
        assert result.pass_count == 0
        assert result.fail_count == 2
        assert result.pass_rates["error_no_growth"] == 0.0

        # Verify failures contain the right devices
        fail_devices = {f["device"] for f in result.failures}
        assert fail_devices == {"switch-A", "switch-B"}

    # 9. Device with no error records (collector skipped) → PASS --------------

    async def test_device_no_error_records_is_pass(
        self, indicator: ErrorCountIndicator, mock_session: AsyncMock,
    ) -> None:
        """Active device with no collected error records -> PASS (無錯誤記錄)."""
        # switch-A has records, switch-B has none (all interfaces zero errors)
        current = [
            _make_record("switch-A", "Gi1/0/1", crc_errors=5, batch_id=200),
        ]
        prev: dict = {}

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["switch-A", "switch-B"],
            ),
            patch(
                "app.indicators.error_count.InterfaceErrorRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=current,
            ),
            patch.object(
                indicator, "_get_previous_batches",
                new_callable=AsyncMock, return_value=prev,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        # 2 devices total, both pass
        assert result.total_count == 2
        assert result.pass_count == 2
        assert result.fail_count == 0
        assert result.passes is not None
        pass_by_device = {p["device"]: p for p in result.passes}
        assert pass_by_device["switch-B"]["reason"] == "無錯誤記錄"
        assert "首次採集" in pass_by_device["switch-A"]["reason"]

    # 10. Mixed pass/fail across devices with different scenarios --------------

    async def test_mixed_pass_fail_devices(
        self, indicator: ErrorCountIndicator, mock_session: AsyncMock,
    ) -> None:
        """3 devices: one no records (pass), one no growth (pass), one growth (fail)."""
        current = [
            # switch-A: stable
            _make_record("switch-A", "Gi1/0/1", crc_errors=10, batch_id=200),
            # switch-B: growth
            _make_record("switch-B", "Gi1/0/1", crc_errors=20, batch_id=201),
            # switch-C: no records (not in current)
        ]
        prev = {
            "switch-A": {"Gi1/0/1": {"crc_errors": 10}},   # delta=0
            "switch-B": {"Gi1/0/1": {"crc_errors": 5}},    # delta=+15
        }

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["switch-A", "switch-B", "switch-C"],
            ),
            patch(
                "app.indicators.error_count.InterfaceErrorRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=current,
            ),
            patch.object(
                indicator, "_get_previous_batches",
                new_callable=AsyncMock, return_value=prev,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.total_count == 3
        assert result.pass_count == 2
        assert result.fail_count == 1
        assert result.pass_rates["error_no_growth"] == pytest.approx(66.666, abs=0.01)
        assert result.summary == "錯誤計數: 2/3 設備通過"


class TestCalcPercent:
    """Tests for ErrorCountIndicator._calc_percent() edge cases."""

    def test_zero_total_returns_zero(self) -> None:
        """0/0 -> 0.0 (avoid ZeroDivisionError)."""
        assert ErrorCountIndicator._calc_percent(0, 0) == 0.0

    def test_half_pass(self) -> None:
        """1/2 -> 50.0."""
        assert ErrorCountIndicator._calc_percent(1, 2) == 50.0

    def test_all_pass(self) -> None:
        """3/3 -> 100.0."""
        assert ErrorCountIndicator._calc_percent(3, 3) == 100.0

    def test_none_pass(self) -> None:
        """0/5 -> 0.0."""
        assert ErrorCountIndicator._calc_percent(0, 5) == 0.0

    def test_partial(self) -> None:
        """2/3 -> 66.666... ."""
        result = ErrorCountIndicator._calc_percent(2, 3)
        assert abs(result - 66.66666666666667) < 1e-10


class TestIndicatorType:
    """Verify class-level attributes."""

    def test_indicator_type(self) -> None:
        indicator = ErrorCountIndicator()
        assert indicator.indicator_type == "error_count"


class TestEvaluateResultStructure:
    """Verify the IndicatorEvaluationResult has correct structural properties."""

    @pytest.fixture()
    def indicator(self) -> ErrorCountIndicator:
        return ErrorCountIndicator()

    @pytest.fixture()
    def mock_session(self) -> AsyncMock:
        return AsyncMock()

    async def test_result_indicator_type_and_maintenance_id(
        self, indicator: ErrorCountIndicator, mock_session: AsyncMock,
    ) -> None:
        """Result carries the correct indicator_type and maintenance_id."""
        current = [_make_record("sw1", "Gi1/0/1", crc_errors=0, batch_id=100)]
        prev: dict = {}

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["sw1"],
            ),
            patch(
                "app.indicators.error_count.InterfaceErrorRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=current,
            ),
            patch.object(
                indicator, "_get_previous_batches",
                new_callable=AsyncMock, return_value=prev,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.indicator_type == "error_count"
        assert result.maintenance_id == MAINTENANCE_ID

    async def test_summary_format(
        self, indicator: ErrorCountIndicator, mock_session: AsyncMock,
    ) -> None:
        """Summary follows '錯誤計數: X/Y 設備通過' format."""
        current = [
            _make_record("sw1", "Gi1/0/1", crc_errors=0, batch_id=100),
            _make_record("sw1", "Gi1/0/2", crc_errors=5, batch_id=100),
        ]
        prev = {
            "sw1": {
                "Gi1/0/1": {"crc_errors": 0},
                "Gi1/0/2": {"crc_errors": 0},   # delta=+5 -> growth
            },
        }

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["sw1"],
            ),
            patch(
                "app.indicators.error_count.InterfaceErrorRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=current,
            ),
            patch.object(
                indicator, "_get_previous_batches",
                new_callable=AsyncMock, return_value=prev,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        # sw1 has growth on Gi1/0/2 -> device fails -> 0/1 pass
        assert result.summary == "錯誤計數: 0/1 設備通過"

    async def test_failures_none_when_all_pass(
        self, indicator: ErrorCountIndicator, mock_session: AsyncMock,
    ) -> None:
        """failures field is None when there are no failures."""
        current = [_make_record("sw1", "Gi1/0/1", crc_errors=10, batch_id=100)]
        prev = {"sw1": {"Gi1/0/1": {"crc_errors": 10}}}

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["sw1"],
            ),
            patch(
                "app.indicators.error_count.InterfaceErrorRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=current,
            ),
            patch.object(
                indicator, "_get_previous_batches",
                new_callable=AsyncMock, return_value=prev,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.failures is None

    async def test_passes_none_when_all_fail(
        self, indicator: ErrorCountIndicator, mock_session: AsyncMock,
    ) -> None:
        """passes field is None when every device fails."""
        current = [_make_record("sw1", "Gi1/0/1", crc_errors=20, batch_id=100)]
        prev = {"sw1": {"Gi1/0/1": {"crc_errors": 5}}}

        with (
            patch.object(
                indicator, "_get_active_device_hostnames",
                new_callable=AsyncMock, return_value=["sw1"],
            ),
            patch(
                "app.indicators.error_count.InterfaceErrorRecordRepo.get_latest_per_device",
                new_callable=AsyncMock, return_value=current,
            ),
            patch.object(
                indicator, "_get_previous_batches",
                new_callable=AsyncMock, return_value=prev,
            ),
        ):
            result = await indicator.evaluate(MAINTENANCE_ID, mock_session)

        assert result.passes is None
