"""Moltbook Identity Integration - Cross-platform identity verification for Genesis Protocol.

Provides identity token generation, verification, reputation querying, and
on-chain identity attestation via the Moltbook API. Uses aiohttp for async HTTP
with retry logic and proper error handling.

Credentials loaded from environment variables:
    MOLTBOOK_API_KEY, MOLTBOOK_APP_KEY
"""
import hashlib
import json
import logging
import os
import subprocess
import time

try:
    import aiohttp as _aiohttp
except ImportError:
    _aiohttp = None

from . import config

logger = logging.getLogger("genesis.moltbook_identity")
logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.0  # seconds


class MoltbookIdentityManager:
    """Manages Moltbook identity verification for Genesis Protocol agents.

    Integrates with the Moltbook API to generate and verify identity tokens,
    query agent reputation data, and attach identity attestations to Strategy NFTs.
    """

    def __init__(
        self,
        api_key: str = "",
        app_key: str = "",
        base_url: str = "",
    ):
        self.api_key = api_key or config.MOLTBOOK_API_KEY or os.environ.get("MOLTBOOK_API_KEY", "")
        self.app_key = app_key or config.MOLTBOOK_APP_KEY or os.environ.get("MOLTBOOK_APP_KEY", "")
        self.base_url = (base_url or config.MOLTBOOK_BASE_URL or "https://www.moltbook.com").rstrip("/")
        self._has_credentials = bool(self.api_key)
        self._session: "_aiohttp.ClientSession | None" = None
        self._identity_cache: dict = {}  # agent_name -> {profile, cached_at}
        if not self._has_credentials:
            logger.warning("MoltbookIdentityManager: missing API key; identity calls will be skipped")

    # ── Session Management ────────────────────────────────────────────────

    async def _get_session(self) -> "_aiohttp.ClientSession":
        """Get or create an aiohttp client session."""
        if _aiohttp is None:
            raise RuntimeError("aiohttp library is required for MoltbookIdentityManager")
        if self._session is None or self._session.closed:
            self._session = _aiohttp.ClientSession(
                headers=self._build_headers(),
                timeout=_aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def close(self):
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _build_headers(self) -> dict:
        """Build authentication headers for Moltbook API requests."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "genesis-protocol/2.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.app_key:
            headers["X-App-Key"] = self.app_key
        return headers

    # ── Low-level Request Helpers ─────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        params: dict | None = None,
    ) -> dict | None:
        """Execute an authenticated API request with retry logic.

        Retries up to MAX_RETRIES times with exponential backoff on transient
        errors (5xx, timeouts, connection errors).
        """
        if not self._has_credentials:
            logger.debug("No credentials; skipping Moltbook request %s %s", method, path)
            return None
        if _aiohttp is None:
            logger.error("aiohttp library not installed; cannot make Moltbook requests")
            return None

        url = self.base_url + path
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                session = await self._get_session()
                kwargs: dict = {}
                if body is not None:
                    kwargs["json"] = body
                if params is not None:
                    kwargs["params"] = params

                async with session.request(method.upper(), url, **kwargs) as resp:
                    data = await resp.json()
                    if resp.status >= 500 and attempt < MAX_RETRIES - 1:
                        wait = RETRY_BACKOFF_BASE * (2 ** attempt)
                        logger.warning(
                            "Moltbook %s %s returned %d; retrying in %.1fs (attempt %d/%d)",
                            method, path, resp.status, wait, attempt + 1, MAX_RETRIES,
                        )
                        import asyncio
                        await asyncio.sleep(wait)
                        continue
                    if resp.status >= 400:
                        logger.error(
                            "Moltbook %s %s failed: status=%d body=%s",
                            method, path, resp.status, json.dumps(data)[:200],
                        )
                        return {"error": True, "status": resp.status, "detail": data}
                    logger.debug("Moltbook %s %s -> OK", method, path)
                    return data

            except Exception as exc:
                last_error = exc
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        "Moltbook %s %s error: %s; retrying in %.1fs (attempt %d/%d)",
                        method, path, exc, wait, attempt + 1, MAX_RETRIES,
                    )
                    import asyncio
                    await asyncio.sleep(wait)

        logger.error("Moltbook %s %s failed after %d retries: %s", method, path, MAX_RETRIES, last_error)
        return None

    # ── Identity Token Operations ─────────────────────────────────────────

    async def generate_identity_token(self) -> dict:
        """Generate a temporary identity token for cross-platform authentication.

        POST /api/v1/agents/me/identity-token

        Returns:
            dict with keys: token, expires_at, agent_id.
            On failure returns dict with 'error' key.
        """
        result = await self._request("POST", "/api/v1/agents/me/identity-token")
        if result is None:
            return {"error": "Failed to generate identity token"}
        if result.get("error"):
            return result
        logger.info(
            "Generated identity token for agent=%s (expires=%s)",
            result.get("agent_id", "?"),
            result.get("expires_at", "?"),
        )
        return result

    async def verify_agent_identity(self, identity_token: str) -> dict:
        """Verify another agent's identity token.

        POST /api/v1/agents/verify-identity

        Args:
            identity_token: The token string to verify.

        Returns:
            dict with keys: valid (bool), agent (dict with id, name, karma, avatar_url, ...).
            On failure returns dict with 'error' key.
        """
        if not identity_token:
            return {"error": "identity_token is required", "valid": False}
        result = await self._request(
            "POST",
            "/api/v1/agents/verify-identity",
            body={"token": identity_token},
        )
        if result is None:
            return {"error": "Verification request failed", "valid": False}
        if result.get("error"):
            result["valid"] = False
            return result
        logger.info(
            "Verified identity: valid=%s agent=%s",
            result.get("valid", False),
            result.get("agent", {}).get("name", "?"),
        )
        return result

    # ── Profile & Reputation ──────────────────────────────────────────────

    async def get_agent_profile(self, agent_name: str = None) -> dict:
        """Get agent profile including reputation data.

        GET /api/v1/agents/me  (for self)
        GET /api/v1/agents/profile/{name}  (for other agents)

        Args:
            agent_name: Name of the agent to look up. None for self.

        Returns:
            dict with agent profile data including id, name, karma, avatar_url,
            followers_count, post_count, comment_count.
        """
        # Check cache first
        cache_key = agent_name or "_self"
        cached = self._identity_cache.get(cache_key)
        if cached and (time.time() - cached["cached_at"]) < 300:
            logger.debug("Cache hit for agent profile: %s", cache_key)
            return cached["profile"]

        if agent_name:
            path = f"/api/v1/agents/profile/{agent_name}"
        else:
            path = "/api/v1/agents/me"

        result = await self._request("GET", path)
        if result is None:
            return {"error": f"Failed to fetch profile for {cache_key}"}
        if result.get("error"):
            return result

        # Cache the result
        self._identity_cache[cache_key] = {
            "profile": result,
            "cached_at": time.time(),
        }
        logger.info("Fetched profile for %s (karma=%s)", cache_key, result.get("karma", "?"))
        return result

    async def get_reputation_score(self, agent_name: str = None) -> dict:
        """Calculate composite reputation score from Moltbook data.

        Combines karma, follower count, post count, and comment count into
        a normalized trust_score (0-100).

        Args:
            agent_name: Name of the agent. None for self.

        Returns:
            dict with keys: karma, followers, posts, comments, trust_score (0-100).
        """
        profile = await self.get_agent_profile(agent_name)
        if profile.get("error"):
            return {"error": profile["error"], "trust_score": 0}

        karma = int(profile.get("karma", 0))
        followers = int(profile.get("followers_count", 0))
        posts = int(profile.get("post_count", 0))
        comments = int(profile.get("comment_count", 0))

        # Composite trust score calculation:
        # - Karma: 40% weight, log-scaled, max contribution at 10000
        # - Followers: 25% weight, log-scaled, max contribution at 1000
        # - Posts: 20% weight, log-scaled, max contribution at 500
        # - Comments: 15% weight, log-scaled, max contribution at 1000
        import math
        karma_score = min(math.log1p(karma) / math.log1p(10000), 1.0) * 40
        follower_score = min(math.log1p(followers) / math.log1p(1000), 1.0) * 25
        post_score = min(math.log1p(posts) / math.log1p(500), 1.0) * 20
        comment_score = min(math.log1p(comments) / math.log1p(1000), 1.0) * 15

        trust_score = round(karma_score + follower_score + post_score + comment_score, 1)
        trust_score = max(0, min(100, trust_score))

        result = {
            "karma": karma,
            "followers": followers,
            "posts": posts,
            "comments": comments,
            "trust_score": trust_score,
        }
        logger.info("Reputation for %s: trust_score=%.1f", agent_name or "self", trust_score)
        return result

    # ── On-chain Identity Attestation ─────────────────────────────────────

    def compute_identity_hash(self, agent_id: str, karma: int, verified_at: int) -> str:
        """Compute keccak256 hash for on-chain identity attestation.

        The hash is computed over the ABI-encoded (agent_id, karma, verified_at)
        tuple, matching the MoltbookIdentityModule's on-chain verification logic.

        Args:
            agent_id: Moltbook agent identifier string.
            karma: Agent's karma score at time of attestation.
            verified_at: Unix timestamp of verification.

        Returns:
            0x-prefixed hex string of the keccak256 hash.
        """
        # ABI-encode: string agent_id, uint256 karma, uint256 verified_at
        payload = json.dumps(
            {"agent_id": agent_id, "karma": karma, "verified_at": verified_at},
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            from hashlib import sha3_256  # keccak256 equivalent in stdlib
            digest = sha3_256(payload.encode("utf-8")).hexdigest()
        except ImportError:
            # Fallback to sha256 if sha3 is not available
            digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            logger.warning("sha3_256 not available; using sha256 fallback for identity hash")
        return "0x" + digest

    async def attest_strategy_nft(self, token_id: int, assembler_address: str = "") -> dict:
        """Attach Moltbook identity attestation to a Strategy NFT.

        Fetches the agent's profile and reputation, computes an identity hash,
        and calls the MoltbookIdentityModule contract to record the attestation
        on-chain via onchainos CLI.

        Args:
            token_id: The Strategy NFT token ID to attest.
            assembler_address: Optional override for the assembler contract address.

        Returns:
            dict with attestation result including identity_hash and trust_score.
        """
        assembler = assembler_address or config.CONTRACTS.get("assembler", "")
        identity_module = getattr(config, "MOLTBOOK_IDENTITY_MODULE_ADDRESS", "")

        # Fetch agent profile and compute attestation data
        profile = await self.get_agent_profile()
        if profile.get("error"):
            return {"error": f"Cannot attest: {profile['error']}"}

        reputation = await self.get_reputation_score()
        agent_id = str(profile.get("id", ""))
        karma = int(profile.get("karma", 0))
        verified_at = int(time.time())

        identity_hash = self.compute_identity_hash(agent_id, karma, verified_at)

        # Build on-chain attestation call
        if config.DRY_RUN:
            logger.info(
                "[DRY_RUN] attest_strategy_nft: token_id=%d identity_hash=%s trust_score=%.1f",
                token_id, identity_hash, reputation.get("trust_score", 0),
            )
            return {
                "dry_run": True,
                "token_id": token_id,
                "identity_hash": identity_hash,
                "trust_score": reputation.get("trust_score", 0),
                "agent_id": agent_id,
                "karma": karma,
                "verified_at": verified_at,
            }

        if not identity_module:
            logger.warning("MOLTBOOK_IDENTITY_MODULE_ADDRESS not configured; skipping on-chain attestation")
            return {
                "error": "MoltbookIdentityModule address not configured",
                "identity_hash": identity_hash,
                "trust_score": reputation.get("trust_score", 0),
            }

        # Execute on-chain attestation via onchainos CLI
        cmd = [
            "onchainos", "wallet", "call",
            "--to", identity_module,
            "--function", "attestIdentity(uint256,bytes32,uint256,uint256)",
            "--args", f"{token_id} {identity_hash} {karma} {verified_at}",
        ]
        result = self._run_cmd(cmd)
        if result.get("error"):
            return {"error": result["error"], "identity_hash": identity_hash}

        logger.info(
            "Identity attestation recorded: token_id=%d identity_hash=%s trust_score=%.1f",
            token_id, identity_hash, reputation.get("trust_score", 0),
        )
        return {
            "token_id": token_id,
            "identity_hash": identity_hash,
            "trust_score": reputation.get("trust_score", 0),
            "agent_id": agent_id,
            "karma": karma,
            "verified_at": verified_at,
            "tx_result": result,
        }

    # ── Utility ───────────────────────────────────────────────────────────

    @staticmethod
    def _run_cmd(cmd: list[str]) -> dict:
        """Execute a subprocess command. Returns dict with stdout or error."""
        logger.debug("cmd: %s", " ".join(cmd))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
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
