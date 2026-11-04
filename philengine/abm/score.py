"""Veil-of-ignorance scorer (plan: plans/layer2-abm.md, "Scoring (veil of ignorance)"; slice 3).

After stabilisation (the run's `steps`), a fresh agent is dropped into a random role and a random position (the
neighbourhood of a random existing agent) and the model replays `probe_steps` more steps with the probe acting as
an ordinary agent. Two vectors are read off the probe:

  freedom      exit         share of probe steps at whose start an UNSANCTIONED exit was enabled for the probe's
                            role. Read through the dataset convention that `can_exit` is a derived fluent
                            (ADR 0013): the step counts iff `Reference.atom(state, "can_exit", (role,))` holds and
                            at least one of the `(enabled a ...)` action instances its expression reads, with the
                            probe's role as actor, is not forbidden now by a sanctionable must_not
                            (`model.forbidden_for`). No derived fluent named `can_exit` -> null, with a reason. A
                            `can_exit` typed to another role reads false for the probe (0.0, noted), never null.
               voice        share of probe steps where a rule-change action was enabled. No encoding has an
                            action that changes rules, so this is null with a reason, never 0.
               recognition  share of probe steps where some rule's condition names the probe's role: the
                            condition's S-expression mentions the role name, or a variable the rule's `var_roles`
                            types to it. Static under the current schema (a rule's text does not change), so it is
                            0.0 or 1.0; kept as a share so a future rule-change action makes it move.
  flourishing  pleasure     mean realised payoff of the probe over the probe steps (`last_payoff`, sanctions
                            deducted).
               meaning      share of probe steps whose choice came from the probe's own threshold rule
                            (`last_choice_source == "threshold"`), not imitation, payoff-following, bootstrap or
                            keeping. The full source histogram is kept per seed.
               being_known  number of the probe's neighbours whose trust toward it exceeds TRUST_KNOWN (0.5) at
                            the end of the probe (ASSUMED: a count at the end, not a mean over steps; trust starts
                            at `initial_trust` = 0.5 so only trust the probe earned counts).

Sums exclude null components and say which were excluded. Every number `score()` reports is a mean over seeds
with the per-seed values kept (A7). `disagreement()` lists pairs of institutions that freedom and flourishing
rank oppositely. `spearman()` is a dependency-free rank correlation (average ranks on ties) for gate (d).

Isolation: the probe is created AFTER the main run, so every draw it causes (its threshold, its role, its
position, its choices) comes from `model.random` after the main run's draws; the base report taken before the
probe equals `run_abm` with the same seed. The probe is not in `model.by_role`, so adoption rates stay rates
over the original population.

ASSUMED: PROBE_STEPS = 10; TRUST_KNOWN = 0.5; the probe keeps the model's `agents_per_role` population and
enters as one more agent of its role (shares among its same-role neighbours include it from the next step).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .. import sexpr as sx
from ..schemas_rules import InstitutionJSON
from .agent import ActionInst, InstitutionAgent
from .model import DEFAULT_AGENTS_PER_ROLE, DEFAULT_STEPS, InstitutionModel
from .report import AbmReport

PROBE_STEPS = 10
TRUST_KNOWN = 0.5
EXIT_FLUENT = "can_exit"
FREEDOM = ("exit", "voice", "recognition")
FLOURISHING = ("pleasure", "meaning", "being_known")
VOICE_NULL = ("no encoding has a rule-change action (no action's effects alter rules), so voice cannot be "
              "measured; null, not 0")


@dataclass
class ProbeScore:
    institution: str
    seed: int
    role: str
    host: int  # unique_id of the agent whose neighbourhood the probe joined (its random position)
    probe_steps: int
    freedom: dict[str, float | None]
    flourishing: dict[str, float | None]
    nulls: dict[str, str] = field(default_factory=dict)  # component -> why it is null
    notes: dict[str, str] = field(default_factory=dict)
    choice_sources: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"institution": self.institution, "seed": self.seed, "role": self.role, "host": self.host,
                "probe_steps": self.probe_steps, "freedom": dict(self.freedom), "flourishing": dict(self.flourishing),
                "freedom_sum": _sum(self.freedom), "flourishing_sum": _sum(self.flourishing),
                "total": _sum({**self.freedom, **self.flourishing}), "nulls": dict(self.nulls),
                "notes": dict(self.notes), "choice_sources": dict(self.choice_sources)}


def _sum(vec: dict[str, float | None]) -> dict:
    excluded = sorted(k for k, v in vec.items() if v is None)
    return {"value": sum(v for v in vec.values() if v is not None), "excluded": excluded}


# ------------------------------------------------------------------ readings of the encoding
def _syms(ast) -> set[str]:
    """Every symbol name mentioned in a condition AST (variables, literal roles, propositional atoms)."""
    out: set[str] = set()
    if isinstance(ast, sx.Sym):
        out.add(ast.name)
    elif isinstance(ast, sx.App):
        for a in ast.args:
            out |= _syms(a)
    elif isinstance(ast, sx.Not):
        out |= _syms(ast.arg)
    elif isinstance(ast, (sx.And, sx.Or)):
        for a in ast.args:
            out |= _syms(a)
    elif isinstance(ast, (sx.Implies, sx.Iff, sx.Eq)):
        out |= _syms(ast.left) | _syms(ast.right)
    elif isinstance(ast, sx.Quant):
        out |= _syms(ast.body)
    return out


def recognised(inst: InstitutionJSON, role: str) -> bool:
    """Does some rule's condition name `role` (literally, or through a `var_roles`-typed variable)?"""
    for r in inst.rules:
        c = (r.conditions or "").strip()
        if not c or c == "true":
            continue
        try:
            names = _syms(sx.parse(c))
        except Exception:  # a condition the parser rejects names nothing we can read
            continue
        if role in names or any(r.var_roles.get(n) == role for n in names):
            return True
    return False


