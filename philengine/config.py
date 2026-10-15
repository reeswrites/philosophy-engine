"""Paths, model ids, thresholds, .env loader (hand-rolled, exo-style: existing env wins)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts"


def _resolve_dir(env_var: str, name: str) -> Path:
    """env var wins; else ./<name> if it exists in the CWD (a private instance); else the engine's own."""
    v = os.environ.get(env_var)
    if v:
        return Path(v).expanduser()
    cwd = Path.cwd() / name
    return cwd if cwd.is_dir() else ROOT / name


def data_dir() -> Path:
    """Data root (holds one subdirectory per family, each with arguments.json). Resolved at call time."""
    return _resolve_dir("PHIL_DATA_DIR", "data")


def runs_dir() -> Path:
    """Where run databases and reports live. Resolved at call time."""
    return _resolve_dir("PHIL_RUNS_DIR", "runs")


# Import-time snapshots, kept for convenience; prefer data_dir()/runs_dir() in code that may run from another cwd.
DATA_DIR = data_dir()
RUNS_DIR = runs_dir()


class ConfigError(RuntimeError):
    pass


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def load_env() -> None:
    """Read ./.env, then <engine root>/.env, then ~/.config/philengine/.env into os.environ; existing env wins."""
    for p in (Path.cwd() / ".env", ROOT / ".env", Path.home() / ".config" / "philengine" / ".env"):
        if p.is_file():
            for k, v in _parse_env_file(p).items():
                os.environ.setdefault(k, v)


# Models (env-overridable)
MODEL_REASON = os.environ.get("PHIL_MODEL_REASON", "claude-sonnet-5-5")
MODEL_JUDGE = os.environ.get("PHIL_MODEL_JUDGE", "claude-haiku-5-5")

# Z3
Z3_TIMEOUT_MS = 5000
Z3_RETRY_FACTOR = 3
Z3_SEED = 0

# Judge thresholds
JUDGE_MIN_SCORE = 0.6
JUDGE_MEAN_SCORE = 0.8
JUDGE_CONCLUSION_SCORE = 0.7
JUDGE_SAMPLES = 2   # judge calls per candidate (sample_idx 0..n-1); scores averaged, hard reject only if all flag it

# Candidate diversity: the SDK no longer takes temperature, so each candidate idx gets a fixed prompt hint.
STRATEGY_HINTS = (
    "Use the minimal set of predicates: reuse one predicate wherever the English allows it.",
    "Use the finest-grained predicates, and declare an explicit sort for every kind of thing (persons, acts, states, ...).",
    "Make every implicit premise its own formula: do not fold any background assumption into another premise.",
    "Prefer binary relations over unary predicates wherever the English relates two things.",
)

# Selection weights
UNKNOWN_PROBE_PENALTY = 0.10  # score deduction for a candidate with any z3-unknown probe
SUSPECT_BICONDITIONAL_PENALTY = 0.15  # implicit / non-definitional biconditional that carries C
ORPHAN_CONCLUSION_PENALTY = 0.10  # soft: a conclusion predicate that appears in no premise
SELECT_WEIGHTS = {"mean": 0.45, "min": 0.25, "minimal": 0.15, "simplicity": 0.10, "decided": 0.05}

# Stage defaults (overridable via Ctx.options)
N_CANDIDATES = 3
TEMP_RECONSTRUCT = 0.7
TEMP_FORMALIZE = 0.8
TEMP_JUDGE = 0.0
ISO_MAX_PREDS = 6          # brute-force predicate-bijection bound
ISO_MAX_PERMS = 5040       # hard cap on mappings tried per pair
