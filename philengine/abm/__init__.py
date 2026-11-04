"""Layer 2: agent-based runs over the same InstitutionJSON that `phil rules` checks.

Plan: computational-liberation/plans/layer2-abm.md. Layer 1 says what the rules permit or force; this layer puts
`agents_per_role` simple adaptive agents under those rules and reports what they do, how often. Outputs are rates
over seeds, statements about an encoding plus a policy, never about real populations (ADR 0011).

Enabledness is never reimplemented here: `model.py` instantiates `rules_reference.Reference` on the institution and
asks it which action instances are enabled (firing floor) and which are powers (`(enabled ...)`, ADR 0013) in the
current state, and uses its `successor` for effects. Anything the reference does not define, the ABM does not know.

SLICE 1 (this package as first committed): `material` mechanism only, as the simplest payoff-following adoption;
`coordination` and `imagination` are stubs raising NotImplementedError. No scorer, no sweep, no gate.

Design choices the plan leaves open; each is taken as the plan's proposed default and is
ASSUMED - awaiting author decision:

  payoff location   ASSUMED: an optional top-level `payoffs` dict ({action name: float}) on the institution's
                    entry in institutions.json (the plan proposes "a payoffs block on the dataset entry, not on
                    InstitutionJSON"). `InstitutionJSON` is not changed; `model.load_payoffs` reads the raw entry.
                    Absent, every action pays `default_payoff` (1.0) and keeping one's practice pays 0.
  per-agent typing  ASSUMED: enabledness is evaluated at the role level. The reference's domain is one agent per
                    role; the ABM's N agents of role r all read the same action instances (a, (r, ...)) as
                    enabled, and the shared institutional state is the reference's role-level state. No
                    per-agent fluent tuples yet (plan open question 1).
  pledge            ASSUMED: not represented in slice 1 (coordination module is a stub). When it lands it will
                    be a dataset convention (an action whose name ends in `_pledge`), not an ActionDecl flag.
  state update      ASSUMED: at each step the union of distinct action instances chosen by any agent fires once
                    (effects land next step via `Reference.successor`); step_mode "many" semantics.
  must rules        ASSUMED: a must rule whose condition holds is always followed in slice 1 (the plan's breach
                    test, expected gain vs or_else cost weighted by belief in sanction, is not in this slice).
  trust             ASSUMED: per-dyad trust starts at 0.5 and moves by delta on a kept obligation, beta*delta on
                    a breach; with must always followed it only rises. It is carried, not yet consumed.
"""
from .report import AbmReport
from .model import InstitutionModel, run_abm, load_payoffs

__all__ = ["AbmReport", "InstitutionModel", "run_abm", "load_payoffs"]