def exit_reader(model: InstitutionModel, role: str):
    """(callable state -> bool, note or None) reading an unsanctioned exit for `role` through `can_exit`, or
    (None, reason) when the encoding has no derived `can_exit`."""
    ref = model.ref
    if EXIT_FLUENT not in ref.derived:
        return None, f"no derived fluent named {EXIT_FLUENT!r} in {model.inst.id}: exit is unmeasurable (null)"
    params, ast = ref.derived[EXIT_FLUENT]
    decl = ref.fluents[EXIT_FLUENT]
    args = tuple(decl.arg_roles) if decl.arg_roles else (role,) * decl.arity
    note = None
    if decl.arg_roles and role not in decl.arg_roles:
        note = f"{EXIT_FLUENT} is typed to {list(decl.arg_roles)}, not {role!r}: no exit is encoded for this role (0.0)"
    env = dict(zip(params, args))
    exit_insts: list[ActionInst] = []

    def collect(x):
        if isinstance(x, sx.App) and x.pred == "enabled":
            inst = (x.args[0].name, tuple(env.get(a.name, a.name) for a in x.args[1:]))
            if inst[1] and inst[1][0] == role:
                exit_insts.append(inst)
        elif isinstance(x, sx.App):
            pass
        elif isinstance(x, sx.Not):
            collect(x.arg)
        elif isinstance(x, (sx.And, sx.Or)):
            for a in x.args:
                collect(a)
        elif isinstance(x, (sx.Implies, sx.Iff)):
            collect(x.left); collect(x.right)
        elif isinstance(x, sx.Quant):
            collect(x.body)
    collect(ast)

    def read(state) -> bool:
        if not ref.atom(state, EXIT_FLUENT, args):
            return False
        if not exit_insts:
            return True
        forbidden = model.forbidden_for(role)
        return any(e not in forbidden for e in exit_insts)
    return read, note


# ------------------------------------------------------------------ the probe
def probe(model: InstitutionModel, probe_steps: int = PROBE_STEPS) -> ProbeScore:
    """Drop a fresh agent into `model` (already stabilised) and replay `probe_steps` steps. Every draw comes from
    `model.random` after the main run's draws."""
    if probe_steps < 1:
        raise ValueError("probe_steps must be >= 1")
    rng = model.random
    population = [a for members in model.by_role.values() for a in members]
    if not population:
        raise ValueError("cannot probe an empty population")
    role = rng.choice(list(model.roles))
    host = rng.choice(population)
    agent = InstitutionAgent(model, role)  # threshold drawn from model.random, after the main run
    agent.neighbours = [host] + [n for n in host.neighbours if n is not host]
    agent.role_neighbours = [n for n in agent.neighbours if n.role == role]
    for n in agent.neighbours:
        n.neighbours.append(agent)
        if n.role == role:
            n.role_neighbours.append(agent)
    read_exit, exit_note = exit_reader(model, role)
    rec = recognised(model.inst, role)
    nulls: dict[str, str] = {"voice": VOICE_NULL}
    notes: dict[str, str] = {}
    if read_exit is None:
        nulls["exit"] = exit_note or "exit unmeasurable"
    elif exit_note:
        notes["exit"] = exit_note
    exit_hits = rec_hits = 0
    payoffs: list[float] = []
    sources: dict[str, int] = {}
    for _ in range(probe_steps):
        if read_exit is not None and read_exit(model.state):
            exit_hits += 1
        rec_hits += int(rec)
        model.step()
        payoffs.append(agent.last_payoff)
        src = getattr(agent, "last_choice_source", "none")
        sources[src] = sources.get(src, 0) + 1
    init_trust = model.params["initial_trust"]
    known = sum(1 for n in agent.neighbours if n.trust.get(agent.unique_id, init_trust) > TRUST_KNOWN)
    freedom = {"exit": None if read_exit is None else exit_hits / probe_steps, "voice": None,
               "recognition": rec_hits / probe_steps}
    flourishing = {"pleasure": sum(payoffs) / probe_steps, "meaning": sources.get("threshold", 0) / probe_steps,
                   "being_known": float(known)}
    return ProbeScore(model.inst.id, model.seed_value, role, host.unique_id, probe_steps, freedom, flourishing,
                      nulls, notes, sources)


