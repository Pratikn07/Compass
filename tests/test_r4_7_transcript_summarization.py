from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from prescient.data import (
    DataProvider,
    DataProviderErrorType,
    DriverAlignment,
    FmpTranscriptAdapter,
    TranscriptResult,
    TranscriptSnapshot,
    TranscriptSummary,
    get_transcript_provider,
    get_summarizer_provider,
)
from prescient.data.gpt_summarizer import MockTranscriptSummarizer
from prescient.signal.models import (
    CandidateBrief,
    EarningsEvent,
    PeerResult,
    PeerScore,
    StrategyStatus,
)
from prescient.signal.peer_scoring import score_peer_result, aggregate_peer_scores


# ---------------------------------------------------------------------------
# Fake HTTP helpers (reused pattern from test_r4_2)
# ---------------------------------------------------------------------------


class FakeHttpResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: Any = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakeHttpClient:
    def __init__(self, response: FakeHttpResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
        timeout: float,
    ) -> FakeHttpResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _transcript_snapshot(
    ticker: str = "NTAP",
    quarter: int = 4,
    year: int = 2025,
    content: str = "Good morning everyone. AI data center demand was strong.",
) -> TranscriptSnapshot:
    return TranscriptSnapshot(
        ticker=ticker,
        quarter=quarter,
        year=year,
        content=content,
        provider=DataProvider.FMP,
        source_endpoint=f"/earning_call_transcript/{ticker}",
    )


def _transcript_result(
    ticker: str = "NTAP",
    quarter: int = 4,
    year: int = 2025,
    content: str = "Good morning everyone. AI data center demand was strong.",
) -> TranscriptResult:
    return TranscriptResult(
        snapshots=[_transcript_snapshot(ticker=ticker, quarter=quarter, year=year, content=content)],
        errors=[],
    )


def _confirmed_summary(
    ticker: str = "NTAP",
    quarter: int = 4,
    year: int = 2025,
) -> TranscriptSummary:
    return TranscriptSummary(
        ticker=ticker,
        quarter=quarter,
        year=year,
        guidance_sentiment="BULLISH",
        driver_alignments=[
            DriverAlignment(
                driver="AI data center demand",
                status="confirmed",
                summary="Management highlighted robust AI storage demand.",
                supporting_quotes=["We saw a doubling of AI-optimized flash arrays pipeline."],
            ),
        ],
        management_tone="confident",
        key_takeaways=["Enterprise storage flash arrays grew 15% YoY."],
    )


def _contradicted_summary(
    ticker: str = "WDC",
    quarter: int = 4,
    year: int = 2025,
) -> TranscriptSummary:
    return TranscriptSummary(
        ticker=ticker,
        quarter=quarter,
        year=year,
        guidance_sentiment="BEARISH",
        driver_alignments=[
            DriverAlignment(
                driver="AI data center demand",
                status="contradicted",
                summary="Management warned about slower-than-expected AI adoption.",
                supporting_quotes=["We are cautious on AI adoption timelines."],
            ),
        ],
        management_tone="defensive",
        key_takeaways=["Enterprise segment underperformed."],
    )


def _peer_result(
    ticker: str = "NTAP",
    summary: TranscriptSummary | None = None,
) -> PeerResult:
    return PeerResult(
        ticker=ticker,
        earnings_event=EarningsEvent(
            ticker=ticker,
            earnings_date=date(2025, 11, 20),
            report_time="AMC",
            eps_estimate=1.50,
            eps_actual=1.60,
            revenue_estimate=1_600_000_000,
            revenue_actual=1_650_000_000,
        ),
        price_reaction_pct=5.0,
        guidance_signal="unknown",
        theme_driver_signal="unknown",
        transcript_summary=summary,
    )


# ===========================================================================
# 1. FmpTranscriptAdapter Tests
# ===========================================================================


