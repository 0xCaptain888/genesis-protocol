"""Multi-Agent Orchestrator - Coordinates multiple specialized agents.

Each agent operates through a dedicated sub-wallet from the Agentic Wallet
hierarchy, ensuring fund isolation and clear role separation.

Agent Roles:
  - StrategyAgent (wallet index 1): Deploys and manages Hook strategies
  - RebalanceAgent (wallet index 4): Executes position rebalancing
  - IncomeAgent (wallet index 2): Manages revenue collection from x402 payments
  - SentinelAgent (wallet index 0): Monitors system health and approves operations

All agents share the same GenesisHookAssembler contract but use different
sub-wallets for their operations.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from . import config

# Lazy imports for optional modules - handled gracefully per action
_strategy_manager = None
_decision_journal = None
_hook_assembler = None
_wallet_manager = None
_payment_handler = None
_market_oracle = None


def _get_strategy_manager():
    global _strategy_manager
    if _strategy_manager is None:
        try:
            from .strategy_manager import StrategyManager
            _strategy_manager = StrategyManager()
        except ImportError:
            _strategy_manager = None
    return _strategy_manager


def _get_decision_journal():
    global _decision_journal
    if _decision_journal is None:
        try:
            from .decision_journal import DecisionJournal
            _decision_journal = DecisionJournal()
        except ImportError:
            _decision_journal = None
    return _decision_journal


def _get_hook_assembler():
    global _hook_assembler
    if _hook_assembler is None:
        try:
            from .hook_assembler import HookAssembler
            _hook_assembler = HookAssembler()
        except ImportError:
            _hook_assembler = None
    return _hook_assembler


def _get_wallet_manager():
    global _wallet_manager
    if _wallet_manager is None:
        try:
            from .wallet_manager import WalletManager
            _wallet_manager = WalletManager()
        except ImportError:
            _wallet_manager = None
    return _wallet_manager


def _get_payment_handler():
    global _payment_handler
    if _payment_handler is None:
        try:
            from .payment_handler import PaymentHandler
            _payment_handler = PaymentHandler()
        except ImportError:
            _payment_handler = None
    return _payment_handler


def _get_market_oracle():
    global _market_oracle
    if _market_oracle is None:
        try:
            from .market_oracle import MarketOracle
            _market_oracle = MarketOracle()
        except ImportError:
            _market_oracle = None
    return _market_oracle


# Maps agent names to their supported actions
AGENT_CAPABILITIES = {
    "SentinelAgent": ["health_check", "approve_operation", "emergency_stop"],
    "StrategyAgent": ["create_strategy", "update_parameters", "deactivate_strategy"],
    "IncomeAgent": ["collect_revenue", "settle_payment", "report_income"],
    "RebalanceAgent": ["check_rebalance", "execute_rebalance", "twap_step"],
}

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """Tracks the operational state of a single agent."""
    name: str
    wallet_role: str
    wallet_index: int
    status: str = "idle"
    last_action_time: float = 0.0
    action_count: int = 0
    error_count: int = 0
    last_error: str = ""


class MultiAgentOrchestrator:
    """Orchestrates multiple specialized agents operating on X Layer.

    Architecture:
    ┌─────────────────────────────────────────────────────┐
    │               Multi-Agent Orchestrator               │
    │                                                     │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
    │  │ Sentinel │  │ Strategy │  │ Rebalance│         │
    │  │ Agent    │  │ Agent    │  │ Agent    │         │
    │  │ (idx 0)  │  │ (idx 1)  │  │ (idx 4)  │         │
    │  └────┬─────┘  └────┬─────┘  └────┬─────┘         │
    │       │              │              │               │
    │       ▼              ▼              ▼               │
    │  ┌──────────────────────────────────────────┐      │
    │  │        Agentic Wallet (TEE-backed)        │      │
    │  │   5 sub-wallets with role isolation        │      │
    │  └──────────────────────────────────────────┘      │
    │                      │                              │
    │                      ▼                              │
    │  ┌──────────────────────────────────────────┐      │
    │  │     GenesisHookAssembler (X Layer)         │      │
    │  └──────────────────────────────────────────┘      │
    └─────────────────────────────────────────────────────┘
    """

    def __init__(self):
        self.agents: dict[str, AgentState] = {}
        self._init_agents()
        logger.info("MultiAgentOrchestrator initialized with %d agents", len(self.agents))

    def _init_agents(self):
        """Initialize all specialized agents."""
        agent_configs = [
            ("SentinelAgent", "master", 0,
             "Monitors system health, approves high-value operations, emergency shutdown"),
            ("StrategyAgent", "strategy", 1,
             "Deploys and manages Uniswap V4 Hook strategies via GenesisHookAssembler"),
            ("IncomeAgent", "income", 2,
             "Collects x402 payment revenue and manages pay-with-any-token settlements"),
            ("RebalanceAgent", "rebalance", 4,
             "Executes position rebalancing with isolated funds"),
        ]

        for name, role, index, description in agent_configs:
            self.agents[name] = AgentState(
                name=name,
                wallet_role=role,
                wallet_index=index,
            )
            logger.debug("Registered agent: %s (wallet=%s, idx=%d) - %s",
                         name, role, index, description)

    def get_agent(self, name: str) -> Optional[AgentState]:
        """Get agent state by name."""
        return self.agents.get(name)

    def dispatch(self, agent_name: str, action: str, params: dict) -> dict:
        """Dispatch an action to a specific agent.

        Each agent operates through its dedicated sub-wallet, ensuring:
        - Fund isolation (strategy funds separate from rebalance funds)
        - Clear audit trail (each agent's actions are traceable)
        - Risk containment (a bug in RebalanceAgent can't drain StrategyAgent's funds)
        """
        agent = self.agents.get(agent_name)
        if not agent:
            return {"error": f"Unknown agent: {agent_name}"}

        if config.PAUSED and agent_name != "SentinelAgent":
            logger.info("System PAUSED - only SentinelAgent can operate")
            return {"status": "paused", "agent": agent_name}

        logger.info("Dispatching %s to %s (wallet_idx=%d)",
                     action, agent_name, agent.wallet_index)

        agent.status = "executing"
        agent.last_action_time = time.time()

        try:
            result = self._execute_agent_action(agent, action, params)
            agent.action_count += 1
            agent.status = "idle"
            return result
        except Exception as exc:
            agent.error_count += 1
            agent.last_error = str(exc)
            agent.status = "error"
            logger.error("Agent %s failed: %s", agent_name, exc)
            return {"error": str(exc), "agent": agent_name}

    def _execute_agent_action(self, agent: AgentState, action: str, params: dict) -> dict:
        """Execute a specific action for an agent.

        Routes to the appropriate handler based on agent name and action.
        Each handler returns a structured result dict with status, details,
        and timestamps.  DRY_RUN is respected inside each handler.
        """
        # Validate that the action is supported for this agent
        supported = AGENT_CAPABILITIES.get(agent.name, [])
        if action not in supported:
            return {
                "error": f"Unsupported action '{action}' for {agent.name}",
                "supported_actions": supported,
            }

        # Build a base result that every handler augments
        base = {
            "agent": agent.name,
            "action": action,
            "wallet_index": agent.wallet_index,
            "dry_run": config.DRY_RUN,
            "timestamp": int(time.time()),
        }

        # Route to the correct agent handler
        handler_map = {
            "SentinelAgent": self._handle_sentinel,
            "StrategyAgent": self._handle_strategy,
            "IncomeAgent": self._handle_income,
            "RebalanceAgent": self._handle_rebalance,
        }
        handler = handler_map.get(agent.name)
        if handler is None:
            return {**base, "error": f"No handler registered for {agent.name}"}

        result = handler(agent, action, params)
        result.update(base)
        return result

    # ── SentinelAgent handlers ───────────────────────────────────────────

    def _handle_sentinel(self, agent: AgentState, action: str, params: dict) -> dict:
        if action == "health_check":
            return self._sentinel_health_check(agent, params)
        elif action == "approve_operation":
            return self._sentinel_approve_operation(agent, params)
        elif action == "emergency_stop":
            return self._sentinel_emergency_stop(agent, params)
        return {"error": f"Unknown sentinel action: {action}"}

    def _sentinel_health_check(self, agent: AgentState, params: dict) -> dict:
        """Run system-wide health check across all agents."""
        logger.info("[SentinelAgent] Running system-wide health check")

        total_errors = sum(a.error_count for a in self.agents.values())
        all_idle = all(a.status == "idle" or a.name == agent.name
                       for a in self.agents.values())
        error_rate = total_errors / max(
            sum(a.action_count for a in self.agents.values()), 1
        )
        agent_statuses = {}
        for name, a in self.agents.items():
            agent_statuses[name] = {
                "status": a.status,
                "action_count": a.action_count,
                "error_count": a.error_count,
                "last_error": a.last_error,
            }

        healthy = total_errors == 0 and all_idle and not config.PAUSED
        return {
            "status": "healthy" if healthy else "degraded",
            "all_idle": all_idle,
            "total_errors": total_errors,
            "error_rate": round(error_rate, 4),
            "paused": config.PAUSED,
            "mode": config.MODE,
            "agent_statuses": agent_statuses,
        }

    def _sentinel_approve_operation(self, agent: AgentState, params: dict) -> dict:
        """Validate and approve high-value operations."""
        logger.info("[SentinelAgent] Evaluating operation approval: %s", params)

        position_size_pct = params.get("position_size_pct", 0)
        max_allowed = config.MAX_POSITION_SIZE_PCT
        operation_type = params.get("operation_type", "unknown")
        strategy_id = params.get("strategy_id", "")

        if position_size_pct > max_allowed:
            reason = (f"Position size {position_size_pct}% exceeds "
                      f"MAX_POSITION_SIZE_PCT ({max_allowed}%)")
            logger.warning("[SentinelAgent] Operation REJECTED: %s", reason)
            journal = _get_decision_journal()
            if journal:
                journal.log_decision(
                    strategy_id, "FUND_TRANSFER",
                    f"Sentinel rejected: {reason}",
                    {"position_size_pct": position_size_pct, "max_allowed": max_allowed},
                )
            return {
                "status": "rejected",
                "approved": False,
                "reason": reason,
                "position_size_pct": position_size_pct,
                "max_allowed": max_allowed,
            }

        logger.info("[SentinelAgent] Operation APPROVED (size=%s%%, type=%s)",
                     position_size_pct, operation_type)
        return {
            "status": "approved",
            "approved": True,
            "operation_type": operation_type,
            "position_size_pct": position_size_pct,
            "max_allowed": max_allowed,
        }

    def _sentinel_emergency_stop(self, agent: AgentState, params: dict) -> dict:
        """Set all agents to stopped status and log to decision journal."""
        reason = params.get("reason", "Emergency stop triggered")
        logger.critical("[SentinelAgent] EMERGENCY STOP: %s", reason)

        stopped_agents = []
        for name, a in self.agents.items():
            a.status = "stopped"
            stopped_agents.append(name)
            logger.info("[SentinelAgent] Stopped agent: %s", name)

        # Log to decision journal
        journal = _get_decision_journal()
        if journal:
            journal.log_decision(
                0, "STRATEGY_DEACTIVATE",
                f"Emergency stop: {reason}",
                {"stopped_agents": stopped_agents, "reason": reason},
            )

        return {
            "status": "emergency_stopped",
            "stopped_agents": stopped_agents,
            "reason": reason,
        }

    # ── StrategyAgent handlers ───────────────────────────────────────────

    def _handle_strategy(self, agent: AgentState, action: str, params: dict) -> dict:
        if action == "create_strategy":
            return self._strategy_create(agent, params)
        elif action == "update_parameters":
            return self._strategy_update_parameters(agent, params)
        elif action == "deactivate_strategy":
            return self._strategy_deactivate(agent, params)
        return {"error": f"Unknown strategy action: {action}"}

    def _strategy_create(self, agent: AgentState, params: dict) -> dict:
        """Select preset based on market regime, compose modules via hook_assembler."""
        logger.info("[StrategyAgent] Creating strategy with params: %s", params)

        market_regime = params.get("market_regime", "low_vol")
        market_data = params.get("market_data", {})

        if config.DRY_RUN:
            logger.info("[StrategyAgent] DRY_RUN: simulating strategy creation")
            assembler = _get_hook_assembler()
            preset_name, modules = ("calm_accumulator", ["dynamic_fee", "auto_rebalance"])
            if assembler:
                preset_name, modules = assembler.select_modules(
                    {"volatility_bps": market_data.get("volatility_bps", 0),
                     "trend": market_data.get("trend", "sideways")}
                )
            return {
                "status": "simulated",
                "preset_name": preset_name,
                "modules": modules,
                "market_regime": market_regime,
            }

        sm = _get_strategy_manager()
        if sm is None:
            return {"status": "error", "error": "StrategyManager unavailable"}

        record = sm.create_strategy(market_regime, market_data)
        if record.get("error"):
            return {"status": "error", "error": record["error"]}

        return {
            "status": "created",
            "strategy_id": record.get("id", ""),
            "preset_name": record.get("preset_name", ""),
            "modules": record.get("modules", []),
            "market_regime": market_regime,
        }

    def _strategy_update_parameters(self, agent: AgentState, params: dict) -> dict:
        """Adjust module parameters based on analysis layer output."""
        logger.info("[StrategyAgent] Updating parameters: %s", params)

        strategy_id = params.get("strategy_id", "")
        new_params = params.get("module_params", {})

        if not strategy_id:
            return {"status": "error", "error": "strategy_id is required"}

        if config.DRY_RUN:
            logger.info("[StrategyAgent] DRY_RUN: simulating parameter update")
            return {
                "status": "simulated",
                "strategy_id": strategy_id,
                "updated_params": new_params,
            }

        assembler = _get_hook_assembler()
        if assembler is None:
            return {"status": "error", "error": "HookAssembler unavailable"}

        results = {}
        for module_address, encoded_params in new_params.items():
            result = assembler.update_module_params(module_address, encoded_params)
            results[module_address] = result

        journal = _get_decision_journal()
        if journal:
            journal.log_decision(
                strategy_id, "FEE_ADJUST",
                f"Updated parameters for strategy {strategy_id}",
                {"module_updates": list(new_params.keys())},
            )

        return {
            "status": "updated",
            "strategy_id": strategy_id,
            "module_results": results,
        }

    def _strategy_deactivate(self, agent: AgentState, params: dict) -> dict:
        """Mark strategy inactive and log decision."""
        logger.info("[StrategyAgent] Deactivating strategy: %s", params)

        strategy_id = params.get("strategy_id", "")
        reason = params.get("reason", "Manual deactivation")

        if not strategy_id:
            return {"status": "error", "error": "strategy_id is required"}

        if config.DRY_RUN:
            logger.info("[StrategyAgent] DRY_RUN: simulating deactivation")
            return {
                "status": "simulated",
                "strategy_id": strategy_id,
                "reason": reason,
            }

        sm = _get_strategy_manager()
        if sm is None:
            return {"status": "error", "error": "StrategyManager unavailable"}

        sm.deactivate_strategy(strategy_id, reason)
        return {
            "status": "deactivated",
            "strategy_id": strategy_id,
            "reason": reason,
        }

    # ── IncomeAgent handlers ─────────────────────────────────────────────

    def _handle_income(self, agent: AgentState, action: str, params: dict) -> dict:
        if action == "collect_revenue":
            return self._income_collect_revenue(agent, params)
        elif action == "settle_payment":
            return self._income_settle_payment(agent, params)
        elif action == "report_income":
            return self._income_report(agent, params)
        return {"error": f"Unknown income action: {action}"}

    def _income_collect_revenue(self, agent: AgentState, params: dict) -> dict:
        """Query income wallet balance and log revenue stats."""
        logger.info("[IncomeAgent] Collecting revenue")

        wm = _get_wallet_manager()
        if wm is None:
            return {"status": "error", "error": "WalletManager unavailable"}

        if config.DRY_RUN:
            logger.info("[IncomeAgent] DRY_RUN: simulating revenue collection")
            return {
                "status": "simulated",
                "balance": "0",
                "collected": False,
            }

        balance_info = wm.get_balance("income", token="USDT")
        balance = balance_info.get("balance", balance_info.get("amount", "0"))

        result = wm.collect_income()
        collected = result.get("status") != "empty"

        logger.info("[IncomeAgent] Revenue collection: balance=%s collected=%s",
                     balance, collected)
        return {
            "status": "collected" if collected else "empty",
            "balance": balance,
            "collected": collected,
            "transfer_result": result,
        }

    def _income_settle_payment(self, agent: AgentState, params: dict) -> dict:
        """Process x402 payment settlement."""
        logger.info("[IncomeAgent] Settling payment: %s", params)

        product = params.get("product", "")
        payer_token = params.get("payer_token", "USDT")
        payer_address = params.get("payer_address", "")

        if not product or not payer_address:
            return {"status": "error", "error": "product and payer_address are required"}

        ph = _get_payment_handler()
        if ph is None:
            return {"status": "error", "error": "PaymentHandler unavailable"}

        if config.DRY_RUN:
            logger.info("[IncomeAgent] DRY_RUN: simulating payment settlement")
            return {
                "status": "simulated",
                "product": product,
                "payer_token": payer_token,
                "payer_address": payer_address,
            }

        result = ph.process_payment(product, payer_token, payer_address)
        return {
            "status": "settled" if result.get("success") else "failed",
            "product": product,
            "payment_result": result,
        }

    def _income_report(self, agent: AgentState, params: dict) -> dict:
        """Generate income summary."""
        logger.info("[IncomeAgent] Generating income report")

        wm = _get_wallet_manager()
        balance_info = {}
        if wm:
            balance_info = wm.get_balance("income", token="USDT")

        journal = _get_decision_journal()
        recent_decisions = []
        if journal:
            recent_decisions = journal.get_decisions_by_type("FUND_TRANSFER")

        ph = _get_payment_handler()
        pricing = {}
        if ph:
            pricing = ph.get_pricing()

        return {
            "status": "reported",
            "income_wallet_balance": balance_info.get(
                "balance", balance_info.get("amount", "0")
            ),
            "x402_pricing": pricing,
            "recent_transfers": len(recent_decisions),
            "x402_enabled": config.X402_ENABLED,
        }

    # ── RebalanceAgent handlers ──────────────────────────────────────────

    def _handle_rebalance(self, agent: AgentState, action: str, params: dict) -> dict:
        if action == "check_rebalance":
            return self._rebalance_check(agent, params)
        elif action == "execute_rebalance":
            return self._rebalance_execute(agent, params)
        elif action == "twap_step":
            return self._rebalance_twap_step(agent, params)
        return {"error": f"Unknown rebalance action: {action}"}

    def _rebalance_check(self, agent: AgentState, params: dict) -> dict:
        """Evaluate if rebalance is needed based on position boundaries."""
        logger.info("[RebalanceAgent] Checking rebalance conditions: %s", params)

        strategy_id = params.get("strategy_id", "")
        market_data = params.get("market_data", {})

        if not strategy_id:
            return {"status": "error", "error": "strategy_id is required"}

        sm = _get_strategy_manager()
        if sm is None:
            return {"status": "error", "error": "StrategyManager unavailable"}

        needs_rebalance, reason = sm.should_rebalance(strategy_id, market_data)
        logger.info("[RebalanceAgent] Rebalance check: needed=%s reason=%s",
                     needs_rebalance, reason)
        return {
            "status": "checked",
            "strategy_id": strategy_id,
            "needs_rebalance": needs_rebalance,
            "reason": reason,
        }

    def _rebalance_execute(self, agent: AgentState, params: dict) -> dict:
        """Execute rebalance via DEX aggregator with slippage check."""
        logger.info("[RebalanceAgent] Executing rebalance: %s", params)

        strategy_id = params.get("strategy_id", "")
        new_market_regime = params.get("new_market_regime", "low_vol")
        max_slippage_bps = params.get("max_slippage_bps", config.DEX_SLIPPAGE_BPS)

        if not strategy_id:
            return {"status": "error", "error": "strategy_id is required"}

        if config.DRY_RUN:
            logger.info("[RebalanceAgent] DRY_RUN: simulating rebalance execution")
            return {
                "status": "simulated",
                "strategy_id": strategy_id,
                "new_market_regime": new_market_regime,
                "max_slippage_bps": max_slippage_bps,
            }

        # Check slippage via market oracle before executing
        oracle = _get_market_oracle()
        if oracle and config.DEX_COMPARE_WITH_HOOK:
            pair = config.ONCHAINOS_MARKET_PAIRS[0] if config.ONCHAINOS_MARKET_PAIRS else {}
            if pair:
                quote = oracle.get_dex_quote(
                    pair.get("base", "ETH"),
                    pair.get("quote", "USDC"),
                    1.0,
                )
                if quote and quote.get("slippage_bps", 0) > max_slippage_bps:
                    logger.warning("[RebalanceAgent] Slippage too high: %s > %s",
                                   quote.get("slippage_bps"), max_slippage_bps)
                    return {
                        "status": "aborted",
                        "strategy_id": strategy_id,
                        "reason": "slippage exceeds limit",
                        "slippage_bps": quote.get("slippage_bps", 0),
                        "max_slippage_bps": max_slippage_bps,
                    }

        sm = _get_strategy_manager()
        if sm is None:
            return {"status": "error", "error": "StrategyManager unavailable"}

        sm.rebalance_strategy(strategy_id, new_market_regime)
        return {
            "status": "rebalanced",
            "strategy_id": strategy_id,
            "new_market_regime": new_market_regime,
        }

    def _rebalance_twap_step(self, agent: AgentState, params: dict) -> dict:
        """Execute one step of a TWAP rebalance strategy."""
        logger.info("[RebalanceAgent] Executing TWAP step: %s", params)

        strategy_id = params.get("strategy_id", "")
        step_number = params.get("step_number", 1)
        total_steps = params.get("total_steps", 5)
        token_in = params.get("token_in", "ETH")
        token_out = params.get("token_out", "USDC")
        total_amount = params.get("total_amount", 0)

        if not strategy_id or total_amount <= 0:
            return {"status": "error", "error": "strategy_id and positive total_amount required"}

        step_amount = total_amount / total_steps

        if config.DRY_RUN:
            logger.info("[RebalanceAgent] DRY_RUN: simulating TWAP step %d/%d",
                         step_number, total_steps)
            return {
                "status": "simulated",
                "strategy_id": strategy_id,
                "step_number": step_number,
                "total_steps": total_steps,
                "step_amount": step_amount,
                "token_in": token_in,
                "token_out": token_out,
            }

        oracle = _get_market_oracle()
        if oracle is None:
            return {"status": "error", "error": "MarketOracle unavailable"}

        quote = oracle.get_dex_quote(token_in, token_out, step_amount)
        if quote is None:
            return {
                "status": "error",
                "error": "Failed to get DEX quote for TWAP step",
                "step_number": step_number,
            }

        journal = _get_decision_journal()
        if journal:
            journal.log_decision(
                strategy_id, "REBALANCE_EXECUTE",
                f"TWAP step {step_number}/{total_steps}: {step_amount} {token_in}->{token_out}",
                {"step": step_number, "total_steps": total_steps,
                 "step_amount": step_amount, "quote": quote},
            )

        logger.info("[RebalanceAgent] TWAP step %d/%d executed: %s %s -> %s",
                     step_number, total_steps, step_amount, token_in, token_out)
        return {
            "status": "executed",
            "strategy_id": strategy_id,
            "step_number": step_number,
            "total_steps": total_steps,
            "step_amount": step_amount,
            "complete": step_number >= total_steps,
            "quote": quote,
        }

    # ── Coordination & capabilities ──────────────────────────────────────

    def coordinate_cycle(self) -> dict:
        """Run a full coordination cycle across all agents.

        Order: sentinel health check -> strategy eval -> rebalance check -> income collection.
        Returns a summary dict with results from each phase.
        """
        logger.info("Starting coordination cycle")
        cycle_start = time.time()
        results = {}

        # Phase 1: Sentinel health check
        health = self.dispatch("SentinelAgent", "health_check", {})
        results["health_check"] = health
        if health.get("status") == "emergency_stopped":
            logger.warning("Coordination cycle aborted: system in emergency stop")
            results["aborted"] = True
            results["cycle_duration_sec"] = round(time.time() - cycle_start, 3)
            return results

        # Phase 2: Strategy evaluation - check active strategies
        sm = _get_strategy_manager()
        strategy_results = []
        if sm:
            active = sm.get_active_strategies()
            for record in active:
                sid = record.get("id", "")
                perf = sm.evaluate_performance(sid)
                strategy_results.append({"strategy_id": sid, "performance": perf})

                # Check if strategy should be deactivated
                should_deactivate, reason = sm.should_deactivate(sid, perf)
                if should_deactivate:
                    self.dispatch("StrategyAgent", "deactivate_strategy",
                                  {"strategy_id": sid, "reason": reason})
                    strategy_results[-1]["deactivated"] = True
                    strategy_results[-1]["deactivate_reason"] = reason
        results["strategy_eval"] = strategy_results

        # Phase 3: Rebalance check for active strategies
        rebalance_results = []
        if sm:
            oracle = _get_market_oracle()
            market_data = {}
            if oracle:
                pair = config.ONCHAINOS_MARKET_PAIRS[0] if config.ONCHAINOS_MARKET_PAIRS else {}
                if pair:
                    base, quote = pair.get("base", "ETH"), pair.get("quote", "USDC")
                    vol = oracle.calculate_volatility(base, quote)
                    trend = oracle.detect_trend(base, quote)
                    market_data = {
                        "volatility_bps": int(vol * 10000) if vol else 0,
                        "trend": trend,
                    }

            for record in sm.get_active_strategies():
                sid = record.get("id", "")
                check = self.dispatch("RebalanceAgent", "check_rebalance",
                                      {"strategy_id": sid, "market_data": market_data})
                rebalance_results.append(check)
                if check.get("needs_rebalance"):
                    regime = market_data.get("trend", "low_vol")
                    exec_result = self.dispatch(
                        "RebalanceAgent", "execute_rebalance",
                        {"strategy_id": sid, "new_market_regime": regime},
                    )
                    rebalance_results.append(exec_result)
        results["rebalance"] = rebalance_results

        # Phase 4: Income collection
        income_result = self.dispatch("IncomeAgent", "collect_revenue", {})
        results["income_collection"] = income_result

        results["cycle_duration_sec"] = round(time.time() - cycle_start, 3)
        logger.info("Coordination cycle complete in %.3fs", results["cycle_duration_sec"])
        return results

    def get_agent_capabilities(self, name: str) -> list[str]:
        """Return list of supported actions for a given agent.

        Args:
            name: Agent name (e.g. 'SentinelAgent').

        Returns:
            List of action strings, or empty list if agent not found.
        """
        return list(AGENT_CAPABILITIES.get(name, []))

    def get_all_status(self) -> dict:
        """Get status snapshot of all agents."""
        return {
            name: {
                "wallet_role": agent.wallet_role,
                "wallet_index": agent.wallet_index,
                "status": agent.status,
                "action_count": agent.action_count,
                "error_count": agent.error_count,
                "last_action": int(agent.last_action_time) if agent.last_action_time else None,
            }
            for name, agent in self.agents.items()
        }

    def health_check(self) -> dict:
        """Run a system-wide health check across all agents."""
        total_errors = sum(a.error_count for a in self.agents.values())
        all_idle = all(a.status == "idle" for a in self.agents.values())

        return {
            "healthy": total_errors == 0 and all_idle,
            "total_agents": len(self.agents),
            "total_actions": sum(a.action_count for a in self.agents.values()),
            "total_errors": total_errors,
            "all_idle": all_idle,
            "paused": config.PAUSED,
            "mode": config.MODE,
            "agents": self.get_all_status(),
        }