def score_run(inst: InstitutionJSON, seed: int = 0, steps: int = DEFAULT_STEPS, probe_steps: int = PROBE_STEPS,
              agents_per_role: int = DEFAULT_AGENTS_PER_ROLE, modules=("material",),
              payoffs: dict[str, float] | None = None, params: dict | None = None) -> tuple[AbmReport, ProbeScore]:
    """(base report of the stabilisation run, identical to `run_abm` with the same arguments; probe score)."""
    m = InstitutionModel(inst, seed=seed, agents_per_role=agents_per_role, modules=modules, payoffs=payoffs,
                         params=params)
    for _ in range(steps):
        m.step()
    base = m.report()
    return base, probe(m, probe_steps)


def _mean_or_null(values: list[float | None]) -> float | None:
    if any(v is None for v in values) or not values:
        return None
    return sum(values) / len(values)


def summarize_scores(scores: list[ProbeScore]) -> dict:
    """Means over seeds of both vectors, their sums (nulls excluded and named), per-seed values kept."""
    if not scores:
        raise ValueError("no scores to summarise")
    freedom = {k: _mean_or_null([s.freedom.get(k) for s in scores]) for k in FREEDOM}
    flourishing = {k: _mean_or_null([s.flourishing.get(k) for s in scores]) for k in FLOURISHING}
    nulls: dict[str, str] = {}
    notes: dict[str, str] = {}
    for s in scores:
        for k, v in s.nulls.items():
            nulls.setdefault(k, v)
        for k, v in s.notes.items():
            notes.setdefault(k, v)
    roles: dict[str, int] = {}
    for s in scores:
        roles[s.role] = roles.get(s.role, 0) + 1
    return {"institution": scores[0].institution, "seeds": [s.seed for s in scores],
            "probe_steps": scores[0].probe_steps, "freedom": freedom, "flourishing": flourishing,
            "freedom_sum": _sum(freedom), "flourishing_sum": _sum(flourishing), "total": _sum({**freedom, **flourishing}),
            "nulls": nulls, "notes": notes, "probe_roles": dict(sorted(roles.items())),
            "per_seed": [s.to_dict() for s in scores]}


def score(inst: InstitutionJSON, seeds: int, steps: int = DEFAULT_STEPS, probe_steps: int = PROBE_STEPS,
          agents_per_role: int = DEFAULT_AGENTS_PER_ROLE, modules=("material",),
          payoffs: dict[str, float] | None = None, params: dict | None = None) -> dict:
    """Score an institution over seeds 0..seeds-1 (A7: rates over seeds, per-seed values kept)."""
    if seeds < 1:
        raise ValueError("seeds must be >= 1")
    scores = [score_run(inst, seed=s, steps=steps, probe_steps=probe_steps, agents_per_role=agents_per_role,
                        modules=modules, payoffs=payoffs, params=params)[1] for s in range(seeds)]
    out = summarize_scores(scores)
    out.update(steps=steps, modules=list(modules))
    return out


# ------------------------------------------------------------------ comparisons
def disagreement(summaries: list[dict]) -> list[dict]:
    """Pairs of institutions that freedom and flourishing rank oppositely (strictly), by their summed vectors."""
    out = []
    for i, a in enumerate(summaries):
        for b in summaries[i + 1:]:
            fa, fb = a["freedom_sum"]["value"], b["freedom_sum"]["value"]
            ga, gb = a["flourishing_sum"]["value"], b["flourishing_sum"]["value"]
            if (fa > fb and ga < gb) or (fa < fb and ga > gb):
                out.append({"a": a["institution"], "b": b["institution"], "freedom": [fa, fb],
                            "flourishing": [ga, gb]})
    return out


def ranks(values: list[float]) -> list[float]:
    """Average ranks (1-based), ties share the mean of the ranks they span."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = r
        i = j + 1
    return out


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation (Pearson on average ranks). None when either side has no variance or n < 2."""
    if len(xs) != len(ys):
        raise ValueError("spearman: lengths differ")
    n = len(xs)
    if n < 2:
        return None
    rx, ry = ranks(list(xs)), ranks(list(ys))
    mx, my = sum(rx) / n, sum(ry) / n
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    return sxy / math.sqrt(sxx * syy)
