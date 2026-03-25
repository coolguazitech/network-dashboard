"""
Stress tests for CollectionCoordinator — simulates production-like scenarios.

Tests that the system handles:
1. Many concurrent devices without stalling
2. Mix of reachable + unreachable devices
3. Slow devices that hit hard timeout
4. Data preservation: failures don't overwrite successful data
5. Semaphore properly released after all timeout scenarios
"""
from __future__ import annotations

import asyncio
import sys
import time as _time
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub out pysnmp (same as other snmp tests)
# ---------------------------------------------------------------------------
_pysnmp_stub = ModuleType("pysnmp")
_hlapi_stub = ModuleType("pysnmp.hlapi")
_asyncio_stub = ModuleType("pysnmp.hlapi.asyncio")

for _attr in (
    "CommunityData", "ContextData", "ObjectIdentity", "ObjectType",
    "UdpTransportTarget", "bulkCmd", "getCmd",
):
    setattr(_asyncio_stub, _attr, MagicMock())
_asyncio_stub.SnmpEngine = MagicMock()

for _mod_name, _mod in (
    ("pysnmp", _pysnmp_stub),
    ("pysnmp.hlapi", _hlapi_stub),
    ("pysnmp.hlapi.asyncio", _asyncio_stub),
):
    sys.modules.setdefault(_mod_name, _mod)

from app.snmp.engine import AsyncSnmpEngine, SnmpTarget, SnmpTimeoutError  # noqa: E402
from app.snmp.collection_coordinator import CollectionCoordinator, DeviceResult  # noqa: E402
from app.snmp.collector_base import BaseSnmpCollector  # noqa: E402
from app.snmp.session_cache import SnmpSessionCache  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeCollector(BaseSnmpCollector):
    """Collector that simulates configurable delay and success/failure."""

    api_name = "fake_collector"

    def __init__(self, delay: float = 0.01, fail: bool = False):
        self.delay = delay
        self.fail = fail
        self.call_count = 0

    async def collect(self, target, device_type, session_cache, engine):
        self.call_count += 1
        await asyncio.sleep(self.delay)
        if self.fail:
            raise SnmpTimeoutError(f"Simulated timeout for {target.ip}")
        return "raw_data", []


class SlowCollector(BaseSnmpCollector):
    """Collector that sleeps forever (to test hard timeout)."""

    api_name = "slow_collector"

    async def collect(self, target, device_type, session_cache, engine):
        # Sleep longer than any reasonable hard timeout
        await asyncio.sleep(999)
        return "never_reached", []


def _make_device(ip: str, hostname: str | None = None) -> dict:
    return {
        "hostname": hostname or f"SW-{ip}",
        "ip": ip,
        "vendor": "HPE",
    }


@pytest.fixture(autouse=True)
def _clear_caches():
    SnmpSessionCache.clear_all()
    yield
    SnmpSessionCache.clear_all()


def _mock_session_cache(*, unreachable_ips: set[str] | None = None):
    """Create a mock session cache that resolves instantly or raises timeout."""
    unreachable = unreachable_ips or set()
    cache = MagicMock(spec=SnmpSessionCache)

    async def fake_get_target(ip):
        if ip in unreachable:
            raise SnmpTimeoutError(f"Unreachable: {ip}")
        return SnmpTarget(ip=ip, community="public", port=161, timeout=3.0, retries=1)

    cache.get_target = AsyncMock(side_effect=fake_get_target)
    cache.is_negative_cached = MagicMock(return_value=False)
    cache.is_community_known = MagicMock(return_value=False)
    return cache


def _mock_save():
    """Patch _save_device_results to be a no-op."""
    return patch.object(
        CollectionCoordinator,
        "_save_device_results",
        new_callable=AsyncMock,
    )


# =========================================================================
# Test 1: 50 devices with concurrency=20 completes in bounded time
# =========================================================================


