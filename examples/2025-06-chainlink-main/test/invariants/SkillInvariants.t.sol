// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {BaseInvariant} from "./BaseInvariant.t.sol";
import {IBUILDFactory} from "../../src/interfaces/IBUILDFactory.sol";

/// @title Skill-contributed invariants for Chainlink Rewards (CLR), layered on the project's own
/// invariant harness (orchestrate, don't rebuild). These target angles the shipped suite does not
/// assert directly: cross-project token isolation and factory-accounting conservation.
contract SkillInvariants is BaseInvariant {
  /// SKILL — cross-project isolation: each BUILDClaim contract only ever holds its OWN token.
  /// Operations on one project (deposit/withdraw/claim/refund) must never move another project's
  /// token into the wrong claim contract. A classic cross-market accounting-bleed bug class.
  function invariant_crossProjectTokenIsolation() public view {
    assertEq(
      s_token_2.balanceOf(address(s_claim)), 0, "claim1 holds token2 (cross-project bleed)"
    );
    assertEq(
      s_token.balanceOf(address(s_claim_2)), 0, "claim2 holds token1 (cross-project bleed)"
    );
  }

  /// SKILL — factory accounting conservation: for each token, tokens WITHDRAWN can never exceed the
  /// tokens that flowed IN (deposited + refunded). A break would mean the withdrawal accounting let
  /// the project pull out more than it ever put in.
  function invariant_withdrawnNeverExceedsInflows() public view {
    IBUILDFactory.TokenAmounts memory a = s_factory.getTokenAmounts(address(s_token));
    assertLe(
      a.totalWithdrawn,
      a.totalDeposited + a.totalRefunded,
      "withdrawn exceeds deposited+refunded (token1)"
    );
    IBUILDFactory.TokenAmounts memory b = s_factory.getTokenAmounts(address(s_token_2));
    assertLe(
      b.totalWithdrawn,
      b.totalDeposited + b.totalRefunded,
      "withdrawn exceeds deposited+refunded (token2)"
    );
  }

  // added to be excluded from coverage report (matches the project's own pattern)
  function test() public override {}
}
