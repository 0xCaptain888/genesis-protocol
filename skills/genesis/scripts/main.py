#!/usr/bin/env python3
"""
Genesis Protocol CLI - Entry point for all Genesis operations.

Usage:
    python -m scripts.main <command> [args...]

Commands:
    start                       Start the autonomous strategy engine
    stop                        Stop the engine gracefully
    status                      Show current engine state
    deploy                      Deploy all contracts to X Layer
    create-strategy [preset]    Create a strategy (calm_accumulator|volatile_defender|trend_rider)
    rebalance <strategy_id>     Force rebalance a strategy
    deactivate <strategy_id>    Deactivate a strategy
    mint-nft <strategy_id>      Check eligibility and mint Strategy NFT
    journal [strategy_id]       View decision journal
    market                      Show current market analysis
    config set <key> <value>    Update configuration
    config show                 Show current configuration
    x402 pricing                Show x402 payment tiers
"""

import sys
import json
import logging

from . import config
from .genesis_engine import GenesisEngine
from .market_oracle import MarketOracle
from .wallet_manager import WalletManager
from .strategy_manager import StrategyManager
from .decision_journal import DecisionJournal
from .hook_assembler import HookAssembler
from .nft_minter import NFTMinter

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("genesis.cli")


def cmd_start():
    """Start the autonomous strategy engine."""
    engine = GenesisEngine()
    print(f"Genesis Engine starting (mode={config.MODE}, paused={config.PAUSED})")
    engine.start()


def cmd_stop():
    """Stop the engine (sends signal)."""
    print("To stop the engine, press Ctrl+C in the running terminal.")
    print("The engine handles SIGINT gracefully.")


def cmd_status():
    """Show current engine state."""
    engine = GenesisEngine()
    status = engine.get_status()
    print(json.dumps(status, indent=2, default=str))


def cmd_deploy():
    """Deploy all contracts to X Layer."""
    assembler = HookAssembler()
    print(f"Deploying Genesis contracts to {config.CHAIN_NAME} (chain {config.CHAIN_ID})")
    print(f"  RPC: {config.RPC_URL}")
    print(f"  DRY_RUN: {config.DRY_RUN}")
    print()

    # Deploy assembler first
    wallet = WalletManager()
    master = wallet.get_wallet_address("master")
    print(f"  Master wallet: {master}")

    # Deploy modules
    modules = {}
    for name, mod_config in config.AVAILABLE_MODULES.items():
        print(f"  Deploying {mod_config['contract']}...")
        params = mod_config["default_params"]
        result = assembler.deploy_module(name, params)
        addr = result.get("address", "0x" + "0" * 40)
        modules[name] = addr
        print(f"    → {addr}")

    # Register modules
    for name, addr in modules.items():
        print(f"  Registering {name}...")
        assembler.register_module(addr)

    print()
    print("Deployment complete. Update config.CONTRACTS with deployed addresses.")
    print(json.dumps(modules, indent=2))


def cmd_create_strategy(preset_name=None):
    """Create a strategy from a preset."""
    if not preset_name:
        preset_name = "calm_accumulator"
    if preset_name not in config.STRATEGY_PRESETS:
        print(f"Unknown preset: {preset_name}")
        print(f"Available: {', '.join(config.STRATEGY_PRESETS.keys())}")
        return

    oracle = MarketOracle()
    prices = oracle.fetch_all_prices()
    pair = config.ONCHAINOS_MARKET_PAIRS[0]
    regime = oracle.get_market_regime(pair["base"], pair["quote"])

    manager = StrategyManager()
    result = manager.create_strategy(regime, {"prices": prices, "regime": regime})
    print(json.dumps(result, indent=2, default=str))


def cmd_rebalance(strategy_id):
    """Force rebalance a strategy."""
    oracle = MarketOracle()
    pair = config.ONCHAINOS_MARKET_PAIRS[0]
    regime = oracle.get_market_regime(pair["base"], pair["quote"])

    manager = StrategyManager()
    manager.rebalance_strategy(int(strategy_id), regime)
    print(f"Strategy {strategy_id} rebalanced.")


def cmd_deactivate(strategy_id):
    """Deactivate a strategy."""
    manager = StrategyManager()
    manager.deactivate_strategy(int(strategy_id), "Manual deactivation via CLI")
    print(f"Strategy {strategy_id} deactivated.")


