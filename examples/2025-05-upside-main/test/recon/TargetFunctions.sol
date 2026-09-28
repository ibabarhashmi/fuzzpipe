// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {BaseTargetFunctions} from "@chimera/BaseTargetFunctions.sol";
import {Properties} from "./Properties.sol";
import {UpsideMetaCoin} from "../../contracts/UpsideMetaCoin.sol";

// Stage 3 (skill): one clamped, revert-tolerant handler per state-changing entry point.
// This revision adds the STAGE 2b PERSONA-derived checks (sell-side value absorption, constant-product
// k monotonicity) that the docs-mining pass missed. Only metaCoin is traded; metaCoin2 is left
// untouched so the cross-coin isolation property is meaningful.
abstract contract TargetFunctions is BaseTargetFunctions, Properties {
    function handler_buy(uint256 amount) public updateGhosts {
        uint256 bal = usdc.balanceOf(address(this));
        if (bal == 0) return;
        amount = (amount % bal) + 1;
        (,, uint256 lt0, uint256 mc0,) = protocol.metaCoinInfoMap(metaCoin);
        protocol.swap(metaCoin, true, amount, 0, address(this));
        // INV-K-MONOTONIC (persona: MEV/flash-loan): the constant product must never decrease.
        (,, uint256 lt1, uint256 mc1,) = protocol.metaCoinInfoMap(metaCoin);
        gte(lt1 * mc1, lt0 * mc0, "INV-K-MONOTONIC: constant product decreased on buy");
    }

    function handler_sell(uint256 amount) public updateGhosts {
        uint256 bal = UpsideMetaCoin(metaCoin).balanceOf(address(this));
        if (bal == 0) return;
        amount = (amount % bal) + 1;
        (,, uint256 lt0, uint256 mc0,) = protocol.metaCoinInfoMap(metaCoin);
        try protocol.swap(metaCoin, false, amount, 0, address(this)) returns (uint256 out) {
            (,, uint256 lt1, uint256 mc1,) = protocol.metaCoinInfoMap(metaCoin);
            gte(lt1 * mc1, lt0 * mc0, "INV-K-MONOTONIC: constant product decreased on sell");
            // INV-NONZERO-OUTPUT (persona: first-depositor/griefer): a sell of a nonzero amount that
            // does NOT revert must return > 0 liquidity token — else the metacoin input is absorbed for
            // nothing. Same integer-truncation class as finding [03], on the sell side.
            gt(out, 0, "INV-NONZERO-OUTPUT: sell of nonzero amount returned 0 (value absorbed)");
        } catch {}
    }

    function handler_claimProtocolFees() public updateGhosts {
        protocol.claimProtocolFees(address(this));
    }

    function handler_claimDeployerFees() public updateGhosts {
        protocol.claimDeployerFees(metaCoin, address(this));
    }

    // Pattern F — a direct donation must never break solvency (can only make the protocol more solvent).
    function handler_donate(uint256 amount) public updateGhosts {
        amount = amount % 1e12;
        usdc.mint(address(protocol), amount);
    }
}
