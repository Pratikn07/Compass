# PRD: R4.7 Earnings-Call Transcript Summarization Capability

## Ownership

Owner: Ours

Drafting support: GPT/Gemini

## Objective

Define the requirements for fetching earnings-call transcripts and using a GPT model (e.g., OpenAI GPT-4o or GPT-4o-mini) to produce structured, token-efficient summaries. These summaries will validate theme drivers, automate peer commentary scoring, and enrich the analyst candidate brief without leaking raw, unbounded text into the execution hot path or the Claude analyst layer.

R4.7 answers:
```text
How can the system ingest massive, unstructured earnings-call transcripts, extract structured alignments with specific theme demand drivers, and summarize guidance/sentiment in a clean, schema-validated JSON format for downstream consumption?
```

---

## Background

Under R1.5 (Peer Result Scoring) and R2.5 (Claude as Analyst Only), `prescient` uses both quantitative metrics (EPS, revenue, price reactions) and qualitative commentary to evaluate candidates. Specifically, peer scoring includes:
* `+1 commentary confirms theme driver`
* `-1 commentary contradicts theme driver`

Currently, evaluating commentary relies on human inputs or is simplified due to the high risk of feeding raw transcripts (often 5,000–15,000 words) directly into the Claude analyst. Doing so would:
1. Exceed cost/token budgets rapidly.
2. Slower execution speeds and potentially hit API rate limits.
3. Degrade Claude's reasoning focus due to "lost in the middle" context issues.

R4.7 resolves this by introducing a read-only transcript adapter and a pluggable GPT-based summarizer. The summarizer parses raw transcript text, compares it against configured theme drivers, and returns a small, structured JSON summary. This summary is then consumed by the deterministic signal engine (to score peer commentary) and by the Claude Analyst (nested inside the structured `CandidateBrief`).

```text
  [Raw Transcript API]
           │
           ▼
[FmpTranscriptAdapter] (Normalized Transcript Model)
           │
           ▼
[GptTranscriptSummarizer] (Theme Drivers list injected)
           │
           ▼
[Normalized Transcript Summary Schema] (Structured JSON)
     ├───► [Deterministic Signal Engine] (Scoring: +1/-1 commentary confirms/contradicts)
     └───► [CandidateBrief] ──► [Claude Analyst] (Narrative context only)
```

---

## Functional Requirements

### R4.7.1 Pluggable Transcript Adapter Protocol
Following the R4.6 Pluggable Data Adapters standard, the data layer must define a structural interface (Protocol) for transcript providers inside `prescient.data.interfaces`.

#### 1. Transcript Provider Protocol
```python
from typing import Protocol, Optional
from datetime import datetime
from prescient.data.models import TranscriptResult

class TranscriptProvider(Protocol):
    def get_transcript(
        self,
        ticker: str,
        year: int,
        quarter: int,
        fetched_at: Optional[datetime] = None
    ) -> TranscriptResult:
        """Fetch raw earnings-call transcript text for a specific ticker, year, and quarter."""
        ...
```

#### 2. FMP Concrete Implementation
The system must provide `FmpTranscriptAdapter` as a concrete implementation fetching from Financial Modeling Prep's Earnings Call Transcript API:
* **Endpoint**: `https://financialmodelingprep.com/api/v3/earning_call_transcript/{ticker}?quarter={quarter}&year={year}&apikey={apikey}`
* The adapter must parse the response list (which typically contains transcript blocks with `quarter`, `year`, `date`, and `content`) and return a normalized `TranscriptResult`.

---

### R4.7.2 GPT Summarizer Protocol & Factory
The summarization capability must be abstracted to support pluggable LLM backends (e.g., OpenAI, local models, or mock implementations for testing).

