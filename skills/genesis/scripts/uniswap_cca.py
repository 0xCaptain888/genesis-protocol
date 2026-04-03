"""Uniswap CCA (Conditional Contingent Auction) Skill Integration.

Integrates the uniswap-cca Uniswap AI skill for MEV-aware auction
mechanisms within the Genesis Protocol. When the MEV Protection Module
detects extractable value, CCA auctions can capture that value for LPs
instead of losing it to searchers.

Reference: https://github.com/Uniswap/uniswap-ai
"""

import json
import logging
import subprocess
from typing import Optional

from . import config

logger = logging.getLogger(__name__)


class UniswapCCAClient:
    """Client for the uniswap-cca (Conditional Contingent Auction) skill on X Layer.

    CCA enables MEV recapture by routing extractable value through a sealed-bid
    auction. Genesis strategies use this to convert detected MEV opportunities
    into LP revenue rather than surrendering value to external searchers.

    Typical flow:
        1. MEV Protection Module detects sandwich / arbitrage opportunity
        2. Genesis Engine calls create_auction() with opportunity parameters
        3. Searchers compete via place_bid()
        4. Winning bid is settled via settle_auction(), proceeds go to LPs
    """

    # Default auction parameters tuned for X Layer block times (~1 s)
    DEFAULT_AUCTION_DURATION_BLOCKS = 5
    DEFAULT_MIN_BID_WEI = "1000000000000000"  # 0.001 ETH equivalent

    def __init__(self, chain_id: int = 0, rpc_url: str = ""):
        self.chain_id = chain_id or config.CHAIN_ID
        self.rpc_url = rpc_url or config.RPC_URL
        self.hook_address = config.CONTRACTS.get("v4_hook", "")
        self.mev_module_address = config.CONTRACTS.get("mev_protection_module", "")

    # ── Auction Lifecycle ─────────────────────────────────────────────

    def create_auction(
        self,
        opportunity_type: str,
        token_in: str,
        token_out: str,
        amount: str,
        duration_blocks: int = 0,
        min_bid: str = "",
        pool_key: Optional[dict] = None,
    ) -> dict:
        """Create a new CCA auction for a detected MEV opportunity.

        Args:
            opportunity_type: One of "sandwich", "arbitrage", "backrun".
            token_in:         Address of the input token involved.
            token_out:        Address of the output token involved.
            amount:           Estimated extractable value in wei.
            duration_blocks:  Auction duration in blocks (default 5).
            min_bid:          Minimum bid amount in wei.
            pool_key:         Optional V4 PoolKey dict scoping the auction.

        Returns:
            dict with auction_id, status, and parameters (or dry_run payload).
        """
        duration = duration_blocks or self.DEFAULT_AUCTION_DURATION_BLOCKS
        bid_floor = min_bid or self.DEFAULT_MIN_BID_WEI

        cmd = [
            "onchainos", "skill", "run", "uniswap-cca",
            "--action", "create-auction",
            "--opportunity-type", opportunity_type,
            "--token-in", token_in,
            "--token-out", token_out,
            "--amount", amount,
            "--duration-blocks", str(duration),
            "--min-bid", bid_floor,
            "--chain", str(self.chain_id),
            "--hook", self.hook_address,
        ]
        if pool_key:
            cmd.extend(["--pool-key", json.dumps(pool_key)])

        return self._run_skill_cmd(cmd, "cca_create_auction")

    def place_bid(
        self,
        auction_id: str,
        bid_amount: str,
        bidder_address: str,
        execution_payload: str = "",
    ) -> dict:
        """Place a sealed bid on an active CCA auction.

        Args:
            auction_id:        Identifier returned by create_auction().
            bid_amount:        Bid amount in wei.
            bidder_address:    Address of the bidder.
            execution_payload: Optional calldata the bidder commits to execute.

        Returns:
            dict with bid confirmation or error details.
        """
        cmd = [
            "onchainos", "skill", "run", "uniswap-cca",
            "--action", "place-bid",
            "--auction-id", auction_id,
            "--bid-amount", bid_amount,
            "--bidder", bidder_address,
            "--chain", str(self.chain_id),
        ]
        if execution_payload:
            cmd.extend(["--execution-payload", execution_payload])

        return self._run_skill_cmd(cmd, "cca_place_bid")

    def settle_auction(self, auction_id: str, settler_address: str = "") -> dict:
        """Settle a completed CCA auction and distribute proceeds.

        The winning bid amount is routed to the Genesis hook's LP fee
        accumulator, increasing returns for liquidity providers.

        Args:
            auction_id:       Identifier of the auction to settle.
            settler_address:  Address triggering settlement (optional).

        Returns:
            dict with settlement result including winning bid and distribution.
        """
        cmd = [
            "onchainos", "skill", "run", "uniswap-cca",
            "--action", "settle",
            "--auction-id", auction_id,
            "--chain", str(self.chain_id),
            "--hook", self.hook_address,
        ]
        if settler_address:
            cmd.extend(["--settler", settler_address])

        return self._run_skill_cmd(cmd, "cca_settle_auction")

    def get_auction_status(self, auction_id: str) -> dict:
        """Query the current status of a CCA auction.

        Args:
            auction_id: Identifier of the auction to query.

        Returns:
            dict with status ("open", "closed", "settled"), bid count,
            current highest bid, and time remaining.
        """
        cmd = [
            "onchainos", "skill", "run", "uniswap-cca",
            "--action", "status",
            "--auction-id", auction_id,
            "--chain", str(self.chain_id),
        ]
        return self._run_skill_cmd(cmd, "cca_auction_status")

    # ── Genesis Strategy Integration ──────────────────────────────────

    def handle_mev_opportunity(
        self,
        opportunity_type: str,
        token_in: str,
        token_out: str,
        estimated_value: str,
        pool_key: Optional[dict] = None,
    ) -> dict:
        """High-level helper called by the MEV Protection Module.

        When Genesis detects an MEV opportunity during beforeSwap, this
        method creates a CCA auction to capture the value for LPs.

        Args:
            opportunity_type: "sandwich", "arbitrage", or "backrun".
            token_in:         Input token address.
            token_out:        Output token address.
            estimated_value:  Estimated extractable value in wei.
            pool_key:         V4 PoolKey identifying the target pool.

        Returns:
            dict with auction_id and creation status.
        """
        logger.info(
            "MEV opportunity detected [%s]: ~%s wei on %s -> %s",
            opportunity_type, estimated_value, token_in, token_out,
        )
        return self.create_auction(
            opportunity_type=opportunity_type,
            token_in=token_in,
            token_out=token_out,
            amount=estimated_value,
            pool_key=pool_key,
        )

    # ── Integration Summary ───────────────────────────────────────────

    def get_integration_summary(self) -> dict:
        """Return a summary of the uniswap-cca skill integration.

        Useful for README documentation and evaluator reference.
        """
        return {
            "uniswap_ai_skill": "uniswap-cca",
            "status": "integrated",
            "usage": "Conditional Contingent Auctions for MEV recapture",
            "capabilities": [
                "create_auction - Open a sealed-bid auction for detected MEV",
                "place_bid - Submit bids on open auctions",
                "settle_auction - Finalize auction and distribute proceeds to LPs",
                "get_auction_status - Query auction state",
                "handle_mev_opportunity - High-level MEV Protection Module hook",
            ],
            "chain_id": self.chain_id,
            "hook_address": self.hook_address,
            "mev_module_address": self.mev_module_address,
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
