// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.27;

import {CentralizedOracle} from "src/oracles/CentralizedOracle.sol";

/// @notice Medusa harness for CentralizedOracle. The tester owns the oracle, so it can drive price
/// updates, and asserts the conversion invariants: a USD<->TOKEN round trip never creates value
/// (both directions round down), and a stale price must return 0 (never misprice on stale data).
contract CryticTester {
    CentralizedOracle public oracle;
    address internal constant TOKEN = address(0xA11ce);
    uint256 internal constant STALENESS = 7 days;

    constructor() {
        oracle = new CentralizedOracle(TOKEN, 1e18);   // 1 USD/token, owner = this tester
    }

    // ---- handlers ----

    function handler_updatePrice(uint256 p) public {
        // updateTokenPrice reverts outside +-5x; let medusa try (reverts are tolerated).
        try oracle.updateTokenPrice(p) {} catch {}
    }

    /// round-trip must never create value: convertFromUsd(convertToUsd(x)) <= x (rounding favors none).
    function handler_roundtrip(uint256 amount) public view {
        amount = amount % 1e30;
        uint256 usd = oracle.convertToUsd(TOKEN, amount);
        uint256 back = oracle.convertFromUsd(TOKEN, usd);
        assert(back <= amount);
    }

    // ---- properties ----

    /// a stale price (older than the staleness threshold) must convert to 0, never a nonzero misprice.
    function property_stale_returns_zero() public view returns (bool) {
        if (block.timestamp - oracle.lastPriceUpdateTimestamp() > STALENESS) {
            return oracle.convertToUsd(TOKEN, 1e18) == 0 && oracle.convertFromUsd(TOKEN, 1e18) == 0;
        }
        return true;
    }
}
