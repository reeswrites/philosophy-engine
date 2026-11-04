# 0007. Dataset as clusters and minimal pairs, with a rediscovery gate

## Context
With about ten institutions, coverage cannot be the aim. The aim is to test whether the engine recovers findings we already trust, from the rules alone.

## Decision
The dataset is built as clusters and minimal pairs, so the engine must tell near-identical rule sets apart. The gate tests rediscovery of known findings: the care-plus-control cluster (police, child protective services, coverture household); one-rule pairs, such as ownership versus guardianship and property versus end-conversation; the kibbutz children's house and Happy the elephant as failures explained by implicit rules; and cosmetic-reform detection, where a renamed ownership role stays isomorphic to ownership while guardianship does not.

## Alternatives rejected
A broad sample with no expected answers: nothing to fail. Scoring against an LLM's opinion: not independent of the encoder.

## Consequences
Each entry needs a stated expectation before it is checked. A failed gate means the encoding or schema is wrong, not that the finding is. Cases are few, so passing the gate is evidence of fitness, not of general validity.

## Status
accepted
