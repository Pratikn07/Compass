from __future__ import annotations

from prescient.journal import merge_source_citations, url_citation
from prescient.signal.models import PeerResult, PeerScore, PeerSignal, StrategySettings


_DEFAULT_SETTINGS = StrategySettings()


def score_peer_result(
    peer: PeerResult,
    settings: StrategySettings = _DEFAULT_SETTINGS,
) -> PeerScore:
    positive_factors: list[str] = []
    negative_factors: list[str] = []
    missing_factors: list[str] = []

    _score_estimate_actual_pair(
        estimate=peer.earnings_event.eps_estimate,
        actual=peer.earnings_event.eps_actual,
        positive_factor="eps_beat",
        negative_factor="eps_miss",
        missing_factor="eps_missing",
        positive_factors=positive_factors,
        negative_factors=negative_factors,
        missing_factors=missing_factors,
    )
    _score_estimate_actual_pair(
        estimate=peer.earnings_event.revenue_estimate,
        actual=peer.earnings_event.revenue_actual,
        positive_factor="revenue_beat",
        negative_factor="revenue_miss",
        missing_factor="revenue_missing",
        positive_factors=positive_factors,
        negative_factors=negative_factors,
        missing_factors=missing_factors,
    )
    # Guidance signal evaluation (from transcript summary if present)
    guidance_sig = peer.guidance_signal
    if peer.transcript_summary is not None:
        if peer.transcript_summary.guidance_sentiment == "BULLISH":
            guidance_sig = "positive"
        elif peer.transcript_summary.guidance_sentiment == "BEARISH":
            guidance_sig = "negative"
        elif peer.transcript_summary.guidance_sentiment == "NEUTRAL":
            guidance_sig = "neutral"
        else:
            guidance_sig = "unknown"

    _score_signal_value(
        signal=guidance_sig,
        positive_factor="positive_guidance",
        negative_factor="negative_guidance",
        missing_factor="guidance_missing",
        positive_factors=positive_factors,
        negative_factors=negative_factors,
        missing_factors=missing_factors,
    )
    _score_price_reaction(
        price_reaction_pct=peer.price_reaction_pct,
        settings=settings,
        positive_factors=positive_factors,
        negative_factors=negative_factors,
        missing_factors=missing_factors,
    )

    # Theme driver signal evaluation (from transcript summary if present)
    theme_driver_sig = peer.theme_driver_signal
    if peer.transcript_summary is not None:
        statuses = [alignment.status for alignment in peer.transcript_summary.driver_alignments]
        has_confirmed = any(s == "confirmed" for s in statuses)
        has_contradicted = any(s == "contradicted" for s in statuses)

        if has_contradicted:
            theme_driver_sig = "negative"
        elif has_confirmed:
            theme_driver_sig = "positive"
        else:
            theme_driver_sig = "neutral"

    _score_signal_value(
        signal=theme_driver_sig,
        positive_factor="positive_theme_driver",
        negative_factor="negative_theme_driver",
        missing_factor="theme_driver_missing",
        positive_factors=positive_factors,
        negative_factors=negative_factors,
        missing_factors=missing_factors,
    )

    return PeerScore(
        ticker=peer.ticker,
        score=len(positive_factors) - len(negative_factors),
        positive_factors=positive_factors,
        negative_factors=negative_factors,
        missing_factors=missing_factors,
        source_citations=merge_source_citations(
            peer.source_citations,
            peer.earnings_event.source_citations,
            peer.transcript_summary.source_citations
            if peer.transcript_summary is not None
            else [],
            [
                url_citation(
                    provider="peer_result_source",
                    source_type="peer_evidence_url",
                    url=url,
                    source_id=f"{peer.ticker}:{idx}",
                )
                for idx, url in enumerate(peer.source_urls)
            ],
        ),
    )


def aggregate_peer_scores(
    scores: list[PeerScore],
    settings: StrategySettings = _DEFAULT_SETTINGS,
) -> PeerSignal:
    if not scores:
        return PeerSignal(
            peer_scores=[],
            average_peer_score=0.0,
            positive_peer_count=0,
            negative_peer_count=0,
            positive_peer_ratio=0.0,
            missing_data_count=0,
            passes_thresholds=False,
        )

    positive_peer_count = sum(score.score > 0 for score in scores)
    negative_peer_count = sum(score.score < 0 for score in scores)
    average_peer_score = sum(score.score for score in scores) / len(scores)
    positive_peer_ratio = positive_peer_count / len(scores)
    missing_data_count = sum(len(score.missing_factors) for score in scores)

    return PeerSignal(
        peer_scores=scores,
        average_peer_score=average_peer_score,
        positive_peer_count=positive_peer_count,
        negative_peer_count=negative_peer_count,
        positive_peer_ratio=positive_peer_ratio,
        missing_data_count=missing_data_count,
        passes_thresholds=(
            positive_peer_ratio >= settings.min_positive_peer_ratio
            and average_peer_score >= settings.min_average_peer_score
        ),
    )


def _score_estimate_actual_pair(
    *,
    estimate: float | None,
    actual: float | None,
    positive_factor: str,
    negative_factor: str,
    missing_factor: str,
    positive_factors: list[str],
    negative_factors: list[str],
    missing_factors: list[str],
) -> None:
    if estimate is None or actual is None:
        missing_factors.append(missing_factor)
        return

    if actual > estimate:
        positive_factors.append(positive_factor)
    elif actual < estimate:
        negative_factors.append(negative_factor)


def _score_signal_value(
    *,
    signal: str,
    positive_factor: str,
    negative_factor: str,
    missing_factor: str,
    positive_factors: list[str],
    negative_factors: list[str],
    missing_factors: list[str],
) -> None:
    if signal == "positive":
        positive_factors.append(positive_factor)
    elif signal == "negative":
        negative_factors.append(negative_factor)
    elif signal == "unknown":
        missing_factors.append(missing_factor)


def _score_price_reaction(
    *,
    price_reaction_pct: float | None,
    settings: StrategySettings,
    positive_factors: list[str],
    negative_factors: list[str],
    missing_factors: list[str],
) -> None:
    if price_reaction_pct is None:
        missing_factors.append("price_reaction_missing")
        return

    if price_reaction_pct >= settings.positive_price_reaction_pct:
        positive_factors.append("positive_price_reaction")
    elif price_reaction_pct <= settings.negative_price_reaction_pct:
        negative_factors.append("negative_price_reaction")
