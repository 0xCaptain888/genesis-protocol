// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @title GenesisRevertLib - Structured revert reasons for agent-readable error recovery
/// @notice Provides EIP-style custom errors with structured fields that autonomous agents
///         can decode to determine recovery actions. Three error categories:
///         1. CognitiveGate   — decision-layer rejections (confidence too low, stale model)
///         2. EconomicConstraint — profitability or gas budget failures
///         3. StateDependency — on-chain state not in expected configuration
///
///  Each error encodes: the failing component, required vs actual values, and a
///  suggested RecoveryAction so the agent can react without human intervention.
library GenesisRevertLib {

    // ─── Recovery Actions ─────────────────────────────────────────────────

    /// @notice Suggested recovery actions an agent can take after a revert
    enum RecoveryAction {
        WAIT,                 // 0: Wait for conditions to change
        RETRY,                // 1: Retry the same operation
        ADJUST_PARAMS,        // 2: Modify parameters and retry
        SPLIT_ROUTE,          // 3: Split into multiple smaller operations
        INCREASE_CONFIDENCE,  // 4: Gather more data before retrying
        REDUCE_POSITION,      // 5: Lower the size of the operation
        CHECK_ORACLE          // 6: Verify oracle data freshness/accuracy
    }

    // ─── Custom Errors ────────────────────────────────────────────────────

    /// @notice Thrown when a cognitive confidence gate rejects an operation
    /// @param layer The cognitive layer that rejected (0=perception, 1=analysis, 2=decision)
    /// @param required Minimum confidence threshold (scaled 1e18)
    /// @param actual Actual confidence score (scaled 1e18)
    /// @param suggestedAction RecoveryAction enum value cast to uint8
    error CognitiveGate(uint8 layer, uint256 required, uint256 actual, uint8 suggestedAction);

    /// @notice Thrown when an operation fails economic viability checks
    /// @param gasPrice Current gas price in wei
    /// @param minProfitThreshold Minimum profit required (in token units)
    /// @param estimatedProfit Estimated profit of the operation (in token units)
    /// @param retryDelaySeconds Suggested seconds to wait before retrying
    error EconomicConstraint(
        uint256 gasPrice,
        uint256 minProfitThreshold,
        uint256 estimatedProfit,
        uint32 retryDelaySeconds
    );

    /// @notice Thrown when on-chain state does not match expected values
    /// @param blockingSlot The storage slot or identifier that is blocking
    /// @param expectedValue What the caller expected
    /// @param actualValue What was actually found
    /// @param oracleToCheck Address of the oracle to re-query
    error StateDependency(
        bytes32 blockingSlot,
        uint256 expectedValue,
        uint256 actualValue,
        address oracleToCheck
    );

    /// @notice Thrown when a module rejects an operation due to fee mismatch
    /// @param moduleId Identifier of the rejecting module
    /// @param currentFee The fee the module computed
    /// @param maxAcceptableFee The maximum fee the caller is willing to pay
    /// @param suggestedAction RecoveryAction enum value cast to uint8
    error ModuleRejection(
        bytes32 moduleId,
        uint24 currentFee,
        uint24 maxAcceptableFee,
        uint8 suggestedAction
    );

    /// @notice Thrown when confidence data is too old to be trustworthy
    /// @param lastUpdate Timestamp of the last confidence update
    /// @param maxAge Maximum allowed age in seconds
    /// @param currentTime Current block.timestamp
    error ConfidenceStale(uint256 lastUpdate, uint256 maxAge, uint256 currentTime);

    // ─── Known Error Selectors ────────────────────────────────────────────

    bytes4 internal constant COGNITIVE_GATE_SELECTOR = 0x8b3dba2e;
    bytes4 internal constant ECONOMIC_CONSTRAINT_SELECTOR = 0x6f1c91a5;
    bytes4 internal constant STATE_DEPENDENCY_SELECTOR = 0x3a72e3d0;
    bytes4 internal constant MODULE_REJECTION_SELECTOR = 0xa1cc5b16;
    bytes4 internal constant CONFIDENCE_STALE_SELECTOR = 0xd4e2fc72;

    // ─── Revert Helpers ───────────────────────────────────────────────────

    /// @notice Reverts with a CognitiveGate error
    /// @param layer The cognitive layer that rejected
    /// @param required Minimum confidence threshold
    /// @param actual Actual confidence score
    /// @param action Suggested recovery action
    function revertCognitiveGate(
        uint8 layer,
        uint256 required,
        uint256 actual,
        RecoveryAction action
    ) internal pure {
        revert CognitiveGate(layer, required, actual, uint8(action));
    }

    /// @notice Reverts with an EconomicConstraint error
    /// @param gasPrice Current gas price
    /// @param minProfit Minimum profit threshold
    /// @param estimatedProfit Estimated profit
    /// @param retryDelay Suggested retry delay in seconds
    function revertEconomicConstraint(
        uint256 gasPrice,
        uint256 minProfit,
        uint256 estimatedProfit,
        uint32 retryDelay
    ) internal pure {
        revert EconomicConstraint(gasPrice, minProfit, estimatedProfit, retryDelay);
    }

    /// @notice Reverts with a StateDependency error
    /// @param slot The blocking storage slot or identifier
    /// @param expected Expected value
    /// @param actual Actual value found
    /// @param oracle Oracle address to re-query
    function revertStateDependency(
        bytes32 slot,
        uint256 expected,
        uint256 actual,
        address oracle
    ) internal pure {
        revert StateDependency(slot, expected, actual, oracle);
    }

    /// @notice Reverts with a ModuleRejection error
    /// @param modId The rejecting module's identifier
    /// @param currentFee Fee computed by the module
    /// @param maxFee Maximum acceptable fee
    /// @param action Suggested recovery action
    function revertModuleRejection(
        bytes32 modId,
        uint24 currentFee,
        uint24 maxFee,
        RecoveryAction action
    ) internal pure {
        revert ModuleRejection(modId, currentFee, maxFee, uint8(action));
    }

    /// @notice Reverts with a ConfidenceStale error
    /// @param lastUpdate When confidence was last updated
    /// @param maxAge Maximum allowed staleness
    function revertConfidenceStale(
        uint256 lastUpdate,
        uint256 maxAge
    ) internal view {
        revert ConfidenceStale(lastUpdate, maxAge, block.timestamp);
    }

    // ─── View Utilities ───────────────────────────────────────────────────

    /// @notice Encodes a recovery hint with action and arbitrary parameters
    /// @param action The suggested RecoveryAction
    /// @param params Additional context for the recovery (action-specific encoding)
    /// @return hint ABI-encoded recovery hint
    function encodeRecoveryHint(
        uint8 action,
        bytes memory params
    ) internal pure returns (bytes memory hint) {
        hint = abi.encode(action, params);
    }

    /// @notice Checks whether a given error selector corresponds to a recoverable error
    /// @dev All GenesisRevertLib errors are considered recoverable by design
    /// @param errorSelector The first 4 bytes of the revert data
    /// @return recoverable True if the error is a known Genesis recoverable error
    function isRecoverable(bytes4 errorSelector) internal pure returns (bool recoverable) {
        recoverable = (
            errorSelector == CognitiveGate.selector ||
            errorSelector == EconomicConstraint.selector ||
            errorSelector == StateDependency.selector ||
            errorSelector == ModuleRejection.selector ||
            errorSelector == ConfidenceStale.selector
        );
    }
}
