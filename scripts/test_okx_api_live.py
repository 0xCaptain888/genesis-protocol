#!/usr/bin/env python3
"""Live integration test for OKX DEX API on X Layer.

Tests real API calls to verify our endpoint paths are correct.
No authentication needed for public read endpoints.
"""
import json
import urllib.request
import urllib.parse
import sys

BASE = "https://web3.okx.com"

# Common token addresses on X Layer (chain 196)
USDT_XLAYER = "0x1E4a5963aBFD975d8c9021ce480b42188849D41d"
OKB_XLAYER = "0x75231F58b43240C9718Dd58B4967c5114342a86c"
WETH_XLAYER = "0x5A77f1443D16ee5761d310e38b62f77f726bC71c"
NATIVE = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

def api_get(path, params=None):
    """Make a GET request to OKX API."""
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={
        "User-Agent": "Genesis-Protocol/1.0",
        "Accept": "application/json",
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.reason}")
        body = e.read().decode() if e.fp else ""
        if body:
            print(f"  Body: {body[:200]}")
        return {"error": f"HTTP {e.code}", "reason": e.reason}
    except Exception as e:
        print(f"  Error: {e}")
        return {"error": str(e)}


def test_supported_chains():
    """Test: Get supported chains for DEX aggregator."""
    print("\n[1] GET /api/v5/dex/aggregator/supported/chain")
    result = api_get("/api/v5/dex/aggregator/supported/chain")
    if result.get("code") == "0" or result.get("data"):
        chains = result.get("data", [])
        xlayer = [c for c in chains if str(c.get("chainId")) == "196"]
        print(f"  OK - {len(chains)} chains supported")
        if xlayer:
            print(f"  X Layer found: {xlayer[0]}")
        return True
    print(f"  Result: {json.dumps(result)[:200]}")
    return False


def test_all_tokens():
    """Test: Get all tokens on X Layer."""
    print("\n[2] GET /api/v5/dex/aggregator/all-tokens?chainId=196")
    result = api_get("/api/v5/dex/aggregator/all-tokens", {"chainId": "196"})
    if result.get("code") == "0" or result.get("data"):
        tokens = result.get("data", [])
        if isinstance(tokens, list):
            print(f"  OK - {len(tokens)} tokens on X Layer")
            for t in tokens[:3]:
                print(f"    {t.get('tokenSymbol', '?')}: {t.get('tokenContractAddress', '?')[:20]}...")
        return True
    print(f"  Result: {json.dumps(result)[:200]}")
    return False


def test_swap_quote():
    """Test: Get a DEX swap quote on X Layer."""
    print("\n[3] GET /api/v5/dex/aggregator/quote")
    params = {
        "chainId": "196",
        "fromTokenAddress": NATIVE,  # OKB native
        "toTokenAddress": USDT_XLAYER,
        "amount": "1000000000000000000",  # 1 OKB
        "slippage": "0.5",
    }
    result = api_get("/api/v5/dex/aggregator/quote", params)
    if result.get("code") == "0" or result.get("data"):
        data = result.get("data", [{}])
        if isinstance(data, list) and len(data) > 0:
            route = data[0]
            print(f"  OK - Quote received")
            print(f"    From: {route.get('fromToken', {}).get('tokenSymbol', '?')}")
            print(f"    To: {route.get('toToken', {}).get('tokenSymbol', '?')}")
            print(f"    Amount out: {route.get('toTokenAmount', '?')}")
        return True
    print(f"  Result: {json.dumps(result)[:200]}")
    return False


def test_liquidity_sources():
    """Test: Get available liquidity sources on X Layer."""
    print("\n[4] GET /api/v5/dex/aggregator/supported/liquidity?chainId=196")
    result = api_get("/api/v5/dex/aggregator/supported/liquidity", {"chainId": "196"})
    if result.get("code") == "0" or result.get("data"):
        sources = result.get("data", [])
        if isinstance(sources, list):
            print(f"  OK - {len(sources)} liquidity sources")
            for s in sources[:5]:
                print(f"    {s.get('dexName', s.get('name', '?'))}")
        return True
    print(f"  Result: {json.dumps(result)[:200]}")
    return False


def main():
    print("=" * 60)
    print("  OKX DEX API - Live Integration Test")
    print("  Base URL:", BASE)
    print("  Chain: X Layer (196)")
    print("=" * 60)

    results = []
    results.append(("Supported Chains", test_supported_chains()))
    results.append(("All Tokens", test_all_tokens()))
    results.append(("Swap Quote", test_swap_quote()))
    results.append(("Liquidity Sources", test_liquidity_sources()))

    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
    print(f"\n  {passed}/{len(results)} tests passed")
    print("=" * 60)

    if passed < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
