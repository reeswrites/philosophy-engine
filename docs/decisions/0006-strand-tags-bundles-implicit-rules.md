# 0006. Strand tags, bundle types and implicit rules as first-class metadata

## Context
Rules differ in what holds them in a bundle. Some are rival inputs, some are superadditive, some tie one benefit to another. Bundles themselves are either contingent or constitutive. Unwritten norms, such as who is called first, are often the rules most worth contesting.

## Decision
Every rule carries `strand: rival | superadditive | tying`. Every bundle is tagged `contingent | constitutive`. Implicit rules are first-class (`implicit: true`) and counted at the select stage, as implicit premises are for arguments.

## Alternatives rejected
Keeping tags in prose notes: not queryable, not checkable. Encoding only written rules: misses the cases that motivate the project, such as the kibbutz and Happy the elephant.

## Consequences
Failure modes (dark twin, displacement, backlash, rebundling) can be written as properties. Open risk: tagging rules as tying could make care plus control isomorphic by construction, so the match would reflect our tags rather than the rules. This is an open question; the gate should include a case where the tags are withheld or shuffled.

## Status
accepted
