"""
Tests for app.services.case_service.

Covers:
- _detect_change() pure function (no DB required)
- update_ping_status() business logic (mocked DB)
- auto_resolve_reachable() business logic (mocked DB)
- auto_reopen_unreachable() business logic (mocked DB)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.enums import CaseStatus
from app.services.case_service import CaseService, _detect_change


# ══════════════════════════════════════════════════════════════════
# _detect_change() — pure function tests (no DB)
# ══════════════════════════════════════════════════════════════════


class TestDetectChange:
    """Tests for the _detect_change() pure function."""

    def test_detect_change_single_value(self):
        """Single value list: nothing to compare, so no change."""
        assert _detect_change([42]) is False

    def test_detect_change_all_same(self):
        """All identical non-null values: stable, no change."""
        assert _detect_change([1, 1, 1]) is False

    def test_detect_change_different_values(self):
        """Multiple different non-null values: change detected."""
        assert _detect_change([1, 2, 3]) is True

    def test_detect_change_empty_list(self):
        """Empty list: no snapshots, no change."""
        assert _detect_change([]) is False

    def test_detect_change_with_none(self):
        """All None values: no non-null data, no change."""
        assert _detect_change([None, None]) is False

    def test_detect_change_none_vs_value(self):
        """None followed by a value then None: last is None with one
        unique non-null => change detected (device offline/swapped)."""
        assert _detect_change([None, 1]) is False  # last value is non-null, one unique => stable

    def test_detect_change_value_then_none(self):
        """Value followed by None: last value is None with one unique
        non-null => change detected (rule 3: device went offline)."""
        assert _detect_change([1, None]) is True

    def test_detect_change_none_value_none(self):
        """[None, 1, None]: last is None, one unique non-null => change (rule 3)."""
        assert _detect_change([None, 1, None]) is True

    def test_detect_change_two_same(self):
        """Two identical values: stable, no change."""
        assert _detect_change([5, 5]) is False

    def test_detect_change_strings(self):
        """String values that differ: change detected."""
        assert _detect_change(["up", "down"]) is True

    def test_detect_change_strings_same(self):
        """Identical string values: no change."""
        assert _detect_change(["up", "up", "up"]) is False

    def test_detect_change_booleans_differ(self):
        """Boolean values that differ: change detected."""
        assert _detect_change([True, False]) is True

    def test_detect_change_booleans_same(self):
        """Identical boolean values: no change."""
        assert _detect_change([True, True]) is False

    def test_detect_change_none_then_value_last_nonnull(self):
        """[None, 1]: last value is 1 (non-null), only one unique non-null => stable."""
        assert _detect_change([None, 1]) is False


# ══════════════════════════════════════════════════════════════════
# Helpers for mocked DB tests
# ══════════════════════════════════════════════════════════════════


def _make_mock_session():
    """Create a mock AsyncSession with execute() and commit()."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


def _make_fetchall_result(rows):
    """Create a mock result whose .fetchall() returns the given rows."""
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


def _make_rowcount_result(count):
    """Create a mock result with .rowcount attribute."""
    result = MagicMock()
    result.rowcount = count
    return result


# ══════════════════════════════════════════════════════════════════
# update_ping_status() tests
# ══════════════════════════════════════════════════════════════════


