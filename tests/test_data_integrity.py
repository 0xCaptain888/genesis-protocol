"""Tests for DataIntegrityVerifier - cross-validation of oracle price data."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import time
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from skills.genesis.scripts.data_integrity import (
    DataIntegrityVerifier,
    OracleSource,
    IntegrityResult,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _verifier(**overrides) -> DataIntegrityVerifier:
    """Create a verifier with sensible test defaults."""
    cfg = {
        "max_deviation_bps": 500,
        "max_staleness_seconds": 300,
        "min_sources_required": 2,
    }
    cfg.update(overrides)
    return DataIntegrityVerifier(cfg)


# ── Oracle Registration ─────────────────────────────────────────────────────

class TestRegisterOracle:
    def test_register_single_oracle(self):
        v = _verifier()
        v.register_oracle("chainlink_eth", "chainlink", "0xABC", weight=1.0)
        assert "chainlink_eth" in v.oracle_sources
        src = v.oracle_sources["chainlink_eth"]
        assert src.source_type == "chainlink"
        assert src.endpoint == "0xABC"
        assert src.weight == 1.0
        assert src.active is True

    def test_register_multiple_oracles(self):
        v = _verifier()
        v.register_oracle("chainlink_eth", "chainlink", "0xABC")
        v.register_oracle("pyth_eth", "pyth", "0xDEF", weight=0.8)
        v.register_oracle("twap_eth", "uniswap_twap", "0x123", weight=1.2)
        assert len(v.oracle_sources) == 3
        assert v.oracle_sources["pyth_eth"].weight == 0.8

    def test_register_overwrites_existing(self):
        v = _verifier()
        v.register_oracle("chainlink_eth", "chainlink", "0xABC")
        v.register_oracle("chainlink_eth", "chainlink", "0xNEW", weight=2.0)
        assert v.oracle_sources["chainlink_eth"].endpoint == "0xNEW"
        assert v.oracle_sources["chainlink_eth"].weight == 2.0

    def test_deregister_oracle(self):
        v = _verifier()
        v.register_oracle("chainlink_eth", "chainlink", "0xABC")
        v.deregister_oracle("chainlink_eth")
        assert "chainlink_eth" not in v.oracle_sources


# ── Cross-Validation ────────────────────────────────────────────────────────

class TestCrossValidateNormal:
    """All oracles agree within threshold -> valid result."""

    def test_all_agree_within_threshold(self):
        v = _verifier(max_deviation_bps=500)
        v.register_oracle("a", "custom", "http://a")
        v.register_oracle("b", "custom", "http://b")
        v.register_oracle("c", "custom", "http://c")

        prices = {"a": 3000.0, "b": 3005.0, "c": 2998.0}
        result = v.cross_validate(prices)

        assert result.valid is True
        assert result.recommended_action == "proceed"
        assert result.source_count == 3
        assert result.median_price > 0
        assert len(result.anomalies) == 0

    def test_median_price_computed_correctly(self):
        v = _verifier()
        prices = {"a": 100.0, "b": 200.0, "c": 150.0}
        result = v.cross_validate(prices)
        assert result.median_price == 150.0


class TestCrossValidateDeviation:
    """One oracle deviates beyond threshold -> anomaly detected."""

    def test_deviation_detected(self):
        v = _verifier(max_deviation_bps=500)
        v.register_oracle("a", "custom", "http://a")
        v.register_oracle("b", "custom", "http://b")
        v.register_oracle("c", "custom", "http://c")

        # "c" deviates by ~33% = 3333 bps, well above 500 bps threshold
        prices = {"a": 3000.0, "b": 3010.0, "c": 4000.0}
        result = v.cross_validate(prices)

        assert result.valid is False
        assert any(a["type"] == "price_deviation" for a in result.anomalies)
        assert result.max_deviation_bps > 500

    def test_severe_deviation_triggers_halt(self):
        v = _verifier(max_deviation_bps=500)
        v.register_oracle("a", "custom", "http://a")
        v.register_oracle("b", "custom", "http://b")

        # Deviation > 2x threshold -> halt
        prices = {"a": 1000.0, "b": 2000.0}
        result = v.cross_validate(prices)

        assert result.valid is False
        assert result.recommended_action == "halt"

    def test_moderate_deviation_triggers_caution(self):
        v = _verifier(max_deviation_bps=500)
        v.register_oracle("a", "custom", "http://a")
        v.register_oracle("b", "custom", "http://b")
        v.register_oracle("c", "custom", "http://c")

        # "c" deviates by ~6.6% = 660 bps, above 500 but below 1000 (2x)
        prices = {"a": 3000.0, "b": 3000.0, "c": 3200.0}
        result = v.cross_validate(prices)

        assert result.valid is False
        assert result.recommended_action == "caution"


class TestStalenessDetection:
    """Oracle data older than max_staleness -> flagged."""

    def test_stale_oracle_flagged(self):
        v = _verifier(max_staleness_seconds=300)
        v.register_oracle("a", "custom", "http://a")
        v.register_oracle("b", "custom", "http://b")

        # Simulate stale update: 600 seconds ago
        v.oracle_sources["a"].last_update = time.time() - 600
        v.oracle_sources["a"].active = True
        v.oracle_sources["b"].last_update = time.time()
        v.oracle_sources["b"].active = True

        prices = {"a": 3000.0, "b": 3000.0}
        result = v.cross_validate(prices)

        stale_anomalies = [a for a in result.anomalies if a["type"] == "stale_data"]
        assert len(stale_anomalies) >= 1
        assert stale_anomalies[0]["source"] == "a"

    def test_fresh_oracle_not_flagged(self):
        v = _verifier(max_staleness_seconds=300)
        v.register_oracle("a", "custom", "http://a")
        v.register_oracle("b", "custom", "http://b")

        v.oracle_sources["a"].last_update = time.time()
        v.oracle_sources["b"].last_update = time.time()

        prices = {"a": 3000.0, "b": 3000.0}
        result = v.cross_validate(prices)

        stale_anomalies = [a for a in result.anomalies if a["type"] == "stale_data"]
        assert len(stale_anomalies) == 0


class TestInsufficientSources:
    """Fewer than min_sources -> halt recommendation."""

    def test_zero_sources(self):
        v = _verifier(min_sources_required=2)
        result = v.cross_validate({})
        assert result.valid is False
        assert result.recommended_action == "halt"
        assert any(a["type"] == "insufficient_sources" for a in result.anomalies)

    def test_one_source_below_minimum(self):
        v = _verifier(min_sources_required=2)
        result = v.cross_validate({"a": 3000.0})
        assert result.valid is False
        assert result.recommended_action == "halt"
        assert result.anomalies[0]["available"] == 1
        assert result.anomalies[0]["required"] == 2

    def test_exact_minimum_passes(self):
        v = _verifier(min_sources_required=2, max_deviation_bps=500)
        v.register_oracle("a", "custom", "http://a")
        v.register_oracle("b", "custom", "http://b")

        prices = {"a": 3000.0, "b": 3000.0}
        result = v.cross_validate(prices)
        assert result.source_count == 2
        assert result.valid is True


class TestAnomalyDetectionSpike:
    """Sudden price spike detection via detect_anomalies."""

    def test_sudden_spike_detected(self):
        v = _verifier(max_deviation_bps=500)

        # Historical prices around 3000
        historical = [
            {"prices": {"a": 3000.0, "b": 3005.0}, "timestamp": time.time() - 60 * i}
            for i in range(10, 0, -1)
        ]

        # Current prices spike to 6000 (100% increase = 10000 bps > 1500 = 500*3)
        current_prices = {"a": 6000.0, "b": 6100.0}
        anomalies = v.detect_anomalies(current_prices, historical)

        spike_anomalies = [a for a in anomalies if a["type"] == "sudden_spike"]
        assert len(spike_anomalies) == 1
        assert spike_anomalies[0]["severity"] == "critical"

    def test_moderate_movement_warning(self):
        v = _verifier(max_deviation_bps=500)

        historical = [
            {"prices": {"a": 3000.0, "b": 3005.0}, "timestamp": time.time() - 60 * i}
            for i in range(10, 0, -1)
        ]

        # ~8% increase = 800 bps, above 750 (500*1.5) but below 1500 (500*3)
        current_prices = {"a": 3240.0, "b": 3250.0}
        anomalies = v.detect_anomalies(current_prices, historical)

        movement = [a for a in anomalies if a["type"] == "price_movement"]
        assert len(movement) == 1
        assert movement[0]["severity"] == "warning"

    def test_no_anomaly_on_stable_prices(self):
        v = _verifier(max_deviation_bps=500)

        historical = [
            {"prices": {"a": 3000.0, "b": 3005.0}, "timestamp": time.time() - 60 * i}
            for i in range(10, 0, -1)
        ]

        current_prices = {"a": 3000.0, "b": 3010.0}
        anomalies = v.detect_anomalies(current_prices, historical)

        spike_or_movement = [a for a in anomalies if a["type"] in ("sudden_spike", "price_movement")]
        assert len(spike_or_movement) == 0

    def test_empty_current_prices_returns_empty(self):
        v = _verifier()
        anomalies = v.detect_anomalies({}, [])
        assert anomalies == []


class TestIntegrityReport:
    """Verify report generation."""

    def test_report_structure(self):
        v = _verifier()
        v.register_oracle("a", "chainlink", "0xABC")
        v.register_oracle("b", "pyth", "0xDEF")

        report = v.get_integrity_report()

        assert "health" in report
        assert "active_oracles" in report
        assert "total_oracles" in report
        assert "oracle_status" in report
        assert "total_checks" in report
        assert "total_halts" in report
        assert "recent_anomaly_count" in report
        assert "anomaly_summary" in report
        assert "timestamp" in report
        assert report["total_oracles"] == 2
        assert report["active_oracles"] == 2

    def test_healthy_status(self):
        v = _verifier(min_sources_required=2)
        v.register_oracle("a", "chainlink", "0xABC")
        v.register_oracle("b", "pyth", "0xDEF")
        report = v.get_integrity_report()
        assert report["health"] == "healthy"

    def test_degraded_status_insufficient_oracles(self):
        v = _verifier(min_sources_required=3)
        v.register_oracle("a", "chainlink", "0xABC")
        report = v.get_integrity_report()
        assert report["health"] == "degraded"

    def test_oracle_status_includes_details(self):
        v = _verifier()
        v.register_oracle("a", "chainlink", "0xABC", weight=1.5)
        v.oracle_sources["a"].last_price = 3000.0
        v.oracle_sources["a"].last_update = time.time()

        report = v.get_integrity_report()
        status_a = report["oracle_status"]["a"]
        assert status_a["type"] == "chainlink"
        assert status_a["weight"] == 1.5
        assert status_a["last_price"] == 3000.0
        assert status_a["active"] is True


class TestVerifyAndFeedPipeline:
    """Mock the full verify_and_feed pipeline."""

    @pytest.mark.asyncio
    async def test_valid_pipeline_returns_proceed(self):
        v = _verifier(min_sources_required=2, max_deviation_bps=500)
        v.register_oracle("a", "custom", "http://a")
        v.register_oracle("b", "custom", "http://b")

        # Mock fetch_all_prices to return agreeing prices
        v.fetch_all_prices = AsyncMock(return_value={"a": 3000.0, "b": 3005.0})

        with patch.object(v, "_feed_onchain", return_value={"dry_run": True}):
            result = await v.verify_and_feed("ETH/USDT")

        assert result["pair"] == "ETH/USDT"
        assert result["valid"] is True
        assert result["recommended_action"] == "proceed"
        assert result["source_count"] == 2
        assert result["median_price"] > 0

    @pytest.mark.asyncio
    async def test_insufficient_sources_pipeline_halts(self):
        v = _verifier(min_sources_required=3)
        v.register_oracle("a", "custom", "http://a")

        v.fetch_all_prices = AsyncMock(return_value={"a": 3000.0})

        result = await v.verify_and_feed("ETH/USDT")

        assert result["valid"] is False
        assert result["recommended_action"] == "halt"

    @pytest.mark.asyncio
    async def test_pipeline_records_price_history(self):
        v = _verifier(min_sources_required=2)
        v.register_oracle("a", "custom", "http://a")
        v.register_oracle("b", "custom", "http://b")

        v.fetch_all_prices = AsyncMock(return_value={"a": 3000.0, "b": 3005.0})

        await v.verify_and_feed("ETH/USDT")
        assert len(v._price_history.get("ETH/USDT", [])) == 1

        await v.verify_and_feed("ETH/USDT")
        assert len(v._price_history["ETH/USDT"]) == 2
