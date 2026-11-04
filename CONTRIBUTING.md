# Contributing

## Tests
```
uv sync
uv run pytest -q -m "not llm" -n auto   # fast: offline suite spread over the CPUs (pytest-xdist, dev group)
uv run pytest -q -m "not llm"           # serial: same suite, one process (the reference when a parallel run is odd)
uv run phil rules check-all
uv run phil rules gate                  # informational for now
```
Live tests need ANTHROPIC_API_KEY and `-m llm`. Every run prints its 15 slowest tests (`--durations=15` in
pyproject). Tests must not share temp paths or module globals: use `tmp_path` and `monkeypatch`, so the serial and
the `-n auto` runs both pass.

Layer-2 ABM commands (`phil abm run/sweep/score/gate`) take `--workers N` (default: the CPU count): seeds run over
N forked processes and the results are identical to `--workers 1`; only the reported `timing` moves.

## Adding an institution
1. Edit the generator in `data/institutions/` (`_gen_institutions.py`, `_gen_properties.py`); never hand-edit the generated JSON.
2. Write the expected verdicts **before** running anything. They are preregistrations.
3. Cite sources for every rule (statute, charter, bylaw). Mark anything you could not confirm `UNVERIFIED`.
4. Rerun the generator, then the checks and tests.
5. Do not edit expected verdicts to match results. If the engine disagrees, record the disagreement (and why) instead.

## Review step
Per [ADR 0012](docs/decisions/0012-participation-in-encoding.md), encodings should be reviewed by people who live under the institution. Disagreements are recorded as alternative rule sets in a `contested` list; diverging verdicts are reported, not resolved by the author. (The ADR is still "proposed".)

## Dual-use limits
Per [ADR 0011](docs/decisions/0011-dual-use-and-scope-limits.md): no encodings of named private individuals; no mode that searches for the cheapest way to keep a property violated or an exit revocable; no simulated populations standing in for marginalized groups without their participation. PRs that cross these lines will be declined.

## License
Contributions are accepted under Apache-2.0.