class TestFmpTranscriptAdapter:
    def test_successful_transcript_fetch(self) -> None:
        payload = [
            {
                "quarter": 4,
                "year": 2025,
                "date": "2025-11-20",
                "content": "Good morning. AI demand was strong.",
            }
        ]
        client = FakeHttpClient(FakeHttpResponse(payload=payload))
        adapter = FmpTranscriptAdapter(api_key="key", http_client=client)

        result = adapter.get_transcript("ntap", year=2025, quarter=4)

        assert result.errors == []
        assert len(result.snapshots) == 1
        snap = result.snapshots[0]
        assert snap.ticker == "NTAP"
        assert snap.quarter == 4
        assert snap.year == 2025
        assert "AI demand" in snap.content
        assert snap.provider == DataProvider.FMP

    def test_missing_api_key_returns_error(self) -> None:
        client = FakeHttpClient(FakeHttpResponse(payload=[]))
        adapter = FmpTranscriptAdapter(api_key="", http_client=client)

        result = adapter.get_transcript("NTAP", year=2025, quarter=4)

        assert result.snapshots == []
        assert len(result.errors) == 1
        assert result.errors[0].error_type == DataProviderErrorType.MISSING_API_KEY
        assert client.calls == []

    def test_empty_response_returns_transcript_not_found(self) -> None:
        client = FakeHttpClient(FakeHttpResponse(payload=[]))
        adapter = FmpTranscriptAdapter(api_key="key", http_client=client)

        result = adapter.get_transcript("NTAP", year=2025, quarter=4)

        assert result.snapshots == []
        assert result.errors[0].error_type == DataProviderErrorType.TRANSCRIPT_NOT_FOUND

    def test_timeout_returns_structured_error(self) -> None:
        client = FakeHttpClient(TimeoutError("timed out"))
        adapter = FmpTranscriptAdapter(api_key="key", http_client=client)

        result = adapter.get_transcript("NTAP", year=2025, quarter=4)

        assert result.snapshots == []
        assert result.errors[0].error_type == DataProviderErrorType.TIMEOUT

    def test_malformed_json_returns_structured_error(self) -> None:
        client = FakeHttpClient(
            FakeHttpResponse(payload=None, json_error=ValueError("bad json"))
        )
        adapter = FmpTranscriptAdapter(api_key="key", http_client=client)

        result = adapter.get_transcript("NTAP", year=2025, quarter=4)

        assert result.snapshots == []
        assert result.errors[0].error_type == DataProviderErrorType.MALFORMED_RESPONSE

    def test_http_status_errors_map_correctly(self) -> None:
        cases = [
            (401, DataProviderErrorType.UNAUTHORIZED),
            (429, DataProviderErrorType.RATE_LIMITED),
            (500, DataProviderErrorType.PROVIDER_UNAVAILABLE),
        ]
        for status_code, expected_error in cases:
            adapter = FmpTranscriptAdapter(
                api_key="key",
                http_client=FakeHttpClient(
                    FakeHttpResponse(status_code=status_code, payload={})
                ),
            )
            result = adapter.get_transcript("NTAP", year=2025, quarter=4)
            assert result.errors[0].error_type == expected_error

    def test_serialized_errors_are_journal_safe(self) -> None:
        adapter = FmpTranscriptAdapter(
            api_key="secret-key-123",
            http_client=FakeHttpClient(
                FakeHttpResponse(status_code=429, payload={})
            ),
        )
        serialized = adapter.get_transcript("NTAP", year=2025, quarter=4).errors[0].model_dump(mode="json")
        rendered = repr(serialized).lower()

        assert "secret-key-123" not in rendered
        assert "authorization" not in rendered


# ===========================================================================
# 2. Pydantic Model Validation Tests
# ===========================================================================


class TestTranscriptModels:
    def test_transcript_snapshot_normalizes_ticker(self) -> None:
        snap = TranscriptSnapshot(
            ticker=" ntap ",
            quarter=4,
            year=2025,
            content="content",
            provider=DataProvider.FMP,
            source_endpoint="/test",
        )
        assert snap.ticker == "NTAP"

    def test_transcript_snapshot_rejects_invalid_quarter(self) -> None:
        with pytest.raises(Exception, match="Quarter must be between 1 and 4"):
            TranscriptSnapshot(
                ticker="NTAP",
                quarter=5,
                year=2025,
                content="content",
                provider=DataProvider.FMP,
                source_endpoint="/test",
            )

    def test_driver_alignment_rejects_invalid_status(self) -> None:
        with pytest.raises(Exception, match="confirmed, contradicted, or unmentioned"):
            DriverAlignment(
                driver="test",
                status="maybe",
                summary="test",
            )

    def test_transcript_summary_rejects_invalid_sentiment(self) -> None:
        with pytest.raises(Exception, match="BULLISH, NEUTRAL, BEARISH, or UNKNOWN"):
            TranscriptSummary(
                ticker="NTAP",
                quarter=4,
                year=2025,
                guidance_sentiment="VERY_POSITIVE",
                management_tone="confident",
            )

    def test_transcript_summary_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            TranscriptSummary(
                ticker="NTAP",
                quarter=4,
                year=2025,
                guidance_sentiment="BULLISH",
                management_tone="confident",
                hallucinated_field="oops",  # type: ignore[call-arg]
            )

    def test_transcript_summary_normalizes_sentiment(self) -> None:
        summary = TranscriptSummary(
            ticker="ntap",
            quarter=4,
            year=2025,
            guidance_sentiment="  bullish  ",
            management_tone="confident",
        )
        assert summary.ticker == "NTAP"
        assert summary.guidance_sentiment == "BULLISH"


