"""
Genesis Configuration - All tunable parameters for the Genesis Protocol.

IMPORTANT SAFETY DEFAULTS:
- PAUSED = True  (must be explicitly enabled)
- MODE = "paper" (paper trading by default)
- DRY_RUN = True (simulate all on-chain operations)

These defaults are required by the OKX plugin-store guidelines.
"""

# ─── Safety Controls ──────────────────────────────────────────────────────
PAUSED = True
MODE = "paper"          # "paper" | "live"
DRY_RUN = True          # If True, simulate all contract calls
LOG_LEVEL = "INFO"      # "DEBUG" | "INFO" | "WARN" | "ERROR"

# ─── Chain Configuration ──────────────────────────────────────────────────
CHAIN_ID = 196                          # X Layer mainnet
CHAIN_NAME = "xlayer"
RPC_URL = "https://rpc.xlayer.tech"
EXPLORER_URL = "https://www.oklink.com/xlayer"
ZERO_GAS_TOKENS = ["USDG", "USDT"]     # Zero gas fee tokens on X Layer

# ─── Agentic Wallet Configuration ─────────────────────────────────────────
WALLET_ROLES = {
    "master":    {"index": 0, "purpose": "Main control wallet"},
    "strategy":  {"index": 1, "purpose": "Deploys and manages Hook strategies"},
    "income":    {"index": 2, "purpose": "Receives LP fees and x402 revenue"},
    "reserve":   {"index": 3, "purpose": "Emergency reserve fund"},
    "rebalance": {"index": 4, "purpose": "Executes rebalance operations"},
}
MAX_SUB_WALLETS = 5     # Start conservative, can expand to 50

# ─── Hook Template Engine ─────────────────────────────────────────────────
AVAILABLE_MODULES = {
    "dynamic_fee": {
        "contract": "DynamicFeeModule",
        "description": "Volatility-responsive dynamic fee adjustment",
        "default_params": {
            "base_fee": 3000,           # 0.30% in hundredths of bip
            "min_fee": 500,             # 0.05%
            "max_fee": 10000,           # 1.00%
            "sensitivity": 10000,       # 1.0x multiplier (PRECISION=10000)
            "low_threshold": 200,       # 2% vol = low regime
            "high_threshold": 800,      # 8% vol = high regime
        },
    },
    "mev_protection": {
        "contract": "MEVProtectionModule",
        "description": "Sandwich attack detection and mitigation",
        "default_params": {
            "swap_count_threshold": 3,   # max same-dir swaps per block
            "volume_threshold": 10000,   # max volume per direction per block (in token units)
            "penalty_fee": 5000,         # 0.50% penalty for suspicious swaps
            "block_suspicious": False,   # penalize rather than block
        },
    },
    "auto_rebalance": {
        "contract": "AutoRebalanceModule",
        "description": "Intelligent position range management with IL protection",
        "default_params": {
            "soft_trigger_pct": 85,      # trigger when 85% toward boundary
            "il_threshold_bps": 200,     # 2% max IL before forced rebalance
            "cooldown_period": 300,      # 5 min between signals
            "strategy": 0,              # 0=IMMEDIATE, 1=TWAP, 2=THRESHOLD_ACCUMULATE
        },
    },
}

