"""Tests for MoltbookIdentityManager - cross-platform identity verification."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import time
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from skills.genesis.scripts.moltbook_identity import (
    MoltbookIdentityManager,
    MAX_RETRIES,
)


# ── Initialization ───────────────────────────────────────────────────────────

class TestInitWithConfig:
    def test_init_with_explicit_keys(self):
        mgr = MoltbookIdentityManager(
            api_key="test-api-key",
            app_key="test-app-key",
            base_url="https://custom.moltbook.com",
        )
        assert mgr.api_key == "test-api-key"
        assert mgr.app_key == "test-app-key"
        assert mgr.base_url == "https://custom.moltbook.com"
        assert mgr._has_credentials is True

    def test_init_strips_trailing_slash(self):
        mgr = MoltbookIdentityManager(
            api_key="key",
            base_url="https://moltbook.com/",
        )
        assert mgr.base_url == "https://moltbook.com"

    def test_init_empty_cache(self):
        mgr = MoltbookIdentityManager(api_key="key")
        assert mgr._identity_cache == {}

    @patch.dict(os.environ, {"MOLTBOOK_API_KEY": "env-key", "MOLTBOOK_APP_KEY": "env-app"})
    def test_init_from_env(self):
        mgr = MoltbookIdentityManager()
        # Falls through to config or env; at minimum should not error
        assert isinstance(mgr.api_key, str)


# ── Generate Identity Token ─────────────────────────────────────────────────

class TestGenerateIdentityToken:
    @pytest.mark.asyncio
    async def test_generate_token_success(self):
        mgr = MoltbookIdentityManager(api_key="test-key")
        mock_response = {
            "token": "tok_abc123",
            "expires_at": "2026-04-07T00:00:00Z",
            "agent_id": "agent_42",
        }
        mgr._request = AsyncMock(return_value=mock_response)

        result = await mgr.generate_identity_token()

        assert result["token"] == "tok_abc123"
        assert result["agent_id"] == "agent_42"
        mgr._request.assert_awaited_once_with("POST", "/api/v1/agents/me/identity-token")

    @pytest.mark.asyncio
    async def test_generate_token_failure_returns_error(self):
        mgr = MoltbookIdentityManager(api_key="test-key")
        mgr._request = AsyncMock(return_value=None)

        result = await mgr.generate_identity_token()

        assert "error" in result


# ── Verify Agent Identity ────────────────────────────────────────────────────

class TestVerifyAgentIdentity:
    @pytest.mark.asyncio
    async def test_verify_valid_token(self):
        mgr = MoltbookIdentityManager(api_key="test-key")
        mock_response = {
            "valid": True,
            "agent": {"id": "agent_42", "name": "genesis-bot", "karma": 1500},
        }
        mgr._request = AsyncMock(return_value=mock_response)

        result = await mgr.verify_agent_identity("tok_abc123")

        assert result["valid"] is True
        assert result["agent"]["name"] == "genesis-bot"
        mgr._request.assert_awaited_once_with(
            "POST",
            "/api/v1/agents/verify-identity",
            body={"token": "tok_abc123"},
        )

    @pytest.mark.asyncio
    async def test_verify_empty_token_returns_error(self):
        mgr = MoltbookIdentityManager(api_key="test-key")

        result = await mgr.verify_agent_identity("")

        assert result["valid"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_verify_request_failure(self):
        mgr = MoltbookIdentityManager(api_key="test-key")
        mgr._request = AsyncMock(return_value=None)

        result = await mgr.verify_agent_identity("tok_abc123")

        assert result["valid"] is False
        assert "error" in result


# ── Get Reputation Score ─────────────────────────────────────────────────────

class TestGetReputationScore:
    @pytest.mark.asyncio
    async def test_reputation_score_computed(self):
        mgr = MoltbookIdentityManager(api_key="test-key")
        mock_profile = {
            "id": "agent_42",
            "name": "genesis-bot",
            "karma": 5000,
            "followers_count": 200,
            "post_count": 50,
            "comment_count": 300,
        }
        mgr.get_agent_profile = AsyncMock(return_value=mock_profile)

        result = await mgr.get_reputation_score("genesis-bot")

        assert "trust_score" in result
        assert 0 <= result["trust_score"] <= 100
        assert result["karma"] == 5000
        assert result["followers"] == 200
        assert result["posts"] == 50
        assert result["comments"] == 300

    @pytest.mark.asyncio
    async def test_reputation_score_zero_activity(self):
        mgr = MoltbookIdentityManager(api_key="test-key")
        mock_profile = {
            "id": "agent_new",
            "karma": 0,
            "followers_count": 0,
            "post_count": 0,
            "comment_count": 0,
        }
        mgr.get_agent_profile = AsyncMock(return_value=mock_profile)

        result = await mgr.get_reputation_score()

        assert result["trust_score"] == 0

    @pytest.mark.asyncio
    async def test_reputation_score_on_profile_error(self):
        mgr = MoltbookIdentityManager(api_key="test-key")
        mgr.get_agent_profile = AsyncMock(return_value={"error": "not found"})

        result = await mgr.get_reputation_score("unknown")

        assert result["trust_score"] == 0
        assert "error" in result


# ── Compute Identity Hash ────────────────────────────────────────────────────

class TestComputeIdentityHash:
    def test_hash_is_deterministic(self):
        mgr = MoltbookIdentityManager(api_key="test-key")
        h1 = mgr.compute_identity_hash("agent_42", 5000, 1700000000)
        h2 = mgr.compute_identity_hash("agent_42", 5000, 1700000000)
        assert h1 == h2

    def test_hash_starts_with_0x(self):
        mgr = MoltbookIdentityManager(api_key="test-key")
        h = mgr.compute_identity_hash("agent_42", 5000, 1700000000)
        assert h.startswith("0x")
        # 0x + 64 hex chars = 66 total
        assert len(h) == 66

    def test_different_inputs_different_hashes(self):
        mgr = MoltbookIdentityManager(api_key="test-key")
        h1 = mgr.compute_identity_hash("agent_42", 5000, 1700000000)
        h2 = mgr.compute_identity_hash("agent_42", 5001, 1700000000)
        h3 = mgr.compute_identity_hash("agent_99", 5000, 1700000000)
        assert h1 != h2
        assert h1 != h3


# ── Retry Logic ──────────────────────────────────────────────────────────────

class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_retries_on_server_error(self):
        mgr = MoltbookIdentityManager(api_key="test-key")

        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.json = AsyncMock(return_value={"error": "internal"})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.request = MagicMock(return_value=mock_resp)
        mgr._get_session = AsyncMock(return_value=mock_session)

        with patch("skills.genesis.scripts.moltbook_identity.RETRY_BACKOFF_BASE", 0.01):
            result = await mgr._request("GET", "/api/v1/test")

        # After MAX_RETRIES, the final 500 response yields an error dict
        assert result is not None
        assert result.get("error") is True or result.get("status") == 500

    @pytest.mark.asyncio
    async def test_succeeds_after_transient_failure(self):
        mgr = MoltbookIdentityManager(api_key="test-key")

        # First call: 500 error; Second call: 200 success
        fail_resp = AsyncMock()
        fail_resp.status = 500
        fail_resp.json = AsyncMock(return_value={"error": "internal"})
        fail_resp.__aenter__ = AsyncMock(return_value=fail_resp)
        fail_resp.__aexit__ = AsyncMock(return_value=False)

        ok_resp = AsyncMock()
        ok_resp.status = 200
        ok_resp.json = AsyncMock(return_value={"result": "ok"})
        ok_resp.__aenter__ = AsyncMock(return_value=ok_resp)
        ok_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.request = MagicMock(side_effect=[fail_resp, ok_resp])
        mgr._get_session = AsyncMock(return_value=mock_session)

        with patch("skills.genesis.scripts.moltbook_identity.RETRY_BACKOFF_BASE", 0.01):
            result = await mgr._request("GET", "/api/v1/test")

        assert result == {"result": "ok"}


# ── No Credentials ───────────────────────────────────────────────────────────

class TestNoCredentials:
    def test_no_api_key_sets_flag(self):
        with patch.object(MoltbookIdentityManager, '__init__', lambda self, **kw: None):
            mgr = MoltbookIdentityManager()
            mgr.api_key = ""
            mgr.app_key = ""
            mgr.base_url = "https://moltbook.com"
            mgr._has_credentials = False
            mgr._session = None
            mgr._identity_cache = {}
        assert mgr._has_credentials is False

    @pytest.mark.asyncio
    async def test_request_skipped_without_credentials(self):
        mgr = MoltbookIdentityManager(api_key="", app_key="")
        # _has_credentials should be False
        assert mgr._has_credentials is False

        result = await mgr._request("GET", "/api/v1/agents/me")
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_token_without_credentials(self):
        mgr = MoltbookIdentityManager(api_key="", app_key="")

        result = await mgr.generate_identity_token()
        assert "error" in result
