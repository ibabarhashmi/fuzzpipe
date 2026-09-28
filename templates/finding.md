# [SEVERITY] <Finding title>

**Severity**: Critical / High / Medium / Low
**Broken invariant**: INV-<id> - <invariant statement>
**Engine**: medusa / echidna / foundry
**Status**: CONFIRMED (reproducing test passes) / NEEDS REVIEW

## Description
What the invariant asserts, and what sequence of calls breaks it. Reference exact
functions and state variables. Explain WHY it breaks (the root cause), not just that it does.

## Minimized reproduction (the PoC)
The smallest call sequence that breaks the invariant, as a Foundry test:

```solidity
function test_repro_INV_<id>() public {
    // <minimized sequence replayed from the fuzzer>
    // asserts the HARM, not just the mechanism
}
```

Command:
```
forge test --match-test test_repro_INV_<id> -vvv
```

## Impact (the harm - quantified)
The concrete consequence: who loses what, how much (in tokens/$ at realistic state).
Not "a function was callable" - the actual damage.

## Likelihood
Preconditions, ordering, or privileged actor needed to trigger it.

## Coverage note
Confirm the campaign actually exercised the relevant code (% / which functions). A break
under uncovered code, or a "pass" under uncovered code, is noted here.

## Recommendation
Specific fix (diff-style where possible). After the fix, the reproducer test should no
longer break the invariant.
