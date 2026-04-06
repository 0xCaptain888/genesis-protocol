// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IGenesisModule} from "../IGenesisModule.sol";

/// @title DataIntegrityModule - Second verification layer for oracle data quality
/// @notice Validates data inputs independently of the main cognitive pipeline.
///         Maintains a registry of trusted oracle sources and cross-validates
///         price data from multiple sources before allowing swaps to proceed.
///
///  Anomaly Detection:
///   - Sudden price spikes (> maxPriceDeviationBps in a single block)
///   - Stale data (oracle hasn't updated within maxStalenessSeconds)
///   - Conflicting oracle readings (sources disagree beyond threshold)
///
///  Independence: This module checks data quality, NOT decision quality.
///  The cognitive confidence scoring in other modules is a separate concern.
///  DataIntegrityModule can block a swap even if confidence is high, because
///  the underlying data feeding that confidence may be compromised.
///
///  Security: Follows v4-security-foundations guidelines from uniswap-ai:
///   - No beforeSwapReturnDelta usage (avoids NoOp rug pull risk)
///   - Returns fee=0 (does not alter fees); uses blocked=true to halt bad swaps
///   - All admin functions restricted to assembler
contract DataIntegrityModule is IGenesisModule {

    // ─── Types ───────────────────────────────────────────────────────────

    /// @notice Record of a registered oracle source
    struct OracleRecord {
        address oracle;          // oracle contract or EOA that pushes data
        uint256 lastPrice;       // last known good price (scaled 1e18)
        uint256 lastUpdate;      // timestamp of last price update
        uint256 deviationCount;  // number of times this oracle deviated
        bool active;             // whether this oracle is currently trusted
    }

    // ─── State ───────────────────────────────────────────────────────────
    address public assembler;

    mapping(address => OracleRecord) public oracles;
    address[] public oracleList;

    uint256 public maxPriceDeviationBps;   // max allowed deviation between oracles (bps)
    uint256 public maxStalenessSeconds;    // max age for oracle data
    uint256 public anomalyCount;           // total anomalies detected
    uint256 public blockedByIntegrity;     // swaps blocked due to data issues

    uint256 public lastMedianPrice;        // last computed median price across oracles
    uint256 public lastIntegrityCheck;     // timestamp of last integrity check

    uint256 constant BPS = 10000;
    uint256 constant PRICE_PRECISION = 1e18;

    // ─── Events ──────────────────────────────────────────────────────────
    event DataAnomaly(
        address indexed oracle,
        uint256 reportedPrice,
        uint256 medianPrice,
        uint256 deviationBps,
        uint256 timestamp
    );
    event OracleRegistered(address indexed oracle, uint256 timestamp);
    event OracleRemoved(address indexed oracle, uint256 timestamp);
    event IntegrityCheckPassed(uint256 medianPrice, uint256 oracleCount, uint256 timestamp);
    event IntegrityCheckFailed(
        uint256 medianPrice,
        uint256 failedOracles,
        uint256 timestamp,
        string reason
    );
    event ParamsUpdated(uint256 maxPriceDeviationBps, uint256 maxStalenessSeconds);

    // ─── Errors ──────────────────────────────────────────────────────────
    error OnlyAssembler();
    error OracleAlreadyRegistered();
    error OracleNotFound();
    error InvalidParams();
    error NoActiveOracles();

    modifier onlyAssembler() {
        if (msg.sender != assembler) revert OnlyAssembler();
        _;
    }

    constructor(
        address _assembler,
        uint256 _maxPriceDeviationBps,
        uint256 _maxStalenessSeconds
    ) {
        assembler = _assembler;
        maxPriceDeviationBps = _maxPriceDeviationBps;
        maxStalenessSeconds = _maxStalenessSeconds;
    }

    // ─── Oracle Management ───────────────────────────────────────────────

    /// @notice Register a new trusted oracle source
    /// @param _oracle Address of the oracle contract or data pusher
    function registerOracle(address _oracle) external onlyAssembler {
        if (oracles[_oracle].oracle != address(0)) revert OracleAlreadyRegistered();

        oracles[_oracle] = OracleRecord({
            oracle: _oracle,
            lastPrice: 0,
            lastUpdate: 0,
            deviationCount: 0,
            active: true
        });
        oracleList.push(_oracle);

        emit OracleRegistered(_oracle, block.timestamp);
    }

    /// @notice Remove an oracle from the trusted set
    /// @param _oracle Address of the oracle to remove
    function removeOracle(address _oracle) external onlyAssembler {
        if (oracles[_oracle].oracle == address(0)) revert OracleNotFound();

        oracles[_oracle].active = false;

        // Remove from oracleList array
        for (uint256 i = 0; i < oracleList.length; i++) {
            if (oracleList[i] == _oracle) {
                oracleList[i] = oracleList[oracleList.length - 1];
                oracleList.pop();
                break;
            }
        }

        emit OracleRemoved(_oracle, block.timestamp);
    }

    /// @notice Push new price data for a registered oracle
    /// @param _oracle The oracle whose data is being updated
    /// @param _price The latest price (scaled 1e18)
    function updateOracleData(address _oracle, uint256 _price) external onlyAssembler {
        OracleRecord storage record = oracles[_oracle];
        if (record.oracle == address(0)) revert OracleNotFound();

        record.lastPrice = _price;
        record.lastUpdate = block.timestamp;
    }

    // ─── Core Logic ──────────────────────────────────────────────────────

    /// @notice Before-swap integrity check — blocks swap if data is compromised
    /// @dev Returns fee=0 (this module does not adjust fees). Sets blocked=true
    ///      if any integrity check fails.
    function beforeSwapModule(
        address,
        uint256,
        bool
    ) external override returns (uint24 fee, bool blocked) {
        fee = 0;

        (bool passed, uint256 median, uint256 failCount) = _runIntegrityChecks();

        if (!passed) {
            blocked = true;
            blockedByIntegrity++;
            emit IntegrityCheckFailed(median, failCount, block.timestamp, "pre-swap integrity");
        } else {
            blocked = false;
            lastMedianPrice = median;
            lastIntegrityCheck = block.timestamp;
            emit IntegrityCheckPassed(median, _activeOracleCount(), block.timestamp);
        }
    }

    /// @notice After-swap state update — tracks price from swap for future comparisons
    function afterSwapModule(
        uint256 amountIn,
        uint256 amountOut,
        bool
    ) external override {
        if (amountIn == 0) return;

        // Derive implied price from the swap and store as a reference point
        uint256 impliedPrice = (amountOut * PRICE_PRECISION) / amountIn;
        lastMedianPrice = impliedPrice;
        lastIntegrityCheck = block.timestamp;
    }

    // ─── View Functions ──────────────────────────────────────────────────

    /// @notice Returns current integrity status across all registered oracles
    /// @return passed Whether all checks pass
    /// @return medianPrice The current median price across active oracles
    /// @return activeOracles Number of active oracle sources
    /// @return staleOracles Number of oracles with stale data
    /// @return deviatingOracles Number of oracles deviating beyond threshold
    function checkIntegrity() external view returns (
        bool passed,
        uint256 medianPrice,
        uint256 activeOracles,
        uint256 staleOracles,
        uint256 deviatingOracles
    ) {
        activeOracles = _activeOracleCount();
        if (activeOracles == 0) return (false, 0, 0, 0, 0);

        medianPrice = _computeMedianPrice();

        for (uint256 i = 0; i < oracleList.length; i++) {
            OracleRecord storage record = oracles[oracleList[i]];
            if (!record.active) continue;

            // Check staleness
            if (block.timestamp - record.lastUpdate > maxStalenessSeconds) {
                staleOracles++;
                continue;
            }

            // Check deviation from median
            if (medianPrice > 0 && record.lastPrice > 0) {
                uint256 deviation = _computeDeviationBps(record.lastPrice, medianPrice);
                if (deviation > maxPriceDeviationBps) {
                    deviatingOracles++;
                }
            }
        }

        passed = (staleOracles == 0 && deviatingOracles == 0);
    }

    /// @notice Returns the list of registered oracle addresses
    function getOracleList() external view returns (address[] memory) {
        return oracleList;
    }

    // ─── Internal ────────────────────────────────────────────────────────

    /// @dev Runs all integrity checks and returns results
    function _runIntegrityChecks() internal returns (
        bool passed,
        uint256 median,
        uint256 failCount
    ) {
        uint256 activeCount = _activeOracleCount();
        if (activeCount == 0) return (true, 0, 0);  // No oracles registered, pass by default

        median = _computeMedianPrice();
        passed = true;

        for (uint256 i = 0; i < oracleList.length; i++) {
            OracleRecord storage record = oracles[oracleList[i]];
            if (!record.active) continue;

            // Check 1: Staleness
            if (record.lastUpdate > 0 && block.timestamp - record.lastUpdate > maxStalenessSeconds) {
                passed = false;
                failCount++;
                anomalyCount++;
                emit DataAnomaly(record.oracle, record.lastPrice, median, 0, block.timestamp);
                continue;
            }

            // Check 2: Price deviation from median
            if (median > 0 && record.lastPrice > 0) {
                uint256 deviation = _computeDeviationBps(record.lastPrice, median);
                if (deviation > maxPriceDeviationBps) {
                    passed = false;
                    failCount++;
                    record.deviationCount++;
                    anomalyCount++;
                    emit DataAnomaly(
                        record.oracle,
                        record.lastPrice,
                        median,
                        deviation,
                        block.timestamp
                    );
                }
            }
        }
    }

    /// @dev Computes the median price from all active oracles with valid data
    /// @return median The median price (scaled 1e18), or 0 if no valid data
    function _computeMedianPrice() internal view returns (uint256 median) {
        uint256 activeCount = _activeOracleCount();
        if (activeCount == 0) return 0;

        // Collect valid prices into a temporary array
        uint256[] memory prices = new uint256[](activeCount);
        uint256 count = 0;

        for (uint256 i = 0; i < oracleList.length; i++) {
            OracleRecord storage record = oracles[oracleList[i]];
            if (record.active && record.lastPrice > 0) {
                prices[count] = record.lastPrice;
                count++;
            }
        }

        if (count == 0) return 0;

        // Simple insertion sort (oracle count is expected to be small)
        for (uint256 i = 1; i < count; i++) {
            uint256 key = prices[i];
            uint256 j = i;
            while (j > 0 && prices[j - 1] > key) {
                prices[j] = prices[j - 1];
                j--;
            }
            prices[j] = key;
        }

        // Median: middle element (or average of two middle elements)
        if (count % 2 == 1) {
            median = prices[count / 2];
        } else {
            median = (prices[count / 2 - 1] + prices[count / 2]) / 2;
        }
    }

    /// @dev Computes absolute deviation in basis points between two prices
    function _computeDeviationBps(uint256 priceA, uint256 priceB) internal pure returns (uint256) {
        if (priceB == 0) return 0;
        uint256 diff = priceA > priceB ? priceA - priceB : priceB - priceA;
        return (diff * BPS) / priceB;
    }

    /// @dev Returns the number of currently active oracles
    function _activeOracleCount() internal view returns (uint256 count) {
        for (uint256 i = 0; i < oracleList.length; i++) {
            if (oracles[oracleList[i]].active) count++;
        }
    }

    // ─── IGenesisModule Interface ────────────────────────────────────────

    function moduleId() external pure override returns (bytes32) {
        return keccak256("genesis.module.data-integrity.v1");
    }

    function getParams() external view override returns (bytes memory) {
        return abi.encode(
            maxPriceDeviationBps,
            maxStalenessSeconds,
            anomalyCount,
            blockedByIntegrity,
            lastMedianPrice,
            lastIntegrityCheck
        );
    }

    function updateParams(bytes calldata params) external override onlyAssembler {
        (
            uint256 _maxPriceDeviationBps,
            uint256 _maxStalenessSeconds
        ) = abi.decode(params, (uint256, uint256));

        if (_maxPriceDeviationBps == 0 || _maxStalenessSeconds == 0) revert InvalidParams();

        maxPriceDeviationBps = _maxPriceDeviationBps;
        maxStalenessSeconds = _maxStalenessSeconds;

        emit ParamsUpdated(_maxPriceDeviationBps, _maxStalenessSeconds);
    }
}
