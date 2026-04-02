"""Payment Handler - x402 payment processing with pay-with-any-token support.

Integrates the Uniswap pay-with-any-token skill to allow agents to pay for
Genesis services using any ERC-20 token. The skill automatically swaps the
payer's token to USDT via Uniswap before settling the x402 payment.

Uses onchainos CLI and Uniswap AI Skills via subprocess for all operations.
"""
import subprocess
import json
import logging
import time

from config import (
    DRY_RUN, LOG_LEVEL, X402_ENABLED, X402_PRICING,
    CONTRACTS, CHAIN_ID, WALLET_ROLES,
)

logger = logging.getLogger("genesis.payment_handler")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))


class PaymentHandler:
    """Handles x402 payments with automatic token swap via pay-with-any-token."""

    SUPPORTED_QUOTE_TOKEN = "USDT"

    def __init__(self, income_wallet_index=None):
        self.income_wallet_index = income_wallet_index or WALLET_ROLES["income"]["index"]
        self.enabled = X402_ENABLED

    def get_pricing(self):
        """Return the x402 pricing tiers."""
        return X402_PRICING

    def process_payment(self, product, payer_token, payer_address):
        """Process an x402 payment, auto-swapping payer's token to USDT if needed.

        Args:
            product: One of 'signal_query', 'strategy_subscribe',
                     'strategy_params_buy', 'nft_license'
            payer_token: The ERC-20 token symbol the payer wants to use
            payer_address: The payer's wallet address

        Returns:
            dict with 'success', 'tx_hash', 'amount_usdt', 'swap_details'
        """
        if not self.enabled:
            return {"success": False, "error": "x402 payments disabled"}

        tier = X402_PRICING.get(product)
        if not tier:
            return {"success": False, "error": f"Unknown product: {product}"}

        amount_usdt = tier["amount"]
        settle_mode = tier["settle"]

        logger.info(
            "Processing x402 payment: product=%s amount=%s USDT payer_token=%s",
            product, amount_usdt, payer_token,
        )

        # If payer is already paying in USDT, skip the swap
        if payer_token.upper() == self.SUPPORTED_QUOTE_TOKEN:
            logger.info("Payer using USDT directly — no swap needed")
            result = self._settle_x402(
                payer_address, amount_usdt, settle_mode,
            )
            return {
                "success": not result.get("error"),
                "amount_usdt": amount_usdt,
                "swap_details": None,
                **result,
            }

        # Use pay-with-any-token to swap payer's token → USDT
        swap_result = self._swap_to_usdt(
            payer_token, amount_usdt, payer_address,
        )

        if swap_result.get("error"):
            logger.error("Token swap failed: %s", swap_result["error"])
            return {"success": False, "error": swap_result["error"]}

        # Settle the x402 payment with the swapped USDT
        settle_result = self._settle_x402(
            payer_address, amount_usdt, settle_mode,
        )

        return {
            "success": not settle_result.get("error"),
            "amount_usdt": amount_usdt,
            "swap_details": swap_result,
            **settle_result,
        }

    def _swap_to_usdt(self, from_token, usdt_amount, payer_address):
        """Use pay-with-any-token skill to swap any token to USDT.

        This calls the Uniswap pay-with-any-token skill which handles:
        1. Quote the exact input amount needed in from_token
        2. Approve the Uniswap router
        3. Execute the swap via Uniswap V4
        4. Deliver exact USDT amount to the income wallet
        """
        cmd = [
            "onchainos", "skill", "run", "pay-with-any-token",
            "--from-token", from_token,
            "--to-token", self.SUPPORTED_QUOTE_TOKEN,
            "--amount", usdt_amount,
            "--amount-type", "exactOutput",
            "--recipient", self._get_income_address(),
            "--payer", payer_address,
            "--chain", str(CHAIN_ID),
            "--slippage", "50",  # 0.5% slippage
        ]

        result = self._run_cmd(cmd)

        if result.get("error"):
            return result

        try:
            data = json.loads(result["stdout"])
            return {
                "from_token": from_token,
                "from_amount": data.get("inputAmount", "unknown"),
                "to_token": self.SUPPORTED_QUOTE_TOKEN,
                "to_amount": usdt_amount,
                "tx_hash": data.get("txHash", ""),
                "route": data.get("route", ""),
            }
        except (json.JSONDecodeError, KeyError):
            return {"from_token": from_token, "to_amount": usdt_amount, "raw": result["stdout"]}

    def _settle_x402(self, payer_address, amount, settle_mode):
        """Settle the x402 payment via onchainos payment module."""
        cmd = [
            "onchainos", "payment", "settle",
            "--protocol", "x402",
            "--payer", payer_address,
            "--amount", amount,
            "--token", self.SUPPORTED_QUOTE_TOKEN,
            "--recipient-wallet-index", str(self.income_wallet_index),
            "--mode", settle_mode,
        ]

        result = self._run_cmd(cmd)

        if result.get("error"):
            return result

        try:
            data = json.loads(result["stdout"])
            return {"tx_hash": data.get("txHash", ""), "settled": True}
        except (json.JSONDecodeError, KeyError):
            return {"raw": result["stdout"], "settled": True}

    def _get_income_address(self):
        """Get the income wallet address via onchainos."""
        cmd = [
            "onchainos", "wallet", "address",
            "--index", str(self.income_wallet_index),
        ]
        result = self._run_cmd(cmd)
        if result.get("error"):
            return ""
        return result["stdout"].strip()

    def estimate_swap(self, from_token, product):
        """Estimate how much of from_token is needed to pay for a product.

        Returns the estimated input amount without executing.
        """
        tier = X402_PRICING.get(product)
        if not tier:
            return {"error": f"Unknown product: {product}"}

        if from_token.upper() == self.SUPPORTED_QUOTE_TOKEN:
            return {"from_token": from_token, "amount": tier["amount"], "swap_needed": False}

        cmd = [
            "onchainos", "skill", "run", "pay-with-any-token",
            "--from-token", from_token,
            "--to-token", self.SUPPORTED_QUOTE_TOKEN,
            "--amount", tier["amount"],
            "--amount-type", "exactOutput",
            "--chain", str(CHAIN_ID),
            "--quote-only",
        ]

        result = self._run_cmd(cmd)

        if result.get("error"):
            return result

        try:
            data = json.loads(result["stdout"])
            return {
                "from_token": from_token,
                "amount": data.get("inputAmount", "unknown"),
                "usdt_amount": tier["amount"],
                "swap_needed": True,
                "route": data.get("route", ""),
            }
        except (json.JSONDecodeError, KeyError):
            return {"raw": result["stdout"]}

    def _run_cmd(self, cmd, dry_run=None):
        """Execute a subprocess command, respecting DRY_RUN config."""
        if dry_run is None:
            dry_run = DRY_RUN
        logger.debug("cmd: %s", " ".join(cmd))
        if dry_run:
            logger.info("[DRY_RUN] %s", " ".join(cmd))
            return {"stdout": json.dumps({
                "dry_run": True,
                "inputAmount": "0.001",
                "txHash": "0x" + "0" * 64,
                "route": "simulated",
            })}
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                logger.error("Command failed (%d): %s", proc.returncode, proc.stderr)
                return {"error": proc.stderr or f"exit code {proc.returncode}"}
            return {"stdout": proc.stdout}
        except subprocess.TimeoutExpired:
            logger.error("Command timed out: %s", " ".join(cmd))
            return {"error": "timeout"}
        except FileNotFoundError:
            logger.error("onchainos CLI not found")
            return {"error": "onchainos CLI not found"}
