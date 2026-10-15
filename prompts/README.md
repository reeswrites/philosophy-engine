# Prompts

Versioned by filename: `<name>.<version>.md`. Never edit a released version in place; add `v2` and switch the caller.
Each file has `=== SYSTEM ===` and `=== USER ===` sections; variables are `{{ name }}` (plain substitution, see `philengine/prompts.py`: `load`, `render`, `split`, `load_split`).
The prompt hash logged in `llm_call` covers the rendered system + user + output schema.

| file | stage | variables | output |
|---|---|---|---|
| reconstruct.v1.md | reconstruct | name, author, work, source_text | `ReconstructionX` (5 premise types incl. metaphysical) |
| formalize.v1.md | formalize | reconstruction (numbered `[P1] text` lines, implicit marked), conclusion, retry_feedback (empty or validator errors) | `FormalizationX` (predicates/constants carry `gloss` template + `sense`) |
| judge.v1.md | judge | reconstruction, verbalization (`[P1] ...`, `[C] ...` lines produced mechanically from glosses) | `JudgeOut` (scores, conclusion_score, flags incl. hard-reject conditions) |

Hard-reject judge flags: `conclusion_smuggled`, `sense_drift`, `missing_implicit_premise` (`models_ext.HARD_REJECT_FLAGS`).
