# Genesis Protocol

**AI-Powered Uniswap V4 Hook Strategy Engine for X Layer**

Genesis is an AI Agent Skill that autonomously generates, deploys, and manages composable Uniswap V4 Hook strategies on [X Layer](https://www.okx.com/xlayer). It combines on-chain Solidity modules with a 5-layer AI cognitive architecture to deliver institutional-grade DeFi strategy management.

> OKX Build X Hackathon 2026 — Skills Arena Submission

**[Live Demo](https://0xcaptain888.github.io/genesis-protocol/)** | **[GitHub](https://github.com/0xCaptain888/genesis-protocol)**

---

## Highlights

- **Hook Template Engine** — 3 composable Solidity modules (DynamicFee, MEVProtection, AutoRebalance) assembled by AI into custom V4 Hook configurations
- **5-Layer AI Cognitive Architecture** — Perception → Analysis → Planning → Evolution → Meta-Cognition
- **Strategy NFTs** — Proven strategies minted as ERC-721 with full on-chain metadata
- **On-Chain Decision Journal** — Every AI decision logged with reasoning hashes for full auditability
- **x402 Payment Monetization** — Signal queries, strategy subscriptions, parameter purchases, NFT licensing
- **X Layer Native** — Zero gas fees with USDG/USDT, ~$0.0005/tx, 1s block time

## Architecture

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
└─────────────────────────────────────────────────────────┘
```

## Project Structure

```
genesis/
├── contracts/                          Solidity (Foundry)
│   ├── src/
│   │   ├── IGenesisModule.sol          Module interface
│   │   ├── GenesisHookAssembler.sol    Core meta-hook factory
│   │   ├── StrategyNFT.sol             ERC-721 with on-chain metadata
│   │   └── modules/
│   │       ├── DynamicFeeModule.sol    Volatility-responsive fees
│   │       ├── MEVProtectionModule.sol Sandwich attack detection
│   │       └── AutoRebalanceModule.sol IL-aware position management
│   ├── script/Deploy.sol               Deployment script
│   └── test/GenesisTest.sol            40 tests, all passing
│
└── skills/genesis/                     AI Agent Skill
    ├── SKILL.md                        Skill definition
    ├── plugin.yaml                     Plugin manifest
    └── scripts/
        ├── config.py                   Configuration & safety defaults
        ├── genesis_engine.py           5-layer AI cognitive engine
        ├── market_oracle.py            Market data via OnchainOS
        ├── wallet_manager.py           Multi sub-wallet management
        ├── hook_assembler.py           Hook Template Engine
        ├── strategy_manager.py         Strategy lifecycle
        ├── decision_journal.py         On-chain + local decision log
        ├── nft_minter.py              Strategy NFT minting
        └── main.py                     CLI entry point
```

## Smart Contracts

### GenesisHookAssembler

The core "meta-hook" factory. Accepts an array of `IGenesisModule` addresses, dispatches `beforeSwap`/`afterSwap` calls to each module, and aggregates results (highest fee wins, any module can block). Includes built-in strategy registry and decision journal.

### Modules

| Module | What It Does |
|--------|-------------|
| **DynamicFeeModule** | Fee = f(volatility). Range 0.05%-1.00%, with low/high regime thresholds. Stale data fallback to maxFee after 1 hour. |
| **MEVProtectionModule** | Per-block swap pattern tracking. Detects sandwich attacks via count threshold, volume threshold, and cross-address buy-sell patterns. Can penalize or block. |
| **AutoRebalanceModule** | Monitors position boundaries, emits `RebalanceNeeded` events for off-chain execution. Three trigger types: hard (out-of-range), soft (approaching boundary), IL threshold. Three strategies: IMMEDIATE, TWAP, THRESHOLD_ACCUMULATE. |

### StrategyNFT

Minimal ERC-721 (no OpenZeppelin dependency). On-chain metadata includes: module composition, all parameters, P&L, swap count, volume, decision count, market conditions at mint time. Fully verifiable — no IPFS dependency.

## Strategy Presets

| Preset | Market Condition | Modules | Key Feature |
|--------|-----------------|---------|-------------|
| `calm_accumulator` | Low vol, sideways | Fee + Rebalance | Low fees (0.01-0.30%) to attract volume |
| `volatile_defender` | High vol, any trend | Fee + MEV + Rebalance | High fees (0.10-1.50%), MEV blocking enabled |
| `trend_rider` | Medium vol, trending | Fee + MEV + Rebalance | TWAP rebalance, damped fee sensitivity |

## AI Cognitive Architecture

| Layer | Interval | Function |
|-------|----------|----------|
| **Perception** | 60s | Fetch market data, wallet balances, strategy states |
| **Analysis** | 300s | Volatility calculation, trend detection, regime classification |
| **Planning** | On signal | Action generation with confidence scoring (threshold: 0.7) |
| **Evolution** | 24h | Meta-learning: adjust thresholds from historical performance |
| **Meta-Cognition** | 24h | Self-assessment: evaluate decision quality, detect biases |

## Safety Defaults

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

## x402 Payment Tiers

| Product | Price | Settlement |
|---------|-------|-----------|
| Signal Query | 0.001 USDT | Async |
| Strategy Subscribe | 0.01 USDT | Async |
| Strategy Params Buy | 1.00 USDT | Sync |
| NFT License | 5.00 USDT | Sync |

## Development

### Prerequisites

- [Foundry](https://book.getfoundry.sh/) (Solc 0.8.26)
- Python 3.10+
- [OnchainOS CLI](https://docs.okx.com/onchainos)

### Build & Test

```bash
cd contracts
forge install foundry-rs/forge-std --no-git
forge build
forge test -vv
```

### Deploy to X Layer

```bash
forge script script/Deploy.sol --rpc-url https://rpc.xlayer.tech --broadcast
```

## Tech Stack Integration

| Component | Integration |
|-----------|------------|
| **OnchainOS Wallet** | TEE-based agentic wallet with 5 sub-wallets |
| **OnchainOS Trade** | DEX aggregation for rebalance execution |
| **OnchainOS Market** | Real-time price feeds for perception layer |
| **OnchainOS Payment** | x402 protocol for strategy monetization |
| **Uniswap V4 Hooks** | Composable hook modules via GenesisHookAssembler |
| **X Layer** | EVM L2, chainId 196, zero gas with USDG/USDT |

## License

MIT