#### 1. Summarizer Protocol
```python
from typing import Protocol, Sequence
from prescient.data.models import TranscriptResult, TranscriptSummary

class TranscriptSummarizer(Protocol):
    def summarize_transcript(
        self,
        transcript: TranscriptResult,
        theme_drivers: Sequence[str]
    ) -> TranscriptSummary:
        """Process raw transcript text using an LLM to extract a structured theme-aware summary."""
        ...
```

#### 2. Configuration Schema
Under `config/config.yaml`, the summarizer must be configuration-driven:
```yaml
summarizer:
  provider: "openai"       # "openai" | "mock"
  model: "gpt-4o-mini"     # gpt-4o, gpt-4o-mini, etc.
  temperature: 0.0         # Zero-temperature for deterministic extraction
  max_tokens: 1000
  api_key: "${OPENAI_API_KEY}"
```
If the API key is missing or invalid, runtime initialization must raise a structured `SummarizerConfigurationError`.

---

### R4.7.3 Normalized Transcript Summary Schema
The output from the GPT summarizer must validate against a strict Pydantic model (`TranscriptSummary`). The GPT model must be instructed (via system prompts and Structured Outputs/JSON Mode) to return a schema matching this structure:

```json
{
  "ticker": "NTAP",
  "quarter": 4,
  "year": 2026,
  "guidance_sentiment": "BULLISH | NEUTRAL | BEARISH | UNKNOWN",
  "driver_alignments": [
    {
      "driver": "AI data center demand",
      "status": "confirmed | contradicted | unmentioned",
      "summary": "Management highlighted robust demand for high-performance AI storage pipelines.",
      "supporting_quotes": [
        "We saw a doubling of our AI-optimized flash arrays pipeline this quarter..."
      ]
    }
  ],
  "management_tone": "confident | neutral | cautious | defensive",
  "key_takeaways": [
    "Enterprise storage flash arrays grew 15% YoY.",
    "AI-related business represented 8% of total bookings."
  ]
}
```

#### Validation Rules:
* `ticker`: Normalized to uppercase.
* `quarter`: Value must be in range `1..4`.
* `guidance_sentiment`: Restructured to uppercase enum.
* `status` in `driver_alignments`: Must map strictly to `confirmed`, `contradicted`, or `unmentioned`.
* Extra fields must be rejected to prevent hallucinated keys from polluting downstream models.

---

### R4.7.4 Integration with Peer Scoring & Analyst Brief

#### 1. Peer Commentary Score Integration (`prescient.signal.core`)
The deterministic signal engine must parse the `driver_alignments` of reported peers to compute the commentary score:
* A peer is scored `+1` (Commentary Confirms Theme Driver) if:
  * At least one theme driver has `"status": "confirmed"` AND no driver has `"status": "contradicted"`.
* A peer is scored `-1` (Commentary Contradicts Theme Driver) if:
  * At least one theme driver has `"status": "contradicted"`.
* A peer is scored `0` (Neutral/No impact) if all drivers are `"unmentioned"` or conflicting results are returned.

#### 2. Candidate Brief Handoff (`prescient.analyst`)
The structured summaries of the reported peers must be appended to the `CandidateBrief` sent to Claude:
* Claude must receive only the structured summaries (Pydantic objects) under a `peer_summaries` list.
* Claude must **never** receive the raw transcript contents, enforcing the boundary established in R2.5.1.

---

### R4.7.5 Safety, Cost, and Token Control

1. **Size Threshold Checks**:
   * Raw transcripts exceeding `150,000` characters (approx. 25,000 tokens) must be rejected with a `TranscriptTooLargeError` or truncated to the first `120,000` characters to prevent runaway token costs and model context limit overflows.
2. **Selective Execution (Gating)**:
   * Summarization must only run on demand when a candidate passes initial deterministic volume and liquidity filters, OR during scheduled pipelines for configured theme peers who reported within `peer_result_window_days`.
   * The system must not run GPT summarization on tickers outside the active user-defined themes.

---

### R4.7.6 Uniform Error Normalization
All failures originating from either the transcript provider API or the GPT summarization client must normalize into structured, journal-safe errors:

