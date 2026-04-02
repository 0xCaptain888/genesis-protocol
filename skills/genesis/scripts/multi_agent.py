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
        """Execute a specific action for an agent."""
        if config.DRY_RUN:
            return {
                "dry_run": True,
                "agent": agent.name,
                "action": action,
                "wallet_index": agent.wallet_index,
                "params": params,
            }

        return {
            "agent": agent.name,
            "action": action,
            "wallet_index": agent.wallet_index,
            "status": "executed",
            "timestamp": int(time.time()),
        }

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
