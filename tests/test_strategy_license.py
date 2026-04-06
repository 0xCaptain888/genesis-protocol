"""Tests for StrategyLicense concepts - Python-side validation of license types,
lease validity, revenue splits, and expiry logic.

These tests model the StrategyLicense.sol contract behavior in Python to validate
the protocol's economic invariants without requiring an on-chain deployment.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import time
from dataclasses import dataclass
from enum import IntEnum

import skills.genesis.scripts.config as config


# ── Python Model of StrategyLicense.sol ──────────────────────────────────────

BPS = 10000


class LicenseType(IntEnum):
    TIME_BASED = 0
    USAGE_BASED = 1
    PERPETUAL = 2


@dataclass
class License:
    price_per_period: int       # cost in wei per lease
    period_seconds: int         # duration (TIME_BASED) or max swaps (USAGE_BASED)
    license_type: LicenseType
    active: bool = True
    total_leases: int = 0
    total_revenue: int = 0


@dataclass
class LeaseRecord:
    start_time: int
    end_time: int           # 0 for PERPETUAL and USAGE_BASED
    swaps_used: int = 0
    max_swaps: int = 0      # 0 for TIME_BASED and PERPETUAL
    active: bool = True


def create_lease(lic: License, now: int) -> LeaseRecord:
    """Simulate the lease() function from StrategyLicense.sol."""
    if lic.license_type == LicenseType.TIME_BASED:
        return LeaseRecord(
            start_time=now,
            end_time=now + lic.period_seconds,
            swaps_used=0,
            max_swaps=0,
            active=True,
        )
    elif lic.license_type == LicenseType.USAGE_BASED:
        return LeaseRecord(
            start_time=now,
            end_time=0,
            swaps_used=0,
            max_swaps=lic.period_seconds,   # periodSeconds repurposed as maxSwaps
            active=True,
        )
    else:  # PERPETUAL
        return LeaseRecord(
            start_time=now,
            end_time=0,
            swaps_used=0,
            max_swaps=0,
            active=True,
        )


def check_lease_valid(lic: License, record: LeaseRecord, now: int) -> bool:
    """Simulate checkLeaseValid from StrategyLicense.sol."""
    if not record.active:
        return False
    if lic.license_type == LicenseType.TIME_BASED:
        return now <= record.end_time
    elif lic.license_type == LicenseType.USAGE_BASED:
        return record.swaps_used < record.max_swaps
    else:  # PERPETUAL
        return True


def compute_revenue_split(payment: int, protocol_fee_bps: int) -> tuple[int, int]:
    """Simulate revenue split from StrategyLicense.sol.

    Returns (owner_cut, protocol_cut).
    """
    protocol_cut = (payment * protocol_fee_bps) // BPS
    owner_cut = payment - protocol_cut
    return owner_cut, protocol_cut


# ── Tests ────────────────────────────────────────────────────────────────────

class TestLicenseTypes:
    """Verify TIME_BASED, USAGE_BASED, PERPETUAL behavior."""

    def test_time_based_lease_has_end_time(self):
        lic = License(
            price_per_period=10**18,
            period_seconds=3600,
            license_type=LicenseType.TIME_BASED,
        )
        now = int(time.time())
        lease = create_lease(lic, now)
        assert lease.end_time == now + 3600
        assert lease.max_swaps == 0

    def test_usage_based_lease_has_max_swaps(self):
        lic = License(
            price_per_period=10**18,
            period_seconds=100,  # repurposed as maxSwaps
            license_type=LicenseType.USAGE_BASED,
        )
        now = int(time.time())
        lease = create_lease(lic, now)
        assert lease.end_time == 0
        assert lease.max_swaps == 100

    def test_perpetual_lease_no_expiry(self):
        lic = License(
            price_per_period=5 * 10**18,
            period_seconds=0,
            license_type=LicenseType.PERPETUAL,
        )
        now = int(time.time())
        lease = create_lease(lic, now)
        assert lease.end_time == 0
        assert lease.max_swaps == 0

    def test_license_type_enum_values(self):
        assert int(LicenseType.TIME_BASED) == 0
        assert int(LicenseType.USAGE_BASED) == 1
        assert int(LicenseType.PERPETUAL) == 2


class TestLeaseValidation:
    """Check lease validity logic."""

    def test_time_based_valid_within_period(self):
        lic = License(10**18, 3600, LicenseType.TIME_BASED)
        now = 1000000
        lease = create_lease(lic, now)
        assert check_lease_valid(lic, lease, now + 1800) is True

    def test_time_based_valid_at_exact_expiry(self):
        lic = License(10**18, 3600, LicenseType.TIME_BASED)
        now = 1000000
        lease = create_lease(lic, now)
        assert check_lease_valid(lic, lease, now + 3600) is True

    def test_time_based_invalid_after_expiry(self):
        lic = License(10**18, 3600, LicenseType.TIME_BASED)
        now = 1000000
        lease = create_lease(lic, now)
        assert check_lease_valid(lic, lease, now + 3601) is False

    def test_usage_based_valid_under_limit(self):
        lic = License(10**18, 50, LicenseType.USAGE_BASED)
        now = 1000000
        lease = create_lease(lic, now)
        lease.swaps_used = 49
        assert check_lease_valid(lic, lease, now + 99999) is True

    def test_usage_based_invalid_at_limit(self):
        lic = License(10**18, 50, LicenseType.USAGE_BASED)
        now = 1000000
        lease = create_lease(lic, now)
        lease.swaps_used = 50
        assert check_lease_valid(lic, lease, now + 99999) is False

    def test_perpetual_always_valid(self):
        lic = License(5 * 10**18, 0, LicenseType.PERPETUAL)
        now = 1000000
        lease = create_lease(lic, now)
        # Valid even far in the future
        assert check_lease_valid(lic, lease, now + 10**9) is True

    def test_inactive_lease_always_invalid(self):
        lic = License(10**18, 3600, LicenseType.TIME_BASED)
        now = 1000000
        lease = create_lease(lic, now)
        lease.active = False
        assert check_lease_valid(lic, lease, now) is False


class TestRevenueSplit:
    """Verify protocol fee calculation."""

    def test_default_protocol_fee(self):
        # Default 500 bps = 5%
        fee_bps = config.STRATEGY_LICENSE_PROTOCOL_FEE_BPS
        payment = 10**18  # 1 ETH
        owner_cut, protocol_cut = compute_revenue_split(payment, fee_bps)

        assert protocol_cut == (payment * fee_bps) // BPS
        assert owner_cut == payment - protocol_cut
        assert owner_cut + protocol_cut == payment

    def test_five_percent_fee(self):
        payment = 10000
        owner_cut, protocol_cut = compute_revenue_split(payment, 500)
        assert protocol_cut == 500
        assert owner_cut == 9500

    def test_zero_fee(self):
        payment = 10000
        owner_cut, protocol_cut = compute_revenue_split(payment, 0)
        assert protocol_cut == 0
        assert owner_cut == 10000

    def test_max_fee_twenty_percent(self):
        payment = 10000
        owner_cut, protocol_cut = compute_revenue_split(payment, 2000)
        assert protocol_cut == 2000
        assert owner_cut == 8000

    def test_revenue_split_invariant(self):
        """owner_cut + protocol_cut must always equal payment."""
        for fee_bps in [0, 100, 500, 1000, 2000]:
            for payment in [1, 100, 10**18, 999999]:
                owner_cut, protocol_cut = compute_revenue_split(payment, fee_bps)
                assert owner_cut + protocol_cut == payment

    def test_small_payment_rounding(self):
        # 1 wei with 500 bps fee -> protocol gets 0 (integer division)
        owner_cut, protocol_cut = compute_revenue_split(1, 500)
        assert protocol_cut == 0
        assert owner_cut == 1


class TestLeaseExpiry:
    """Time-based lease expiration behavior."""

    def test_lease_expires_after_period(self):
        lic = License(10**18, 7200, LicenseType.TIME_BASED)
        now = 1000000
        lease = create_lease(lic, now)

        # Valid just before expiry
        assert check_lease_valid(lic, lease, now + 7199) is True
        # Valid at exact expiry
        assert check_lease_valid(lic, lease, now + 7200) is True
        # Invalid 1 second after expiry
        assert check_lease_valid(lic, lease, now + 7201) is False

    def test_usage_based_expiry_on_swap_limit(self):
        lic = License(10**18, 10, LicenseType.USAGE_BASED)
        now = 1000000
        lease = create_lease(lic, now)

        for i in range(10):
            assert check_lease_valid(lic, lease, now) is True
            lease.swaps_used += 1

        # After 10 swaps, lease is no longer valid
        assert check_lease_valid(lic, lease, now) is False

    def test_perpetual_never_expires(self):
        lic = License(5 * 10**18, 0, LicenseType.PERPETUAL)
        now = 1000000
        lease = create_lease(lic, now)

        # Still valid after a very long time
        far_future = now + 365 * 24 * 3600 * 100  # 100 years
        assert check_lease_valid(lic, lease, far_future) is True

    def test_short_period_lease(self):
        lic = License(10**18, 1, LicenseType.TIME_BASED)
        now = 1000000
        lease = create_lease(lic, now)
        assert check_lease_valid(lic, lease, now) is True
        assert check_lease_valid(lic, lease, now + 1) is True
        assert check_lease_valid(lic, lease, now + 2) is False
