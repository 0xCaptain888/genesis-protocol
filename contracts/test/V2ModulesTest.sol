// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "forge-std/Test.sol";
import {IGenesisModule} from "../src/IGenesisModule.sol";
import {GenesisHookAssembler} from "../src/GenesisHookAssembler.sol";
import {GenesisRevertLib} from "../src/libraries/GenesisRevertLib.sol";
import {DataIntegrityModule} from "../src/modules/DataIntegrityModule.sol";
import {MoltbookIdentityModule} from "../src/modules/MoltbookIdentityModule.sol";
import {StrategyLicense} from "../src/StrategyLicense.sol";
import {StrategyNFT} from "../src/StrategyNFT.sol";

contract V2ModulesTest is Test {
    // --- Actors ---
    address owner = address(0xA1);
    address agent = address(0xA2);
    address alice = address(0xB1);
    address bob   = address(0xB2);
    address oracle1 = address(0xC1);
    address oracle2 = address(0xC2);
    address oracle3 = address(0xC3);
    address treasury = address(0xD1);

    // --- Contracts ---
    GenesisHookAssembler assembler;
    DataIntegrityModule  dataIntegrity;
    MoltbookIdentityModule moltbookIdentity;
    StrategyNFT          nft;
    StrategyLicense      license;

    function setUp() public {
        vm.startPrank(owner);

        assembler = new GenesisHookAssembler(owner);
        assembler.setAgent(agent);

        // Deploy V2 modules
        dataIntegrity = new DataIntegrityModule(
            address(assembler),
            500,    // maxPriceDeviationBps (5%)
            300     // maxStalenessSeconds (5 min)
        );

        moltbookIdentity = new MoltbookIdentityModule(
            address(assembler),
            false,  // requireIdentity
            50      // identityTrustBonus (0.50%)
        );

        nft = new StrategyNFT(owner);

        license = new StrategyLicense(
            address(nft),
            treasury,
            500     // protocolFeeBps (5%)
        );

        // Register V2 modules with assembler
        assembler.registerModule(address(dataIntegrity));
        assembler.registerModule(address(moltbookIdentity));

        vm.stopPrank();
    }

    // ================================================================
    // SECTION 1: GenesisRevertLib Tests
    // ================================================================

    function test_revertLib_cognitiveGate_reverts() public {
        RevertLibHarness harness = new RevertLibHarness();
        vm.expectRevert(
            abi.encodeWithSelector(
                GenesisRevertLib.CognitiveGate.selector,
                uint8(1), 0.8e18, 0.5e18, uint8(4) // INCREASE_CONFIDENCE = 4
            )
        );
        harness.triggerCognitiveGate();
    }

    function test_revertLib_economicConstraint_reverts() public {
        RevertLibHarness harness = new RevertLibHarness();
        vm.expectRevert(
            abi.encodeWithSelector(
                GenesisRevertLib.EconomicConstraint.selector,
                50 gwei, 1 ether, 0.5 ether, uint32(60)
            )
        );
        harness.triggerEconomicConstraint();
    }

    function test_revertLib_stateDependency_reverts() public {
        RevertLibHarness harness = new RevertLibHarness();
        vm.expectRevert(
            abi.encodeWithSelector(
                GenesisRevertLib.StateDependency.selector,
                bytes32(uint256(1)), 100, 200, address(0xC1)
            )
        );
        harness.triggerStateDependency();
    }

    function test_revertLib_moduleRejection_reverts() public {
        RevertLibHarness harness = new RevertLibHarness();
        vm.expectRevert(
            abi.encodeWithSelector(
                GenesisRevertLib.ModuleRejection.selector,
                keccak256("test.module"), uint24(5000), uint24(3000), uint8(2) // ADJUST_PARAMS = 2
            )
        );
        harness.triggerModuleRejection();
    }

    function test_revertLib_confidenceStale_reverts() public {
        RevertLibHarness harness = new RevertLibHarness();
        vm.expectRevert(
            abi.encodeWithSelector(
                GenesisRevertLib.ConfidenceStale.selector,
                uint256(100), uint256(3600), block.timestamp
            )
        );
        harness.triggerConfidenceStale();
    }

    function test_revertLib_isRecoverable_knownSelectors() public {
        RevertLibHarness harness = new RevertLibHarness();
        assertTrue(harness.callIsRecoverable(GenesisRevertLib.CognitiveGate.selector));
        assertTrue(harness.callIsRecoverable(GenesisRevertLib.EconomicConstraint.selector));
        assertTrue(harness.callIsRecoverable(GenesisRevertLib.StateDependency.selector));
        assertTrue(harness.callIsRecoverable(GenesisRevertLib.ModuleRejection.selector));
        assertTrue(harness.callIsRecoverable(GenesisRevertLib.ConfidenceStale.selector));
    }

    function test_revertLib_isRecoverable_unknownSelector() public {
        RevertLibHarness harness = new RevertLibHarness();
        assertFalse(harness.callIsRecoverable(bytes4(0xdeadbeef)));
    }

    function test_revertLib_encodeRecoveryHint() public {
        RevertLibHarness harness = new RevertLibHarness();
        bytes memory params = abi.encode(uint256(42));
        bytes memory hint = harness.callEncodeRecoveryHint(1, params); // RETRY = 1
        (uint8 action, bytes memory decoded) = abi.decode(hint, (uint8, bytes));
        assertEq(action, 1);
        assertEq(abi.decode(decoded, (uint256)), 42);
    }

    // ================================================================
    // SECTION 2: DataIntegrityModule Tests
    // ================================================================

    function test_dataIntegrity_registerOracle() public {
        vm.prank(address(assembler));
        dataIntegrity.registerOracle(oracle1);

        address[] memory list = dataIntegrity.getOracleList();
        assertEq(list.length, 1);
        assertEq(list[0], oracle1);
    }

    function test_dataIntegrity_registerOracle_revertsDuplicate() public {
        vm.startPrank(address(assembler));
        dataIntegrity.registerOracle(oracle1);

        vm.expectRevert(DataIntegrityModule.OracleAlreadyRegistered.selector);
        dataIntegrity.registerOracle(oracle1);
        vm.stopPrank();
    }

    function test_dataIntegrity_registerOracle_revertsNonAssembler() public {
        vm.prank(alice);
        vm.expectRevert(DataIntegrityModule.OnlyAssembler.selector);
        dataIntegrity.registerOracle(oracle1);
    }

    function test_dataIntegrity_updateOracleData() public {
        vm.startPrank(address(assembler));
        dataIntegrity.registerOracle(oracle1);
        dataIntegrity.updateOracleData(oracle1, 2000e18);
        vm.stopPrank();

        (address oAddr, uint256 lastPrice, uint256 lastUpdate, , bool active) = dataIntegrity.oracles(oracle1);
        assertEq(oAddr, oracle1);
        assertEq(lastPrice, 2000e18);
        assertGt(lastUpdate, 0);
        assertTrue(active);
    }

    function test_dataIntegrity_updateOracleData_revertsUnknown() public {
        vm.prank(address(assembler));
        vm.expectRevert(DataIntegrityModule.OracleNotFound.selector);
        dataIntegrity.updateOracleData(oracle1, 2000e18);
    }

    function test_dataIntegrity_checkIntegrity_passesWithConsistentData() public {
        vm.startPrank(address(assembler));
        dataIntegrity.registerOracle(oracle1);
        dataIntegrity.registerOracle(oracle2);
        dataIntegrity.updateOracleData(oracle1, 2000e18);
        dataIntegrity.updateOracleData(oracle2, 2010e18); // within 5% deviation
        vm.stopPrank();

        (bool passed, uint256 medianPrice, uint256 activeOracles, uint256 stale, uint256 deviating) =
            dataIntegrity.checkIntegrity();

        assertTrue(passed);
        assertGt(medianPrice, 0);
        assertEq(activeOracles, 2);
        assertEq(stale, 0);
        assertEq(deviating, 0);
    }

    function test_dataIntegrity_checkIntegrity_failsWithStaleData() public {
        vm.startPrank(address(assembler));
        dataIntegrity.registerOracle(oracle1);
        dataIntegrity.updateOracleData(oracle1, 2000e18);
        vm.stopPrank();

        // Warp past staleness threshold (300s)
        vm.warp(block.timestamp + 301);

        (bool passed, , , uint256 stale, ) = dataIntegrity.checkIntegrity();
        assertFalse(passed);
        assertEq(stale, 1);
    }

    function test_dataIntegrity_checkIntegrity_failsWithDeviatingData() public {
        vm.startPrank(address(assembler));
        dataIntegrity.registerOracle(oracle1);
        dataIntegrity.registerOracle(oracle2);
        dataIntegrity.registerOracle(oracle3);
        dataIntegrity.updateOracleData(oracle1, 2000e18);
        dataIntegrity.updateOracleData(oracle2, 2000e18);
        dataIntegrity.updateOracleData(oracle3, 3000e18); // 50% deviation
        vm.stopPrank();

        (bool passed, , , , uint256 deviating) = dataIntegrity.checkIntegrity();
        assertFalse(passed);
        assertGt(deviating, 0);
    }

    function test_dataIntegrity_beforeSwapModule_blocksOnBadData() public {
        vm.startPrank(address(assembler));
        dataIntegrity.registerOracle(oracle1);
        dataIntegrity.registerOracle(oracle2);
        dataIntegrity.updateOracleData(oracle1, 2000e18);
        dataIntegrity.updateOracleData(oracle2, 4000e18); // huge deviation
        vm.stopPrank();

        (uint24 fee, bool blocked) = dataIntegrity.beforeSwapModule(alice, 1 ether, true);
        assertEq(fee, 0);
        assertTrue(blocked);
        assertEq(dataIntegrity.blockedByIntegrity(), 1);
    }

    function test_dataIntegrity_beforeSwapModule_passesWithGoodData() public {
        vm.startPrank(address(assembler));
        dataIntegrity.registerOracle(oracle1);
        dataIntegrity.registerOracle(oracle2);
        dataIntegrity.updateOracleData(oracle1, 2000e18);
        dataIntegrity.updateOracleData(oracle2, 2010e18);
        vm.stopPrank();

        (uint24 fee, bool blocked) = dataIntegrity.beforeSwapModule(alice, 1 ether, true);
        assertEq(fee, 0);
        assertFalse(blocked);
    }

    function test_dataIntegrity_beforeSwapModule_passesWithNoOracles() public {
        // No oracles registered - should pass by default
        (uint24 fee, bool blocked) = dataIntegrity.beforeSwapModule(alice, 1 ether, true);
        assertEq(fee, 0);
        assertFalse(blocked);
    }

    function test_dataIntegrity_removeOracle() public {
        vm.startPrank(address(assembler));
        dataIntegrity.registerOracle(oracle1);
        dataIntegrity.registerOracle(oracle2);
        dataIntegrity.removeOracle(oracle1);
        vm.stopPrank();

        address[] memory list = dataIntegrity.getOracleList();
        assertEq(list.length, 1);
        assertEq(list[0], oracle2);
    }

    // ================================================================
    // SECTION 3: MoltbookIdentityModule Tests
    // ================================================================

    function test_moltbook_verifyAgent() public {
        vm.prank(address(assembler));
        moltbookIdentity.verifyAgent(alice, keccak256("alice-id"), 100, "Alice Agent");

        assertTrue(moltbookIdentity.isAgentVerified(alice));
        assertEq(moltbookIdentity.totalVerified(), 1);

        MoltbookIdentityModule.AgentIdentity memory identity = moltbookIdentity.getAgentIdentity(alice);
        assertEq(identity.moltbookIdHash, keccak256("alice-id"));
        assertEq(identity.karma, 100);
        assertTrue(identity.isVerified);
    }

    function test_moltbook_verifyAgent_revertsDuplicate() public {
        vm.startPrank(address(assembler));
        moltbookIdentity.verifyAgent(alice, keccak256("alice-id"), 100, "Alice");

        vm.expectRevert(MoltbookIdentityModule.AgentAlreadyVerified.selector);
        moltbookIdentity.verifyAgent(alice, keccak256("alice-id-2"), 200, "Alice2");
        vm.stopPrank();
    }

    function test_moltbook_verifyAgent_revertsNonAssembler() public {
        vm.prank(alice);
        vm.expectRevert(MoltbookIdentityModule.OnlyAssembler.selector);
        moltbookIdentity.verifyAgent(bob, keccak256("bob-id"), 50, "Bob");
    }

    function test_moltbook_revokeAgent() public {
        vm.startPrank(address(assembler));
        moltbookIdentity.verifyAgent(alice, keccak256("alice-id"), 100, "Alice");
        moltbookIdentity.revokeAgent(alice);
        vm.stopPrank();

        assertFalse(moltbookIdentity.isAgentVerified(alice));
        assertEq(moltbookIdentity.totalVerified(), 0);
    }

    function test_moltbook_revokeAgent_revertsNotVerified() public {
        vm.prank(address(assembler));
        vm.expectRevert(MoltbookIdentityModule.AgentNotVerified.selector);
        moltbookIdentity.revokeAgent(alice);
    }

    function test_moltbook_beforeSwap_feeDiscountForVerified() public {
        vm.prank(address(assembler));
        moltbookIdentity.verifyAgent(alice, keccak256("alice-id"), 100, "Alice");

        (uint24 fee, bool blocked) = moltbookIdentity.beforeSwapModule(alice, 1 ether, true);
        assertEq(fee, 50); // identityTrustBonus
        assertFalse(blocked);
        assertEq(moltbookIdentity.totalDiscountsApplied(), 1);
    }

    function test_moltbook_beforeSwap_noDiscountForUnverified() public {
        (uint24 fee, bool blocked) = moltbookIdentity.beforeSwapModule(alice, 1 ether, true);
        assertEq(fee, 0);
        assertFalse(blocked);
        assertEq(moltbookIdentity.totalDiscountsApplied(), 0);
    }

    function test_moltbook_beforeSwap_blocksUnverifiedWhenRequired() public {
        // Deploy a module with requireIdentity = true
        vm.prank(owner);
        MoltbookIdentityModule strictModule = new MoltbookIdentityModule(
            address(assembler),
            true,   // requireIdentity
            50
        );

        (uint24 fee, bool blocked) = strictModule.beforeSwapModule(alice, 1 ether, true);
        assertEq(fee, 0);
        assertTrue(blocked);
    }

    function test_moltbook_beforeSwap_allowsVerifiedWhenRequired() public {
        vm.prank(owner);
        MoltbookIdentityModule strictModule = new MoltbookIdentityModule(
            address(assembler),
            true,   // requireIdentity
            50
        );

        vm.prank(address(assembler));
        strictModule.verifyAgent(alice, keccak256("alice-id"), 100, "Alice");

        (uint24 fee, bool blocked) = strictModule.beforeSwapModule(alice, 1 ether, true);
        assertEq(fee, 50);
        assertFalse(blocked);
    }

    // ================================================================
    // SECTION 4: StrategyLicense Tests
    // ================================================================

    function test_license_listForLicense() public {
        // Mint an NFT first so ownerOf works
        address[] memory mods = new address[](0);
        bytes[] memory params = new bytes[](0);
        vm.prank(owner);
        uint256 tokenId = nft.mint(
            alice, address(assembler), 0, keccak256("config"),
            mods, params, 10, 50 ether, 200, 3, 7 days, 500, 1800e18
        );

        vm.prank(alice);
        license.listForLicense(
            tokenId,
            0.1 ether,              // price
            30 days,                 // period
            StrategyLicense.LicenseType.TIME_BASED
        );

        (
            uint256 price,
            uint256 period,
            StrategyLicense.LicenseType ltype,
            bool active,
            ,
        ) = license.licenses(tokenId);

        assertEq(price, 0.1 ether);
        assertEq(period, 30 days);
        assertTrue(ltype == StrategyLicense.LicenseType.TIME_BASED);
        assertTrue(active);
    }

    function test_license_listForLicense_revertsNonOwner() public {
        address[] memory mods = new address[](0);
        bytes[] memory params = new bytes[](0);
        vm.prank(owner);
        uint256 tokenId = nft.mint(
            alice, address(assembler), 0, keccak256("config"),
            mods, params, 0, 0, 0, 0, 0, 0, 0
        );

        vm.prank(bob);
        vm.expectRevert(StrategyLicense.OnlyNFTOwner.selector);
        license.listForLicense(tokenId, 0.1 ether, 30 days, StrategyLicense.LicenseType.TIME_BASED);
    }

    function test_license_listForLicense_revertsZeroPrice() public {
        address[] memory mods = new address[](0);
        bytes[] memory params = new bytes[](0);
        vm.prank(owner);
        uint256 tokenId = nft.mint(
            alice, address(assembler), 0, keccak256("config"),
            mods, params, 0, 0, 0, 0, 0, 0, 0
        );

        vm.prank(alice);
        vm.expectRevert(StrategyLicense.InvalidParams.selector);
        license.listForLicense(tokenId, 0, 30 days, StrategyLicense.LicenseType.TIME_BASED);
    }

    function test_license_lease_timeBased() public {
        // Setup: mint NFT and list license
        address[] memory mods = new address[](0);
        bytes[] memory params = new bytes[](0);
        vm.prank(owner);
        uint256 tokenId = nft.mint(
            alice, address(assembler), 0, keccak256("config"),
            mods, params, 0, 0, 0, 0, 0, 0, 0
        );

        vm.prank(alice);
        license.listForLicense(tokenId, 0.1 ether, 30 days, StrategyLicense.LicenseType.TIME_BASED);

        // Fund treasury to receive protocol fee transfer
        vm.deal(bob, 1 ether);
        vm.deal(treasury, 0);

        vm.prank(bob);
        license.lease{value: 0.1 ether}(tokenId);

        assertTrue(license.checkLeaseValid(tokenId, bob));
        assertEq(license.totalLeasesCreated(), 1);

        // Revenue distribution: 5% to protocol, 95% to owner
        uint256 protocolCut = (0.1 ether * 500) / 10000; // 0.005 ether
        uint256 ownerCut = 0.1 ether - protocolCut;
        assertEq(license.ownerRevenue(tokenId), ownerCut);
        assertEq(treasury.balance, protocolCut);
    }

    function test_license_lease_revertsInsufficientPayment() public {
        address[] memory mods = new address[](0);
        bytes[] memory params = new bytes[](0);
        vm.prank(owner);
        uint256 tokenId = nft.mint(
            alice, address(assembler), 0, keccak256("config"),
            mods, params, 0, 0, 0, 0, 0, 0, 0
        );

        vm.prank(alice);
        license.listForLicense(tokenId, 0.1 ether, 30 days, StrategyLicense.LicenseType.TIME_BASED);

        vm.deal(bob, 1 ether);
        vm.prank(bob);
        vm.expectRevert(StrategyLicense.InsufficientPayment.selector);
        license.lease{value: 0.05 ether}(tokenId);
    }

    function test_license_checkLeaseValid_expiredTimeBased() public {
        address[] memory mods = new address[](0);
        bytes[] memory params = new bytes[](0);
        vm.prank(owner);
        uint256 tokenId = nft.mint(
            alice, address(assembler), 0, keccak256("config"),
            mods, params, 0, 0, 0, 0, 0, 0, 0
        );

        vm.prank(alice);
        license.listForLicense(tokenId, 0.1 ether, 30 days, StrategyLicense.LicenseType.TIME_BASED);

        vm.deal(bob, 1 ether);
        vm.prank(bob);
        license.lease{value: 0.1 ether}(tokenId);

        // Warp past lease expiry
        vm.warp(block.timestamp + 31 days);
        assertFalse(license.checkLeaseValid(tokenId, bob));
    }

    function test_license_checkLeaseValid_perpetualNeverExpires() public {
        address[] memory mods = new address[](0);
        bytes[] memory params = new bytes[](0);
        vm.prank(owner);
        uint256 tokenId = nft.mint(
            alice, address(assembler), 0, keccak256("config"),
            mods, params, 0, 0, 0, 0, 0, 0, 0
        );

        vm.prank(alice);
        license.listForLicense(tokenId, 1 ether, 0, StrategyLicense.LicenseType.PERPETUAL);

        vm.deal(bob, 2 ether);
        vm.prank(bob);
        license.lease{value: 1 ether}(tokenId);

        // Even far in the future, perpetual lease is valid
        vm.warp(block.timestamp + 365 days);
        assertTrue(license.checkLeaseValid(tokenId, bob));
    }

    function test_license_revenueDistribution() public {
        address[] memory mods = new address[](0);
        bytes[] memory params = new bytes[](0);
        vm.prank(owner);
        uint256 tokenId = nft.mint(
            alice, address(assembler), 0, keccak256("config"),
            mods, params, 0, 0, 0, 0, 0, 0, 0
        );

        vm.prank(alice);
        license.listForLicense(tokenId, 1 ether, 30 days, StrategyLicense.LicenseType.TIME_BASED);

        vm.deal(bob, 2 ether);
        vm.deal(treasury, 0);
        vm.prank(bob);
        license.lease{value: 1 ether}(tokenId);

        // Protocol gets 5% = 0.05 ether
        assertEq(treasury.balance, 0.05 ether);
        // Owner gets 95% = 0.95 ether (claimable)
        assertEq(license.ownerRevenue(tokenId), 0.95 ether);
        assertEq(license.totalProtocolRevenue(), 0.05 ether);
    }

    function test_license_usageBased_expiresAfterSwaps() public {
        address[] memory mods = new address[](0);
        bytes[] memory params = new bytes[](0);
        vm.prank(owner);
        uint256 tokenId = nft.mint(
            alice, address(assembler), 0, keccak256("config"),
            mods, params, 0, 0, 0, 0, 0, 0, 0
        );

        // List as USAGE_BASED with maxSwaps = 3 (periodSeconds repurposed)
        vm.prank(alice);
        license.listForLicense(tokenId, 0.1 ether, 3, StrategyLicense.LicenseType.USAGE_BASED);

        vm.deal(bob, 1 ether);
        vm.prank(bob);
        license.lease{value: 0.1 ether}(tokenId);

        assertTrue(license.checkLeaseValid(tokenId, bob));

        // Record 3 swap usages
        license.recordSwapUsage(tokenId, bob);
        license.recordSwapUsage(tokenId, bob);
        license.recordSwapUsage(tokenId, bob);

        // Should now be expired
        assertFalse(license.checkLeaseValid(tokenId, bob));
    }
}

