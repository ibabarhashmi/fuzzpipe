// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.27;

import {InvariantsHelperSingleAsset} from "./helper.sol";
import {FractionalAssets} from "src/fractional/FractionalAssets.sol";
import {PinlinkShop} from "src/marketplaces/pinlinkShop.sol";
import {Test} from "forge-std/Test.sol";
import {DummyOracle} from "src/oracles/DummyOracle.sol";
import {ERC20Mock} from "lib/openzeppelin-contracts/contracts/mocks/token/ERC20Mock.sol";

/// @notice Skill-contributed invariants for PinlinkShop, layered on the project's own fuzzing helper
/// (orchestrate, don't rebuild). These target PHYSICAL-vs-accounting solvency and PIN flow — angles
/// the shipped suite (balance consistency + reward conservation) does not assert directly.
contract PinlinkShop_SkillInvariants is Test {
    FractionalAssets fractions;
    PinlinkShop pshop;
    DummyOracle oracle;
    ERC20Mock PIN;
    ERC20Mock USDC;
    InvariantsHelperSingleAsset helper;

    uint256 tokenId = 2222;
    address admin = makeAddr("admin");
    address feeReceiver = makeAddr("feeReceiver");
    address operator = makeAddr("operator");

    function setUp() public {
        PIN = new ERC20Mock();
        USDC = new ERC20Mock();
        oracle = new DummyOracle(address(PIN), 0.95 ether);

        vm.startPrank(admin);
        fractions = new FractionalAssets("https://metadata.pinlink.dev/metadata/0xaaaa/");
        fractions.mint(uint256(tokenId), admin, 100);
        pshop = new PinlinkShop(address(PIN), address(oracle), address(USDC));
        pshop.setFeeReceiver(feeReceiver);
        fractions.setApprovalForAll(address(pshop), true);
        pshop.grantRole(pshop.OPERATOR_ROLE(), operator);
        vm.stopPrank();

        helper = new InvariantsHelperSingleAsset(fractions, pshop, address(PIN), address(USDC), tokenId);
        targetContract(address(helper));
    }

    /// SKILL P0 — asset solvency: the shop must PHYSICALLY hold exactly the fractions it credits as
    /// staked to real accounts. Withdrawn assets keep their staking credit at REWARDS_PROXY_ACCOUNT
    /// but physically leave the shop, so the proxy is excluded from the credited sum.
    function invariant_assetSolvency() public view {
        uint256 physical = fractions.balanceOf(address(pshop), tokenId);
        uint256 credited;
        uint256 n = helper.nActors();
        for (uint256 i; i < n; i++) {
            (uint256 staked,,) = pshop.getBalances(address(fractions), tokenId, helper.actorAt(i));
            credited += staked;
        }
        assertEq(physical, credited, "asset solvency: shop ERC1155 balance != sum of credited staking");
    }

    /// SKILL — the fee is always bounded and PIN (the payment token) never rests in the shop: every
    /// purchase routes PIN buyer->seller and buyer->feeReceiver, never to the shop.
    function invariant_feeBoundAndNoRestingPin() public view {
        assertLe(pshop.purchaseFeePerc(), pshop.MAX_FEE_PERC(), "fee exceeds MAX_FEE_PERC");
        assertEq(PIN.balanceOf(address(pshop)), 0, "PIN should never rest in the shop");
    }
}
