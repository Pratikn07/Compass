# prescient.edge - Edge-Measurement Backtest Harness

Disprove-first, implied-move-aware backtest. See
`docs/superpowers/specs/2026-06-05-edge-measurement-backtest-harness-design.md`.

Pipeline: universe -> point-in-time contexts (no lookahead) -> strategies
(reaction-aware peer + coin-flip + always-up) -> event scorer (direction,
beat-implied, IV-crush+cost option P&L) -> scorecards with survival verdict +
sample-size label.

Survival rule: a strategy survives only if its beat-implied rate exceeds BOTH
baselines by a margin AND has enough evaluable events. Free-data-first; paid data
must prove itself via `scripts/edge_data_probe.py` findings before becoming a
dependency.
