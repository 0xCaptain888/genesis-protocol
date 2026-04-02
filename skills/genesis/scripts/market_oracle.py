"""Market data aggregation using OnchainOS Market module.

Provides price fetching, volatility calculation, trend detection,
and market regime classification via the onchainos CLI.
"""
import subprocess
import json
import logging
import math
import time
import statistics

from . import config

logger = logging.getLogger(__name__)
PRICE_CACHE_TTL = 60  # seconds


class MarketOracle:
    """Aggregates market data from OnchainOS for strategy decisions."""

    def __init__(self):
        """Initialize with configured trading pairs, price cache, and history."""
        self.pairs = config.ONCHAINOS_MARKET_PAIRS
        self.chain_id = getattr(config, "CHAIN_ID", "1")
        self._price_cache = {}  # (base, quote) -> (timestamp, price)
        self._price_history = {}  # (base, quote) -> [(timestamp, price), ...]
        logger.info("MarketOracle initialized with %d pairs", len(self.pairs))

    # -- Price fetching ------------------------------------------------- #

    def fetch_price(self, base: str, quote: str) -> float | None:
        """Get the current price for a base/quote pair via onchainos CLI.

        Returns the cached value if it is younger than PRICE_CACHE_TTL seconds.
        """
        key = (base, quote)
        now = time.time()
        cached = self._price_cache.get(key)
        if cached and (now - cached[0]) < PRICE_CACHE_TTL:
            logger.debug("Cache hit for %s/%s", base, quote)
            return cached[1]

        cmd = [
            "onchainos", "market", "price",
            "--base", base,
            "--quote", quote,
            "--chain", self.chain_id,
        ]
        data = self._run_cmd(cmd)
        if data is None:
            return None

        price = float(data.get("price", 0))
        self._price_cache[key] = (now, price)
        self.update_price_history(base, quote, price)
        logger.info("Fetched price %s/%s = %s", base, quote, price)
        return price

    def fetch_all_prices(self) -> dict:
        """Fetch prices for every configured pair.

        Returns a dict mapping ``(base, quote)`` to the latest price.
        """
        results = {}
        for pair in self.pairs:
            base, quote = pair["base"], pair["quote"]
            price = self.fetch_price(base, quote)
            if price is not None:
                results[(base, quote)] = price
        logger.info("Fetched prices for %d/%d pairs", len(results), len(self.pairs))
        return results

    # -- Analytics ------------------------------------------------------- #

    def calculate_volatility(
        self, base: str, quote: str, window_hours: float | None = None
    ) -> float | None:
        """Calculate realised volatility from stored price history.

        Uses standard deviation of log-returns over *window_hours*
        (defaults to ``config.VOLATILITY_WINDOW_HOURS``).
        """
        window = window_hours or config.VOLATILITY_WINDOW_HOURS
        prices = self._windowed_prices(base, quote, window)
        if len(prices) < 2:
            logger.warning("Not enough price points for %s/%s volatility", base, quote)
            return None

        log_returns = self._calculate_log_returns(prices)
        vol = statistics.stdev(log_returns) * math.sqrt(len(log_returns))
        logger.info("Volatility %s/%s (%.1fh): %.6f", base, quote, window, vol)
        return vol

    def detect_trend(
        self, base: str, quote: str, window_hours: float | None = None
    ) -> str:
        """Detect trend direction using a simple moving-average comparison.

        Compares the short-window SMA (first half) against the long-window SMA
        (full window).  Returns ``"trending_up"``, ``"trending_down"``, or
        ``"sideways"``.
        """
        window = window_hours or config.TREND_WINDOW_HOURS
        prices = self._windowed_prices(base, quote, window)
        if len(prices) < 4:
            logger.warning("Not enough data to detect trend for %s/%s", base, quote)
            return "sideways"

        mid = len(prices) // 2
        sma_recent = statistics.mean(prices[mid:])
        sma_full = statistics.mean(prices)

        pct_diff = (sma_recent - sma_full) / sma_full if sma_full else 0
        threshold = getattr(config, "TREND_THRESHOLD", 0.005)

        if pct_diff > threshold:
            trend = "trending_up"
        elif pct_diff < -threshold:
            trend = "trending_down"
        else:
            trend = "sideways"

        logger.info("Trend %s/%s: %s (delta=%.4f)", base, quote, trend, pct_diff)
        return trend

    def get_market_regime(self, base: str, quote: str) -> dict:
        """Combine volatility and trend into a market-regime classification.

        Returns a dict with keys: ``volatility``, ``trend``, ``regime_name``,
        and ``confidence``.  The ``regime_name`` maps to one of the keys in
        ``config.STRATEGY_PRESETS``.
        """
        vol = self.calculate_volatility(base, quote)
        trend = self.detect_trend(base, quote)

        high_vol_threshold = getattr(config, "HIGH_VOL_THRESHOLD", 0.04)
        is_high_vol = vol is not None and vol > high_vol_threshold

        if is_high_vol and trend == "trending_up":
            regime = "momentum"
            confidence = 0.8
        elif is_high_vol and trend == "trending_down":
            regime = "defensive"
            confidence = 0.75
        elif is_high_vol:
            regime = "volatile_range"
            confidence = 0.6
        elif trend in ("trending_up", "trending_down"):
            regime = "trend_following"
            confidence = 0.7
        else:
            regime = "mean_reversion"
            confidence = 0.65

        presets = getattr(config, "STRATEGY_PRESETS", {})
        if regime not in presets:
            logger.warning("Regime '%s' not found in STRATEGY_PRESETS", regime)

        result = {
            "volatility": vol,
            "trend": trend,
            "regime_name": regime,
            "confidence": confidence,
        }
        logger.info("Market regime %s/%s: %s", base, quote, result)
        return result

    # -- Price history --------------------------------------------------- #

    def update_price_history(self, base: str, quote: str, price: float) -> None:
        """Append a timestamped price entry to the history for a pair."""
        key = (base, quote)
        self._price_history.setdefault(key, []).append((time.time(), price))

    # -- DEX quoting ---------------------------------------------------- #

    def get_dex_quote(
        self, token_in: str, token_out: str, amount: float
    ) -> dict | None:
        """Get a DEX swap quote via the onchainos CLI.

        Uses ``config.DEX_SLIPPAGE_BPS`` for slippage tolerance.
        """
        cmd = [
            "onchainos", "trade", "quote",
            "--token-in", token_in,
            "--token-out", token_out,
            "--amount", str(amount),
            "--chain", self.chain_id,
            "--slippage", str(config.DEX_SLIPPAGE_BPS),
        ]
        data = self._run_cmd(cmd)
        if data is not None:
            logger.info(
                "DEX quote %s->%s (%s): %s", token_in, token_out, amount, data
            )
        return data

    # -- Uniswap AI Skills Integration --------------------------------- #

    def get_uniswap_pool_data(
        self, token_in: str, token_out: str
    ) -> dict | None:
        """Get Uniswap pool liquidity and pricing data via the uniswap-trading skill.

        Returns the skill response dict, or ``None`` on failure.
        """
        cmd = ["onchainos", "skill", "run", "uniswap-trading", "pool-info",
               "--token-in", token_in,
               "--token-out", token_out,
               "--chain", str(config.CHAIN_ID)]
        logger.info("Fetching Uniswap pool data for %s -> %s", token_in, token_out)
        data = self._run_cmd(cmd)
        if data is not None:
            logger.info("Uniswap pool data %s/%s: %s", token_in, token_out, data)
        else:
            logger.error("Failed to fetch Uniswap pool data for %s/%s", token_in, token_out)
        return data

    def get_optimal_swap_route(
        self, token_in: str, token_out: str, amount: float
    ) -> dict | None:
        """Get the optimal Uniswap swap route via the uniswap-trading skill.

        Returns the skill response dict with route information, or ``None`` on failure.
        """
        cmd = ["onchainos", "skill", "run", "uniswap-trading", "route",
               "--token-in", token_in,
               "--token-out", token_out,
               "--amount", str(amount),
               "--chain", str(config.CHAIN_ID)]
        logger.info("Fetching optimal swap route %s -> %s (amount=%s)", token_in, token_out, amount)
        data = self._run_cmd(cmd)
        if data is not None:
            logger.info("Optimal route %s->%s: %s", token_in, token_out, data)
        else:
            logger.error("Failed to fetch optimal swap route for %s->%s", token_in, token_out)
        return data

    # -- Internal helpers ------------------------------------------------ #

    def _run_cmd(self, cmd: list[str]) -> dict | None:
        """Execute a subprocess command and return parsed JSON output.

        Returns ``None`` on any failure (non-zero exit, invalid JSON, etc.).
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                logger.error(
                    "Command %s failed (rc=%d): %s",
                    cmd, result.returncode, result.stderr.strip(),
                )
                return None
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            logger.error("Command timed out: %s", cmd)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON from command %s: %s", cmd, exc)
        except OSError as exc:
            logger.error("OS error running %s: %s", cmd, exc)
        return None

    def _calculate_log_returns(self, prices: list[float]) -> list[float]:
        """Compute log-returns from an ordered list of prices."""
        return [
            math.log(prices[i] / prices[i - 1])
            for i in range(1, len(prices))
            if prices[i - 1] > 0
        ]

    def _windowed_prices(
        self, base: str, quote: str, window_hours: float
    ) -> list[float]:
        """Return prices within the last *window_hours* hours."""
        key = (base, quote)
        history = self._price_history.get(key, [])
        cutoff = time.time() - (window_hours * 3600)
        return [p for ts, p in history if ts >= cutoff]
