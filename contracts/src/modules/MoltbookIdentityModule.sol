// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {IGenesisModule} from "../IGenesisModule.sol";

/// @title MoltbookIdentityModule - Moltbook identity verification for Strategy NFT trust scoring
/// @notice Integrates Moltbook agent identity verification into the Genesis hook pipeline.
///         Stores verified Moltbook agent identity hashes on-chain and optionally gates
///         swap access to verified agents. Verified agents receive a configurable fee
///         discount as a trust incentive.
///
///  Identity Flow:
///   1. Off-chain: Agent proves Moltbook identity through the Moltbook API
///   2. Assembler calls verifyAgent() with the identity hash and karma score
///   3. On-chain: beforeSwapModule checks verification status
///   4. Verified agents get identityTrustBonus bps discount on swap fees
///   5. Identity data enriches Strategy NFT metadata via getAgentIdentity()
///
///  Modes:
///   - requireIdentity = false (default): anyone can swap, verified get fee discount
///   - requireIdentity = true: only verified Moltbook agents can swap
///
///  Security: Follows v4-security-foundations guidelines from uniswap-ai:
///   - No beforeSwapReturnDelta usage (avoids NoOp rug pull risk)
///   - Identity hashes are one-way — no PII stored on-chain
///   - All admin functions restricted to assembler
contract MoltbookIdentityModule is IGenesisModule {

    // ─── Types ───────────────────────────────────────────────────────────

    /// @notice On-chain record of a verified Moltbook agent
    struct AgentIdentity {
        bytes32 moltbookIdHash;  // keccak256 of the Moltbook identity token
        uint256 karma;           // Moltbook karma score at verification time
        uint256 verifiedAt;      // timestamp of verification
        bool isVerified;         // current verification status
        string agentName;        // human-readable agent name
    }

    // ─── State ───────────────────────────────────────────────────────────
    address public assembler;

    mapping(address => AgentIdentity) public verifiedAgents;
    uint256 public totalVerified;          // count of currently verified agents
    bool public requireIdentity;           // whether swaps require identity (default false)
    uint256 public identityTrustBonus;     // fee discount in bps for verified agents

    uint256 public totalIdentityChecks;    // total beforeSwap identity checks performed
    uint256 public totalDiscountsApplied;  // times a trust discount was applied

    // ─── Events ──────────────────────────────────────────────────────────
    event AgentVerified(
        address indexed agent,
        bytes32 moltbookIdHash,
        uint256 karma,
        string agentName,
        uint256 timestamp
    );
    event AgentRevoked(address indexed agent, uint256 timestamp);
    event IdentityTrustApplied(
        address indexed agent,
        uint256 discountBps,
        uint256 timestamp
    );
    event ParamsUpdated(bool requireIdentity, uint256 identityTrustBonus);

    // ─── Errors ──────────────────────────────────────────────────────────
    error OnlyAssembler();
    error AgentAlreadyVerified();
    error AgentNotVerified();
    error IdentityRequired();
    error InvalidParams();

    modifier onlyAssembler() {
        if (msg.sender != assembler) revert OnlyAssembler();
        _;
    }

    constructor(
        address _assembler,
        bool _requireIdentity,
        uint256 _identityTrustBonus
    ) {
        assembler = _assembler;
        requireIdentity = _requireIdentity;
        identityTrustBonus = _identityTrustBonus;
    }

    // ─── Identity Management ─────────────────────────────────────────────

    /// @notice Verify a Moltbook agent identity on-chain
    /// @param _agent Wallet address of the agent
    /// @param _idHash keccak256 of the Moltbook identity token
    /// @param _karma Moltbook karma score at time of verification
    /// @param _name Human-readable agent name
    function verifyAgent(
        address _agent,
        bytes32 _idHash,
        uint256 _karma,
        string calldata _name
    ) external onlyAssembler {
        if (verifiedAgents[_agent].isVerified) revert AgentAlreadyVerified();

        verifiedAgents[_agent] = AgentIdentity({
            moltbookIdHash: _idHash,
            karma: _karma,
            verifiedAt: block.timestamp,
            isVerified: true,
            agentName: _name
        });

        totalVerified++;

        emit AgentVerified(_agent, _idHash, _karma, _name, block.timestamp);
    }

    /// @notice Revoke a previously verified agent's identity
    /// @param _agent Wallet address of the agent to revoke
    function revokeAgent(address _agent) external onlyAssembler {
        if (!verifiedAgents[_agent].isVerified) revert AgentNotVerified();

        verifiedAgents[_agent].isVerified = false;
        totalVerified--;

        emit AgentRevoked(_agent, block.timestamp);
    }

    // ─── Core Logic ──────────────────────────────────────────────────────

    /// @notice Before-swap identity check and fee discount application
    /// @dev If requireIdentity is true, blocks unverified senders.
    ///      If sender is verified, returns identityTrustBonus as a fee value
    ///      that the assembler can use to apply a discount (fee represents the
    ///      discount amount in bps, not an additional fee).
    function beforeSwapModule(
        address sender,
        uint256,
        bool
    ) external override returns (uint24 fee, bool blocked) {
        totalIdentityChecks++;

        bool verified = verifiedAgents[sender].isVerified;

        // Gate: block unverified agents if identity is required
        if (requireIdentity && !verified) {
            return (0, true);
        }

        // Reward: apply trust bonus fee discount for verified agents
        if (verified && identityTrustBonus > 0) {
            fee = uint24(identityTrustBonus);
            totalDiscountsApplied++;
            emit IdentityTrustApplied(sender, identityTrustBonus, block.timestamp);
        } else {
            fee = 0;
        }

        blocked = false;
    }

    /// @notice After-swap hook — no-op for identity module
    function afterSwapModule(uint256, uint256, bool) external override {
        // MoltbookIdentityModule has no after-swap logic
    }

    // ─── View Functions ──────────────────────────────────────────────────

    /// @notice Returns the full identity record for an agent
    /// @param _agent Wallet address to query
    /// @return identity The agent's identity record
    function getAgentIdentity(address _agent) external view returns (AgentIdentity memory identity) {
        identity = verifiedAgents[_agent];
    }

    /// @notice Checks whether an agent has a verified Moltbook identity
    /// @param _agent Wallet address to check
    /// @return True if the agent is currently verified
    function isAgentVerified(address _agent) external view returns (bool) {
        return verifiedAgents[_agent].isVerified;
    }

    // ─── IGenesisModule Interface ────────────────────────────────────────

    function moduleId() external pure override returns (bytes32) {
        return keccak256("genesis.module.moltbook-identity.v1");
    }

    function getParams() external view override returns (bytes memory) {
        return abi.encode(
            requireIdentity,
            identityTrustBonus,
            totalVerified,
            totalIdentityChecks,
            totalDiscountsApplied
        );
    }

    function updateParams(bytes calldata params) external override onlyAssembler {
        (
            bool _requireIdentity,
            uint256 _identityTrustBonus
        ) = abi.decode(params, (bool, uint256));

        if (_identityTrustBonus > 10000) revert InvalidParams(); // max 100% discount

        requireIdentity = _requireIdentity;
        identityTrustBonus = _identityTrustBonus;

        emit ParamsUpdated(_requireIdentity, _identityTrustBonus);
    }
}
