# ADR: Contextual Bayesian Search Remains Offline and Evidence-Gated

Date: 2026-08-04
Status: Accepted

## Decision

RacerZLab includes a deterministic, testable contextual Gaussian-process
surrogate for choosing **one next controlled test**. It is not exposed through
a production route and cannot manipulate the simulator.

The helper operates only when all of these facts are already server-verified:

- the P0-P6 experimentation unlock is satisfied from controlled history;
- every observation belongs to one exact driver/car/track/build/weather/setup
  context and links to evidence packets;
- every setup was observed passing tech;
- every searched factor has sufficient controlled history;
- every candidate changes exactly one control;
- every value remains inside the observed tech-passing envelope and, for
  discrete controls, an observed legal-option table;
- uncertainty is reported and penalized, with a 95% predicted interval and
  support distance.

The result is a next-test candidate, not a best setup or guaranteed gain.

## Why production activation is deferred

The repository does not yet contain enough real, independently validated,
exact-context controlled history to pass the unlock threshold and offline
holdout/backtest audit. Client-supplied history cannot unlock the production
route. The existing `/api/engineering/experimentation/*` endpoints therefore
remain fail-closed.

## Activation evidence required

Activation requires a separate reviewed change proving DB-derived unlock,
held-out predictive calibration, safe constraint coverage, deterministic tie
behavior, legal-option provenance, and no regression in every permanent trust
rule. Live input automation remains prohibited.
