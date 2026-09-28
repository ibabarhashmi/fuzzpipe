// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

// Minimal self-contained harness entrypoint at the engine-discoverable path (test/recon/).
// Used by the R5 preflight test: a harness here IS compiled by forge; the preflight passes.
contract CryticTester {
    function property_ok() public pure returns (bool) {
        return true;
    }
}
