# layer 2: agent-based Phase 1 plan

Agent-based layer over the same `InstitutionJSON` that `phil rules` checks. **Phase 1 scope:** instantiate simple
adaptive agents from `roles`, let them pick among rule-enabled actions, run three switchable mechanism modules
(material, coordination, imagination), score runs under a veil of ignorance, and backtest four historical cases.
Layer 1 says what rules permit or force (ADR 0004); this layer says what adaptive agents under those rules do, how
often, and which mechanism a change needed (`docs/intent.md`, "How change happens").

The question this phase answers: **given verified rules, which mechanism module is needed to reproduce a known
collapse, persistence or regendering, and do the rankings survive random seeds?**

Status: plan only (2026-11-03). No code until the handoff decisions are accepted.

## Handoff decisions

- **Same JSON, same enabledness.** The ABM reads `schemas_rules.InstitutionJSON` unchanged. An action is available
  at step t iff the ADR 0013 `enabled` reading says so; the ABM imports `rules_reference`'s reading and never
  reimplements rule semantics.
- **Frequency, not entailment.** Outputs are rates over seeds ("collapsed by step 40 in 94/100 seeds"): statements
  about encodings plus a policy, not about real populations (ADR 0011).
- **Mechanisms are switches.** `material`, `coordination`, `imagination` are on/off; a run reports which subset was
  necessary (outcome fails with the switch off).
- **Modular additive scoring.** Freedom and flourishing reported separately and summed; disagreement is an output
  row, never resolved.
- **Expectations before runs**, written in the dataset, as in Phase 0.

## Design

**Framework: Python Mesa 3.x.** Same language as `philengine/`, so `enabled` is imported, not ported; `batch_run`
sweeps parameters over seeds into DataFrames; `model.rng` threads one seed through every agent; `AgentSet.shuffle_do`
is the random activation threshold models assume. Agents.jl is faster per step but would split the codebase and put
rule semantics behind an FFI. A few hundred agents over a few hundred steps runs in seconds.

**Agents.** One class parametrised by `RoleDecl.name`; `agents_per_role` (default 20) replaces layer 1's
one-agent-per-role domain. State: the institution's fluents for its tuple plus `trust` [0,1], `threshold` [0,1]
(drawn once per seed), `surplus` ≥ 0. Agents sit on a Watts–Strogatz graph (k=6, p=0.1); neighbours are the
reference group for every mechanism.

**Step.** An agent (a) lists enabled actions, (b) drops those a module forbids, (c) chooses: with probability
`copy_rate` it imitates the neighbour whose last action earned most (Axelrod-style success imitation); otherwise it
takes the action whose neighbour adoption share exceeds its `threshold` (Granovetter 1978), else keeps its practice.
`must` rules are followed unless expected gain from breach exceeds the `or_else` cost weighted by the agent's belief
that sanction will land.

**Trust.** Per-dyad `trust` rises by δ when a neighbour kept an obligation bearing on this agent and falls by βδ
(β>1) on betrayal, per the solidarity-modeling design: calibrated asymmetric trust, Ostrom-style light monitoring
(each agent observes a random sample of neighbours per step) and graduated sanctions (`or_else` cost escalates on
repeat breach, fires only if a monitor saw it). Trust feeds the assurance test below (Skyrms 2004: cooperation is
risk-dominated without assurance).

**Modules.**
- `material`: `surplus` accrues from income fluents and decays by a floor cost. Below `floor` the choice set
  collapses to current practice; scarcity narrows choice, a material floor widens it.
- `coordination`: actions tagged `coordinated` pay off only when neighbour share ≥ `threshold` (assurance game).
  A `pledge` action counts as adoption for neighbours' thresholds without changing practice; practice flips when
  pledged share crosses the threshold (Mackie 1996). A `committed_minority` fraction holds an action regardless of
  payoff (Centola et al. 2018).
- `imagination`: an agent can only choose actions it has a `script` for; seeing a neighbour act adds the script with
  probability `exposure_rate`. Off, every agent has every script.

Eight configurations; `necessary_modules` lists the minimal subsets under which the expected outcome occurs in
≥ 80% of seeds.

**Scoring (veil of ignorance).** After stabilisation, drop a fresh agent into a random role and position and replay
`L` steps. Freedom: share of steps where an unsanctioned exit action was enabled (exit), a rule-change action was
enabled (voice), some rule's condition named the agent's interest (recognition). Flourishing: mean realised payoff
(pleasure), share of steps chosen by own threshold rather than imitation (meaning), neighbours with trust > 0.5
toward it (being-known). Report both vectors, sums, and `disagreement` where freedom and flourishing rank a pair
oppositely.

**Reproducibility.** `phil abm run --inst ID --seeds 100 --modules m,c,i`, `phil abm sweep` (8 switch sets × seeds),
`phil abm gate`, mirroring `phil rules`. `AbmReport` JSON per run: seed, modules, parameters, per-step adoption
shares, final fluent rates, score vectors, `necessary_modules`. Seed 0 default; every draw from `model.rng`.

## Pass tests (`phil abm gate`)

(a) **Footbinding collapse** (Mackie 1996): a `footbinding` institution collapses within 60 steps in ≥ 80% of seeds
    iff `coordination` is on and pledge actions exist; with either absent it persists.
(b) **Committed minority without hand-tuning**: sweep `committed_minority` 0.05–0.50 on a naming-convention
    institution; pass iff adoption jumps > 0.5 between adjacent sweep points and no constant in the code sets the
    location. Centola's band (about a quarter) is recorded in the dataset, not asserted by the model.
(c) **Kibbutz regendering**: on `kibbutz-childrens-house` with the implicit assignment rule, `care_assigned_by_sex`
    rate rises toward 1; with it removed it stays flat under every module configuration.
(d) **Seed stability**: Spearman rank of institutions by summed score ≥ 0.9 between disjoint halves of ≥ 100
    seeds, for every switch set.

## Non-goals

- No LLM agents in Phase 1; rule-based policies until (d) passes.
- No simulated real populations or named groups (ADR 0011); roles are institutional sorts, not demographics.
- No forward claim about any real institution before layer 3 and passing backtests (ADR 0004).
- No fitting of trust, thresholds or payoffs to data; parameters are swept, not calibrated.

## Open questions

- Does `enabled` need per-agent typing beyond `arg_roles` when several agents share a role?
- Do (a)–(c) depend on the small-world graph? Rerun on lattice and random graphs.
- Where do payoffs live? Proposal: a `payoffs` block on the dataset entry, not on `InstitutionJSON`.
- Pledge actions: dataset convention or a first-class `ActionDecl` flag?

## Sources opened

Granovetter, "Threshold Models of Collective Behavior", AJS 1978. Centola, Becker, Brackbill, Baronchelli,
"Experimental evidence for tipping points in social convention", Science 360(6393):1116–1119, 2018. Mackie, "Ending
Footbinding and Infibulation: A Convention Account", ASR 61(6):999–1017, 1996. Skyrms, The Stag Hunt and the
Evolution of Social Structure, CUP 2004 (via the Economics & Philosophy review). Axelrod, The Evolution of
Cooperation, 1984 (imitation policy; not reopened). Mesa documentation, "Overview" (readthedocs, stable). Ostrom,
Governing the Commons, 1990 (monitoring, graduated sanctions; via project glossary).
