// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {BeforeAfter} from "./BeforeAfter.sol";
import {Asserts} from "@chimera/Asserts.sol";
import {UpsideMetaCoin} from "../../contracts/UpsideMetaCoin.sol";

// Stage 3 (skill): one boolean property_* per approved invariant, mapped to its IR id.
abstract contract Properties is BeforeAfter, Asserts {
    /// INV-SOLVENCY-LT: the protocol always holds enough liquidity token to cover protocol fees + net reserves.
    function property_INV_SOLVENCY_LT() public returns (bool) {
        (,, uint256 ltRes,,) = protocol.metaCoinInfoMap(metaCoin);
        uint256 obligations = protocol.claimableProtocolFees() + (ltRes - INITIAL);
        return usdc.balanceOf(address(protocol)) >= obligations;
    }

    /// INV-SOLVENCY-MC: the protocol always holds enough MetaCoin to cover reserves + unclaimed deployer fees.
    function property_INV_SOLVENCY_MC() public returns (bool) {
        (address deployer,,, uint256 mcRes,) = protocol.metaCoinInfoMap(metaCoin);
        uint256 obligations = mcRes + protocol.claimableDeployerFees(metaCoin, deployer);
        return UpsideMetaCoin(metaCoin).balanceOf(address(protocol)) >= obligations;
    }

    /// INV-RESERVES-FLOOR: the (virtual) liquidity reserve floor is never breached.
    function property_INV_RESERVES_FLOOR() public returns (bool) {
        (,, uint256 ltRes,,) = protocol.metaCoinInfoMap(metaCoin);
        return ltRes >= INITIAL;
    }

    /// INV-CROSS-COIN-ISOLATION (persona: reentrancy composer): the SECOND coin, which is never
    /// traded, keeps its untouched initial reserves — one coin's ops must not corrupt another's.
    function property_INV_CROSS_COIN_ISOLATION() public returns (bool) {
        (,, uint256 ltRes2, uint256 mcRes2,) = protocol.metaCoinInfoMap(metaCoin2);
        // metaCoin2 is never traded by any handler, so its reserves must equal the tokenize defaults.
        return ltRes2 == INITIAL && mcRes2 == 1_000_000e18;
    }

    /// INV-SOLVENCY-MC-2 (persona: composer): per-coin metacoin solvency also holds for the 2nd coin.
    function property_INV_SOLVENCY_MC_2() public returns (bool) {
        (address deployer,,, uint256 mcRes,) = protocol.metaCoinInfoMap(metaCoin2);
        uint256 obligations = mcRes + protocol.claimableDeployerFees(metaCoin2, deployer);
        return UpsideMetaCoin(metaCoin2).balanceOf(address(protocol)) >= obligations;
    }
}
