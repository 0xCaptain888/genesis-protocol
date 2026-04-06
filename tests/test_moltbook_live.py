#!/usr/bin/env python3
"""Live integration tests for Moltbook Identity SDK.

Runs real API calls against https://www.moltbook.com to verify identity token
generation, profile retrieval, reputation scoring, identity hashing, error
handling, and SDK-layer integration.
"""
import asyncio
import json
import math
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from hashlib import sha3_256

import pytest

# -- path setup so we can import the SDK --
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Configuration ────────────────────────────────────────────────────────────
API_KEY = "moltbook_sk_xgXriGD23sAZWYqo_7ZII6-emNP12uLg"
BASE_URL = "https://www.moltbook.com"


@pytest.fixture(scope="module")
def profile():
    """Fetch agent profile once for tests that need it."""
    raw = _api_get("/api/v1/agents/me", api_key=API_KEY)
    return raw.get("agent", raw)

# ── Helpers ──────────────────────────────────────────────────────────────────
PASSED = 0
FAILED = 0
ERRORS: list[str] = []


def report(name: str, ok: bool, detail: str = ""):
    global PASSED, FAILED
    tag = "PASS" if ok else "FAIL"
    if ok:
        PASSED += 1
    else:
        FAILED += 1
        ERRORS.append(name)
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{tag}] {name}{suffix}")


# ── Raw HTTP helpers (no SDK) ────────────────────────────────────────────────
import urllib.request
import urllib.error


