# Threat model (auto-generated, Stage 0) — UpsideProtocol

Derived from the contract surface per `guidance/08-threat-model-gen.md`. Feeds Stage 2b personas.

## Actors
- unprivileged trader (buys/sells on the bonding curve)
- MetaCoin deployer (whoever called `tokenize`; earns deployer fees)
- protocol owner / admin (owns `UpsideProtocol`)
- staking contract (receives sell-side staker fees)
- URL squatter / front-runner (races `tokenize`)

## Assets at risk
- liquidity token (USDC) held by the protocol: in on buy, out on sell / `claimProtocolFees` / `withdrawLiquidity`
- MetaCoin inventory (1M minted to protocol per `tokenize`): out on buy, in on sell, out via deployer/staker fees + `withdrawLiquidity`
- `claimableProtocolFees` (USDC), `claimableDeployerFees` (MetaCoin) — accrued obligations
- bonding-curve reserves (`liquidityTokenReserves` incl. a *virtual* `INITIAL_LIQUIDITY_RESERVES`, `metaCoinReserves`)

## External calls / trust
- `safeTransferFrom`/`safeTransfer` on arbitrary ERC20 (liquidity token, tokenize-fee token) and on the MetaCoin
- `IUpsideStaking.distributeRewards` / `whitelistStakingToken` (staking contract, owner-set)
- MetaCoin transfer whitelist gate (`metaCoinWhitelist`) — protocol + staking auto-whitelisted
- NOTE: swaps use the *internal* bonding curve, **no external price oracle** (so oracle-manipulation is N/A)

## Attacker goals (each → an anti-property for Stage 2b)
| # | Goal (one sentence) | Surface | Persona |
|---|---------------------|---------|---------|
| G1 | buy tokens while paying zero swap fee | swap fee | MEV / rounding |
| G2 | profit from a buy→sell round trip | bonding curve | MEV / first-depositor |
| G3 | drain or strand a *different* MetaCoin's reserves | cross-coin accounting | reentrancy composer |
| G4 | call an owner-only function as a non-owner | privileged setters | malicious admin |
| G5 | front-run `tokenize` to squat a URL | tokenize | griefer / MEV |
| G6 | make the protocol owe more than it holds | value flows | first-depositor / composer |
| G7 | grief `withdrawLiquidity` / lock funds via the global 14-day timer | withdraw path | griefer |
| G8 | claim more deployer fees than accrued | deployer fees | malicious admin / rounding |
| G9 | inflate share price against the next buyer (donation / first deposit) | curve init | first-depositor |

## Trust assumptions (recorded, not fuzzed)
- the owner and the configured staking contract are honest
- the liquidity token and tokenize-fee tokens are standard ERC20 (no fee-on-transfer / no callbacks)
