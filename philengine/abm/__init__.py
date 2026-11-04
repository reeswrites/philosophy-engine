"""Layer 2: agent-based runs over the same InstitutionJSON that `phil rules` checks.

Plan: computational-liberation/plans/layer2-abm.md. Layer 1 says what the rules permit or force; this layer puts
`agents_per_role` simple adaptive agents under those rules and reports what they do, how often. Outputs are rates
over seeds, statements about an encoding plus a policy, never about real populations (ADR 0011).

Enabledness is never reimplemented here: `model.py` instantiates `rules_reference.Reference` on the institution and
asks it which action instances are powers (`Reference.power`, the ADR 0013 `(enabled ...)` reading) in the current
state, which must / must_not instances bind now, and uses its `successor` for effects. Anything the reference does
not define, the ABM does not know.

SLICE 1: `material` mechanism only, as the simplest payoff-following adoption; `coordination` and `imagination`
are stubs raising NotImplementedError. SLICE 2 (author decisions A3-A5, A7 in
computational-liberation/docs/decisions-pending.md): breach as a choice with graduated sanctions, directed trust,
the `_pledge` stand-in, `phil abm sweep`. SLICE 3: the veil-of-ignorance scorer (`score.py`: a probe agent
dropped in after stabilisation; freedom = exit / voice / recognition, flourishing = pleasure / meaning /
being-known, nulls excluded from sums and named) and the layer-2 gate (`gate.py`, `phil abm gate`): (a)
footbinding and (b) committed minority are BLOCKED until the institutions and the coordination module exist,
(c) kibbutz regendering and (d) seed stability run on the material module. The agent gained one additive
attribute, `last_choice_source`, so the scorer can read which rule of `choose` fired.

Design choices, each marked DECIDED (author decision cited) or ASSUMED (the plan's proposed default or the simplest
reading, awaiting author decision):

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
  breach            DECIDED (A4): a must is a choice. An agent breaches when an action's net payoff (payoff minus
                    the expected sanction of every rule the choice breaches) beats the best lawful net payoff. A
                    sanction exists iff the rule has `or_else`; a must with `or_else: null` is free to breach, and
                    a must_not with `or_else: null` is a disability `Reference.power` already removed, so
                    `forbidden_for` lists only sanctionable must_nots. The per-step charge while sanctioned is
                    sanction_weight * sanction_escalation ** (prior sanctionable breaches) (graduated), applied
                    to the realised payoff and the surplus for sanction_steps steps from the breach; the sanction
                    the agent EXPECTS before breaching is that charge times sanction_steps, so expectation and
                    realisation are one quantity (slice-2 review item a). ASSUMED within A4: no "belief that the
                    sanction lands" factor (monitoring is a later slice); breaching several rules at once sums
                    their expected sanctions but counts as one breach; a breach inside a running sanction window
                    replaces the window rather than stacking.
  state obligations DECIDED (A8, ADR 0015 amendment 2026-11-04, ASSUMED accepted): a `must-be P when C` rule
                    (ADR 0009) whose C holds obliges each agent in the rule's attribute role to choose an action
                    whose effects leave P true in the successor; choosing nothing keeps P iff P already holds.
                    Read locally (shared state plus this agent's own action, through `Reference.successor`;
                    A2 deferred). Breach is charged as an action-rule breach and feeds trust under A5 through
                    the fluent's declared `arg_roles`. Strict enabledness stands: a must-be no available action
                    can keep is an unavoidable breach, reported once per run in `warnings`. Must-not-be is read
                    symmetrically (ASSUMED). Musts that leave a role no lawful option are reported once per run
                    as an inconsistent encoding naming the rule ids (slice-2 review item d).
  choice order      ASSUMED (agent.py): lawful/breach candidate set > material floor collapse > success imitation
                    (copy_rate, only if the neighbour earned more) > material switch to a strictly better net-paying
                    candidate > same-role threshold (practice or pledge share) > material bootstrap argmax (no
                    usable practice) > keep (random obligation if none). Payoff-following sits BEFORE the threshold
                    rule, on purpose: under threshold-first a same-role convention at share 1.0 meets every
                    threshold in [0,1] and locks forever, so no payoff block could ever move it and the material
                    switch would be dead code. The alternative, a payoff-weighted share inside the threshold rule,
                    was rejected because it fuses the material and coordination mechanisms into one rule, and the
                    plan needs them as separable switches. With uniform payoffs the switch never fires and the
                    threshold rule alone governs, so the coordination reading is untouched in that regime.
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
  trust             DECIDED (A5): my trust in neighbour n moves only when n keeps (+delta) or breaches
                    (-beta*delta) an obligation bearing on me: the obligation instance's action has my role among
                    its non-actor arguments (instance args are role names, resolved from arg_roles / typing by the
                    reference). Obligations with no role argument move no trust. Clipped to [0,1]; carried, not
                    yet consumed (the assurance test is a later slice).
  pledge            DECIDED (A3, stand-in): an action named `X_pledge` with X declared is a pledge for X. Choosing
                    it sets the agent's public `pledge` to the X instance and leaves practice unchanged; same-role
                    neighbours' threshold shares count practice or pledge. Target per A3 is a public derived
                    fluent; the suffix convention is a magic string and is flagged as such.
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
                      sanction_weight  1.0   -> {0.0, 0.5, 1.0, 2.0, 5.0} (0.0 = sanctions exist but cost nothing)
                      sanction_steps   3     -> {1, 3, 5, 10}
                      sanction_escalation 1.5 -> {1.0, 1.5, 2.0} (1.0 = no graduation)
                    `phil abm sweep --param name=lo:hi:steps` runs these as grids (A7); payoff.<action> axes too.
                    plus graph k in {4, 6, 8} and p in {0.0, 0.1, 0.5} (plan open question 2: lattice / random).
"""
from .model import InstitutionModel, load_payoffs, run_abm
from .report import AbmReport, summarize
from .score import ProbeScore, score, score_run

__all__ = ["AbmReport", "InstitutionModel", "ProbeScore", "run_abm", "load_payoffs", "score", "score_run", "summarize"]
