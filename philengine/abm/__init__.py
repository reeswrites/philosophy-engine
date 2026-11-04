"""Layer 2: agent-based runs over the same InstitutionJSON that `phil rules` checks.

Plan: computational-liberation/plans/layer2-abm.md. Layer 1 says what the rules permit or force; this layer puts
`agents_per_role` simple adaptive agents under those rules and reports what they do, how often. Outputs are rates
over seeds, statements about an encoding plus a policy, never about real populations (ADR 0011).

Enabledness is never reimplemented here: `model.py` instantiates `rules_reference.Reference` on the institution and
asks it which action instances are powers (`Reference.power`, the ADR 0013 `(enabled ...)` reading) in the current
state, which must / must_not instances bind now, and uses its `successor` for effects. Anything the reference does
not define, the ABM does not know.

SLICE 1: `material` mechanism only, as the simplest payoff-following adoption; `coordination` and `imagination`
are stubs raising NotImplementedError. No scorer, no sweep, no gate.

Design choices the plan leaves open, or that this slice had to make. Each is taken as the plan's proposed default
(or the simplest reading) and is ASSUMED - awaiting author decision:

  payoff location   ASSUMED: an optional top-level `payoffs` dict on the institution's entry in institutions.json
                    (the plan proposes "a payoffs block on the dataset entry, not on InstitutionJSON").
                    `InstitutionJSON` is not changed; `model.load_payoffs` reads the raw entry. A key naming an
                    action is that action's payoff (imitation, payoff-following); a key naming a fluent is an
                    income fluent (surplus). Absent: every action pays `default_payoff`, income is `default_income`.
  per-agent typing  ASSUMED: enabledness is evaluated at the role level. The reference's domain is one agent per
                    role; the ABM's N agents of role r all read the same action instances (a, (r, ...)) as
                    available, and the shared institutional state is the reference's role-level state. No
                    per-agent fluent tuples yet (plan open question 1).
  availability      ASSUMED: available = `Reference.power` exactly (a sanctionable must_not leaves the action
                    available; only an `or_else: null` disability bars it). An action no may/must rule names is
                    never available to an agent (ADR 0013 amendment).
  compliance        ASSUMED: strict on the firing side. A must whose condition holds is always followed; an action a
                    must_not (sanctionable or not) forbids now is never chosen. The plan's breach test (expected
                    gain vs or_else cost weighted by belief in sanction) is not in this slice.
  choice order      ASSUMED (agent.py): must > forbidden filter > material floor collapse > success imitation
                    (copy_rate, only if the neighbour earned more) > material switch to a strictly better-paying
                    candidate > same-role threshold > material bootstrap argmax (no usable practice) > keep.
                    Payoff-following sits before the threshold rule so that a payoff block can move a convention
                    at all; with uniform payoffs it never fires and the threshold rule alone governs.
  update            ASSUMED: synchronous. Practices are snapshotted at the start of a step and every choice reads
                    the snapshot; `shuffle_do` still randomises order for the rng draws. (Asynchronous update was
                    the first cut; it let early movers' choices feed late movers' shares within one step.)
  graph             ASSUMED: one Watts-Strogatz graph (k=6, p=0.1) spans all roles; neighbours of every role are
                    the reference group for imitation and trust, but adoption shares (threshold rule) are taken
                    over same-role neighbours only, so a role's share is not capped by its fraction of the graph.
                    For a population n <= k the graph is complete (tests), reported as a warning.
  state update      ASSUMED: at each step the union of distinct action instances chosen by any agent fires once
                    (effects land next step via `Reference.successor`); step_mode "many" semantics.
  initial state     ASSUMED: the reference's declared/empty split, with every unconstrained atom false (warned).
  trust             ASSUMED: per-dyad trust starts at `initial_trust`, +delta when a neighbour met the obligation
                    that bound it this step, -beta*delta when it did not; clipped to [0,1]; carried, not consumed.
                    OPEN QUESTION: the code keys the update off the neighbour's own obligation; the plan (lines
                    45-46) says an obligation "bearing on this agent" (the observer). Needs a reading of which
                    rule instances bear on whom; left as is until decided.
  pledge            ASSUMED: not represented in slice 1 (coordination module is a stub). When it lands it will
                    be a dataset convention (an action whose name ends in `_pledge`), not an ActionDecl flag.
  parameters        ASSUMED: every DEFAULT_PARAMS value (model.py) is a placeholder, to be swept, never calibrated
                    (plan: "Non-goals"; gate (b) forbids a constant that sets the tipping location). Proposed
                    sweep ranges:
                      copy_rate        0.3   -> {0.0, 0.1, 0.3, 0.5, 0.7}
                      default_payoff   1.0   -> held at 1.0 (a unit; payoff blocks are relative to it)
                      default_income   1.0   -> {0.0, 0.5, 1.0, 2.0} (0.0 makes the floor bind for everyone)
                      initial_surplus  2.0   -> {0.0, 1.0, 2.0, 5.0}
                      floor            1.0   -> {0.5, 1.0, 2.0}
                      floor_cost       0.5   -> {0.0, 0.25, 0.5, 1.0}
                      initial_trust    0.5   -> {0.2, 0.5, 0.8}
                      trust_delta      0.1   -> {0.05, 0.1, 0.2}
                      trust_beta       2.0   -> {1.5, 2.0, 3.0}
                    plus graph k in {4, 6, 8} and p in {0.0, 0.1, 0.5} (plan open question 2: lattice / random).
"""
from .model import InstitutionModel, load_payoffs, run_abm
from .report import AbmReport, summarize

__all__ = ["AbmReport", "InstitutionModel", "run_abm", "load_payoffs", "summarize"]
