# Contributing

## Tests
```
uv sync
uv run pytest -q -m "not llm"      # offline; live tests need ANTHROPIC_API_KEY and `-m llm`
uv run phil rules check-all
uv run phil rules gate             # informational for now
```

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