/// @dev Helper contract to test GenesisRevertLib revert functions
contract RevertLibHarness {
    using GenesisRevertLib for bytes4;

    function triggerCognitiveGate() external pure {
        GenesisRevertLib.revertCognitiveGate(
            1, 0.8e18, 0.5e18, GenesisRevertLib.RecoveryAction.INCREASE_CONFIDENCE
        );
    }

    function triggerEconomicConstraint() external pure {
        GenesisRevertLib.revertEconomicConstraint(50 gwei, 1 ether, 0.5 ether, 60);
    }

    function triggerStateDependency() external view {
        GenesisRevertLib.revertStateDependency(
            bytes32(uint256(1)), 100, 200, address(0xC1)
        );
    }

    function triggerModuleRejection() external pure {
        GenesisRevertLib.revertModuleRejection(
            keccak256("test.module"), 5000, 3000, GenesisRevertLib.RecoveryAction.ADJUST_PARAMS
        );
    }

    function triggerConfidenceStale() external view {
        GenesisRevertLib.revertConfidenceStale(100, 3600);
    }

    function callIsRecoverable(bytes4 selector) external pure returns (bool) {
        return GenesisRevertLib.isRecoverable(selector);
    }

    function callEncodeRecoveryHint(uint8 action, bytes memory params) external pure returns (bytes memory) {
        return GenesisRevertLib.encodeRecoveryHint(action, params);
    }
}