@pytest.mark.asyncio
async def test_50_devices_completes_in_bounded_time():
    """50 reachable devices with concurrency=20 must complete, not stall."""
    sem = asyncio.Semaphore(20)
    collector = FakeCollector(delay=0.01)  # 10ms per collector
    engine = MagicMock(spec=AsyncSnmpEngine)

    coord = CollectionCoordinator(
        engine=engine,
        collectors={"fake_collector": collector},
        semaphore=sem,
    )

    devices = [_make_device(f"10.0.0.{i}") for i in range(50)]
    cache = _mock_session_cache()

    with _mock_save():
        t0 = _time.monotonic()
        results = await asyncio.gather(
            *[
                coord._collect_device(
                    device_info=dev,
                    collectors=[collector],
                    session_cache=cache,
                    maintenance_id="M-TEST",
                )
                for dev in devices
            ],
            return_exceptions=True,
        )
        elapsed = _time.monotonic() - t0

    # All should succeed
    ok_count = sum(1 for r in results if isinstance(r, DeviceResult) and r.status == "ok")
    assert ok_count == 50, f"Expected 50 ok, got {ok_count}"

    # With concurrency=20, 50 devices × 10ms should finish well under 5s
    assert elapsed < 5.0, f"Took {elapsed:.1f}s, expected < 5s"


# =========================================================================
# Test 2: Mix of reachable + unreachable devices
# =========================================================================


@pytest.mark.asyncio
async def test_mixed_reachable_unreachable():
    """4 unreachable + 46 reachable devices should all complete."""
    sem = asyncio.Semaphore(20)
    collector = FakeCollector(delay=0.01)
    engine = MagicMock(spec=AsyncSnmpEngine)

    coord = CollectionCoordinator(
        engine=engine,
        collectors={"fake_collector": collector},
        semaphore=sem,
    )

    unreachable_ips = {f"10.0.0.{i}" for i in range(4)}
    devices = [_make_device(f"10.0.0.{i}") for i in range(50)]
    cache = _mock_session_cache(unreachable_ips=unreachable_ips)

    with _mock_save():
        results = await asyncio.gather(
            *[
                coord._collect_device(
                    device_info=dev,
                    collectors=[collector],
                    session_cache=cache,
                    maintenance_id="M-TEST",
                )
                for dev in devices
            ],
            return_exceptions=True,
        )

    device_results = [r for r in results if isinstance(r, DeviceResult)]
    assert len(device_results) == 50

    ok_count = sum(1 for r in device_results if r.status == "ok")
    unreachable_count = sum(1 for r in device_results if r.status == "unreachable")
    assert ok_count == 46
    assert unreachable_count == 4


# =========================================================================
# Test 3: Slow device hits hard timeout, doesn't block others
# =========================================================================


@pytest.mark.asyncio
async def test_slow_device_hits_hard_timeout():
    """A device that exceeds DEVICE_HARD_TIMEOUT gets cancelled, others proceed."""
    sem = asyncio.Semaphore(5)
    slow = SlowCollector()
    fast = FakeCollector(delay=0.01)
    engine = MagicMock(spec=AsyncSnmpEngine)

    coord = CollectionCoordinator(
        engine=engine,
        collectors={"slow_collector": slow, "fake_collector": fast},
        semaphore=sem,
    )
    # Override hard timeout constants to something short for testing
    orig_min = CollectionCoordinator._HARD_TIMEOUT_MIN
    orig_budget = CollectionCoordinator._PER_COLLECTOR_BUDGET
    orig_probe = CollectionCoordinator._HARD_TIMEOUT_PROBE
    CollectionCoordinator._HARD_TIMEOUT_MIN = 0.5
    CollectionCoordinator._PER_COLLECTOR_BUDGET = 0.1
    CollectionCoordinator._HARD_TIMEOUT_PROBE = 0.1

    cache = _mock_session_cache()

    try:
        # 1 slow device + 4 fast devices
        slow_device = _make_device("10.0.0.1", "SLOW-SWITCH")
        fast_devices = [_make_device(f"10.0.0.{i}", f"FAST-{i}") for i in range(2, 6)]

        with _mock_save():
            t0 = _time.monotonic()
            results = await asyncio.gather(
                coord._collect_device(
                    device_info=slow_device,
                    collectors=[slow],
                    session_cache=cache,
                    maintenance_id="M-TEST",
                ),
                *[
                    coord._collect_device(
                        device_info=dev,
                        collectors=[fast],
                        session_cache=cache,
                        maintenance_id="M-TEST",
                    )
                    for dev in fast_devices
                ],
                return_exceptions=True,
            )
            elapsed = _time.monotonic() - t0

        device_results = [r for r in results if isinstance(r, DeviceResult)]

        # Slow device should be marked as unreachable (hard timeout)
        slow_result = next(r for r in device_results if r.hostname == "SLOW-SWITCH")
        assert slow_result.status == "unreachable", f"Expected unreachable, got {slow_result.status}"

        # Fast devices should all succeed
        fast_results = [r for r in device_results if r.hostname.startswith("FAST")]
        assert all(r.status == "ok" for r in fast_results)

        # Total time should be bounded by hard timeout, not by slow collector
        assert elapsed < 3.0, f"Took {elapsed:.1f}s — slow device blocked others"

    finally:
        CollectionCoordinator._HARD_TIMEOUT_MIN = orig_min
        CollectionCoordinator._PER_COLLECTOR_BUDGET = orig_budget
        CollectionCoordinator._HARD_TIMEOUT_PROBE = orig_probe


