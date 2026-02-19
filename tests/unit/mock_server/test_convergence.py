"""Tests for mock_server.convergence."""
from mock_server.convergence import (
    exponential_decay_failure_rate,
    get_converging_variance,
    should_device_fail,
    should_fail,
)


class TestShouldDeviceFail:
    """Test the device convergence behavior."""

    def test_none_is_old_always_reachable(self):
        """is_old=None means device role unknown → always reachable."""
        assert should_device_fail(None, 0, 600) is False
        assert should_device_fail(None, 300, 600) is False
        assert should_device_fail(None, 600, 600) is False

    def test_old_device_before_switch(self):
        """Old device: reachable before switch point."""
        assert should_device_fail(True, 0, 600) is False
        assert should_device_fail(True, 299, 600) is False

    def test_old_device_after_switch(self):
        """Old device: unreachable after switch point (converge_time/2)."""
        assert should_device_fail(True, 300, 600) is True
        assert should_device_fail(True, 600, 600) is True

    def test_new_device_before_switch(self):
        """New device: unreachable before switch point."""
        assert should_device_fail(False, 0, 600) is True
        assert should_device_fail(False, 299, 600) is True

    def test_new_device_after_switch(self):
        """New device: reachable after switch point."""
        assert should_device_fail(False, 300, 600) is False
        assert should_device_fail(False, 600, 600) is False

    def test_zero_converge_time_old(self):
        """converge_time=0: old device always fails."""
        assert should_device_fail(True, 0, 0) is True

    def test_zero_converge_time_new(self):
        """converge_time=0: new device never fails."""
        assert should_device_fail(False, 0, 0) is False


class TestExponentialDecayFailureRate:
    def test_initial_rate(self):
        """At t=0, rate equals initial_failure_rate."""
        rate = exponential_decay_failure_rate(0, 600, 1.0, 0.0)
        assert abs(rate - 1.0) < 0.01

    def test_converged_rate(self):
        """At t=2T, rate equals target_failure_rate."""
        rate = exponential_decay_failure_rate(1200, 600, 1.0, 0.0)
        assert abs(rate - 0.0) < 0.01

    def test_midpoint(self):
        """At t=T, rate is ~95% converged (≈0.05 for 1.0→0.0)."""
        rate = exponential_decay_failure_rate(600, 600, 1.0, 0.0)
        assert rate < 0.10  # Should be approximately 0.05

    def test_zero_converge_time(self):
        """converge_time=0 returns target immediately."""
        rate = exponential_decay_failure_rate(0, 0, 1.0, 0.05)
        assert rate == 0.05


class TestShouldFail:
    def test_always_fail_when_rate_1(self):
        """With 100% failure rate, should always fail."""
        # Test multiple times for statistical confidence
        results = [should_fail(0, 600, 1.0, 1.0) for _ in range(10)]
        assert all(results)

    def test_never_fail_when_rate_0(self):
        """With 0% failure rate, should never fail."""
        results = [should_fail(1200, 600, 0.0, 0.0) for _ in range(10)]
        assert not any(results)


class TestGetConvergingVariance:
    def test_initial(self):
        v = get_converging_variance(0, 600, 10.0, 1.0)
        assert abs(v - 10.0) < 0.1

    def test_converged(self):
        v = get_converging_variance(1200, 600, 10.0, 1.0)
        assert abs(v - 1.0) < 0.01

    def test_zero_converge_time(self):
        v = get_converging_variance(0, 0, 10.0, 1.0)
        assert v == 1.0
