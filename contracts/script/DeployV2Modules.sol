// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import "forge-std/Script.sol";
import {GenesisHookAssembler} from "../src/GenesisHookAssembler.sol";
import {DataIntegrityModule} from "../src/modules/DataIntegrityModule.sol";
import {MoltbookIdentityModule} from "../src/modules/MoltbookIdentityModule.sol";
import {StrategyLicense} from "../src/StrategyLicense.sol";
import {StrategyNFT} from "../src/StrategyNFT.sol";

/// @title DeployV2Modules - Deploy Genesis Protocol V2 modules to an existing assembler
/// @notice Run: forge script script/DeployV2Modules.sol:DeployV2Modules --rpc-url https://rpc.xlayer.tech --broadcast
/// @dev Requires PRIVATE_KEY, ASSEMBLER_ADDRESS, STRATEGY_NFT_ADDRESS, and TREASURY_ADDRESS env vars
contract DeployV2Modules is Script {

    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        address assemblerAddr = vm.envAddress("ASSEMBLER_ADDRESS");
        address strategyNFTAddr = vm.envAddress("STRATEGY_NFT_ADDRESS");
        address treasuryAddr = vm.envAddress("TREASURY_ADDRESS");

        console.log("=== Genesis Protocol - V2 Modules Deployment ===");
        console.log("Deployer:", deployer);
        console.log("Chain ID:", block.chainid);
        console.log("Assembler:", assemblerAddr);

        GenesisHookAssembler assembler = GenesisHookAssembler(assemblerAddr);

        vm.startBroadcast(deployerKey);

        // 1. Deploy DataIntegrityModule
        DataIntegrityModule dataIntegrity = new DataIntegrityModule(
            assemblerAddr,
            500,    // maxPriceDeviationBps (5%)
            300     // maxStalenessSeconds (5 min)
        );
        console.log("DataIntegrityModule:", address(dataIntegrity));

        // 2. Deploy MoltbookIdentityModule
        MoltbookIdentityModule moltbookIdentity = new MoltbookIdentityModule(
            assemblerAddr,
            false,  // requireIdentity (start permissive)
            50      // identityTrustBonus (0.50% fee discount)
        );
        console.log("MoltbookIdentityModule:", address(moltbookIdentity));

        // 3. Deploy StrategyLicense
        StrategyLicense strategyLicense = new StrategyLicense(
            strategyNFTAddr,
            treasuryAddr,
            500     // protocolFeeBps (5%)
        );
        console.log("StrategyLicense:", address(strategyLicense));

        // 4. Register modules with assembler
        assembler.registerModule(address(dataIntegrity));
        assembler.registerModule(address(moltbookIdentity));
        console.log("V2 modules registered with assembler (2 modules).");

        vm.stopBroadcast();

        console.log("\n=== V2 Deployment Complete ===");
        console.log("DataIntegrityModule:", address(dataIntegrity));
        console.log("MoltbookIdentityModule:", address(moltbookIdentity));
        console.log("StrategyLicense:", address(strategyLicense));
        console.log("Update .env with V2 contract addresses.");
    }
}
