// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {BaseSetup} from "@chimera/BaseSetup.sol";
import {UpsideProtocol} from "../../contracts/UpsideProtocol.sol";
import {UpsideMetaCoin} from "../../contracts/UpsideMetaCoin.sol";
import {UpsideStakingStub} from "../../contracts/UpsideStakingStub.sol";
import {USDCMock} from "../../contracts/mock/USDCMock.sol";

// Stage 3 (skill): deploy the UpsideProtocol system, tokenize one MetaCoin, fund + approve the actor.
abstract contract Setup is BaseSetup {
    UpsideProtocol internal protocol;
    USDCMock internal usdc;
    UpsideStakingStub internal staking;
    address internal metaCoin;
    address internal metaCoin2; // second coin — for the persona cross-coin-isolation invariant

    uint256 internal constant INITIAL = 10_000 * 1e6; // INITIAL_LIQUIDITY_RESERVES (virtual)
    address internal constant FEE_DEST = address(0xFEE);

    function setup() internal virtual override {
        usdc = new USDCMock();
        protocol = new UpsideProtocol(address(this));
        staking = new UpsideStakingStub(address(this));
        staking.setFeeDestinationAddress(FEE_DEST);

        protocol.init(address(usdc));
        protocol.setStakingContractAddress(address(staking));

        UpsideProtocol.FeeInfo memory fi = UpsideProtocol.FeeInfo({
            tokenizeFeeDestinationAddress: address(this),
            swapFeeDecayInterval: 3600,
            tokenizeFeeEnabled: false,
            swapFeeStartingBp: 100,
            swapFeeDecayBp: 1,
            swapFeeFinalBp: 10,
            swapFeeSellBp: 100,
            swapFeeDeployerBp: 1000
        });
        protocol.setFeeInfo(fi);

        metaCoin = protocol.tokenize("https://upside.gg", address(0));
        metaCoin2 = protocol.tokenize("https://upside.xyz", address(0));

        usdc.mint(address(this), 1e24);
        usdc.approve(address(protocol), type(uint256).max);
        UpsideMetaCoin(metaCoin).approve(address(protocol), type(uint256).max);
        UpsideMetaCoin(metaCoin2).approve(address(protocol), type(uint256).max);
    }
}