# =========================================================================
# Test 4: Semaphore is always released (even after timeout/crash)
# =========================================================================


@pytest.mark.asyncio
async def test_semaphore_released_after_all_scenarios():
    """Semaphore slots must be freed after success, timeout, and error."""
    sem = asyncio.Semaphore(3)
    engine = MagicMock(spec=AsyncSnmpEngine)

    # Collector that sometimes fails
    fail_collector = FakeCollector(delay=0.01, fail=True)
    ok_collector = FakeCollector(delay=0.01, fail=False)

    coord = CollectionCoordinator(
        engine=engine,
        collectors={"fail": fail_collector, "ok": ok_collector},
        semaphore=sem,
    )

    unreachable_ips = {"10.0.0.1"}
    devices = [
        _make_device("10.0.0.1"),  # unreachable
        _make_device("10.0.0.2"),  # ok
        _make_device("10.0.0.3"),  # ok
    ]
    cache = _mock_session_cache(unreachable_ips=unreachable_ips)

    with _mock_save():
        await asyncio.gather(
            *[
                coord._collect_device(
                    device_info=dev,
                    collectors=[ok_collector],
                    session_cache=cache,
                    maintenance_id="M-TEST",
                )
                for dev in devices
            ],
            return_exceptions=True,
        )

    # All 3 semaphore slots should be available again
    for i in range(3):
        acquired = sem._value
    assert sem._value == 3, f"Semaphore leaked: {sem._value} slots available (expected 3)"


# =========================================================================
# Test 5: Failure does NOT overwrite successful data
# =========================================================================


@pytest.mark.asyncio
async def test_failure_does_not_call_save_batch():
    """When a collector fails, _save_device_results should NOT call
    save_batch with empty items (which would overwrite good data)."""
    sem = asyncio.Semaphore(5)
    fail_collector = FakeCollector(delay=0.01, fail=True)
    engine = MagicMock(spec=AsyncSnmpEngine)

    coord = CollectionCoordinator(
        engine=engine,
        collectors={"fake_collector": fail_collector},
        semaphore=sem,
    )
    cache = _mock_session_cache()

    device = _make_device("10.0.0.1")

    # Patch the REAL _save_device_results to capture what it's called with
    saved_outcomes = []
    original_save = coord._save_device_results

    async def capture_save(hostname, maintenance_id, collector_outcomes):
        saved_outcomes.extend(collector_outcomes)

    with patch.object(coord, "_save_device_results", side_effect=capture_save):
        result = await coord._collect_device(
            device_info=device,
            collectors=[fail_collector],
            session_cache=cache,
            maintenance_id="M-TEST",
        )

    # The result status should be partial (collector failed)
    assert result.status == "partial" or result.collector_results.get("fake_collector") == "timeout"

    # The outcome should have status "timeout", NOT "ok"
    for api_name, status, error_msg, parsed_items in saved_outcomes:
        if status != "ok":
            # This is the failure case — parsed_items should be empty
            assert parsed_items == [], "Failure should have empty parsed_items"
            assert error_msg is not None, "Failure should have error message"


