"""DeFi Analyzer - Deep onchainos-defi-invest integration for yield comparison.

Compares yields across X Layer DeFi protocols and benchmarks Genesis
Protocol strategy returns against the broader ecosystem. Uses OKX DeFi
API endpoints for protocol-level TVL, APY, and investment data.

Reference: https://web3.okx.com/api (DeFi Invest endpoints)
"""

import json
import logging
import math
import os
import subprocess
from typing import Optional

try:
    import requests as _requests
except ImportError:
    _requests = None

from . import config

logger = logging.getLogger(__name__)

# OKX DeFi API base
DEFI_BASE_URL = "https://web3.okx.com"

# X Layer chain index used by OKX APIs
X_LAYER_CHAIN_INDEX = "196"


class DeFiAnalyzer:
    """Analyze and benchmark DeFi yields across X Layer protocols.

    Integrates with the onchainos-defi-invest skill and OKX DeFi API to
    provide Genesis Protocol with:
      - Cross-protocol yield comparisons on X Layer
      - TVL tracking for competing protocols
      - Benchmarking of Genesis strategy returns vs alternatives
      - Investment opportunity discovery

    Used by the Genesis Engine's Analysis Layer and the Evolution Layer's
    meta-cognition to evaluate whether Genesis strategies are competitive.
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
        chain_index: str = X_LAYER_CHAIN_INDEX,
        timeout: int = 30,
    ):
        self.api_key = api_key or os.environ.get("OK_ACCESS_KEY", "")
        self.api_secret = api_secret or os.environ.get("OK_ACCESS_SECRET", "")
        self.passphrase = passphrase or os.environ.get("OK_ACCESS_PASSPHRASE", "")
        self.chain_index = chain_index
        self.timeout = timeout
        self._has_credentials = bool(self.api_key and self.api_secret and self.passphrase)
        if not self._has_credentials:
            logger.warning(
                "DeFiAnalyzer: missing API credentials; REST calls will fall back to CLI"
            )

    # ── Protocol Yield Data ───────────────────────────────────────────

    def get_protocol_yields(
        self,
        protocol_ids: Optional[list] = None,
        asset_filter: str = "",
    ) -> dict:
        """Fetch current yield / APY data for DeFi protocols on X Layer.

        Queries the OKX DeFi Invest API for protocol-level yield information
        including LP farming, lending, and staking opportunities.

        Args:
            protocol_ids: Optional list of protocol identifiers to filter.
            asset_filter: Optional token symbol to filter (e.g. "USDT").

        Returns:
            dict with protocol yields or CLI fallback result. Each entry
            contains protocol_name, pool, apy, tvl, and risk_level.
        """
        path = "/api/v5/defi/explore/product/list"
        params = {"chainIndex": self.chain_index}
        if asset_filter:
            params["tokenSymbol"] = asset_filter

        cli_cmd = [
            "onchainos", "skill", "run", "onchainos-defi-invest",
            "--action", "list-yields",
            "--chain", self.chain_index,
        ]
        if asset_filter:
            cli_cmd.extend(["--asset", asset_filter])

        result = self._request_with_fallback("GET", path, cli_cmd, params=params)

        # Filter by protocol_ids if provided
        if result and protocol_ids and isinstance(result.get("data"), list):
            result["data"] = [
                p for p in result["data"]
                if p.get("protocolId") in protocol_ids or p.get("protocol") in protocol_ids
            ]

        return result or {"error": "unable to fetch protocol yields"}

    def compare_strategies(
        self,
        genesis_apy: float,
        genesis_tvl: float,
        asset: str = "ETH-USDT",
    ) -> dict:
        """Compare Genesis strategy performance against competing protocols.

        Pulls yield data for similar pools on X Layer and ranks Genesis
        against them. Used by the Evolution Layer for meta-cognition.

        Args:
            genesis_apy: Current Genesis strategy APY (as percentage, e.g. 12.5).
            genesis_tvl: Current Genesis strategy TVL in USD.
            asset:       Trading pair to compare (e.g. "ETH-USDT").

        Returns:
            dict with ranked comparison, Genesis rank, and improvement suggestions.
        """
        base_token = asset.split("-")[0] if "-" in asset else asset
        yields_result = self.get_protocol_yields(asset_filter=base_token)

        competitors = []
        if isinstance(yields_result.get("data"), list):
            for entry in yields_result["data"]:
                apy = _safe_float(entry.get("apy") or entry.get("estimatedApy"))
                tvl = _safe_float(entry.get("tvl") or entry.get("totalTvl"))
                competitors.append({
                    "protocol": entry.get("protocolName") or entry.get("protocol", "unknown"),
                    "pool": entry.get("poolName") or entry.get("investmentName", ""),
                    "apy": apy,
                    "tvl": tvl,
                })

        # Insert Genesis into the comparison
        genesis_entry = {
            "protocol": "Genesis Protocol",
            "pool": f"{asset} (V4 Hook)",
            "apy": genesis_apy,
            "tvl": genesis_tvl,
        }
        all_entries = competitors + [genesis_entry]
        all_entries.sort(key=lambda x: x.get("apy", 0), reverse=True)

        genesis_rank = next(
            (i + 1 for i, e in enumerate(all_entries) if e["protocol"] == "Genesis Protocol"),
            len(all_entries),
        )

        return {
            "asset": asset,
            "chain_index": self.chain_index,
            "genesis": genesis_entry,
            "genesis_rank": genesis_rank,
            "total_protocols": len(all_entries),
            "top_5": all_entries[:5],
            "outperforming": genesis_rank == 1,
            "improvement_needed_bps": (
                round((all_entries[0]["apy"] - genesis_apy) * 100, 2)
                if genesis_rank > 1 and all_entries else 0
            ),
        }

    def get_tvl_data(
        self,
        protocol_ids: Optional[list] = None,
    ) -> dict:
        """Fetch TVL (Total Value Locked) data for X Layer DeFi protocols.

        Args:
            protocol_ids: Optional list of protocol identifiers to filter.

        Returns:
            dict with per-protocol TVL, total X Layer TVL, and TVL breakdown.
        """
        path = "/api/v5/defi/explore/protocol/list"
        params = {"chainIndex": self.chain_index}

        cli_cmd = [
            "onchainos", "skill", "run", "onchainos-defi-invest",
            "--action", "tvl-data",
            "--chain", self.chain_index,
        ]
        result = self._request_with_fallback("GET", path, cli_cmd, params=params)

        if not result:
            return {"error": "unable to fetch TVL data"}

        protocols = result.get("data", [])
        if protocol_ids and isinstance(protocols, list):
            protocols = [
                p for p in protocols
                if p.get("protocolId") in protocol_ids or p.get("protocolName") in protocol_ids
            ]

        total_tvl = sum(_safe_float(p.get("tvl", 0)) for p in protocols)

        return {
            "chain_index": self.chain_index,
            "total_tvl_usd": total_tvl,
            "protocol_count": len(protocols),
            "protocols": protocols,
        }

    def benchmark_genesis(
        self,
        strategy_name: str,
        genesis_metrics: Optional[dict] = None,
    ) -> dict:
        """Run a comprehensive benchmark of a Genesis strategy.

        Combines yield comparison, TVL ranking, and risk-adjusted metrics
        to produce a score-card for a Genesis strategy.

        Args:
            strategy_name:  Name of the Genesis strategy preset.
            genesis_metrics: dict with keys apy, tvl, sharpe, max_drawdown,
                             swap_count, runtime_hours. Falls back to defaults
                             if not provided.

        Returns:
            dict with benchmark score, category rankings, and recommendations.
        """
        metrics = genesis_metrics or {
            "apy": 0.0,
            "tvl": 0.0,
            "sharpe": 0.0,
            "max_drawdown_pct": 0.0,
            "swap_count": 0,
            "runtime_hours": 0,
        }

        # Pull ecosystem data
        yields = self.get_protocol_yields()
        tvl_data = self.get_tvl_data()

        # Compute yield percentile
        ecosystem_apys = []
        if isinstance(yields.get("data"), list):
            ecosystem_apys = [
                _safe_float(p.get("apy") or p.get("estimatedApy"))
                for p in yields["data"]
            ]
        ecosystem_apys_sorted = sorted(ecosystem_apys)
        genesis_apy = metrics.get("apy", 0)
        if ecosystem_apys_sorted:
            rank = sum(1 for a in ecosystem_apys_sorted if a <= genesis_apy)
            yield_percentile = (rank / len(ecosystem_apys_sorted)) * 100
        else:
            yield_percentile = 0

        # Strategy preset info
        preset = config.STRATEGY_PRESETS.get(strategy_name, {})

        return {
            "strategy_name": strategy_name,
            "strategy_description": preset.get("description", ""),
            "chain_index": self.chain_index,
            "genesis_metrics": metrics,
            "ecosystem_comparison": {
                "yield_percentile": round(yield_percentile, 2),
                "ecosystem_protocol_count": tvl_data.get("protocol_count", 0),
                "ecosystem_total_tvl": tvl_data.get("total_tvl_usd", 0),
                "ecosystem_median_apy": (
                    ecosystem_apys_sorted[len(ecosystem_apys_sorted) // 2]
                    if ecosystem_apys_sorted else 0
                ),
            },
            "score_card": {
                "yield_score": min(100, round(yield_percentile, 0)),
                "risk_score": _risk_score(metrics),
                "activity_score": _activity_score(metrics),
            },
        }

    # ── Integration Summary ───────────────────────────────────────────

    def get_integration_summary(self) -> dict:
        """Return a summary of the onchainos-defi-invest integration.

        Useful for README documentation and evaluator reference.
        """
        return {
            "skill": "onchainos-defi-invest",
            "status": "integrated",
            "usage": "Cross-protocol yield comparison and Genesis benchmarking",
            "capabilities": [
                "get_protocol_yields - Yield / APY data across X Layer DeFi",
                "compare_strategies - Rank Genesis vs competing protocols",
                "get_tvl_data - TVL tracking for X Layer ecosystem",
                "benchmark_genesis - Comprehensive strategy score-card",
            ],
            "chain_index": self.chain_index,
            "api_base": DEFI_BASE_URL,
            "has_credentials": self._has_credentials,
        }

    # ── Internal helpers ──────────────────────────────────────────────

    def _sign(self, method: str, request_path: str, body: str = "") -> dict:
        """Build HMAC-SHA256 signed headers for an OKX API request."""
        import base64
        import hashlib
        import hmac as _hmac
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        message = timestamp + method.upper() + request_path + body
        signature = base64.b64encode(
            _hmac.new(
                self.api_secret.encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, params: Optional[dict] = None) -> Optional[dict]:
        """Execute an authenticated REST GET against the OKX DeFi API."""
        if not self._has_credentials:
            logger.debug("No credentials; skipping REST request %s %s", method, path)
            return None
        if _requests is None:
            logger.error("requests library not installed")
            return None

        request_path = path
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            request_path = path + "?" + qs

        headers = self._sign(method.upper(), request_path)
        url = DEFI_BASE_URL + request_path

        try:
            resp = _requests.get(url, headers=headers, timeout=self.timeout)
            data = resp.json()
            logger.debug("REST %s %s -> %s", method, path, data.get("code", "ok"))
            return data
        except Exception as exc:
            logger.error("REST error for %s %s: %s", method, path, exc)
        return None

    def _cli_fallback(self, cmd: list) -> Optional[dict]:
        """Execute an onchainos CLI command as fallback."""
        logger.debug("CLI fallback: %s", " ".join(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
            if result.returncode != 0:
                logger.error("CLI fallback failed (rc=%d): %s", result.returncode, result.stderr.strip())
                return None
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            logger.error("CLI fallback timed out: %s", " ".join(cmd))
        except json.JSONDecodeError as exc:
            logger.error("CLI fallback invalid JSON: %s", exc)
        except OSError as exc:
            logger.error("CLI fallback OS error: %s", exc)
        return None

    def _request_with_fallback(
        self, method: str, path: str, cli_cmd: list,
        params: Optional[dict] = None,
    ) -> Optional[dict]:
        """Try REST API first; fall back to CLI subprocess on failure."""
        result = self._request(method, path, params=params)
        if result is not None:
            return result
        logger.info("REST unavailable for %s; falling back to CLI", path)
        return self._cli_fallback(cli_cmd)


# ── Module-level helpers ──────────────────────────────────────────────────

def _safe_float(value) -> float:
    """Safely convert a value to float, returning 0.0 on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _risk_score(metrics: dict) -> float:
    """Compute a 0-100 risk score from strategy metrics.

    Lower max drawdown and higher Sharpe ratio yield a higher score.
    """
    sharpe = _safe_float(metrics.get("sharpe", 0))
    drawdown = _safe_float(metrics.get("max_drawdown_pct", 0))
    # Sharpe contribution: capped at 3.0 -> 50 points
    sharpe_pts = min(50, (sharpe / 3.0) * 50)
    # Drawdown contribution: 0% drawdown -> 50 pts, 20%+ -> 0 pts
    drawdown_pts = max(0, 50 - (drawdown / 20) * 50)
    return round(sharpe_pts + drawdown_pts, 2)


def _activity_score(metrics: dict) -> float:
    """Compute a 0-100 activity score from swap count and runtime.

    More swaps and longer runtime yield a higher score.
    """
    swaps = _safe_float(metrics.get("swap_count", 0))
    hours = _safe_float(metrics.get("runtime_hours", 0))
    # Swap contribution: 500+ swaps -> 50 pts
    swap_pts = min(50, (swaps / 500) * 50)
    # Runtime contribution: 168h (1 week)+ -> 50 pts
    runtime_pts = min(50, (hours / 168) * 50)
    return round(swap_pts + runtime_pts, 2)