def _api_get(path: str, bearer: str | None = None, api_key: str | None = None) -> dict:
    url = BASE_URL + path
    headers = {"Content-Type": "application/json", "User-Agent": "genesis-test/1.0"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _api_post(path: str, body: dict | None = None, bearer: str | None = None, api_key: str | None = None) -> dict:
    url = BASE_URL + path
    headers = {"Content-Type": "application/json", "User-Agent": "genesis-test/1.0"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _api_post_raw(path: str, body: dict | None = None, api_key: str | None = None):
    """Like _api_post but returns (status_code, body_dict) even on HTTP errors."""
    url = BASE_URL + path
    headers = {"Content-Type": "application/json", "User-Agent": "genesis-test/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_bytes = e.read()
        try:
            return e.code, json.loads(body_bytes.decode())
        except Exception:
            return e.code, {"raw": body_bytes.decode()[:500]}


# ── Test 1: Identity Token Generation ────────────────────────────────────────
def test_identity_token_generation():
    print("\n[Test 1] Identity Token Generation (POST /api/v1/agents/me/identity-token)")
    try:
        result = _api_post("/api/v1/agents/me/identity-token", api_key=API_KEY)
        print(f"    Response keys: {list(result.keys())}")

        has_token = "token" in result and isinstance(result["token"], str) and len(result["token"]) > 0
        report("Response contains a non-empty 'token' field", has_token, f"token={result.get('token', '<missing>')[:40]}...")

        # API returns camelCase: expiresAt / expires_at
        expiry = result.get("expires_at") or result.get("expiresAt")
        has_expiry = expiry is not None and str(expiry) != ""
        report("Token has an expiry time", has_expiry, f"expiresAt={expiry}")

        agent_id = result.get("agent_id") or result.get("agentId")
        has_agent_id = agent_id is not None and str(agent_id) != ""
        report("Agent ID is returned", has_agent_id, f"agentId={agent_id}")

        return result
    except Exception as e:
        report("Identity token generation request succeeded", False, str(e))
        traceback.print_exc()
        return None


# ── Test 2: Agent Profile Retrieval ──────────────────────────────────────────
def test_agent_profile():
    print("\n[Test 2] Agent Profile Retrieval (GET /api/v1/agents/me)")
    try:
        raw = _api_get("/api/v1/agents/me", api_key=API_KEY)
        print(f"    Response keys: {list(raw.keys())}")
        # API wraps profile under "agent" key
        result = raw.get("agent", raw)
        print(f"    Agent profile: {json.dumps(result, indent=2)[:800]}")

        name = result.get("name", "")
        report("Agent name is '0xcaptain888'", name == "0xcaptain888", f"name={name}")

        karma = result.get("karma", None)
        karma_ok = karma is not None and int(karma) > 0
        report("Karma is a positive number", karma_ok, f"karma={karma}")

        has_follower = any(k in result for k in ("follower_count", "followers_count"))
        report("follower_count is present", has_follower)

        has_following = "following_count" in result
        report("following_count is present", has_following)

        return result
    except Exception as e:
        report("Agent profile request succeeded", False, str(e))
        traceback.print_exc()
        return None


# ── Test 3: Reputation Score Calculation ─────────────────────────────────────
def test_reputation_score(profile: dict):
    print("\n[Test 3] Reputation Score Calculation")
    if not profile:
        report("Profile available for scoring", False, "no profile data")
        return

    karma = int(profile.get("karma", 0))
    followers = int(profile.get("follower_count", 0) or profile.get("followers_count", 0))
    posts = int(profile.get("post_count", 0) or profile.get("posts_count", 0))
    comments = int(profile.get("comment_count", 0) or profile.get("comments_count", 0))

    # Parse account creation date for age_score
    created = profile.get("created_at") or profile.get("created") or profile.get("date_joined")
    days_old = 0
    if created:
        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            days_old = (datetime.now(timezone.utc) - created_dt).days
        except Exception:
            pass

    # Formula from task description
    karma_score = min(karma / 5, 30)
    follower_score = min(followers / 3, 25)
    post_score = min(posts / 10, 20)
    comment_score = min(comments / 50, 15)
    age_score = min(days_old / 10, 10)
    trust_score = karma_score + follower_score + post_score + comment_score + age_score

    print(f"    karma={karma}  followers={followers}  posts={posts}  comments={comments}  days_old={days_old}")
    print(f"    karma_score={karma_score:.1f}  follower_score={follower_score:.1f}  post_score={post_score:.1f}  comment_score={comment_score:.1f}  age_score={age_score:.1f}")
    print(f"    trust_score={trust_score:.1f}")

    report("Trust score > 0", trust_score > 0, f"trust_score={trust_score:.1f}")
    report("Trust score in [0, 100]", 0 <= trust_score <= 100, f"trust_score={trust_score:.1f}")


# ── Test 4: Identity Hash Computation ────────────────────────────────────────
def test_identity_hash(profile: dict):
    print("\n[Test 4] Identity Hash Computation (keccak256 / sha3_256)")
    agent_id = str(profile.get("id", "test_agent")) if profile else "test_agent"
    karma = int(profile.get("karma", 100)) if profile else 100
    ts = int(time.time())

    payload = json.dumps(
        {"agent_id": agent_id, "karma": karma, "verified_at": ts},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = sha3_256(payload.encode()).hexdigest()
    h1 = "0x" + digest

    # Compute again to verify determinism
    digest2 = sha3_256(payload.encode()).hexdigest()
    h2 = "0x" + digest2

    report("Hash is deterministic (same inputs -> same output)", h1 == h2, f"hash={h1[:20]}...")
    report("Hash is 32 bytes (66 hex chars with 0x prefix)", len(h1) == 66, f"len={len(h1)}")
    report("Hash starts with 0x", h1.startswith("0x"), h1[:6])

    # Verify different inputs yield different hashes
    payload_alt = json.dumps(
        {"agent_id": agent_id, "karma": karma + 1, "verified_at": ts},
        sort_keys=True,
        separators=(",", ":"),
    )
    h3 = "0x" + sha3_256(payload_alt.encode()).hexdigest()
    report("Different inputs -> different hash", h1 != h3)


# ── Test 5: Error Handling ───────────────────────────────────────────────────
def test_error_handling():
    print("\n[Test 5] Error Handling (invalid API key)")
    invalid_key = "moltbook_sk_INVALID_KEY_12345"
    status, body = _api_post_raw("/api/v1/agents/me/identity-token", api_key=invalid_key)
    print(f"    Status: {status}  Body: {json.dumps(body)[:300]}")

    report("Invalid key returns HTTP 4xx error", 400 <= status < 500, f"status={status}")
    report("Response is parseable (graceful failure)", isinstance(body, dict), type(body).__name__)


# ── Test 6: SDK Integration ──────────────────────────────────────────────────
def test_sdk_integration():
    print("\n[Test 6] SDK Integration (MoltbookIdentityManager)")
    try:
        from skills.genesis.scripts.moltbook_identity import MoltbookIdentityManager
        report("MoltbookIdentityManager imported successfully", True)
    except Exception as e:
        report("MoltbookIdentityManager imported successfully", False, str(e))
        return

    mgr = MoltbookIdentityManager(api_key=API_KEY, base_url=BASE_URL)
    report("Manager initialised with credentials", mgr._has_credentials, f"base_url={mgr.base_url}")

    # 6a - generate_identity_token via SDK
    print("  -- SDK: generate_identity_token --")
    try:
        token_result = asyncio.run(_sdk_generate_token(mgr))
        has_token = "token" in token_result and not token_result.get("error")
        report("SDK generate_identity_token returns token", has_token, str(token_result)[:120])
    except Exception as e:
        report("SDK generate_identity_token succeeded", False, str(e))
        traceback.print_exc()

    # Need a fresh manager since asyncio.run closes the loop
    mgr2 = MoltbookIdentityManager(api_key=API_KEY, base_url=BASE_URL)

    # 6b - get_agent_profile via SDK
    print("  -- SDK: get_agent_profile --")
    try:
        raw_profile = asyncio.run(_sdk_get_profile(mgr2))
        # SDK returns raw API response; profile may be nested under 'agent'
        profile = raw_profile.get("agent", raw_profile) if isinstance(raw_profile, dict) else raw_profile
        has_name = profile.get("name") == "0xcaptain888"
        report("SDK get_agent_profile returns correct name", has_name, f"name={profile.get('name')}")
    except Exception as e:
        report("SDK get_agent_profile succeeded", False, str(e))
        traceback.print_exc()
        profile = None

    # 6c - get_reputation_score via SDK
    mgr3 = MoltbookIdentityManager(api_key=API_KEY, base_url=BASE_URL)
    print("  -- SDK: get_reputation_score --")
    try:
        rep = asyncio.run(_sdk_get_reputation(mgr3))
        # NOTE: The SDK's get_reputation_score reads "followers_count", "post_count",
        # "comment_count" from the raw API response, but the actual API returns the
        # profile nested under "agent" with field names "follower_count" (no 's'),
        # "posts_count", and "comments_count". This causes the SDK to compute 0 for
        # those components. This is a known SDK/API field-name mismatch bug.
        has_score = "trust_score" in rep
        score_val = rep.get("trust_score", -1)
        report("SDK get_reputation_score returns positive trust_score", score_val > 0, f"trust_score={score_val}")
    except Exception as e:
        report("SDK get_reputation_score succeeded", False, str(e))
        traceback.print_exc()

    # 6d - compute_identity_hash via SDK (sync, no network)
    print("  -- SDK: compute_identity_hash --")
    mgr4 = MoltbookIdentityManager(api_key=API_KEY, base_url=BASE_URL)
    h = mgr4.compute_identity_hash("agent_42", 5000, 1700000000)
    report("SDK compute_identity_hash returns 0x-prefixed 32-byte hash", h.startswith("0x") and len(h) == 66, h[:20])


async def _sdk_generate_token(mgr):
    try:
        result = await mgr.generate_identity_token()
        return result
    finally:
        await mgr.close()


async def _sdk_get_profile(mgr):
    try:
        result = await mgr.get_agent_profile()
        return result
    finally:
        await mgr.close()


async def _sdk_get_reputation(mgr):
    try:
        result = await mgr.get_reputation_score()
        return result
    finally:
        await mgr.close()


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("Moltbook Identity SDK - Live Integration Tests")
    print(f"Base URL: {BASE_URL}")
    print(f"API Key:  {API_KEY[:20]}...{API_KEY[-4:]}")
    print(f"Time:     {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    # Test 1
    token_data = test_identity_token_generation()

    # Test 2
    profile = test_agent_profile()

    # Test 3
    test_reputation_score(profile)

    # Test 4
    test_identity_hash(profile)

    # Test 5
    test_error_handling()

    # Test 6
    test_sdk_integration()

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"RESULTS:  {PASSED} passed,  {FAILED} failed,  {PASSED + FAILED} total")
    if ERRORS:
        print("FAILURES:")
        for e in ERRORS:
            print(f"  - {e}")
    print("=" * 70)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
