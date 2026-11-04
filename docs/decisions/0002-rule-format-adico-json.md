# 0002. Rule format: ADICO as our own JSON, borrowing IG Script tags

## Context
Each institution is a set of rules. Ostrom's Institutional Grammar (ADICO: Attribute, Deontic, aIm, Conditions, Or else) is the established way to state them. A survey of IG tooling is complete. IG Parser (https://github.com/chrfrantz/IG-Parser) exports only CSV and a tree, not JSON or XML. Its component text is free natural language, so grounding predicates is our work regardless. No public ADICO-coded corpus exists; the realistic path is hand-coding against the IG 2.0 Codebook (arXiv 2008.08937).

## Decision
Our own JSON is the canonical form. We borrow IG Script's component tags (A, D, I, Bdir, Bind, Cac, Cex, O), its [AND]/[OR]/[XOR] combinators, brace nesting, and its Core/Extended/Logico levels, so our JSON maps one-to-one. An IG Script reader may be added later as an optional front end.

## Alternatives rejected
Free-form predicates: no shared structure to compare. Deontic logic formulas: heavier, and poorly matched to the Z3 lowering we want. IG Script directly: no JSON export, and free-text components still need grounding.

## Consequences
We own the schema and its validation. Hand-coding is slow but is the only source of data. Staying tag-compatible keeps a later reader cheap.

## Status
accepted
