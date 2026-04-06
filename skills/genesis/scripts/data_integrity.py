"""Data Integrity Verification Layer for Genesis Protocol.

Independent cross-validation of market data from multiple oracle sources
before feeding it to the cognitive pipeline. Acts as a circuit breaker
for poisoned or stale data, feeding results to the on-chain DataIntegrityModule.

Credentials and thresholds loaded from config module.
"""
import json
import logging
import statistics
import subprocess
import time
from dataclasses import dataclass, field

try:
    import aiohttp as _aiohttp
except ImportError:
    _aiohttp = None

from . import config

logger = logging.getLogger("genesis.data_integrity")
logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))


@dataclass
class OracleSource:
    """Represents a registered price data source."""
    name: str
    source_type: str  # 'chainlink', 'uniswap_twap', 'pyth', 'custom'
    endpoint: str
    weight: float = 1.0
    last_price: float = 0.0
    last_update: float = 0.0
    deviation_count: int = 0
    active: bool = True


@dataclass
class IntegrityResult:
    """Result of a cross-validation check across multiple oracle sources."""
    valid: bool
    median_price: float
    max_deviation_bps: float
    source_count: int
    anomalies: list = field(default_factory=list)
    timestamp: float = 0.0
    recommended_action: str = "proceed"  # 'proceed', 'caution', 'halt'


