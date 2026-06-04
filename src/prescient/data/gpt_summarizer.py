from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from openai import OpenAI, OpenAIError, APIStatusError, APITimeoutError, APIConnectionError
from pydantic import ValidationError

from prescient.data.models import (
    TranscriptResult,
    TranscriptSummary,
    DriverAlignment,
)


class GptTranscriptSummarizer:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        max_tokens: int = 1000,
        openai_client: Any | None = None,
    ) -> None:
        key = api_key or __import__("os").environ.get("OPENAI_API_KEY") or ""
        self._api_key = key.strip()
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

        if openai_client is not None:
            self._client = openai_client
        else:
            self._client = OpenAI(api_key=self._api_key) if self._api_key else None

    def summarize_transcript(
        self,
        transcript: TranscriptResult,
        theme_drivers: Sequence[str],
    ) -> TranscriptSummary:
        if not transcript.snapshots:
            raise ValueError("No transcript snapshot available to summarize.")

        snapshot = transcript.snapshots[0]
        ticker = snapshot.ticker
        quarter = snapshot.quarter
        year = snapshot.year
        content = snapshot.content

        # Size check/truncation:
        if len(content) > 150_000:
            content = content[:120_000]

        if not self._client:
            raise ValueError("OpenAI API key is missing. Cannot perform summarization.")

        prompt = f"""
You are an expert financial analyst. Analyze the following earnings call transcript for {ticker} Q{quarter} {year}.

Your task is to identify and summarize details matching these pre-configured theme demand drivers:
{chr(10).join(f"- {d}" for d in theme_drivers)}

For each theme driver, determine if it was:
1. "confirmed": mentioned as a positive driver (e.g. strong demand, growth, positive outlook).
2. "contradicted": mentioned as a negative driver (e.g. demand drop, cost overrun, weak outlook).
3. "unmentioned": not mentioned at all.

Also extract the overall guidance sentiment (BULLISH, NEUTRAL, BEARISH, or UNKNOWN), management tone, and key takeaways.
Provide supporting quotes from the transcript where applicable.
"""

        try:
            completion = self._client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that returns structured JSON matching the requested schema.",
                    },
                    {"role": "user", "content": f"{prompt}\n\nTranscript:\n{content}"},
                ],
                response_format=TranscriptSummary,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            parsed_summary = completion.choices[0].message.parsed
            if parsed_summary is None:
                raise ValueError("LLM returned empty or malformed structured output.")
            return parsed_summary
        except ValidationError as e:
            raise ValueError(f"OpenAI response failed schema validation: {e}")
        except APITimeoutError as e:
            raise TimeoutError(f"OpenAI API request timed out: {e}")
        except APIConnectionError as e:
            raise ConnectionError(f"OpenAI API connection error: {e}")
        except APIStatusError as e:
            raise RuntimeError(f"OpenAI API status error: {e}")
        except OpenAIError as e:
            raise RuntimeError(f"OpenAI API error: {e}")


class MockTranscriptSummarizer:
    def __init__(
        self, *, response_summary: TranscriptSummary | None = None, **kwargs: Any
    ) -> None:
        self.response_summary = response_summary
        self.calls: list[tuple[TranscriptResult, Sequence[str]]] = []

    def summarize_transcript(
        self,
        transcript: TranscriptResult,
        theme_drivers: Sequence[str],
    ) -> TranscriptSummary:
        self.calls.append((transcript, theme_drivers))
        if self.response_summary is not None:
            return self.response_summary

        snapshot = transcript.snapshots[0]
        alignments = [
            DriverAlignment(
                driver=d,
                status="confirmed",
                summary=f"Mock summary for {d}",
                supporting_quotes=[f"Mock quote for {d}"],
            )
            for d in theme_drivers
        ]
        return TranscriptSummary(
            ticker=snapshot.ticker,
            quarter=snapshot.quarter,
            year=snapshot.year,
            guidance_sentiment="BULLISH",
            driver_alignments=alignments,
            management_tone="confident",
            key_takeaways=[f"Mock key takeaway 1 for {snapshot.ticker}"],
        )
