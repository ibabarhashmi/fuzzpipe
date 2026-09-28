// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Setup} from "./Setup.sol";

// Stage 3 (skill): ghost snapshots of the fee + reserve accounting before/after each handler.
abstract contract BeforeAfter is Setup {
    struct Vars {
        uint256 protocolFees;
        uint256 ltReserves;
        uint256 mcReserves;
        uint256 k; // constant-product ltReserves * mcReserves (must be non-decreasing across a swap)
    }

    Vars internal _before;
    Vars internal _after;

    modifier updateGhosts() {
        __snapshot(_before);
        _;
        __snapshot(_after);
    }

    function __snapshot(Vars storage v) internal {
        v.protocolFees = protocol.claimableProtocolFees();
        (,, uint256 lt, uint256 mc,) = protocol.metaCoinInfoMap(metaCoin);
        v.ltReserves = lt;
        v.mcReserves = mc;
        v.k = lt * mc;
    }
}