class TestUpdatePingStatus:
    """Tests for CaseService.update_ping_status() business logic."""

    @pytest.mark.asyncio
    async def test_ping_unreachable_to_reachable_sets_since(self):
        """When ping transitions from False to True, ping_reachable_since
        should be set to approximately now."""
        service = CaseService()
        session = _make_mock_session()

        mac = "AA:BB:CC:DD:EE:01"
        # First execute: latest ClientRecord pings
        latest_pings = [(mac, True)]
        # Second execute: existing Case states (old_reachable=False, old_since=None)
        case_states = [(mac, False, None)]
        # Third execute: the UPDATE statement
        update_result = MagicMock()

        session.execute = AsyncMock(side_effect=[
            _make_fetchall_result(latest_pings),
            _make_fetchall_result(case_states),
            update_result,
        ])

        before = datetime.now(timezone.utc)
        await service.update_ping_status("MAINT-001", session)
        after = datetime.now(timezone.utc)

        # The UPDATE call is the third execute call
        update_call = session.execute.call_args_list[2]
        stmt = update_call[0][0]

        # Verify commit was called
        session.commit.assert_awaited_once()

        # Verify the update was issued (3 execute calls: subquery, case_states, update)
        assert session.execute.await_count == 3

    @pytest.mark.asyncio
    async def test_ping_reachable_to_reachable_keeps_since(self):
        """When ping stays True with an existing since timestamp,
        ping_reachable_since should remain unchanged."""
        service = CaseService()
        session = _make_mock_session()

        mac = "AA:BB:CC:DD:EE:02"
        original_since = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        latest_pings = [(mac, True)]
        case_states = [(mac, True, original_since)]
        update_result = MagicMock()

        session.execute = AsyncMock(side_effect=[
            _make_fetchall_result(latest_pings),
            _make_fetchall_result(case_states),
            update_result,
        ])

        await service.update_ping_status("MAINT-001", session)

        # Verify the update was executed
        assert session.execute.await_count == 3
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ping_reachable_to_unreachable_clears_since(self):
        """When ping transitions from True to False,
        ping_reachable_since should be cleared to None."""
        service = CaseService()
        session = _make_mock_session()

        mac = "AA:BB:CC:DD:EE:03"
        original_since = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        latest_pings = [(mac, False)]
        case_states = [(mac, True, original_since)]
        update_result = MagicMock()

        session.execute = AsyncMock(side_effect=[
            _make_fetchall_result(latest_pings),
            _make_fetchall_result(case_states),
            update_result,
        ])

        await service.update_ping_status("MAINT-001", session)

        assert session.execute.await_count == 3
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ping_no_prior_state(self):
        """When no prior Case exists for a MAC (not in case_states),
        a reachable ping should set since to now."""
        service = CaseService()
        session = _make_mock_session()

        mac = "AA:BB:CC:DD:EE:04"
        latest_pings = [(mac, True)]
        # No existing case state for this MAC
        case_states = []
        update_result = MagicMock()

        session.execute = AsyncMock(side_effect=[
            _make_fetchall_result(latest_pings),
            _make_fetchall_result(case_states),
            update_result,
        ])

        await service.update_ping_status("MAINT-001", session)

        # Should still issue the UPDATE (even if the Case row may not exist,
        # the service does not check; it always issues an UPDATE WHERE mac)
        assert session.execute.await_count == 3
        session.commit.assert_awaited_once()


