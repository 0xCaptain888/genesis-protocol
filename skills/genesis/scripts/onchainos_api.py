"""Onchain OS REST API Client - stdlib-only alternative to subprocess CLI calls.

Uses urllib.request with HMAC-SHA256 authentication per OKX Web3 API docs.
Falls back to onchainos CLI subprocess when the REST API is unavailable.

Credentials loaded from environment variables:
    OK_ACCESS_KEY, OK_ACCESS_SECRET, OK_ACCESS_PASSPHRASE
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BASE_URL = "https://web3.okx.com"


class OnchainOSAPI:
    """REST API client for Onchain OS with CLI fallback."""

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
        base_url: str = BASE_URL,
        timeout: int = 30,
    ):
        self.api_key = api_key or os.environ.get("OK_ACCESS_KEY", "")
        self.api_secret = api_secret or os.environ.get("OK_ACCESS_SECRET", "")
        self.passphrase = passphrase or os.environ.get("OK_ACCESS_PASSPHRASE", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._has_credentials = bool(self.api_key and self.api_secret and self.passphrase)
        if not self._has_credentials:
            logger.warning(
                "OnchainOSAPI: missing API credentials; REST calls will fall back to CLI"
            )

    # ── Authentication ────────────────────────────────────────────────────

    def _sign(self, method: str, request_path: str, body: str = "") -> dict:
        """Build HMAC-SHA256 signed headers for an OKX Web3 API request."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        message = timestamp + method.upper() + request_path + body
        signature = base64.b64encode(
            hmac.new(
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

    # ── Low-level request helpers ─────────────────────────────────────────

    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict | None:
        """Execute an authenticated REST request. Returns parsed JSON or None."""
        if not self._has_credentials:
            logger.debug("No credentials; skipping REST request %s %s", method, path)
            return None

        request_path = path
        if params:
            request_path = path + "?" + urllib.parse.urlencode(params)

        body_str = json.dumps(body) if body else ""
        headers = self._sign(method.upper(), request_path, body_str)

        url = self.base_url + request_path

        try:
            req = urllib.request.Request(
                url,
                data=body_str.encode("utf-8") if body_str else None,
                headers=headers,
                method=method.upper(),
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                logger.debug("REST %s %s -> %s", method, path, data.get("code", "ok"))
                return data
        except urllib.error.HTTPError as exc:
            logger.error("REST HTTP %d for %s %s: %s", exc.code, method, path, exc.reason)
        except urllib.error.URLError as exc:
            logger.error("REST URL error for %s %s: %s", method, path, exc.reason)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("REST error for %s %s: %s", method, path, exc)
        return None

    def _cli_fallback(self, cmd: list[str]) -> dict | None:
        """Execute an onchainos CLI command as fallback. Returns parsed JSON or None."""
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

    def _request_with_fallback(self, method: str, path: str, cli_cmd: list[str],
                                params: dict | None = None, body: dict | None = None) -> dict | None:
        """Try REST API first; fall back to CLI subprocess on failure."""
        result = self._request(method, path, params=params, body=body)
        if result is not None:
            return result
        logger.info("REST unavailable for %s; falling back to CLI", path)
        return self._cli_fallback(cli_cmd)

    # ── Market Endpoints ──────────────────────────────────────────────────

    def get_price(self, base: str, quote: str, chain_id: str = "196") -> dict | None:
        """GET price data for a base/quote pair via the aggregator all-tokens endpoint."""
        path = "/api/v5/dex/aggregator/all-tokens"
        params = {"chainId": chain_id}
        cli_cmd = ["onchainos", "aggregator", "all-tokens", "--chain", chain_id]
        return self._request_with_fallback("GET", path, cli_cmd, params=params)

    # ── Trade Endpoints ───────────────────────────────────────────────────

    def get_dex_quote(self, token_in: str, token_out: str, amount: str, chain_id: str = "196", slippage: str = "50") -> dict | None:
        """GET a DEX swap quote."""
        path = "/api/v5/dex/aggregator/quote"
        params = {
            "fromTokenAddress": token_in, "toTokenAddress": token_out,
            "amount": amount, "chainId": chain_id, "slippage": slippage,
        }
        cli_cmd = [
            "onchainos", "aggregator", "quote",
            "--from-token", token_in, "--to-token", token_out,
            "--amount", amount, "--chain", chain_id, "--slippage", slippage,
        ]
        return self._request_with_fallback("GET", path, cli_cmd, params=params)

    def post_swap(self, token_in: str, token_out: str, amount: str, user_address: str,
                  chain_id: str = "196", slippage: str = "50") -> dict | None:
        """POST a DEX swap execution."""
        path = "/api/v5/dex/aggregator/swap"
        body = {
            "fromTokenAddress": token_in, "toTokenAddress": token_out,
            "amount": amount, "userWalletAddress": user_address,
            "chainId": chain_id, "slippage": slippage,
        }
        cli_cmd = [
            "onchainos", "aggregator", "swap",
            "--from-token", token_in, "--to-token", token_out,
            "--amount", amount, "--user", user_address,
            "--chain", chain_id, "--slippage", slippage,
        ]
        return self._request_with_fallback("POST", path, cli_cmd, body=body)

    # ── Wallet Endpoints ──────────────────────────────────────────────────

    def get_balances(self, address: str, chain_id: str = "196") -> dict | None:
        """GET wallet token balances."""
        path = "/api/v5/wallet/asset/token-balances-by-address"
        params = {"address": address, "chainId": chain_id}
        cli_cmd = ["onchainos", "wallet", "balances", "--address", address, "--chain", chain_id]
        return self._request_with_fallback("GET", path, cli_cmd, params=params)

    def get_portfolio(self, address: str) -> dict | None:
        """GET wallet portfolio overview (cross-chain)."""
        path = "/api/v5/dex/wallet/portfolio"
        params = {"address": address}
        cli_cmd = ["onchainos", "wallet", "portfolio", "--address", address]
        return self._request_with_fallback("GET", path, cli_cmd, params=params)