# ─── Strategy Presets (AI selects based on market analysis) ───────────────
STRATEGY_PRESETS = {
    "calm_accumulator": {
        "description": "Low volatility environment - maximize volume via low fees",
        "modules": ["dynamic_fee", "auto_rebalance"],
        "overrides": {
            "dynamic_fee": {"min_fee": 100, "max_fee": 3000, "sensitivity": 8000},
            "auto_rebalance": {"soft_trigger_pct": 90, "il_threshold_bps": 150},
        },
        "market_conditions": {"vol_range": [0, 300], "trend": "sideways"},
    },
    "volatile_defender": {
        "description": "High volatility - protect LP with high fees + MEV guard",
        "modules": ["dynamic_fee", "mev_protection", "auto_rebalance"],
        "overrides": {
            "dynamic_fee": {"min_fee": 1000, "max_fee": 15000, "sensitivity": 12000},
            "mev_protection": {"block_suspicious": True},
            "auto_rebalance": {"soft_trigger_pct": 70, "cooldown_period": 120},
        },
        "market_conditions": {"vol_range": [500, 9999], "trend": "any"},
    },
    "trend_rider": {
        "description": "Trending market - wider range, TWAP rebalance",
        "modules": ["dynamic_fee", "mev_protection", "auto_rebalance"],
        "overrides": {
            "dynamic_fee": {"sensitivity": 9000},
            "auto_rebalance": {"strategy": 1, "soft_trigger_pct": 75},
        },
        "market_conditions": {"vol_range": [200, 600], "trend": "trending"},
    },
}

# ─── AI Decision Engine ───────────────────────────────────────────────────
PERCEPTION_INTERVAL_SEC = 60        # How often to poll market data
ANALYSIS_INTERVAL_SEC = 300         # How often to run full analysis
EVOLUTION_INTERVAL_SEC = 86400      # How often to run meta-cognition (24h)

VOLATILITY_WINDOW_HOURS = 24        # Lookback for vol calculation
TREND_WINDOW_HOURS = 72             # Lookback for trend detection
CONFIDENCE_THRESHOLD = 0.7          # Min confidence to act on a signal
MAX_POSITION_SIZE_PCT = 30          # Max % of wallet to deploy in one strategy

# ─── Decision Journal ─────────────────────────────────────────────────────
JOURNAL_ON_CHAIN = True             # Log decisions to DecisionJournal contract
JOURNAL_LOCAL_PATH = "decisions/"   # Also store locally for analysis
DECISION_TYPES = {
    "STRATEGY_CREATE": "0x01",
    "STRATEGY_DEACTIVATE": "0x02",
    "FEE_ADJUST": "0x03",
    "REBALANCE_EXECUTE": "0x04",
    "FUND_TRANSFER": "0x05",
    "MODULE_SWAP": "0x06",
    "PERFORMANCE_EVAL": "0x07",
    "META_COGNITION": "0x08",
    "NFT_MINT": "0x09",
}

# ─── Strategy NFT ─────────────────────────────────────────────────────────
NFT_MINT_THRESHOLD_PNL_BPS = 100    # Min +1% P&L to mint
NFT_MINT_THRESHOLD_SWAPS = 50       # Min 50 swaps processed
NFT_MINT_THRESHOLD_HOURS = 48       # Min 48h runtime

# ─── x402 Payment Configuration ──────────────────────────────────────────
X402_ENABLED = True
X402_PRICING = {
    "signal_query": {"amount": "0.001", "token": "USDT", "settle": "async"},
    "strategy_subscribe": {"amount": "0.01", "token": "USDT", "settle": "async"},
    "strategy_params_buy": {"amount": "1.00", "token": "USDT", "settle": "sync"},
    "nft_license": {"amount": "5.00", "token": "USDT", "settle": "sync"},
}

# ─── OnchainOS Integration ────────────────────────────────────────────────
ONCHAINOS_MARKET_PAIRS = [
    {"base": "ETH", "quote": "USDC", "chain": CHAIN_ID},
    {"base": "OKB", "quote": "USDT", "chain": CHAIN_ID},
]
DEX_SLIPPAGE_BPS = 50              # 0.5% default slippage
DEX_COMPARE_WITH_HOOK = True       # Always compare Hook pool vs DEX aggregator

# ─── Contract Addresses (populated after deployment) ──────────────────────
CONTRACTS = {
    "assembler": "",
    "dynamic_fee_module": "",
    "mev_protection_module": "",
    "auto_rebalance_module": "",
    "strategy_nft": "",
}