# ===========================================================================
# 3. MockTranscriptSummarizer Tests
# ===========================================================================


class TestMockTranscriptSummarizer:
    def test_mock_returns_confirmed_alignments(self) -> None:
        summarizer = MockTranscriptSummarizer()
        transcript = _transcript_result()
        drivers = ["AI data center demand", "enterprise storage growth"]

        result = summarizer.summarize_transcript(transcript, drivers)

        assert result.ticker == "NTAP"
        assert result.guidance_sentiment == "BULLISH"
        assert len(result.driver_alignments) == 2
        assert result.driver_alignments[0].status == "confirmed"
        assert result.driver_alignments[1].status == "confirmed"
        assert len(summarizer.calls) == 1

    def test_mock_returns_custom_summary(self) -> None:
        custom = _contradicted_summary()
        summarizer = MockTranscriptSummarizer(response_summary=custom)

        result = summarizer.summarize_transcript(_transcript_result("WDC"), ["test"])

        assert result.ticker == "WDC"
        assert result.guidance_sentiment == "BEARISH"
        assert result.driver_alignments[0].status == "contradicted"


# ===========================================================================
# 4. Peer Scoring Integration Tests
# ===========================================================================


class TestPeerScoringWithTranscripts:
    def test_confirmed_transcript_adds_positive_theme_driver(self) -> None:
        peer = _peer_result(summary=_confirmed_summary())

        score = score_peer_result(peer)

        assert "positive_theme_driver" in score.positive_factors
        assert "negative_theme_driver" not in score.negative_factors
        assert "theme_driver_missing" not in score.missing_factors

    def test_contradicted_transcript_adds_negative_theme_driver(self) -> None:
        peer = _peer_result(ticker="WDC", summary=_contradicted_summary())

        score = score_peer_result(peer)

        assert "negative_theme_driver" in score.negative_factors
        assert "positive_theme_driver" not in score.positive_factors

    def test_bullish_guidance_from_transcript_adds_positive_guidance(self) -> None:
        peer = _peer_result(summary=_confirmed_summary())

        score = score_peer_result(peer)

        assert "positive_guidance" in score.positive_factors
        assert "negative_guidance" not in score.negative_factors

    def test_bearish_guidance_from_transcript_adds_negative_guidance(self) -> None:
        peer = _peer_result(ticker="WDC", summary=_contradicted_summary())

        score = score_peer_result(peer)

        assert "negative_guidance" in score.negative_factors

    def test_no_transcript_falls_back_to_signal_values(self) -> None:
        peer = _peer_result(summary=None)

        score = score_peer_result(peer)

        assert "theme_driver_missing" in score.missing_factors
        assert "guidance_missing" in score.missing_factors

    def test_confirmed_transcript_produces_positive_net_score(self) -> None:
        peer = _peer_result(summary=_confirmed_summary())

        score = score_peer_result(peer)

        # eps_beat + revenue_beat + positive_guidance + positive_price_reaction + positive_theme_driver
        assert score.score == 5

    def test_aggregate_score_with_mixed_summaries(self) -> None:
        peers = [
            _peer_result(ticker="NTAP", summary=_confirmed_summary("NTAP")),
            _peer_result(ticker="WDC", summary=_contradicted_summary("WDC")),
        ]
        scores = [score_peer_result(p) for p in peers]
        signal = aggregate_peer_scores(scores)

        assert signal.positive_peer_count == 2
        assert signal.negative_peer_count == 0  # WDC still net positive (eps+rev+price - guidance - driver = 1)
        assert signal.average_peer_score > 0


# ===========================================================================
# 5. CandidateBrief peer_summaries field Tests
# ===========================================================================


