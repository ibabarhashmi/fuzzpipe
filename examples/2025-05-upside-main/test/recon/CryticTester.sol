// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {TargetFunctions} from "./TargetFunctions.sol";
import {CryticAsserts} from "@chimera/CryticAsserts.sol";

// Echidna/Medusa entrypoint. Usually left as-is.
contract CryticTester is TargetFunctions, CryticAsserts {
    constructor() payable {
        setup();
    }
}
