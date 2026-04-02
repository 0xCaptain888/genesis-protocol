"""Wallet Manager - Agentic Wallet sub-wallets on X Layer (chainId 196).

All writes go through the `onchainos` CLI via subprocess. Respects DRY_RUN.
"""

import subprocess
import json
import logging
import os

from . import config

logger = logging.getLogger(__name__)


class WalletManager:
    """Manages onchainos sub-wallets mapped to operational roles."""

    def __init__(self):
        """Initialize wallet manager from config.WALLET_ROLES."""
        self.roles = config.WALLET_ROLES
        self.initialized: set[str] = set()
        logger.info("WalletManager created with roles: %s", list(self.roles.keys()))

    # ── Public API ───────────────────────────────────────────────────────

    def initialize_wallets(self) -> dict[str, dict]:
        """Create a sub-wallet for every defined role.

        Returns a dict mapping role names to their creation results.
        """
        results: dict[str, dict] = {}
        for role, meta in self.roles.items():
            idx = meta["index"]
            logger.info("Creating sub-wallet role=%s index=%d", role, idx)
            out = self._run_cmd([
                "onchainos", "wallet", "create-sub",
                "--index", str(idx),
                "--label", role,
            ])
            if "error" not in out:
                self.initialized.add(role)
            results[role] = out
        return results

    def get_wallet_address(self, role: str) -> dict:
        """Return the on-chain address for *role*.

        Args:
            role: A key from WALLET_ROLES (e.g. 'master', 'strategy').
        """
        idx = self._role_index(role)
        if idx is None:
            return {"error": f"Unknown role: {role}"}
        return self._run_cmd([
            "onchainos", "wallet", "address",
            "--index", str(idx),
        ])

    def get_balance(self, role: str, token: str = "native") -> dict:
        """Query the balance for *role*.

        Args:
            role:  Wallet role name.
            token: Token symbol or 'native' for OKB gas token.
        """
        idx = self._role_index(role)
        if idx is None:
            return {"error": f"Unknown role: {role}"}
        return self._run_cmd([
            "onchainos", "wallet", "balance",
            "--index", str(idx),
            "--token", token,
        ])

    def transfer(
        self,
        from_role: str,
        to_role: str,
        amount: str,
        token: str = "OKB",
    ) -> dict:
        """Transfer *amount* of *token* between two sub-wallets.

        Args:
            from_role: Source wallet role.
            to_role:   Destination wallet role.
            amount:    Human-readable amount (e.g. '1.5').
            token:     Token symbol (default OKB).
        """
        from_idx = self._role_index(from_role)
        to_idx = self._role_index(to_role)
        if from_idx is None or to_idx is None:
            return {"error": f"Invalid role(s): {from_role}, {to_role}"}

        logger.info(
            "Transfer %s %s: %s (idx %d) -> %s (idx %d)",
            amount, token, from_role, from_idx, to_role, to_idx,
        )
        return self._run_cmd([
            "onchainos", "wallet", "transfer",
            "--from-index", str(from_idx),
            "--to-index", str(to_idx),
            "--amount", str(amount),
            "--token", token,
        ])

    def fund_strategy_wallet(self, amount: str, token: str = "USDT") -> dict:
        """Move funds from master wallet to strategy wallet.

        Args:
            amount: Human-readable amount to transfer.
            token:  Token symbol (default USDT).
        """
        logger.info("Funding strategy wallet: %s %s", amount, token)
        return self.transfer("master", "strategy", amount, token=token)

    def collect_income(self) -> dict:
        """Sweep the full balance of the income wallet back to master.

        Queries the income wallet balance first, then transfers if non-zero.
        """
        logger.info("Collecting income -> master")
        bal = self.get_balance("income", token="USDT")
        amount = bal.get("balance", bal.get("amount", "0"))
        if float(amount) <= 0:
            logger.info("Income wallet empty, nothing to collect")
            return {"status": "empty", "amount": "0"}
        return self.transfer("income", "master", str(amount), token="USDT")

    def get_all_balances(self) -> dict[str, dict]:
        """Return a balance snapshot for every wallet role.

        Returns:
            Dict keyed by role name, each value is the balance response.
        """
        balances: dict[str, dict] = {}
        for role in self.roles:
            balances[role] = self.get_balance(role)
        return balances

    # ── Internal Helpers ─────────────────────────────────────────────────

    def _role_index(self, role: str) -> int | None:
        """Resolve a role name to its sub-wallet index."""
        meta = self.roles.get(role)
        return meta["index"] if meta else None

    def _run_cmd(self, cmd: list[str], dry_run: bool | None = None) -> dict:
        """Execute an onchainos CLI command and return parsed JSON.

        Args:
            cmd:     Command tokens (e.g. ['onchainos', 'wallet', 'balance', ...]).
            dry_run: Override config.DRY_RUN for this call. None = use config.

        Returns:
            Parsed JSON dict from stdout, or an error dict on failure.
        """
        is_dry = config.DRY_RUN if dry_run is None else dry_run
        is_write = any(
            tok in cmd for tok in ("create-sub", "transfer", "deploy", "send")
        )

        if is_dry and is_write:
            logger.info("[DRY_RUN] Would execute: %s", " ".join(cmd))
            return {"dry_run": True, "cmd": " ".join(cmd)}

        logger.debug("Executing: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode != 0:
                logger.error(
                    "Command failed (rc=%d): %s\nstderr: %s",
                    result.returncode, " ".join(cmd), result.stderr.strip(),
                )
                return {
                    "error": "command_failed",
                    "returncode": result.returncode,
                    "stderr": result.stderr.strip(),
                }
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            logger.error("Command timed out: %s", " ".join(cmd))
            return {"error": "timeout", "cmd": " ".join(cmd)}
        except json.JSONDecodeError:
            logger.error("Non-JSON output from: %s", " ".join(cmd))
            return {"error": "invalid_json", "stdout": result.stdout.strip()}
        except FileNotFoundError:
            logger.error("onchainos CLI not found on PATH")
            return {"error": "cli_not_found"}
        except OSError as exc:
            logger.error("OS error running command: %s", exc)
            return {"error": "os_error", "detail": str(exc)}
