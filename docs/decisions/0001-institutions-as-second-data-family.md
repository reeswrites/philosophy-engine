# 0001. Institutions as a second data family in the philosophy engine

## Context
The engine already takes hand-reconstructed arguments, formalizes them, checks them with Z3, judges faithfulness by back-translation, selects a candidate, and tests isomorphism. We want to do the same for institutions described as rule sets. A survey of institutional-grammar tooling found no prior work that runs a solver over Institutional Grammar statements, so there is no existing project to join or extend. Sources: https://github.com/chrfrantz/IG-Parser, https://arxiv.org/html/2505.13393v2, https://arxiv.org/pdf/1711.06128.

## Decision
Institutions are a second data family inside the philosophy engine. They reuse the S-expression grammar and `fol.validate`, the Z3 core, and the judge, select and iso stages. New code is limited to a rule schema, temporal lowering, and the institution-specific checks.

## Alternatives rejected
A separate project would duplicate the grammar, the Z3 harness and the judge, and the two would drift. Extending the arguments schema in place would break the frozen `schemas.py`.

## Consequences
Arguments and institutions share verdict semantics (`open` is never `invalid` or `safe`). Changes to the shared core must keep both families passing. The new schema file is a request, not a change, until accepted.

## Status
accepted