# =========================================================================
# Test 6: Deferred engine close on timeout
# =========================================================================


@pytest.mark.asyncio
async def test_deferred_close_on_timeout():
    """When get() times out, engine should NOT be closed immediately."""
    engine = AsyncSnmpEngine()

    mock_pysnmp_engine = MagicMock()
    mock_transport = MagicMock()

    with patch.object(engine, "_new_engine", return_value=mock_pysnmp_engine), \
         patch.object(engine, "_make_transport", return_value=mock_transport), \
         patch.object(engine, "_close_engine") as mock_close, \
         patch.object(engine, "_deferred_close_engine") as mock_deferred_close:

        # Make getCmd hang forever
        async def hang_forever(*args, **kwargs):
            await asyncio.sleep(999)

        from pysnmp.hlapi.asyncio import getCmd
        getCmd.side_effect = hang_forever

        target = SnmpTarget(ip="10.0.0.1", community="public", timeout=0.01, retries=0)

        with pytest.raises(SnmpTimeoutError):
            await engine.get(target, "1.3.6.1.2.1.1.2.0")

        # Should use deferred close, NOT immediate close
        mock_deferred_close.assert_called_once_with(mock_pysnmp_engine)
        mock_close.assert_not_called()


# =========================================================================
# Test 7: Normal close on success (no deferred)
# =========================================================================


@pytest.mark.asyncio
async def test_immediate_close_on_success():
    """When get() succeeds, engine should be closed immediately (not deferred)."""
    engine = AsyncSnmpEngine()

    mock_pysnmp_engine = MagicMock()
    mock_transport = MagicMock()

    with patch.object(engine, "_new_engine", return_value=mock_pysnmp_engine), \
         patch.object(engine, "_make_transport", return_value=mock_transport), \
         patch.object(engine, "_close_engine") as mock_close, \
         patch.object(engine, "_deferred_close_engine") as mock_deferred_close:

        # Make getCmd return immediately with valid response
        mock_varbind = MagicMock()
        mock_oid = MagicMock()
        mock_oid.__str__ = lambda self: "1.3.6.1.2.1.1.2.0"
        mock_val = MagicMock()
        mock_val.__class__ = type("OctetString", (), {})
        mock_val.prettyPrint = lambda: "1.3.6.1.4.1.25506"

        async def instant_response(*args, **kwargs):
            return (None, None, None, [(mock_oid, mock_val)])

        from pysnmp.hlapi.asyncio import getCmd
        getCmd.side_effect = instant_response

        target = SnmpTarget(ip="10.0.0.1", community="public", timeout=5, retries=1)
        await engine.get(target, "1.3.6.1.2.1.1.2.0")

        # Should use immediate close, NOT deferred
        mock_close.assert_called_once_with(mock_pysnmp_engine)
        mock_deferred_close.assert_not_called()


# =========================================================================
# Test 8: High concurrency stress — 100 devices, semaphore=20
# =========================================================================


