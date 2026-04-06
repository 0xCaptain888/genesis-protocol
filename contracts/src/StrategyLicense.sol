// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @title StrategyLicense - Leasing and licensing for Strategy NFTs
/// @notice Allows Strategy NFT owners to list their proven strategies for lease.
///         Lessees pay a fee to use the strategy parameters for a configurable
///         time period or number of swaps. The NFT owner retains full ownership;
///         lessees receive read access to strategy configuration data.
///
///  License Types:
///   - TIME_BASED:  Lease expires after N seconds from activation
///   - USAGE_BASED: Lease expires after N swaps are executed
///   - PERPETUAL:   Lease never expires (one-time payment)
///
///  Revenue Model:
///   - Lessee pays pricePerPeriod in native token (msg.value)
///   - Protocol takes protocolFeeBps cut (default 5%)
///   - Remainder accrues to NFT owner, claimable via reclaimRevenue()
///
///  Integration: Sits alongside StrategyNFT. Queries StrategyNFT.ownerOf()
///  to verify listing authority and StrategyNFT.getStrategyMeta() to serve
///  strategy parameters to valid lessees.
contract StrategyLicense {

    // ─── Types ───────────────────────────────────────────────────────────

    enum LicenseType {
        TIME_BASED,    // 0: expires after periodSeconds
        USAGE_BASED,   // 1: expires after maxSwaps
        PERPETUAL      // 2: never expires
    }

    /// @notice Terms set by the NFT owner for licensing a strategy
    struct License {
        uint256 pricePerPeriod;  // cost in wei per lease
        uint256 periodSeconds;   // duration for TIME_BASED; ignored for others
        LicenseType licenseType;
        bool active;             // whether the license listing is active
        uint256 totalLeases;     // number of leases created
        uint256 totalRevenue;    // total revenue accrued (before protocol fee)
    }

    /// @notice Record of an active lease for a specific lessee
    struct LeaseRecord {
        uint256 startTime;   // block.timestamp when lease was activated
        uint256 endTime;     // expiry timestamp (0 for PERPETUAL)
        uint256 swapsUsed;   // swap count consumed (for USAGE_BASED)
        uint256 maxSwaps;    // max swaps allowed (for USAGE_BASED)
        bool active;         // whether lease is currently active
    }

    // ─── State ───────────────────────────────────────────────────────────
    address public owner;              // protocol admin
    address public strategyNFT;        // reference to StrategyNFT contract
    address public treasury;           // protocol fee recipient

    uint256 public protocolFeeBps;     // protocol cut (default 500 = 5%)

    /// @notice tokenId => license terms set by NFT owner
    mapping(uint256 => License) public licenses;

    /// @notice tokenId => lessee address => lease record
    mapping(uint256 => mapping(address => LeaseRecord)) public leases;

    /// @notice tokenId => accumulated owner revenue (claimable)
    mapping(uint256 => uint256) public ownerRevenue;

    uint256 public totalLeasesCreated;
    uint256 public totalProtocolRevenue;

    uint256 constant BPS = 10000;

    // ─── Events ──────────────────────────────────────────────────────────
    event LicenseListed(
        uint256 indexed tokenId,
        uint256 pricePerPeriod,
        uint256 periodSeconds,
        LicenseType licenseType
    );
    event LicenseUpdated(
        uint256 indexed tokenId,
        uint256 pricePerPeriod,
        uint256 periodSeconds,
        LicenseType licenseType
    );
    event LeaseCreated(
        uint256 indexed tokenId,
        address indexed lessee,
        uint256 startTime,
        uint256 endTime,
        uint256 maxSwaps,
        uint256 pricePaid
    );
    event LeaseExpired(
        uint256 indexed tokenId,
        address indexed lessee,
        uint256 timestamp
    );
    event RevenueDistributed(
        uint256 indexed tokenId,
        address indexed nftOwner,
        uint256 ownerAmount,
        uint256 protocolAmount
    );
    event LicenseCancelled(uint256 indexed tokenId, uint256 timestamp);
    event ProtocolFeeUpdated(uint256 oldFeeBps, uint256 newFeeBps);

    // ─── Errors ──────────────────────────────────────────────────────────
    error OnlyOwner();
    error OnlyNFTOwner();
    error LicenseNotActive();
    error LicenseAlreadyActive();
    error LeaseAlreadyActive();
    error LeaseNotActive();
    error InsufficientPayment();
    error InvalidParams();
    error NoRevenueToClaim();
    error TransferFailed();

    modifier onlyOwner() {
        if (msg.sender != owner) revert OnlyOwner();
        _;
    }

    constructor(
        address _strategyNFT,
        address _treasury,
        uint256 _protocolFeeBps
    ) {
        owner = msg.sender;
        strategyNFT = _strategyNFT;
        treasury = _treasury;
        protocolFeeBps = _protocolFeeBps;
    }

    // ─── License Management ──────────────────────────────────────────────

    /// @notice List a Strategy NFT for licensing
    /// @dev Only the current NFT owner can list. For USAGE_BASED, periodSeconds
    ///      is interpreted as maxSwaps per lease.
    /// @param _tokenId The Strategy NFT token ID
    /// @param _price Price per lease period in wei
    /// @param _period Duration in seconds (TIME_BASED) or max swaps (USAGE_BASED)
    /// @param _ltype The license type
    function listForLicense(
        uint256 _tokenId,
        uint256 _price,
        uint256 _period,
        LicenseType _ltype
    ) external {
        if (_getNFTOwner(_tokenId) != msg.sender) revert OnlyNFTOwner();
        if (licenses[_tokenId].active) revert LicenseAlreadyActive();
        if (_price == 0) revert InvalidParams();

        licenses[_tokenId] = License({
            pricePerPeriod: _price,
            periodSeconds: _period,
            licenseType: _ltype,
            active: true,
            totalLeases: 0,
            totalRevenue: 0
        });

        emit LicenseListed(_tokenId, _price, _period, _ltype);
    }

    /// @notice Lease a licensed strategy
    /// @dev Lessee sends msg.value >= pricePerPeriod. Revenue is split between
    ///      NFT owner and protocol treasury.
    /// @param _tokenId The Strategy NFT token ID to lease
    function lease(uint256 _tokenId) external payable {
        License storage lic = licenses[_tokenId];
        if (!lic.active) revert LicenseNotActive();
        if (leases[_tokenId][msg.sender].active) revert LeaseAlreadyActive();
        if (msg.value < lic.pricePerPeriod) revert InsufficientPayment();

        // Compute lease terms based on license type
        uint256 endTime;
        uint256 maxSwaps;

        if (lic.licenseType == LicenseType.TIME_BASED) {
            endTime = block.timestamp + lic.periodSeconds;
            maxSwaps = 0;
        } else if (lic.licenseType == LicenseType.USAGE_BASED) {
            endTime = 0;
            maxSwaps = lic.periodSeconds; // periodSeconds repurposed as maxSwaps
        } else {
            // PERPETUAL
            endTime = 0;
            maxSwaps = 0;
        }

        leases[_tokenId][msg.sender] = LeaseRecord({
            startTime: block.timestamp,
            endTime: endTime,
            swapsUsed: 0,
            maxSwaps: maxSwaps,
            active: true
        });

        // Revenue accounting
        uint256 protocolCut = (msg.value * protocolFeeBps) / BPS;
        uint256 ownerCut = msg.value - protocolCut;

        ownerRevenue[_tokenId] += ownerCut;
        totalProtocolRevenue += protocolCut;

        lic.totalLeases++;
        lic.totalRevenue += msg.value;
        totalLeasesCreated++;

        // Transfer protocol fee to treasury
        if (protocolCut > 0) {
            (bool sent, ) = treasury.call{value: protocolCut}("");
            if (!sent) revert TransferFailed();
        }

        emit LeaseCreated(_tokenId, msg.sender, block.timestamp, endTime, maxSwaps, msg.value);
        emit RevenueDistributed(_tokenId, _getNFTOwner(_tokenId), ownerCut, protocolCut);
    }

    // ─── Lease Queries ───────────────────────────────────────────────────

    /// @notice Check whether a lease is currently valid
    /// @param _tokenId The Strategy NFT token ID
    /// @param _lessee Address of the lessee
    /// @return valid True if the lease is active and not expired
    function checkLeaseValid(uint256 _tokenId, address _lessee) public view returns (bool valid) {
        LeaseRecord storage record = leases[_tokenId][_lessee];
        if (!record.active) return false;

        License storage lic = licenses[_tokenId];

        if (lic.licenseType == LicenseType.TIME_BASED) {
            return block.timestamp <= record.endTime;
        } else if (lic.licenseType == LicenseType.USAGE_BASED) {
            return record.swapsUsed < record.maxSwaps;
        } else {
            // PERPETUAL
            return true;
        }
    }

    /// @notice Returns strategy parameters if the caller has a valid lease
    /// @dev Queries StrategyNFT.getStrategyMeta() and returns the module params
    /// @param _tokenId The Strategy NFT token ID
    /// @param _lessee Address of the lessee to validate
    /// @return modules Array of module addresses
    /// @return moduleParams Array of encoded module parameters
    function getStrategyParams(
        uint256 _tokenId,
        address _lessee
    ) external view returns (address[] memory modules, bytes[] memory moduleParams) {
        if (!checkLeaseValid(_tokenId, _lessee)) revert LeaseNotActive();

        // Call StrategyNFT.getStrategyMeta() to fetch params
        // Uses low-level staticcall to avoid interface import dependency
        (bool success, bytes memory data) = strategyNFT.staticcall(
            abi.encodeWithSignature("getStrategyMeta(uint256)", _tokenId)
        );
        require(success, "StrategyNFT call failed");

        // Decode the StrategyMeta struct — we only need modules and moduleParams
        (
            , // assembler
            , // strategyId
            , // configHash
            address[] memory _modules,
            bytes[] memory _moduleParams,
            , // totalSwaps
            , // totalVolume
            , // pnlBps
            , // decisionCount
            , // mintedAt
            , // runDurationSeconds
            , // marketVolatility
              // marketPrice
        ) = abi.decode(
            data,
            (address, uint256, bytes32, address[], bytes[], uint256, uint256, int256, uint256, uint256, uint256, uint256, uint256)
        );

        modules = _modules;
        moduleParams = _moduleParams;
    }

    /// @notice Record a swap usage for a USAGE_BASED lease
    /// @dev Called by the assembler or hook to decrement remaining swaps
    /// @param _tokenId The Strategy NFT token ID
    /// @param _lessee The lessee whose swap count to increment
    function recordSwapUsage(uint256 _tokenId, address _lessee) external {
        LeaseRecord storage record = leases[_tokenId][_lessee];
        if (!record.active) revert LeaseNotActive();

        record.swapsUsed++;

        // Auto-expire if usage limit reached
        if (licenses[_tokenId].licenseType == LicenseType.USAGE_BASED) {
            if (record.swapsUsed >= record.maxSwaps) {
                record.active = false;
                emit LeaseExpired(_tokenId, _lessee, block.timestamp);
            }
        }
    }

    // ─── Revenue Management ──────────────────────────────────────────────

    /// @notice NFT owner claims accumulated revenue from leases
    /// @param _tokenId The Strategy NFT token ID
    function reclaimRevenue(uint256 _tokenId) external {
        if (_getNFTOwner(_tokenId) != msg.sender) revert OnlyNFTOwner();

        uint256 amount = ownerRevenue[_tokenId];
        if (amount == 0) revert NoRevenueToClaim();

        ownerRevenue[_tokenId] = 0;

        (bool sent, ) = msg.sender.call{value: amount}("");
        if (!sent) revert TransferFailed();
    }

    // ─── License Admin ───────────────────────────────────────────────────

    /// @notice NFT owner cancels an active license listing
    /// @dev Existing active leases remain valid until they expire
    /// @param _tokenId The Strategy NFT token ID
    function cancelLicense(uint256 _tokenId) external {
        if (_getNFTOwner(_tokenId) != msg.sender) revert OnlyNFTOwner();
        if (!licenses[_tokenId].active) revert LicenseNotActive();

        licenses[_tokenId].active = false;

        emit LicenseCancelled(_tokenId, block.timestamp);
    }

    /// @notice Protocol owner updates the protocol fee percentage
    /// @param _newFeeBps New fee in basis points (max 2000 = 20%)
    function updateProtocolFee(uint256 _newFeeBps) external onlyOwner {
        if (_newFeeBps > 2000) revert InvalidParams(); // cap at 20%

        uint256 oldFee = protocolFeeBps;
        protocolFeeBps = _newFeeBps;

        emit ProtocolFeeUpdated(oldFee, _newFeeBps);
    }

    // ─── Internal ────────────────────────────────────────────────────────

    /// @dev Queries StrategyNFT.ownerOf(tokenId) via low-level staticcall
    function _getNFTOwner(uint256 _tokenId) internal view returns (address nftOwner) {
        (bool success, bytes memory data) = strategyNFT.staticcall(
            abi.encodeWithSignature("ownerOf(uint256)", _tokenId)
        );
        require(success, "StrategyNFT ownerOf failed");
        nftOwner = abi.decode(data, (address));
    }
}