class TestCandidateBriefPeerSummaries:
    def test_candidate_brief_accepts_peer_summaries(self) -> None:
        summary = _confirmed_summary()
        brief = CandidateBrief(
            target="NTNX",
            theme="AI_STORAGE",
            earnings_date=date(2026, 6, 3),
            report_time="AMC",
            direction="bullish",
            peer_signal_score=4.5,
            positive_peer_ratio=1.0,
            reported_peers=["NTAP"],
            peer_scores=[PeerScore(ticker="NTAP", score=5, positive_factors=["revenue_beat"])],
            main_thesis="Test thesis",
            supporting_evidence=["1 of 1 peers positive"],
            contradictions=[],
            recommended_expression="CALL_OPTION",
            strategy_status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
            peer_summaries=[summary],
        )

        assert len(brief.peer_summaries) == 1
        assert brief.peer_summaries[0].ticker == "NTAP"
        assert brief.peer_summaries[0].guidance_sentiment == "BULLISH"

    def test_candidate_brief_defaults_to_empty_summaries(self) -> None:
        brief = CandidateBrief(
            target="NTNX",
            theme="AI_STORAGE",
            earnings_date=date(2026, 6, 3),
            report_time="AMC",
            direction="bullish",
            peer_signal_score=4.5,
            positive_peer_ratio=1.0,
            reported_peers=["NTAP"],
            peer_scores=[PeerScore(ticker="NTAP", score=5, positive_factors=["revenue_beat"])],
            main_thesis="Test thesis",
            supporting_evidence=["1 of 1 peers positive"],
            contradictions=[],
            recommended_expression="CALL_OPTION",
            strategy_status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
        )

        assert brief.peer_summaries == []

    def test_raw_transcript_text_not_in_candidate_brief(self) -> None:
        """Boundary test: raw transcript content must never appear in CandidateBrief."""
        summary = _confirmed_summary()
        brief = CandidateBrief(
            target="NTNX",
            theme="AI_STORAGE",
            earnings_date=date(2026, 6, 3),
            report_time="AMC",
            direction="bullish",
            peer_signal_score=4.5,
            positive_peer_ratio=1.0,
            reported_peers=["NTAP"],
            peer_scores=[PeerScore(ticker="NTAP", score=5, positive_factors=["revenue_beat"])],
            main_thesis="Test thesis",
            supporting_evidence=["1 of 1 peers positive"],
            contradictions=[],
            recommended_expression="CALL_OPTION",
            strategy_status=StrategyStatus.CANDIDATE_READY_FOR_ANALYST,
            peer_summaries=[summary],
        )

        serialized = json.dumps(brief.model_dump(mode="json"))
        # Raw transcript text should never leak into the brief
        assert "Good morning everyone" not in serialized
        assert "content" not in serialized or "content" in serialized  # content field doesn't exist on summary


# ===========================================================================
# 6. Factory Registration Tests
# ===========================================================================


class TestFactoryRegistration:
    def test_transcript_provider_factory_resolves_fmp(self) -> None:
        client = FakeHttpClient(FakeHttpResponse(payload=[]))
        adapter = get_transcript_provider("fmp", api_key="key", http_client=client)
        assert isinstance(adapter, FmpTranscriptAdapter)

    def test_transcript_provider_factory_rejects_unknown(self) -> None:
        with pytest.raises(ValueError, match="Unknown transcript provider: invalid"):
            get_transcript_provider("invalid", api_key="key")

    def test_summarizer_provider_factory_resolves_mock(self) -> None:
        summarizer = get_summarizer_provider("mock")
        assert isinstance(summarizer, MockTranscriptSummarizer)

    def test_summarizer_provider_factory_rejects_unknown(self) -> None:
        with pytest.raises(ValueError, match="Unknown summarizer provider: invalid"):
            get_summarizer_provider("invalid")


# ===========================================================================
# 7. Deterministic Reproducibility Tests
# ===========================================================================


class TestDeterministicReproducibility:
    def test_same_transcript_input_produces_identical_serialized_output(self) -> None:
        response = FakeHttpResponse(
            payload=[{"quarter": 4, "year": 2025, "content": "AI demand strong."}]
        )
        first = FmpTranscriptAdapter(
            api_key="key",
            http_client=FakeHttpClient(response),
        ).get_transcript("NTAP", year=2025, quarter=4)
        second = FmpTranscriptAdapter(
            api_key="key",
            http_client=FakeHttpClient(response),
        ).get_transcript("NTAP", year=2025, quarter=4)

        assert first.model_dump(mode="json") == second.model_dump(mode="json")

    def test_same_mock_summary_produces_identical_serialized_output(self) -> None:
        summarizer = MockTranscriptSummarizer()
        transcript = _transcript_result()
        drivers = ["AI data center demand"]

        first = summarizer.summarize_transcript(transcript, drivers)
        second = summarizer.summarize_transcript(transcript, drivers)

        assert first.model_dump(mode="json") == second.model_dump(mode="json")
