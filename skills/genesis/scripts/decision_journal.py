"""Decision journal for logging AI decisions locally and on-chain.

Records every strategy decision to a local JSONL file and, when enabled,
to the GenesisHookAssembler's logDecision function via the onchainos CLI.
"""

import subprocess
import json
import logging
import os
import time
import hashlib

from . import config

logger = logging.getLogger(__name__)


class DecisionJournal:
    """Logs AI decisions to a local JSONL file and on-chain via onchainos."""

    def __init__(self, assembler_address=""):
        """Initialize with assembler contract address and local journal path."""
        self.assembler = assembler_address or config.CONTRACTS.get("assembler", "")
        self.journal_path = config.JOURNAL_LOCAL_PATH
        self._ensure_journal_dir()
        logger.info("DecisionJournal initialized (assembler=%s)", self.assembler)

    # -- public API --------------------------------------------------------

    def log_decision(self, strategy_id, decision_type, reasoning, params=None):
        """Log a decision both locally and on-chain.

        Args:
            strategy_id: Numeric strategy identifier.
            decision_type: Key from config.DECISION_TYPES (e.g. "FEE_ADJUST").
            reasoning: Human-readable reasoning string.
            params: Optional dict of extra parameters.

        Returns:
            The journal entry dict.
        """
        decision_type_hex = config.DECISION_TYPES.get(decision_type, "0x00")
        reasoning_hash = self.compute_reasoning_hash(reasoning)
        params_bytes = self._encode_params(params)

        entry = {
            "id": self._next_id(),
            "timestamp": int(time.time()),
            "strategy_id": strategy_id,
            "decision_type": decision_type,
            "reasoning": reasoning,
            "reasoning_hash": reasoning_hash,
            "params": params or {},
            "on_chain_status": "pending",
        }

        # On-chain logging
        if config.JOURNAL_ON_CHAIN and self.assembler:
            if config.DRY_RUN:
                entry["on_chain_status"] = "dry_run"
                logger.info("DRY_RUN: would log decision #%d on-chain", entry["id"])
            else:
                try:
                    self._log_onchain(
                        strategy_id, decision_type_hex, reasoning_hash, params_bytes
                    )
                    entry["on_chain_status"] = "confirmed"
                except Exception as exc:
                    logger.error("On-chain log failed: %s", exc)
                    entry["on_chain_status"] = "failed"
        else:
            entry["on_chain_status"] = "skipped"

        self._log_local(entry)
        logger.info("Decision #%d logged (%s)", entry["id"], entry["on_chain_status"])
        return entry

    def get_decision_count(self):
        """Return the number of decisions in the local journal."""
        return len(self._read_journal())

    def get_recent_decisions(self, n=10):
        """Return the last *n* decisions from the local journal."""
        return self._read_journal()[-n:]

    def get_decisions_by_type(self, decision_type):
        """Filter journal entries by decision_type string."""
        return [e for e in self._read_journal() if e.get("decision_type") == decision_type]

    def get_decisions_by_strategy(self, strategy_id):
        """Filter journal entries by strategy_id."""
        return [e for e in self._read_journal() if e.get("strategy_id") == strategy_id]

    def compute_reasoning_hash(self, reasoning_text):
        """Compute a sha256 hex digest as a simplified keccak256 stand-in."""
        return "0x" + hashlib.sha256(reasoning_text.encode("utf-8")).hexdigest()

    def export_journal(self):
        """Return the full journal as a list of dicts."""
        return self._read_journal()

    # -- private helpers ---------------------------------------------------

    def _log_local(self, entry):
        """Append a JSON entry as one line to the local JSONL journal."""
        filepath = os.path.join(self.journal_path, "journal.jsonl")
        try:
            with open(filepath, "a") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError as exc:
            logger.error("Failed to write local journal: %s", exc)

    def _log_onchain(self, strategy_id, decision_type_hex, reasoning_hash, params_bytes):
        """Call the assembler's logDecision via onchainos CLI."""
        cmd = [
            "onchainos", "wallet", "call",
            "--to", self.assembler,
            "--function",
            'logDecision(uint256,bytes32,bytes32,bytes)',
            "--args",
            str(strategy_id),
            decision_type_hex,
            reasoning_hash,
            params_bytes,
            "--index", "1",
        ]
        logger.debug("On-chain call: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"onchainos call failed (rc={result.returncode}): {result.stderr.strip()}")
        logger.debug("On-chain tx output: %s", result.stdout.strip())

    def _read_journal(self):
        """Read all entries from the local JSONL journal file."""
        filepath = os.path.join(self.journal_path, "journal.jsonl")
        entries = []
        if not os.path.isfile(filepath):
            return entries
        try:
            with open(filepath, "r") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to read journal: %s", exc)
        return entries

    def _next_id(self):
        """Return the next sequential decision id."""
        return self.get_decision_count() + 1

    def _encode_params(self, params):
        """Encode params dict to a hex-string for on-chain submission."""
        if not params:
            return "0x"
        raw = json.dumps(params, separators=(",", ":"), sort_keys=True)
        return "0x" + raw.encode("utf-8").hex()

    def _ensure_journal_dir(self):
        """Create the local journal directory if it doesn't exist."""
        os.makedirs(self.journal_path, exist_ok=True)