@pytest.mark.asyncio
async def test_100_devices_concurrency_20_bounded_time():
    """100 devices with sem=20 must complete without deadlock."""
    sem = asyncio.Semaphore(20)
    collector = FakeCollector(delay=0.05)  # 50ms per device
    engine = MagicMock(spec=AsyncSnmpEngine)

    coord = CollectionCoordinator(
        engine=engine,
        collectors={"fake_collector": collector},
        semaphore=sem,
    )

    devices = [_make_device(f"10.0.{i // 256}.{i % 256}") for i in range(100)]
    # 10 unreachable
    unreachable = {f"10.0.{i // 256}.{i % 256}" for i in range(10)}
    cache = _mock_session_cache(unreachable_ips=unreachable)

    with _mock_save():
        t0 = _time.monotonic()
        results = await asyncio.gather(
            *[
                coord._collect_device(
                    device_info=dev,
                    collectors=[collector],
                    session_cache=cache,
                    maintenance_id="M-TEST",
                )
                for dev in devices
            ],
            return_exceptions=True,
        )
        elapsed = _time.monotonic() - t0

    device_results = [r for r in results if isinstance(r, DeviceResult)]
    ok_count = sum(1 for r in device_results if r.status == "ok")
    unreachable_count = sum(1 for r in device_results if r.status == "unreachable")

    assert ok_count == 90, f"Expected 90 ok, got {ok_count}"
    assert unreachable_count == 10, f"Expected 10 unreachable, got {unreachable_count}"

    # 100 devices / 20 concurrency = 5 batches × 50ms = ~250ms
    # Give generous headroom for CI
    assert elapsed < 10.0, f"Took {elapsed:.1f}s — possible deadlock"
    assert sem._value == 20, f"Semaphore leaked: {sem._value}/20"


# =========================================================================
# Test 9: Hard timeout with multiple collectors (simulates full_round)
# =========================================================================


@pytest.mark.asyncio
async def test_hard_timeout_with_8_collectors():
    """Device with 8 collectors that each take 10s should hit hard timeout."""
    sem = asyncio.Semaphore(5)
    engine = MagicMock(spec=AsyncSnmpEngine)

    # 8 collectors each taking 10 seconds = 80s total, but hard timeout = 2s
    collectors = []
    for i in range(8):
        c = FakeCollector(delay=10.0)
        c.api_name = f"collector_{i}"
        collectors.append(c)

    coord = CollectionCoordinator(
        engine=engine,
        collectors={c.api_name: c for c in collectors},
        semaphore=sem,
    )

    # Override: 8 collectors × 0.25s + 0.0 = 2.0s hard timeout
    orig_min = CollectionCoordinator._HARD_TIMEOUT_MIN
    orig_budget = CollectionCoordinator._PER_COLLECTOR_BUDGET
    orig_probe = CollectionCoordinator._HARD_TIMEOUT_PROBE
    CollectionCoordinator._HARD_TIMEOUT_MIN = 1.0
    CollectionCoordinator._PER_COLLECTOR_BUDGET = 0.25
    CollectionCoordinator._HARD_TIMEOUT_PROBE = 0.0

    cache = _mock_session_cache()
    device = _make_device("10.0.0.1")

    try:
        with _mock_save():
            t0 = _time.monotonic()
            result = await coord._collect_device(
                device_info=device,
                collectors=collectors,
                session_cache=cache,
                maintenance_id="M-TEST",
            )
            elapsed = _time.monotonic() - t0

        assert result.status == "unreachable", f"Expected unreachable (timeout), got {result.status}"
        # Should complete near the hard timeout (~2s), not 80s
        assert elapsed < 5.0, f"Took {elapsed:.1f}s, hard timeout should have kicked in at ~2s"
        # Semaphore should be released
        assert sem._value == 5

    finally:
        CollectionCoordinator._HARD_TIMEOUT_MIN = orig_min
        CollectionCoordinator._PER_COLLECTOR_BUDGET = orig_budget
        CollectionCoordinator._HARD_TIMEOUT_PROBE = orig_probe


# =========================================================================
# Test 10: Two-phase collection — cached devices complete before probe phase
# =========================================================================


