![CI](https://github.com/0xCaptain888/genesis-protocol/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![X Layer](https://img.shields.io/badge/X%20Layer-Chain%20196-blue)
![Uniswap V4](https://img.shields.io/badge/Uniswap-V4-ff007a)

# Genesis Protocol

**AI-Powered Uniswap V4 Hook Strategy Engine for X Layer**

Genesis is an AI Agent Skill that autonomously generates, deploys, and manages composable Uniswap V4 Hook strategies on [X Layer](https://www.okx.com/xlayer). It combines on-chain Solidity modules with a 5-layer AI cognitive architecture to deliver institutional-grade DeFi strategy management.

**[Interactive dApp](https://0xcaptain888.github.io/genesis-protocol/)** | **[GitHub](https://github.com/0xCaptain888/genesis-protocol)**

---

## Project Overview / 项目简介

Genesis Protocol is an autonomous AI agent that manages Uniswap V4 Hook strategies on X Layer. It perceives market conditions, analyzes volatility regimes, plans optimal hook configurations, evolves its own parameters over time, and mints proven strategies as NFTs. Every decision is logged on-chain with reasoning hashes for full auditability.

### Highlights

- **Hook Template Engine** -- 3 composable Solidity modules (DynamicFee, MEVProtection, AutoRebalance) assembled by AI into custom V4 Hook configurations
- **5-Layer AI Cognitive Architecture** -- Perception, Analysis, Planning, Evolution, Meta-Cognition
- **Strategy NFTs** -- Proven strategies minted as ERC-721 with full on-chain metadata
- **On-Chain Decision Journal** -- Every AI decision logged with reasoning hashes for full auditability
- **x402 Payment Monetization** -- Signal queries, strategy subscriptions, parameter purchases, NFT licensing. **Pay with any token** via Uniswap auto-swap.
- **X Layer Native** -- Zero gas fees with USDG/USDT, ~$0.0005/tx, 1s block time

---

## Architecture Overview / 架构概述

```
┌─────────────────────────────────────────────────────────┐
│                    AI Agent (Python)                     │
│                                                         │
│  ┌───────────┐  ┌──────────┐  ┌───────────────────┐    │
│  │  Market    │  │ Genesis  │  │    Strategy        │    │
│  │  Oracle    │→ │ Engine   │→ │    Manager         │    │
│  │           │  │ (5-layer)│  │                    │    │
│  └───────────┘  └──────────┘  └───────────────────┘    │
│        ↑              │              │                   │
│   onchainos       Decision       Hook                   │
│   market          Journal        Assembler              │
│                      │              │                   │
├──────────────────────┼──────────────┼───────────────────┤
│                 X Layer (Chain 196)                      │
│                                                         │
│  ┌────────────────────────────────────────────────┐     │
│  │          GenesisHookAssembler                   │     │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐   │     │
│  │  │DynamicFee│ │   MEV    │ │AutoRebalance │   │     │
│  │  │ Module   │ │Protection│ │   Module     │   │     │
│  │  └──────────┘ └──────────┘ └──────────────┘   │     │
│  └────────────────────────────────────────────────┘     │
│                                                         │
│  ┌──────────────┐  ┌──────────────────────────┐        │
│  │ StrategyNFT  │  │   Decision Journal       │        │
│  │  (ERC-721)   │  │   (on-chain log)         │        │
│  └──────────────┘  └──────────────────────────┘        │
│                                                         │
│  ┌──────────────────────────────────────────────┐      │
│  │         Uniswap V4 Core (X Layer)            │      │
│  │  PoolManager · PositionManager · Quoter      │      │
│  └──────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

---

## Deployment Addresses / 部署地址

### Genesis Protocol Contracts (X Layer Testnet - Chain 1952)

| Contract | Address |
|----------|---------|
| **GenesisHookAssembler** | `0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78` |
| **DynamicFeeModule** | `0x277Ee5801D5d1e5126A76c986c96923AB5eC54Ed` |
| **MEVProtectionModule** | `0xA4f6ABd6F77928b06F075637ccBACA8f89e17386` |
| **AutoRebalanceModule** | `0xe04E22e78E1935b60e8827EB72CEc3b56299c8ee` |
| **StrategyNFT** | `0xd969448dfc24Fe3Aff25e86db338fAB41b104319` |

Explorer: [View on OKLink](https://www.oklink.com/xlayer-test/address/0xC5E851fEC9188DD4F6cCB2Ebc134b33210D4aC78)

### Uniswap V4 Core Contracts (X Layer)

| Contract | Address |
|----------|---------|
| **PoolManager** | `0x360e68faCCca8cA495c1B759Fd9EEe466dB9Fb32` |
| **PositionManager** | `0x1b35d13a2e2528f192637f14b05f0dc0e7deb566` |
| **Quoter** | `0x3972c00f7ed4885e145823eb7c655375d275a1c5` |

---

## Agentic Wallet / 代理钱包架构

Genesis uses a **5 sub-wallet architecture** via OnchainOS TEE-based agentic wallet to isolate risk and enforce separation of concerns:

| Index | Role | Purpose |
|-------|------|---------|
| 0 | **Master** | Main control wallet -- approvals, ownership, admin |
| 1 | **Strategy** | Deploys and manages Hook strategies on Uniswap V4 |
| 2 | **Income** | Receives LP fees and x402 payment revenue |
| 3 | **Reserve** | Emergency reserve fund -- untouched during normal operation |
| 4 | **Rebalance** | Executes rebalance operations with isolated funds |

This architecture ensures that a bug in rebalance logic cannot drain strategy funds, and income is always separated from operational capital. The master wallet holds no trading funds -- it only signs administrative transactions.

---

## Onchain OS Integration / Onchain OS Skill 使用情况

Genesis integrates deeply with the OnchainOS skill ecosystem:

| OnchainOS Skill | Usage in Genesis |
|----------------|-----------------|
| **onchainos-wallet** | TEE-based agentic wallet with 5 sub-wallets for role isolation (master, strategy, income, reserve, rebalance) |
| **onchainos-market** | Real-time price feeds for the Perception layer -- fetches ETH/USDC, OKB/USDT prices on X Layer for volatility calculation and regime detection |
| **onchainos-trade** | DEX aggregation for rebalance execution -- compares Hook pool rates vs aggregator, routes through best path with 0.5% max slippage |
| **onchainos-payment** | x402 protocol integration for strategy monetization -- signal queries, strategy subscriptions, parameter purchases, NFT licensing |
| **onchainos-security** | Token risk scanning before strategy creation -- checks contract safety, liquidity depth, and rugpull indicators before deploying any strategy |
| **onchainos-defi-invest** | Yield comparison across X Layer DeFi protocols to benchmark Genesis strategy performance against alternative yield sources |

---

## Uniswap Skills Integration / Uniswap Skill 使用情况

Genesis leverages Uniswap V4 as its core DeFi primitive:

| Uniswap Skill | Usage in Genesis |
|--------------|-----------------|
| **uniswap-v4-hooks** | Composable hook modules via GenesisHookAssembler -- DynamicFee, MEVProtection, and AutoRebalance modules are registered as V4 hooks that intercept `beforeSwap` and `afterSwap` |
| **uniswap-v4-position-manager** | Manages concentrated liquidity positions for each strategy -- creates, adjusts, and closes positions based on AI rebalance signals |
| **uniswap-v4-quoter** | Pre-swap quotes for slippage estimation -- used by the Planning layer to simulate strategy outcomes before execution |
| **uniswap-pay-with-any-token** | Accept x402 payments in any ERC-20 token -- auto-swaps to USDT via Uniswap before settlement, enabling frictionless monetization |

---

## How It Works / 运作机制

### AI Cognitive Architecture (5 Layers)

| Layer | Interval | Function |
|-------|----------|----------|
| **Perception** | 60s | Fetch market data, wallet balances, strategy states via onchainos-market |
| **Analysis** | 300s | Volatility calculation, trend detection, regime classification |
| **Planning** | On signal | Action generation with confidence scoring (threshold: 0.7) |
| **Evolution** | 24h | Meta-learning: adjust thresholds from historical performance |
| **Meta-Cognition** | 24h | Self-assessment: evaluate decision quality, detect biases |

### Smart Contracts

**GenesisHookAssembler** -- The core "meta-hook" factory. Accepts an array of `IGenesisModule` addresses, dispatches `beforeSwap`/`afterSwap` calls to each module, and aggregates results (highest fee wins, any module can block). Includes built-in strategy registry and decision journal.

| Module | What It Does |
|--------|-------------|
| **DynamicFeeModule** | Fee = f(volatility). Range 0.05%-1.00%, with low/high regime thresholds. Stale data fallback to maxFee after 1 hour. |
| **MEVProtectionModule** | Per-block swap pattern tracking. Detects sandwich attacks via count threshold, volume threshold, and cross-address buy-sell patterns. Can penalize or block. |
| **AutoRebalanceModule** | Monitors position boundaries, emits `RebalanceNeeded` events for off-chain execution. Three trigger types: hard, soft, IL threshold. Three strategies: IMMEDIATE, TWAP, THRESHOLD_ACCUMULATE. |

**StrategyNFT** -- Minimal ERC-721 (no OpenZeppelin dependency). On-chain metadata includes: module composition, all parameters, P&L, swap count, volume, decision count, market conditions at mint time. Fully verifiable -- no IPFS dependency.

### Strategy Presets

| Preset | Market Condition | Modules | Key Feature |
|--------|-----------------|---------|-------------|
| `calm_accumulator` | Low vol, sideways | Fee + Rebalance | Low fees (0.01-0.30%) to attract volume |
| `volatile_defender` | High vol, any trend | Fee + MEV + Rebalance | High fees (0.10-1.50%), MEV blocking enabled |
| `trend_rider` | Medium vol, trending | Fee + MEV + Rebalance | TWAP rebalance, damped fee sensitivity |

### Safety Defaults

Genesis ships paused with paper trading enabled. All three flags must be explicitly disabled:

```python
PAUSED   = True     # Engine observes but does not act
MODE     = "paper"  # Paper trading simulation
DRY_RUN  = True     # No on-chain transactions broadcast
```

Additional safeguards:
- Max 30% of wallet per strategy
- Confidence gating at 0.7
- 5-wallet isolation (master/strategy/income/reserve/rebalance)
- Rebalance cooldown enforcement (300s default)
- 0.5% max slippage on DEX operations

### x402 Payment Tiers

| Product | Price | Settlement |
|---------|-------|-----------|
| Signal Query | 0.001 USDT | Async |
| Strategy Subscribe | 0.01 USDT | Async |
| Strategy Params Buy | 1.00 USDT | Sync |
| NFT License | 5.00 USDT | Sync |

---

## X Layer Ecosystem Positioning / 项目在 X Layer 生态中的定位

Genesis Protocol is positioned as the **AI strategy infrastructure layer** for X Layer's DeFi ecosystem:

- **For LPs**: Autonomous management of Uniswap V4 concentrated liquidity positions with AI-optimized hook configurations -- no manual parameter tuning required.
- **For Traders**: MEV protection and dynamic fees that adapt to real-time market conditions, creating fairer trading environments.
- **For Developers**: Open hook module system -- new `IGenesisModule` implementations can be plugged into the Assembler without modifying core contracts.
- **For the X Layer Ecosystem**: Demonstrates that AI agents can operate as first-class citizens on X Layer, leveraging zero gas fees (USDG/USDT), 1-second block times, and the OnchainOS skill ecosystem to deliver autonomous DeFi infrastructure.

Genesis leverages X Layer's unique advantages:
- **Zero gas with USDG/USDT** -- AI agent can make frequent on-chain decisions without cost concerns
- **1s block time** -- Enables real-time MEV detection and rapid rebalance execution
- **OnchainOS native** -- Deep integration with wallet, market, trade, and payment skills
- **OKX ecosystem** -- Access to OKX liquidity and user base via X Layer bridge

---

## Demo

### Run the Cognitive Cycle Demo

```bash
python3 demo.py
```

[![Genesis Protocol Demo](https://asciinema.org/a/eb4XTEwMtod594xz.svg)](https://asciinema.org/a/eb4XTEwMtod594xz)

> Recording also saved as [`docs/demo.cast`](docs/demo.cast) -- play locally with `asciinema play docs/demo.cast`

The demo connects to X Layer Testnet to read live chain state, then simulates a complete AI agent lifecycle:

- **Layer 1 Perception** -- Fetches market prices, wallet balances, strategy states
- **Layer 2 Analysis** -- Computes volatility, classifies market regime
- **Layer 3 Planning** -- Generates action plan with confidence scoring
- **Layer 4 Evolution** -- Reviews performance, adjusts internal parameters
- **Layer 5 Meta-Cognition** -- Self-assessment, bias detection
- **NFT Check** -- Evaluates mint eligibility and mints Strategy NFT

### On-Chain Activity (X Layer Testnet)

| Metric | Value |
|--------|-------|
| Strategies created | 1 |
| Decision journal entries | 5 |
| Swaps processed | 2 (5.5 ETH volume) |
| Strategy NFTs minted | 1 (Token #0) |
| P&L recorded | +150 bps |

---

## Agent Interaction Example

Genesis is designed as a **Skill** for AI agents. Here's how an agent interacts with Genesis through natural language:

```
User: "The market looks volatile today. What should we do?"

Agent: Let me check the current market conditions.
> genesis market

  ETH/USDC: $2,450  vol=5.8%  trend=volatile
  OKB/USDT: $48.50  vol=4.2%  trend=sideways

  Recommended regime: volatile_defender
  Confidence: 0.87

The volatility is elevated. I recommend switching to the volatile_defender
preset which activates all three modules including MEV protection.

> genesis create-strategy volatile_defender

  Strategy #1 created with modules:
  - DynamicFeeModule (fee range: 0.10% - 1.50%)
  - MEVProtectionModule (blocking enabled)
  - AutoRebalanceModule (70% trigger, 120s cooldown)

  Decision logged: STRATEGY_CREATE (on-chain confirmed)

User: "How is our existing strategy performing?"

Agent: > genesis status

  Strategy #0: calm_accumulator
  - P&L: +1.5% (150 bps)
  - Swaps: 128 processed
  - Runtime: 72 hours
  - NFT eligible: Yes

  Strategy #1: volatile_defender
  - P&L: 0% (just created)
  - Swaps: 0
  - Runtime: 0 hours

User: "Mint the NFT for strategy 0."

Agent: > genesis mint-nft 0

  All thresholds met (P&L >= 1%, Swaps >= 50, Runtime >= 48h)
  Minting Strategy NFT...

  Token ID: 0
  Contract: 0xd969448dfc24Fe3Aff25e86db338fAB41b104319
  Metadata: on-chain (modules, params, P&L, market state)
  NFT minted successfully!
```

---

## Project Structure

```
genesis-protocol/
├── .github/workflows/ci.yml          GitHub Actions CI
├── contracts/                         Solidity (Foundry)
│   ├── src/
│   │   ├── IGenesisModule.sol         Module interface
│   │   ├── GenesisHookAssembler.sol   Core meta-hook factory
│   │   ├── StrategyNFT.sol            ERC-721 with on-chain metadata
│   │   └── modules/
│   │       ├── DynamicFeeModule.sol   Volatility-responsive fees
│   │       ├── MEVProtectionModule.sol Sandwich attack detection
│   │       └── AutoRebalanceModule.sol IL-aware position management
│   ├── script/Deploy.sol              Deployment script
│   └── test/GenesisTest.sol           40 tests, all passing
│
├── skills/genesis/                    AI Agent Skill
│   ├── SKILL.md                       Skill definition
│   ├── plugin.yaml                    Plugin manifest
│   └── scripts/
│       ├── config.py                  Configuration & safety defaults
│       ├── genesis_engine.py          5-layer AI cognitive engine
│       ├── market_oracle.py           Market data via OnchainOS
│       ├── wallet_manager.py          Multi sub-wallet management
│       ├── hook_assembler.py          Hook Template Engine
│       ├── strategy_manager.py        Strategy lifecycle
│       ├── decision_journal.py        On-chain + local decision log
│       ├── nft_minter.py             Strategy NFT minting
│       ├── payment_handler.py        x402 payments + pay-with-any-token
│       └── main.py                    CLI entry point
│
└── tests/                             Python test suite
    ├── test_config.py                 Safety defaults & structure validation
    ├── test_decision_journal.py       Decision logging & hash computation
    ├── test_nft_minter.py            NFT eligibility checks
    └── test_market_oracle.py         Market analytics functions
```

---

## How to Run

### Prerequisites

- [Foundry](https://book.getfoundry.sh/) (Solc 0.8.26)
- Python 3.10+
- [OnchainOS CLI](https://docs.okx.com/onchainos)

### Build & Test Solidity

```bash
cd contracts
forge install foundry-rs/forge-std --no-git
forge build
forge test -vv
```

### Run Python Tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

### Run the Demo

```bash
python3 demo.py
```

### Deploy to X Layer

```bash
cd contracts
forge script script/Deploy.sol --rpc-url https://rpc.xlayer.tech --broadcast
```

### Environment Setup

Copy the example env file and fill in your keys:

```bash
cp .env.example .env
```

---

## Team / 团队成员

| Member | Role |
|--------|------|
| **0xCaptain888** | Solo developer -- smart contracts, AI engine, integrations, frontend |

---

## License

MIT