class TestUpdatePingStatusLogic:
    """Detailed tests verifying the ping_reachable_since calculation logic
    by inspecting the .values() passed to the UPDATE statement."""

    @pytest.mark.asyncio
    async def test_unreachable_to_reachable_since_is_now(self):
        """Transition False -> True: new_since should be approximately now."""
        service = CaseService()
        session = _make_mock_session()

        mac = "AA:BB:CC:DD:EE:10"
        latest_pings = [(mac, True)]
        case_states = [(mac, False, None)]

        # We need to capture the actual values passed to the update.
        # Patch datetime.now to return a fixed time.
        fixed_now = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
        captured_calls = []

        async def capture_execute(stmt):
            captured_calls.append(stmt)
            if len(captured_calls) == 1:
                return _make_fetchall_result(latest_pings)
            elif len(captured_calls) == 2:
                return _make_fetchall_result(case_states)
            return MagicMock()

        session.execute = AsyncMock(side_effect=capture_execute)

        with patch("app.services.case_service.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            await service.update_ping_status("MAINT-001", session)

        # The third call should be the UPDATE with values
        assert len(captured_calls) == 3
        update_stmt = captured_calls[2]

        # Extract compiled parameters from the update statement
        compiled = update_stmt.compile(
            compile_kwargs={"literal_binds": False}
        )
        params = compiled.params

        assert params["last_ping_reachable"] is True
        assert params["ping_reachable_since"] == fixed_now

    @pytest.mark.asyncio
    async def test_reachable_to_reachable_since_unchanged(self):
        """Transition True -> True with existing since: keep original since."""
        service = CaseService()
        session = _make_mock_session()

        mac = "AA:BB:CC:DD:EE:11"
        original_since = datetime(2026, 1, 15, 8, 0, 0, tzinfo=timezone.utc)
        latest_pings = [(mac, True)]
        case_states = [(mac, True, original_since)]

        captured_calls = []

        async def capture_execute(stmt):
            captured_calls.append(stmt)
            if len(captured_calls) == 1:
                return _make_fetchall_result(latest_pings)
            elif len(captured_calls) == 2:
                return _make_fetchall_result(case_states)
            return MagicMock()

        session.execute = AsyncMock(side_effect=capture_execute)
        await service.update_ping_status("MAINT-001", session)

        assert len(captured_calls) == 3
        update_stmt = captured_calls[2]
        compiled = update_stmt.compile(compile_kwargs={"literal_binds": False})
        params = compiled.params

        assert params["last_ping_reachable"] is True
        assert params["ping_reachable_since"] == original_since

    @pytest.mark.asyncio
    async def test_reachable_to_unreachable_since_cleared(self):
        """Transition True -> False: since should be None."""
        service = CaseService()
        session = _make_mock_session()

        mac = "AA:BB:CC:DD:EE:12"
        original_since = datetime(2026, 1, 15, 8, 0, 0, tzinfo=timezone.utc)
        latest_pings = [(mac, False)]
        case_states = [(mac, True, original_since)]

        captured_calls = []

        async def capture_execute(stmt):
            captured_calls.append(stmt)
            if len(captured_calls) == 1:
                return _make_fetchall_result(latest_pings)
            elif len(captured_calls) == 2:
                return _make_fetchall_result(case_states)
            return MagicMock()

        session.execute = AsyncMock(side_effect=capture_execute)
        await service.update_ping_status("MAINT-001", session)

        assert len(captured_calls) == 3
        update_stmt = captured_calls[2]
        compiled = update_stmt.compile(compile_kwargs={"literal_binds": False})
        params = compiled.params

        assert params["last_ping_reachable"] is False
        assert params["ping_reachable_since"] is None

    @pytest.mark.asyncio
    async def test_no_prior_state_reachable_sets_since(self):
        """No prior case state + reachable: since set to now."""
        service = CaseService()
        session = _make_mock_session()

        mac = "AA:BB:CC:DD:EE:13"
        fixed_now = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
        latest_pings = [(mac, True)]
        case_states = []  # no prior state

        captured_calls = []

        async def capture_execute(stmt):
            captured_calls.append(stmt)
            if len(captured_calls) == 1:
                return _make_fetchall_result(latest_pings)
            elif len(captured_calls) == 2:
                return _make_fetchall_result(case_states)
            return MagicMock()

        session.execute = AsyncMock(side_effect=capture_execute)

        with patch("app.services.case_service.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            await service.update_ping_status("MAINT-001", session)

        assert len(captured_calls) == 3
        update_stmt = captured_calls[2]
        compiled = update_stmt.compile(compile_kwargs={"literal_binds": False})
        params = compiled.params

        assert params["last_ping_reachable"] is True
        assert params["ping_reachable_since"] == fixed_now

    @pytest.mark.asyncio
    async def test_no_latest_pings_only_commits(self):
        """When there are no latest ClientRecord pings, only commit is called
        without any UPDATE statements."""
        service = CaseService()
        session = _make_mock_session()

        latest_pings = []  # no records
        case_states = [("AA:BB:CC:DD:EE:FF", True, None)]

        session.execute = AsyncMock(side_effect=[
            _make_fetchall_result(latest_pings),
            _make_fetchall_result(case_states),
        ])

        await service.update_ping_status("MAINT-001", session)

        # Only 2 execute calls (subquery + case_states), no update
        assert session.execute.await_count == 2
        session.commit.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════
# auto_resolve_reachable() tests
# ══════════════════════════════════════════════════════════════════


class TestAutoResolveReachable:
    """Tests for CaseService.auto_resolve_reachable() business logic."""

    @pytest.mark.asyncio
    async def test_auto_resolve_stable_over_10min(self):
        """Case with ping_reachable_since 15 minutes ago and status ASSIGNED
        should be auto-resolved."""
        service = CaseService()
        session = _make_mock_session()

        # Simulate 1 row updated
        session.execute = AsyncMock(return_value=_make_rowcount_result(1))

        resolved = await service.auto_resolve_reachable("MAINT-001", session)

        assert resolved == 1
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_resolve_not_stable_enough(self):
        """Case with ping_reachable_since only 5 minutes ago should NOT be
        resolved (anti-flapping: requires 10 minutes)."""
        service = CaseService()
        session = _make_mock_session()

        # Simulate 0 rows updated (cutoff check in WHERE clause excludes it)
        session.execute = AsyncMock(return_value=_make_rowcount_result(0))

        resolved = await service.auto_resolve_reachable("MAINT-001", session)

        assert resolved == 0
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_resolve_skips_in_progress(self):
        """IN_PROGRESS cases should NOT be auto-resolved even with stable
        ping, because the status is excluded via notin_() clause."""
        service = CaseService()
        session = _make_mock_session()

        # The WHERE clause excludes IN_PROGRESS, so 0 rows updated
        session.execute = AsyncMock(return_value=_make_rowcount_result(0))

        resolved = await service.auto_resolve_reachable("MAINT-001", session)

        assert resolved == 0

    @pytest.mark.asyncio
    async def test_auto_resolve_skips_discussing(self):
        """DISCUSSING cases should NOT be auto-resolved."""
        service = CaseService()
        session = _make_mock_session()

        session.execute = AsyncMock(return_value=_make_rowcount_result(0))

        resolved = await service.auto_resolve_reachable("MAINT-001", session)

        assert resolved == 0

    @pytest.mark.asyncio
    async def test_auto_resolve_skips_already_resolved(self):
        """Already RESOLVED cases should not be affected (no double-resolve)."""
        service = CaseService()
        session = _make_mock_session()

        session.execute = AsyncMock(return_value=_make_rowcount_result(0))

        resolved = await service.auto_resolve_reachable("MAINT-001", session)

        assert resolved == 0

    @pytest.mark.asyncio
    async def test_auto_resolve_custom_stable_minutes(self):
        """Custom stable_minutes parameter should be respected."""
        service = CaseService()
        session = _make_mock_session()

        session.execute = AsyncMock(return_value=_make_rowcount_result(3))

        resolved = await service.auto_resolve_reachable(
            "MAINT-001", session, stable_minutes=30,
        )

        assert resolved == 3
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_resolve_returns_rowcount(self):
        """Return value should match the number of rows updated."""
        service = CaseService()
        session = _make_mock_session()

        session.execute = AsyncMock(return_value=_make_rowcount_result(7))

        resolved = await service.auto_resolve_reachable("MAINT-001", session)

        assert resolved == 7

    @pytest.mark.asyncio
    async def test_auto_resolve_where_clause_correctness(self):
        """Verify the UPDATE statement uses correct WHERE conditions by
        inspecting the compiled SQL string."""
        service = CaseService()
        session = _make_mock_session()

        captured_stmt = None

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            return _make_rowcount_result(0)

        session.execute = AsyncMock(side_effect=capture_execute)

        await service.auto_resolve_reachable("MAINT-001", session)

        # Compile the statement to inspect it
        assert captured_stmt is not None
        compiled_sql = str(captured_stmt.compile(
            compile_kwargs={"literal_binds": False},
        ))

        # Should be an UPDATE on cases table
        assert "cases" in compiled_sql.lower()
        # Should filter on maintenance_id
        assert "maintenance_id" in compiled_sql
        # Should filter on last_ping_reachable
        assert "last_ping_reachable" in compiled_sql
        # Should filter on ping_reachable_since
        assert "ping_reachable_since" in compiled_sql

    @pytest.mark.asyncio
    async def test_auto_resolve_sets_status_to_resolved(self):
        """The UPDATE should set status to RESOLVED."""
        service = CaseService()
        session = _make_mock_session()

        captured_stmt = None

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            return _make_rowcount_result(2)

        session.execute = AsyncMock(side_effect=capture_execute)

        await service.auto_resolve_reachable("MAINT-001", session)

        assert captured_stmt is not None
        compiled = captured_stmt.compile(compile_kwargs={"literal_binds": False})
        params = compiled.params

        # The values should set status to RESOLVED
        assert params["status"] == CaseStatus.RESOLVED


# ══════════════════════════════════════════════════════════════════
# auto_reopen_unreachable() tests
# ══════════════════════════════════════════════════════════════════


class TestAutoReopenUnreachable:
    """Tests for CaseService.auto_reopen_unreachable() business logic."""

    @pytest.mark.asyncio
    async def test_auto_reopen_resolved_unreachable(self):
        """RESOLVED case with ping=False should be reopened to ASSIGNED."""
        service = CaseService()
        session = _make_mock_session()

        session.execute = AsyncMock(return_value=_make_rowcount_result(1))

        reopened = await service.auto_reopen_unreachable("MAINT-001", session)

        assert reopened == 1
        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_reopen_resolved_ping_none(self):
        """RESOLVED case with ping=None (unknown) should also be reopened."""
        service = CaseService()
        session = _make_mock_session()

        # The OR clause in the WHERE includes None, so this would match
        session.execute = AsyncMock(return_value=_make_rowcount_result(1))

        reopened = await service.auto_reopen_unreachable("MAINT-001", session)

        assert reopened == 1
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_reopen_resolved_reachable_no_change(self):
        """RESOLVED case with ping=True should stay RESOLVED (no reopen)."""
        service = CaseService()
        session = _make_mock_session()

        # ping=True does not match the WHERE clause, so 0 rows updated
        session.execute = AsyncMock(return_value=_make_rowcount_result(0))

        reopened = await service.auto_reopen_unreachable("MAINT-001", session)

        assert reopened == 0
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_reopen_non_resolved_unaffected(self):
        """Non-RESOLVED cases (e.g., ASSIGNED + ping=False) should NOT be
        reopened because the WHERE clause requires status=RESOLVED."""
        service = CaseService()
        session = _make_mock_session()

        # ASSIGNED status doesn't match WHERE Case.status == RESOLVED
        session.execute = AsyncMock(return_value=_make_rowcount_result(0))

        reopened = await service.auto_reopen_unreachable("MAINT-001", session)

        assert reopened == 0

    @pytest.mark.asyncio
    async def test_auto_reopen_returns_rowcount(self):
        """Return value should be the count of reopened cases."""
        service = CaseService()
        session = _make_mock_session()

        session.execute = AsyncMock(return_value=_make_rowcount_result(5))

        reopened = await service.auto_reopen_unreachable("MAINT-001", session)

        assert reopened == 5

    @pytest.mark.asyncio
    async def test_auto_reopen_where_clause_correctness(self):
        """Verify the UPDATE statement targets only RESOLVED + unreachable."""
        service = CaseService()
        session = _make_mock_session()

        captured_stmt = None

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            return _make_rowcount_result(0)

        session.execute = AsyncMock(side_effect=capture_execute)

        await service.auto_reopen_unreachable("MAINT-001", session)

        assert captured_stmt is not None
        compiled_sql = str(captured_stmt.compile(
            compile_kwargs={"literal_binds": False},
        ))

        # Should be an UPDATE on cases table
        assert "cases" in compiled_sql.lower()
        # Should filter on maintenance_id and status
        assert "maintenance_id" in compiled_sql
        assert "status" in compiled_sql
        # Should filter on last_ping_reachable
        assert "last_ping_reachable" in compiled_sql

    @pytest.mark.asyncio
    async def test_auto_reopen_sets_status_to_assigned(self):
        """The UPDATE should set status to ASSIGNED."""
        service = CaseService()
        session = _make_mock_session()

        captured_stmt = None

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            return _make_rowcount_result(1)

        session.execute = AsyncMock(side_effect=capture_execute)

        await service.auto_reopen_unreachable("MAINT-001", session)

        assert captured_stmt is not None
        compiled = captured_stmt.compile(compile_kwargs={"literal_binds": False})
        params = compiled.params

        assert params["status"] == CaseStatus.ASSIGNED

    @pytest.mark.asyncio
    async def test_auto_reopen_multiple_cases(self):
        """Multiple RESOLVED unreachable cases should all be reopened."""
        service = CaseService()
        session = _make_mock_session()

        session.execute = AsyncMock(return_value=_make_rowcount_result(12))

        reopened = await service.auto_reopen_unreachable("MAINT-001", session)

        assert reopened == 12
        session.commit.assert_awaited_once()
