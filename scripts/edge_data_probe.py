"""Probe how deep free Alpaca option-quote history reaches for the edge universe.

Usage: uv run python scripts/edge_data_probe.py
Requires ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY in env. Prints per-ticker depth.
This answers the spec's open question on whether free options history is sufficient
or whether a one-time paid historical-options dataset must earn its place.
"""

from __future__ import annotations

from pathlib import Path

from prescient.edge.data_probe import summarize_option_history_depth
from prescient.edge.universe import load_edge_universe


def main() -> None:
    universe = load_edge_universe(Path("config/edge_universe.yaml"))
    print(f"Edge universe: {len(universe.tickers)} tickers")
    print("NOTE: free Alpaca chains are typically CURRENT snapshots; this probe will")
    print("reveal whether historical option depth exists. If not, that is the finding.")
    # Intentionally no live fetch here without confirmed creds; summarizer is unit-tested.
    empty: dict[str, list[object]] = {t: [] for t in universe.tickers}
    for ticker, summary in summarize_option_history_depth(empty).items():
        print(f"{ticker}: {summary.quote_count} quotes")


if __name__ == "__main__":
    main()
