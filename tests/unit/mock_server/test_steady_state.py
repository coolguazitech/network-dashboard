"""Tests for mock_server.steady_state — deterministic failure logic."""

from mock_server.steady_state import _deterministic_float, should_fail_steady


class TestDeterministicFloat:
    """Tests for the _deterministic_float() helper."""

    def test_same_inputs_same_output(self):
        """Identical inputs must always produce the same float."""
        a = _deterministic_float("10.0.0.1", "get_fan")
        b = _deterministic_float("10.0.0.1", "get_fan")
        assert a == b

    def test_same_inputs_same_output_with_salt(self):
        """Salt is part of the key; same salt must reproduce the same value."""
        a = _deterministic_float("10.0.0.1", "get_fan", salt="onset")
        b = _deterministic_float("10.0.0.1", "get_fan", salt="onset")
        assert a == b

    def test_different_ip_different_output(self):
        """Different IPs should (almost certainly) produce different values."""
        a = _deterministic_float("10.0.0.1", "get_fan")
        b = _deterministic_float("10.0.0.2", "get_fan")
        assert a != b

    def test_different_api_different_output(self):
        """Different API names should produce different values."""
        a = _deterministic_float("10.0.0.1", "get_fan")
        b = _deterministic_float("10.0.0.1", "get_version")
        assert a != b

    def test_different_salt_different_output(self):
        """Different salt values should produce different values."""
        a = _deterministic_float("10.0.0.1", "get_fan", salt="")
        b = _deterministic_float("10.0.0.1", "get_fan", salt="onset")
        assert a != b

    def test_output_range(self):
        """Return value must be in [0, 1)."""
        ips = [f"10.0.0.{i}" for i in range(256)]
        apis = ["get_fan", "get_version", "get_power", "get_mac"]
        for ip in ips:
            for api in apis:
                v = _deterministic_float(ip, api)
                assert 0.0 <= v < 1.0, f"Out of range for {ip}:{api} -> {v}"

    def test_granularity(self):
        """Values should have at most 4 decimal digits (mod 10000)."""
        v = _deterministic_float("10.0.0.1", "get_fan")
        assert v == round(v, 4)


class TestShouldFailSteady:
    """Tests for the should_fail_steady() function."""

    # --- Failure rate controls proportion --------------------------------

    def test_zero_failure_rate_never_fails(self):
        """With failure_rate=0.0, no combo should ever fail."""
        for i in range(200):
            result = should_fail_steady(
                f"10.0.{i // 256}.{i % 256}",
                "get_fan",
                active_seconds=99999.0,
                failure_rate=0.0,
            )
            assert result is False

    def test_full_failure_rate_always_fails(self):
        """With failure_rate=1.0 and enough elapsed time, every combo fails."""
        for i in range(200):
            result = should_fail_steady(
                f"10.0.{i // 256}.{i % 256}",
                "get_fan",
                active_seconds=99999.0,
                failure_rate=1.0,
                onset_range=3600.0,
            )
            assert result is True

    def test_failure_rate_approximate_proportion(self):
        """The proportion of failing combos should approximate the rate."""
        n = 2000
        failures = 0
        rate = 0.10
        for i in range(n):
            ip = f"172.16.{i // 256}.{i % 256}"
            if should_fail_steady(
                ip,
                "get_fan",
                active_seconds=999999.0,
                failure_rate=rate,
                onset_range=1.0,
            ):
                failures += 1
        actual_rate = failures / n
        # Allow generous tolerance for hash-based distribution
        assert 0.05 <= actual_rate <= 0.18, (
            f"Expected ~{rate}, got {actual_rate}"
        )

    # --- Deterministic behavior ------------------------------------------

    def test_deterministic_result(self):
        """Same arguments must always return the same boolean."""
        args = ("10.0.0.5", "get_version", 1800.0, 0.10, 3600.0)
        results = [should_fail_steady(*args) for _ in range(50)]
        assert len(set(results)) == 1

    # --- Onset range timing ----------------------------------------------

    def test_before_onset_no_failure(self):
        """A combo destined to fail should NOT fail before its onset time."""
        # Find a combo that will fail (p < failure_rate with rate=1.0)
        ip, api = "10.0.0.1", "get_fan"
        # With rate=1.0 this combo is selected to fail
        assert should_fail_steady(
            ip, api, active_seconds=999999.0, failure_rate=1.0
        )
        # At active_seconds=0, onset = deterministic * onset_range.
        # If onset > 0, then active_seconds=0 should NOT trigger failure.
        onset_val = _deterministic_float(ip, api, "onset")
        onset_range = 3600.0
        onset_time = onset_val * onset_range
        if onset_time > 0:
            assert should_fail_steady(
                ip, api, active_seconds=0.0, failure_rate=1.0,
                onset_range=onset_range,
            ) is False

    def test_after_onset_failure(self):
        """A combo destined to fail SHOULD fail after its onset time."""
        ip, api = "10.0.0.1", "get_fan"
        onset_val = _deterministic_float(ip, api, "onset")
        onset_range = 3600.0
        onset_time = onset_val * onset_range
        # Just past the onset time
        assert should_fail_steady(
            ip, api, active_seconds=onset_time + 1.0,
            failure_rate=1.0, onset_range=onset_range,
        ) is True

    def test_exactly_at_onset_fails(self):
        """At exactly the onset second, active_seconds >= onset is True."""
        ip, api = "10.0.0.1", "get_fan"
        onset_val = _deterministic_float(ip, api, "onset")
        onset_range = 3600.0
        onset_time = onset_val * onset_range
        assert should_fail_steady(
            ip, api, active_seconds=onset_time,
            failure_rate=1.0, onset_range=onset_range,
        ) is True

    def test_zero_onset_range_immediate_failure(self):
        """With onset_range=0, failures appear immediately (onset = 0)."""
        # Every selected combo fails at active_seconds=0
        failures = 0
        n = 200
        for i in range(n):
            if should_fail_steady(
                f"10.0.{i // 256}.{i % 256}",
                "get_fan",
                active_seconds=0.0,
                failure_rate=1.0,
                onset_range=0.0,
            ):
                failures += 1
        assert failures == n

    # --- Onset staggering ------------------------------------------------

    def test_failures_stagger_over_time(self):
        """Not all failures appear at the same moment within onset_range."""
        rate = 1.0
        onset_range = 3600.0
        # Collect onset fractions for many combos
        onset_fractions = set()
        for i in range(100):
            ip = f"192.168.1.{i}"
            frac = _deterministic_float(ip, "get_fan", "onset")
            onset_fractions.add(frac)
        # With 100 different IPs, we should see many distinct onset fractions
        assert len(onset_fractions) > 20, (
            "Expected staggered onset times across combos"
        )

    # --- Non-failing combo ------------------------------------------------

    def test_non_failing_combo_stays_healthy(self):
        """A combo with p >= failure_rate never fails regardless of time."""
        # Find a combo that does NOT fail at rate=0.05
        non_failing_ip = None
        for i in range(256):
            ip = f"10.10.0.{i}"
            p = _deterministic_float(ip, "get_fan")
            if p >= 0.05:
                non_failing_ip = ip
                break
        assert non_failing_ip is not None
        # Should remain healthy at any time
        for t in [0.0, 100.0, 3600.0, 999999.0]:
            assert should_fail_steady(
                non_failing_ip, "get_fan", active_seconds=t,
                failure_rate=0.05,
            ) is False
