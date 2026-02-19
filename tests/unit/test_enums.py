"""Tests for app.core.enums."""
from app.core.enums import (
    AggregationProtocol,
    CaseStatus,
    ClientDetectionStatus,
    DeviceType,
    DuplexMode,
    LinkStatus,
    OperationalStatus,
    UserRole,
)


class TestDeviceType:
    def test_values(self):
        assert DeviceType.HPE.value == "HPE"
        assert DeviceType.CISCO_IOS.value == "Cisco-IOS"
        assert DeviceType.CISCO_NXOS.value == "Cisco-NXOS"

    def test_api_value(self):
        assert DeviceType.HPE.api_value == "hpe"
        assert DeviceType.CISCO_IOS.api_value == "ios"
        assert DeviceType.CISCO_NXOS.api_value == "nxos"

    def test_string_enum(self):
        assert isinstance(DeviceType.HPE, str)
        assert DeviceType("HPE") == DeviceType.HPE


class TestOperationalStatus:
    def test_healthy_statuses(self):
        for s in ("ok", "good", "normal", "online", "active"):
            assert OperationalStatus(s) is not None

    def test_unhealthy_statuses(self):
        assert OperationalStatus.FAIL.value == "fail"
        assert OperationalStatus.ABSENT.value == "absent"
        assert OperationalStatus.UNKNOWN.value == "unknown"


class TestLinkStatus:
    def test_values(self):
        assert LinkStatus.UP.value == "up"
        assert LinkStatus.DOWN.value == "down"
        assert LinkStatus.UNKNOWN.value == "unknown"


class TestDuplexMode:
    def test_values(self):
        assert DuplexMode.FULL.value == "full"
        assert DuplexMode.HALF.value == "half"
        assert DuplexMode.AUTO.value == "auto"
        assert DuplexMode.UNKNOWN.value == "unknown"


class TestAggregationProtocol:
    def test_values(self):
        assert AggregationProtocol.LACP.value == "lacp"
        assert AggregationProtocol.STATIC.value == "static"
        assert AggregationProtocol.PAGP.value == "pagp"
        assert AggregationProtocol.NONE.value == "none"


class TestUserRole:
    def test_values(self):
        assert UserRole.ROOT.value == "ROOT"
        assert UserRole.PM.value == "PM"
        assert UserRole.GUEST.value == "GUEST"


class TestCaseStatus:
    def test_all_values(self):
        assert len(CaseStatus) == 5
        expected = {"UNASSIGNED", "ASSIGNED", "IN_PROGRESS", "DISCUSSING", "RESOLVED"}
        assert {s.value for s in CaseStatus} == expected


class TestClientDetectionStatus:
    def test_all_values(self):
        assert len(ClientDetectionStatus) == 4
        expected = {"NOT_CHECKED", "DETECTED", "MISMATCH", "NOT_DETECTED"}
        assert {s.value for s in ClientDetectionStatus} == expected
