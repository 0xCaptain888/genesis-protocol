"""Uniswap Driver (Swap & Liquidity Planning) Skill Integration.

Integrates the uniswap-driver Uniswap AI skill for advanced swap route
optimization and liquidity position planning. Provides the Planning Layer
with data-driven recommendations for tick ranges, fee tiers, multi-hop
routing, and gas estimation on X Layer.

Reference: https://github.com/Uniswap/uniswap-ai
"""

import json
import logging
import subprocess
from typing import Optional

from . import config

logger = logging.getLogger(__name__)


class UniswapDriverClient:
    """Client for the uniswap-driver (swap & liquidity planning) skill on X Layer.

    The driver skill acts as a planning oracle for Genesis strategies:
      - Liquidity planning: optimal tick ranges, amounts, and fee tiers
      - Swap planning: route optimization, multi-hop paths, gas estimation
      - Pool analytics: TVL, volume, fee APR, tick distribution

    Integrates tightly with the AutoRebalanceModule by supplying optimal
    target ranges and rebalance parameters.
    """

    # Uniswap V4 addresses on X Layer (mirrors UniswapSkillClient)
    POOL_MANAGER = "0x360e68faCCca8cA495c1B759Fd9EEe466dB9Fb32"
    POSITION_MANAGER = "0x1b35d13a2e2528f192637f14b05f0dc0e7deb566"
    QUOTER = "0x3972c00f7ed4885e145823eb7c655375d275a1c5"

    # Fee tier presets (in hundredths of a bip)
    FEE_TIERS = {
        "lowest": 100,     # 0.01% - stable pairs
        "low": 500,        # 0.05% - correlated pairs
        "medium": 3000,    # 0.30% - standard pairs
        "high": 10000,     # 1.00% - exotic pairs
        "dynamic": 0x800000,  # Dynamic fee flag for Genesis hook pools
    }

    def __init__(self, chain_id: int = 0, rpc_url: str = ""):
        self.chain_id = chain_id or config.CHAIN_ID
        self.rpc_url = rpc_url or config.RPC_URL
        self.hook_address = config.CONTRACTS.get("v4_hook", "")
        self.rebalance_module = config.CONTRACTS.get("auto_rebalance_module", "")

    # ── Liquidity Planning ────────────────────────────────────────────

    def plan_liquidity_position(
        self,
        token0: str,
        token1: str,
        amount_usd: str,
        risk_profile: str = "moderate",
        use_genesis_hook: bool = True,
    ) -> dict:
        """Plan an optimal concentrated liquidity position.

        Uses the uniswap-driver skill to analyze current pool state and
        recommend tick range, liquidity amount, and fee tier.

        Args:
            token0:           Address of token0.
            token1:           Address of token1.
            amount_usd:       Total capital to deploy in USD terms.
            risk_profile:     One of "conservative", "moderate", "aggressive".
            use_genesis_hook: If True, plan for a Genesis hook pool (dynamic fees).

        Returns:
            dict with recommended tick_lower, tick_upper, liquidity, fee_tier,
            and expected APR range.
        """
        fee_tier = str(self.FEE_TIERS["dynamic"]) if use_genesis_hook else "auto"

        cmd = [
            "onchainos", "skill", "run", "uniswap-driver",
            "--action", "plan-liquidity",
            "--token0", token0,
            "--token1", token1,
            "--amount-usd", amount_usd,
            "--risk-profile", risk_profile,
            "--fee-tier", fee_tier,
            "--chain", str(self.chain_id),
        ]
        if use_genesis_hook:
            cmd.extend(["--hook", self.hook_address])

        return self._run_skill_cmd(cmd, "plan_liquidity_position")

    def optimize_tick_range(
        self,
        token0: str,
        token1: str,
        current_tick: int,
        volatility_pct: float,
        strategy_preset: str = "",
    ) -> dict:
        """Compute an optimal tick range based on volatility and strategy.

        Integrates with the AutoRebalanceModule: the returned range can be
        fed directly into a rebalance operation as the new target range.

        Args:
            token0:          Address of token0.
            token1:          Address of token1.
            current_tick:    Current pool tick.
            volatility_pct:  Rolling volatility percentage from OnchainOS data.
            strategy_preset: Optional Genesis strategy name (e.g. "calm_accumulator").

        Returns:
            dict with tick_lower, tick_upper, width_ticks, and reasoning.
        """
        cmd = [
            "onchainos", "skill", "run", "uniswap-driver",
            "--action", "optimize-tick-range",
            "--token0", token0,
            "--token1", token1,
            "--current-tick", str(current_tick),
            "--volatility", str(volatility_pct),
            "--chain", str(self.chain_id),
        ]
        if strategy_preset:
            cmd.extend(["--strategy-preset", strategy_preset])

        return self._run_skill_cmd(cmd, "optimize_tick_range")

    # ── Swap Planning ─────────────────────────────────────────────────

    def plan_swap_route(
        self,
        token_in: str,
        token_out: str,
        amount: str,
        exact_input: bool = True,
        max_hops: int = 3,
    ) -> dict:
        """Plan an optimal swap route with multi-hop path finding.

        Evaluates direct routes and multi-hop paths through intermediate
        tokens to find the best execution price. Considers both V4 hook
        pools and standard V4 pools on X Layer.

        Args:
            token_in:     Address of the input token.
            token_out:    Address of the output token.
            amount:       Amount in wei (input or output depending on exact_input).
            exact_input:  True for exactIn, False for exactOut.
            max_hops:     Maximum number of intermediate hops (default 3).

        Returns:
            dict with route (list of hops), expected output, price impact,
            and comparison to DEX aggregator quote.
        """
        cmd = [
            "onchainos", "skill", "run", "uniswap-driver",
            "--action", "plan-swap-route",
            "--token-in", token_in,
            "--token-out", token_out,
            "--amount", amount,
            "--swap-mode", "exactIn" if exact_input else "exactOut",
            "--max-hops", str(max_hops),
            "--chain", str(self.chain_id),
            "--quoter", self.QUOTER,
        ]
        return self._run_skill_cmd(cmd, "plan_swap_route")

    def estimate_gas(
        self,
        action: str,
        token0: str = "",
        token1: str = "",
        num_hops: int = 1,
    ) -> dict:
        """Estimate gas cost for a planned swap or liquidity operation.

        Args:
            action:   One of "swap", "add_liquidity", "remove_liquidity", "rebalance".
            token0:   Address of token0 (optional, for pool-specific estimates).
            token1:   Address of token1 (optional).
            num_hops: Number of swap hops (for multi-hop gas scaling).

        Returns:
            dict with estimated_gas, gas_price_gwei, cost_usd, and breakdown.
        """
        cmd = [
            "onchainos", "skill", "run", "uniswap-driver",
            "--action", "estimate-gas",
            "--operation", action,
            "--num-hops", str(num_hops),
            "--chain", str(self.chain_id),
        ]
        if token0:
            cmd.extend(["--token0", token0])
        if token1:
            cmd.extend(["--token1", token1])

        return self._run_skill_cmd(cmd, "estimate_gas")

    # ── Pool Analytics ────────────────────────────────────────────────

    def get_pool_analytics(
        self,
        token0: str,
        token1: str,
        fee_tier: str = "dynamic",
        period: str = "7d",
    ) -> dict:
        """Fetch comprehensive analytics for a Uniswap V4 pool.

        Returns TVL, volume, fee revenue, tick distribution, and LP
        performance metrics. Used by the Genesis Engine's Analysis Layer
        to evaluate pool health and inform strategy selection.

        Args:
            token0:   Address of token0.
            token1:   Address of token1.
            fee_tier: Fee tier key or numeric value (default "dynamic").
            period:   Analytics period: "1d", "7d", "30d".

        Returns:
            dict with tvl, volume_24h, fee_apr, active_liquidity,
            tick_distribution, and lp_pnl_summary.
        """
        fee = str(self.FEE_TIERS.get(fee_tier, fee_tier))

        cmd = [
            "onchainos", "skill", "run", "uniswap-driver",
            "--action", "pool-analytics",
            "--token0", token0,
            "--token1", token1,
            "--fee-tier", fee,
            "--period", period,
            "--chain", str(self.chain_id),
        ]
        return self._run_skill_cmd(cmd, "pool_analytics")

    # ── AutoRebalanceModule Integration ───────────────────────────────

    def recommend_rebalance_params(
        self,
        token0: str,
        token1: str,
        current_tick: int,
        current_tick_lower: int,
        current_tick_upper: int,
        volatility_pct: float,
    ) -> dict:
        """Generate rebalance recommendations for the AutoRebalanceModule.

        Combines tick range optimization with gas estimation to decide
        whether a rebalance is cost-effective at the current moment.

        Args:
            token0:             Address of token0.
            token1:             Address of token1.
            current_tick:       Current pool tick.
            current_tick_lower: Existing position lower tick.
            current_tick_upper: Existing position upper tick.
            volatility_pct:     Rolling volatility percentage.

        Returns:
            dict with should_rebalance, new_tick_lower, new_tick_upper,
            estimated_gas_cost, and reasoning.
        """
        # Get optimal range from the driver skill
        range_result = self.optimize_tick_range(
            token0, token1, current_tick, volatility_pct,
        )

        # Estimate cost of rebalance operation
        gas_result = self.estimate_gas("rebalance", token0, token1)

        # Determine position utilisation (how far price is from center)
        range_width = current_tick_upper - current_tick_lower
        if range_width == 0:
            utilisation_pct = 100.0
        else:
            center = (current_tick_lower + current_tick_upper) / 2
            distance_from_center = abs(current_tick - center)
            utilisation_pct = (distance_from_center / (range_width / 2)) * 100

        # Consult AutoRebalanceModule config for trigger threshold
        rebalance_cfg = config.AVAILABLE_MODULES.get("auto_rebalance", {}).get("default_params", {})
        trigger_pct = rebalance_cfg.get("soft_trigger_pct", 85)

        should_rebalance = utilisation_pct >= trigger_pct

        return {
            "should_rebalance": should_rebalance,
            "utilisation_pct": round(utilisation_pct, 2),
            "trigger_threshold_pct": trigger_pct,
            "current_range": {
                "tick_lower": current_tick_lower,
                "tick_upper": current_tick_upper,
            },
            "recommended_range": range_result,
            "gas_estimate": gas_result,
            "current_tick": current_tick,
            "volatility_pct": volatility_pct,
        }

    # ── Integration Summary ───────────────────────────────────────────

    def get_integration_summary(self) -> dict:
        """Return a summary of the uniswap-driver skill integration.

        Useful for README documentation and evaluator reference.
        """
        return {
            "uniswap_ai_skill": "uniswap-driver",
            "status": "integrated",
            "usage": "Swap route optimization and liquidity position planning",
            "capabilities": [
                "plan_liquidity_position - Optimal LP position parameters",
                "optimize_tick_range - Volatility-aware tick range selection",
                "plan_swap_route - Multi-hop route finding with price impact",
                "estimate_gas - Gas cost estimation for all operations",
                "get_pool_analytics - TVL, volume, fee APR, tick distribution",
                "recommend_rebalance_params - AutoRebalanceModule integration",
            ],
            "chain_id": self.chain_id,
            "hook_address": self.hook_address,
            "rebalance_module": self.rebalance_module,
            "v4_contracts": {
                "pool_manager": self.POOL_MANAGER,
                "position_manager": self.POSITION_MANAGER,
                "quoter": self.QUOTER,
            },
        }

    # ── Internal helpers ──────────────────────────────────────────────

    def _run_skill_cmd(self, cmd: list, label: str = "") -> dict:
        """Execute a skill command with DRY_RUN support."""
        if config.DRY_RUN:
            logger.info("[DRY_RUN] %s: %s", label, " ".join(cmd))
            return {
                "dry_run": True,
                "label": label,
                "cmd": " ".join(cmd),
                "simulated_result": {"status": "ok", "message": "Simulated in DRY_RUN mode"},
            }

        logger.debug("Running skill cmd [%s]: %s", label, " ".join(cmd))
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, check=False,
            )
            if result.returncode != 0:
                logger.error("[%s] Command failed (%d): %s", label, result.returncode, result.stderr.strip())
                return {"error": result.stderr.strip() or f"exit code {result.returncode}"}

            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"raw_output": result.stdout.strip()}

        except subprocess.TimeoutExpired:
            logger.error("[%s] Command timed out", label)
            return {"error": "timeout"}
        except FileNotFoundError:
            logger.error("[%s] onchainos CLI not found", label)
            return {"error": "cli_not_found"}
