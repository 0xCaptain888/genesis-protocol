"""Genesis Engine - 5-Layer Cognitive Architecture for the Genesis Protocol.
Layers: Perception -> Analysis -> Planning -> Evolution -> Meta-Cognition.
Only stdlib imports. All decisions logged to DecisionJournal.
"""
import logging
import time
import json
import os

from . import config
from .market_oracle import MarketOracle
from .wallet_manager import WalletManager
from .decision_journal import DecisionJournal
from .strategy_manager import StrategyManager

logger = logging.getLogger(__name__)


class GenesisEngine:
    """5-layer AI cognitive engine orchestrating the Genesis Protocol."""

    def __init__(self):
        self.oracle = MarketOracle()
        self.wallet = WalletManager()
        self.journal = DecisionJournal()
        self.strategy_mgr = StrategyManager()
        self._last_perception = 0.0
        self._last_analysis = 0.0
        self._last_evolution = 0.0
        self._cycle_count = 0
        self._world_state: dict = {}
        self._analysis_cache: dict = {}
        self._running = False
        self._preferences = {
            "risk_tolerance": 0.5, "rebalance_eagerness": 0.5, "new_strategy_bias": 0.5,
        }
        self._predictions: list = []   # [(ts, prediction_dict, outcome_dict|None)]
        self._prediction_accuracy = 0.5
        logger.info("GenesisEngine initialized (paused=%s, mode=%s)", config.PAUSED, config.MODE)

    # ═══════════════════════════════════════════════════════════════════
    # LAYER 1 — PERCEPTION: gather world state
    # ═══════════════════════════════════════════════════════════════════

    def perceive(self) -> dict:
        """Fetch market data, wallet balances, strategy statuses. Returns world-state dict."""
        try:
            prices = self.oracle.fetch_all_prices()
            balances = self.wallet.get_all_balances()
            active = self.strategy_mgr.get_active_strategies()
            health = {s["id"]: self.strategy_mgr.monitor_strategy(s["id"]) for s in active}
            self._world_state = {
                "timestamp": int(time.time()),
                "prices": {f"{k[0]}/{k[1]}": v for k, v in prices.items()},
                "balances": balances, "active_strategies": active,
                "strategy_health": health,
                "strategy_summary": self.strategy_mgr.get_strategy_summary(),
            }
            self._last_perception = time.time()
            logger.info("Perception: %d prices, %d strategies", len(prices), len(active))
        except Exception as exc:
            logger.error("Perception layer failed: %s", exc)
            self._world_state["error"] = str(exc)
        return self._world_state

    # ═══════════════════════════════════════════════════════════════════
    # LAYER 2 — ANALYSIS: regime detection, mismatch & anomaly finding
    # ═══════════════════════════════════════════════════════════════════

    def analyze(self) -> dict:
        """Analyze market regimes, compare strategies to optimal, detect anomalies."""
        try:
            regimes = {}
            for pair in config.ONCHAINOS_MARKET_PAIRS:
                b, q = pair["base"], pair["quote"]
                regimes[f"{b}/{q}"] = self.oracle.get_market_regime(b, q)
            # Strategy-regime mismatch detection
            mismatches = []
            first_regime = next((r.get("regime_name", "") for r in regimes.values()), "")
            for strat in self._world_state.get("active_strategies", []):
                created = strat.get("market_regime_at_creation", "")
                if created and first_regime and created != first_regime:
                    mismatches.append({"strategy_id": strat["id"], "was": created, "now": first_regime})
            anomalies = self._detect_anomalies(regimes)
            self._analysis_cache = {
                "timestamp": int(time.time()), "regimes": regimes,
                "mismatches": mismatches, "anomalies": anomalies,
            }
            self._last_analysis = time.time()
            logger.info("Analysis: %d regimes, %d mismatches, %d anomalies",
                        len(regimes), len(mismatches), len(anomalies))
        except Exception as exc:
            logger.error("Analysis layer failed: %s", exc)
            self._analysis_cache["error"] = str(exc)
        return self._analysis_cache

    def _detect_anomalies(self, regimes: dict) -> list:
        """Detect sudden vol spikes and balance drain."""
        anomalies = []
        for pair_key, regime in regimes.items():
            vol = regime.get("volatility")
            if vol is not None and vol > 0.10:
                anomalies.append({"type": "vol_spike", "pair": pair_key,
                                  "volatility": vol, "severity": "high"})
        for role, bal_data in self._world_state.get("balances", {}).items():
            if role == "reserve":
                raw = bal_data.get("balance", bal_data.get("amount", "0"))
                try:
                    if float(raw) <= 0:
                        anomalies.append({"type": "balance_drain", "wallet": role,
                                          "balance": raw, "severity": "critical"})
                except (ValueError, TypeError):
                    pass
        return anomalies

    # ═══════════════════════════════════════════════════════════════════
    # LAYER 3 — PLANNING: generate actions with confidence scores
    # ═══════════════════════════════════════════════════════════════════

    def plan(self) -> list:
        """Generate action plan: create/adjust/rebalance/deactivate/hold. Returns action list."""
        actions: list = []
        try:
            regimes = self._analysis_cache.get("regimes", {})
            mismatches = self._analysis_cache.get("mismatches", [])
            anomalies = self._analysis_cache.get("anomalies", [])
            active = self._world_state.get("active_strategies", [])

            # Critical anomalies -> hold
            for a in anomalies:
                if a["severity"] == "critical":
                    target = a.get("wallet", a.get("pair", "?"))
                    actions.append({"type": "hold", "confidence": 0.95,
                                    "reasoning": f"Critical anomaly: {a['type']} on {target}",
                                    "params": {"anomaly": a}})
            # Rebalance mismatched strategies
            for mm in mismatches:
                conf = min(0.6 + self._preferences["rebalance_eagerness"] * 0.3, 0.95)
                actions.append({"type": "rebalance", "confidence": conf,
                                "reasoning": f"Regime shifted {mm['was']}->{mm['now']} for {mm['strategy_id']}",
                                "params": {"strategy_id": mm["strategy_id"], "new_regime": mm["now"]}})
            # Evaluate existing strategies for deactivation
            for strat in active:
                sid = strat["id"]
                perf = self.strategy_mgr.evaluate_performance(sid)
                should, reason = self.strategy_mgr.should_deactivate(sid, perf)
                if should:
                    actions.append({"type": "deactivate", "confidence": 0.85,
                                    "reasoning": f"Deactivate {sid}: {reason}",
                                    "params": {"strategy_id": sid, "reason": reason}})
            # Create new strategy if few active and regime is clear
            if len(active) < 2 and regimes:
                best_r, best_c = None, 0.0
                for regime in regimes.values():
                    c = regime.get("confidence", 0)
                    if c > best_c:
                        best_c, best_r = c, regime
                if best_r and best_c > config.CONFIDENCE_THRESHOLD:
                    bias = self._preferences["new_strategy_bias"]
                    actions.append({
                        "type": "create_strategy",
                        "confidence": min(best_c * (0.7 + bias * 0.3), 0.95),
                        "reasoning": f"Regime {best_r['regime_name']} confidence {best_c:.2f}",
                        "params": {"regime": best_r["regime_name"], "market_data": best_r},
                    })
            # Default hold
            if not actions:
                actions.append({"type": "hold", "confidence": 1.0,
                                "reasoning": "All strategies within bounds", "params": {}})
            # Track predictions for meta-cognition
            for act in actions:
                if act["type"] != "hold":
                    self._predictions.append((time.time(), {
                        "action": act["type"], "confidence": act["confidence"],
                        "reasoning": act["reasoning"]}, None))
            logger.info("Planning: %d actions planned", len(actions))
        except Exception as exc:
            logger.error("Planning layer failed: %s", exc)
        return actions

    # ═══════════════════════════════════════════════════════════════════
    # LAYER 4 — EVOLUTION: adjust preferences via meta-learning
    # ═══════════════════════════════════════════════════════════════════

    def evolve(self) -> dict:
        """Adjust internal preferences based on historical performance."""
        try:
            summary = self.strategy_mgr.get_strategy_summary()
            avg_pnl = summary.get("avg_pnl_bps", 0)
            active_n = summary.get("active_count", 0)
            old = dict(self._preferences)
            p = self._preferences
            # Risk tolerance adapts to P&L
            if avg_pnl > 100:
                p["risk_tolerance"] = min(p["risk_tolerance"] + 0.05, 0.9)
            elif avg_pnl < -100:
                p["risk_tolerance"] = max(p["risk_tolerance"] - 0.05, 0.1)
            # Rebalance eagerness: increase if frequent rebalances in history
            recent = self.journal.get_recent_decisions(20)
            if sum(1 for d in recent if d.get("decision_type") == "REBALANCE_EXECUTE") > 3:
                p["rebalance_eagerness"] = min(p["rebalance_eagerness"] + 0.05, 0.9)
            # New strategy bias: fewer active -> more eager
            if active_n > 3:
                p["new_strategy_bias"] = max(p["new_strategy_bias"] - 0.1, 0.1)
            elif active_n == 0:
                p["new_strategy_bias"] = min(p["new_strategy_bias"] + 0.1, 0.9)
            # Low prediction accuracy -> reduce risk
            if self._prediction_accuracy < 0.4:
                p["risk_tolerance"] = max(p["risk_tolerance"] - 0.1, 0.1)
            self._last_evolution = time.time()
            self.journal.log_decision(0, "META_COGNITION",
                f"Evolution: prefs {old} -> {p}",
                {"old": old, "new": dict(p), "avg_pnl_bps": avg_pnl,
                 "prediction_accuracy": self._prediction_accuracy})
            logger.info("Evolution complete: %s", p)
            return {"old": old, "new": dict(p)}
        except Exception as exc:
            logger.error("Evolution layer failed: %s", exc)
            return {"error": str(exc)}

    # ═══════════════════════════════════════════════════════════════════
    # LAYER 5 — META-COGNITION: self-assess prediction quality
    # ═══════════════════════════════════════════════════════════════════
    def reflect(self) -> dict:
        """Evaluate decision quality: compare predictions to actual outcomes."""
        try:
            resolved = correct = 0
            recent_decisions = self.journal.get_recent_decisions(50)
            for i, (ts, pred, outcome) in enumerate(self._predictions):
                if outcome is not None:
                    continue
                atype = pred.get("action", "")
                matched = [d for d in recent_decisions
                           if d.get("decision_type", "").lower().replace("_", "")
                           == atype.replace("_", "") and d.get("timestamp", 0) >= ts]
                if matched:
                    self._predictions[i] = (ts, pred, {"executed": True, "n": len(matched)})
                    resolved += 1
                    if pred.get("confidence", 0) > config.CONFIDENCE_THRESHOLD:
                        correct += 1
            total = sum(1 for _, _, o in self._predictions if o is not None)
            self._prediction_accuracy = (correct / total) if total > 0 else 0.5
            if len(self._predictions) > 100:
                self._predictions = self._predictions[-100:]
            insights = {
                "total_predictions": len(self._predictions),
                "resolved_this_cycle": resolved,
                "prediction_accuracy": round(self._prediction_accuracy, 3),
                "preferences": dict(self._preferences),
            }
            self.journal.log_decision(0, "META_COGNITION",
                f"Reflection: accuracy={self._prediction_accuracy:.2%}, resolved={resolved}",
                insights)
            logger.info("Reflection: accuracy=%.1f%%, %d tracked",
                        self._prediction_accuracy * 100, len(self._predictions))
            return insights
        except Exception as exc:
            logger.error("Meta-cognition layer failed: %s", exc)
            return {"error": str(exc)}

    # ═══════════════════════════════════════════════════════════════════
    # ORCHESTRATION: execute_plan, run_cycle, start/stop, status
    # ═══════════════════════════════════════════════════════════════════
    def execute_plan(self, actions: list) -> list:
        """Dispatch actions to managers. Respects CONFIDENCE_THRESHOLD and PAUSED."""
        results = []
        for action in actions:
            atype, conf = action["type"], action.get("confidence", 0)
            params = action.get("params", {})
            if conf < config.CONFIDENCE_THRESHOLD:
                logger.info("Skip %s (conf %.2f < %.2f)", atype, conf, config.CONFIDENCE_THRESHOLD)
                results.append({"action": atype, "status": "skipped_low_confidence"})
                continue
            if config.PAUSED:
                logger.info("PAUSED — skip %s", atype)
                results.append({"action": atype, "status": "paused"})
                continue
            try:
                if atype == "create_strategy":
                    r = self.strategy_mgr.create_strategy(params["regime"], params.get("market_data", {}))
                    results.append({"action": atype, "status": "ok", "result": r})
                elif atype == "rebalance":
                    self.strategy_mgr.rebalance_strategy(params["strategy_id"], params["new_regime"])
                    results.append({"action": atype, "status": "ok"})
                elif atype == "deactivate":
                    self.strategy_mgr.deactivate_strategy(params["strategy_id"], params["reason"])
                    results.append({"action": atype, "status": "ok"})
                elif atype == "hold":
                    results.append({"action": atype, "status": "ok"})
                else:
                    logger.warning("Unknown action type: %s", atype)
                    results.append({"action": atype, "status": "unknown_type"})
            except Exception as exc:
                logger.error("Execute %s failed: %s", atype, exc)
                results.append({"action": atype, "status": "error", "error": str(exc)})
        return results

    def run_cycle(self) -> dict:
        """One full cognitive cycle: perceive -> analyze -> plan -> execute -> reflect."""
        self._cycle_count += 1
        t0 = time.time()
        logger.info("=== Cycle %d start ===", self._cycle_count)
        self.perceive()
        now = time.time()
        if now - self._last_analysis >= config.ANALYSIS_INTERVAL_SEC or self._cycle_count == 1:
            self.analyze()
        actions = self.plan()
        results = self.execute_plan(actions)
        evolution = self.evolve() if (now - self._last_evolution >= config.EVOLUTION_INTERVAL_SEC) else None
        reflection = self.reflect()
        elapsed = time.time() - t0
        logger.info("=== Cycle %d done (%.2fs) ===", self._cycle_count, elapsed)
        return {
            "cycle": self._cycle_count, "elapsed_sec": round(elapsed, 3),
            "actions_planned": len(actions),
            "actions_executed": sum(1 for r in results if r["status"] == "ok"),
            "evolution": evolution,
            "prediction_accuracy": reflection.get("prediction_accuracy"),
        }

    def start(self):
        """Main loop — runs cycles at PERCEPTION_INTERVAL_SEC."""
        self._running = True
        logger.info("GenesisEngine starting (interval=%ds)", config.PERCEPTION_INTERVAL_SEC)
        try:
            while self._running:
                self.run_cycle()
                time.sleep(config.PERCEPTION_INTERVAL_SEC)
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            logger.info("GenesisEngine stopped")

    def stop(self):
        """Signal the main loop to stop after the current cycle."""
        self._running = False

    def get_status(self) -> dict:
        """Current engine status for external monitoring."""
        return {
            "running": self._running, "paused": config.PAUSED, "mode": config.MODE,
            "cycle_count": self._cycle_count,
            "prediction_accuracy": round(self._prediction_accuracy, 3),
            "preferences": dict(self._preferences),
            "active_strategies": self.strategy_mgr.get_strategy_summary(),
            "last_perception": int(self._last_perception) or None,
            "last_analysis": int(self._last_analysis) or None,
            "last_evolution": int(self._last_evolution) or None,
        }