class DataIntegrityVerifier:
    """Independent data integrity verification layer for Genesis Protocol.

    Validates market data from multiple sources before feeding it to
    the cognitive pipeline. Acts as a circuit breaker for poisoned data.
    """

    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self.oracle_sources: dict[str, OracleSource] = {}
        self.anomaly_log: list[dict] = []
        self.max_deviation_bps = cfg.get(
            "max_deviation_bps",
            getattr(config, "DATA_INTEGRITY_MAX_DEVIATION_BPS", 500),
        )
        self.max_staleness_seconds = cfg.get(
            "max_staleness_seconds",
            getattr(config, "DATA_INTEGRITY_MAX_STALENESS", 300),
        )
        self.min_sources_required = cfg.get(
            "min_sources_required",
            getattr(config, "DATA_INTEGRITY_MIN_SOURCES", 2),
        )
        self._price_history: dict[str, list[dict]] = {}  # pair -> [{price, ts, source}, ...]
        self._session: "_aiohttp.ClientSession | None" = None
        self._check_count = 0
        self._halt_count = 0
        logger.info(
            "DataIntegrityVerifier initialized: max_deviation=%d bps, staleness=%ds, min_sources=%d",
            self.max_deviation_bps, self.max_staleness_seconds, self.min_sources_required,
        )

    # ── Oracle Registration ───────────────────────────────────────────────

    def register_oracle(self, name: str, source_type: str, endpoint: str, weight: float = 1.0):
        """Register a price data source.

        Args:
            name: Unique identifier for this oracle (e.g. 'chainlink_eth_usd').
            source_type: Type of oracle ('chainlink', 'uniswap_twap', 'pyth', 'custom').
            endpoint: URL or contract address for fetching price data.
            weight: Relative weight in median calculation (default 1.0).
        """
        if name in self.oracle_sources:
            logger.warning("Overwriting existing oracle: %s", name)
        self.oracle_sources[name] = OracleSource(
            name=name,
            source_type=source_type,
            endpoint=endpoint,
            weight=weight,
        )
        logger.info("Registered oracle: %s (type=%s, weight=%.2f)", name, source_type, weight)

    def deregister_oracle(self, name: str):
        """Remove a registered oracle source."""
        if name in self.oracle_sources:
            del self.oracle_sources[name]
            logger.info("Deregistered oracle: %s", name)

    # ── Price Fetching ────────────────────────────────────────────────────

    async def _get_session(self) -> "_aiohttp.ClientSession":
        """Get or create an aiohttp client session."""
        if _aiohttp is None:
            raise RuntimeError("aiohttp library is required for DataIntegrityVerifier")
        if self._session is None or self._session.closed:
            self._session = _aiohttp.ClientSession(
                timeout=_aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "genesis-protocol/2.0"},
            )
        return self._session

    async def close(self):
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _fetch_price_from_source(self, source: OracleSource, pair: str) -> float | None:
        """Fetch a price from a single oracle source.

        Handles different source types with appropriate request patterns.
        Returns the price as a float, or None on failure.
        """
        if not source.active:
            return None

        try:
            if source.source_type == "custom" and source.endpoint.startswith("http"):
                session = await self._get_session()
                async with session.get(source.endpoint, params={"pair": pair}) as resp:
                    if resp.status != 200:
                        logger.warning("Oracle %s returned status %d", source.name, resp.status)
                        return None
                    data = await resp.json()
                    price = float(data.get("price", data.get("result", 0)))
                    if price > 0:
                        source.last_price = price
                        source.last_update = time.time()
                        return price
                    return None

            elif source.source_type in ("chainlink", "pyth", "uniswap_twap"):
                # On-chain oracle: read via onchainos CLI
                price = self._read_onchain_oracle(source, pair)
                if price is not None and price > 0:
                    source.last_price = price
                    source.last_update = time.time()
                    return price
                return None

            else:
                logger.warning("Unknown source type %s for oracle %s", source.source_type, source.name)
                return None

        except Exception as exc:
            logger.error("Failed to fetch price from %s: %s", source.name, exc)
            return None

    @staticmethod
    def _read_onchain_oracle(source: OracleSource, pair: str) -> float | None:
        """Read price from an on-chain oracle via onchainos CLI."""
        function_map = {
            "chainlink": "latestAnswer()",
            "pyth": "getPrice(bytes32)",
            "uniswap_twap": "consult(address,uint256)",
        }
        fn = function_map.get(source.source_type, "latestAnswer()")
        cmd = [
            "onchainos", "wallet", "call",
            "--to", source.endpoint,
            "--function", fn,
            "--args", pair,
            "--read-only",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
            if proc.returncode != 0:
                logger.error("Oracle CLI call failed for %s: %s", source.name, proc.stderr.strip())
                return None
            data = json.loads(proc.stdout)
            return float(data.get("price", data.get("answer", data.get("result", 0))))
        except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.error("Oracle CLI error for %s: %s", source.name, exc)
            return None

    async def fetch_all_prices(self, pair: str) -> dict[str, float]:
        """Fetch prices from all registered oracles for a given pair.

        Args:
            pair: Trading pair string (e.g. 'ETH/USDT').

        Returns:
            dict mapping oracle name to price. Only includes successful fetches.
        """
        prices: dict[str, float] = {}
        for name, source in self.oracle_sources.items():
            price = await self._fetch_price_from_source(source, pair)
            if price is not None and price > 0:
                prices[name] = price
        logger.debug("Fetched %d/%d prices for %s", len(prices), len(self.oracle_sources), pair)
        return prices

    # ── Cross-Validation ──────────────────────────────────────────────────

    def cross_validate(self, prices: dict[str, float]) -> IntegrityResult:
        """Cross-validate prices from multiple sources.

        Computes the weighted median price and checks that all source prices
        fall within the configured max_deviation_bps threshold.

        Args:
            prices: dict mapping oracle name to price.

        Returns:
            IntegrityResult with validation status, median price, and anomalies.
        """
        now = time.time()
        self._check_count += 1

        if len(prices) < self.min_sources_required:
            anomaly = {
                "type": "insufficient_sources",
                "available": len(prices),
                "required": self.min_sources_required,
                "timestamp": now,
            }
            self.anomaly_log.append(anomaly)
            return IntegrityResult(
                valid=False,
                median_price=0.0,
                max_deviation_bps=0.0,
                source_count=len(prices),
                anomalies=[anomaly],
                timestamp=now,
                recommended_action="halt",
            )

        # Compute weighted median
        price_values = list(prices.values())
        median_price = statistics.median(price_values)

        # Check deviations
        anomalies: list[dict] = []
        max_dev_bps = 0.0
        for name, price in prices.items():
            if median_price > 0:
                dev_bps = abs(price - median_price) / median_price * 10000
            else:
                dev_bps = 0.0
            if dev_bps > max_dev_bps:
                max_dev_bps = dev_bps
            if dev_bps > self.max_deviation_bps:
                source = self.oracle_sources.get(name)
                if source:
                    source.deviation_count += 1
                anomaly = {
                    "type": "price_deviation",
                    "source": name,
                    "price": price,
                    "median": median_price,
                    "deviation_bps": round(dev_bps, 1),
                    "timestamp": now,
                }
                anomalies.append(anomaly)
                self.anomaly_log.append(anomaly)

        # Check staleness
        for name, source in self.oracle_sources.items():
            if source.active and source.last_update > 0:
                age = now - source.last_update
                if age > self.max_staleness_seconds:
                    anomaly = {
                        "type": "stale_data",
                        "source": name,
                        "age_seconds": round(age, 1),
                        "max_staleness": self.max_staleness_seconds,
                        "timestamp": now,
                    }
                    anomalies.append(anomaly)
                    self.anomaly_log.append(anomaly)

        # Determine action recommendation
        valid = len(anomalies) == 0
        if not valid and any(a["type"] == "price_deviation" for a in anomalies):
            # Price deviation: caution if minor, halt if severe
            if max_dev_bps > self.max_deviation_bps * 2:
                action = "halt"
                self._halt_count += 1
            else:
                action = "caution"
        elif not valid:
            action = "caution"
        else:
            action = "proceed"

        return IntegrityResult(
            valid=valid,
            median_price=round(median_price, 8),
            max_deviation_bps=round(max_dev_bps, 1),
            source_count=len(prices),
            anomalies=anomalies,
            timestamp=now,
            recommended_action=action,
        )

    # ── Anomaly Detection ─────────────────────────────────────────────────

    def detect_anomalies(self, current_prices: dict[str, float], historical_prices: list[dict]) -> list[dict]:
        """Detect price anomalies: sudden spikes, stale data, conflicting readings.

        Args:
            current_prices: dict mapping oracle name to current price.
            historical_prices: list of previous price snapshots
                [{prices: {name: price}, timestamp: float}, ...].

        Returns:
            list of anomaly dicts with type, severity, and details.
        """
        anomalies: list[dict] = []
        now = time.time()

        if not current_prices:
            return anomalies

        current_median = statistics.median(current_prices.values()) if current_prices else 0

        # Sudden spike detection: compare current median to historical medians
        if historical_prices and current_median > 0:
            recent_medians = []
            for snapshot in historical_prices[-10:]:
                snap_prices = snapshot.get("prices", {})
                if snap_prices:
                    recent_medians.append(statistics.median(snap_prices.values()))

            if recent_medians:
                hist_median = statistics.median(recent_medians)
                if hist_median > 0:
                    change_bps = abs(current_median - hist_median) / hist_median * 10000
                    if change_bps > self.max_deviation_bps * 3:
                        anomalies.append({
                            "type": "sudden_spike",
                            "severity": "critical",
                            "current_median": round(current_median, 8),
                            "historical_median": round(hist_median, 8),
                            "change_bps": round(change_bps, 1),
                            "timestamp": now,
                        })
                    elif change_bps > self.max_deviation_bps * 1.5:
                        anomalies.append({
                            "type": "price_movement",
                            "severity": "warning",
                            "current_median": round(current_median, 8),
                            "historical_median": round(hist_median, 8),
                            "change_bps": round(change_bps, 1),
                            "timestamp": now,
                        })

        # Conflicting readings: check if sources disagree significantly
        if len(current_prices) >= 2:
            price_list = list(current_prices.values())
            spread_bps = (max(price_list) - min(price_list)) / current_median * 10000 if current_median > 0 else 0
            if spread_bps > self.max_deviation_bps:
                anomalies.append({
                    "type": "conflicting_sources",
                    "severity": "high",
                    "spread_bps": round(spread_bps, 1),
                    "source_count": len(current_prices),
                    "timestamp": now,
                })

        # Stale data detection across all oracles
        for name, source in self.oracle_sources.items():
            if source.active and source.last_update > 0:
                age = now - source.last_update
                if age > self.max_staleness_seconds * 2:
                    anomalies.append({
                        "type": "stale_data",
                        "severity": "high",
                        "source": name,
                        "age_seconds": round(age, 1),
                        "timestamp": now,
                    })
                elif age > self.max_staleness_seconds:
                    anomalies.append({
                        "type": "stale_data",
                        "severity": "warning",
                        "source": name,
                        "age_seconds": round(age, 1),
                        "timestamp": now,
                    })

        if anomalies:
            self.anomaly_log.extend(anomalies)
        return anomalies

    # ── Full Pipeline ─────────────────────────────────────────────────────

    async def verify_and_feed(self, pair: str) -> dict:
        """Full pipeline: fetch -> validate -> feed to on-chain module.

        Fetches prices from all registered oracles, cross-validates them,
        and if valid, feeds the median price to the DataIntegrityModule on-chain.

        Args:
            pair: Trading pair string (e.g. 'ETH/USDT').

        Returns:
            dict with verification result and action recommendation.
        """
        # Fetch prices
        prices = await self.fetch_all_prices(pair)

        # Cross-validate
        result = self.cross_validate(prices)

        # Record historical price snapshot
        if pair not in self._price_history:
            self._price_history[pair] = []
        self._price_history[pair].append({
            "prices": prices,
            "timestamp": result.timestamp,
        })
        # Keep last 100 snapshots per pair
        if len(self._price_history[pair]) > 100:
            self._price_history[pair] = self._price_history[pair][-100:]

        # Run anomaly detection against history
        anomalies = self.detect_anomalies(prices, self._price_history.get(pair, []))

        # Merge additional anomalies into result
        if anomalies:
            result.anomalies.extend(anomalies)
            # Upgrade action if critical anomalies found
            for a in anomalies:
                if a.get("severity") == "critical":
                    result.recommended_action = "halt"
                    result.valid = False
                    break

        output = {
            "pair": pair,
            "valid": result.valid,
            "median_price": result.median_price,
            "max_deviation_bps": result.max_deviation_bps,
            "source_count": result.source_count,
            "anomaly_count": len(result.anomalies),
            "recommended_action": result.recommended_action,
            "timestamp": result.timestamp,
        }

        # Feed to on-chain module if valid and enabled
        if result.valid and result.recommended_action == "proceed":
            integrity_module = getattr(config, "DATA_INTEGRITY_MODULE_ADDRESS", "")
            if integrity_module and not config.DRY_RUN:
                tx_result = self._feed_onchain(integrity_module, pair, result)
                output["onchain_feed"] = tx_result
            elif config.DRY_RUN:
                logger.info(
                    "[DRY_RUN] feed_onchain: pair=%s median=%.8f sources=%d",
                    pair, result.median_price, result.source_count,
                )
                output["onchain_feed"] = {"dry_run": True}

        logger.info(
            "Integrity check: pair=%s valid=%s action=%s median=%.8f sources=%d anomalies=%d",
            pair, result.valid, result.recommended_action,
            result.median_price, result.source_count, len(result.anomalies),
        )
        return output

    @staticmethod
    def _feed_onchain(module_address: str, pair: str, result: IntegrityResult) -> dict:
        """Feed verified price data to the DataIntegrityModule on-chain."""
        # Encode price as uint256 (8 decimal places)
        price_encoded = int(result.median_price * 10**8)
        cmd = [
            "onchainos", "wallet", "call",
            "--to", module_address,
            "--function", "feedVerifiedPrice(string,uint256,uint256,uint256)",
            "--args", f"{pair} {price_encoded} {result.source_count} {int(result.timestamp)}",
        ]
        logger.debug("cmd: %s", " ".join(cmd))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
            if proc.returncode != 0:
                logger.error("Feed on-chain failed (%d): %s", proc.returncode, proc.stderr.strip())
                return {"error": proc.stderr or f"exit code {proc.returncode}"}
            return {"stdout": proc.stdout}
        except subprocess.TimeoutExpired:
            logger.error("Feed on-chain timed out")
            return {"error": "timeout"}
        except FileNotFoundError:
            logger.error("onchainos CLI not found")
            return {"error": "onchainos CLI not found"}

    # ── Reporting ─────────────────────────────────────────────────────────

    def get_integrity_report(self) -> dict:
        """Generate integrity report for logging/decision journal.

        Returns:
            dict with oracle status, anomaly summary, and overall health.
        """
        now = time.time()
        oracle_status = {}
        for name, source in self.oracle_sources.items():
            age = now - source.last_update if source.last_update > 0 else -1
            oracle_status[name] = {
                "type": source.source_type,
                "active": source.active,
                "weight": source.weight,
                "last_price": source.last_price,
                "age_seconds": round(age, 1) if age >= 0 else None,
                "stale": age > self.max_staleness_seconds if age >= 0 else None,
                "deviation_count": source.deviation_count,
            }

        # Summarize recent anomalies (last hour)
        cutoff = now - 3600
        recent_anomalies = [a for a in self.anomaly_log if a.get("timestamp", 0) > cutoff]
        anomaly_summary = {}
        for a in recent_anomalies:
            atype = a.get("type", "unknown")
            anomaly_summary[atype] = anomaly_summary.get(atype, 0) + 1

        # Trim anomaly log to last 500 entries
        if len(self.anomaly_log) > 500:
            self.anomaly_log = self.anomaly_log[-500:]

        active_oracles = sum(1 for s in self.oracle_sources.values() if s.active)
        health = "healthy"
        if active_oracles < self.min_sources_required:
            health = "degraded"
        if self._halt_count > 0 and any(
            a.get("timestamp", 0) > now - 300 for a in self.anomaly_log
            if a.get("type") in ("price_deviation", "sudden_spike")
        ):
            health = "critical"

        return {
            "health": health,
            "active_oracles": active_oracles,
            "total_oracles": len(self.oracle_sources),
            "oracle_status": oracle_status,
            "total_checks": self._check_count,
            "total_halts": self._halt_count,
            "recent_anomaly_count": len(recent_anomalies),
            "anomaly_summary": anomaly_summary,
            "max_deviation_bps": self.max_deviation_bps,
            "max_staleness_seconds": self.max_staleness_seconds,
            "min_sources_required": self.min_sources_required,
            "timestamp": now,
        }
