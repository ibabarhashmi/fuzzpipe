// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

// Self-contained fixture for the verdict-gate regression test. No forge-std / chimera imports,
// so it compiles OFFLINE. A `test`-prefixed function that reverts is a failing forge test.

contract Vault {
    uint256 public assets;
    uint256 public owed;

    function deposit(uint256 a) external {
        assets += a;
        owed += a;
    }

    // BUG under test: liability grows without backing assets -> can become insolvent.
    function donate(uint256 a) external {
        owed += a;
    }

    function solvent() public view returns (bool) {
        return assets >= owed;
    }
}

contract PoC {
    // (1) Reproduces the SPECIFIC INV-SOLVENCY break AND asserts harm -> gate must say CONFIRMED.
    function test_repro_INV_SOLVENCY() external {
        Vault v = new Vault();
        v.deposit(100);
        v.donate(50); // owed=150 > assets=100
        require(v.solvent(), "INV-SOLVENCY broken: assets < owed");
    }

    // (2) Invariant HOLDS (no break) -> gate must say SUSPECTED ("did not reproduce").
    function test_holds_INV_SOLVENCY() external {
        Vault v = new Vault();
        v.deposit(100);
        require(v.solvent(), "INV-SOLVENCY broken: assets < owed");
    }

    // (3) Reverts for an UNRELATED reason -> gate must say SUSPECTED, NOT CONFIRMED.
    //     This is the R7 discriminator: "any revert == reproduction" would wrongly confirm here.
    function test_unrelated_INV_SOLVENCY() external {
        Vault v = new Vault();
        v.deposit(100);
        revert("some other unrelated failure");
    }
}