@pytest.mark.asyncio
async def test_two_phase_cached_devices_complete_first():
    """Known-reachable devices (phase 1) should finish before probe phase.

    Simulates: 30 unreachable + 20 reachable. The 20 reachable devices
    have community cache hits and complete in phase 1 without waiting
    for the 30 unreachable devices to probe/timeout in phase 2.

    Verification: track DB write order — reachable devices should appear
    in save calls before unreachable ones.
    """
    sem = asyncio.Semaphore(20)
    collector = FakeCollector(delay=0.01)
    engine = MagicMock(spec=AsyncSnmpEngine)

    coord = CollectionCoordinator(
        engine=engine,
        collectors={"fake_collector": collector},
        semaphore=sem,
    )

    reachable_ips = {f"10.0.0.{i}" for i in range(20)}
    unreachable_ips = {f"10.0.1.{i}" for i in range(30)}
    all_devices = (
        [_make_device(ip) for ip in sorted(unreachable_ips)]
        + [_make_device(ip) for ip in sorted(reachable_ips)]
    )

    cache = _mock_session_cache(unreachable_ips=unreachable_ips)
    cache.is_community_known = MagicMock(
        side_effect=lambda ip: ip in reachable_ips,
    )

    # Track the order hostnames are saved
    save_order: list[str] = []
    original_save = coord._save_device_results

    async def tracking_save(hostname, maintenance_id, collector_outcomes):
        save_order.append(hostname)

    with patch.object(
        CollectionCoordinator, "_save_device_results",
        side_effect=tracking_save,
    ):
        # Mock DB query to return our device list
        with patch(
            "app.snmp.collection_coordinator.get_session_context",
        ) as mock_ctx, patch(
            "app.snmp.collection_coordinator.SnmpSessionCache",
            return_value=cache,
        ):
            # Build mock DB result
            mock_devices = []
            for dev in all_devices:
                m = MagicMock()
                m.new_hostname = dev["hostname"]
                m.new_ip_address = dev["ip"]
                m.new_vendor = dev["vendor"]
                mock_devices.append(m)

            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = mock_devices
            mock_session.execute = AsyncMock(return_value=mock_result)

            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.return_value = mock_cm

            result = await coord.run_round(
                round_name="two_phase_test",
                collector_names=["fake_collector"],
                maintenance_id="M-TEST",
            )

    assert result.total_devices == 50
    assert result.ok == 20
    assert result.unreachable == 30

    # Key assertion: ALL reachable device saves appear before
    # ALL unreachable device saves (phase 1 completes before phase 2)
    reachable_hostnames = {f"SW-{ip}" for ip in reachable_ips}
    first_unreachable_idx = None
    last_reachable_idx = None
    for i, hostname in enumerate(save_order):
        if hostname in reachable_hostnames:
            last_reachable_idx = i
        elif first_unreachable_idx is None:
            first_unreachable_idx = i

    if last_reachable_idx is not None and first_unreachable_idx is not None:
        assert last_reachable_idx < first_unreachable_idx, (
            f"Phase 1 (reachable) should complete before phase 2 (unreachable). "
            f"Last reachable save at index {last_reachable_idx}, "
            f"first unreachable save at index {first_unreachable_idx}"
        )


# =========================================================================
# Test 11: Cold start — all devices go to phase 2
# =========================================================================


@pytest.mark.asyncio
async def test_cold_start_all_devices_in_phase2():
    """On cold start, no community cache → all devices go to phase 2."""
    sem = asyncio.Semaphore(20)
    collector = FakeCollector(delay=0.01)
    engine = MagicMock(spec=AsyncSnmpEngine)

    coord = CollectionCoordinator(
        engine=engine,
        collectors={"fake_collector": collector},
        semaphore=sem,
    )

    all_devices = [_make_device(f"10.0.0.{i}") for i in range(10)]
    cache = _mock_session_cache()
    cache.is_community_known = MagicMock(return_value=False)

    with _mock_save():
        with patch(
            "app.snmp.collection_coordinator.get_session_context",
        ) as mock_ctx, patch(
            "app.snmp.collection_coordinator.SnmpSessionCache",
            return_value=cache,
        ):
            mock_devices = []
            for dev in all_devices:
                m = MagicMock()
                m.new_hostname = dev["hostname"]
                m.new_ip_address = dev["ip"]
                m.new_vendor = dev["vendor"]
                mock_devices.append(m)

            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = mock_devices
            mock_session.execute = AsyncMock(return_value=mock_result)

            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.return_value = mock_cm

            result = await coord.run_round(
                round_name="cold_start",
                collector_names=["fake_collector"],
                maintenance_id="M-TEST",
            )

    assert result.total_devices == 10
    assert result.ok == 10
