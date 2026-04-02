// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @title Deploy - Genesis Protocol deployment script for X Layer
/// @notice Deploys all Genesis contracts in order:
///   1. GenesisHookAssembler (owner = deployer)
///   2. DynamicFeeModule
///   3. MEVProtectionModule
///   4. AutoRebalanceModule
///   5. StrategyNFT (minter = assembler or deployer)
///   6. Register all modules with assembler

import {GenesisHookAssembler} from "../src/GenesisHookAssembler.sol";
import {DynamicFeeModule} from "../src/modules/DynamicFeeModule.sol";
import {MEVProtectionModule} from "../src/modules/MEVProtectionModule.sol";
import {AutoRebalanceModule} from "../src/modules/AutoRebalanceModule.sol";
import {StrategyNFT} from "../src/StrategyNFT.sol";

contract Deploy {

    struct Deployment {
        address assembler;
        address dynamicFee;
        address mevProtection;
        address autoRebalance;
        address strategyNFT;
    }

    function run(address _owner) external returns (Deployment memory d) {
        // 1. Deploy Assembler
        GenesisHookAssembler assembler = new GenesisHookAssembler(_owner);
        d.assembler = address(assembler);

        // 2. Deploy DynamicFeeModule
        //    Default params: baseFee=3000, minFee=500, maxFee=10000,
        //    sensitivity=10000, lowThreshold=200, highThreshold=800
        DynamicFeeModule dynFee = new DynamicFeeModule(
            d.assembler,
            3000,   // baseFee (0.30%)
            500,    // minFee (0.05%)
            10000,  // maxFee (1.00%)
            10000,  // sensitivity (1.0x)
            200,    // lowThreshold (2% vol)
            800     // highThreshold (8% vol)
        );
        d.dynamicFee = address(dynFee);

        // 3. Deploy MEVProtectionModule
        //    Default params: swapCountThreshold=3, volumeThreshold=10000,
        //    penaltyFee=5000, blockSuspicious=false
        MEVProtectionModule mevProt = new MEVProtectionModule(
            d.assembler,
            3,      // swapCountThreshold
            10000,  // volumeThreshold
            5000,   // penaltyFee (0.50%)
            false   // blockSuspicious (penalize, don't block)
        );
        d.mevProtection = address(mevProt);

        // 4. Deploy AutoRebalanceModule
        //    Default params: softTriggerPct=85, ilThresholdBps=200,
        //    cooldownPeriod=300, strategy=IMMEDIATE
        AutoRebalanceModule autoRebal = new AutoRebalanceModule(
            d.assembler,
            -887220,    // lowerTick (wide range, full range ≈ ±887272)
            887220,     // upperTick
            85,         // softTriggerPct
            200,        // ilThresholdBps (2%)
            300,        // cooldownPeriod (5 min)
            AutoRebalanceModule.RebalanceStrategy.IMMEDIATE
        );
        d.autoRebalance = address(autoRebal);

        // 5. Deploy StrategyNFT (minter = deployer for now, can be updated)
        StrategyNFT nft = new StrategyNFT(_owner);
        d.strategyNFT = address(nft);

        // 6. Register modules with assembler
        assembler.registerModule(d.dynamicFee);
        assembler.registerModule(d.mevProtection);
        assembler.registerModule(d.autoRebalance);
    }
}
