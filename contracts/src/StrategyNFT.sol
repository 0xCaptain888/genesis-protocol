// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @title StrategyNFT - On-chain representation of proven trading strategies
/// @notice When a Genesis strategy demonstrates profitability above a threshold,
///         the Agent mints a Strategy NFT encoding the full configuration.
///         Other agents can query the NFT to replicate or license the strategy.
///
///  NFT Metadata (stored on-chain, not IPFS — fully verifiable):
///   - Module composition (which modules + order)
///   - All module parameters at time of minting
///   - Performance stats (swaps, volume, P&L)
///   - Decision journal reference (count of decisions, last decision ID)
///   - Market conditions at minting (volatility, price)
///
///  This is a minimal ERC-721 implementation (no OpenZeppelin dependency
///  to keep deployment simple on X Layer).
contract StrategyNFT {

    // ─── ERC-721 Core ────────────────────────────────────────────────────
    string public name = "Genesis Strategy";
    string public symbol = "GSTRAT";

    uint256 public totalSupply;
    mapping(uint256 => address) public ownerOf;
    mapping(address => uint256) public balanceOf;
    mapping(uint256 => address) public getApproved;
    mapping(address => mapping(address => bool)) public isApprovedForAll;

    // ─── Strategy Metadata ───────────────────────────────────────────────
    struct StrategyMeta {
        address assembler;           // GenesisHookAssembler address
        uint256 strategyId;          // ID in the assembler
        bytes32 configHash;          // Hash of all module params
        address[] modules;           // Module addresses
        bytes[] moduleParams;        // Encoded params at mint time
        uint256 totalSwaps;
        uint256 totalVolume;
        int256  pnlBps;              // P&L at mint time
        uint256 decisionCount;       // Number of AI decisions made
        uint256 mintedAt;
        uint256 runDurationSeconds;  // How long strategy ran before mint
        uint256 marketVolatility;    // Vol at mint time (from Agent)
        uint256 marketPrice;         // Price at mint time (from Agent)
    }

    mapping(uint256 => StrategyMeta) public strategyMeta;

    // Access control
    address public minter;  // GenesisHookAssembler or Agent wallet

    // ─── Events ──────────────────────────────────────────────────────────
    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);
    event StrategyMinted(
        uint256 indexed tokenId,
        address indexed assembler,
        uint256 strategyId,
        int256 pnlBps,
        uint256 totalSwaps
    );

    error OnlyMinter();
    error NotOwnerOrApproved();
    error InvalidRecipient();
    error TokenDoesNotExist();

    constructor(address _minter) {
        minter = _minter;
    }

    // ─── Minting ─────────────────────────────────────────────────────────

    function mint(
        address _to,
        address _assembler,
        uint256 _strategyId,
        bytes32 _configHash,
        address[] calldata _modules,
        bytes[] calldata _moduleParams,
        uint256 _totalSwaps,
        uint256 _totalVolume,
        int256 _pnlBps,
        uint256 _decisionCount,
        uint256 _runDuration,
        uint256 _marketVol,
        uint256 _marketPrice
    ) external returns (uint256 tokenId) {
        if (msg.sender != minter) revert OnlyMinter();
        if (_to == address(0)) revert InvalidRecipient();

        tokenId = totalSupply++;

        ownerOf[tokenId] = _to;
        balanceOf[_to]++;

        strategyMeta[tokenId] = StrategyMeta({
            assembler: _assembler,
            strategyId: _strategyId,
            configHash: _configHash,
            modules: _modules,
            moduleParams: _moduleParams,
            totalSwaps: _totalSwaps,
            totalVolume: _totalVolume,
            pnlBps: _pnlBps,
            decisionCount: _decisionCount,
            mintedAt: block.timestamp,
            runDurationSeconds: _runDuration,
            marketVolatility: _marketVol,
            marketPrice: _marketPrice
        });

        emit Transfer(address(0), _to, tokenId);
        emit StrategyMinted(tokenId, _assembler, _strategyId, _pnlBps, _totalSwaps);
    }

    // ─── View ────────────────────────────────────────────────────────────

    function getStrategyMeta(uint256 _tokenId) external view returns (StrategyMeta memory) {
        if (ownerOf[_tokenId] == address(0)) revert TokenDoesNotExist();
        return strategyMeta[_tokenId];
    }

    // ─── Minimal ERC-721 ─────────────────────────────────────────────────

    function approve(address _to, uint256 _tokenId) external {
        address tokenOwner = ownerOf[_tokenId];
        if (msg.sender != tokenOwner && !isApprovedForAll[tokenOwner][msg.sender])
            revert NotOwnerOrApproved();
        getApproved[_tokenId] = _to;
        emit Approval(tokenOwner, _to, _tokenId);
    }

    function setApprovalForAll(address _operator, bool _approved) external {
        isApprovedForAll[msg.sender][_operator] = _approved;
        emit ApprovalForAll(msg.sender, _operator, _approved);
    }

    function transferFrom(address _from, address _to, uint256 _tokenId) external {
        if (_to == address(0)) revert InvalidRecipient();
        address tokenOwner = ownerOf[_tokenId];
        if (_from != tokenOwner) revert NotOwnerOrApproved();
        if (
            msg.sender != tokenOwner &&
            msg.sender != getApproved[_tokenId] &&
            !isApprovedForAll[tokenOwner][msg.sender]
        ) revert NotOwnerOrApproved();

        balanceOf[_from]--;
        balanceOf[_to]++;
        ownerOf[_tokenId] = _to;
        delete getApproved[_tokenId];

        emit Transfer(_from, _to, _tokenId);
    }
}