def cmd_mint_nft(strategy_id):
    """Check eligibility and mint Strategy NFT."""
    minter = NFTMinter()
    manager = StrategyManager()

    strategies = manager.get_active_strategies()
    strat = next((s for s in strategies if s.get("id") == int(strategy_id)), None)
    if not strat:
        print(f"Strategy {strategy_id} not found.")
        return

    eligible, reasons = minter.check_mint_eligibility({
        "pnl_bps": strat.get("pnl_bps", 0),
        "total_swaps": strat.get("total_swaps", 0),
        "run_hours": strat.get("run_hours", 0),
    })

    if eligible:
        print(f"Strategy {strategy_id} is eligible for NFT minting!")
        result = minter.mint_strategy_nft(
            strat.get("owner", ""),
            strat,
        )
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"Strategy {strategy_id} is NOT eligible:")
        for r in reasons:
            print(f"  - {r}")


def cmd_journal(strategy_id=None):
    """View decision journal."""
    journal = DecisionJournal()
    if strategy_id:
        entries = journal.get_decisions_by_strategy(int(strategy_id))
    else:
        entries = journal.get_recent_decisions(20)

    for entry in entries:
        print(json.dumps(entry, indent=2, default=str))
        print("---")
    print(f"Total entries shown: {len(entries)}")


def cmd_market():
    """Show current market analysis."""
    oracle = MarketOracle()
    print("Market Analysis")
    print("=" * 60)

    for pair in config.ONCHAINOS_MARKET_PAIRS:
        base, quote = pair["base"], pair["quote"]
        print(f"\n{base}/{quote}:")

        price = oracle.fetch_price(base, quote)
        print(f"  Price:      {price}")

        vol = oracle.calculate_volatility(base, quote)
        print(f"  Volatility: {vol:.2f} bps (24h)")

        trend = oracle.detect_trend(base, quote)
        print(f"  Trend:      {trend}")

        regime = oracle.get_market_regime(base, quote)
        print(f"  Regime:     {regime.get('regime_name', 'unknown')}")
        print(f"  Confidence: {regime.get('confidence', 0):.2f}")


def cmd_config_show():
    """Show current configuration."""
    sections = {
        "Safety": {"PAUSED": config.PAUSED, "MODE": config.MODE, "DRY_RUN": config.DRY_RUN},
        "Chain": {"CHAIN_ID": config.CHAIN_ID, "CHAIN_NAME": config.CHAIN_NAME, "RPC_URL": config.RPC_URL},
        "AI Engine": {
            "PERCEPTION_INTERVAL": config.PERCEPTION_INTERVAL_SEC,
            "ANALYSIS_INTERVAL": config.ANALYSIS_INTERVAL_SEC,
            "CONFIDENCE_THRESHOLD": config.CONFIDENCE_THRESHOLD,
        },
        "NFT Thresholds": {
            "PNL_BPS": config.NFT_MINT_THRESHOLD_PNL_BPS,
            "SWAPS": config.NFT_MINT_THRESHOLD_SWAPS,
            "HOURS": config.NFT_MINT_THRESHOLD_HOURS,
        },
        "Contracts": config.CONTRACTS,
    }
    print(json.dumps(sections, indent=2))


def cmd_x402_pricing():
    """Show x402 payment tiers."""
    print("x402 Payment Tiers")
    print("=" * 60)
    for service, pricing in config.X402_PRICING.items():
        print(f"  {service:25s}  {pricing['amount']} {pricing['token']}  ({pricing['settle']})")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "start": lambda: cmd_start(),
        "stop": lambda: cmd_stop(),
        "status": lambda: cmd_status(),
        "deploy": lambda: cmd_deploy(),
        "create-strategy": lambda: cmd_create_strategy(args[0] if args else None),
        "rebalance": lambda: cmd_rebalance(args[0]) if args else print("Usage: rebalance <strategy_id>"),
        "deactivate": lambda: cmd_deactivate(args[0]) if args else print("Usage: deactivate <strategy_id>"),
        "mint-nft": lambda: cmd_mint_nft(args[0]) if args else print("Usage: mint-nft <strategy_id>"),
        "journal": lambda: cmd_journal(args[0] if args else None),
        "market": lambda: cmd_market(),
        "config": lambda: cmd_config_show() if not args or args[0] == "show" else print("Usage: config show"),
        "x402": lambda: cmd_x402_pricing() if args and args[0] == "pricing" else print("Usage: x402 pricing"),
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
