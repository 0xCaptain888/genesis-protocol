"""Security Scanner -- token risk assessment via onchainos okx-security skill.

Scans tokens and pools for contract safety, liquidity depth, and rugpull
indicators before any strategy is deployed.  Uses subprocess to call the
onchainos CLI, following the same pattern as payment_handler.py and
strategy_manager.py.
"""
import json
import logging
import subprocess

from .config import DRY_RUN, CHAIN_ID, LOG_LEVEL

logger = logging.getLogger("genesis.security_scanner")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

# ── Risk-score thresholds ────────────────────────────────────────────────
_MAX_ACCEPTABLE_RISK = 50          # 0-100 scale; above this is "unsafe"
_SIMULATED_RISK_SCORE = 15         # benign default for DRY_RUN / simulations


class SecurityScanner:
    """Assess token and pool risk via the onchainos okx-security skill."""

    # ── Public API ───────────────────────────────────────────────────────

    def scan_token(self, address: str) -> dict:
        """Return a risk-score dict for a single token address.

        Keys: risk_score (int 0-100), flags (list[str]), safe (bool).
        """
        cmd = [
            "onchainos", "skill", "run", "okx-security",
            "--action", "token-risk",
            "--address", address,
            "--chain", str(CHAIN_ID),
        ]
        result = self._run_cmd(cmd)

        if result.get("error"):
            logger.warning("Security scan failed for %s: %s", address, result["error"])
            return {"risk_score": 100, "flags": ["scan_error"], "safe": False,
                    "error": result["error"]}

        try:
            data = json.loads(result["stdout"])
        except (json.JSONDecodeError, KeyError):
            logger.warning("Unparseable security response for %s", address)
            return {"risk_score": 100, "flags": ["parse_error"], "safe": False}

        risk_score = int(data.get("risk_score", 100))
        flags = list(data.get("flags", []))
        safe = risk_score <= _MAX_ACCEPTABLE_RISK
        return {"risk_score": risk_score, "flags": flags, "safe": safe}

    def scan_pool(self, token0: str, token1: str) -> dict:
        """Scan both tokens of a pool and return a combined risk dict.

        Keys: token0 (dict), token1 (dict), combined_risk (int), safe (bool).
        """
        t0_risk = self.scan_token(token0)
        t1_risk = self.scan_token(token1)
        combined = max(t0_risk["risk_score"], t1_risk["risk_score"])
        safe = t0_risk["safe"] and t1_risk["safe"]
        return {
            "token0": t0_risk,
            "token1": t1_risk,
            "combined_risk": combined,
            "safe": safe,
        }

    def is_safe_for_strategy(self, token0: str, token1: str) -> tuple:
        """Determine whether a token pair is safe enough for strategy deployment.

        Returns:
            (bool, str) -- (is_safe, human-readable reason)
        """
        pool_risk = self.scan_pool(token0, token1)

        if pool_risk["safe"]:
            reason = (
                f"Pool passed security scan "
                f"(combined_risk={pool_risk['combined_risk']})"
            )
            logger.info("Security OK for %s / %s: %s", token0, token1, reason)
            return True, reason

        # Build a descriptive rejection reason
        parts = []
        for label, tok in [("token0", pool_risk["token0"]),
                           ("token1", pool_risk["token1"])]:
            if not tok["safe"]:
                parts.append(
                    f"{label} risk={tok['risk_score']} flags={tok['flags']}"
                )
        reason = "Security check failed: " + "; ".join(parts)
        logger.warning("Security REJECT for %s / %s: %s", token0, token1, reason)
        return False, reason

    # ── Private helpers ──────────────────────────────────────────────────

    def _run_cmd(self, cmd):
        """Execute a subprocess command, respecting DRY_RUN."""
        logger.debug("cmd: %s", " ".join(cmd))
        if DRY_RUN:
            logger.info("[DRY_RUN] %s", " ".join(cmd))
            return {"stdout": json.dumps({
                "risk_score": _SIMULATED_RISK_SCORE,
                "flags": [],
                "dry_run": True,
            })}
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                return {"error": proc.stderr or f"exit code {proc.returncode}"}
            return {"stdout": proc.stdout}
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return {"error": str(exc)}