* **FMP Transcript Fetch Errors**:
  * `TRANSCRIPT_NOT_FOUND`: Transcript for the specified Q/Y does not exist.
  * `PROVIDER_TIMEOUT`: API call timed out.
  * `RATE_LIMIT_EXCEEDED`: API rate limit reached.
* **GPT Summarization Errors**:
  * `SUMMARIZER_RATE_LIMIT`: OpenAI API rate limit (HTTP 429).
  * `SUMMARIZER_TIMEOUT`: Request timed out.
  * `INVALID_SCHEMA_RESPONSE`: LLM returned JSON that does not match the Pydantic schema after retries.
  * `API_CREDENTIALS_EXPIRED`: Unauthorized client.

No raw API stack traces, HTTP request headers, or secrets (e.g. API keys) may leak into the log or database journal.

---

## Acceptance Criteria

1. **Protocols & Interfaces Defined**:
   * `TranscriptProvider` and `TranscriptSummarizer` exist in `prescient.data.interfaces`.
2. **Strict Schema Validation**:
   * Output from the summarizer is validated using Pydantic, rejecting any extra keys or incorrect enums.
3. **Commentary Scoring Automation**:
   * Integration tests prove that a simulated NTAP transcript confirming "AI data center demand" successfully generates a `+1` score in the peer scoring step.
4. **Claude Isolation Intact**:
   * Code audits confirm that no raw transcript strings are imported, read, or references passed to the Claude analyst module (`prescient.analyst`).
5. **Robust Error Handling**:
   * Tests verify that API timeouts, rate limits, and schema mismatches are captured and normalized without bubbling raw exceptions.
6. **Mocking Support**:
   * A `MockTranscriptProvider` and `MockTranscriptSummarizer` allow fully offline unit and integration tests without calling live APIs or spending LLM credits.

---

## Non-Goals

* **No Live Audio Processing**: No integration with transcription services (e.g., AssemblyAI, Whisper). The inputs are strictly pre-existing text transcripts.
* **No Multi-Agent Chat**: No interactive chat sessions allowing users to ask arbitrary questions against the transcript database.
* **No Hot-Path Trading Authority**: The summaries cannot override deterministic safety gates or trigger execution directly.
* **No Dynamic Theme Generation**: The GPT model must not create new drivers; it must only evaluate the transcript against the pre-configured theme drivers passed by the engine.

---

## Open Questions

> [!IMPORTANT]
> The following details should be aligned upon before finalize code construction:

1. **Missing Transcripts Fallback**: How should the strategy engine score a candidate if a major competitor has reported, but their transcript is not yet published on FMP? Should we score it as 0, or delay strategy evaluation?
2. **Q&A vs. Prepared Remarks**: Transcripts contain both a presentation segment and a Q&A segment. Should the summarization scan both, or prioritize prepared remarks where guidance is explicitly stated?
3. **Archiving Raw Data**: Do we store the full raw transcript text locally for compliance and downstream inspection, or do we only save the token-efficient summary JSON?

---

## Product FAQ

### Why use GPT for transcript summarization if the primary analyst is Claude?
GPT models (especially OpenAI's GPT-4o-mini) offer highly cost-effective, fast, and reliable structured JSON outputs for heavy document-processing workloads. Claude is saved for the higher-level synthetic analyst role, which requires interpreting the *final candidate brief* rather than parsing thousands of words of raw conference calls.

### What happens if the GPT model fails to return valid JSON?
The system logs a normalized `INVALID_SCHEMA_RESPONSE` error, scores the peer's commentary component as `0` (neutral), and proceeds with the rest of the deterministic strategy metrics so that a single GPT failure does not freeze the pipeline.

### Can this run continuously?
No. To minimize API costs, transcripts are fetched and summarized only when the scheduler triggers a scan for upcoming earnings candidates, or when a user requests a manual evaluation of a theme ticker.
